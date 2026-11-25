#!/usr/bin/python3
"""Conservative official-app updates: never install kernel/boot/base upgrades here.

Check the complete pending transaction in an isolated database. If it contains
base changes, defer the official phase to General. A pretransaction hook also
guards the resolved transaction without refreshing the live databases.
"""
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

FROZEN = frozenset(('base', 'filesystem', 'glibc', 'bash', 'coreutils', 'sudo', 'util-linux',
    'grub', 'efibootmgr', 'sddm', 'kwin', 'mesa', 'lib32-mesa', 'gdm', 'dbus', 'dbus-broker',
    'networkmanager', 'linux-firmware', 'linux-api-headers', 'plymouth', 'dracut', 'booster', 'amd-ucode', 'intel-ucode', 'kmod', 'libxnvctrl'))
PREFIXES = ('linux', 'nvidia', 'lib32-nvidia', 'systemd', 'pacman', 'mkinitcpio', 'plasma', 'opencl-nvidia', 'lib32-opencl-nvidia', 'vulkan-', 'lib32-vulkan')
DRIVER_RECORD = Path('/etc/callas-nvidia-version')
DRIVER_PACKAGES = {'nvidia-utils', 'nvidia-open-dkms', 'nvidia-open', 'nvidia-open-lts',
                   'lib32-nvidia-utils', 'nvidia-settings', 'libxnvctrl', 'opencl-nvidia', 'lib32-opencl-nvidia'}

GRAPHICS_PACKAGES = {
    'radv': ('vulkan-radeon', 'lib32-vulkan-radeon'),
    'anv': ('vulkan-intel', 'lib32-vulkan-intel'),
    'lavapipe': ('vulkan-swrast', 'lib32-vulkan-swrast'),
}


def frozen(name): return name in FROZEN or name.startswith(PREFIXES)

def pretransaction_code(marker=None, allowed=()):
    return 'import sys\nfrom pathlib import Path\nMARKER=' + repr(str(marker) if marker else None) + '\nFROZEN=' + repr(set(FROZEN)) + '\nPREFIXES=' + repr(PREFIXES) + '\nALLOWED=' + repr(tuple(allowed)) + '''
names = [line.strip() for line in sys.stdin if line.strip()]
blocked = [name for name in names if name not in ALLOWED and (name in FROZEN or name.startswith(PREFIXES))]
if blocked:
    if MARKER: Path(MARKER).write_text('blocked')
    print('Esta transação exige Atualizar geral: ' + ', '.join(blocked), file=sys.stderr)
    sys.exit(1)
'''

def guarded_transaction(arguments, runner=None, *, graphics=()):
    """Guard the resolved transaction, including dependencies and replacements."""
    if not arguments or arguments[0] not in ('-S', '-U', '-R'):
        raise ValueError('Somente instalações ou remoções explícitas são permitidas neste fluxo.')
    options = {'--noconfirm'} if arguments[0] == '-R' else {'--needed', '--noconfirm', '--asdeps'}
    if any(arg.startswith('-') and arg not in options for arg in arguments[1:]):
        raise ValueError('Sincronização e atualização geral não são permitidas neste fluxo.')
    with tempfile.TemporaryDirectory(prefix='callas-install-') as temp:
        guard = Path(temp) / 'guard.py'
        guard.write_text(pretransaction_code(allowed=graphics))
        guard.chmod(0o600)
        hooks = Path(temp) / 'hooks'
        hooks.mkdir()
        (hooks / '00-callas-targeted-guard.hook').write_text('''[Trigger]
Operation = Install
Operation = Upgrade
Operation = Remove
Type = Package
Target = *

[Action]
Description = Impedir alteracoes de kernel, driver, boot e base em aplicativos
When = PreTransaction
NeedsTargets
AbortOnFail
Exec = /usr/bin/python3 ''' + str(guard) + '\n')
        if graphics:
            (hooks / '00-callas-graphics-no-remove.hook').write_text("""[Trigger]
Operation = Remove
Type = Package
Target = *

[Action]
Description = Impedir remoções na instalação de drivers Vulkan
When = PreTransaction
AbortOnFail
Exec = /usr/bin/false
""")
        command = ['/usr/bin/pacman', '--hookdir', '/etc/pacman.d/hooks', '--hookdir', str(hooks), *arguments]
        if runner is not None:
            return runner(command)
        env = dict(os.environ, CALLAS_KERNEL_UPDATE_CONTEXT='apps')
        return subprocess.run(command, stdin=subprocess.DEVNULL, env=env)


def install_packages(packages):
    """Explicit apps from the existing database, never -y/-u."""
    if not packages or any(not re.fullmatch(r'[a-zA-Z0-9@_+][a-zA-Z0-9@_.+\-]*', p) or frozen(p) for p in packages):
        raise ValueError('Instalação pontual inválida ou exige alteração da base; nenhuma transação iniciada.')
    result = guarded_transaction(['-S', '--needed', '--noconfirm', *packages])
    if result.returncode:
        print('Instalação pontual não concluída. Nenhuma atualização geral será iniciada automaticamente.', file=sys.stderr)
    return result.returncode

def local_package_version(package):
    installed = subprocess.check_output(['/usr/bin/pacman', '-Q', package], text=True)
    return installed.split()[1]


def install_graphics(profile):
    packages = GRAPHICS_PACKAGES[profile]
    try:
        mesa, mesa32 = map(local_package_version, ('mesa', 'lib32-mesa'))
        expected = {packages[0]: mesa, packages[1]: mesa32,
                    'vulkan-mesa-implicit-layers': mesa, 'lib32-vulkan-mesa-implicit-layers': mesa32}
        output = subprocess.check_output(
            ['/usr/bin/pacman', '-Sp', '--needed', '--print-format', '%n %v', '--', *packages],
            text=True, env={**os.environ, 'LC_ALL': 'C'})
        selected = dict(line.split() for line in output.splitlines() if line.strip())
        for name in packages:
            if name not in selected:
                selected[name] = local_package_version(name)
        if any(selected[name] != version for name, version in expected.items() if name in selected):
            raise ValueError('Os pacotes Vulkan disponíveis precisam corresponder ao Mesa instalado.')
    except (OSError, IndexError, ValueError, subprocess.CalledProcessError) as error:
        print(f'Driver Vulkan: {error} Use Atualizar geral para alinhar os pacotes do Mesa.', file=sys.stderr)
        return 1
    supported = (*expected, 'vulkan-icd-loader', 'lib32-vulkan-icd-loader')
    allowed = tuple(name for name in supported if name in selected)
    result = guarded_transaction(['-S', '--needed', '--noconfirm', *packages], graphics=allowed)
    return result.returncode


def pending_updates(output, exclusions):
    return [entry for line in output.splitlines() if (entry := line.strip())
            and '[ignored]' not in entry and entry.split()[0] not in exclusions]


def update():
    with tempfile.TemporaryDirectory(prefix='callas-native-') as temp:
        env = dict(os.environ, CHECKUPDATES_DB=temp + '/db', LC_ALL='C')
        check = subprocess.run(['/usr/bin/checkupdates'], env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True)
        if check.returncode == 2:
            print('Aplicativos oficiais: nenhuma atualização disponível.'); return 0
        if check.returncode:
            print(check.stderr, file=sys.stderr); return 1
        exclusions = DRIVER_PACKAGES if DRIVER_RECORD.is_file() else set()
        expected = pending_updates(check.stdout, exclusions)
        pending = [line.split()[0] for line in expected]
        blocked = [name for name in pending if frozen(name)]
        if not any(not frozen(name) for name in pending):
            print('Nenhum aplicativo oficial pendente; alterações de base ficam reservadas a Atualizar geral.')
            return 0
        if blocked:
            print('Aplicativos oficiais aguardam a opção 4 — Atualizar geral, pois há mudanças de base pendentes: ' + ', '.join(blocked))
            print('Nenhum kernel ou pacote de boot foi alterado pela opção 2.')
            return 2
        # Do not refresh the live database or invoke --sysupgrade here. The
        # installed sync databases must describe exactly the isolated snapshot.
        local = subprocess.run(['/usr/bin/pacman', '-Qu'], stdin=subprocess.DEVNULL,
                               capture_output=True, text=True, env=dict(os.environ, LC_ALL='C'))
        if local.returncode not in (0, 1) or (local.returncode == 1 and (local.stdout or local.stderr)):
            print('Não consegui verificar o banco local de pacotes.', file=sys.stderr)
            return 1
        current = pending_updates(local.stdout, exclusions)
        if set(current) != set(expected):
            print('Aplicativos adiados: banco local difere dos repositórios atuais. Use a opção 4 quando decidir atualizar a base.')
            return 2
        return install_packages(pending)

if __name__ == '__main__':
    if os.geteuid() != 0: raise SystemExit('Uso interno do atualizador')
    if len(sys.argv) == 1:
        sys.exit(update())
    if len(sys.argv) == 3 and sys.argv[1] == '--graphics' and sys.argv[2] in GRAPHICS_PACKAGES:
        sys.exit(install_graphics(sys.argv[2]))
    if len(sys.argv) > 2 and sys.argv[1] == '--install':
        sys.exit(install_packages(sys.argv[2:]))
    raise SystemExit('Uso interno do atualizador')
