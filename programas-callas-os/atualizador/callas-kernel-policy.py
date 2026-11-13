#!/usr/bin/python3
"""Abort installed-system kernel transactions before hooks remove working modules.

Only General may request kernels. With pinned NVIDIA, candidate official kernel
and headers must already be in pacman's verified download cache and build in a
private mount namespace. Nothing is installed by this helper; uncertainty aborts
the entire transaction. AUR/custom kernels are deliberately not approved here.
"""
import contextlib
import io
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

PAIRS = {'linux': 'linux-headers', 'linux-lts': 'linux-lts-headers'}
PINNED = {'nvidia-utils', 'nvidia-open-dkms', 'nvidia-open', 'nvidia-open-lts',
          'lib32-nvidia-utils', 'nvidia-settings', 'libxnvctrl', 'opencl-nvidia', 'lib32-opencl-nvidia'}
VERSION_FILE = Path('/etc/callas-nvidia-version')
SOURCE_ROOT = Path('/usr/src')
BUILD_PACKAGES = {'glibc', 'make', 'dkms', 'libelf', 'elfutils', 'openssl', 'zstd', 'pahole', 'python', 'libbpf',
                  'compiler-rt', 'kmod', 'sbsigntools', 'mokutil', 'util-linux'}


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
    if os.geteuid() != 0 or sys.argv[1:] not in ([], ['--remove']):
        raise RuntimeError('Uso interno do hook PreTransaction, como root.')
    targets = sys.stdin.read().splitlines()
    version = VERSION_FILE.read_text().strip() if VERSION_FILE.exists() else None
    if version and any(p in set(PAIRS) | set(PAIRS.values()) for p in targets):
        print('Verificando kernel candidato e NVIDIA fixada antes de alterar pacotes; a compilação pode levar alguns minutos.', flush=True)
    log = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        try:
            context = 'remove' if sys.argv[1:] == ['--remove'] else os.environ.get('CALLAS_KERNEL_UPDATE_CONTEXT', '')
            guard(targets, context, version)
        except Exception as exc:
            print('Atualização de kernel bloqueada antes de alterar pacotes: ' + str(exc))
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
