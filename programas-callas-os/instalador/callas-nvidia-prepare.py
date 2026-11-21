#!/usr/bin/python3
"""Prepare the selected NVIDIA branch for installed Arch kernels; never change packages.

Clean-install and live repair helper. Preserves matching modules; fails closed on DKMS errors.
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
PINNED = os.environ.get('CALLAS_NVIDIA_REPAIR_TARGET') or VERSION_FILE.read_text().strip()
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


# Linux 7.2 renamed drm_atomic_state to drm_atomic_commit. The Deepin 25
# RTX 3060/595.71.05 report used unconditional renames; these aliases instead
# apply only to new kernels so the same DKMS source still builds for linux-lts.
DRM_COMPAT = """/* Callas OS NVIDIA 595.71.05: DRM atomic API on Linux >= 7.2. */
#if !defined(NV_BSD)
#include <linux/version.h>
#if LINUX_VERSION_CODE >= KERNEL_VERSION(7, 2, 0)
#define drm_atomic_state drm_atomic_commit
#define drm_atomic_state_alloc drm_atomic_commit_alloc
#define drm_atomic_state_clear drm_atomic_commit_clear
#define drm_atomic_state_default_clear drm_atomic_commit_default_clear
#define drm_atomic_state_default_release drm_atomic_commit_default_release
#define drm_atomic_state_free drm_atomic_commit_put
#define drm_atomic_state_get drm_atomic_commit_get
#define drm_atomic_state_init drm_atomic_commit_init
#define drm_atomic_state_put drm_atomic_commit_put
/* Old conftests silently choose pre-7.2 callback signatures otherwise. */
#ifndef NV_DRM_ATOMIC_STATE_REF_COUNTING_PRESENT
#define NV_DRM_ATOMIC_STATE_REF_COUNTING_PRESENT
#endif
#ifndef NV_DRM_CRTC_ATOMIC_CHECK_HAS_ATOMIC_STATE_ARG
#define NV_DRM_CRTC_ATOMIC_CHECK_HAS_ATOMIC_STATE_ARG
#endif
#ifndef NV_DRM_PLANE_ATOMIC_CHECK_HAS_ATOMIC_STATE_ARG
#define NV_DRM_PLANE_ATOMIC_CHECK_HAS_ATOMIC_STATE_ARG
#endif
#ifndef NV_DRM_ATOMIC_HELPER_SWAP_STATE_HAS_STALL_ARG
#define NV_DRM_ATOMIC_HELPER_SWAP_STATE_HAS_STALL_ARG
#endif
#ifndef NV_DRM_ATOMIC_HELPER_SWAP_STATE_RETURN_INT
#define NV_DRM_ATOMIC_HELPER_SWAP_STATE_RETURN_INT
#endif
#endif
#endif
"""
DRM_PROBE = """#include <linux/version.h>
#if LINUX_VERSION_CODE >= KERNEL_VERSION(7, 2, 0)
#define drm_atomic_state drm_atomic_commit
#endif
"""
STRNCPY_WRAPPER = """/* Preserve strncpy's zero-padding on kernels without strncpy(). */
static char *callas_595_strncpy(char *dest, const char *src, size_t length)
{
    size_t i;
    for (i = 0; i < length && src[i] != '\\0'; ++i)
        dest[i] = src[i];
    for (; i < length; ++i)
        dest[i] = '\\0';
    return dest;
}

"""


def patch_595_atomic_tree(source):
    """Idempotent, signature-checked patch for NVIDIA 595.71.05 sources only.

    Source-level version gates make linux-lts (6.x) continue to use its old
    API; no kernel, pacman or DKMS state is modified by this function.
    """
    if PINNED != '595.71.05':
        return False
    if source.is_symlink() or not source.is_dir() or source.stat().st_uid != os.geteuid():
        raise RuntimeError('Fonte NVIDIA insegura/ausente: ' + str(source))
    # Arch packages the upstream tree below /usr/src/nvidia-VERSION/kernel-open,
    # whereas the Deepin source example can expose its files at the root.
    # Match only known layouts; never patch an unrelated directory.
    if (source / 'kernel-open/nvidia-drm/nvidia-drm-conftest.h').is_file():
        tree = source / 'kernel-open'
    elif (source / 'nvidia-drm/nvidia-drm-conftest.h').is_file():
        tree = source
    else:
        raise RuntimeError('Árvore NVIDIA 595 desconhecida: esperado kernel-open/nvidia-drm ou nvidia-drm.')
    if tree.is_symlink() or tree.stat().st_uid != os.geteuid():
        raise RuntimeError('Árvore NVIDIA insegura: ' + str(tree))
    header = tree / 'nvidia-drm/nvidia-drm-conftest.h'
    probe = tree / 'conftest.sh'
    nvswitch = tree / 'nvidia/linux_nvswitch.c'
    modeset = tree / 'nvidia-modeset/nvidia-modeset-linux.c'
    uvm = tree / 'nvidia-uvm/uvm_pmm_gpu.c'
    interface = tree / 'nvidia/os-interface.c'
    planned = {}
    for path in (header, probe, nvswitch, modeset, uvm, interface):
        if path.is_symlink() or not path.is_file() or path.stat().st_uid != os.geteuid():
            raise RuntimeError('Arquivo NVIDIA 595 esperado não existe ou é inseguro: ' + str(path))
        content = path.read_text(encoding='utf-8')
        result = content
        if path == header:
            anchor = '#include "nvtypes.h"\n'
            if '/* Callas OS NVIDIA 595.71.05:' not in content:
                if content.count(anchor) != 1:
                    raise RuntimeError('Cabeçalho NVIDIA DRM desconhecido: ' + str(path))
                result = content.replace(anchor, anchor + '\n' + DRM_COMPAT, 1)
        elif path == probe:
            anchor = '#include <drm/drm_modeset_helper_vtables.h>\n'
            if DRM_PROBE not in content:
                if content.count(anchor) != 2:
                    raise RuntimeError('Detecção DRM NVIDIA 595 desconhecida; não aplicarei substituição indiscriminada.')
                result = content.replace(anchor, anchor + DRM_PROBE, 2)
        elif path == nvswitch:
            if 'static char *callas_595_strncpy' not in content:
                a = 'strncpy(regkey_val, regkey_val_start, regkey_val_len);'
                b = 'return strncpy(dest, src, length);'
                anchor = '#define CREATE_TRACE_POINTS\n'
                if content.count(a) != 1 or content.count(b) != 1 or content.count(anchor) != 1:
                    raise RuntimeError('Fonte NVSwitch NVIDIA 595 desconhecida.')
                result = content.replace(a, 'callas_595_strncpy(regkey_val, regkey_val_start, regkey_val_len);')
                result = result.replace(b, 'return callas_595_strncpy(dest, src, length);')
                result = result.replace(anchor, STRNCPY_WRAPPER + anchor, 1)
        elif path == modeset:
            old = 'return strncpy(dest, src, n);'
            marker = '/* Callas OS strncpy compatibility */'
            if marker not in content:
                if content.count(old) != 1:
                    raise RuntimeError('Fonte NVIDIA modeset sem assinatura strncpy reconhecida.')
                replacement = (marker + "\n"
                               "size_t i;\n"
                               "for (i = 0; i < n && src[i] != '\\0'; ++i) dest[i] = src[i];\n"
                               "for (; i < n; ++i) dest[i] = '\\0';\n"
                               "return dest;")
                result = content.replace(old, replacement, 1)
        elif path == uvm:
            old = 'strncpy(chunk_split_cache[level].name, "uvm_gpu_chunk_t", sizeof(chunk_split_cache[level].name) - 1);'
            new = 'strscpy(chunk_split_cache[level].name, "uvm_gpu_chunk_t", sizeof(chunk_split_cache[level].name));'
            if new not in content:
                if content.count(old) != 1:
                    raise RuntimeError('Fonte NVIDIA UVM sem assinatura strncpy reconhecida.')
                result = content.replace(old, new, 1)
        elif path == interface:
            old = "strncpy(buf, current->comm, len - 1);"
            new = "strscpy(buf, current->comm, len);"
            if new not in content:
                if content.count(old) != 1:
                    raise RuntimeError('Fonte NVIDIA OS interface sem assinatura strncpy reconhecida.')
                result = content.replace(old, new, 1)
        if result != content:
            planned[path] = result
    # Validate every expected input before changing any file. On write failure
    # restore from in-memory originals (best effort) and abort compilation.
    originals = {path: path.read_text(encoding='utf-8') for path in planned}
    written = []
    try:
        for path, updated in planned.items():
            with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent,
                                             prefix='.callas-595-', delete=False) as stream:
                temporary = Path(stream.name)
                try:
                    stream.write(updated)
                    stream.flush()
                    os.fsync(stream.fileno())
                    os.chmod(temporary, path.stat().st_mode & 0o777)
                    os.replace(temporary, path)
                    written.append(path)
                finally:
                    temporary.unlink(missing_ok=True)
    except OSError:
        for path in written:
            path.write_text(originals[path], encoding='utf-8')
        raise
    if planned:
        print('Compatibilidade NVIDIA 595.71.05 Linux 7.2+: DRM/conftest e chamadas strncpy corrigidas; LTS preservado.', flush=True)
    return bool(planned)


def prepare_compat_tree(source, release):
    if not re.fullmatch(r'\d+\.\d+\.\d+[-_a-zA-Z0-9.]*', release):
        raise RuntimeError('Release do kernel inválido.')
    if kernel_family(release) >= (7, 2):
        patch_595_atomic_tree(source)
    if kernel_family(release) >= (7, 3):
        patch_73_source(source / 'kernel-open/nvidia/os-interface.c' if
                        (source / 'kernel-open/nvidia/os-interface.c').is_file()
                        else source / 'nvidia/os-interface.c')


def prepare_installed_source():
    """Pacman PostTransaction pre-DKMS: patch only the newly installed source."""
    if os.geteuid() != 0:
        raise RuntimeError('Compatibilidade NVIDIA exige root.')
    if PINNED != '595.71.05':
        return
    releases = versions()
    newer = [value for value in releases.values() if kernel_family(value) >= (7, 2)]
    if not newer:
        return
    prepare_compat_tree(Path('/usr/src') / ('nvidia-' + PINNED),
                        max(newer, key=lambda name: kernel_family(name)))


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
                                         prefix='.callas-nvidia-', delete=False) as stream:
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
    patched = False
    for name in ('linux', 'linux-lts'):
        release = kernels[name]
        try:
            inspect_modules(release)
        except RuntimeError:
            if not patched and kernel_family(release) >= (7, 2):
                main_source = Path('/usr/src') / ('nvidia-' + PINNED)
                prepare_compat_tree(main_source, release)
                # Some DKMS installations retain physical (non-symlink) copies
                # of source/build. Mirror only recognizable trees, never touch
                # other NVIDIA versions or remove the working LTS modules.
                dkms_dir = Path('/var/lib/dkms/nvidia') / PINNED
                for name_copy in ('source', 'build'):
                    copy = dkms_dir / name_copy
                    resolved = copy.resolve() if copy.is_symlink() else copy
                    if resolved == main_source.resolve():
                        continue
                    if copy.is_symlink() and not resolved.is_relative_to(dkms_dir.resolve()):
                        raise RuntimeError('Link DKMS NVIDIA fora do diretório esperado: ' + str(copy))
                    if resolved.is_dir() and (
                        (resolved / 'kernel-open/nvidia-drm/nvidia-drm-conftest.h').is_file()
                        or (resolved / 'nvidia-drm/nvidia-drm-conftest.h').is_file()
                    ):
                        prepare_compat_tree(resolved, release)
                patched = True
            print(f'>>> Reparando NVIDIA {PINNED} para {name} ({release})', flush=True)
            run('dkms', 'build', '--force', '-m', 'nvidia', '-v', PINNED, '-k', release)
            run('dkms', 'install', '--force', '-m', 'nvidia', '-v', PINNED, '-k', release)
            run('depmod', '-a', release)
            inspect_modules(release)
        else:
            print(f'NVIDIA {PINNED} já válida para {name} ({release}); preservada.', flush=True)
        print(f'OK: todos os 4 módulos NVIDIA foram verificados para {release}.', flush=True)
    print('OK: NVIDIA '+PINNED+' pronta para gerar initramfs. Nenhum kernel/driver foi alterado.')


if __name__ == '__main__':
    try:
        if sys.argv[1:] == ['--compat-installed']:
            prepare_installed_source()
        elif len(sys.argv) == 4 and sys.argv[1] == '--compat-tree':
            if os.geteuid() != 0:
                raise RuntimeError('Preparação de fonte NVIDIA exige root.')
            prepare_compat_tree(Path(sys.argv[2]), sys.argv[3])
        elif len(sys.argv) == 1:
            main()
        else:
            raise RuntimeError('Argumentos inválidos para o preparador NVIDIA.')
    except (OSError, RuntimeError) as error:
        print('ERRO NVIDIA DKMS: ' + str(error), file=sys.stderr)
        print_build_logs()
        print('Instalação interrompida antes do initramfs/GRUB; não reinicie ainda.', file=sys.stderr)
        sys.exit(1)
