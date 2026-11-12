"""Exercise the Spotify migration block without installing host packages."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

class SpotifyUpdateTests(unittest.TestCase):
    def run_migration(self, scenario):
        text=(ROOT/'atualizador/callas-config-update.sh').read_text()
        block=text[text.index('# Complete the native application set'):text.index('# End native Spotify preparation.')]
        block=block.replace('/usr/local/libexec/callas-aur-install','install_fixture').replace('/usr/local/libexec/callas-spotify-permissions','permissions_fixture')
        code='''set -euo pipefail
usuario=fixture
erro() { printf '%s\\n' "$*" >&2; exit 1; }
pacman() {
 [[ "$*" == '-Q spotify' ]] || exit 90
 case "$SCENARIO" in
  existing) return 0 ;;
  query-error) return 2 ;;
 esac
 [[ -f "$STATE/installed" ]]
}
permissions_fixture() { printf "PERMISSIONS\\n"; }
install_fixture() {
 printf '%s\\n' "$*" >> "$STATE/invocations"
 [[ "$*" == 'fixture spotify' ]] || exit 91
 [[ "$SCENARIO" != build-error ]] || return 1
 [[ "$SCENARIO" == verify-error ]] || touch "$STATE/installed"
}
'''+block+'\nprintf "COMPLETE\\n"\n'
        with tempfile.TemporaryDirectory() as temp:
            result=subprocess.run(['bash','-c',code],env=dict(os.environ,STATE=temp,SCENARIO=scenario),capture_output=True,text=True)
            calls=Path(temp)/'invocations'
            return result,calls.read_text().splitlines() if calls.exists() else []

    def test_existing_spotify_is_preserved_without_reinstall(self):
        result,calls=self.run_migration('existing')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(calls,[])
        self.assertIn('já instalado',result.stdout)
        self.assertIn('PERMISSIONS',result.stdout)

    def test_missing_spotify_is_installed_and_verified(self):
        result,calls=self.run_migration('missing')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(calls,['fixture spotify'])
        self.assertIn('COMPLETE',result.stdout)
        self.assertIn('PERMISSIONS',result.stdout)

    def test_build_failure_or_missing_result_cannot_report_completion(self):
        for scenario,message in [('build-error','Não consegui instalar'),('verify-error','não foi encontrado')]:
            with self.subTest(scenario=scenario):
                result,calls=self.run_migration(scenario)
                self.assertNotEqual(result.returncode,0)
                self.assertEqual(calls,['fixture spotify'])
                self.assertNotIn('COMPLETE',result.stdout)
                self.assertIn(message,result.stderr)

    def test_database_query_error_stops_before_build(self):
        result,calls=self.run_migration('query-error')
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(calls,[])
        self.assertIn('banco de pacotes',result.stderr)

    def test_required_step_precedes_favorites_and_release_completion(self):
        text=(ROOT/'atualizador/callas-config-update.sh').read_text()
        start=text.index('# Complete the native application set')
        self.assertLess(start,text.index('Prepend='))
        self.assertLess(start,text.index('/usr/local/libexec/callas-version --complete'))
        self.assertLess(text.index('/usr/bin/bash "$CALLAS_RELEASE_DIR/callas-security.sh"'),start)

if __name__=='__main__': unittest.main()
