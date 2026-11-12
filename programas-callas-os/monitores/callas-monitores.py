#!/usr/bin/env python3
"""Callas OS: output priority, Plasma desktop and login display.
Only Steam launch dialogs are routed to the primary output. No display mode changes.
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
    subprocess.run([str(LIBEXEC / 'callas-janelas'), '--steam-dialogs'], check=True)
    subprocess.run([str(LIBEXEC / 'callas-kde-desligamento-login'), '--monitor', chosen['name']], check=True)
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
Comment=Escolher monitor principal, login, painel, atalhos e notificações
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
        print('\nCallas OS — Monitores\n1. Escolher monitor principal e configurar KDE/login\n2. Abrir configurações de telas do KDE\n0. Sair')
        option = input('Escolha: ').strip()
        try:
            if option == '0':
                return
            if option == '1':
                choose()
            elif option == '2':
                subprocess.Popen(['systemsettings', 'kcm_kscreen'])
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
