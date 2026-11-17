"""Run the real Update GRUB block using temporary boot files and synthetic commands."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2];UP=ROOT/'programas-callas-os/atualizador'

class LegacyBootIntegrationTests(unittest.TestCase):
    def fixture(self, root, valid=True):
        source=(ROOT/'instalar-arch.sh').read_text()
        entries=source.split("cat > /etc/grub.d/09_callas <<'GRUB_CALLAS'\n",1)[1].split('\nGRUB_CALLAS',1)[0]+'\n'
        entries=entries.replace('initrd /initramfs-','initrd /intel-ucode.img /initramfs-')
        if not valid: entries=entries.replace('    initrd /intel-ucode.img /initramfs-linux-lts.img\n','')
        path=root/'09_callas';path.write_text(entries);path.chmod(0o755)
        grub=root/'boot/grub';grub.mkdir(parents=True)
        (grub/'grub.cfg').write_text('original-working-config\n')
        return path,grub

    def run_block(self, root, entries, grub, fail=False):
        source=(UP/'callas-config-update.sh').read_text()
        block=source.split('# CALLAS_PHASE_BEGIN boot\n',1)[1].split('# Plymouth do Callas OS.',1)[0]+'\nfi\n'
        block=block.replace('/etc/grub.d/09_callas',str(entries)).replace('/boot/grub',str(grub))
        block=block.replace('/boot/.callas-initramfs-pending',str(root/'boot/.callas-initramfs-pending'))
        block=block.replace('/usr/local/libexec/callas-grub-silencioso',str(root/'retired-helper'))
        block=block.replace('/etc/pacman.d/hooks/99-callas-grub-silencioso.hook',str(root/'retired-hook'))
        prelude='''set -Eeuo pipefail
phase_needed() { return 0; }
erro() { echo "$*" >&2; exit 1; }
asset() {
  touch "$FIXTURE_ROOT/assets-touched"
  if [[ -f $2 ]]; then asset_changed=0; else
    printf 'fixture asset\\n' > "$2"; asset_changed=1
  fi
}
grub-mkconfig() { sh "$FIXTURE_ENTRIES" > "$2"; }
grub-script-check() { [[ $FIXTURE_FAIL != 1 ]]; }
'''
        env=dict(os.environ,CALLAS_RELEASE_DIR=str(UP),FIXTURE_ROOT=str(root),FIXTURE_ENTRIES=str(entries),FIXTURE_FAIL='1' if fail else '0')
        return subprocess.run(['bash','-c',prelude+block],env=env,capture_output=True,text=True)

    def test_intel_legacy_entry_upgrade_and_retry_after_grub_validation_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);entries,grub=self.fixture(root);original=entries.read_text()
            result=self.run_block(root,entries,grub,True)
            self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual((grub/'grub.cfg').read_text(),'original-working-config\n')
            self.assertTrue((grub/'.callas-theme-pending').exists())
            for line in original.splitlines():
                if line.strip().startswith(('linux ','initrd ','search ')):self.assertIn(line,entries.read_text())
            result=self.run_block(root,entries,grub)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertFalse((grub/'.callas-theme-pending').exists())
            self.assertIn('initrd /intel-ucode.img /initramfs-linux.img',(grub/'grub.cfg').read_text())
            self.assertEqual((grub/'grub.cfg').read_text().count('source $prefix/themes/callas/loading.cfg'),3)

    def test_quoted_kernel_paths_pass_the_entire_update_boot_block(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);entries,grub=self.fixture(root)
            source=entries.read_text().replace('linux /vmlinuz-linux ', 'linux "/vmlinuz-linux" ')
            source=source.replace('linux /vmlinuz-linux-lts ', 'linux "/vmlinuz-linux-lts" ')
            entries.write_text(source)
            result=self.run_block(root,entries,grub)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('linux "/vmlinuz-linux" ',(grub/'grub.cfg').read_text())

    def test_invalid_entry_fails_before_assets_or_boot_configuration_are_changed(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);entries,grub=self.fixture(root,False);before=entries.read_bytes()
            result=self.run_block(root,entries,grub)
            self.assertNotEqual(result.returncode,0)
            self.assertFalse((root/'assets-touched').exists())
            self.assertEqual(entries.read_bytes(),before)
            self.assertEqual((grub/'grub.cfg').read_text(),'original-working-config\n')

if __name__=='__main__':unittest.main()
