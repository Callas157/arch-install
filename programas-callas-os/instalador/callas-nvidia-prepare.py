#!/usr/bin/python3
"""Prepare the selected NVIDIA branch for installed Arch kernels; never change packages.

Clean-install helper. Fails before mkinitcpio/GRUB if the DKMS modules are missing.
No partitioning, mounting, kernel/package upgrade, or NVIDIA version changes.
"""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

VERSION_FILE = Path('/etc/callas-nvidia-version')
PINNED = VERSION_FILE.read_text().strip()
if not re.fullmatch(r'[0-9]+(?:\.[0-9]+){2,3}', PINNED):
    raise RuntimeError('Versão NVIDIA selecionada inválida.')
SOURCE = Path('/usr/src') / f'nvidia-{PINNED}' / 'kernel-open/nvidia/os-interface.c'
MODULES = ('nvidia', 'nvidia_modeset', 'nvidia_uvm', 'nvidia_drm')
OLD = '''void* NV_API_CALL os_dmem_cgroup_register_region(NvU64 size, const char *name)
{
    void *region = dmem_cgroup_register_region(size, name);
    if (IS_ERR(region))'''
NEW = '''void* NV_API_CALL os_dmem_cgroup_register_region(NvU64 size, const char *name)
{
#if LINUX_VERSION_CODE >= KERNEL_VERSION(7, 3, 0)
    struct dmem_cgroup_init init = { .size = size };
    void *region = dmem_cgroup_register_region(&init, name);
#else
    void *region = dmem_cgroup_register_region(size, name);
#endif
    if (IS_ERR(region))'''


def run(*command):
    print('+', ' '.join(command), flush=True)
    result = subprocess.run(command, check=False)
    if result.returncode:
        raise RuntimeError(f'Comando falhou ({result.returncode}): {" ".join(command)}')


def versions():
    result = {}
    for pkgbase in Path('/usr/lib/modules').glob('*/pkgbase'):
        if pkgbase.is_symlink() or not pkgbase.is_file():
            continue
        base = pkgbase.read_text().strip()
        if base not in ('linux', 'linux-lts'):
            continue
        if base in result:
            raise RuntimeError(f'Múltiplos kernels detectados para {base}; instalação não prosseguirá.')
        release = pkgbase.parent.name
        if not re.fullmatch(r'\d+\.\d+\.\d+[-_a-zA-Z0-9.]*', release):
            raise RuntimeError('Versão de kernel inválida: ' + release)
        build = pkgbase.parent / 'build' / 'Makefile'
        if not build.is_file():
            raise RuntimeError(f'Headers ausentes para {base} ({release}).')
        result[base] = release
    if set(result) != {'linux', 'linux-lts'}:
        raise RuntimeError('Kernel Linux e LTS com headers precisam estar instalados.')
    return result


def kernel_family(release):
    match = re.match(r'^(\d+)\.(\d+)\.', release)
    if not match:
        raise RuntimeError('Não foi possível identificar o kernel: ' + release)
    major, minor = map(int, match.groups())
    return (major, minor)


def patch_73_source(path=SOURCE):
    if path.is_symlink():
        raise RuntimeError(f'Fonte NVIDIA com link inseguro: {path}')
    if not path.is_file():
        print('Fonte sem patch dmem conhecido; DKMS determinará compatibilidade.')
        return False
    if path.stat().st_uid != 0:
        raise RuntimeError('A fonte NVIDIA deve pertencer ao root.')
    original = path.read_text(encoding='utf-8')
    if NEW in original and OLD not in original:
        print('Compatibilidade da API dmem já presente na fonte.')
        return False
    if OLD not in original and NEW not in original:
        print('Fonte NVIDIA sem assinatura dmem antiga; testando a compilação original.')
        return False
    if original.count(OLD) != 1 or NEW in original:
        raise RuntimeError('Fonte NVIDIA diferente do padrão reconhecido; nenhum patch será forçado.')
    # Use the kernel version macros independently of any indirect NVIDIA includes.
    includes = '#include <linux/version.h>\n'
    before = '#include "nv-linux.h"\n'
    if includes not in original:
        if original.count(before) != 1:
            raise RuntimeError('Cabeçalho nv-linux.h não encontrado no local esperado.')
        original = original.replace(before, before + includes, 1)
    patched = original.replace(OLD, NEW, 1)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.callas-nvidia-610-', delete=False) as stream:
            tmp = Path(stream.name)
            stream.write(patched)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp, path.stat().st_mode & 0o777)
        os.replace(tmp, path)
        print('Compatibilidade para a API dmem do Linux 7.3 aplicada à fonte NVIDIA selecionada.')
        return True
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def package_version(name):
    result = subprocess.run(('pacman', '-Q', name), capture_output=True, text=True, check=False)
    if result.returncode or len(result.stdout.strip().split()) != 2:
        raise RuntimeError(f'Pacote {name} ausente: {result.stderr.strip()}')
    return result.stdout.split()[1].rsplit('-', 1)[0]


def inspect_modules(release):
    for name in MODULES:
        version = subprocess.run(('modinfo', '-k', release, '-F', 'version', name),
                                 capture_output=True, text=True, check=False)
        vermagic = subprocess.run(('modinfo', '-k', release, '-F', 'vermagic', name),
                                  capture_output=True, text=True, check=False)
        if version.returncode or version.stdout.strip() != PINNED:
            raise RuntimeError(f'Módulo {name} versão {PINNED} ausente para {release}.')
        if vermagic.returncode or not vermagic.stdout.strip().startswith(release + ' '):
            raise RuntimeError(f'Módulo {name} pertence a outro kernel, não {release}.')


def print_build_logs():
    path = Path('/var/lib/dkms/nvidia') / PINNED
    try:
        candidates = sorted(path.rglob('make.log'), key=lambda p: p.stat().st_mtime, reverse=True)
        for logfile in candidates[:2]:
            if logfile.is_symlink() or not logfile.is_file():
                continue
            print(f'--- Últimas linhas de {logfile} ---', file=sys.stderr)
            for line in logfile.read_text(errors='replace').splitlines()[-50:]:
                print(line, file=sys.stderr)
    except OSError as exc:
        print('Não consegui ler o make.log: ' + str(exc), file=sys.stderr)


def main():
    if os.geteuid() != 0:
        raise RuntimeError('A preparação DKMS exige root no sistema de destino.')
    for pkg in ('nvidia-open-dkms', 'nvidia-utils', 'lib32-nvidia-utils'):
        if package_version(pkg) != PINNED:
            raise RuntimeError(f'{pkg} não corresponde à NVIDIA {PINNED}. Nenhum pacote foi trocado.')
    kernels = versions()
    if any(kernel_family(release) >= (7, 3) for release in kernels.values()):
        patch_73_source()
    for name in ('linux', 'linux-lts'):
        release = kernels[name]
        print(f'>>> Compilando NVIDIA {PINNED} para {name} ({release})', flush=True)
        run('dkms', 'build', '--force', '-m', 'nvidia', '-v', PINNED, '-k', release)
        run('dkms', 'install', '--force', '-m', 'nvidia', '-v', PINNED, '-k', release)
        run('depmod', '-a', release)
        inspect_modules(release)
        print(f'OK: todos os 4 módulos NVIDIA foram verificados para {release}.', flush=True)
    print('OK: NVIDIA '+PINNED+' pronta para gerar initramfs. Nenhum kernel/driver foi alterado.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError) as error:
        print('ERRO NVIDIA DKMS: ' + str(error), file=sys.stderr)
        print_build_logs()
        print('Instalação interrompida antes do initramfs/GRUB; não reinicie ainda.', file=sys.stderr)
        sys.exit(1)
