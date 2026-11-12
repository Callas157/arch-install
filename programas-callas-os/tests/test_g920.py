"""Real provisioning shell/file operations; package manager and udev are simulated."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
UP = ROOT / 'programas-callas-os/atualizador'
SECURITY = (UP / 'callas-security.sh').read_text()


class G920Tests(unittest.TestCase):
    def test_missing_modeswitch_is_installed_without_prompts_and_errors_propagate(self):
        start = SECURITY.index('  if [[ ${2:-} != --installation ]]; then')
        block = SECURITY[start:SECURITY.index('  nvidia_after=')]
        for query, transaction, expected in ((0, 0, 0), (1, 0, 0), (2, 0, 1), (1, 23, 23)):
            with self.subTest(query=query, transaction=transaction), tempfile.TemporaryDirectory() as temp:
                code = '''set -Eeuo pipefail
pacman() {
  if [[ $1 == -Qq ]]; then
    [[ $2 != usb_modeswitch ]] || return "$QUERY_STATUS"
    return 0
  fi
  printf '%s\\n' "$*" >> "$TEST_ROOT/transactions"
  return "$TRANSACTION_STATUS"
}
mountpoint() { return 0; }
provision() {
''' + block + '}\nprovision fixture --config-update\n'
                result = subprocess.run(['bash', '-c', code], env=dict(os.environ, TEST_ROOT=temp,
                    QUERY_STATUS=str(query), TRANSACTION_STATUS=str(transaction)), capture_output=True, text=True)
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                calls = Path(temp) / 'transactions'
                if query == 1:
                    self.assertEqual(len(calls.read_text().splitlines()), 1)
                    args = shlex.split(calls.read_text())
                    self.assertEqual(args[:3], ['-Syu', '--needed', '--noconfirm'])
                    self.assertEqual(args[-1], 'usb_modeswitch')
                    self.assertIn('--ignore=nvidia-utils,', calls.read_text())
                else:
                    self.assertFalse(calls.exists())

    def test_rule_is_idempotent_preserves_headset_and_skips_reload_inside_chroot(self):
        start = SECURITY.index('  # G920:')
        block = SECURITY[start:SECURITY.index('  cat > /etc/sudoers.d/20-callas-security', start)]
        for chroot in (True, False):
            with self.subTest(chroot=chroot), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                rules = root / 'etc/udev/rules.d'
                rules.mkdir(parents=True)
                headset = rules / '59-callas-logitech-hidraw.rules'
                headset.write_text('existing headset configuration\n')
                code = '''set -Eeuo pipefail
umask 077
systemd-detect-virt() { return "$CHROOT_STATUS"; }
udevadm() { printf '%s\\n' "$*" >> "$TEST_ROOT/reloads"; }
''' + block.replace('/etc/udev/rules.d', str(rules))
                env = dict(os.environ, TEST_ROOT=temp, CHROOT_STATUS='0' if chroot else '1')
                for _ in range(2):
                    result = subprocess.run(['bash', '-c', code], env=env, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                rule = rules / '70-callas-g920.rules'
                self.assertEqual(rule.stat().st_mode & 0o777, 0o644)
                self.assertEqual(headset.read_text(), 'existing headset configuration\n')
                self.assertEqual((root / 'reloads').exists(), not chroot)
                if not chroot:
                    self.assertEqual((root / 'reloads').read_text().splitlines(), ['control --reload-rules'] * 2)
                text = rule.read_text()
                self.assertIn('ATTRS{idVendor}=="046d", ATTRS{idProduct}=="c262"', text)
                self.assertIn('SUBSYSTEM=="input"', text)
                self.assertIn('MODE="0660", TAG+="uaccess"', text)
                self.assertNotIn('RUN', text)
                if shutil.which('udevadm'):
                    checked = subprocess.run(['udevadm', 'verify', str(rule)], capture_output=True, text=True)
                    self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_clean_installation_and_checkpoint_repair_include_g920(self):
        installer = (ROOT / 'instalar-arch.sh').read_text()
        packages = installer.split('pacstrap -K /mnt', 1)[1].split('\ngenfstab', 1)[0]
        self.assertIn('usb_modeswitch', packages.split())
        self.assertIn('callas-security.sh" "$usuario" --installation', installer)
        state = (UP / 'callas-update-state.py').read_text()
        self.assertIn('/etc/udev/rules.d/70-callas-g920.rules', state)


if __name__ == '__main__':
    unittest.main()
