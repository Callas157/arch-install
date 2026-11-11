"""Complete-update regressions; all package/service operations are mocked."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
UPDATER = ROOT / 'atualizador'
spec = importlib.util.spec_from_file_location('aur', UPDATER / 'callas-aur.py')
aur = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aur)

class AurTests(unittest.TestCase):
    def test_dependency_plan_preserves_order(self):
        result = aur.plan('INSTALL MAKE extra meson\nAUR DEP dependency dep\nAUR TARGET split app app-libs\n')
        self.assertEqual(result, [('INSTALL', 'MAKE', 'extra', ['meson']),
                                  ('AUR', 'DEP', 'dependency', ['dep']),
                                  ('AUR', 'TARGET', 'split', ['app', 'app-libs'])])

    def test_unsafe_or_unsolved_plan_is_rejected(self):
        for text in ('AUR TARGET x --root\n', 'AUR TARGET ../bad app\n',
                     'INSTALL DEP extra nvidia-utils\n', 'AUR TARGET x nvidia-open-dkms\n',
                     'MISSING broken\n', 'CONFLICT LOCAL a b\n', 'UNRECOGNIZED format\n'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                aur.plan(text)

    def test_build_sandbox_does_not_grant_sudo(self):
        builder = aur.Builder.__new__(aur.Builder)
        builder.work = Path('/private/work')
        builder.env = {'HOME': '/private/work/home'}
        with patch.object(aur, 'command', return_value=types.SimpleNamespace(stdout='')) as command:
            builder.run(['/usr/bin/makepkg', '--noconfirm'])
        args = command.call_args.args[0]
        self.assertIn('--property=NoNewPrivileges=yes', args)
        self.assertIn('--property=ProtectHome=yes', args)
        self.assertIn('--property=ProtectSystem=strict', args)
        self.assertIn('--property=ReadWritePaths=/private/work', args)
        self.assertNotIn('/usr/bin/sudo', args)
        self.assertNotIn('--skippgpcheck', args)

    def test_root_commands_have_no_interactive_stdin(self):
        with patch.object(aur.subprocess, 'run') as run:
            aur.command(['/usr/bin/pacman', '-Qmq'], capture=True)
        self.assertEqual(run.call_args.kwargs['stdin'], subprocess.DEVNULL)
        self.assertTrue(run.call_args.kwargs['check'])

    def test_empty_package_query_is_accepted_but_errors_are_not(self):
        with patch.object(aur.subprocess, 'run', return_value=types.SimpleNamespace(returncode=1, stdout='', stderr='')):
            aur.command(['query'], empty_ok=True)
        with patch.object(aur.subprocess, 'run', return_value=types.SimpleNamespace(returncode=1, stdout='', stderr='database error')):
            with self.assertRaises(subprocess.CalledProcessError):
                aur.command(['query'], empty_ok=True)

    def test_empty_paru_query_is_normalized_without_hiding_real_errors(self):
        builder = aur.Builder.__new__(aur.Builder)
        builder.work = Path('/fixture/work'); builder.env = {}
        with patch.object(aur, 'command') as command:
            builder.run(['/usr/bin/paru', '-Qua', '--quiet'], capture=True, empty_ok=True)
        argv = command.call_args.args[0]
        script = argv[argv.index('-c') + 1]
        for body, expected in (('exit 1', 0), ('echo network-failed >&2; exit 1', 1), ('echo app; exit 0', 0)):
            result = subprocess.run(['bash', '-c', script, 'query', '/usr/bin/bash', '-c', body], capture_output=True)
            self.assertEqual(result.returncode, expected)

    def test_previous_launcher_can_expand_new_release_file_list(self):
        text = (UPDATER / 'callas-config-update.sh').read_text()
        expansion = text.split("<<'EXPAND_STAGE'\n", 1)[1].split('\nEXPAND_STAGE', 1)[0]
        with tempfile.TemporaryDirectory() as temp:
            stage = Path(temp)
            (stage / 'callas-release.py').write_text('from pathlib import Path\ndef stage_files(destination, ref):\n    (Path(destination)/"callas-aur.py").write_text(ref)\n')
            subprocess.run(['/usr/bin/python3', '-', temp, 'a' * 40], input=expansion, text=True, check=True)
            self.assertEqual((stage / 'callas-aur.py').read_text(), 'a' * 40)
        self.assertLess(text.index("<<'EXPAND_STAGE'"), text.index('/usr/bin/bash "$CALLAS_RELEASE_DIR/callas-security.sh"'))

    def test_symlink_build_output_is_rejected_before_package_install(self):
        with tempfile.TemporaryDirectory() as temp:
            builder = aur.Builder.__new__(aur.Builder)
            builder.directory = Path(temp)
            builder.work = Path(temp) / 'work'; builder.work.mkdir()
            builder.uid = os.getuid()
            (builder.work / 'out').mkdir()
            checkout = builder.work / 'src-app'; checkout.mkdir()
            (checkout / '.SRCINFO').write_text('pkgbase = app\npkgname = app\n')
            (builder.work / 'out' / 'bad.pkg.tar.zst').symlink_to('/etc/passwd')
            with patch.object(builder, 'run'), patch.object(aur, 'command') as command:
                with self.assertRaises(OSError):
                    builder.build('app', ['app'])
            command.assert_not_called()

    def test_updates_and_required_rebuilds_are_combined(self):
        calls = []
        def command(args, capture=False, empty_ok=False):
            calls.append(args)
            return types.SimpleNamespace(stdout='app\nold-python\n' if '-Qmq' in args else '')
        class FakeBuilder:
            def __init__(self, directory): self.checks = 0
            def run(self, args, capture=False, empty_ok=False):
                if '-Qua' in args: out = 'app\n'
                elif '-Po' in args: out = 'AUR TARGET app app\nAUR TARGET old-python old-python\n'
                else:
                    self.checks += 1
                    out = 'foreign\told-python\n' if self.checks == 1 else ''
                return types.SimpleNamespace(stdout=out)
            def build(self, base, expected): return ['/private/' + base + '.pkg.tar.zst']
        with tempfile.TemporaryDirectory() as temp, patch.object(aur, 'BUILDS_ROOT', Path(temp) / 'builds'), \
             patch.object(aur, 'Builder', FakeBuilder), patch.object(aur, 'command', command):
            aur.run_update()
        installs = [args for args in calls if '-U' in args]
        self.assertEqual(len(installs), 2)
        self.assertTrue(all('--noconfirm' in args for args in installs))

class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.text = (UPDATER / 'put-update.sh').read_text()

    def test_boot_validation_runs_last_even_after_aur_failure(self):
        function = self.text[self.text.index('atualizar_sistema() {'):self.text.index('\natualizar_apps()')]
        for fail in ('', 'AUR e recompilações necessárias'):
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as temp:
                log = Path(temp) / 'order'
                script = '''set -euo pipefail
etapa() { printf '%s\\n' "$1" >> "$ORDER"; [[ $1 != "$FAIL" ]]; }
''' + function + '\natualizar_sistema automatico user /home/user\n'
                result = subprocess.run(['bash', '-c', script], env=dict(os.environ, ORDER=str(log), FAIL=fail))
                self.assertEqual(result.returncode, int(bool(fail)))
                self.assertEqual(log.read_text().splitlines(), ['Ponto de recuperação pré-update',
                    'Arch e aplicativos dos repositórios', 'AUR e recompilações necessárias',
                    'Flatpaks e Discord', 'Kernels padrão/LTS, DKMS e boot'])

    def test_reboot_notice_only_after_successful_transaction_and_log(self):
        function = self.text[self.text.index('registrar_atualizacao() {'):self.text.index('\nnotificar_falha_usuario()')]
        for fail in (0, 1):
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as temp:
                log, events = Path(temp) / 'log', Path(temp) / 'events'
                script = '''set -euo pipefail
program=/unused
home_do_usuario() { printf /home/test; }
atualizar_sistema() { printf transaction; return "$FAIL"; }
como_usuario() { cat > "$LOG"; }
proxima_data() { printf 2026-11-18; }
gravar_data_agenda() { printf 'schedule\\n' >> "$EVENTS"; }
marcar_reinicio_pendente() { grep -q 'Fim da atualização' "$LOG"; printf 'reboot\\n' >> "$EVENTS"; }
notificar_falha_usuario() { printf 'failed\\n' >> "$EVENTS"; }
''' + function + '\nregistrar_atualizacao user sistema automatico\n'
                result = subprocess.run(['bash', '-c', script], env=dict(os.environ, LOG=str(log), EVENTS=str(events), FAIL=str(fail)), capture_output=True)
                self.assertEqual(result.returncode, fail)
                self.assertIn('transaction', log.read_text())
                self.assertEqual(events.read_text().splitlines(), ['failed'] if fail else ['schedule', 'schedule', 'reboot'])

    def test_full_update_advances_app_schedule_so_it_is_not_run_twice(self):
        function = self.text[self.text.index('executar_agendado() {'):self.text.index('\nverificar_agenda()')]
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / 'dates'
            script = '''set -euo pipefail
ler_data_agenda() { printf 2020-01-01; }
registrar_atualizacao() { return 0; }
proxima_data() { printf 2026-11-18; }
gravar_data_agenda() { printf '%s %s\\n' "$1" "$2" >> "$LOG"; }
''' + function + '\nexecutar_agendado user sistema\n'
            subprocess.run(['bash', '-c', script], env=dict(os.environ, LOG=str(log)), check=True)
            self.assertEqual(log.read_text().splitlines(), ['sistema 2026-11-18', 'apps 2026-11-18'])

    def test_notification_from_previous_boot_is_discarded(self):
        function = self.text[self.text.index('notificar_reinicio_usuario() {'):self.text.index('\nmarcar_reinicio_pendente()')]
        function = function.replace("(( EUID != 0 )) || erro 'A notificação deve rodar na sessão do usuário.'", ': # fixture')
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / 'callas'; state.mkdir()
            marker = state / 'reinicio-pendente'; marker.write_text('a-previous-boot\n')
            subprocess.run(['bash', '-c', 'set -euo pipefail\n' + function + '\nnotificar_reinicio_usuario'],
                           env=dict(os.environ, XDG_STATE_HOME=temp), check=True)
            self.assertFalse(marker.exists())

if __name__ == '__main__':
    unittest.main()
