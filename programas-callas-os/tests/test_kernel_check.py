"""Real shell/file regression checks; DKMS, pacman and boot tools are simulated."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

UPDATER = Path(__file__).resolve().parents[1] / 'atualizador'

class KernelCheckTests(unittest.TestCase):
    def fixture(self, root, *, failure='', nvidia=True):
        for path in ('boot/grub', 'usr/lib/modules/installed-main', 'usr/lib/modules/installed-lts',
                     'etc', 'var/tmp', 'var/lib/callas-os', 'usr/local/libexec', 'bin'):
            (root/path).mkdir(parents=True, exist_ok=True)
        if nvidia: (root/'etc/callas-nvidia-version').write_text('610.57.04\n')
        for folder, package in (('installed-main', 'linux'), ('installed-lts', 'linux-lts')):
            (root/'usr/lib/modules'/folder/'pkgbase').write_text(package)
            (root/'usr/lib/modules'/folder/'vmlinuz').write_text('kernel')
            (root/'boot'/('vmlinuz-'+package)).write_text('kernel')
            (root/'boot'/('initramfs-'+package+'.img')).write_text('initramfs')
        (root/'boot/grub/grub.cfg').write_text('menuentry Callas\nlinux /vmlinuz-linux root=UUID=test\nlinux /vmlinuz-linux-lts root=UUID=test\n')
        commands = {
            'uname': 'echo iso-kernel-without-headers',
            'mountpoint': 'exit 1' if failure=='mount' else 'exit 0',
            'pacman': 'exit 1' if failure=='packages' else 'exit 0',
            'dkms': '''printf '%s\n' "$*" >> "$FAKE_ROOT/dkms-calls"
[[ $1 == autoinstall && ${2:-} == -k && ${3:-} == installed-* ]] || {
  echo "Missing headers for running $(uname -r)" >&2; exit 1;
}
'''+('exit 1' if failure=='dkms' else 'exit 0'),
            'modinfo': 'exit 1' if failure=='module' else 'exit 0',
            'mkinitcpio': 'exit 1' if failure=='initramfs' else 'exit 0',
            'lsinitcpio': '''case "$*" in
*linux-lts.img*) echo 'usr/lib/modules/installed-lts/kernel/module.ko' ;;
*) echo 'usr/lib/modules/installed-main/kernel/module.ko' ;;
esac''',
            'grub-script-check': 'exit 1' if failure=='grub-syntax' else 'exit 0',
            'grub-mkconfig': '''while [[ $# -gt 0 ]]; do
if [[ $1 == -o ]]; then
  cp "$FAKE_ROOT/boot/grub/grub.cfg" "$2"
  [[ ${BAD_GRUB:-} != yes ]] || sed -i '/vmlinuz-linux root/d' "$2"
  exit 0
fi
shift
done''',
        }
        for name, body in commands.items():
            path=root/'bin'/name; path.write_text('#!/bin/bash\n'+body+'\n'); path.chmod(0o755)
        logger=root/'usr/local/libexec/callas-logs'
        logger.write_text('#!/bin/bash\ncat >> "$FAKE_ROOT/recorded.log"\n'+('exit 1\n' if failure=='logger' else ''))
        logger.chmod(0o755)
        source=(UPDATER/'callas-kernel-check.sh').read_text()
        for prefix in ('/var/tmp/', '/var/lib/', '/usr/local/', '/usr/lib/', '/boot', '/etc/'):
            source=source.replace(prefix, str(root)+prefix)
        source=source.replace('export PATH=/usr/bin:/bin', 'export PATH="'+str(root/'bin')+':/usr/bin:/bin"')
        source=source.replace('(( EUID == 0 )) || exit 1', ': # fixture remains unprivileged')
        return source

    def run_check(self, root, source, **extra):
        return subprocess.run(['bash','-c',source], env=dict(os.environ, FAKE_ROOT=str(root), **extra),
                              capture_output=True,text=True,timeout=10)

    def test_iso_kernel_is_never_used_for_dkms(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); source=self.fixture(root)
            broken=self.run_check(root,source.replace('dkms autoinstall -k "$release"','dkms autoinstall'))
            self.assertNotEqual(broken.returncode,0)
            self.assertIn('Missing headers for running iso-kernel-without-headers',broken.stdout)
            (root/'dkms-calls').unlink()
            fixed=self.run_check(root,source)
            self.assertEqual(fixed.returncode,0,fixed.stdout+fixed.stderr)
            self.assertEqual((root/'dkms-calls').read_text().splitlines(),
                             ['autoinstall -k installed-main','autoinstall -k installed-lts'])
            self.assertFalse((root/'var/lib/callas-os/kernel-check-failed').exists())

    def test_required_failures_keep_specific_diagnostic_and_last_log(self):
        cases={'mount':'/boot não está montado','packages':'headers obrigatório ausente',
               'dkms':'DKMS não conseguiu','module':'Módulo NVIDIA ausente',
               'initramfs':'Falha ao gerar initramfs','grub-syntax':'Sintaxe inválida',
               'logger':'Kernels padrão e LTS'}
        for failure, message in cases.items():
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temp:
                root=Path(temp); result=self.run_check(root,self.fixture(root,failure=failure))
                self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn(message,result.stdout)
                self.assertTrue((root/'var/lib/callas-os/kernel-check-failed').exists())
                last=root/'var/lib/callas-os/kernel-check-last.log'
                self.assertIn(message,last.read_text())
                self.assertEqual(last.stat().st_mode & 0o777,0o600)
                if failure=='mount': self.assertFalse((root/'dkms-calls').exists())

    def test_lts_entry_cannot_hide_missing_standard_kernel_and_grub_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); source=self.fixture(root,nvidia=False)
            before=(root/'boot/grub/grub.cfg').read_bytes()
            result=self.run_check(root,source,BAD_GRUB='yes')
            self.assertNotEqual(result.returncode,0)
            self.assertIn('configuração anterior preservada',result.stdout)
            self.assertEqual((root/'boot/grub/grub.cfg').read_bytes(),before)

    def test_unexpected_exit_still_publishes_log_and_marks_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); source=self.fixture(root)
            source=source.replace('  mkinitcpio -P || falha', '  false\n  mkinitcpio -P || falha')
            result=self.run_check(root,source)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('checagem de kernel interrompida',result.stdout)
            self.assertIn('checagem de kernel interrompida',(root/'recorded.log').read_text())
            self.assertTrue((root/'var/lib/callas-os/kernel-check-failed').exists())
            self.assertEqual(list((root/'var/tmp').iterdir()),[])

    def test_missing_kernel_or_image_cannot_report_success(self):
        for missing in ('usr/lib/modules/installed-main/pkgbase','boot/vmlinuz-linux-lts','boot/initramfs-linux.img'):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as temp:
                root=Path(temp); source=self.fixture(root)
                (root/missing).unlink()
                result=self.run_check(root,source)
                self.assertNotEqual(result.returncode,0)
                self.assertIn('ERRO:',result.stdout)
                self.assertNotIn('boot verificados.',result.stdout)

    def test_verify_only_rejects_stale_kernel_and_initramfs(self):
        for stale in ('vmlinuz', 'initramfs'):
            with self.subTest(stale=stale), tempfile.TemporaryDirectory() as temp:
                root=Path(temp); source=self.fixture(root)
                if stale=='vmlinuz':
                    (root/'boot/vmlinuz-linux').write_text('previous kernel')
                else:
                    (root/'bin/lsinitcpio').write_text('#!/bin/bash\necho usr/lib/modules/previous/kernel/module.ko\n')
                result=self.run_check(root,'set -- --verify-only\n'+source)
                self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertTrue((root/'var/lib/callas-os/kernel-check-failed').exists())

    def test_general_update_targets_installed_kernels_after_pacman(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); self.fixture(root)
            text=(UPDATER/'put-update.sh').read_text()
            fn=text[text.index('atualizar_arch() {'):text.index('\natualizar_aur()')]
            fn=fn.replace('/usr/lib/modules/',str(root)+'/usr/lib/modules/').replace('/etc/callas-nvidia-version',str(root)+'/etc/callas-nvidia-version')
            code='''mountpoint() { return 0; }
pacman-conf() { printf '%s\n' "$FAKE_ROOT"; }
pacman() { return 0; }
'''+fn+'\natualizar_arch manual\n'
            result=self.run_check(root,'export PATH="'+str(root/'bin')+':/usr/bin:/bin"\nparu_conf=/missing\n'+code)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual((root/'dkms-calls').read_text().splitlines(),
                             ['autoinstall -k installed-lts','autoinstall -k installed-main'])

    def test_installer_and_update_preserve_grub_until_both_kernels_and_syntax_pass(self):
        installer=(UPDATER.parents[1]/'instalar-arch.sh').read_text()
        helper=installer.split("<<'CALLAS_GRUB_CUSTOM'\n",1)[1].split('\nCALLAS_GRUB_CUSTOM',1)[0]
        updater=(UPDATER/'callas-config-update.sh').read_text()
        update='grub_changed=1\n'+updater[updater.index('if (( grub_changed )); then'):updater.index('# Plymouth do Callas OS.')]
        for program, source in (('installer',helper),('update',update)):
            for failure in ('','grub-syntax','missing-main'):
                with self.subTest(program=program,failure=failure), tempfile.TemporaryDirectory() as temp:
                    root=Path(temp); self.fixture(root,failure=failure)
                    (root/'etc/grub.d').mkdir()
                    (root/'etc/grub.d/09_callas').write_text('#!/bin/sh\n')
                    (root/'etc/grub.d/09_callas').chmod(0o755)
                    config=root/'boot/grub/grub.cfg'
                    config.write_text("menuentry 'Callas OS Linux' { linux /vmlinuz-linux root=x }\n"
                                      "menuentry 'Callas OS (kernel LTS - recuperação)' { linux /vmlinuz-linux-lts root=x }\n"
                                      "menuentry 'Callas OS (diagnóstico sem splash)' {}\n")
                    previous=config.read_bytes()
                    variant=source.replace('/boot',str(root)+'/boot').replace('/etc/',str(root)+'/etc/')
                    code='set -euo pipefail\nexport PATH="'+str(root/'bin')+':/usr/bin:/bin"\nerro() { echo "$*" >&2; exit 1; }\n'+variant
                    result=self.run_check(root,code,BAD_GRUB='yes' if failure=='missing-main' else '')
                    self.assertEqual(result.returncode==0,not failure,result.stdout+result.stderr)
                    self.assertEqual(config.read_bytes(),previous)

if __name__=='__main__': unittest.main()
