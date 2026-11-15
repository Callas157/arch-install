"""Exercise shared GUI deployment routing without root, packages or services."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
UP = ROOT / 'atualizador'


def module(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), UP / (name + '.py'))
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


class GraphicalUpdaterIntegrationTests(unittest.TestCase):
    def shared_block(self):
        source = (UP / 'callas-security.sh').read_text()
        start = source.index('  if [[ ${2:-} == --config-update ]]; then\n    /usr/local/libexec/put-update')
        end = source.index('  if [[ ${2:-} != --config-update ]]; then', start)
        return source[start:end]

    def test_both_modes_deploy_the_same_staged_gui_after_the_backend(self):
        # Both actual shell branches run. Only privileged backend provisioning and
        # account switching are replaced; GUI/askpass/icon/desktop writes are real.
        for mode in ('--installation', '--config-update'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temp:
                base = Path(temp); stage = base / 'stage'; stage.mkdir()
                for name in ('callas-update-gui.py', 'callas-update-gui-install.py'):
                    (stage / name).write_bytes((UP / name).read_bytes())
                runner = base / 'runner.py'
                runner.write_text('''import importlib.util, json, os, sys
from pathlib import Path
source, *args = sys.argv[1:]
assert args == ['--install-system', 'fixture', '--gui', str(Path(source).with_name('callas-update-gui.py'))], args
spec=importlib.util.spec_from_file_location('staged_deploy',source)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
prefix=Path(os.environ['FIXTURE_PREFIX'])
entry,gui=m.deploy(args[-1],prefix)
m.configure_user(Path(os.environ['FIXTURE_HOME']),entry,gui)
print(json.dumps({'gui':str(gui),'id':m.ID}))
''')
                backend = base / 'backend'
                backend.write_text('''#!/bin/bash
set -eu
printf '%s\\n' "$*" > "$FIXTURE_BACKEND_ARGS"
mkdir -p "$FIXTURE_PREFIX/share/applications"
printf '[Desktop Entry]\\nTerminal=true\\n' > "$FIXTURE_PREFIX/share/applications/io.github.Callas157.AtualizadorDoSistema.desktop"
'''); backend.chmod(0o755)
                code = 'set -Eeuo pipefail\nusuario=fixture\nstage="$FIXTURE_STAGE"\npython(){ /usr/bin/python3 "$FIXTURE_RUNNER" "$@"; }\n'
                code += self.shared_block().replace('/usr/local/libexec/put-update', '"$FIXTURE_BACKEND"')
                env = dict(os.environ, FIXTURE_STAGE=str(stage), FIXTURE_PREFIX=str(base / 'system'),
                           FIXTURE_HOME=str(base / 'home'), FIXTURE_BACKEND=str(backend),
                           FIXTURE_BACKEND_ARGS=str(base / 'backend-args'), FIXTURE_RUNNER=str(runner))
                result = subprocess.run(['bash', '-c', code, 'fixture', 'fixture', mode],
                                        env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                installed = json.loads(result.stdout)
                self.assertEqual(Path(installed['gui']).read_bytes(), (UP / 'callas-update-gui.py').read_bytes())
                desktop = base / 'system/share/applications' / installed['id']
                self.assertIn('Terminal=false', desktop.read_text())
                self.assertEqual((base / 'home/.local/share/applications' / installed['id']).read_bytes(), desktop.read_bytes())
                expected = '--instalar-para fixture' + (' --preserve-schedule' if mode == '--config-update' else '')
                self.assertEqual((base / 'backend-args').read_text().strip(), expected)
                self.assertEqual(len(list(desktop.parent.glob('*.desktop'))), 1)

    def test_failed_gui_deployment_stops_the_shared_phase(self):
        code = 'set -Eeuo pipefail\nusuario=fixture\nstage=/verified\nbackend(){ :; }\npython(){ return 19; }\n'
        code += self.shared_block().replace('/usr/local/libexec/put-update', 'backend')
        code += '\nprintf "UNEXPECTED_SUCCESS\\n"\n'
        for mode in ('--installation', '--config-update'):
            result = subprocess.run(['bash', '-c', code, 'fixture', 'fixture', mode], capture_output=True, text=True)
            self.assertEqual(result.returncode, 19)
            self.assertNotIn('UNEXPECTED_SUCCESS', result.stdout)

    def test_gui_change_invalidates_update_checkpoint(self):
        state = module('callas-update-state')
        release = module('callas-release')
        with tempfile.TemporaryDirectory() as temp:
            stage = Path(temp)
            for path in release.FILES:
                (stage / Path(path).name).write_bytes((ROOT.parent / path).read_bytes())
            before = state.fingerprint('security', stage)
            gui = stage / 'callas-update-gui.py'
            gui.write_bytes(gui.read_bytes() + b'\n# test revision\n')
            self.assertNotEqual(state.fingerprint('security', stage), before)


if __name__ == '__main__': unittest.main()
