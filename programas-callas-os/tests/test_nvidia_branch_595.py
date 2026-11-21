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


class NvidiaBranch595Tests(unittest.TestCase):
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
        data = policy.default_driver()
        self.assertEqual(data['version'], '595.91.07')
        self.assertEqual(set(data['packages']), set(policy.DRIVER))

    def test_matching_optional_pair_is_installed(self):
        self.index['nvidia-settings']['595.91.07'] = 'https://archive.archlinux.org/opt/595a'
        self.index['libxnvctrl']['595.91.07'] = 'https://archive.archlinux.org/opt/595b'
        data = policy.default_driver()
        self.assertEqual(set(data['packages']), set(policy.DRIVER) | {'nvidia-settings', 'libxnvctrl'})

    def test_incomplete_core_rejects_default(self):
        del self.index['lib32-nvidia-utils']['595.91.07']
        with self.assertRaisesRegex(RuntimeError, 'pilha NVIDIA Open DKMS 595'):
            policy.default_driver()

    def test_newest_complete_patch_within_595(self):
        for p in policy.DRIVER:
            self.index[p]['595.112.07'] = f'https://archive.archlinux.org/new/{p}'
        data = policy.default_driver()
        self.assertEqual(data['version'], '595.112.07')


if __name__ == '__main__':
    unittest.main()
