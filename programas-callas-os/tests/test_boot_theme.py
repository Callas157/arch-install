"""Boot entry migration is tested only on temporary copies, never /boot."""
import importlib.util
import ctypes
import subprocess
import tempfile
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT/'programas-callas-os/atualizador/callas-boot-theme.py'

class BootThemeTests(unittest.TestCase):
    def helper(self):
        spec = importlib.util.spec_from_file_location('boot_theme', HELPER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def entries(self):
        installer = (ROOT/'instalar-arch.sh').read_text()
        return installer.split("cat > /etc/grub.d/09_callas <<'GRUB_CALLAS'\n",1)[1].split('\nGRUB_CALLAS',1)[0]+'\n'

    def test_migration_preserves_kernel_arguments_and_is_idempotent(self):
        helper = self.helper()
        original = self.entries()
        result = helper.migrate(original)
        self.assertEqual(result.count(helper.TRANSITION), 3)
        self.assertEqual(helper.migrate(result), result)
        for line in original.splitlines():
            if line.strip().startswith(('linux ', 'initrd ', 'search ')):
                self.assertIn(line, result)
        self.assertNotIn('echo ', result)
        self.assertNotIn('sleep ', result)

    def test_legacy_lts_first_is_migrated_to_main_then_lts(self):
        helper = self.helper()
        original = ('#!/bin/sh\ncat <<\'MENU\'\n'
                    "menuentry 'Callas OS (kernel LTS - recuperação)' {\n linux /vmlinuz-linux-lts\n initrd /initramfs-linux-lts.img\n}\n\n"
                    "menuentry 'Callas OS Linux' {\n linux /vmlinuz-linux\n initrd /initramfs-linux.img\n}\n\n"
                    "menuentry 'Callas OS (diagnóstico sem splash)' {\n linux /vmlinuz-linux\n initrd /initramfs-linux.img\n}\nMENU\n")
        result = helper.migrate(original)
        titles = [line.split("'", 2)[1] for line in result.splitlines() if line.startswith('menuentry ')]
        self.assertEqual(titles, list(helper.TITLES))
        self.assertEqual(helper.migrate(result), result)

    def test_valid_legacy_variants_preserve_all_boot_commands(self):
        helper = self.helper()
        base = self.entries()
        variants = {
            'intel-microcode': base.replace('initrd /initramfs-', 'initrd /intel-ucode.img /initramfs-'),
            'amd-microcode': base.replace('initrd /initramfs-', 'initrd /amd-ucode.img /initramfs-'),
            'initrd-continuation': base.replace('initrd /initramfs-', 'initrd /intel-ucode.img ' + chr(92) + '\n      /initramfs-'),
            'tabs': base.replace('    ', '\t'),
            'two-spaces': base.replace('    ', '  '),
            'boot-path': base.replace('/vmlinuz-', '/boot/vmlinuz-').replace('/initramfs-', '/boot/initramfs-'),
            'efi-commands': base.replace('    linux ', '    linuxefi ').replace('    initrd ', '    initrdefi '),
            'quoted-paths': base.replace('linux /vmlinuz-linux ', 'linux "/vmlinuz-linux" ').replace('initrd /initramfs-linux.img', 'initrd "/initramfs-linux.img"'),
            'fallback-images': base.replace('/initramfs-linux.img', '/initramfs-linux-fallback.img').replace('/initramfs-linux-lts.img', '/initramfs-linux-lts-fallback.img'),
            'indented-entry': '\n'.join('  '+line if line else line for line in base.split('\n')),
            'trailing-comments': base.replace('initrd /initramfs-linux.img', 'initrd /initramfs-linux.img # initial image'),
        }
        for name, original in variants.items():
            with self.subTest(name=name):
                result = helper.migrate(original)
                self.assertEqual(result.count('source $prefix/themes/callas/loading.cfg'), 3)
                self.assertEqual(helper.migrate(result), result)
                for line in original.splitlines():
                    if line.lstrip().startswith(('linux', 'initrd', 'search ')):
                        self.assertIn(line, result)

    def test_mismatched_kernel_and_initramfs_still_rejected(self):
        helper = self.helper()
        with self.assertRaises(ValueError):
            helper.migrate(self.entries().replace('initrd /initramfs-linux-lts.img', 'initrd /initramfs-linux.img'))

    def test_check_mode_does_not_change_legacy_entries_or_permissions(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'09_callas'; original = self.entries().replace('initrd /initramfs-', 'initrd /intel-ucode.img /initramfs-')
            path.write_text(original); path.chmod(0o755)
            result = subprocess.run([sys.executable,str(HELPER),'--entries',str(path),'--check'],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout.strip(),'changed')
            self.assertEqual(path.read_text(),original); self.assertEqual(path.stat().st_mode & 0o777,0o755)

    def test_cli_preserves_crlf_boot_commands(self):
        original=self.entries().replace('\n','\r\n').encode()
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'09_callas';path.write_bytes(original)
            result=subprocess.run([sys.executable,str(HELPER),'--entries',str(path)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            after=path.read_bytes()
            for line in original.splitlines(keepends=True):
                if line.strip().startswith((b'linux ',b'initrd ',b'search ')):self.assertIn(line,after)

    def test_unknown_or_incomplete_layout_is_rejected(self):
        helper = self.helper()
        with self.assertRaises(ValueError):
            helper.migrate(self.entries().replace('Callas OS Linux', 'My own Linux'))
        with self.assertRaises(ValueError):
            helper.migrate(self.entries().replace('    initrd /initramfs-linux-lts.img', ''))

    def test_cli_preserves_mode_and_invalid_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'09_callas'
            path.write_text(self.entries())
            path.chmod(0o755)
            command = [sys.executable, str(HELPER), '--entries', str(path)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), 'changed')
            self.assertEqual(path.stat().st_mode & 0o777, 0o755)
            before = path.read_bytes()
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.stdout.strip(), 'unchanged')
            self.assertEqual(path.read_bytes(), before)
            path.write_text('unknown layout')
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(path.read_text(), 'unknown layout')

    def test_plymouth_script_is_accepted_by_native_parser(self):
        plugin = Path('/usr/lib/plymouth/script.so')
        if not plugin.exists():
            self.skipTest('Plymouth native parser unavailable')
        library = ctypes.CDLL(str(plugin))
        library.script_parse_file.argtypes = [ctypes.c_char_p]
        library.script_parse_file.restype = ctypes.c_void_p
        library.script_parse_op_free.argtypes = [ctypes.c_void_p]
        script = ROOT/'assets/plymouth/callas/callas.script'
        parsed = library.script_parse_file(str(script).encode())
        self.assertTrue(parsed, 'Native Plymouth parser rejected theme')
        library.script_parse_op_free(parsed)

    def test_custom_entries_remain_unchanged(self):
        helper = self.helper()
        custom = "\nmenuentry 'Personal' {\n linux /other\n}\n"
        self.assertTrue(helper.migrate(self.entries()+custom).endswith(custom))

if __name__ == '__main__':
    unittest.main()
