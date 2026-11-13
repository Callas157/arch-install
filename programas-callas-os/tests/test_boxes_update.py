"""Run the real Boxes migration with package managers simulated offline."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BoxesUpdateTests(unittest.TestCase):
    def migrate(self, scenario='missing'):
        source = (ROOT / 'atualizador/callas-config-update.sh').read_text()
        block = source.partition('# BEGIN native Boxes migration\n')[2].partition('# END native Boxes migration')[0]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for scope in ('system', 'user'):
                (root / scope).write_text('org.gnome.Boxes\ncom.example.Keep\n')
            if scenario == 'no-flatpak-app':
                for scope in ('system', 'user'):
                    (root / scope).write_text('com.example.Keep\n')
            data = root / '.var/app/org.gnome.Boxes/data/gnome-boxes/images/disk.qcow2'
            data.parent.mkdir(parents=True)
            data.write_bytes(b'VM disk and configuration must survive')
            if scenario == 'existing':
                (root / 'native').touch()
            code = r'''set -euo pipefail
usuario=fixture
erro() { echo "$*" >&2; exit 1; }
como_usuario() { USER_SCOPE=1 "$@"; }
pacman() {
  case "$*" in
    '-Q gnome-boxes')
      [[ $SCENARIO != query-error ]] || return 2
      [[ -f $STATE/native ]] ;;
    '-S --needed --noconfirm gnome-boxes')
      [[ $SCENARIO != existing ]] || return 94
      [[ $SCENARIO != install-error ]] || return 1
      [[ $SCENARIO == verify-error ]] || touch "$STATE/native" ;;
    *) return 90 ;;
  esac
}
native_fixture() {
  [[ "$*" == '--install gnome-boxes' ]] || return 95
  pacman -S --needed --noconfirm gnome-boxes
}
kernel_fixture() { [[ "$*" == '--verify-only' && $SCENARIO != boot-error ]]; }
flatpak() {
  local scope=system
  [[ ${USER_SCOPE:-0} != 1 ]] || scope=user
  [[ " $* " != *' --delete-data '* ]] || exit 91
  case "$*" in
    "list --$scope --app --columns=application")
      [[ $SCENARIO != list-error ]] || return 2
      cat "$STATE/$scope" ;;
    "uninstall --$scope --noninteractive --assumeyes org.gnome.Boxes")
      [[ -f $STATE/native ]] || exit 92
      [[ $SCENARIO != uninstall-error ]] || return 1
      [[ $SCENARIO == uninstall-noop ]] || sed -i '/^org.gnome.Boxes$/d' "$STATE/$scope" ;;
    *) return 93 ;;
  esac
}
'''
            block = block.replace('/usr/local/libexec/callas-native', 'native_fixture').replace('/usr/local/libexec/callas-kernel-check', 'kernel_fixture')
            if scenario == 'repeat':
                block += '\n' + block
            result = subprocess.run(['bash', '-c', code + block + '\necho COMPLETE\n'],
                                    env=dict(os.environ, STATE=temp, SCENARIO=scenario),
                                    capture_output=True, text=True)
            return result, (root / 'native').exists(), [
                (root / scope).read_text() for scope in ('system', 'user')], data.read_bytes()

    def test_installs_native_and_removes_both_flatpak_scopes_preserving_vm_data(self):
        result, native, scopes, data = self.migrate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(native)
        self.assertEqual(scopes, ['com.example.Keep\n', 'com.example.Keep\n'])
        self.assertEqual(data, b'VM disk and configuration must survive')

    def test_existing_native_still_removes_flatpak(self):
        result, native, scopes, _ = self.migrate('existing')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(native)
        self.assertEqual(scopes, ['com.example.Keep\n', 'com.example.Keep\n'])

    def test_repeated_migration_or_absent_flatpak_app_is_harmless(self):
        for scenario in ('repeat', 'no-flatpak-app'):
            with self.subTest(scenario=scenario):
                result, native, scopes, _ = self.migrate(scenario)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(native)
                self.assertEqual(scopes, ['com.example.Keep\n', 'com.example.Keep\n'])

    def test_clean_install_requests_native_boxes_in_base_packages(self):
        installer = (ROOT.parent / 'instalar-arch.sh').read_text()
        command = 'pacstrap -K /mnt ' + installer.split('pacstrap -K /mnt ', 1)[1].split('\ngenfstab', 1)[0]
        code = '''set -eu
UCODE_PACKAGE=intel-ucode
REDE_PACOTES=() GPU_PACOTES=() RISEMODE_PACOTES=()
pacstrap() { printf '%s\\n' "$@"; }
''' + command
        result = subprocess.run(['bash', '-c', code], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('gnome-boxes', result.stdout.splitlines())

    def test_package_failure_never_removes_flatpak_or_claims_success(self):
        for scenario in ('query-error', 'install-error', 'verify-error', 'boot-error'):
            with self.subTest(scenario=scenario):
                result, _, scopes, _ = self.migrate(scenario)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('COMPLETE', result.stdout)
                self.assertTrue(all('org.gnome.Boxes' in scope for scope in scopes))

    def test_flatpak_errors_or_failed_removal_cannot_complete_update(self):
        for scenario in ('list-error', 'uninstall-error', 'uninstall-noop'):
            with self.subTest(scenario=scenario):
                result, _, _, data = self.migrate(scenario)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('COMPLETE', result.stdout)
                self.assertEqual(data, b'VM disk and configuration must survive')


if __name__ == '__main__':
    unittest.main()
