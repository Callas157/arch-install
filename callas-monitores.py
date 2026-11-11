#!/usr/bin/env python3
"""Callas OS: output priority, Plasma desktop and native KWin Remember rules.
Never forces application windows onto the primary output. No display mode changes.
"""
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

APP_ID = 'io.github.Callas157.Monitores.desktop'
CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config')))
STATE = CONFIG / 'callas-os'
LIBEXEC = Path('/usr/local/libexec')


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


def plasma(script):
    import dbus
    interface = dbus.Interface(bus().get_object('org.kde.plasmashell', '/PlasmaShell'), 'org.kde.PlasmaShell')
    result = str(interface.evaluateScript(script, timeout=30))
    if 'Error' in result or 'CALLAS_OK' not in result:
        raise RuntimeError('Plasma não confirmou o ajuste: ' + result)


def backup():
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    dest = STATE / 'monitor-backups' / stamp
    dest.mkdir(parents=True)
    for name in ('callas-os/monitors.json', 'kwinrulesrc', 'kwinoutputconfig.json', 'plasmanotifyrc', 'plasma-org.kde.plasma.desktop-appletsrc', 'ksmserverrc'):
        path = CONFIG / name
        if path.is_file():
            shutil.copy2(path, dest / Path(name).name)
    print('Backup:', dest)
    return dest


def remember_windows():
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
workspace.windowList().forEach(function(w) {
    if (!w.normalWindow || w.transient || !w.resourceClass) return;
    const g = w.frameGeometry;
    result.push({app: String(w.resourceClass).toLowerCase(), role: String(w.windowRole || ""), output: String(w.output.name),
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
    remember_rules(received[0])


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
            if any(cfg[s].get('Description', '').startswith('Callas OS: lembrar ') and cfg[s].get('wmclass') == app for s in cfg.sections()):
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
    atomic(path, out.getvalue())
    dbus.Interface(bus().get_object('org.kde.KWin', '/KWin'), 'org.kde.KWin').reconfigure()
    print(f'Regras Lembrar: {added} adicionadas. As regras aprendidas foram preservadas.')
    print('Discord, Spotify e Brave: mova/redimensione suas janelas uma vez e feche normalmente para o KDE aprender.')
    print('Para guardar também maximização, deixe o aplicativo aberto ao ativar esta opção pela primeira vez.')


def remap_rule_screens(old_order, new_order):
    # KWin stores Remember-screen as an index. Keep the same physical connector
    # when the primary choice changes that index; never alter user-owned rules.
    path = CONFIG / 'kwinrulesrc'
    if not path.exists():
        return
    cfg = configparser.ConfigParser(interpolation=None, strict=True)
    cfg.optionxform = str
    cfg.read(path)
    changed = False
    for section in cfg.sections():
        rule = cfg[section]
        if not rule.get('Description', '').startswith('Callas OS: lembrar ') or rule.get('screenrule') != '4':
            continue
        index = rule.get('screen', '')
        if not index.isdigit() or int(index) >= len(old_order):
            continue
        connector = old_order[int(index)]['name']
        names = [o['name'] for o in new_order]
        if connector in names and index != str(names.index(connector)):
            rule['screen'] = str(names.index(connector))
            changed = True
    if changed:
        import io
        out = io.StringIO()
        cfg.write(out, space_around_delimiters=False)
        atomic(path, out.getvalue())
        import dbus
        dbus.Interface(bus().get_object('org.kde.KWin', '/KWin'), 'org.kde.KWin').reconfigure()


def apply_desktop():
    desktop_dir = run('xdg-user-dir', 'DESKTOP').strip()
    if not desktop_dir.startswith('/'):
        raise RuntimeError('A pasta Área de Trabalho não foi identificada.')
    secondary = Path.home() / '.local/share/callas-os/secondary-desktop'
    secondary.mkdir(parents=True, exist_ok=True)
    # KScreen priority 1 is Plasma screen 0. Use only this folder view for Desktop.
    # No shortcuts are moved or deleted; other desktop widgets remain intact.
    script = '''
const spare = SPARE;
const desktopUrl = DESKTOP_URL;
var primary = false;
desktops().forEach(function(d) {
    d.currentConfigGroup = ["General"];
    const url = d.readConfig("url", "desktop:/");
    if (d.screen === 0) {
        d.writeConfig("url", "desktop:/");
        primary = true;
    } else if (url === "desktop:/" || url === desktopUrl || url.indexOf(spare) === 0) {
        d.writeConfig("url", spare);
    }
    d.reloadConfig();
});
if (!primary) throw new Error("Área de trabalho principal ainda indisponível");
panels().forEach(function(p) {
    if (p.widgets("org.kde.plasma.kickoff").length || p.widgets("org.kde.plasma.icontasks").length) p.screen = 0;
});
print("CALLAS_OK");
'''.replace('SPARE', json.dumps(secondary.as_uri())).replace('DESKTOP_URL', json.dumps(Path(desktop_dir).as_uri()))
    plasma(script)
    run('kwriteconfig6', '--file', 'plasmanotifyrc', '--group', 'Notifications', '--key', 'PopupPosition', 'CloseToWidget')
    # Plasma's notification applet follows the panel/tray moved above.
    print('Painel e notificações no principal; novos arquivos da Área de Trabalho aparecem nele.')


def choose():
    current = outputs()
    for n, o in enumerate(current, 1):
        size = o.get('size', {})
        print(f"{n}. {o['name']} — {size.get('width', '?')} × {size.get('height', '?')} — prioridade {o.get('priority', '?')}")
    answer = input('Qual será o principal? [0 cancela]: ').strip()
    if answer == '0':
        return
    if not answer.isdigit() or not 1 <= int(answer) <= len(current):
        raise RuntimeError('Escolha inválida; nenhuma alteração aplicada.')
    if any(o.get('replicationSource', 0) for o in current):
        raise RuntimeError('Desative o espelhamento nas configurações de telas antes de escolher o principal.')
    chosen = current[int(answer) - 1]
    # Refresh before mutation; do not act on a disconnected/replaced output.
    if {o['name'] for o in outputs()} != {o['name'] for o in current}:
        raise RuntimeError('Os monitores mudaram. Abra a lista novamente.')
    backup()
    # Authorize login changes before touching the desktop; never restart SDDM.
    run('sudo', '-v')
    order = [chosen] + sorted((o for o in current if o != chosen), key=lambda o: o.get('priority', 100))
    run('kscreen-doctor', *(f"output.{o['id']}.priority.{i}" for i, o in enumerate(order, 1)))
    active = outputs()
    if next(o for o in active if o['name'] == chosen['name']).get('priority') != 1:
        raise RuntimeError('O KDE não confirmou a prioridade. Configurações adicionais não foram aplicadas.')
    remap_rule_screens(sorted(current, key=lambda o: o.get('priority', 100)), sorted(active, key=lambda o: o.get('priority', 100)))
    atomic(STATE / 'monitors.json', json.dumps({'primary': chosen['name']}, indent=2) + '\n')
    # KScreen saves output geometry asynchronously. The login helper validates its input.
    apply_desktop()
    subprocess.run([str(LIBEXEC / 'callas-kde-desligamento-login'), '--monitor', chosen['name']], check=True)
    remember_windows()
    run('kwriteconfig6', '--file', 'ksmserverrc', '--group', 'General', '--key', 'loginMode', 'emptySession')
    print('Principal:', chosen['name'], '— confira o formulário no próximo login.')
    print('Resolução, frequência, escala e disposição física dos monitores foram mantidas.')


def favorite():
    import dbus
    obj = bus().get_object('org.kde.ActivityManager', '/ActivityManager/Resources/Linking')
    interface = dbus.Interface(obj, 'org.kde.ActivityManager.ResourcesLinking')
    for ident in (APP_ID, 'io.github.Callas157.AtualizadorDoSistema.desktop'):
        interface.LinkResourceToActivity('org.kde.plasma.favorites.applications', 'applications:' + ident, ':global')


def install_system():
    if os.geteuid() != 0:
        raise RuntimeError('Instalação de sistema requer root.')
    target = Path('/usr/local/share/applications') / APP_ID
    atomic(target, '''[Desktop Entry]
Type=Application
Name=Callas OS — Monitores
Comment=Escolher monitor principal, login, painel e lembrar janelas
Exec=/usr/local/libexec/callas-monitores
TryExec=/usr/local/libexec/callas-monitores
Icon=preferences-desktop-display
Terminal=true
Categories=System;Settings;HardwareSettings;
Keywords=monitor;tela;principal;DisplayPort;HDMI;Callas;
''', 0o644)
    atomic(Path('/etc/xdg/autostart/callas-monitores.desktop'), '''[Desktop Entry]
Type=Application
Name=Preferências de monitores Callas OS
Exec=/usr/local/libexec/callas-monitores --session
OnlyShowIn=KDE;
NoDisplay=true
X-KDE-autostart-phase=2
''', 0o644)


def session_setup():
    # Never reassign priority or move panels each boot: KScreen persists the choice.
    # One-time favorites import supports existing Kickoff profiles and manual unpinning.
    if not (STATE / 'monitor-favorites-v1').exists():
        favorite()
        atomic(STATE / 'monitor-favorites-v1', '1\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install-system', action='store_true')
    parser.add_argument('--session', action='store_true')
    args = parser.parse_args()
    if args.install_system:
        install_system()
        return
    if os.geteuid() == 0:
        raise RuntimeError('Abra pelo menu do KDE como usuário normal.')
    if os.environ.get('XDG_SESSION_TYPE') != 'wayland':
        raise RuntimeError('Esta ferramenta requer Plasma Wayland.')
    if args.session:
        session_setup()
        return
    try:
        session_setup()
    except Exception as exc:
        print('Aviso: favoritos não puderam ser importados:', exc)
    while True:
        print('\nCallas OS — Monitores\n1. Escolher monitor principal e configurar KDE/login\n2. Ativar memória de posição/tamanho (Discord, Spotify, Brave)\n3. Abrir configurações de telas do KDE\n4. Abrir Regras de janelas (outros aplicativos)\n0. Sair')
        option = input('Escolha: ').strip()
        try:
            if option == '0':
                return
            if option == '1':
                choose()
            elif option == '2':
                backup()
                remember_windows()
            elif option == '3':
                subprocess.Popen(['systemsettings', 'kcm_kscreen'])
            elif option == '4':
                subprocess.Popen(['systemsettings', 'kcm_kwinrules'])
            else:
                print('Opção inválida.')
        except Exception as exc:
            print('Não foi possível concluir:', exc)
            print('As etapas já confirmadas podem ter sido aplicadas. O backup foi preservado.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Erro:', exc, file=sys.stderr)
        sys.exit(1)
