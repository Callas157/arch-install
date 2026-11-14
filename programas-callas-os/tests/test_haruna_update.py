"""Exercise Haruna provisioning offline; package operations are simulated."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class HarunaTests(unittest.TestCase):
    def test_clean_install_includes_native_haruna(self):
        installer = (ROOT.parent / 'instalar-arch.sh').read_text()
        command = 'pacstrap -K /mnt ' + installer.split('pacstrap -K /mnt ', 1)[1].split('\ngenfstab', 1)[0]
        result = subprocess.run(['bash', '-c', 'set -eu\nUCODE_PACKAGE=intel-ucode\nREDE_PACOTES=() GPU_PACOTES=() RISEMODE_PACOTES=()\npacstrap() { printf "%s\\n" "$@"; }\n' + command], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('haruna', result.stdout.splitlines())

    def test_existing_missing_and_failed_installations(self):
        source = (ROOT / 'atualizador/callas-config-update.sh').read_text()
        block = source.partition('# BEGIN native Haruna preparation\n')[2].partition('# END native Haruna preparation')[0]
        self.assertTrue(block, 'Haruna provisioning is missing')
        block = block.replace('/usr/local/libexec/callas-native', 'native_fixture')
        for scenario in ('existing', 'missing', 'query-error', 'install-error', 'verify-error'):
            with self.subTest(scenario=scenario):
                code = r'''set -euo pipefail
installed=0
[[ $1 != existing ]] || installed=1
erro() { echo "$*" >&2; exit 1; }
pacman() {
  [[ "$*" == '-Q haruna' ]] || exit 90
  [[ $scenario != query-error ]] || return 2
  (( installed == 1 ))
}
native_fixture() {
  [[ "$*" == '--install haruna' && $scenario != existing ]] || exit 92
  [[ $scenario != install-error ]] || return 1
  [[ $scenario == verify-error ]] || installed=1
}
scenario=$1
'''
                result = subprocess.run(['bash', '-c', code + block + '\necho COMPLETE', 'fixture', scenario], capture_output=True, text=True)
                self.assertEqual(result.returncode == 0, scenario in ('existing', 'missing'), result.stdout + result.stderr)
                self.assertEqual('COMPLETE' in result.stdout, scenario in ('existing', 'missing'))
