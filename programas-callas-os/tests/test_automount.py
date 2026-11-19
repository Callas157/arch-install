"""Exercise disk discovery with lsblk/findmnt fixtures, without mounting devices."""
import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


HELPER = Path(__file__).resolve().parents[1] / 'atualizador/callas-automount.py'
spec = importlib.util.spec_from_file_location('callas_automount', HELPER)
automount = importlib.util.module_from_spec(spec)
spec.loader.exec_module(automount)

LINUX_DATA = '0fc63daf-8483-4772-8e79-3d69d8477de4'
WINDOWS_DATA = 'ebd0a0a2-b9e5-4433-87c0-68b6b72699c7'
WINDOWS_RECOVERY = 'de94bba4-06d1-4d40-a16a-bfd50179d6ac'
EFI = 'c12a7328-f81f-11d2-ba4b-00a0c93ec93b'
ROOT_UUID = '0b93809a-2b93-4ed9-9f4e-a306b214efe8'
NTFS_UUID = '71F0CBD05A9D0D42'


def partition(name, fstype, uuid, parttype, **properties):
    return {'name': '/dev/' + name, 'type': 'part', 'ro': False, 'rm': False,
            'hotplug': False, 'fstype': fstype, 'uuid': uuid, 'parttype': parttype,
            'partflags': None, 'mountpoints': [], **properties}


def disk(name, *children, **properties):
    return {'name': '/dev/' + name, 'type': 'disk', 'tran': 'sata', 'ro': False,
            'rm': False, 'hotplug': False, 'fstype': None, 'uuid': None,
            'parttype': None, 'mountpoints': [], 'children': list(children), **properties}


class PlanMountTests(unittest.TestCase):
    def setUp(self):
        self.root = '/dev/nvme0n1p2'
        self.system = disk(
            'nvme0n1',
            partition('nvme0n1p1', 'vfat', '9921-6A78', EFI, mountpoints=['/boot']),
            partition('nvme0n1p2', 'ext4', ROOT_UUID, LINUX_DATA, mountpoints=['/']),
            tran='nvme',
        )
        self.secondary = disk('sda', partition('sda1', 'ntfs', NTFS_UUID, '0x7'))
        self.target = '/mnt/callas-' + NTFS_UUID.lower()

    def plan(self, *disks, configured=(), available_target=lambda _target, _mounted: True):
        return automount.plan_mounts([self.system, *disks], self.root, list(configured),
                                     'ana', 1507, 1608, available_target)

    def test_ntfs_uses_detected_uuid_current_account_and_bounded_boot_wait(self):
        [(target, row)] = self.plan(self.secondary)
        source, mountpoint, fs_type, options, dump, passno = row.split()
        self.assertEqual((target, source, mountpoint, fs_type, dump, passno),
                         (self.target, 'UUID=' + NTFS_UUID, self.target, 'ntfs3', '0', '0'))
        self.assertTrue({'nodev', 'nosuid', 'uid=1507', 'gid=1608', 'nofail'}.issubset(options.split(',')))
        self.assertRegex(options, r'(^|,)x-systemd\.device-timeout=[1-9][0-9]*s?(,|$)')

    def test_existing_udisks_path_is_preserved_and_spaces_are_escaped(self):
        active_path = '/run/media/ana/Jogos antigos'
        self.secondary['children'][0]['mountpoints'] = [active_path]
        targets = []

        def available(target, mounted):
            targets.append((target, mounted))
            return True

        [(target, row)] = self.plan(self.secondary, available_target=available)
        self.assertEqual(target, active_path)
        self.assertEqual(row.split()[1], r'/run/media/ana/Jogos\040antigos')
        self.assertEqual(targets, [(active_path, True)])

    def test_existing_fstab_source_alias_and_target_collision_are_preserved(self):
        variants = (
            {'source': 'LABEL=Jogos', 'sources': ['/dev/sda1'], 'target': '/srv/jogos'},
            {'source': 'UUID=' + NTFS_UUID, 'sources': [], 'target': '/srv/jogos'},
            {'source': 'UUID=4EA9AEE988EE7741', 'sources': [], 'target': self.target},
        )
        for entry in variants:
            with self.subTest(entry=entry):
                self.assertEqual(self.plan(self.secondary, configured=[entry]), [])
        self.assertEqual(self.plan(self.secondary, available_target=lambda _target, _mounted: False), [])

    def test_system_disk_and_volume_mounted_elsewhere_are_preserved(self):
        self.system['children'].append(partition('nvme0n1p3', 'ntfs', NTFS_UUID, WINDOWS_DATA))
        self.assertEqual(self.plan(), [])
        separate_boot_disk = disk('sdb',
                                  partition('sdb1', 'vfat', 'B977-DAAA', EFI, mountpoints=['/efi']),
                                  partition('sdb2', 'ntfs', NTFS_UUID, WINDOWS_DATA))
        self.assertEqual(self.plan(separate_boot_disk), [])
        active_partition = self.secondary['children'][0]
        for path in ('/mnt/meus-jogos', '/run/media/outra-pessoa/Jogos', '/home'):
            with self.subTest(path=path):
                active_partition['mountpoints'] = [path]
                self.assertEqual(self.plan(self.secondary), [])

    def test_removable_and_unclassified_drives_are_not_selected(self):
        for properties in ({'tran': 'usb'}, {'tran': None}, {'rm': True},
                           {'hotplug': True}, {'ro': True}):
            with self.subTest(properties=properties):
                external = disk('sda', partition('sda1', 'ntfs', NTFS_UUID, '0x7'), **properties)
                self.assertEqual(self.plan(external), [])

    def test_unknown_root_ancestry_disables_discovery(self):
        for source in ('overlay', '/dev/mapper/other', None):
            with self.subTest(source=source):
                self.assertEqual(automount.plan_mounts([self.secondary], source, [], 'ana',
                                                       1507, 1608, lambda *_: True), [])

    def test_unsupported_and_ambiguous_partitions_are_not_selected(self):
        for properties in ({'fstype': 'crypto_LUKS'}, {'parttype': WINDOWS_RECOVERY},
                           {'partflags': '0x80'}, {'children': [{'type': 'crypt'}]},
                           {'ro': True}, {'uuid': 'invalid value\nUUID=other'}):
            with self.subTest(properties=properties):
                candidate = dict(self.secondary['children'][0], **properties)
                self.assertEqual(self.plan(disk('sda', candidate)), [])
        clone = disk('sdb', partition('sdb1', 'ntfs', NTFS_UUID, WINDOWS_DATA))
        self.assertEqual(self.plan(self.secondary, clone), [])

    def test_ext4_keeps_native_permissions_and_exfat_uses_current_account(self):
        ext4_uuid = '1fed69a4-6258-49ca-8590-66dd1bc51ec5'
        data = disk('sda',
                    partition('sda1', 'ext4', ext4_uuid, LINUX_DATA),
                    partition('sda2', 'exfat', '6D42-EF48', WINDOWS_DATA))
        entries = {row.split()[2]: row.split()[3].split(',') for _, row in self.plan(data)}
        self.assertEqual(set(entries), {'ext4', 'exfat'})
        self.assertFalse(any(option.startswith(('uid=', 'gid=', 'umask=')) for option in entries['ext4']))
        self.assertTrue({'uid=1507', 'gid=1608'}.issubset(entries['exfat']))


class ApplyMountTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.fstab = self.directory / 'fstab'
        self.target = self.directory / 'volume'
        self.previous = b'# locally managed\nUUID=' + ROOT_UUID.encode() + b' / ext4 defaults 0 1'
        self.fstab.write_bytes(self.previous)
        self.fstab.chmod(0o640)
        self.root = '/dev/nvme0n1p2'
        self.disks = [disk('nvme0n1', partition('nvme0n1p2', 'ext4', ROOT_UUID, LINUX_DATA), tran='nvme'),
                      disk('sda', partition('sda1', 'ntfs', NTFS_UUID, '0x7'))]
        self.verified = []
        real_lstat = Path.lstat
        real_plan = automount.plan_mounts

        def root_owned(path, *args, **kwargs):
            metadata = real_lstat(path, *args, **kwargs)
            if path != self.fstab:
                return metadata
            # Keep the real inode, mode and timestamps to exercise the change check.
            fields = (*metadata[:4], 0, *metadata[5:])
            times = {name: getattr(metadata, name) for name in ('st_atime_ns', 'st_ctime_ns', 'st_mtime_ns')}
            return os.stat_result(fields, times)

        def plan(*args):
            # Use real discovery. Redirect only its destination to the fixture.
            return [(str(self.target), line.replace(target, str(self.target)))
                    for target, line in real_plan(*args)]

        self.enterContext(patch.object(automount, 'FSTAB', self.fstab))
        self.enterContext(patch.object(Path, 'lstat', root_owned))
        self.enterContext(patch.object(automount.os, 'geteuid', return_value=0))
        self.enterContext(patch.object(automount.os, 'fchown'))
        self.enterContext(patch.object(automount.pwd, 'getpwnam', return_value=SimpleNamespace(pw_uid=1507, pw_gid=1608)))
        self.enterContext(patch.object(automount, 'inventory', side_effect=self.inventory))
        self.enterContext(patch.object(automount, 'available_target', return_value=True))
        self.enterContext(patch.object(automount, 'plan_mounts', side_effect=plan))
        self.verify = self.enterContext(patch.object(automount.subprocess, 'run', side_effect=self.verify_fstab))

    def inventory(self, executable, *options):
        if executable == 'lsblk':
            return {'blockdevices': self.disks}
        if executable == 'findmnt' and '--kernel' in options:
            return {'filesystems': [{'source': self.root, 'target': '/'}]}
        if executable == 'findmnt' and '--fstab' in options:
            return {'filesystems': [dict(zip(('source', 'target'), line.split()[:2]))
                                    for line in self.fstab.read_text().splitlines()
                                    if not line.startswith('#')]}
        self.fail(f'Unexpected inventory command: {executable} {options}')

    def verify_fstab(self, command, *, check):
        self.assertEqual(command[:3], ['findmnt', '--verify', '--tab-file'])
        self.assertTrue(check)
        self.assertTrue(self.target.is_dir())
        staged = Path(command[3])
        self.assertEqual(staged.parent, self.fstab.parent)
        self.assertNotEqual(staged, self.fstab)
        self.verified.append(staged.read_bytes())
        self.assertEqual(self.fstab.read_bytes(), self.previous)

    def test_validates_atomically_and_preserves_previous_lines_mode_and_repeat(self):
        before = self.fstab.stat().st_ino
        automount.apply('ana')
        after = self.fstab.read_bytes()
        self.assertEqual(self.verified, [after])
        self.assertTrue(after.startswith(self.previous + b'\n'))
        self.assertIn(b'UUID=' + NTFS_UUID.encode() + b'\t' + bytes(self.target), after)
        self.assertNotEqual(self.fstab.stat().st_ino, before)
        self.assertEqual(stat.S_IMODE(self.fstab.stat().st_mode), 0o640)
        self.assertTrue(self.target.is_dir())
        automount.apply('ana')
        self.assertEqual(self.fstab.read_bytes(), after)
        self.verify.assert_called_once()
        self.assertCountEqual(self.directory.iterdir(), [self.fstab, self.target])

    def test_invalid_candidate_leaves_existing_fstab_and_files_intact(self):
        before = self.fstab.stat().st_ino

        def fail_verification(command, *, check):
            self.verify_fstab(command, check=check)
            raise subprocess.CalledProcessError(1, command)

        self.verify.side_effect = fail_verification
        with self.assertRaises(subprocess.CalledProcessError):
            automount.apply('ana')
        self.assertEqual(self.fstab.read_bytes(), self.previous)
        self.assertEqual(self.fstab.stat().st_ino, before)
        self.assertCountEqual(self.directory.iterdir(), [self.fstab])

    def test_concurrent_edit_after_validation_is_preserved(self):
        edited = self.previous + b'\n# another administrator\n'

        def edit_during_verification(command, *, check):
            self.verify_fstab(command, check=check)
            self.fstab.write_bytes(edited)

        self.verify.side_effect = edit_during_verification
        with self.assertRaises(RuntimeError):
            automount.apply('ana')
        self.assertEqual(self.fstab.read_bytes(), edited)
        self.assertCountEqual(self.directory.iterdir(), [self.fstab])


if __name__ == '__main__':
    unittest.main()
