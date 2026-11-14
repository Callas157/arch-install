"""No general upgrade or scheduler activation from application/configuration work."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
UP = ROOT / 'atualizador'
spec = importlib.util.spec_from_file_location('isolated_native', UP / 'callas-native.py')
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


class IsolationTests(unittest.TestCase):
    def test_native_apps_never_request_sync_or_system_upgrade(self):
        calls = []
        def run(argv, **kwargs):
            calls.append(argv)
            if argv[0].endswith('checkupdates'):
                return types.SimpleNamespace(returncode=0, stdout='haruna 1 -> 2\n', stderr='')
            if '-Qu' in argv:
                return types.SimpleNamespace(returncode=0, stdout='haruna 1 -> 2\n', stderr='')
            return types.SimpleNamespace(returncode=0)
        with patch.object(native.subprocess, 'run', side_effect=run):
            self.assertEqual(native.update(), 0)
        transactions = [args for args in calls if args[0].endswith('pacman') and '-Qu' not in args]
        self.assertEqual(len(transactions), 1)
        self.assertIn('-S', transactions[0])
        self.assertIn('haruna', transactions[0])
        self.assertNotIn('-Syu', transactions[0])
        self.assertNotIn('-Sy', transactions[0])

    def test_outdated_local_database_defers_apps_without_a_transaction(self):
        calls = []
        def run(argv, **kwargs):
            calls.append(argv)
            if argv[0].endswith('checkupdates'):
                return types.SimpleNamespace(returncode=0, stdout='haruna 1 -> 3\n', stderr='')
            return types.SimpleNamespace(returncode=0, stdout='haruna 1 -> 2\n', stderr='')
        with patch.object(native.subprocess, 'run', side_effect=run):
            self.assertEqual(native.update(), 2)
        self.assertFalse(any('-S' in args or '-Syu' in args for args in calls))

    def test_config_deployment_installs_kernel_hooks_before_helpers_only_exit(self):
        source = (UP / 'callas-security.sh').read_text()
        before_exit = source.split('[[ ${2:-} != --helpers-only ]] || exit 0', 1)[0]
        self.assertIn("<<'KERNEL_POLICY_HOOK'", before_exit)
        self.assertIn("<<'KERNEL_REMOVE_HOOK'", before_exit)

    def test_config_update_preserves_the_scheduler_instead_of_starting_it(self):
        source = (UP / 'callas-security.sh').read_text()
        self.assertIn('put-update --instalar-para "$usuario" --preserve-schedule', source)
        updater = (UP / 'put-update.sh').read_text()
        self.assertIn('if (( ! preservar_agenda )); then', updater)
        self.assertIn('[[ ${2:-} != --preserve-schedule ]] || preservar_agenda=1', updater)

    def test_apps_checkpoint_requires_haruna(self):
        spec = importlib.util.spec_from_file_location('isolated_state', UP / 'callas-update-state.py')
        state = importlib.util.module_from_spec(spec); spec.loader.exec_module(state)
        self.assertIn('/usr/bin/haruna', state.REQUIRED['apps'])

class GeneralGateTests(unittest.TestCase):
    def test_missing_enforcement_aborts_before_pacman(self):
        source = (UP / 'put-update.sh').read_text()
        block = source.split('atualizar_arch() {', 1)[1].split('\natualizar_aur()', 1)[0]
        block = 'atualizar_arch() {' + block
        block = block.replace('/usr/local/libexec/callas-kernel-policy', 'policy_fixture')
        code = '''set -euo pipefail
mountpoint() { return 0; }
policy_fixture() { return 1; }
pacman() { echo TRANSACTION; }
pacman-conf() { echo /tmp/nonexistent; }
paru_conf=/nonexistent
''' + block + '\natualizar_arch manual\n'
        result = subprocess.run(['bash', '-c', code], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('TRANSACTION', result.stdout)

class SchedulerPreservationTests(unittest.TestCase):
    def test_overdue_dates_and_running_timer_are_not_changed_by_config_install(self):
        source = (UP / 'put-update.sh').read_text()
        disable = source.split('desativar_agendamento_antigo() {', 1)[1].split('\ninstalar() {', 1)[0]
        install = source.split('instalar() {', 1)[1].split('\nperguntar_reinicio()', 1)[0]
        functions = 'desativar_agendamento_antigo() {' + disable + '\ninstalar() {' + install
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for path in ('etc/systemd/system', 'run/systemd/system', 'home', 'agenda'):
                (root / path).mkdir(parents=True)
            (root / 'etc/arch-release').touch()
            for name, content in {'inicio':'2020-01-01\n', 'sistema':'2020-02-01\n', 'apps':'2020-01-08\n'}.items():
                (root / 'agenda' / name).write_text(content)
            units = root / 'etc/systemd/system'
            (units / 'put-update-check.timer').write_text('existing running timer\n')
            (units / 'put-update-check.service').write_text('existing check service\n')
            before = {str(p.relative_to(root)):p.read_bytes() for folder in ('agenda', 'etc/systemd/system') for p in (root / folder).iterdir()}
            functions = functions.replace('/etc/', str(root) + '/etc/').replace('/run/', str(root) + '/run/')
            prefix = r'''set -euo pipefail
servico_check=put-update-check.service
timer_check=put-update-check.timer
agenda_dir="$TEST_ROOT/agenda"
lock_atualizador="$TEST_ROOT/lock"
program="$TEST_ROOT/program"
atalho_menu="$TEST_ROOT/desktop"
sudo_rule="$TEST_ROOT/rule"
sudo_template="$TEST_ROOT/template"
paru_conf="$TEST_ROOT/paru"
CALLAS_UPDATE_LOCK_HELD=1
home_do_usuario() { echo "$TEST_ROOT/home"; }
realpath() { echo "$program"; }
erro() { echo "$*" >&2; exit 1; }
como_usuario() { return 0; }
instalar_entrada_menu() { return 0; }
systemd-detect-virt() { return 1; }
systemctl() {
  printf '%s\n' "$*" >> "$TEST_ROOT/systemctl"
  [[ $1 != show ]] || echo loaded
}
preparar_agenda() { echo 'UNEXPECTED DATE CHANGE' >&2; exit 93; }
'''
            result = subprocess.run(['bash', '-c', prefix + functions + '\ninstalar fixture --preserve-schedule\n'], env=dict(os.environ, TEST_ROOT=temp), capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            after = {str(p.relative_to(root)):p.read_bytes() for folder in ('agenda', 'etc/systemd/system') for p in (root / folder).iterdir()}
            self.assertEqual(before, after)
            commands = (root / 'systemctl').read_text()
            self.assertNotIn('put-update-check', commands)
            self.assertNotIn('restart', commands)
            self.assertNotIn('start ', commands)
            self.assertNotIn('enable', commands)

class SharedPolicyTests(unittest.TestCase):
    def test_aur_transactions_use_the_resolved_dependency_and_removal_guard(self):
        for filename in ('callas-aur.py', 'callas-aur-install.py'):
            with self.subTest(filename=filename):
                spec = importlib.util.spec_from_file_location('aur_isolation_' + filename, UP / filename)
                module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
                for dependency in ('linux', 'linux-lts-headers', 'nvidia-utils', 'glibc', 'mesa', 'systemd'):
                    writes = []
                    def transaction(argv):
                        hooks = Path(argv[argv.index('--hookdir', argv.index('--hookdir') + 1) + 1])
                        hook = next(hooks.glob('*.hook')).read_text()
                        self.assertIn('Operation = Remove', hook)
                        guard = hook.split('Exec = /usr/bin/python3 ', 1)[1].strip()
                        result = subprocess.run(['/usr/bin/python3', guard], input='app\n' + dependency + '\n', capture_output=True, text=True)
                        if result.returncode == 0: writes.append('installed')
                        return result
                    result = module.native_policy().guarded_transaction(['-U', '--noconfirm', '/fixture/app.pkg.tar.zst'], runner=transaction)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(writes, [])

    def test_aur_app_plan_preserves_the_same_base_as_native_apps(self):
        spec = importlib.util.spec_from_file_location('aur_plan_isolation', UP / 'callas-aur.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        for package in native.FROZEN:
            with self.subTest(package=package), self.assertRaises(module.RequiresGeneral):
                module.plan(f'AUR TARGET {package} {package}', apps_only=True)

    def test_clean_install_deploys_native_policy_before_initial_aur_work(self):
        source = (ROOT.parent / 'instalar-arch.sh').read_text()
        native_copy = source.index('install -m 0755 "$CALLAS_SECURITY_TMP/callas-native.py" /mnt/usr/local/libexec/callas-native')
        self.assertLess(native_copy, source.index('instalar_aur paru-bin'))

    def test_installed_extensionless_aur_helpers_find_their_verified_sibling(self):
        from importlib.machinery import SourceFileLoader
        from importlib.util import module_from_spec, spec_from_loader
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'callas-native').write_bytes((UP / 'callas-native.py').read_bytes())
            for filename in ('callas-aur', 'callas-aur-install'):
                (root / filename).write_bytes((UP / (filename + '.py')).read_bytes())
                loader = SourceFileLoader('installed_' + filename, str(root / filename))
                module = module_from_spec(spec_from_loader(loader.name, loader)); loader.exec_module(module)
                self.assertTrue(module.native_policy().frozen('linux'))
                self.assertTrue(module.native_policy().frozen('nvidia-open-dkms'))

class HookInstallationTests(unittest.TestCase):
    def test_general_requires_intact_root_owned_policy_and_hooks(self):
        spec = importlib.util.spec_from_file_location('hook_install_policy', UP / 'callas-kernel-policy.py')
        policy = importlib.util.module_from_spec(spec); spec.loader.exec_module(policy)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); hooks = root / 'hooks'; hooks.mkdir()
            program = root / 'policy'; program.write_text('#!/bin/sh\nexit 0\n'); program.chmod(0o755)
            for name, content in policy.REQUIRED_HOOKS.items():
                (hooks / name).write_text(content); (hooks / name).chmod(0o644)
            original_stat = Path.stat
            def root_owned(path, *args, **kwargs):
                result = original_stat(path, *args, **kwargs)
                if path.is_relative_to(root):
                    fields = list(result); fields[4] = 0
                    return os.stat_result(fields)
                return result
            with patch.object(policy, 'HOOK_DIRECTORY', hooks), patch.object(policy, 'POLICY_PROGRAM', program), patch.object(Path, 'stat', root_owned):
                policy.check_hooks()
                target = hooks / '00-callas-kernel-policy.hook'
                good = target.read_text()
                target.write_text(good.replace('AbortOnFail\n', ''))
                with self.assertRaises(RuntimeError): policy.check_hooks()
                target.write_text(good); target.chmod(0o666)
                with self.assertRaises(RuntimeError): policy.check_hooks()
                target.unlink(); target.symlink_to('/dev/null')
                with self.assertRaises(RuntimeError): policy.check_hooks()


if __name__ == '__main__': unittest.main()
