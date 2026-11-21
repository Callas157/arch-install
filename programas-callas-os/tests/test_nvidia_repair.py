"""Offline tests: no hardware, pacman writes, DKMS or boot operations."""
import importlib.util
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "atualizador/callas-kernel-policy.py"
PREPARE = ROOT / "instalador/callas-nvidia-prepare.py"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = load(POLICY, "repair_policy")

    def test_detects_missing_primary_modules(self):
        mod = self.policy
        output = mock.Mock(returncode=0, stdout="595.71.05\n")
        missing = mock.Mock(returncode=1, stdout="")
        with mock.patch.object(mod, "installed_release_map", return_value={
                "linux": "7.3.5-arch1-1", "linux-lts": "6.18.64-1-lts"}), \
             mock.patch.object(mod.subprocess, "run", side_effect=[
                 missing, output]):
            self.assertFalse(mod.modules_coherent("595.71.05"))

    def test_rejects_automatic_change_from_610_to_595(self):
        mod = self.policy
        with TemporaryDirectory() as tmp:
            marker = Path(tmp) / "pinned"
            marker.write_text("610.57.04\n")
            lock = Path(tmp) / "lock"
            with mock.patch.object(mod, "VERSION_FILE", marker), \
                 mock.patch.object(mod, "DRIVER_LOCK", lock), \
                 mock.patch.object(mod, "check_hooks"), \
                 mock.patch.object(mod, "command"), \
                 mock.patch.object(mod, "installed_driver", return_value={
                     "nvidia-open-dkms": "595.71.05-2",
                     "nvidia-utils": "595.71.05-2",
                     "lib32-nvidia-utils": "595.71.05-1"}), \
                 mock.patch.object(mod, "modules_coherent") as check:
                with self.assertRaisesRegex(RuntimeError, "confirm"):
                    mod.repair_driver()
                check.assert_not_called()
                self.assertEqual(marker.read_text(), "610.57.04\n")

    def test_rejects_mixed_installed_packages_even_with_consent(self):
        mod = self.policy
        with TemporaryDirectory() as tmp:
            with mock.patch.object(mod, "DRIVER_LOCK", Path(tmp)/"lock"), \
                 mock.patch.object(mod, "check_hooks"), \
                 mock.patch.object(mod, "command"), \
                 mock.patch.object(mod, "installed_driver", return_value={
                     "nvidia-open-dkms": "595.71.05-2",
                     "nvidia-utils": "610.57.04-1",
                     "lib32-nvidia-utils": "595.71.05-1"}):
                with self.assertRaisesRegex(RuntimeError, "versões diferentes"):
                    mod.repair_driver(adopt_installed=True, expected="595.71.05")


class PrepareTests(unittest.TestCase):
    def test_preserves_valid_lts_and_builds_only_missing_kernel(self):
        with mock.patch.dict(os.environ, {"CALLAS_NVIDIA_REPAIR_TARGET": "595.71.05"}):
            mod = load(PREPARE, "repair_prepare")
        checked = []
        commands = []

        def inspect(release):
            checked.append(release)
            if release == "7.3.5-arch1-1" and checked.count(release) == 1:
                raise RuntimeError("missing module")
        def run(*args):
            commands.append(args)

        with mock.patch.object(mod.os, "geteuid", return_value=0), \
             mock.patch.object(mod, "package_version", return_value="595.71.05"), \
             mock.patch.object(mod, "versions", return_value={
                 "linux": "7.3.5-arch1-1", "linux-lts": "6.18.64-1-lts"}), \
             mock.patch.object(mod, "inspect_modules", side_effect=inspect), \
             mock.patch.object(mod, "patch_73_source"), \
             mock.patch.object(mod, "run", side_effect=run):
            mod.main()
        self.assertEqual(checked.count("6.18.64-1-lts"), 1)
        self.assertTrue(any("7.3.5-arch1-1" in step for step in commands))
        self.assertFalse(any("6.18.64-1-lts" in step for step in commands))


    def test_patch_595_drm_is_conditional_and_idempotent(self):
        with mock.patch.dict(os.environ, {"CALLAS_NVIDIA_REPAIR_TARGET": "595.71.05"}):
            mod = load(PREPARE, "compat_595")
        with TemporaryDirectory() as tmp:
            source = Path(tmp)
            drm = source / "nvidia-drm"
            drm.mkdir()
            nv = source / "nvidia"
            nv.mkdir()
            (drm / "nvidia-drm-conftest.h").write_text('#include "nvtypes.h"\n')
            (source / "conftest.sh").write_text(
                ('#include <drm/drm_modeset_helper_vtables.h>\n'
                 'struct drm_atomic_state *state;\n') * 2)
            (nv / "linux_nvswitch.c").write_text(
                "#define CREATE_TRACE_POINTS\n"
                "strncpy(regkey_val, regkey_val_start, regkey_val_len);\n"
                "return strncpy(dest, src, length);\n")
            self.assertTrue(mod.patch_595_atomic_tree(source))
            header = (drm / "nvidia-drm-conftest.h").read_text()
            conftest = (source / "conftest.sh").read_text()
            nvswitch = (nv / "linux_nvswitch.c").read_text()
            self.assertIn('#if LINUX_VERSION_CODE >= KERNEL_VERSION(7, 2, 0)', header)
            self.assertIn('#define drm_atomic_state drm_atomic_commit', header)
            self.assertEqual(conftest.count('#define drm_atomic_state drm_atomic_commit'), 2)
            self.assertIn('callas_595_strncpy', nvswitch)
            self.assertFalse(mod.patch_595_atomic_tree(source))
            self.assertEqual(header, (drm / "nvidia-drm-conftest.h").read_text())

    def test_patch_rejects_unknown_595_source_without_partial_writes(self):
        with mock.patch.dict(os.environ, {"CALLAS_NVIDIA_REPAIR_TARGET": "595.71.05"}):
            mod = load(PREPARE, "compat_unknown")
        with TemporaryDirectory() as tmp:
            source = Path(tmp)
            drm = source / "nvidia-drm"
            drm.mkdir()
            nv = source / "nvidia"
            nv.mkdir()
            header = drm / "nvidia-drm-conftest.h"
            header.write_text('#include "nvtypes.h"\n')
            (source / "conftest.sh").write_text("incompatible conftest")
            (nv / "linux_nvswitch.c").write_text("#define CREATE_TRACE_POINTS\n")
            with self.assertRaisesRegex(RuntimeError, "Detecção DRM"):
                mod.patch_595_atomic_tree(source)
            self.assertEqual(header.read_text(), '#include "nvtypes.h"\n')



if __name__ == "__main__":
    unittest.main()
