#!/usr/bin/python3
"""Skip each social app's autostart once, only when a clean install armed it.

Menu launchers remain unchanged. Existing installations have no pending markers.
"""
import os
from pathlib import Path
import sys

APPS = frozenset(('steam', 'discord'))

def state_directory():
    base = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state')))
    if not base.is_absolute(): raise ValueError('XDG_STATE_HOME precisa ser absoluto')
    return base / 'callas-os'

def skip_first_start(app):
    if app not in APPS: raise ValueError('Aplicativo inválido')
    marker = state_directory() / ('first-login-' + app + '.pending')
    try: marker.unlink()
    except FileNotFoundError: return False
    print('Callas OS: início automático de ' + app + ' adiado apenas neste primeiro login.')
    return True

def main():
    if os.geteuid() == 0 or len(sys.argv) < 3:
        raise ValueError('Uso interno do autostart do usuário')
    app, command = sys.argv[1], sys.argv[2:]
    if not skip_first_start(app): os.execvp(command[0], command)

if __name__ == '__main__':
    try: main()
    except Exception as error:
        print('Autostart do Callas OS: ' + str(error), file=sys.stderr); sys.exit(1)
