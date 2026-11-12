"""Offline installer regressions; never partition disks or install packages."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('aur_install', ROOT / 'programas-callas-os/atualizador/callas-aur.py')
aur = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aur)

class InstallerTests(unittest.TestCase):
    def test_distinct_passwords_and_retry_preserve_special_characters(self):
        text = (ROOT / 'instalar-arch.sh').read_text()
        fragment = text[text.index('for conta in usuario root; do'):text.index('\n# Full installation output')]
        result = subprocess.run(['bash', '-c', fragment + '\nprintf "%s\\n%s\\n" "$SENHA" "$SENHA_ROOT"'],
                                input='wrong\nmismatch\nu $`\\!\nu $`\\!\nr :$`\\!\nr :$`\\!\n',
                                capture_output=True, text=True, check=True)
        self.assertTrue(result.stdout.endswith('u $`\\!\nr :$`\\!\n'))
        self.assertNotIn('u $', result.stderr)
        self.assertNotIn('r :', result.stderr)

    def test_build_in_chroot_has_no_root_sudo_or_systemd(self):
        builder = object.__new__(aur.InstallationBuilder)
        builder.work = Path('/temporary/work')
        builder.env = {'HOME': '/temporary/work/home', 'PATH': '/usr/bin:/bin'}
        with patch.object(aur.pwd, 'getpwnam', return_value=SimpleNamespace(pw_uid=987, pw_gid=987)), \
             patch.object(aur, 'command') as command:
            builder.run(['/usr/bin/makepkg', '--noconfirm'])
        invocation = command.call_args.args[0]
        self.assertEqual(invocation[0], '/usr/bin/setpriv')
        self.assertIn('--no-new-privs', invocation)
        self.assertIn('--reuid=987', invocation)
        self.assertIn('--clear-groups', invocation)
        self.assertNotIn('sudo', ' '.join(invocation))
        self.assertNotIn('systemd-run', ' '.join(invocation))

    def test_failed_build_never_installs_artifacts(self):
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(aur, 'BUILDS_ROOT', Path(temp)), \
             patch.object(aur.pwd, 'getpwnam'), \
             patch.object(aur, 'InstallationBuilder') as builder, \
             patch.object(aur, 'command') as command:
            builder.return_value.run.return_value.stdout = 'AUR TARGET brave-bin brave-bin\n'
            builder.return_value.build.side_effect = RuntimeError('checksum failure')
            with self.assertRaisesRegex(RuntimeError, 'checksum'):
                aur.run_install(['brave-bin'])
            command.assert_not_called()

    def test_installation_refuses_pinned_driver(self):
        with self.assertRaises(ValueError):
            aur.run_install(['nvidia-utils'])

    def test_chroot_reports_actual_command_and_failure_code(self):
        text = (ROOT / 'instalar-arch.sh').read_text()
        block = text.split("<<'CALLAS_CHROOT'\n", 1)[1].split('\nusuario=$1', 1)[0]
        result = subprocess.run(['bash', '-c', block + '\nfalse\nprintf unreachable'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('comando: false', result.stderr)
        self.assertNotIn('unreachable', result.stdout)

if __name__ == '__main__':
    unittest.main()
