import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def test_single_file_installer_works_without_the_source_directory(self):
        from build_installer import build
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)/'perfil'
            home.mkdir()
            script = Path(temp)/'instalar.sh'
            build(script)
            env = dict(os.environ, HOME=str(home), XDG_DATA_HOME=str(home/'dados'))
            result = subprocess.run([str(script), '--sem-dependencias'], cwd=temp, env=env,
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            installed = home/'dados/callas-chat/app/callas_chat/ui.py'
            self.assertEqual(installed.read_bytes(), (ROOT/'callas_chat/ui.py').read_bytes())
            damaged = script.read_text().replace("hexdigest()!='", "hexdigest()!='0", 1)
            script.write_text(damaged)
            result = subprocess.run([str(script), '--extrair', str(Path(temp)/'bad')],
                                    text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('integridade', result.stderr)

    def test_reinstall_preserves_user_data_and_registers_kde_entry(self):
        with tempfile.TemporaryDirectory(prefix='callas chat ') as temp:
            home = Path(temp)
            env = dict(os.environ, HOME=temp, XDG_DATA_HOME=str(home/'dados'),
                       XDG_CONFIG_HOME=str(home/'config'))
            target = home/'dados/callas-chat'
            target.mkdir(parents=True)
            keep = target/'attachments/photo.png'
            keep.parent.mkdir()
            keep.write_bytes(b'keep')
            for _ in range(2):
                result = subprocess.run(['python', str(ROOT/'installer.py'), '--sem-dependencias'],
                                        env=env, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            self.assertEqual(keep.read_bytes(), b'keep')
            desktop = home/'dados/applications/io.github.callasos.CallasChat.desktop'
            self.assertTrue(desktop.exists())
            self.assertIn('Name=Codex', desktop.read_text())
            self.assertIn('codex.svg', desktop.read_text())
            self.assertTrue((home/'.local/bin/codex-askpass').is_file())
            subprocess.run(['sh', '-n', str(home/'.local/bin/codex-askpass')], check=True)
            self.assertEqual(len(list(desktop.parent.glob('*.desktop'))), 1)
            subprocess.run(['desktop-file-validate', str(desktop)], check=True)
            self.assertTrue((home/'.local/bin/callas-chat').stat().st_mode & 0o100)
            self.assertTrue((target/'app/callas_chat/ui.py').exists())

    def test_system_dependencies_use_guard_and_abort_on_failure(self):
        import installer
        with patch.object(installer.Path, 'is_file', return_value=True), \
             patch.object(installer.Path, 'stat', return_value=SimpleNamespace(st_uid=0, st_mode=0o755)), \
             patch.object(installer.shutil, 'which', return_value='/usr/bin/codex'), \
             patch.object(installer.subprocess, 'run') as run, \
             patch.dict(os.environ, {'SUDO_ASKPASS': '/safe/askpass'}):
            run.side_effect = [subprocess.CompletedProcess([], 1), subprocess.CalledProcessError(1, 'guard')]
            with self.assertRaises(subprocess.CalledProcessError): installer.prepare_system_dependencies()
            self.assertEqual(run.call_args.args[0],
                ['/usr/bin/sudo', '-A', '--', '/usr/local/libexec/callas-native', '--install', 'pyside6'])

    def test_whisper_model_is_reused_without_redownload(self):
        import setup_voice
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model = root/'models'/setup_voice.MODEL
            model.mkdir(parents=True)
            for name in setup_voice.FILES:
                (model/name).write_bytes(b'model-fixture')
            # System Python intentionally has no faster_whisper/huggingface_hub.
            # Reusing a prepared model must not import downloader dependencies.
            setup_voice.prepare(root)

    def test_whisper_model_requires_all_files(self):
        from callas_chat.model_files import whisper_ready
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'model.bin').write_bytes(b'model-fixture')
            self.assertFalse(whisper_ready(root))


if __name__ == '__main__': unittest.main()
