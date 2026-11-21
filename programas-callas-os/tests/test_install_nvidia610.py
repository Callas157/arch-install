"""Offline tests for pinned NVIDIA 610 kernel preparation (not a DKMS build)."""
import importlib.util
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
INSTALLER = REPO / 'instalar-arch.sh'
HELPER = REPO / 'programas-callas-os/instalador/callas-nvidia-610-prepare.py'
RESCUE = REPO / 'programas-callas-os/instalador/callas-recuperar-nvidia.sh'
spec = importlib.util.spec_from_file_location('nv610', HELPER)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Nvidia610Test(unittest.TestCase):
    def test_patch_only_known_driver_610_source(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'os-interface.c'
            path.write_text('#include "nv-linux.h"\n' + module.OLD + '\n')
            stat_original = Path.stat
            def stat_as_root(target, *args, **kwargs):
                result = stat_original(target, *args, **kwargs)
                if target == path:
                    return SimpleNamespace(st_uid=0, st_mode=result.st_mode)
                return result
            with patch.object(Path, 'stat', stat_as_root):
                self.assertTrue(module.patch_73_source(path))
                self.assertFalse(module.patch_73_source(path))
            self.assertIn('#include <linux/version.h>', path.read_text())
            self.assertIn('dmem_cgroup_register_region(&init, name)', path.read_text())
            self.assertIn('#else\n    void *region = dmem_cgroup_register_region(size, name);', path.read_text())

    def test_unknown_source_is_never_patched(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'os-interface.c'
            path.write_text('#include "nv-linux.h"\nnot NVIDIA source\n')
            stat_original = Path.stat
            def stat_as_root(target, *args, **kwargs):
                result = stat_original(target, *args, **kwargs)
                if target == path:
                    return SimpleNamespace(st_uid=0, st_mode=result.st_mode)
                return result
            with patch.object(Path, 'stat', stat_as_root):
                with self.assertRaisesRegex(RuntimeError, 'diferente do padrão'):
                    module.patch_73_source(path)
            self.assertIn('not NVIDIA source', path.read_text())

    def test_new_kernel_range_is_fail_closed(self):
        self.assertEqual(module.kernel_family('7.3.5-arch1-1'), (7, 3))
        self.assertEqual(module.kernel_family('6.18.1-1-lts'), (6, 18))
        with self.assertRaisesRegex(RuntimeError, 'ainda não validado'):
            module.kernel_family('7.4.0-arch1-1')

    def test_main_installer_validates_before_mkinitcpio(self):
        source = INSTALLER.read_text(encoding='utf-8')
        self.assertIn('CALLAS_NVIDIA_STAGE', source)
        self.assertIn('callas-nvidia-610-prepare.py', source)
        self.assertIn('digest != matches[0]', source)
        self.assertLess(source.index('CALLAS_NVIDIA_STAGE'), source.index('wipefs -af "$DISCO"'))
        self.assertLess(source.index('"$libexec/callas-nvidia-610-prepare"'), source.index('mkinitcpio -P'))
        self.assertEqual(source.count('"$libexec/callas-nvidia-610-prepare"'), 1)
        self.assertIn('610.57.04', source)

    def test_rescue_never_wipes_and_has_strict_mount_guards(self):
        script = RESCUE.read_text(encoding='utf-8')
        for forbidden in ('wipefs -af', 'mkfs.ext4', 'sgdisk --zap-all', 'pacstrap -K'):
            self.assertNotIn(forbidden, script)
        self.assertIn('mountpoint -q /mnt/boot', script)
        self.assertIn('CALLAS_RECOVERY_PREPARE', script)
        self.assertIn('CALLAS_RECOVERY_RESUME', script)
        self.assertIn('arch-chroot /mnt /usr/local/libexec/callas-nvidia-610-prepare', script)
        self.assertIn('arch-chroot /mnt /usr/bin/mkinitcpio -P', script)


if __name__ == '__main__':
    unittest.main()
