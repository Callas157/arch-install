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
