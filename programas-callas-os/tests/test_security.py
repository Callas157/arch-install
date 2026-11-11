"""Offline security regression tests. No network, pacman changes or real /etc writes."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
UPDATER = ROOT / 'atualizador'

def module(name):
    spec = importlib.util.spec_from_file_location(name, UPDATER / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

release = module('callas-release')
logs = module('callas-logs')

class ReleaseTests(unittest.TestCase):
    def test_immutable_download_and_tamper_rejection(self):
        ref = 'a' * 40
        data = {name: (UPDATER / Path(name).name).read_bytes()
                if (UPDATER / Path(name).name).exists() else b'# harmless\n'
                for name in release.FILES}
        tree = {'tree': [{'path': name, 'type': 'blob', 'mode': '100644',
                          'sha': hashlib.sha1(b'blob ' + str(len(body)).encode() + b'\0' + body).hexdigest()}
                         for name, body in data.items()]}
        seen = []
        def request(url):
            seen.append(url)
            if '/git/trees/' in url:
                return json.dumps(tree).encode()
            return data[url.split('/' + ref + '/', 1)[1]]
        with tempfile.TemporaryDirectory() as stage, patch.object(release, 'request', request):
            release.stage_files(stage, ref)
            self.assertTrue((Path(stage) / 'callas-security.sh').exists())
            self.assertTrue(all('/' + ref in url for url in seen))
            data[release.FILES[0]] += b'\n# tampered'
            with self.assertRaisesRegex(ValueError, 'blob'):
                release.stage_files(stage, ref)

    def test_rejects_non_commit_and_incomplete_tree(self):
        with tempfile.TemporaryDirectory() as stage:
            with self.assertRaises(ValueError):
                release.stage_files(stage, 'main')
            with patch.object(release, 'request', return_value=b'{"truncated":true}'):
                with self.assertRaises(ValueError):
                    release.stage_files(stage, 'a' * 40)

class LogTests(unittest.TestCase):
    def test_documents_categories_private_and_separate_executions(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(logs, 'documents', return_value=Path(temp)), \
             patch.object(logs.os, 'geteuid', return_value=1000):
            first = logs.write_log('Kernel Linux', b'kernel failure\n')
            second = logs.write_log('Kernel Linux', b'kernel success\n')
            self.assertNotEqual(first, second)
            self.assertEqual(first.read_bytes(), b'kernel failure\n')
            self.assertEqual(first.stat().st_mode & 0o777, 0o600)
            for category in logs.CATEGORIES:
                self.assertTrue((Path(temp) / 'Logs do Callas OS' / category).is_dir())
            with self.assertRaises(ValueError):
                logs.write_log('../escape', b'bad')

    def test_root_cannot_write_into_documents(self):
        with patch.object(logs.os, 'geteuid', return_value=0):
            with self.assertRaises(ValueError):
                logs.write_log('AUR', b'bad')

class ShellTests(unittest.TestCase):
    def test_installer_stage_ignores_python_cache_directories(self):
        installer = (ROOT.parent / 'instalar-arch.sh').read_text()
        copy = installer[installer.index('for security_file in '):]
        copy = copy[:copy.index('\ndone') + len('\ndone')]
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp); source = base / 'source'; target = base / 'target'
            source.mkdir(); target.mkdir(); (source / '__pycache__').mkdir()
            (source / 'callas-release.py').write_text('# staged\n')
            (source / 'callas-security.sh').write_text('# staged\n')
            copy = copy.replace('/mnt/usr/local/share/callas-os/security-stage/', str(target) + '/')
            subprocess.run(['bash', '-c', 'set -euo pipefail\n' + copy],
                           env=dict(os.environ, CALLAS_SECURITY_TMP=str(source)), check=True)
            self.assertEqual(sorted(p.name for p in target.iterdir()), ['callas-release.py', 'callas-security.sh'])

    def test_system_agenda_is_weekly(self):
        text = (UPDATER / 'put-update.sh').read_text()
        fn = text[text.index('proxima_data() {'):text.index('\nler_data_agenda()')]
        result = subprocess.run(['bash', '-c', fn + '\nproxima_data sistema 2026-11-11'], capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), '2026-11-18')

    def test_no_passwordless_pacman_and_installer_matches_updater(self):
        installer = (ROOT.parent / 'instalar-arch.sh').read_text()
        updater = (UPDATER / 'put-update.sh').read_text()
        for text in (installer, updater):
            self.assertNotIn('NOPASSWD:', text)
            self.assertNotIn('--skipreview', text)
        embedded = installer.split("<<'CALLAS_UPDATER'\n", 1)[1].split('\nCALLAS_UPDATER', 1)[0]
        self.assertEqual(embedded, updater.rstrip('\n'))

    def test_failed_pacman_aborts_security_before_later_changes(self):
        text = (UPDATER / 'callas-security.sh').read_text()
        function = text[text.index('seguranca() {'):text.index('\n# Do not place this function')]
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / 'etc').mkdir()
            (base / 'etc/pacman.conf').write_text('[options]\nSigLevel = Never\n[core]\nSigLevel = Never\n')
            bindir = base / 'bin'; bindir.mkdir()
            fake = bindir / 'pacman'
            fake.write_text('#!/bin/bash\n[[ $1 == -Q ]] && exit 1\nexit 23\n')
            fake.chmod(0o755)
            function = function.replace('/etc/', str(base / 'etc') + '/')
            env = dict(os.environ, PATH=str(bindir) + ':' + os.environ['PATH'])
            result = subprocess.run(['bash', '-c', 'set -Eeuo pipefail\n' + function + '\nseguranca tester\nprintf reached'], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 23, result.stderr)
            self.assertNotIn('reached', result.stdout)
            self.assertFalse((base / 'etc/sudoers.d/20-callas-security').exists())
            policy = (base / 'etc/pacman.conf').read_text()
            self.assertNotIn('SigLevel = Never', policy)
            self.assertIn('SigLevel = Required', policy)

    def test_kernel_failure_and_success_are_logged_and_marked(self):
        text = (UPDATER / 'callas-kernel-check.sh').read_text()
        for fail in (False, True):
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as temp:
                base = Path(temp)
                for path in ('boot/grub', 'usr/lib/modules/main', 'usr/lib/modules/lts', 'etc', 'var/tmp', 'var/lib/callas-os', 'usr/local/libexec', 'bin'):
                    (base / path).mkdir(parents=True, exist_ok=True)
                (base / 'etc/callas-nvidia-version').write_text('610.57.04\n')
                for folder, pkg in (('main', 'linux'), ('lts', 'linux-lts')):
                    (base / ('usr/lib/modules/' + folder + '/pkgbase')).write_text(pkg)
                    (base / ('usr/lib/modules/' + folder + '/vmlinuz')).write_text('kernel')
                    (base / ('boot/vmlinuz-' + pkg)).write_text('kernel')
                    (base / ('boot/initramfs-' + pkg + '.img')).write_text('initramfs')
                (base / 'boot/grub/grub.cfg').write_text('menuentry Callas\nvmlinuz-linux\nvmlinuz-linux-lts\n')
                for cmd, body in {'mountpoint':'exit 0', 'pacman':'exit 0', 'dkms':'exit 0',
                                  'modinfo': 'exit ' + ('1' if fail else '0'), 'mkinitcpio':'exit 0',
                                  'grub-script-check':'exit 0',
                                  'grub-mkconfig': 'while [[ $# -gt 0 ]]; do if [[ $1 == -o ]]; then cp "$FAKE_ROOT/boot/grub/grub.cfg" "$2"; exit; fi; shift; done'}.items():
                    script = base / 'bin' / cmd; script.write_text('#!/bin/bash\n' + body + '\n'); script.chmod(0o755)
                logger = base / 'usr/local/libexec/callas-logs'
                logger.write_text('#!/bin/bash\ncat >> "$FAKE_ROOT/recorded.log"\n'); logger.chmod(0o755)
                for prefix in ('/var/tmp/', '/var/lib/', '/usr/local/', '/usr/lib/', '/boot', '/etc/'):
                    text_variant = text if prefix == '/var/tmp/' else text_variant
                    text_variant = text_variant.replace(prefix, str(base) + prefix)
                text_variant = text_variant.replace('export PATH=/usr/bin:/bin', 'export PATH="' + str(base / 'bin') + ':/usr/bin:/bin"')
                # All absolute system paths above point into this fixture; the
                # test process itself deliberately stays unprivileged.
                text_variant = text_variant.replace('(( EUID == 0 )) || exit 1', ': # simulated root guard')
                result = subprocess.run(['bash', '-c', text_variant], env=dict(os.environ, FAKE_ROOT=str(base)), capture_output=True, text=True)
                self.assertEqual(result.returncode, int(fail), result.stdout + result.stderr)
                self.assertEqual((base / 'var/lib/callas-os/kernel-check-failed').exists(), fail)
                self.assertIn('610.57.04', (base / 'recorded.log').read_text())

if __name__ == '__main__':
    unittest.main()
