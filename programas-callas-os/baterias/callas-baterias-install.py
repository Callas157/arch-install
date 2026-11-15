#!/usr/bin/python3
"""Provision Callas Baterias from the commit-verified stage, never as a GUI root app."""
import argparse
import configparser
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import tarfile
import tempfile
import time

APP = Path('/usr/local/share/callas-os/baterias')
HELPER = Path('/usr/local/share/plasma/plasmoids/br.com.callas.ordem-baterias')
SELF = '/usr/local/libexec/callas-baterias-install'
UNIT = '''[Unit]
Description=Callas Baterias - teclado e mouse
PartOf=graphical-session.target
After=graphical-session.target
StartLimitIntervalSec=60
StartLimitBurst=3
[Service]
Type=simple
ExecStart=/usr/bin/python3 /usr/local/share/callas-os/baterias/callas_baterias.py
ExecStartPost=/usr/bin/python3 /usr/local/libexec/callas-baterias-install --arrange-tray
Restart=on-failure
RestartSec=5
TimeoutStartSec=45
TimeoutStopSec=8
'''
LAUNCHER = '''#!/usr/bin/bash
set -euo pipefail
variables=()
for name in DISPLAY WAYLAND_DISPLAY XAUTHORITY XDG_CURRENT_DESKTOP; do
    if [[ -v $name ]]; then variables+=("$name"); fi
done
if ((${#variables[@]})); then systemctl --user import-environment "${variables[@]}"; fi
systemctl --user reset-failed callas-baterias.service 2>/dev/null || true
exec systemctl --user start callas-baterias.service
'''
DESKTOP = '''[Desktop Entry]
Type=Application
Name=Callas Baterias
Comment=Baterias do teclado FreeWolf F75 e mouse Attack Shark
Exec=/usr/local/bin/callas-baterias
Icon=battery
Terminal=false
Categories=Utility;
'''
RULES = '''SUBSYSTEM=="hidraw", SUBSYSTEMS=="usb", ATTRS{modalias}=="usb:v1A2Cp8FFFd*in00", TAG+="uaccess"
SUBSYSTEM=="hidraw", SUBSYSTEMS=="usb", ATTRS{modalias}=="usb:v1D57pFA60d*in02", TAG+="uaccess"
SUBSYSTEM=="hidraw", SUBSYSTEMS=="usb", ATTRS{modalias}=="usb:v1D57pFA61d*in02", TAG+="uaccess"
'''
ARRANGE = '''var count=0; for(var p of panels()){var tray=false;var helper=null;for(var w of p.widgets()){if(w.type==="org.kde.plasma.systemtray")tray=true;if(w.type==="br.com.callas.ordem-baterias")helper=w;}if(tray){if(!helper)p.addWidget("br.com.callas.ordem-baterias");count++;}}if(!count)throw new Error("Painel ainda não disponível");'''


def write(path, content, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Do not overwrite through a link, including a user-created launcher link.
    if path.is_symlink(): path.unlink()
    path.write_text(content)
    path.chmod(mode)


def ensure_dependencies():
    result = subprocess.run(['pacman', '-Q', 'pyside6'], stdout=subprocess.DEVNULL)
    if result.returncode == 1:
        subprocess.run(['/usr/local/libexec/callas-native', '--install', 'pyside6'], check=True)
        subprocess.run(['pacman', '-Q', 'pyside6'], check=True, stdout=subprocess.DEVNULL)
    elif result.returncode:
        raise RuntimeError('Falha ao consultar pyside6 no banco de pacotes')


def public_directory(path):
    missing = []
    current = path
    while not current.exists():
        missing.append(current)
        current = current.parent
    path.mkdir(parents=True, exist_ok=True)
    for directory in missing: directory.chmod(0o755)
    path.chmod(0o755)


def autostart_disabled(path):
    config = configparser.ConfigParser(interpolation=None)
    try:
        config.read(path)
        return config.getboolean('Desktop Entry', 'Hidden', fallback=False)
    except (OSError, configparser.Error, ValueError):
        return False


def deploy(archive, system=Path('/')):
    with tempfile.TemporaryDirectory(prefix='callas-baterias-') as temp:
        with tarfile.open(archive, 'r:gz') as tar:
            members = tar.getmembers()
            if sum(m.size for m in members) > 4 * 1024 * 1024:
                raise ValueError('Pacote excedeu o limite')
            for member in members:
                path = Path(member.name)
                if (path.is_absolute() or '..' in path.parts or not path.parts
                        or path.parts[0] not in ('app', 'painel')
                        or not (member.isfile() or member.isdir())):
                    raise ValueError('Entrada insegura no pacote: ' + member.name)
            tar.extractall(temp, filter='data')
        source = Path(temp)
        for name in ('app/callas_baterias.py', 'app/sharktray/mouse.py', 'painel/metadata.json'):
            if not (source / name).is_file(): raise ValueError('Pacote incompleto: ' + name)
        for src, target in ((source / 'app', system / APP.relative_to('/')),
                            (source / 'painel', system / HELPER.relative_to('/'))):
            public_directory(target)
            shutil.copytree(src, target, dirs_exist_ok=True)
            target.chmod(0o755)
            for path in target.rglob('*'): path.chmod(0o755 if path.is_dir() else 0o644)
        for directory in ('etc/systemd/user', 'etc/xdg/autostart',
                          'usr/local/share/applications', 'usr/local/bin',
                          'etc/udev/rules.d', 'usr/local/libexec'):
            public_directory(system / directory)
        write(system / 'etc/systemd/user/callas-baterias.service', UNIT)
        write(system / 'etc/xdg/autostart/callas-baterias.desktop', DESKTOP)
        write(system / 'usr/local/share/applications/callas-baterias.desktop', DESKTOP)
        write(system / 'usr/local/bin/callas-baterias', LAUNCHER, 0o755)
        write(system / 'etc/udev/rules.d/71-callas-baterias.rules', RULES)
        write(system / SELF.lstrip('/'), Path(__file__).read_text(), 0o755)


def configure_user(home, system=Path('/')):
    # Called as the desktop user, so their home directory never receives root writes.
    write(home / '.config/systemd/user/callas-baterias.service', UNIT)
    autostart = home / '.config/autostart/callas-baterias.desktop'
    disabled = autostart_disabled(autostart)
    write(autostart, DESKTOP + ('Hidden=true\n' if disabled else ''))
    write(home / '.local/share/applications/callas-baterias.desktop', DESKTOP)
    write(home / '.local/bin/callas-baterias', LAUNCHER, 0o755)
    target = home / '.local/share/plasma/plasmoids/br.com.callas.ordem-baterias'
    if target.is_symlink(): target.unlink()
    shutil.copytree(system / HELPER.relative_to('/'), target, dirs_exist_ok=True)
    for name in ('attackshark-tray', 'freewolf-battery'):
        write(home / '.config/autostart' / (name + '.desktop'),
              '[Desktop Entry]\nType=Application\nName=Indicador anterior\nHidden=true\n')
    # QSettings appearance, keyboard preferences and battery history are preserved.


def arrange_tray():
    if not shutil.which('qdbus6'): return
    for _ in range(15):
        try:
            result = subprocess.run(['qdbus6', 'org.kde.plasmashell', '/PlasmaShell',
                                     'org.kde.PlasmaShell.evaluateScript', ARRANGE],
                                    capture_output=True, text=True, timeout=1)
            if result.returncode == 0:
                print('Baterias agrupadas à esquerda da rede.'); return
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass  # Optional placement must not stop battery monitoring.
        time.sleep(1)
    print('Aviso: painel KDE indisponível; a ordem será tentada na próxima inicialização.')


def current(archive, home, system=Path('/')):
    """Compare generated system/profile files with this verified release.

    No receipt is needed: this also recognizes installations made by older
    installers. Only managed files are compared; preferences stay private.
    """
    with tempfile.TemporaryDirectory(prefix='callas-baterias-compare-') as temp:
        expected = Path(temp) / 'system'
        profile = Path(temp) / 'home'
        deploy(archive, expected)
        configure_user(profile, expected)
        override = Path(home) / '.config/autostart/callas-baterias.desktop'
        if autostart_disabled(override):
            write(profile / '.config/autostart/callas-baterias.desktop', DESKTOP + 'Hidden=true\n')
        for source, destination in ((expected, system), (profile, Path(home))):
            for path in source.rglob('*'):
                target = destination / path.relative_to(source)
                if path.is_file():
                    if (target.is_symlink() or not target.is_file()
                            or target.read_bytes() != path.read_bytes()
                            or target.stat().st_mode & 0o777 != path.stat().st_mode & 0o777):
                        return False
        return True


def install_system(user, archive):
    account = pwd.getpwnam(user)
    if os.geteuid() != 0 or account.pw_uid == 0: raise ValueError('Requer root e usuário normal')
    ensure_dependencies()  # Guarded transaction first; never falls back to a general upgrade.
    if current(archive, Path(account.pw_dir)):
        print('Callas Baterias já corresponde ao repositório; preservado sem reinstalação ou reinício.')
        return
    deploy(archive)
    env = ['env', '-i', 'PATH=/usr/bin:/bin', 'HOME=' + account.pw_dir,
           'USER=' + user, 'LOGNAME=' + user, 'LANG=C.UTF-8',
           'XDG_RUNTIME_DIR=/run/user/' + str(account.pw_uid),
           'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/' + str(account.pw_uid) + '/bus']
    run_user = ['runuser', '-u', user, '--', *env]
    subprocess.run([*run_user, '/usr/bin/python3', SELF, '--configure-user'], check=True)
    subprocess.run(['udevadm', 'control', '--reload-rules'], check=False)
    # Only these vendor HID interfaces are retriggered, without resetting USB devices.
    for product in ('0003:1A2C:8FFF.*', '0003:1D57:FA60.*', '0003:1D57:FA61.*'):
        for device in Path('/sys/bus/hid/devices').glob(product):
            for node in device.glob('hidraw/hidraw*'):
                subprocess.run(['udevadm', 'trigger', '--action=change', str(node.resolve())], check=False)
    # No session exists inside a clean-install chroot. Autostart handles first login.
    if Path('/run/user/' + str(account.pw_uid) + '/bus').exists():
        ctl = [*run_user, 'systemctl', '--user']
        subprocess.run([*ctl, 'daemon-reload'], check=True)
        for old in ('attackshark-tray.service', 'freewolf-battery.service'):
            subprocess.run([*ctl, 'disable', '--now', old], capture_output=True)
        active = subprocess.run([*ctl, 'is-active', '--quiet', 'callas-baterias.service']).returncode == 0
        if active or not autostart_disabled(Path(account.pw_dir) / '.config/autostart/callas-baterias.desktop'):
            subprocess.run([*ctl, 'restart', 'callas-baterias.service'], check=True)
    print('Callas Baterias instalado; preferências preservadas e início automático configurado.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--install-system', metavar='USER')
    group.add_argument('--configure-user', action='store_true')
    group.add_argument('--arrange-tray', action='store_true')
    parser.add_argument('--payload', type=Path)
    args = parser.parse_args()
    if args.install_system:
        if args.payload is None: parser.error('--payload é obrigatório')
        install_system(args.install_system, args.payload)
    elif args.configure_user:
        if os.geteuid() == 0: raise ValueError('Configure o perfil como usuário normal')
        configure_user(Path.home())
    else:
        if os.geteuid() == 0: raise ValueError('Ajuste a bandeja como usuário normal')
        arrange_tray()


if __name__ == '__main__': main()
