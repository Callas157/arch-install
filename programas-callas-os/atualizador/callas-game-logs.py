#!/usr/bin/python3
"""Bounded game diagnostics: coredump events, KWin hangs and manual collection.

No game injection, ptrace, core copies, USB policy changes or automatic Proton
launch-option changes. Only the fixed installed helper runs as the target user.
"""
import argparse
import configparser
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time

HELPER = '/usr/local/libexec/callas-game-logs'
PROC = Path('/proc')
POLICY = Path('/etc/callas-os/game-logs.ini')
SEEN = Path('/var/lib/callas-os/game-log-events.json')
CORE_ID = 'fc2e22bc6ee647b6b90729ab34a250b1'
BUS_NAME = 'io.github.Callas157.GameLogs'
MAX_INPUT = 2 * 1024**2
CHUNK = 384 * 1024


def clean(value, limit=160):
    return ''.join(c for c in str(value) if c.isprintable())[:limit].strip()


def selected_env(raw):
    # Never record the full environment (tokens, passwords and session secrets).
    values = {}
    for line in raw.replace(b'\0', b'\n').decode('utf-8', 'replace').splitlines():
        key, sep, value = line.partition('=')
        if sep and key in ('SteamAppId', 'SteamGameId', 'HEROIC_APP_NAME', 'LUTRIS_GAME_UUID'):
            values[key] = clean(value)
    return values


def identity(values, hint=''):
    for key in ('SteamAppId', 'SteamGameId'):
        value = values.get(key, '')
        if re.fullmatch(r'[1-9][0-9]{0,19}', value):
            return {'appid': value, 'name': 'Steam-' + value}
    match = re.search(r'(?:steam_app_|app-steam-app)([1-9][0-9]{0,19})(?:\D|$)', hint)
    if match:
        return {'appid': match[1], 'name': 'Steam-' + match[1]}
    for key in ('HEROIC_APP_NAME', 'LUTRIS_GAME_UUID'):
        if values.get(key): return {'appid': '', 'name': clean(values[key])}
    return None


def owned_process(pid, uid):
    try:
        return int(pid) > 1 and (PROC / str(int(pid))).stat().st_uid == uid
    except (OSError, ValueError, TypeError):
        return False


def process_game(pid, uid, hint=''):
    if not owned_process(pid, uid): return None
    try:
        with (PROC / str(int(pid)) / 'environ').open('rb') as stream:
            values = selected_env(stream.read(128 * 1024))
    except OSError:
        values = {}
    return identity(values, hint)


def bounded_command(argv, limit=CHUNK, timeout=12):
    # A file avoids building an unbounded stdout buffer in RAM.
    with tempfile.TemporaryFile() as output:
        try:
            result = subprocess.run(argv, stdout=output, stderr=subprocess.STDOUT,
                                    timeout=timeout, check=False)
            output.seek(0, 2); size = output.tell(); output.seek(max(0, size - limit))
            data = output.read(limit).decode('utf-8', 'replace')
            return ('[Trecho final; saída limitada]\n' if size > limit else '') + data + (
                '\n[Comando retornou código ' + str(result.returncode) + ']\n' if result.returncode else '')
        except (OSError, subprocess.TimeoutExpired) as exc:
            return '[Coleta indisponível: ' + clean(exc) + ']\n'


def steam_name(appid):
    if not re.fullmatch(r'[1-9][0-9]{0,19}', appid): return ''
    bases = [Path.home()/'.local/share/Steam', Path.home()/'.steam/steam',
             Path.home()/'.var/app/com.valvesoftware.Steam/.local/share/Steam']
    libraries = list(bases)
    for base in bases:
        file = base/'steamapps/libraryfolders.vdf'
        try:
            with file.open() as stream: text = stream.read(1024*1024)
            libraries += [Path(p.replace('\\\\', '\\')) for p in re.findall(r'"path"\s+"([^"]+)"', text)]
        except OSError: pass
    for base in libraries:
        try:
            with (base/'steamapps'/('appmanifest-'+appid+'.acf')).open() as stream: text = stream.read(128*1024)
            found = re.search(r'"name"\s+"([^"]+)"', text)
            if found: return clean(found[1])
        except OSError: pass
    return ''


def logs_module():
    path = Path('/usr/local/libexec/callas-logs')
    if not path.is_file(): path = Path(__file__).with_name('callas-logs.py')
    from importlib.machinery import SourceFileLoader
    loader = SourceFileLoader('callas_game_log_storage', str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec); loader.exec_module(module)
    return module


def policy():
    cfg = configparser.ConfigParser()
    try: cfg.read(POLICY)
    except configparser.Error: pass
    def number(key, default, low, high):
        try: return max(low, min(high, cfg.getint('Jogos', key, fallback=default)))
        except ValueError: return default
    return number('limit_mib', 64, 4, 128)*1024**2, number('retention_days', 30, 1, 30), number('files_per_game', 20, 1, 60)


def prune_games(base):
    limit, days, count = policy(); files = []
    for directory, dirs, names in os.walk(base, followlinks=False):
        dirs[:] = [n for n in dirs if not (Path(directory)/n).is_symlink()]
        group = []
        for name in names:
            p = Path(directory)/name
            if p.suffix != '.log' or p.is_symlink() or not p.is_file(): continue
            info = p.stat()
            if info.st_mtime < time.time()-days*86400: p.unlink(); continue
            group.append((info.st_mtime_ns, str(p), info.st_size))
        group.sort()
        for _, name, _ in group[:-count]: Path(name).unlink()
        files += group[-count:]
    total = sum(size for _, _, size in files)
    for _, name, size in sorted(files):
        if total <= limit: break
        Path(name).unlink(); total -= size


def receive(payload):
    if os.geteuid() == 0: raise ValueError('Documentos são escritos pelo próprio usuário')
    logs = logs_module()
    base = logs.prepare()/'Jogos'
    if base.is_symlink(): raise ValueError('Pasta Jogos simbólica; conteúdo preservado')
    base.mkdir(mode=0o700, exist_ok=True)
    game = payload['game']; appid = clean(game.get('appid', ''), 20)
    if appid and not re.fullmatch(r'[1-9][0-9]{0,19}', appid): raise ValueError('AppID inválido')
    title = steam_name(appid) or clean(game.get('name', 'Jogo não identificado'))
    slug = re.sub(r'[^\w .()-]', '-', title).strip(' .-')[:100] or 'Jogo'
    folder = base/(slug + (' ('+appid+')' if appid else ''))
    if folder.is_symlink(): raise ValueError('Pasta do jogo simbólica; conteúdo preservado')
    folder.mkdir(mode=0o700, exist_ok=True)
    chunks = [f"Jogo: {title}\nSteam AppID: {appid or 'não identificado'}\n"
              f"Motivo: {clean(payload.get('reason', 'manual'))}\n"
              f"Evento: {clean(payload.get('time', ''))}\nPID: {payload.get('pid', '')}\n",
              '=== Evento e processo ===\n'+str(payload.get('detail', ''))[:CHUNK],
              '=== Kernel, USB e GPU ===\n'+str(payload.get('kernel', ''))[:CHUNK],
              '=== Sessão do usuário (últimos 10 minutos) ===\n'+bounded_command(
                  ['journalctl', '--user', '-b', '--since=-10min', '-n', '1000', '--no-pager', '-o', 'short-iso'])]
    if appid:
        proton = Path.home()/('steam-'+appid+'.log')
        try:
            fd = os.open(proton, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid():
                    stream.seek(max(0, info.st_size-CHUNK))
                    chunks.append('=== Proton: trecho do arquivo existente; pode ser de outra execução ===\n'
                                  +stream.read(CHUNK).decode('utf-8', 'replace'))
        except OSError: pass
    data = logs.completed('\n'.join(chunks).encode('utf-8'))
    fd, path = logs.create_log(folder)
    with os.fdopen(fd, 'wb') as stream: stream.write(data)
    prune_games(base); logs.prune(logs.prepare())
    print('Diagnóstico salvo em:', path, flush=True)
    return path


def snapshot(account, game, pid, reason, detail=''):
    # Root never follows a user path or writes into the user's Documents folder.
    if os.geteuid() != 0 or account.pw_uid < 1000: raise ValueError('Usuário inválido')
    process = ''
    if owned_process(pid, account.pw_uid):
        process = bounded_command(['ps', '-L', '-p', str(int(pid)), '-o', 'pid,tid,stat,wchan:32,comm'], limit=64*1024)
    payload = dict(game=game, pid=pid, reason=reason, time=datetime.datetime.now().astimezone().isoformat(),
        detail=''.join(c for c in str(detail) if c.isprintable() or c in '\n\t')[:64*1024]+'\n'+process,
        kernel=bounded_command(['journalctl', '-k', '-b', '--since=-10min', '-n', '1500', '--no-pager', '-o', 'short-iso']))
    env = ['env', '-i', 'PATH=/usr/bin:/bin', 'HOME='+account.pw_dir, 'USER='+account.pw_name,
           'LOGNAME='+account.pw_name, 'LANG=C.UTF-8', 'XDG_RUNTIME_DIR=/run/user/'+str(account.pw_uid)]
    subprocess.run(['runuser', '-u', account.pw_name, '--', *env, HELPER, '--receive'],
                   input=json.dumps(payload).encode(), timeout=45, check=True)


def event_game(event, uid):
    if event.get('MESSAGE_ID') == CORE_ID:
        if event.get('COREDUMP_UID') != str(uid): return None
        raw = event.get('COREDUMP_ENVIRON', '')
        if isinstance(raw, list):
            raw = bytes(raw).decode('utf-8', 'replace') if all(isinstance(n, int) and 0 <= n <= 255 for n in raw) else '\n'.join(str(n) for n in raw)
        return identity(selected_env(str(raw).encode()), str(event.get('COREDUMP_CGROUP', '')))
    if event.get('_UID') != str(uid) or event.get('SYSLOG_IDENTIFIER') != 'callas-game-event': return None
    try:
        data = json.loads(event.get('MESSAGE', ''))
        if not isinstance(data, dict) or data.get('reason') != 'KDE: jogo não respondendo': return None
        pid = int(data['pid'])
        # No root read of arbitrary user-provided paths. Only /proc of this UID.
        found = process_game(pid, uid, clean(data.get('class', '')))
        if found: return found
        # KWin may have been killed already by the time the journal is read.
        # _UID is assigned by journald, so only this account can submit its own
        # diagnostic metadata. No path or command from the event is executed.
        game = data.get('game', {})
        if not isinstance(game, dict): return None
        found = identity({'SteamAppId':str(game.get('appid', ''))}, clean(data.get('class', '')))
        if found: return found
        if clean(game.get('name', '')): return {'appid':'', 'name':clean(game['name'])}
        return None
    except (ValueError, KeyError, TypeError): return None


def handle_event(event, account, seen):
    game = event_game(event, account.pw_uid)
    if not game: return False
    key = hashlib.sha256(str(event.get('__CURSOR', json.dumps(event, sort_keys=True))).encode()).hexdigest()
    if key in seen: return False
    if event.get('MESSAGE_ID') == CORE_ID:
        pid = event.get('COREDUMP_PID', ''); reason = 'Sistema: falha com coredump'
        detail = '\n'.join(k+'='+str(event.get(k, ''))[:16000 if k=='MESSAGE' else 800] for k in
            ('COREDUMP_COMM', 'COREDUMP_EXE', 'COREDUMP_SIGNAL', 'COREDUMP_USER_UNIT', 'MESSAGE'))
    else:
        data = json.loads(event['MESSAGE']); pid = data['pid']; reason = data['reason']
        detail = 'Janela: '+clean(data.get('title', ''))
    dedupe = 'recent:'+str(game.get('appid') or game['name'])+':'+str(pid)
    if time.time()-seen.get(dedupe, 0) < 120: return False
    snapshot(account, game, pid, reason, detail)
    seen[key] = time.time()
    seen[dedupe] = time.time()
    return True


def watch_system():
    if os.geteuid() != 0: raise ValueError('Monitor do journal requer root')
    user = Path('/etc/callas-os/log-user').read_text().strip(); account = pwd.getpwnam(user)
    if account.pw_uid < 1000: raise ValueError('Usuário inválido')
    try: seen = json.loads(SEEN.read_text())
    except (OSError, ValueError): seen = {}
    if not isinstance(seen, dict): seen = {}
    seen = {k:v for k,v in seen.items() if isinstance(k, str) and isinstance(v, (int, float))}
    fields = '__CURSOR,MESSAGE_ID,MESSAGE,_UID,SYSLOG_IDENTIFIER,COREDUMP_UID,COREDUMP_PID,COREDUMP_COMM,COREDUMP_EXE,COREDUMP_SIGNAL,COREDUMP_CGROUP,COREDUMP_USER_UNIT,COREDUMP_ENVIRON'
    command = ['journalctl', '-b', '-f', '--since=-2min', '--no-pager', '-o', 'json', '--output-fields='+fields,
               'MESSAGE_ID='+CORE_ID, '+', 'SYSLOG_IDENTIFIER=callas-game-event', '_UID='+str(account.pw_uid)]
    child = subprocess.Popen(command, stdout=subprocess.PIPE)
    try:
        while True:
            raw = child.stdout.readline(MAX_INPUT+1)
            if not raw: break
            if not raw.endswith(b'\n'):
                while raw and not raw.endswith(b'\n'): raw = child.stdout.readline(MAX_INPUT+1)
                continue
            try:
                if handle_event(json.loads(raw), account, seen):
                    seen = dict(sorted(seen.items(), key=lambda pair: pair[1])[-256:])
                    atomic(SEEN, json.dumps(seen)+'\n', 0o600)
            except Exception as exc: print('Diagnóstico automático não concluído:', clean(exc), file=sys.stderr, flush=True)
        raise RuntimeError('O acompanhamento do journal foi interrompido')
    finally:
        child.terminate(); child.wait(timeout=5)


def kwin_script():
    return r'''const watched = new WeakSet(), reported = new WeakSet();
function observe(w) {
    if (watched.has(w)) return;
    watched.add(w);
    function report() {
        if (!w.unresponsive || !w.normalWindow || w.transient || reported.has(w)) return;
        reported.add(w);
        callDBus("io.github.Callas157.GameLogs", "/GameLogs", "io.github.Callas157.GameLogs", "Report",
            JSON.stringify({pid:Number(w.pid),class:String(w.resourceClass||""),title:String(w.caption||"").slice(0,160)}));
    }
    if (w.unresponsiveChanged) w.unresponsiveChanged.connect(report);
    report();
}
workspace.windowAdded.connect(observe);
const windows = typeof workspace.windowList === "function" ? workspace.windowList() : workspace.stackingOrder;
windows.forEach(observe);
'''


def watch_user():
    if os.geteuid() == 0: raise ValueError('Monitor KDE requer usuário normal')
    import dbus
    import dbus.service
    from dbus.mainloop.glib import DBusGMainLoop
    from gi.repository import GLib
    DBusGMainLoop(set_as_default=True); session = dbus.SessionBus()
    owner = dbus.service.BusName(BUS_NAME, session, do_not_queue=True)
    recent = {}
    class Receiver(dbus.service.Object):
        @dbus.service.method(BUS_NAME, in_signature='s', out_signature='')
        def Report(self, raw):
            if len(raw) > 4096: return
            try:
                data = json.loads(str(raw)); pid = int(data['pid'])
                game = process_game(pid, os.getuid(), clean(data.get('class', '')))
                if not game: return
                if time.monotonic()-recent.get(pid, -1000) < 120: return
                recent[pid] = time.monotonic()
                if len(recent) > 256: recent.pop(next(iter(recent)))
                event = dict(pid=pid, game=game, reason='KDE: jogo não respondendo',
                             title=clean(data.get('title', '')), **{'class':clean(data.get('class', ''))})
                subprocess.run(['logger', '-t', 'callas-game-event', '--', json.dumps(event)], check=True, timeout=3)
            except Exception as exc: print('Evento KDE ignorado:', clean(exc), file=sys.stderr, flush=True)
    receiver = Receiver(owner, '/GameLogs')
    state = Path(os.environ.get('XDG_RUNTIME_DIR', '/run/user/'+str(os.getuid())))/'callas-game-logs'
    state.mkdir(mode=0o700, exist_ok=True)
    path = state/'watch.js'; atomic(path, kwin_script(), 0o600)
    scripting = dbus.Interface(session.get_object('org.kde.KWin', '/Scripting'), 'org.kde.kwin.Scripting')
    name = 'callas-game-diagnostics'
    if scripting.isScriptLoaded(name): scripting.unloadScript(name)
    number = scripting.loadScript(str(path), name)
    if number < 0: raise RuntimeError('KWin não carregou o monitor de jogos')
    script = dbus.Interface(session.get_object('org.kde.KWin', '/Scripting/Script'+str(number)), 'org.kde.kwin.Script')
    loop = GLib.MainLoop()
    for sig in (signal.SIGTERM, signal.SIGINT): GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, lambda: (loop.quit(), False)[1])
    try:
        script.run(); print('Diagnóstico de jogos: monitor KDE ativo.', flush=True); loop.run()
    finally:
        scripting.unloadScript(name); receiver.remove_from_connection()


def atomic(path, text, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.callas-game-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream: stream.write(text)
        os.chmod(temp, mode); os.replace(temp, path)
    finally: Path(temp).unlink(missing_ok=True)


def install_system():
    if os.geteuid() != 0: raise ValueError('Instalação requer root')
    atomic(Path('/etc/systemd/system/callas-game-events.service'), '''[Unit]
Description=Diagnósticos de falhas em jogos Callas OS
After=systemd-journald.service
StartLimitIntervalSec=60
StartLimitBurst=5
[Service]
Type=simple
ExecStart=/usr/local/libexec/callas-game-logs --watch-system
Restart=on-failure
RestartSec=5
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=full
RestrictAddressFamilies=AF_UNIX
[Install]
WantedBy=multi-user.target
''')
    atomic(Path('/etc/systemd/user/callas-game-logs.service'), '''[Unit]
Description=Detectar jogos sem resposta no KDE
After=plasma-kwin_wayland.service
PartOf=graphical-session.target
StartLimitIntervalSec=60
StartLimitBurst=5
[Service]
Type=simple
ExecStart=/usr/local/libexec/callas-game-logs --watch-user
Restart=on-failure
RestartSec=5
''')
    atomic(Path('/etc/xdg/autostart/callas-game-logs.desktop'), '''[Desktop Entry]
Type=Application
Name=Diagnóstico de jogos Callas OS
Exec=/usr/bin/systemctl --user start callas-game-logs.service
OnlyShowIn=KDE;
NoDisplay=true
StartupNotify=false
X-KDE-autostart-phase=2
''')
    if not POLICY.exists(): atomic(POLICY, '[Jogos]\nlimit_mib=64\nretention_days=30\nfiles_per_game=20\n')
    chroot = subprocess.run(['systemd-detect-virt', '--chroot'], stdout=subprocess.DEVNULL).returncode == 0
    if chroot:
        subprocess.run(['systemctl', '--root=/', 'enable', 'callas-game-events.service'], check=True)
    else:
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
        subprocess.run(['systemctl', 'enable', 'callas-game-events.service'], check=True)
        subprocess.run(['systemctl', 'restart', 'callas-game-events.service'], check=True)


def collect(user):
    if os.geteuid() != 0: raise ValueError('Coleta completa requer autorização administrativa')
    account = pwd.getpwnam(user)
    if account.pw_uid < 1000: raise ValueError('Use um usuário normal')
    games = {}
    for entry in PROC.iterdir():
        if entry.name.isdigit():
            game = process_game(int(entry.name), account.pw_uid)
            if game:
                key = game.get('appid') or game['name']
                games.setdefault(key, (game, int(entry.name)))
    choices = list(games.values())
    for i, (game, pid) in enumerate(choices, 1): print(f"{i}. {game['name']} (PID {pid})")
    print('0. Outro jogo ou jogo já encerrado')
    answer = input('Escolha o jogo [0]: ').strip() or '0'
    if not answer.isdigit() or not 0 <= int(answer) <= len(choices): raise ValueError('Escolha inválida')
    if int(answer): game, pid = choices[int(answer)-1]
    else:
        name = clean(input('Nome do jogo: ')) or 'Jogo não identificado'
        value = input('PID, se ainda estiver aberto (Enter para ignorar): ').strip()
        pid = int(value) if value else 0
        if pid and not owned_process(pid, account.pw_uid): raise ValueError('PID não pertence ao usuário ou já encerrou')
        game = process_game(pid, account.pw_uid) or {'name':name, 'appid':''}
    snapshot(account, game, pid, 'Coleta manual solicitada pelo usuário')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    for name in ('install-system', 'watch-system', 'watch-user', 'receive'): group.add_argument('--'+name, action='store_true')
    group.add_argument('--collect', metavar='USUARIO')
    args = parser.parse_args()
    if args.install_system: install_system()
    elif args.watch_system: watch_system()
    elif args.watch_user: watch_user()
    elif args.receive:
        raw = sys.stdin.buffer.read(MAX_INPUT+1)
        if len(raw) > MAX_INPUT: raise ValueError('Diagnóstico excedeu o limite')
        receive(json.loads(raw))
    else: collect(args.collect)

if __name__ == '__main__':
    try: main()
    except Exception as exc:
        print('Diagnóstico de jogos:', clean(exc), file=sys.stderr)
        sys.exit(1)
