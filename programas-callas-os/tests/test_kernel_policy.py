"""PreTransaction policy: no installed kernel replacement without prior build."""
import importlib.util
import io
import os
from pathlib import Path
import tarfile
import tempfile
import types
import unittest
from unittest.mock import patch

FILE = Path(__file__).resolve().parents[1] / 'atualizador/callas-kernel-policy.py'


class KernelPolicyTests(unittest.TestCase):
    def load(self):
        self.assertTrue(FILE.exists(), 'Kernel PreTransaction policy is missing')
        spec = importlib.util.spec_from_file_location('kernel_policy', FILE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_non_general_modes_cannot_replace_either_kernel_or_headers(self):
        policy = self.load()
        for target in ('linux', 'linux-lts', 'linux-headers', 'linux-lts-headers', 'linux-zen'):
            for context in ('', 'apps', 'config', 'discord'):
                with self.subTest(target=target, context=context), patch.object(policy, 'verify_candidate') as build:
                    with self.assertRaises(RuntimeError):
                        policy.guard([target], context, '610.57.04')
                    build.assert_not_called()

    def test_general_never_changes_pinned_driver(self):
        policy = self.load()
        for target in ('nvidia-utils', 'nvidia-open-dkms', 'lib32-nvidia-utils', 'nvidia-settings'):
            with self.subTest(target=target), self.assertRaises(RuntimeError):
                policy.guard([target], 'general', '610.57.04')

    def test_failed_candidate_build_aborts_general_transaction(self):
        policy = self.load()
        with patch.object(policy, 'verify_candidate', side_effect=RuntimeError('compile failed')):
            with self.assertRaisesRegex(RuntimeError, 'compile failed'):
                policy.guard(['linux', 'linux-headers'], 'general', '610.57.04')

    def test_both_candidate_pairs_must_build_before_allowing_transaction(self):
        policy = self.load()
        with patch.object(policy, 'verify_candidate') as build:
            policy.guard(['linux', 'linux-headers', 'linux-lts', 'linux-lts-headers'], 'general', '610.57.04')
            self.assertEqual([call.args[:2] for call in build.call_args_list],
                             [('linux', '610.57.04'), ('linux-lts', '610.57.04')])

    def test_apps_do_not_trigger_kernel_compilation(self):
        policy = self.load()
        with patch.object(policy, 'verify_candidate') as build:
            policy.guard(['gnome-boxes', 'usb_modeswitch', 'discord'], '', '610.57.04')
            build.assert_not_called()

    def test_toolchain_change_in_same_transaction_cannot_invalidate_preflight(self):
        policy = self.load()
        for package in ('gcc', 'gcc-libs', 'binutils', 'glibc', 'dkms', 'make', 'libelf', 'clang', 'llvm-libs'):
            with self.subTest(package=package), patch.object(policy, 'verify_candidate') as build:
                with self.assertRaises(RuntimeError):
                    policy.guard(['linux', 'linux-headers', package], 'general', '610.57.04')
                build.assert_not_called()

    def test_all_four_correct_modules_pass_validation(self):
        policy = self.load()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in ('nvidia', 'nvidia-modeset', 'nvidia-uvm', 'nvidia-drm'):
                (root/(name+'.ko')).write_text('fixture binary')
            with patch.object(policy, 'command', side_effect=lambda args: '610.57.04' if args[2]=='version' else 'candidate-release SMP'):
                policy.verify_modules(root, 'candidate-release', '610.57.04')

    def test_header_only_or_kernel_only_transaction_is_not_approved(self):
        policy = self.load()
        for target in ('linux', 'linux-headers', 'linux-lts', 'linux-lts-headers'):
            with self.subTest(target=target), patch.object(policy, 'verify_candidate') as build:
                with self.assertRaises(RuntimeError):
                    policy.guard([target], 'general', '610.57.04')
                build.assert_not_called()

    def test_metadata_queries_force_c_locale_on_portuguese_system(self):
        policy = self.load()
        with patch.dict(os.environ, {'LC_ALL':'pt_BR.UTF-8'}), patch.object(policy.subprocess, 'run',
                return_value=types.SimpleNamespace(returncode=0,stdout='Version : 7.2.15.arch1-1\n',stderr='')) as run:
            self.assertEqual(policy.repository_version('linux'), '7.2.15.arch1-1')
            self.assertEqual(run.call_args.kwargs['env']['LC_ALL'], 'C')

    def test_candidate_pipeline_uses_extracted_headers_and_private_dkms_tree(self):
        policy=self.load()
        for failed in (False, True):
            with self.subTest(namespace_failure=failed), tempfile.TemporaryDirectory() as temp:
                root=Path(temp);cache=root/'cache';cache.mkdir();work=root/'work';work.mkdir()
                sources=root/'sources';(sources/'nvidia-610.57.04').mkdir(parents=True)
                (sources/'nvidia-610.57.04/dkms.conf').write_text('fixture source')
                installed=root/'working-kernel';installed.write_bytes(b'working kernel untouched')
                for package, files in {
                    'linux':{'usr/lib/modules/candidate/pkgbase':'linux\n','usr/lib/modules/candidate/vmlinuz':'new kernel'},
                    'linux-headers':{'usr/lib/modules/candidate/build/Makefile':'fixture headers'},
                }.items():
                    with tarfile.open(cache/(package+'-new.pkg.tar.zst'),'w') as tar:
                        for path, content in files.items():
                            data=content.encode();info=tarfile.TarInfo(path);info.size=len(data)
                            tar.addfile(info,io.BytesIO(data))
                def external(argv):
                    args=[str(x) for x in argv]
                    if args[:2]==['/usr/bin/pacman','-Si']:return 'Version : new\n'
                    if args[:2]==['/usr/bin/pacman','-Q']:return 'nvidia-open-dkms 610.57.04-1'
                    if args[0]=='/usr/bin/pacman-conf':return str(cache)
                    if args[:2]==['/usr/bin/pacman','-Qp']:
                        return ('linux-headers' if Path(args[2]).name.startswith('linux-headers-') else 'linux')+' new'
                    if args[0]=='/usr/bin/bsdtar':
                        with tarfile.open(args[2]) as tar:tar.extractall(args[4],filter='data')
                        return ''
                    if args[0]=='/usr/bin/unshare':
                        if failed:raise RuntimeError('mount namespace unavailable')
                        self.assertIn('private',args)
                        recipe=args[args.index('-c')+1]
                        self.assertIn('dkms build',recipe)
                        self.assertNotIn('dkms install',recipe)
                        tree=Path(args[-1]);self.assertTrue(tree.is_relative_to(work))
                        self.assertTrue((Path(args[-4])/'candidate/build/Makefile').is_file())
                        for name in ('nvidia','nvidia-modeset','nvidia-uvm','nvidia-drm'):
                            (tree/(name+'.ko')).write_text('610.57.04 candidate')
                        return 'candidate build complete'
                    if args[0]=='/usr/bin/modinfo':
                        return Path(args[-1]).read_text().split()[0 if args[2]=='version' else 1]
                    raise AssertionError('unexpected external command '+str(args))
                with patch.object(policy,'SOURCE_ROOT',sources), patch.object(policy,'command',side_effect=external):
                    if failed:
                        with self.assertRaisesRegex(RuntimeError,'namespace unavailable'):
                            policy.verify_candidate('linux','610.57.04',work)
                    else:
                        policy.verify_candidate('linux','610.57.04',work)
                self.assertEqual(installed.read_bytes(),b'working kernel untouched')

    def test_partial_build_or_wrong_driver_or_vermagic_is_rejected(self):
        policy = self.load()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in ('nvidia', 'nvidia-modeset', 'nvidia-uvm', 'nvidia-drm'):
                (root/(name+'.ko')).write_text('fixture binary')
            for wrong in ('version', 'vermagic', 'missing'):
                with self.subTest(wrong=wrong):
                    def command(argv):
                        if argv[2]=='version': return '620.0' if wrong=='version' else '610.57.04'
                        return 'other-release SMP' if wrong=='vermagic' else 'candidate-release SMP'
                    if wrong=='missing': (root/'nvidia-drm.ko').unlink()
                    with patch.object(policy, 'command', side_effect=command), self.assertRaises(RuntimeError):
                        policy.verify_modules(root, 'candidate-release', '610.57.04')

    def test_archive_version_must_match_candidate_not_old_cache(self):
        policy = self.load()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'linux-old.pkg.tar.zst').write_text('old cached archive')
            with patch.object(policy, 'command', return_value='linux old'):
                with self.assertRaises(RuntimeError):
                    policy.archive('linux', 'new', [root])


if __name__ == '__main__': unittest.main()
