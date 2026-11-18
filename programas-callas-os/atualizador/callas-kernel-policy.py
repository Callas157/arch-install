#!/usr/bin/python3
"""Abort installed-system kernel transactions before hooks remove working modules.

Only General may request kernels. With pinned NVIDIA, candidate official kernel
and headers must already be in pacman's verified download cache and build in a
private mount namespace. Nothing is installed by this helper; uncertainty aborts
the entire transaction. AUR/custom kernels are deliberately not approved here.
"""
import contextlib
import io
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor

PAIRS = {'linux': 'linux-headers', 'linux-lts': 'linux-lts-headers'}
PINNED = {'nvidia-utils', 'nvidia-open-dkms', 'nvidia-open', 'nvidia-open-lts',
          'lib32-nvidia-utils', 'nvidia-settings', 'libxnvctrl', 'opencl-nvidia', 'lib32-opencl-nvidia'}
VERSION_FILE = Path('/etc/callas-nvidia-version')
SOURCE_ROOT = Path('/usr/src')
BUILD_PACKAGES = {'glibc', 'make', 'dkms', 'libelf', 'elfutils', 'openssl', 'zstd', 'pahole', 'python', 'libbpf',
                  'compiler-rt', 'kmod', 'sbsigntools', 'mokutil', 'util-linux'}


REQUIRED_HOOKS = {'00-callas-kernel-policy.hook': '[Trigger]\nOperation = Install\nOperation = Upgrade\nType = Package\nTarget = *\n\n[Action]\nDescription = Preservar kernel e NVIDIA ate validar compilacao candidata\nWhen = PreTransaction\nNeedsTargets\nAbortOnFail\nExec = /usr/local/libexec/callas-kernel-policy\n', '00-callas-kernel-deny-remove.hook': '[Trigger]\nOperation = Remove\nType = Package\nTarget = linux*\nTarget = nvidia*\nTarget = lib32-nvidia*\nTarget = libxnvctrl\nTarget = opencl-nvidia\nTarget = lib32-opencl-nvidia\n\n[Action]\nDescription = Impedir remocao automatica dos kernels e driver preservados\nWhen = PreTransaction\nNeedsTargets\nAbortOnFail\nExec = /usr/local/libexec/callas-kernel-policy --remove\n'}
HOOK_DIRECTORY = Path('/etc/pacman.d/hooks')
POLICY_PROGRAM = Path('/usr/local/libexec/callas-kernel-policy')


def check_hooks():
    for path in [POLICY_PROGRAM, *(HOOK_DIRECTORY / name for name in REQUIRED_HOOKS)]:
        if path.is_symlink() or not path.is_file():
            raise RuntimeError('Proteção de kernel ausente ou desativada: ' + str(path))
        info = path.stat()
        if info.st_uid != 0 or info.st_mode & 0o022:
            raise RuntimeError('Proteção de kernel sem permissões seguras: ' + str(path))
    if not os.access(POLICY_PROGRAM, os.X_OK):
        raise RuntimeError('Proteção de kernel não executável.')
    for name, expected in REQUIRED_HOOKS.items():
        if (HOOK_DIRECTORY / name).read_text() != expected:
            raise RuntimeError('Hook de kernel diverge da proteção esperada: ' + name)


def command(args):
    print('+ ' + ' '.join(str(x) for x in args), flush=True)
    result = subprocess.run([str(x) for x in args], stdin=subprocess.DEVNULL,
                            capture_output=True, text=True, timeout=900,
                            env=dict(os.environ, LC_ALL='C', PATH='/usr/bin:/bin'))
    if result.stderr:
        print(result.stderr, file=sys.stderr, end='')
    if result.returncode:
        if result.stdout: print(result.stdout, end='')
        raise RuntimeError('Não foi possível validar: ' + str(args[0]))
    return result.stdout.strip()


def archive(package, version, caches):
    for cache in caches:
        for candidate in sorted(cache.glob(package + '-*.pkg.tar.*')):
            if candidate.name.endswith('.sig') or candidate.is_symlink() or not candidate.is_file():
                continue
            if command(['/usr/bin/pacman', '-Qp', candidate]).split() == [package, version]:
                return candidate
    raise RuntimeError('Pacote candidato não disponível no cache para teste: ' + package + ' ' + version)


def repository_version(package):
    info = command(['/usr/bin/pacman', '-Si', package])
    versions = re.findall(r'^Version\s*:\s*(\S+)\s*$', info, re.M)
    if len(versions) != 1 or not re.fullmatch(r'[a-zA-Z0-9_.+:\-]+', versions[0]):
        raise RuntimeError('Não consegui identificar a versão candidata de ' + package)
    return versions[0]


def verify_modules(root, release, version):
    for name in ('nvidia', 'nvidia-modeset', 'nvidia-uvm', 'nvidia-drm'):
        files = [p for p in root.rglob(name + '.ko*') if p.is_file() and not p.is_symlink()]
        if not files:
            raise RuntimeError('Compilação candidata incompleta: ' + name)
        for path in files:
            if command(['/usr/bin/modinfo', '-F', 'version', path]) != version:
                raise RuntimeError('A compilação não preservou a versão NVIDIA: ' + name)
            vermagic = command(['/usr/bin/modinfo', '-F', 'vermagic', path]).split()
            if not vermagic or vermagic[0] != release:
                raise RuntimeError('Módulo compilado para outro kernel: ' + name)


def verify_candidate(kernel, version, work):
    candidate_version = repository_version(kernel)
    headers_version = repository_version(PAIRS[kernel])
    if candidate_version != headers_version:
        raise RuntimeError('Kernel e headers candidatos não têm a mesma versão.')
    installed = command(['/usr/bin/pacman', '-Q', 'nvidia-open-dkms']).split()
    if len(installed) != 2 or not installed[1].startswith(version + '-'):
        raise RuntimeError('O pacote NVIDIA instalado diverge da versão fixada; não será substituído.')
    source = SOURCE_ROOT / ('nvidia-' + version)
    if not (source / 'dkms.conf').is_file():
        raise RuntimeError('Fonte DKMS da NVIDIA fixada ausente; kernel preservado.')
    caches = [Path(p) for p in command(['/usr/bin/pacman-conf', 'CacheDir']).splitlines() if p]
    if not caches:
        raise RuntimeError('Cache do pacman indisponível; kernel preservado.')
    root = work / kernel
    root.mkdir(mode=0o700)
    for package in (kernel, PAIRS[kernel]):
        package_path = archive(package, candidate_version, caches)
        # Pacman invokes this PreTransaction hook only after signature/integrity
        # validation. Extract data only; never execute package install scripts.
        command(['/usr/bin/bsdtar', '-xf', package_path, '-C', root, 'usr/lib/modules'])
    modules = root / 'usr/lib/modules'
    candidates = [p.parent for p in modules.glob('*/pkgbase') if p.read_text().strip() == kernel]
    if len(candidates) != 1 or not (candidates[0] / 'build/Makefile').is_file():
        raise RuntimeError('Árvore de kernel/headers candidata incompleta.')
    release = candidates[0].name
    if not re.fullmatch(r'[a-zA-Z0-9_.+\-]+', release):
        raise RuntimeError('Release candidato inválido.')
    dkms_tree = root / 'dkms'
    dkms_tree.mkdir(mode=0o700)
    script = '''set -euo pipefail
export PATH=/usr/bin:/bin
mount --bind "$1" /usr/lib/modules
mount --bind /usr/src /usr/src
mount -o remount,bind,ro /usr/src
dkms add -m nvidia -v "$2" --dkmstree "$4" --sourcetree /usr/src --installtree "$1"
dkms build -m nvidia -v "$2" -k "$3" --dkmstree "$4" --sourcetree /usr/src --installtree "$1"
'''
    print('Testando NVIDIA ' + version + ' no kernel candidato ' + release + ' antes de instalar.', flush=True)
    output = command(['/usr/bin/unshare', '--mount', '--propagation', 'private', '/usr/bin/bash', '-c',
                      script, 'callas-kernel-build', modules, version, release, dkms_tree])
    if output: print(output)
    verify_modules(dkms_tree, release, version)
    print('Compilação candidata validada: ' + kernel + ' / NVIDIA ' + version, flush=True)


DRIVER = ('nvidia-open-dkms', 'nvidia-utils', 'lib32-nvidia-utils')
DRIVER_OPTIONAL = ('nvidia-settings', 'libxnvctrl', 'opencl-nvidia', 'lib32-opencl-nvidia')
DRIVER_CONTEXT = 'nvidia-selection'
DRIVER_VERSION = re.compile(r'[0-9]+(?:\.[0-9]+){1,3}')
ARCHIVE_URL = 'https://archive.archlinux.org/packages'
MODULES = Path('/usr/lib/modules')
KERNEL_CHECK = '/usr/local/libexec/callas-kernel-check'
DRIVER_LOCK = Path('/run/lock/callas-nvidia-selection.lock')


def installed_driver():
    result = subprocess.run(['/usr/bin/pacman', '-Q', *DRIVER, *DRIVER_OPTIONAL],
                            capture_output=True, text=True, timeout=15)
    if result.returncode not in (0, 1):
        raise RuntimeError('Falha ao consultar a pilha NVIDIA.')
    packages = dict(line.split() for line in result.stdout.splitlines())
    if not set(DRIVER) <= packages.keys():
        raise RuntimeError('O seletor requer a pilha NVIDIA Open DKMS de 64 e 32 bits do Callas OS.')
    return packages


def archive_index(package):
    url = f'{ARCHIVE_URL}/{package[0]}/{package}/'
    request = urllib.request.Request(url, headers={'User-Agent': 'CallasOS-NVIDIA'})
    with urllib.request.urlopen(request, timeout=12) as response:
        html = response.read(3_000_000).decode('utf-8')
    pattern = rf'href="({re.escape(package)}-({DRIVER_VERSION.pattern})-([0-9]+(?:\.[0-9]+)?)-(?:x86_64|any)\.pkg\.tar\.zst)\.sig"'
    versions = {}
    for filename, version, release in re.findall(pattern, html):
        if f'href="{filename}"' not in html:
            continue
        key = tuple(map(int, release.split('.')))
        if version not in versions or versions[version][0] < key:
            versions[version] = (key, f'{url}{filename}')
    return {version: entry[1] for version, entry in versions.items()}


def driver_catalog(packages):
    with ThreadPoolExecutor(max_workers=len(packages)) as pool:
        indices = dict(zip(packages, pool.map(archive_index, packages)))
    common = set.intersection(*(set(index) for index in indices.values()))
    return {version: [indices[package][version] for package in packages]
            for version in sorted(common, key=lambda value: tuple(map(int, value.split('.'))), reverse=True)}


def download_driver(urls, directory):
    directory.mkdir()
    paths = []
    for url in urls:
        target = directory / url.rsplit('/', 1)[-1]
        for suffix in ('.sig', ''):
            command(['/usr/bin/curl', '--fail', '--silent', '--show-error',
                     '--location', '--proto', '=https', '--proto-redir', '=https', '--max-time', '600', '--output', str(target) + suffix, url + suffix])
        paths.append(target)
    return paths


def driver_preflight(targets, version, directory):
    if not DRIVER_VERSION.fullmatch(version):
        raise RuntimeError('Versão NVIDIA inválida.')
    installed = installed_driver()
    if set(targets) != set(installed):
        raise RuntimeError('A troca só pode alterar os pacotes NVIDIA instalados.')
    paths = list(directory.glob('*.pkg.tar.zst'))
    metadata = [command(['/usr/bin/pacman', '-Qp', path]).split() for path in paths]
    if (len(metadata) != len(installed) or {row[0] for row in metadata} != set(installed)
            or any(row[1].rsplit('-', 1)[0] != version for row in metadata)):
        raise RuntimeError('Os pacotes não correspondem à seleção NVIDIA.')
    by_package = {row[0]: path for row, path in zip(metadata, paths)}
    device_ids = {path.read_text().strip()[2:].lower()
                  for path in Path('/sys/bus/pci/drivers/nvidia').glob('*:*:*.*/device')}
    if not device_ids:
        raise RuntimeError('Nenhuma GPU está ativa com o driver NVIDIA atual.')
    chips = command(['/usr/bin/bsdtar', '-xOf', by_package['nvidia-utils'],
                     'usr/share/doc/nvidia/html/supportedchips.html'])
    supported = set(re.findall(r'<tr id="devid([0-9a-f]{4})', chips.lower()))
    if not device_ids <= supported:
        raise RuntimeError('A versão selecionada não confirma suporte a todas as GPUs NVIDIA em uso.')
    dkms_package = by_package[DRIVER[0]]
    with tempfile.TemporaryDirectory(prefix='callas-nvidia-build-', dir='/var/tmp') as temp:
        root = Path(temp)
        source = f'usr/src/nvidia-{version}'
        command(['/usr/bin/bsdtar', '-xf', dkms_package, '-C', root, source])
        if not (root / source / 'dkms.conf').is_file():
            raise RuntimeError('Fonte DKMS ausente no pacote NVIDIA selecionado.')
        for kernel in PAIRS:
            releases = [path.parent for path in MODULES.glob('*/pkgbase')
                        if path.read_text().strip() == kernel]
            if len(releases) != 1 or not (releases[0] / 'build/Makefile').is_file():
                raise RuntimeError('Kernel/headers indisponíveis: ' + kernel)
            release = releases[0].name
            tree = root / kernel
            tree.mkdir()
            script = """set -euo pipefail
mount --bind /usr/lib/modules /usr/lib/modules
mount -o remount,bind,ro /usr/lib/modules
mount --bind "$1" /usr/src
mount -o remount,bind,ro /usr/src
dkms add -m nvidia -v "$2" --dkmstree "$4"
dkms build -m nvidia -v "$2" -k "$3" --dkmstree "$4"
"""
            print(f'Testando NVIDIA {version} em {release} antes de instalar.', flush=True)
            command(['/usr/bin/unshare', '--mount', '--propagation', 'private', '/usr/bin/bash',
                     '-c', script, 'callas-nvidia-build', root / 'usr/src', version, release, tree])
            verify_modules(tree, release, version)


def run_driver_transaction(paths, version, work):
    env = dict(os.environ, CALLAS_KERNEL_UPDATE_CONTEXT=DRIVER_CONTEXT,
               CALLAS_NVIDIA_TARGET=version, CALLAS_NVIDIA_PACKAGES=str(paths[0].parent),
               LC_ALL='C', PATH='/usr/bin:/bin')
    subprocess.run(['/usr/bin/pacman', '--config', str(work / 'pacman.conf'),
                    '--hookdir', str(HOOK_DIRECTORY), '--hookdir', str(work / 'hooks'),
                    '-U', '--noconfirm', '--', *map(str, paths)], check=True, env=env,
                   stdin=subprocess.DEVNULL)
    if any(value.rsplit('-', 1)[0] != version for value in installed_driver().values()):
        raise RuntimeError('O pacman não confirmou toda a pilha NVIDIA selecionada.')
    if Path('/var/lib/callas-os/kernel-check-failed').exists():
        raise RuntimeError('A verificação de boot após a troca NVIDIA falhou.')
    subprocess.run([KERNEL_CHECK, '--verify-only'], check=True, env=env)
    with tempfile.NamedTemporaryFile(mode='w', dir=VERSION_FILE.parent, delete=False) as marker:
        marker_path = Path(marker.name)
        try:
            marker.write(version + '\n')
            marker.flush()
            os.fchmod(marker.fileno(), 0o644)
            os.fsync(marker.fileno())
            marker_path.replace(VERSION_FILE)
        finally:
            marker_path.unlink(missing_ok=True)


def select_driver(version):
    if not DRIVER_VERSION.fullmatch(version):
        raise ValueError('Versão NVIDIA inválida.')
    check_hooks()
    command(['/usr/bin/mountpoint', '-q', '/boot'])
    with DRIVER_LOCK.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        current = VERSION_FILE.read_text().strip()
        packages = installed_driver()
        if current == version and all(value.rsplit('-', 1)[0] == version for value in packages.values()):
            return
        catalog = driver_catalog(packages)
        if current not in catalog or version not in catalog:
            raise RuntimeError('O arquivo oficial não oferece a pilha completa selecionada e a versão de retorno.')
        with tempfile.TemporaryDirectory(prefix='callas-nvidia-selection-', dir='/var/tmp') as temp:
            work = Path(temp)
            (work / 'pacman.conf').write_text('[options]\nArchitecture = auto\nSigLevel = Required\nLocalFileSigLevel = Required\n')
            (work / 'hooks').mkdir()
            (work / 'hooks/00-0-callas-nvidia-no-remove.hook').write_text(
                '[Trigger]\nOperation = Remove\nType = Package\nTarget = *\n\n'
                '[Action]\nWhen = PreTransaction\nNeedsTargets\nAbortOnFail\n'
                'Exec = /usr/local/libexec/callas-kernel-policy --remove\n')
            old_urls = []
            if all(value.rsplit('-', 1)[0] == current for value in packages.values()):
                for (package, old_version), url in zip(packages.items(), catalog[current]):
                    architecture = url.rsplit('-', 1)[-1]
                    old_urls.append(f'{ARCHIVE_URL}/{package[0]}/{package}/{package}-{old_version}-{architecture}')
            elif version != current:
                raise RuntimeError('A pilha instalada diverge da fixação. Selecione a versão fixada para repará-la.')
            previous = download_driver(old_urls, work / 'previous') if old_urls else []
            for path in previous:
                command(['/usr/bin/pacman-key', '--verify', str(path) + '.sig', path])
            selected = download_driver(catalog[version], work / 'selected')
            try:
                run_driver_transaction(selected, version, work)
            except Exception:
                if previous and installed_driver() != packages:
                    print('A troca falhou. Restaurando a versão NVIDIA anterior.', flush=True)
                    run_driver_transaction(previous, current, work)
                raise


def guard(targets, context, version):
    targets = set(targets)
    if version and targets & PINNED:
        raise RuntimeError('A transação tentaria alterar a NVIDIA fixada; operação bloqueada.')
    kernels = {p for p in targets if p.startswith('linux') and p not in ('linux-firmware', 'linux-api-headers')
               and not p.startswith('linux-firmware-')}
    if not kernels:
        return
    if context != 'general':
        raise RuntimeError('Kernel só pode ser atualizado pela opção 4 — Atualizar geral.')
    if not kernels <= (set(PAIRS) | set(PAIRS.values())):
        raise RuntimeError('Kernel fora dos pares oficiais suportados; transação preservada.')
    if not version:
        return
    if not re.fullmatch(r'[0-9]+(?:\.[0-9]+)+', version):
        raise RuntimeError('Versão NVIDIA fixada inválida.')
    for kernel, headers in PAIRS.items():
        if (kernel in kernels) != (headers in kernels):
            raise RuntimeError('Kernel e headers precisam estar juntos na transação; par incompleto preservado: ' + kernel)
    if any(p in BUILD_PACKAGES or p.startswith(('gcc', 'binutils', 'llvm', 'clang')) for p in targets):
        raise RuntimeError('O ambiente de compilação também mudaria nesta transação; não é seguro aprovar o kernel com o ambiente antigo. Kernel preservado.')
    with tempfile.TemporaryDirectory(prefix='callas-kernel-preflight-', dir='/var/tmp') as temp:
        for kernel in sorted(PAIRS):
            if kernel in kernels or PAIRS[kernel] in kernels:
                verify_candidate(kernel, version, Path(temp))


def main():
    args = sys.argv[1:]
    if args == ['--nvidia-list']:
        if not VERSION_FILE.is_file():
            raise RuntimeError('Nenhum driver NVIDIA fixado foi encontrado neste Callas OS.')
        current = VERSION_FILE.read_text().strip()
        packages = installed_driver()
        state = {'fixed': current, 'installed': packages['nvidia-utils'].rsplit('-', 1)[0],
                 'coherent': all(value.rsplit('-', 1)[0] == current for value in packages.values()),
                 'versions': []}
        try:
            state['versions'] = list(driver_catalog(packages))
        except (OSError, ValueError):
            state['error'] = 'Arquivo do Arch indisponível. Tente atualizar a lista.'
        print(json.dumps(state))
        return 0
    if os.geteuid() == 0 and len(args) == 2 and args[0] == '--nvidia-select':
        select_driver(args[1])
        return 0
    if os.geteuid() != 0 or args not in ([], ['--remove'], ['--check-hooks']):
        raise RuntimeError('Uso interno do hook PreTransaction, como root.')
    if sys.argv[1:] == ['--check-hooks']:
        check_hooks()
        return 0
    targets = sys.stdin.read().splitlines()
    version = VERSION_FILE.read_text().strip() if VERSION_FILE.exists() else None
    if version and any(p in set(PAIRS) | set(PAIRS.values()) for p in targets):
        print('Verificando kernel candidato e NVIDIA fixada antes de alterar pacotes; a compilação pode levar alguns minutos.', flush=True)
    log = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        try:
            if os.environ.get('CALLAS_KERNEL_UPDATE_CONTEXT') == DRIVER_CONTEXT:
                if args == ['--remove']:
                    raise RuntimeError('A seleção NVIDIA não pode remover pacotes.')
                driver_preflight(targets, os.environ['CALLAS_NVIDIA_TARGET'],
                                 Path(os.environ['CALLAS_NVIDIA_PACKAGES']))
            else:
                context = 'remove' if sys.argv[1:] == ['--remove'] else os.environ.get('CALLAS_KERNEL_UPDATE_CONTEXT', '')
                guard(targets, context, version)
        except Exception as exc:
            operation = ('Troca NVIDIA' if os.environ.get('CALLAS_KERNEL_UPDATE_CONTEXT') == DRIVER_CONTEXT
                         else 'Atualização de kernel')
            print(operation + ' bloqueada antes de alterar pacotes: ' + str(exc))
            print('Kernel, headers e driver anteriores serão preservados. Nenhuma atualização parcial será aplicada.')
            code = 1
    text = log.getvalue()
    if not text:
        return code
    print(text, end='', flush=True)
    # Keep a persistent diagnosis even when the application-log exporter fails.
    path = Path('/var/lib/callas-os/kernel-preflight-last.log')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(0o600)
    logger = Path('/usr/local/libexec/callas-logs')
    if logger.is_file():
        result = subprocess.run([str(logger), '--record', 'Kernel Linux'], input=text, text=True, check=False)
        if result.returncode:
            print('Diagnóstico preservado em ' + str(path), file=sys.stderr)
    return code


if __name__ == '__main__':
    try:
        os.umask(0o077)
        sys.exit(main())
    except Exception as exc:
        print('Não consegui validar a transação de kernel: ' + str(exc), file=sys.stderr)
        sys.exit(1)
