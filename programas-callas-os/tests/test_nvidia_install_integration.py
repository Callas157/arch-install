#!/usr/bin/env python3
"""Offline regression gates: no real package, kernel or disk operations."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / 'instalar-arch.sh'
PREPARE = ROOT / 'programas-callas-os/instalador/callas-nvidia-prepare.py'
POLICY = ROOT / 'programas-callas-os/atualizador/callas-kernel-policy.py'
RELEASE = ROOT / 'programas-callas-os/atualizador/callas-release.py'


class NvidiaInstallationIntegration(unittest.TestCase):
    def test_helper_python_syntax(self):
        for source in (PREPARE, POLICY, RELEASE):
            ast.parse(source.read_text(), filename=str(source))

    def test_clean_install_stages_signed_preparer_before_disk_operations(self):
        script = INSTALLER.read_text()
        self.assertIn('callas-nvidia-default.json', script)
        self.assertIn('pacman-key --verify "$arquivo.sig" "$arquivo"', script)
        self.assertLess(script.index('--nvidia-check-hardware'), script.index('wipefs -af "$DISCO"'))
        self.assertIn('programas-callas-os/instalador/callas-nvidia-prepare.py', RELEASE.read_text())

    def test_clean_install_uses_archived_primary_pair_and_lts_from_repo(self):
        script = INSTALLER.read_text()
        base = script.split('pacstrap -K /mnt ', 1)[1].split('\ngenfstab', 1)[0].split()
        self.assertIn('linux-lts', base)
        self.assertIn('linux-lts-headers', base)
        self.assertNotIn('linux', base)
        self.assertNotIn('linux-headers', base)
        self.assertLess(script.index('for pacote in linux linux-headers; do'), script.index('wipefs -af "$DISCO"'))
        self.assertIn('linux-headers-$kernel_version-x86_64.pkg.tar.zst', script)
        self.assertIn('LocalFileSigLevel = Required', script)
        config = script.split("<<'CALLAS_CHROOT'", 1)[1]
        self.assertNotIn('pacman -Syu', config)
        self.assertNotIn('IgnorePkg', config)
        self.assertLess(config.index("menuentry 'Callas OS (kernel LTS"), config.index("menuentry 'Callas OS Linux'"))

    def test_clean_install_patches_before_dkms_then_verifies_both_kernels(self):
        script = INSTALLER.read_text()
        chroot = script.split("cat > /mnt/usr/local/share/callas-os/install-config.sh <<'CALLAS_CHROOT'", 1)[1]
        self.assertIn("30-callas-nvidia-initial-compat.hook", chroot)
        self.assertIn('When = PostTransaction', chroot)
        self.assertIn('Exec = /usr/local/libexec/callas-nvidia-prepare --compat-installed', chroot)
        local_install = 'pacman --config /var/tmp/callas-install-pacman.conf -U --noconfirm'
        self.assertLess(chroot.index('printf \'%s\\n\' "$nvidia_version"'), chroot.index(local_install))
        self.assertLess(chroot.index(local_install),
                        chroot.index('"$libexec/callas-nvidia-prepare"'))
        self.assertLess(chroot.index('"$libexec/callas-nvidia-prepare"'),
                        chroot.index('mkinitcpio -P'))
        self.assertLess(chroot.index('mkinitcpio -P'),
                        chroot.index('bash "$CALLAS_RELEASE_DIR/callas-security.sh"'))
        self.assertIn('linux-lts', chroot)
        self.assertIn('nvidia-open-dkms nvidia-utils lib32-nvidia-utils', chroot)

    def test_manual_switch_has_validation_and_pre_dkms_hook(self):
        policy = POLICY.read_text()
        self.assertIn('30-callas-nvidia-compat.hook', policy)
        self.assertIn('--compat-installed', policy)
        self.assertIn('driver_preflight(targets, os.environ[\'CALLAS_NVIDIA_TARGET\']', policy)
        self.assertIn('verify_modules(tree, release, version)', policy)
        self.assertIn("subprocess.run([KERNEL_CHECK, '--verify-only']", policy)
        self.assertIn('A troca falhou. Restaurando a versão NVIDIA anterior.', policy)

    def test_595_compatibility_includes_known_linux_7_2_breakages(self):
        source = PREPARE.read_text()
        for item in ('NV_DRM_CRTC_ATOMIC_CHECK_HAS_ATOMIC_STATE_ARG',
                     'NV_DRM_PLANE_ATOMIC_CHECK_HAS_ATOMIC_STATE_ARG',
                     'strscpy(chunk_split_cache',
                     'strscpy(buf, current->comm, len)',
                     'Callas OS strncpy compatibility',
                     'kernel-open/nvidia-drm/nvidia-drm-conftest.h'):
            self.assertIn(item, source)


if __name__ == '__main__':
    unittest.main()
