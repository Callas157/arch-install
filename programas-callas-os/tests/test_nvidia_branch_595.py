#!/usr/bin/python3
"""Offline tests for the signed-archive NVIDIA branch selector."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

POLICY_PATH = Path(__file__).resolve().parents[1] / 'atualizador/callas-kernel-policy.py'
spec = importlib.util.spec_from_file_location('callas_kernel_policy', POLICY_PATH)
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class NvidiaArchiveTests(unittest.TestCase):
    def setUp(self):
        self.index = {
            'nvidia-open-dkms': {'595.91.07': 'https://archive.archlinux.org/core/595a',
                                 '610.57.04': 'https://archive.archlinux.org/core/610a'},
            'nvidia-utils': {'595.91.07': 'https://archive.archlinux.org/core/595b',
                             '610.57.04': 'https://archive.archlinux.org/core/610b'},
            'lib32-nvidia-utils': {'595.91.07': 'https://archive.archlinux.org/core/595c',
                                   '610.57.04': 'https://archive.archlinux.org/core/610c'},
            'nvidia-settings': {'610.57.04': 'https://archive.archlinux.org/opt/610a'},
            'libxnvctrl': {'610.57.04': 'https://archive.archlinux.org/opt/610b'},
        }
        self.patcher = patch.object(policy, 'archive_index', side_effect=lambda pkg: self.index.get(pkg, {}))
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_optional_packages_do_not_hide_595(self):
        catalog = policy.driver_catalog((*policy.DRIVER, 'nvidia-settings', 'libxnvctrl'))
        self.assertEqual(set(catalog['595.91.07']), set(policy.DRIVER))

    def test_installer_starts_with_exact_nvidia_610_arch_packages(self):
        data = policy.default_driver()
        self.assertEqual(data['version'], '610.57.04')
        self.assertEqual(data['packages'], {name: policy.package_url(name, '610.57.04-1')
                                             for name in (*policy.DRIVER, 'nvidia-settings', 'libxnvctrl')})

    def test_saved_installer_manifest_remains_on_595(self):
        self.assertEqual(policy.legacy_default_driver()['version'], '595.91.07')

    def test_incomplete_core_is_absent_from_switch_catalog(self):
        del self.index['lib32-nvidia-utils']['595.91.07']
        self.assertNotIn('595.91.07', policy.driver_catalog(policy.DRIVER))

    def test_newer_complete_patch_remains_selectable(self):
        for p in policy.DRIVER:
            self.index[p]['595.112.07'] = f'https://archive.archlinux.org/new/{p}'
        self.assertEqual(list(policy.driver_catalog(policy.DRIVER)),
                         ['610.57.04', '595.112.07', '595.91.07'])


if __name__ == '__main__':
    unittest.main()
