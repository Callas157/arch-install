"""Targeted option-5 installs must never upgrade the base or hide boot failures."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

UP = Path(__file__).resolve().parents[1] / 'atualizador'
spec = importlib.util.spec_from_file_location('targeted_native', UP / 'callas-native.py')
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)
REAL_RUN = subprocess.run


class TargetedInstallTests(unittest.TestCase):
    def transaction(self, dependency='libhandy', result=0):
        seen = []
        def pacman(argv, **kwargs):
            self.assertEqual(argv[0], '/usr/bin/pacman')
            self.assertIn('-S', argv)
            self.assertNotIn('-Syu', argv)
            self.assertNotIn('-Sy', argv)
            self.assertEqual(argv[-1], 'gnome-boxes')
            hooks = Path(argv[argv.index('--hookdir', argv.index('--hookdir') + 1) + 1])
            hook = next(hooks.glob('*.hook')).read_text()
            self.assertIn('AbortOnFail', hook)
            self.assertIn('NeedsTargets', hook)
            guard = hook.split('Exec = /usr/bin/python3 ', 1)[1].strip()
            check = REAL_RUN(['python', guard], input='gnome-boxes\n' + dependency + '\n',
                             text=True, capture_output=True)
            if check.returncode:
                return types.SimpleNamespace(returncode=1)
            seen.append('installed')
            return types.SimpleNamespace(returncode=result)
        with patch.object(native.subprocess, 'run', side_effect=pacman):
            code = native.install_packages(['gnome-boxes'])
        return code, seen

    def test_targeted_install_allows_app_dependencies_without_system_upgrade(self):
        code, seen = self.transaction()
        self.assertEqual(code, 0)
        self.assertEqual(seen, ['installed'])

    def test_base_dependency_aborts_before_any_package_is_installed(self):
        for dependency in ('linux', 'linux-lts', 'nvidia-open-dkms', 'glibc', 'systemd', 'dbus'):
            with self.subTest(dependency=dependency):
                code, seen = self.transaction(dependency)
                self.assertNotEqual(code, 0)
                self.assertEqual(seen, [])

    def test_package_manager_failure_is_propagated(self):
        self.assertNotEqual(self.transaction(result=1)[0], 0)

    def test_invalid_or_base_targets_are_rejected_without_running_pacman(self):
        for packages in ([], ['--root'], ['../app'], ['linux'], ['gnome-boxes', 'glibc']):
            with self.subTest(packages=packages), patch.object(native.subprocess, 'run') as run:
                with self.assertRaises(ValueError):
                    native.install_packages(packages)
                run.assert_not_called()


class CompletionGateTests(unittest.TestCase):
    def test_boot_failure_never_reaches_release_completion(self):
        source = (UP / 'callas-config-update.sh').read_text()
        gate = source.partition('# BEGIN completion boot gate\n')[2].partition('# END completion boot gate')[0]
        for failed in (False, True):
            with self.subTest(failed=failed), tempfile.TemporaryDirectory() as temp:
                log = Path(temp) / 'complete'
                code = '''set -euo pipefail
erro() { echo "$*" >&2; exit 1; }
kernel_fixture() { [[ $BOOT_FAILED == 0 ]]; }
''' + gate.replace('/usr/local/libexec/callas-kernel-check', 'kernel_fixture')
                code += '\nprintf complete > "$COMPLETE_FILE"\n'
                result = REAL_RUN(['bash', '-c', code], capture_output=True, text=True,
                                  env=dict(os.environ, BOOT_FAILED=str(int(failed)), COMPLETE_FILE=str(log)))
                self.assertEqual(result.returncode == 0, not failed, result.stderr)
                self.assertEqual(log.exists(), not failed)

    def test_failed_export_preserves_temporary_log_and_reports_failure(self):
        source = (UP / 'callas-config-update.sh').read_text()
        function = 'finalizar() {' + source.split('finalizar() {', 1)[1].split('\ntrap finalizar EXIT', 1)[0]
        for failed in (False, True):
            with self.subTest(failed=failed), tempfile.TemporaryDirectory() as temp:
                root=Path(temp)
                stage=root/'capture'; stage.mkdir()
                log=stage/'update.log'; log.write_text('transaction output\n')
                logger=root/'logger'
                logger.write_text('#!/bin/bash\n[[ $LOG_FAILED == 0 ]]\n')
                logger.chmod(0o755)
                code='''set +e
exec 3>&1 4>&2
aviso() { echo "$*" >&2; }
true &
logpid=$!
'''+function.replace('/usr/local/libexec/callas-logs', str(logger))+'\ntrue\nfinalizar\n'
                result=REAL_RUN(['bash','-c',code],capture_output=True,text=True,
                                env=dict(os.environ,logstage=str(stage),usuario='fixture',LOG_FAILED=str(int(failed))))
                self.assertEqual(result.returncode==0,not failed,result.stderr)
                self.assertEqual(log.exists(),failed)
                if failed:
                    self.assertIn(str(stage),result.stderr)
                    self.assertEqual(log.read_text(),'transaction output\n')


if __name__ == '__main__':
    unittest.main()
