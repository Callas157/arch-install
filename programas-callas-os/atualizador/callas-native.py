#!/usr/bin/python3
"""Conservative official-app updates: never install kernel/boot/base upgrades here.

Check the complete pending transaction in an isolated database. If it contains
base changes, defer the official phase to General. A pretransaction hook also
guards against repository changes between the check and pacman's refresh.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

FROZEN = frozenset(('base', 'filesystem', 'glibc', 'bash', 'coreutils', 'sudo', 'util-linux',
    'grub', 'efibootmgr', 'sddm', 'kwin', 'mesa', 'lib32-mesa', 'gdm', 'dbus', 'dbus-broker',
    'networkmanager', 'linux-firmware', 'linux-api-headers', 'plymouth', 'dracut', 'booster', 'amd-ucode', 'intel-ucode', 'kmod', 'libxnvctrl'))
PREFIXES = ('linux', 'nvidia', 'lib32-nvidia', 'systemd', 'pacman', 'mkinitcpio', 'plasma', 'opencl-nvidia', 'lib32-opencl-nvidia', 'vulkan-', 'lib32-vulkan')

def frozen(name): return name in FROZEN or name.startswith(PREFIXES)

def pretransaction_code(marker=None):
    return 'import sys\nfrom pathlib import Path\nMARKER=' + repr(str(marker) if marker else None) + '\nFROZEN=' + repr(set(FROZEN)) + '\nPREFIXES=' + repr(PREFIXES) + '''
names = [line.strip() for line in sys.stdin if line.strip()]
blocked = [name for name in names if name in FROZEN or name.startswith(PREFIXES)]
if blocked:
    if MARKER: Path(MARKER).write_text('blocked')
    print('Esta transação exige Atualizar geral: ' + ', '.join(blocked), file=sys.stderr)
    sys.exit(1)
'''

def update():
    with tempfile.TemporaryDirectory(prefix='callas-native-', dir='/var/tmp') as temp:
        env = dict(os.environ, CHECKUPDATES_DB=temp + '/db')
        check = subprocess.run(['/usr/bin/checkupdates'], env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True)
        if check.returncode == 2:
            print('Aplicativos oficiais: nenhuma atualização disponível.'); return 0
        if check.returncode:
            print(check.stderr, file=sys.stderr); return 1
        pending = [line.split()[0] for line in check.stdout.splitlines() if line.split() and '[ignored]' not in line]
        blocked = [name for name in pending if frozen(name)]
        if not any(not frozen(name) for name in pending):
            print('Nenhum aplicativo oficial pendente; alterações de base ficam reservadas a Atualizar geral.')
            return 0
        if blocked:
            print('Aplicativos oficiais aguardam a opção 4 — Atualizar geral, pois há mudanças de base pendentes: ' + ', '.join(blocked))
            print('Nenhum kernel ou pacote de boot foi alterado pela opção 2.')
            return 2
        marker = Path(temp) / 'blocked'
        guard = Path(temp) / 'guard.py'; guard.write_text(pretransaction_code(marker)); guard.chmod(0o600)
        hooks = Path(temp) / 'hooks'; hooks.mkdir()
        (hooks / '00-callas-native-guard.hook').write_text('''[Trigger]
Operation = Install
Operation = Upgrade
Operation = Remove
Type = Package
Target = *

[Action]
Description = Preservar kernel, boot e base na atualização de aplicativos
When = PreTransaction
NeedsTargets
AbortOnFail
Exec = /usr/bin/python3 ''' + str(guard) + '\n')
        # Complete transaction only, never pacman -Sy followed by selected packages.
        result = subprocess.run(['/usr/bin/pacman', '--hookdir', '/etc/pacman.d/hooks', '--hookdir', str(hooks),
                                 '-Syu', '--needed', '--noconfirm'], stdin=subprocess.DEVNULL)
        if result.returncode:
            print('A fase oficial não terminou. Use Atualizar geral para resolver a transação completa.', file=sys.stderr)
            return 2 if marker.exists() else 1
        return 0

if __name__ == '__main__':
    if os.geteuid() != 0 or len(sys.argv) != 1: raise SystemExit('Uso interno do atualizador')
    sys.exit(update())
