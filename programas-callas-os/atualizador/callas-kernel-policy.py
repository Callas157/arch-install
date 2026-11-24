#!/usr/bin/python3
"""Abort installed-system kernel transactions before hooks remove working modules.

General and the manual selector may request kernels. With NVIDIA, candidate official kernel
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
import shutil
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


def verify_candidate(kernel, version, work, *, packages=None):
    installed = command(['/usr/bin/pacman', '-Q', 'nvidia-open-dkms']).split()
    if len(installed) != 2 or not installed[1].startswith(version + '-'):
        raise RuntimeError('O pacote NVIDIA instalado diverge da versão fixada; não será substituído.')
    source = SOURCE_ROOT / ('nvidia-' + version)
    if not (source / 'dkms.conf').is_file():
        raise RuntimeError('Fonte DKMS da NVIDIA fixada ausente; kernel preservado.')
    if packages is None:
        candidate_version = repository_version(kernel)
        if candidate_version != repository_version(PAIRS[kernel]):
            raise RuntimeError('Kernel e headers candidatos não têm a mesma versão.')
        caches = [Path(p) for p in command(['/usr/bin/pacman-conf', 'CacheDir']).splitlines() if p]
        if not caches:
            raise RuntimeError('Cache do pacman indisponível; kernel preservado.')
        packages = [archive(package, candidate_version, caches) for package in (kernel, PAIRS[kernel])]
    root = work / kernel
    root.mkdir(mode=0o700)
    for package_path in packages:
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
PCI_DEVICES = Path('/sys/bus/pci/devices')
KERNEL_CHECK = '/usr/local/libexec/callas-kernel-check'
DRIVER_LOCK = Path('/run/lock/callas-nvidia-selection.lock')
WORK_DIRECTORY = Path('/var/tmp')
KERNEL_CONTEXT = 'kernel-selection'
ARCH_VERSION = re.compile(r'[0-9][0-9A-Za-z_.+]*-[0-9]+(?:\.[0-9]+)*')
PRIMARY_PAIR = ('linux', PAIRS['linux'])
INITIAL_KERNEL = '7.2.15.arch1-1'
INITIAL_DRIVER = '610.57.04'


class SelectionVerificationError(RuntimeError):
    def __init__(self, message, expected):
        super().__init__(message)
        self.expected = expected


def installed_driver(*, required=True):
    result = subprocess.run(['/usr/bin/pacman', '-Q', *DRIVER, *DRIVER_OPTIONAL],
                            capture_output=True, text=True, timeout=15)
    if result.returncode not in (0, 1):
        raise RuntimeError('Falha ao consultar a pilha NVIDIA.')
    packages = dict(line.split() for line in result.stdout.splitlines())
    if not required and not set(DRIVER) & packages.keys():
        return {}
    if not set(DRIVER) <= packages.keys():
        raise RuntimeError('O seletor requer a pilha NVIDIA Open DKMS de 64 e 32 bits do Callas OS.')
    return packages


def package_index(package):
    url = f'{ARCHIVE_URL}/{package[0]}/{package}/'
    request = urllib.request.Request(url, headers={'User-Agent': 'CallasOS-Packages'})
    with urllib.request.urlopen(request, timeout=12) as response:
        html = response.read(8_000_001).decode('utf-8')
    if len(html) > 8_000_000:
        raise ValueError('Índice de pacotes acima do limite: ' + package)
    links = set(re.findall(r'href="([^"/]+)"', html))
    pattern = re.compile(rf'{re.escape(package)}-({ARCH_VERSION.pattern})-(?:x86_64|any)\.pkg\.tar\.zst')
    return {match[1]: url + filename for filename in sorted(links)
            if (match := pattern.fullmatch(filename)) and filename + '.sig' in links}


def archive_index(package):
    versions = {}
    for pkgver, url in package_index(package).items():
        version, release = pkgver.rsplit('-', 1)
        if not DRIVER_VERSION.fullmatch(version):
            continue
        key = tuple(map(int, release.split('.')))
        if version not in versions or versions[version][0] < key:
            versions[version] = (key, url)
    return {version: entry[1] for version, entry in versions.items()}


def driver_catalog(packages):
    """Only the three driver components are mandatory. Optional tools are not
    allowed to hide an otherwise usable signed driver version."""
    names = list(dict.fromkeys((*DRIVER, *packages)))
    def safe_index(package):
        try:
            return archive_index(package)
        except (OSError, ValueError):
            if package in DRIVER:
                raise
            return {}
    with ThreadPoolExecutor(max_workers=min(len(names), 8)) as pool:
        indices = dict(zip(names, pool.map(safe_index, names)))
    common = set.intersection(*(set(indices[package]) for package in DRIVER))
    return {
        version: {package: indices[package][version] for package in names
                  if version in indices[package]}
        for version in sorted(common, key=lambda value: tuple(map(int, value.split('.'))), reverse=True)
    }


def package_url(package, version):
    return f'{ARCHIVE_URL}/{package[0]}/{package}/{package}-{version}-x86_64.pkg.tar.zst'


def default_driver():
    return {'version': INITIAL_DRIVER,
            'packages': {p: package_url(p, INITIAL_DRIVER + '-1')
                         for p in (*DRIVER, 'nvidia-settings', 'libxnvctrl')}}


def legacy_default_driver():
    # Saved installers before 3.25 reject any branch other than 595.
    tools = ('nvidia-settings', 'libxnvctrl')
    catalog = driver_catalog((*DRIVER, *tools))
    version = next((candidate for candidate in catalog if candidate.startswith('595.')), None)
    if version is None:
        raise RuntimeError('A pilha NVIDIA 595 exigida pelo instalador antigo está indisponível no Arquivo do Arch.')
    packages = {name: catalog[version][name] for name in DRIVER}
    if all(name in catalog[version] for name in tools):
        packages.update({name: catalog[version][name] for name in tools})
    return {'version': version, 'packages': packages}


def kernel_catalog():
    with ThreadPoolExecutor(max_workers=2) as pool:
        kernel, headers = pool.map(package_index, PRIMARY_PAIR)
    versions = sorted(kernel.keys() & headers.keys(),
                      key=lambda version: tuple(int(part) if part.isdigit() else part
                                                for part in re.split(r'([0-9]+)', version)),
                      reverse=True)
    return {v: dict(zip(PRIMARY_PAIR, (kernel[v], headers[v]))) for v in versions}


def stage_packages(urls, directory):
    directory.mkdir()
    caches = [Path(path) for path in command(['/usr/bin/pacman-conf', 'CacheDir']).splitlines()]
    paths = []
    for url in urls:
        target = directory / url.rsplit('/', 1)[-1]
        signature = target.with_name(target.name + '.sig')
        for cache in caches:
            files = (cache / target.name, cache / signature.name)
            if all(path.is_file() and not path.is_symlink() for path in files):
                shutil.copyfile(files[0], target)
                shutil.copyfile(files[1], signature)
                break
        else:
            for suffix in ('.sig', ''):
                command(['/usr/bin/curl', '--fail', '--silent', '--show-error', '--retry', '2',
                         '--location', '--proto', '=https', '--proto-redir', '=https',
                         '--max-time', '600', '--output', str(target) + suffix, url + suffix])
        command(['/usr/bin/pacman-key', '--verify', signature, target])
        paths.append(target)
    return paths


def primary_version():
    packages = dict(line.split() for line in command(['/usr/bin/pacman', '-Q', *PRIMARY_PAIR]).splitlines())
    version = packages.get('linux', '')
    if not ARCH_VERSION.fullmatch(version) or packages.get(PAIRS['linux']) != version:
        raise RuntimeError('Os pacotes linux e linux-headers instalados precisam ter a mesma versão.')
    return version


def kernel_preflight(targets, version, directory, expected=None):
    if set(targets) != set(PRIMARY_PAIR):
        raise RuntimeError('A seleção pode alterar apenas o par linux e linux-headers.')
    if not ARCH_VERSION.fullmatch(version):
        raise RuntimeError('Versão de kernel inválida.')
    if expected is not None and primary_version() != expected:
        raise RuntimeError('O kernel principal mudou durante a preparação. Atualize a lista na Central.')
    paths = sorted(directory.glob('*.pkg.tar.zst'))
    metadata = sorted(command(['/usr/bin/pacman', '-Qp', path]).split() for path in paths)
    if metadata != sorted([package, version] for package in PRIMARY_PAIR):
        raise RuntimeError('Os pacotes não correspondem ao par de kernel selecionado.')
    driver = installed_driver(required=False)
    if driver or VERSION_FILE.is_file():
        driver_version = VERSION_FILE.read_text().strip() if VERSION_FILE.is_file() else ''
        if (not DRIVER_VERSION.fullmatch(driver_version)
                or any(driver.get(name, '').rsplit('-', 1)[0] != driver_version for name in DRIVER)):
            raise RuntimeError('Registro NVIDIA inconsistente. Use "Reparar versão instalada" na Central.')
        with tempfile.TemporaryDirectory(prefix='callas-kernel-preflight-', dir=WORK_DIRECTORY) as temp:
            verify_candidate('linux', driver_version, Path(temp), packages=paths)


def run_kernel_transaction(paths, version, work, *, expected):
    env = dict(os.environ, CALLAS_KERNEL_UPDATE_CONTEXT=KERNEL_CONTEXT,
               CALLAS_KERNEL_TARGET=version, CALLAS_KERNEL_EXPECTED=expected,
               CALLAS_KERNEL_PACKAGES=str(paths[0].parent),
               LC_ALL='C', PATH='/usr/bin:/bin')
    subprocess.run(['/usr/bin/pacman', '--config', str(work / 'pacman.conf'),
                    '--hookdir', str(HOOK_DIRECTORY), '--hookdir', str(work / 'hooks'),
                    '-U', '--noconfirm', '--', *map(str, paths)], check=True, env=env,
                   stdin=subprocess.DEVNULL)
    try:
        if primary_version() != version:
            raise RuntimeError('O pacman não confirmou o par solicitado.')
        if Path('/var/lib/callas-os/kernel-check-failed').exists():
            raise RuntimeError('O hook de boot falhou após a troca de kernel.')
        subprocess.run([KERNEL_CHECK, '--verify-only'], check=True, env=env)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        raise SelectionVerificationError(str(error), version) from error


def prepare_local_transaction(work):
    (work / 'pacman.conf').write_text('[options]\nArchitecture = auto\nSigLevel = Required\nLocalFileSigLevel = Required\n')
    (work / 'hooks').mkdir()
    (work / 'hooks/00-0-callas-no-remove.hook').write_text(
        '[Trigger]\nOperation = Remove\nType = Package\nTarget = *\n\n'
        '[Action]\nWhen = PreTransaction\nNeedsTargets\nAbortOnFail\n'
        'Exec = /usr/local/libexec/callas-kernel-policy --remove\n')


def select_kernel(version):
    if not ARCH_VERSION.fullmatch(version):
        raise ValueError('Versão de kernel inválida.')
    check_hooks()
    command(['/usr/bin/mountpoint', '-q', '/boot'])
    with DRIVER_LOCK.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        current = primary_version()
        if version == current:
            return
        with tempfile.TemporaryDirectory(prefix='callas-kernel-selection-', dir=WORK_DIRECTORY) as temp:
            work = Path(temp)
            prepare_local_transaction(work)
            previous = stage_packages([package_url(p, current) for p in PRIMARY_PAIR], work / 'previous')
            selected = stage_packages([package_url(p, version) for p in PRIMARY_PAIR], work / 'selected')
            try:
                run_kernel_transaction(selected, version, work, expected=current)
            except SelectionVerificationError as error:
                print(str(error), flush=True)
                try:
                    run_kernel_transaction(previous, current, work, expected=error.expected)
                except Exception as rollback:
                    raise RuntimeError('Não consegui restaurar o kernel anterior. Consulte os detalhes e use o LTS no GRUB.') from rollback
                print(f'Kernel anterior {current} restaurado e verificado.', flush=True)
                raise


def nvidia_device_ids():
    device_ids = set()
    for device in PCI_DEVICES.iterdir():
        try:
            if ((device / 'vendor').read_text().strip() == '0x10de'
                    and (device / 'class').read_text().startswith('0x03')):
                device_ids.add((device / 'device').read_text().strip()[2:].lower())
        except FileNotFoundError:
            continue
    return device_ids


def current_nvidia_devices(chips):
    table = re.search(r'<h3>\s*Current NVIDIA GPUs\s*</h3>.*?<table\b[^>]*>(.*?)</table>', chips,
                      re.IGNORECASE | re.DOTALL)
    if table is None:
        raise RuntimeError('Tabela de GPUs atuais ausente na documentação NVIDIA.')
    return set(re.findall(r'<tr\s+id="devid([0-9a-f]{4})', table[1].lower()))


def check_nvidia_hardware(utils_package, version):
    device_ids = nvidia_device_ids()
    if not device_ids:
        raise RuntimeError('Nenhuma GPU NVIDIA foi detectada no barramento PCI.')
    chips = command(['/usr/bin/bsdtar', '-xOf', utils_package,
                     'usr/share/doc/nvidia/html/supportedchips.html'])
    supported = current_nvidia_devices(chips)
    if int(version.split('.')[0]) < 590:
        # Those lists also include GPUs supported only by the proprietary module.
        url = f'https://download.nvidia.com/XFree86/Linux-x86_64/{INITIAL_DRIVER}/README/supportedchips.html'
        with urllib.request.urlopen(url, timeout=15) as response:
            supported &= current_nvidia_devices(response.read(1_000_000).decode('utf-8'))
    unsupported = sorted(device_ids - supported)
    if unsupported:
        raise RuntimeError('A versão selecionada não confirma suporte às GPUs NVIDIA: ' + ', '.join(unsupported))


def driver_preflight(targets, version, directory, expected=None):
    if not DRIVER_VERSION.fullmatch(version):
        raise RuntimeError('Versão NVIDIA inválida.')
    installed = installed_driver()
    if expected is not None and installed != expected:
        raise RuntimeError('A pilha NVIDIA mudou durante a preparação. Atualize a lista na Central.')
    if not set(DRIVER) <= set(targets) or not set(targets) <= set(installed):
        raise RuntimeError('A seleção só pode alterar a pilha NVIDIA Open DKMS completa.')
    paths = list(directory.glob('*.pkg.tar.zst'))
    metadata = [command(['/usr/bin/pacman', '-Qp', path]).split() for path in paths]
    if (len(metadata) != len(targets) or {row[0] for row in metadata} != set(targets)
            or any(row[1].rsplit('-', 1)[0] != version for row in metadata)):
        raise RuntimeError('Os pacotes não correspondem à seleção NVIDIA.')
    by_package = {row[0]: path for row, path in zip(metadata, paths)}
    check_nvidia_hardware(by_package['nvidia-utils'], version)
    dkms_package = by_package[DRIVER[0]]
    with tempfile.TemporaryDirectory(prefix='callas-nvidia-build-', dir=WORK_DIRECTORY) as temp:
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
            # Prepare the known compatibility patches in the extracted candidate.
            if version in ('595.71.05', INITIAL_DRIVER):
                command(['/usr/bin/env', 'CALLAS_NVIDIA_REPAIR_TARGET=' + version,
                         '/usr/bin/python3', '/usr/local/libexec/callas-nvidia-prepare',
                         '--compat-tree', root / source, release])
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


def run_driver_transaction(paths, version, work, *, expected):
    selected = dict(command(['/usr/bin/pacman', '-Qp', path]).split() for path in paths)
    candidate = {**expected, **selected}
    env = dict(os.environ, CALLAS_KERNEL_UPDATE_CONTEXT=DRIVER_CONTEXT,
               CALLAS_NVIDIA_TARGET=version, CALLAS_NVIDIA_REPAIR_TARGET=version,
               CALLAS_NVIDIA_EXPECTED=json.dumps(expected),
               CALLAS_NVIDIA_PACKAGES=str(paths[0].parent),
               LC_ALL='C', PATH='/usr/bin:/bin')
    subprocess.run(['/usr/bin/pacman', '--config', str(work / 'pacman.conf'),
                    '--hookdir', str(HOOK_DIRECTORY), '--hookdir', str(work / 'hooks'),
                    '-U', '--noconfirm', '--', *map(str, paths)], check=True, env=env,
                   stdin=subprocess.DEVNULL)
    try:
        if installed_driver() != candidate:
            raise RuntimeError('O pacman não confirmou todos os componentes NVIDIA substituídos.')
        if Path('/var/lib/callas-os/kernel-check-failed').exists():
            raise RuntimeError('A verificação de boot após a troca NVIDIA falhou.')
        subprocess.run([KERNEL_CHECK, '--verify-only'], check=True, env=env)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        raise SelectionVerificationError(str(error), candidate) from error
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
        packages = installed_driver()
        versions = {packages[name].rsplit('-', 1)[0] for name in DRIVER}
        if len(versions) != 1:
            raise RuntimeError('Os três pacotes NVIDIA instalados precisam ter a mesma versão antes da troca.')
        current = versions.pop()
        if current == version:
            # The GUI exposes a dedicated repair path for missing modules.
            if not modules_coherent(version):
                raise RuntimeError('Módulos NVIDIA ausentes. Use "Reparar versão instalada" na Central.')
            return
        try:
            available = driver_catalog(packages).get(version, {})
        except (OSError, ValueError):
            available = {}
        selected_urls = {p: available.get(p, package_url(p, version + '-1')) for p in DRIVER}
        tools = ('nvidia-settings', 'libxnvctrl')
        if all(p in packages and p in available and packages[p].rsplit('-', 1)[0] == current for p in tools):
            selected_urls.update({p: available[p] for p in tools})
        for package in ('opencl-nvidia', 'lib32-opencl-nvidia'):
            if package in packages:
                if packages[package].rsplit('-', 1)[0] != current:
                    raise RuntimeError('O componente OpenCL instalado diverge da versão NVIDIA: ' + package)
                selected_urls[package] = available.get(package, package_url(package, version + '-1'))
        with tempfile.TemporaryDirectory(prefix='callas-nvidia-selection-', dir=WORK_DIRECTORY) as temp:
            work = Path(temp)
            prepare_local_transaction(work)
            # The archive package installs unpatched DKMS sources. This hook
            # runs before 70-dkms-install and after pacman unpacked the source;
            # otherwise the candidate preflight would succeed but the real
            # installed module would still fail to build on Linux 7.3.
            (work / 'hooks/30-callas-nvidia-compat.hook').write_text(
                '[Trigger]\nOperation = Install\nOperation = Upgrade\n'
                'Type = Package\nTarget = nvidia-open-dkms\n\n'
                '[Action]\nDescription = Preparar compatibilidade NVIDIA antes do DKMS\n'
                'When = PostTransaction\n'
                'Exec = /usr/local/libexec/callas-nvidia-prepare --compat-installed\n')
            old_urls = [package_url(p, packages[p]) for p in selected_urls]
            previous = stage_packages(old_urls, work / 'previous')
            selected = stage_packages(list(selected_urls.values()), work / 'selected')
            try:
                run_driver_transaction(selected, version, work, expected=packages)
            except SelectionVerificationError as error:
                print(str(error), flush=True)
                print('A troca falhou. Restaurando a versão NVIDIA anterior.', flush=True)
                try:
                    run_driver_transaction(previous, current, work, expected=error.expected)
                except Exception as rollback:
                    raise RuntimeError('Não consegui restaurar a NVIDIA anterior. Consulte os detalhes antes de reiniciar.') from rollback
                raise



def installed_release_map():
    """Determine the actual installed kernel releases; never use uname here."""
    found = {}
    for base in MODULES.glob('*/pkgbase'):
        if base.is_symlink() or not base.is_file():
            continue
        name = base.read_text().strip()
        if name not in PAIRS:
            continue
        release = base.parent.name
        if name in found or not re.fullmatch(r'[a-zA-Z0-9_.+-]+', release):
            raise RuntimeError('Identificação ambígua do kernel ' + name)
        if not (base.parent / 'build/Makefile').is_file():
            raise RuntimeError('Headers ausentes para ' + release)
        found[name] = release
    if set(found) != set(PAIRS):
        raise RuntimeError('Os kernels linux e linux-lts e seus headers são necessários.')
    return found


def modules_coherent(version):
    """Read-only, installed-kernel test for all four NVIDIA modules."""
    for release in installed_release_map().values():
        for name in ('nvidia', 'nvidia-modeset', 'nvidia-uvm', 'nvidia-drm'):
            result = subprocess.run(['/usr/bin/modinfo', '-k', release, '-F', 'version', name],
                                    capture_output=True, text=True, timeout=10)
            magic = subprocess.run(['/usr/bin/modinfo', '-k', release, '-F', 'vermagic', name],
                                   capture_output=True, text=True, timeout=10)
            if result.returncode or result.stdout.strip() != version:
                return False
            if magic.returncode or not magic.stdout.split() or magic.stdout.split()[0] != release:
                return False
    return True


def repair_driver(*, adopt_installed=False, expected=None):
    """Rebuild the installed branch only. Adopting a mismatched pin requires a click."""
    check_hooks()
    command(['/usr/bin/mountpoint', '-q', '/boot'])
    with DRIVER_LOCK.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        packages = installed_driver()
        versions = {packages[name].rsplit('-', 1)[0] for name in DRIVER}
        if len(versions) != 1:
            raise RuntimeError('Pacotes NVIDIA essenciais de versões diferentes. Nenhuma troca automática permitida.')
        installed = versions.pop()
        if not DRIVER_VERSION.fullmatch(installed):
            raise RuntimeError('Versão NVIDIA instalada inválida.')
        if expected is not None and installed != expected:
            raise RuntimeError('A NVIDIA mudou desde a confirmação. Reabra a Central.')
        fixed = VERSION_FILE.read_text().strip() if VERSION_FILE.is_file() else ''
        if fixed != installed and not adopt_installed:
            raise RuntimeError(
                f'NVIDIA instalada {installed}, mas fixada {fixed or "ausente"}. '
                'Abra Central Callas OS > Driver NVIDIA e confirme "Reparar versão instalada". '
                'Não mudarei sua escolha automaticamente.')
        if modules_coherent(installed) and fixed == installed:
            print('NVIDIA ' + installed + ' já íntegra nos kernels linux e linux-lts. Nenhuma recompilação.', flush=True)
            return
        env = dict(os.environ, PATH='/usr/bin:/bin', LC_ALL='C',
                   CALLAS_NVIDIA_REPAIR_TARGET=installed,
                   CALLAS_KERNEL_UPDATE_CONTEXT=DRIVER_CONTEXT,
                   CALLAS_NVIDIA_TARGET=installed)
        logs = Path('/var/lib/callas-os')
        logs.mkdir(parents=True, exist_ok=True)
        logfile = logs / 'nvidia-repair-last.log'
        lines = [f'Reparo NVIDIA: instalado={installed}; fixado={fixed or "ausente"}; adoção={adopt_installed}']
        def step(args, *, timeout=1800):
            print('Executando: ' + ' '.join(map(str, args)), flush=True)
            try:
                result = subprocess.run(args, env=env, stdin=subprocess.DEVNULL,
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        text=True, errors='replace', timeout=timeout)
                output = result.stdout or ''
                lines.append(output)
                if output:
                    print(output, end='' if output.endswith('\n') else '\n', flush=True)
                if result.returncode:
                    raise RuntimeError(f'Falha (código {result.returncode}): {args[0]}')
            except subprocess.TimeoutExpired as error:
                raise RuntimeError('Tempo excedido durante o reparo: ' + str(args[0])) from error
        try:
            print('Reparando módulos sem instalar outro driver ou atualizar kernels.', flush=True)
            step(['/usr/bin/python3', '/usr/local/libexec/callas-nvidia-prepare'])
            if not modules_coherent(installed):
                raise RuntimeError('A compilação não entregou os quatro módulos nos dois kernels.')
            # Both sets of modules must exist BEFORE rewriting boot images.
            step(['/usr/bin/mkinitcpio', '-P'])
            step([KERNEL_CHECK, '--verify-only'])
            if fixed != installed:
                with tempfile.NamedTemporaryFile(mode='w', dir=VERSION_FILE.parent,
                                                 prefix='.callas-nvidia-', delete=False) as marker:
                    marker_path = Path(marker.name)
                    try:
                        marker.write(installed + '\n')
                        marker.flush()
                        os.fchmod(marker.fileno(), 0o644)
                        os.fsync(marker.fileno())
                        marker_path.replace(VERSION_FILE)
                    finally:
                        marker_path.unlink(missing_ok=True)
                print('Fixação NVIDIA atualizada somente após validar módulos e boot: ' + installed, flush=True)
            print('Reparo concluído. Reinicie apenas depois de terminar a atualização.', flush=True)
        except Exception as error:
            lines.append('FALHA: ' + str(error))
            print('Reparo não concluído: ' + str(error), file=sys.stderr)
            print('Versão fixada não alterada. Não reinicie; consulte o log do reparo.', file=sys.stderr)
            raise
        finally:
            logfile.write_text('\n'.join(lines) + '\n')
            logfile.chmod(0o600)
            logger = Path('/usr/local/libexec/callas-logs')
            try:
                if logger.is_file() and not logger.is_symlink():
                    with logfile.open('rb') as stream:
                        subprocess.run([str(logger), '--record', 'Driver NVIDIA'], stdin=stream,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       check=False, timeout=30)
                    log_user_file = Path('/etc/callas-os/log-user')
                    if log_user_file.is_file():
                        log_user = log_user_file.read_text().strip()
                        if re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', log_user):
                            subprocess.run([str(logger), '--export', log_user], check=False,
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                           timeout=45)
            except (OSError, subprocess.TimeoutExpired) as error:
                print('Não consegui exportar o log NVIDIA: ' + str(error), file=sys.stderr)



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
    with tempfile.TemporaryDirectory(prefix='callas-kernel-preflight-', dir=WORK_DIRECTORY) as temp:
        for kernel in sorted(PAIRS):
            if kernel in kernels or PAIRS[kernel] in kernels:
                verify_candidate(kernel, version, Path(temp))


def main():
    args = sys.argv[1:]
    if args == ['--nvidia-default']:
        print(json.dumps(legacy_default_driver(), sort_keys=True))
        return 0
    if args == ['--nvidia-install-default']:
        print(json.dumps(default_driver(), sort_keys=True))
        return 0
    if args == ['--kernel-default']:
        print(INITIAL_KERNEL)
        return 0
    if len(args) == 2 and args[0] == '--nvidia-check-hardware':
        check_nvidia_hardware(Path(args[1]), INITIAL_DRIVER)
        return 0
    if args == ['--kernel-list']:
        with contextlib.redirect_stdout(sys.stderr):
            installed = primary_version()
            lts = command(['/usr/bin/pacman', '-Q', 'linux-lts']).split()[1]
        state = {'installed': installed, 'lts': lts, 'running': os.uname().release,
                 'versions': [INITIAL_KERNEL]}
        try:
            state['versions'] = list(dict.fromkeys((*kernel_catalog(), INITIAL_KERNEL)))
        except (OSError, ValueError):
            state['error'] = 'Lista do Arquivo do Arch indisponível. Você pode digitar a versão completa do pacote.'
        print(json.dumps(state))
        return 0
    if args == ['--nvidia-list']:
        try:
            current = VERSION_FILE.read_text().strip()
        except (FileNotFoundError, PermissionError):
            current = ''
        packages = installed_driver()
        installed = packages['nvidia-utils'].rsplit('-', 1)[0]
        coherent = all(packages[p].rsplit('-', 1)[0] == installed for p in DRIVER)
        state = {'fixed': current, 'installed': installed, 'packages_coherent': coherent,
                 'coherent': coherent and installed == current, 'modules_ok': False, 'versions': [INITIAL_DRIVER]}
        try:
            state['modules_ok'] = coherent and modules_coherent(installed)
        except RuntimeError as exc:
            state['error'] = str(exc)
        try:
            state['versions'] = list(dict.fromkeys((*driver_catalog(packages), INITIAL_DRIVER)))
        except (OSError, ValueError):
            state['error'] = 'Lista do Arquivo do Arch indisponível. Você pode digitar a versão do driver.'
        print(json.dumps(state))
        return 0
    if os.geteuid() == 0 and args == ['--nvidia-repair']:
        if VERSION_FILE.exists():
            repair_driver()
        else:
            print('Sem NVIDIA fixada: verificação de reparo ignorada.', flush=True)
        return 0
    if os.geteuid() == 0 and len(args) == 2 and args[0] == '--nvidia-repair-installed':
        if not DRIVER_VERSION.fullmatch(args[1]):
            raise RuntimeError('Versão NVIDIA inválida na confirmação.')
        repair_driver(adopt_installed=True, expected=args[1])
        return 0
    if os.geteuid() == 0 and len(args) == 2 and args[0] == '--nvidia-select':
        select_driver(args[1])
        return 0
    if os.geteuid() == 0 and len(args) == 2 and args[0] == '--kernel-select':
        select_kernel(args[1])
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
            context = os.environ.get('CALLAS_KERNEL_UPDATE_CONTEXT')
            if context == DRIVER_CONTEXT:
                if args == ['--remove']:
                    raise RuntimeError('A seleção NVIDIA não pode remover pacotes.')
                driver_preflight(targets, os.environ['CALLAS_NVIDIA_TARGET'],
                                 Path(os.environ['CALLAS_NVIDIA_PACKAGES']),
                                 json.loads(os.environ['CALLAS_NVIDIA_EXPECTED']))
            elif context == KERNEL_CONTEXT:
                if args == ['--remove']:
                    raise RuntimeError('A seleção de kernel não pode remover pacotes.')
                kernel_preflight(targets, os.environ['CALLAS_KERNEL_TARGET'],
                                 Path(os.environ['CALLAS_KERNEL_PACKAGES']), os.environ['CALLAS_KERNEL_EXPECTED'])
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
