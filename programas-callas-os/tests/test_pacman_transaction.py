"""Opt-in real libalpm transactions against synthetic packages and a private DB.

Set CALLAS_TEST_PACMAN to a sandboxed pacman executable/wrapper. Packages only
contain files under a TemporaryDirectory, never /boot or /usr/lib/modules.
This validates transaction hooks, not an Arch installation or NVIDIA/boot.
"""
import hashlib
import importlib.util
import io
import os
import shutil
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

UP = Path(__file__).resolve().parents[1] / 'atualizador'
spec = importlib.util.spec_from_file_location('real_transaction_native', UP / 'callas-native.py')
native = importlib.util.module_from_spec(spec); spec.loader.exec_module(native)
PACMAN = os.environ.get('CALLAS_TEST_PACMAN')


@unittest.skipUnless(PACMAN, 'set CALLAS_TEST_PACMAN for isolated real libalpm transactions')
class RealPacmanTests(unittest.TestCase):
    def test_kernel_dependency_aborts_whole_transaction_and_plain_app_succeeds(self):
        with tempfile.TemporaryDirectory(prefix='callas-pacman-test-') as temp:
            root = Path(temp)
            for name in ('db/sync', 'cache', 'files', 'repository'):
                (root / name).mkdir(parents=True)
            config = root / 'pacman.conf'
            config.write_text('[options]\nArchitecture = x86_64\nSigLevel = Never\n[fixture]\nServer = file://' + str(root / 'repository') + '\n')
            common = [PACMAN, '--config', str(config), '--dbpath', str(root / 'db'),
                      '--cachedir', str(root / 'cache'), '--logfile', str(root / 'pacman.log')]

            def package(name, version, dependency=None, replacement=None):
                path = root / 'repository' / (name + '-' + version + '-x86_64.pkg.tar.gz')
                metadata = f'pkgname = {name}\npkgbase = {name}\npkgver = {version}\npkgdesc = Synthetic test\narch = x86_64\nsize = 4\n'
                if dependency:
                    metadata += 'depend = ' + dependency + '\n'
                if replacement:
                    metadata += 'conflict = ' + replacement + '\nprovides = ' + replacement + '\nreplaces = ' + replacement + '\n'
                with tarfile.open(path, 'w:gz') as archive:
                    for filename, content in {'.PKGINFO': metadata, str(root / 'files' / name).lstrip('/'): version}.items():
                        data = content.encode(); entry = tarfile.TarInfo(filename)
                        entry.size = len(data); entry.mode = 0o644
                        archive.addfile(entry, io.BytesIO(data))
                shutil.copyfile(path, root / 'cache' / path.name)
                return path

            def invoke(argv):
                # Use the production temporary hook and arguments, only replacing
                # the executable/database/cache/log with sandbox fixture paths.
                return subprocess.run(common + argv[1:], capture_output=True, text=True)

            old = package('linux', '7.2.15-1')
            initial = subprocess.run(common + ['-U', '--noconfirm', str(old)], capture_output=True, text=True)
            self.assertEqual(initial.returncode, 0, initial.stdout + initial.stderr)
            candidate = package('linux', '7.3.4-1')

            def repository(app_dependency):
                app = package('haruna', '1-1', app_dependency)
                with tarfile.open(root / 'db/sync/fixture.db', 'w:gz') as archive:
                    for name, version, path, dependency in [('linux', '7.3.4-1', candidate, None), ('haruna', '1-1', app, app_dependency)]:
                        fields = {'FILENAME': path.name, 'NAME': name, 'VERSION': version, 'DESC': 'Synthetic test',
                                  'ARCH': 'x86_64', 'CSIZE': str(path.stat().st_size), 'ISIZE': '4',
                                  'SHA256SUM': hashlib.sha256(path.read_bytes()).hexdigest()}
                        if dependency: fields['DEPENDS'] = dependency
                        data = ''.join('%' + key + '%\n' + value + '\n\n' for key, value in fields.items()).encode()
                        entry = tarfile.TarInfo(name + '-' + version + '/desc'); entry.size = len(data)
                        archive.addfile(entry, io.BytesIO(data))

            repository('linux>=7.3.4')
            result = native.guarded_transaction(['-S', '--needed', '--noconfirm', 'haruna'], runner=invoke)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('Esta transação exige Atualizar geral: linux', result.stdout + result.stderr)
            self.assertEqual((root / 'files/linux').read_text(), '7.2.15-1')
            self.assertFalse((root / 'files/haruna').exists())
            # The same hook also blocks a directly supplied kernel archive.
            blocked = native.guarded_transaction(['-U', '--noconfirm', str(candidate)], runner=invoke)
            self.assertNotEqual(blocked.returncode, 0)
            self.assertEqual((root / 'files/linux').read_text(), '7.2.15-1')
            replacement = package('unrelated-app', '1-1', replacement='linux')
            def confirm_replacement(argv):
                return subprocess.run(common + argv[1:], input='y\ny\n', capture_output=True, text=True)
            removed = native.guarded_transaction(['-U', str(replacement)], runner=confirm_replacement)
            self.assertNotEqual(removed.returncode, 0, removed.stdout + removed.stderr)
            self.assertIn('Esta transação exige Atualizar geral: linux', removed.stdout + removed.stderr)
            self.assertEqual((root / 'files/linux').read_text(), '7.2.15-1')
            self.assertFalse((root / 'files/unrelated-app').exists())
            repository(None)
            result = native.guarded_transaction(['-S', '--needed', '--noconfirm', 'haruna'], runner=invoke)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((root / 'files/haruna').read_text(), '1-1')
            self.assertEqual((root / 'files/linux').read_text(), '7.2.15-1')
