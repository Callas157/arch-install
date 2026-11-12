#!/usr/bin/env python3
"""Callas OS: automatic native KWin Remember rules, independent of monitor setup."""
import argparse
import configparser
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid

CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config')))
STATE = CONFIG / 'callas-os'


def run(*args):
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout



def atomic(path, text, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.callas-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(text)
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)



def outputs():
    data = json.loads(run('kscreen-doctor', '-j'))
    result = [o for o in data['outputs'] if o.get('connected') and o.get('enabled', True)]
    if not result:
        raise RuntimeError('Nenhum monitor ativo encontrado.')
    return result



def bus():
    import dbus
    return dbus.SessionBus()



def capture_windows():
    """Seed native Remember rules from live windows without changing their geometry.
    Snapshot transport is private to this invocation; KWin owns persistence afterward.
    """
    import dbus
    import dbus.service
    from dbus.mainloop.glib import DBusGMainLoop
    from gi.repository import GLib
    DBusGMainLoop(set_as_default=True)
    session = dbus.SessionBus(private=True)
    loop = GLib.MainLoop()
    received = []
    service = 'io.github.Callas157.Snapshot.p' + str(os.getpid())
    owner = dbus.service.BusName(service, session, do_not_queue=True)

    class Receiver(dbus.service.Object):
        @dbus.service.method('io.github.Callas157.Snapshot', in_signature='s', out_signature='')
        def accept(self, payload):
            received.append(json.loads(str(payload)))
            loop.quit()

    receiver = Receiver(owner, '/Snapshot')
    js = '''const result = [];
const windows = typeof workspace.windowList === "function" ? workspace.windowList() : workspace.stackingOrder;
windows.forEach(function(w) {
    if (!w.normalWindow || w.transient || !w.resourceClass) return;
    const g = w.frameGeometry;
    result.push({app: String(w.resourceClass).toLowerCase(), rawClass: String(w.resourceClass), role: String(w.windowRole || ""), output: String(w.output ? w.output.name : ""),
        x: Math.round(g.x), y: Math.round(g.y), width: Math.round(g.width), height: Math.round(g.height),
        maxH: (Number(w.maximizeMode) & 2) !== 0,
        maxV: (Number(w.maximizeMode) & 1) !== 0});
});
callDBus(SERVICE, "/Snapshot", "io.github.Callas157.Snapshot", "accept", JSON.stringify(result));
'''.replace('SERVICE', json.dumps(service))
    fd, name = tempfile.mkstemp(prefix='callas-snapshot-', suffix='.js')
    script_name = 'callas-snapshot-' + str(os.getpid())
    scripting = dbus.Interface(session.get_object('org.kde.KWin', '/Scripting'), 'org.kde.kwin.Scripting')
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(js)
        number = scripting.loadScript(name, script_name)
        if number < 0:
            raise RuntimeError('KWin não carregou a captura das janelas.')
        script = dbus.Interface(session.get_object('org.kde.KWin', '/Scripting/Script' + str(number)), 'org.kde.kwin.Script')
        script.run()
        def timeout():
            loop.quit()
            return False
        timer = GLib.timeout_add_seconds(10, timeout)
        loop.run()
        if received:
            GLib.source_remove(timer)
        else:
            raise RuntimeError('KWin não respondeu à captura; regras existentes preservadas.')
    finally:
        try:
            scripting.unloadScript(script_name)
        finally:
            Path(name).unlink(missing_ok=True)
            receiver.remove_from_connection()
            session.close()
    return received[0]



def remember_windows():
    try:
        windows = capture_windows()
    except Exception as exc:
        # Only snapshot errors use the fallback. Saving/reloading the rules
        # below remains required and errors propagate to the updater.
        message = 'Captura de janelas indisponível: ' + str(exc)
        print('Aviso:', message, file=sys.stderr)
        helper = Path('/usr/local/libexec/callas-logs')
        if helper.is_file():
            subprocess.run([str(helper), '--write', 'Janelas'], input=(message+'\n').encode(), check=False)
        windows = []
    before = discord_state(windows)
    try:
        remember_rules(windows)
    finally:
        log_discord_state(before, windows)


def repair_discord_rule(rule, sample, output_names):
    """Retire the unsuccessful geometry-request override, only for our Discord rule.

    Preserve learned size, position, screen and maximize state. No live window
    coordinates are promoted over learned values during this recovery.
    """
    if rule.get('wmclass') != 'discord' or not rule.get('Description', '').startswith('Callas OS: lembrar '):
        return 0
    if rule.get('ignoregeometry') == 'true' and rule.get('ignoregeometryrule') == '2':
        del rule['ignoregeometry']
        del rule['ignoregeometryrule']
        return 2
    return 0


def discord_state(windows):
    """Only placement metadata, never account settings, titles or conversations."""
    result = {'session': os.environ.get('XDG_SESSION_TYPE', ''), 'windows': [], 'rules': []}
    for w in windows:
        if 'discord' in str(w.get('app', '')).lower():
            result['windows'].append({k:w[k] for k in ('app','rawClass','role','output','x','y','width','height','maxH','maxV') if k in w})
    cfg = configparser.ConfigParser(interpolation=None, strict=True); cfg.optionxform = str
    try:
        cfg.read(CONFIG / 'kwinrulesrc')
        order = cfg.get('General', 'rules', fallback='').split(',')
        allowed = ('Description','wmclass','wmclassmatch','wmclasscomplete','types','windowrole','windowrolematch',
                   'position','positionrule','size','sizerule','screen','screenrule','maximizehoriz','maximizehorizrule',
                   'maximizevert','maximizevertrule','ignoregeometry','ignoregeometryrule')
        for section in cfg.sections():
            rule = cfg[section]
            if 'discord' in rule.get('wmclass', '').lower():
                values = {k:rule[k] for k in allowed if k in rule}
                # Descriptions may contain personal text; only mark project ownership.
                values['managed'] = rule.get('Description', '').startswith('Callas OS: lembrar ')
                values.pop('Description', None)
                values['order'] = order.index(section) if section in order else -1
                result['rules'].append(values)
    except (OSError, configparser.Error) as exc:
        result['rules_error'] = str(exc)
    try:
        result['outputs'] = [{k:o[k] for k in ('name','id','priority','pos','scale','connected','enabled') if k in o} for o in outputs()]
    except Exception as exc:
        result['outputs_error'] = str(exc)
    try:
        path = CONFIG / 'discord/settings.json'
        if path.is_file():
            with path.open() as stream: settings = json.loads(stream.read(1024*1024))
            bounds = {}
            for key in ('WINDOW_BOUNDS', 'windowBounds'):
                value = settings.get(key)
                if isinstance(value, dict):
                    bounds[key] = {k:value[k] for k in ('x','y','width','height','displayId') if isinstance(value.get(k), (int,float,str))}
            result['discord_bounds'] = bounds
    except (OSError, ValueError, AttributeError) as exc:
        result['bounds_error'] = type(exc).__name__
    return result


def log_discord_state(before, windows):
    helper = Path('/usr/local/libexec/callas-logs')
    if not helper.is_file(): return
    payload = {'before': before, 'rules_after': discord_state([])}
    text = 'Diagnóstico do Discord — janela capturada antes; regras antes/depois\n'+json.dumps(payload, ensure_ascii=False, indent=2)+'\n'
    try:
        result = subprocess.run([str(helper), '--write', 'Janelas'], input=text.encode(), check=False, timeout=5)
        if result.returncode:
            print('Aviso: não foi possível salvar o diagnóstico do Discord.', file=sys.stderr)
        else:
            print('Diagnóstico do Discord salvo em Documentos/Callas OS/Callas OS Logs/Janelas.')
    except (OSError, subprocess.TimeoutExpired) as exc:
        print('Aviso: diagnóstico do Discord indisponível:', exc, file=sys.stderr)


def remember_rules(windows):
    import dbus
    path = CONFIG / 'kwinrulesrc'
    cfg = configparser.ConfigParser(interpolation=None, strict=True)
    cfg.optionxform = str
    if path.exists():
        cfg.read(path)
    if not cfg.has_section('General'):
        cfg.add_section('General')
    ids = [s for s in cfg['General'].get('rules', '').split(',') if s]
    # Only the requested apps. Separate roles keep dialogs out of the main rule.
    targets = ('discord', 'spotify', 'brave', 'brave-browser')
    samples = {}
    counts = {}
    for w in windows:
        if w['app'] in targets:
            key = (w['app'], w['role'])
            counts[key] = counts.get(key, 0) + 1
            samples[key] = w
    names = [o['name'] for o in sorted(outputs(), key=lambda o: o.get('priority', 100))] if any(w.get('output') for w in samples.values()) else []
    added = 0
    for app in targets:
        entries = [(key, w) for key, w in samples.items() if key[0] == app]
        if not entries:
            entries = [((app, ''), None)]
        for (app, role), sample in entries:
            marker = 'Callas OS: lembrar ' + app + (' (' + role + ')' if role else '')
            # Do not overwrite learned values on updates or later invocations.
            existing = next((cfg[s] for s in cfg.sections() if cfg[s].get('Description', '').startswith('Callas OS: lembrar ') and cfg[s].get('wmclass') == app), None)
            if existing is not None:
                added += repair_discord_rule(existing,
                    sample if counts.get((app, role), 0) == 1 else None, names)
                # Bootstrap attributes for apps that were closed during installation.
                # Existing learned coordinates and state always take precedence.
                if sample and counts.get((app, role), 0) == 1:
                    missing = {'position': f"{sample['x']},{sample['y']}",
                               'size': f"{sample['width']},{sample['height']}"}
                    if 'maximizehorizrule' not in existing:
                        missing.update(maximizehorizrule='4', maximizehoriz=str(sample['maxH']).lower())
                    if 'maximizevertrule' not in existing:
                        missing.update(maximizevertrule='4', maximizevert=str(sample['maxV']).lower())
                    if 'screenrule' not in existing and sample.get('output') in names:
                        missing.update(screenrule='4', screen=str(names.index(sample['output'])))
                    for key, value in missing.items():
                        if key not in existing:
                            existing[key] = value
                            added += 1
                continue
            if counts.get((app, role), 0) > 1:
                print('Aviso:', app, 'tem várias janelas equivalentes; use Regras de janelas para diferenciá-las.')
                continue
            ident = str(uuid.uuid4())
            cfg[ident] = {'Description': marker, 'wmclass': app, 'wmclassmatch': '1',
                          'wmclasscomplete': 'false', 'types': '1', 'positionrule': '4', 'sizerule': '4'}
            rule = cfg[ident]
            if role:
                rule['windowrole'] = role
                rule['windowrolematch'] = '1'
            if sample:
                rule['position'] = f"{sample['x']},{sample['y']}"
                rule['size'] = f"{sample['width']},{sample['height']}"
                if sample.get('output') in names:
                    rule['screenrule'] = '4'
                    rule['screen'] = str(names.index(sample['output']))
                rule['maximizehorizrule'] = '4'
                rule['maximizevertrule'] = '4'
                rule['maximizehoriz'] = str(sample['maxH']).lower()
                rule['maximizevert'] = str(sample['maxV']).lower()
            repair_discord_rule(rule, sample, names)
            ids.append(ident)
            added += 1
    if not added:
        print('Regras já instaladas; posições aprendidas preservadas.')
        return
    cfg['General']['rules'] = ','.join(ids)
    cfg['General']['count'] = str(len(ids))
    import io
    out = io.StringIO()
    cfg.write(out, space_around_delimiters=False)
    backup_rules(path)
    atomic(path, out.getvalue())
    dbus.Interface(bus().get_object('org.kde.KWin', '/KWin'), 'org.kde.KWin').reconfigure()
    print('Memória de janelas ativada/atualizada. Valores aprendidos foram preservados.')
    print('Discord, Spotify e Brave: mova/redimensione suas janelas uma vez e feche normalmente para o KDE aprender.')
    if windows:
        print('As janelas abertas tiveram sua posição atual capturada; as fechadas serão aprendidas no uso normal.')



def backup_rules(path):
    if not path.is_file():
        return
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    dest = STATE / 'window-backups' / stamp
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest / 'kwinrulesrc')


def steam_dialog_script(output_name):
    """Route Steam's launch/progress dialogs only; never route game windows."""
    return r'''const preferredOutput = OUTPUT_NAME;
const watched = new WeakSet();
const moved = new WeakMap();
const reported = new WeakSet();
function steamClient(w) {
    const cls = String(w.resourceClass || "").toLowerCase();
    return cls === "steam" || cls === "steamwebhelper" || cls === "com.valvesoftware.steam";
}
function launchDialog(w) {
    if (!steamClient(w) || w.fullScreen) return false;
    const role = String(w.windowRole || "");
    const title = String(w.captionNormal || w.caption || "");
    return /^(?:(?:c?steam|c)[-_ ]?)?(?:game[-_ ]?launch|launch[-_ ]?game)(?:[-_ ]?(?:dialog|window|progress))?(?:[-_ :]*[0-9]+)?$/i.test(role)
        || /^(?:Steam\s*[-–:]\s*)?(?:Launching(?:\s+(?:game|a game))?|Iniciando\s+(?:o\s+)?jogo|Preparing\s+to\s+launch|Preparando\s+para\s+iniciar)(?:\s|[:.…-]|$)/i.test(title);
}
function route(w) {
    try {
        if (!w || !steamClient(w)) return;
        if (!reported.has(w)) {
            reported.add(w);
            print("CallasSteamDialog: " + JSON.stringify({app:String(w.resourceClass), role:String(w.windowRole || ""), title:String(w.captionNormal || w.caption || "").slice(0,160)}));
        }
        if (!launchDialog(w)) return;
        const outputs = workspace.screenOrder || workspace.screens || [];
        let target = null;
        for (let i=0; i<outputs.length; ++i) {
            if (String(outputs[i].name) === preferredOutput) target = outputs[i];
        }
        // KWin's screenOrder follows the configured primary ordering. Fall back
        // to its first active output if the saved connector was unplugged.
        if (!target && outputs.length) target = outputs[0];
        if (!target || (w.output && String(w.output.name) === String(target.name))) return;
        const count = moved.get(w) || 0;
        if (count >= 8) return; // Bound misbehaving-client reposition loops.
        moved.set(w,count+1);
        workspace.sendClientToScreen(w,target);
    } catch (error) {
        print("CallasSteamDialog: erro ao posicionar diálogo: " + String(error));
    }
}
function watch(w) {
    if (!w || watched.has(w)) return;
    watched.add(w);
    // Steam/CEF can set identity, caption and placement after windowAdded.
    [w.windowClassChanged,w.windowRoleChanged,w.captionChanged,w.outputChanged].forEach(function(signal) {
        if (signal && typeof signal.connect === "function") signal.connect(function(){route(w);});
    });
    route(w);
}
workspace.windowAdded.connect(watch);
const existing = typeof workspace.windowList === "function" ? workspace.windowList() : workspace.stackingOrder;
(existing || []).forEach(watch);
'''.replace('OUTPUT_NAME', json.dumps(output_name))


def start_steam_dialogs():
    if os.geteuid() == 0:
        raise RuntimeError('Diálogos Steam devem ser ajustados pelo usuário da sessão.')
    import fcntl
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / 'steam-dialogs.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        _load_steam_dialogs()


def _load_steam_dialogs():
    import dbus
    preferred = ''
    try:
        preferred = json.loads((STATE / 'monitors.json').read_text()).get('primary', '')
    except FileNotFoundError:
        pass
    if not isinstance(preferred, str):
        raise ValueError('Monitor principal salvo inválido.')
    code = steam_dialog_script(preferred)
    path = STATE / 'steam-dialogs.js'
    session = bus()
    scripting = dbus.Interface(session.get_object('org.kde.KWin', '/Scripting'), 'org.kde.kwin.Scripting')
    name = 'callas-steam-launch-dialogs'
    loaded = bool(scripting.isScriptLoaded(name))
    if loaded and path.is_file() and path.read_text() == code:
        return
    if loaded and not scripting.unloadScript(name):
        raise RuntimeError('KWin não descarregou o ajuste anterior de diálogos Steam.')
    atomic(path, code)
    number = int(scripting.loadScript(str(path), name))
    if number < 0:
        raise RuntimeError('KWin não carregou o ajuste dos diálogos Steam.')
    script = dbus.Interface(session.get_object('org.kde.KWin', '/Scripting/Script' + str(number)), 'org.kde.kwin.Script')
    script.run()
    print('Diálogos de inicialização da Steam: direcionamento ao monitor principal ativado.')
    # Keep a bounded diagnostic of Steam's actual window identity. A screenshot
    # alone cannot reveal class/role/caption variants from future Steam builds.
    try:
        diagnostic = subprocess.run(['journalctl', '--user', '-b', '--since=-2min',
            '--grep=CallasSteamDialog:', '-n', '20', '--no-pager', '-o', 'cat'],
            capture_output=True, text=True, timeout=3)
        logger = Path('/usr/local/libexec/callas-logs')
        if diagnostic.returncode == 0 and diagnostic.stdout and logger.is_file():
            subprocess.run([str(logger), '--write', 'Janelas'],
                input=diagnostic.stdout.encode(), check=False, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        pass


def activate():
    # Runs in the user's graphical session, including when started by the updater.
    # Does not choose a primary output, move a panel, or change autostart preferences.
    if os.geteuid() == 0:
        raise RuntimeError('A memória de janelas deve ser aplicada como usuário da sessão.')
    import fcntl
    STATE.mkdir(parents=True, exist_ok=True)
    fd = os.open(STATE / 'window-memory.lock', os.O_WRONLY | os.O_CREAT, 0o600)
    with os.fdopen(fd, 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        start_steam_dialogs()
        remember_windows()


def install_system():
    if os.geteuid() != 0:
        raise RuntimeError('Instalação de sistema requer root.')
    atomic(Path('/etc/xdg/autostart/callas-janelas.desktop'), '[Desktop Entry]\nType=Application\nName=Memória de janelas Callas OS\nExec=/usr/local/libexec/callas-janelas --activate\nOnlyShowIn=KDE;\nNoDisplay=true\nStartupNotify=false\nX-KDE-autostart-phase=2\n', 0o644)
    # The updater starts this unit in the active user's manager. Its environment
    # comes from Plasma, avoiding the root/sudo environment for display access.
    atomic(Path('/etc/systemd/user/callas-janelas.service'), '[Unit]\nDescription=Memória de janelas do Callas OS\nAfter=plasma-kwin_wayland.service\n\n[Service]\nType=oneshot\nExecStart=/usr/local/libexec/callas-janelas --activate\nTimeoutStartSec=30\n', 0o644)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--install-system', action='store_true')
    group.add_argument('--activate', action='store_true')
    group.add_argument('--steam-dialogs', action='store_true')
    args = parser.parse_args()
    if args.install_system:
        install_system()
    elif args.steam_dialogs:
        if os.geteuid() == 0:
            raise RuntimeError('Diálogos Steam devem ser ajustados pelo usuário da sessão.')
        start_steam_dialogs()
    else:
        activate()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Erro ao ativar memória de janelas:', exc, file=sys.stderr)
        sys.exit(1)
