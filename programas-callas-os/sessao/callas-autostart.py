#!/usr/bin/python3
"""Block Steam/Discord autostart throughout the first clean-install boot.

Menu launchers remain unchanged. Only a different boot ID releases autostart;
existing installations without pending markers are never armed by migration.
"""
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import uuid

APPS = frozenset(('steam', 'discord'))


def state_directory():
    base = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state')))
    if not base.is_absolute(): raise ValueError('XDG_STATE_HOME precisa ser absoluto')
    return base / 'callas-os'


def boot_id():
    return str(uuid.UUID(Path('/proc/sys/kernel/random/boot_id').read_text().strip()))


def skip_first_start(app):
    if app not in APPS: raise ValueError('Aplicativo inválido')
    state = state_directory()
    marker = state / ('first-login-' + app + '.pending')
    first_boot = state / 'first-login.boot-id'
    if not marker.exists() and not first_boot.exists():
        return False
    # Both applications and repeated KDE logins share the same boot boundary.
    # Serialize their startup so they cannot arm different first boots or race
    # when removing the pending state after a real restart.
    with (state / 'first-login.lock').open('a') as lock:
        os.chmod(lock.name, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not marker.exists() and not first_boot.exists():
            return False
        current = boot_id()
        if first_boot.exists():
            initial = str(uuid.UUID(first_boot.read_text().strip()))
        else:
            first_boot.write_text(current + '\n')
            first_boot.chmod(0o600)
            initial = current
        if current != initial:
            for name in APPS:
                (state / ('first-login-' + name + '.pending')).unlink(missing_ok=True)
            first_boot.unlink()
            return False
    print('Callas OS: início automático de ' + app + ' bloqueado até reiniciar o sistema.')
    return True


def main():
    if os.geteuid() == 0 or len(sys.argv) < 3:
        raise ValueError('Uso interno do autostart do usuário')
    app, command = sys.argv[1], sys.argv[2:]
    if skip_first_start(app):
        return
    if app == 'steam':
        try:
            subprocess.run(['/usr/local/libexec/callas-steam-libraries'], check=True, timeout=8)
        except FileNotFoundError:
            pass
        except (OSError, subprocess.SubprocessError) as error:
            print('Bibliotecas Steam do Callas OS: ' + str(error), file=sys.stderr)
    os.execvp(command[0], command)


if __name__ == '__main__':
    try: main()
    except Exception as error:
        print('Autostart do Callas OS: ' + str(error), file=sys.stderr); sys.exit(1)
