"""Exercise disk discovery with lsblk/findmnt fixtures, without mounting devices."""
import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import call, patch


HELPER = Path(__file__).resolve().parents[1] / 'atualizador/callas-automount.py'
spec = importlib.util.spec_from_file_location('callas_automount', HELPER)
automount = importlib.util.module_from_spec(spec)
spec.loader.exec_module(automount)

LINUX_DATA = '0fc63daf-8483-4772-8e79-3d69d8477de4'
WINDOWS_DATA = 'ebd0a0a2-b9e5-4433-87c0-68b6b72699c7'
WINDOWS_RESERVED = 'e3c9e316-0b5c-4db8-817d-f92df00215ae'
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

    def test_new_ext4_data_mount_enables_journal_check_before_login(self):
        [(target, row)] = self.plan(disk('sda', partition('sda1', 'ext4', NTFS_UUID, LINUX_DATA)))
        self.assertEqual(row.split()[-1], '2')
        self.assertIn('errors=remount-ro', row)
        self.assertIn('x-systemd.before=local-fs.target', row)

    def test_migration_preserves_custom_mounts_and_is_idempotent(self):
        header = '# Montagem de discos de dados — Callas OS\n'
        options = ','.join(sorted(automount.MANAGED_OPTIONS))
        original = f'UUID={NTFS_UUID} {self.target} ext4 {options} 0 0\n'
        custom = f'UUID={ROOT_UUID} /run/media/ana/Dados ext4 nosuid,nodev,nofail 0 0\n'
        result = automount.refresh_managed_fstab((original + header + original + custom).encode())
        self.assertIn((original + header).encode(), result)
        self.assertIn(custom.encode(), result)
        self.assertIn(b'errors=remount-ro', result)
        self.assertEqual(automount.refresh_managed_fstab(result), result)

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
                           {'tran': 'nvme', 'rm': True, 'hotplug': True}, {'ro': True}):
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

    def test_sata_system_and_hotplug_nvme_with_reserved_siblings(self):
        self.root = '/dev/sda2'
        self.system = disk('sda', partition('sda2', 'ext4', ROOT_UUID, LINUX_DATA, mountpoints=['/']))
        data_uuid = '1557ea53-066c-450e-b104-d8399c7729f3'
        active_path = '/run/media/ana/Jogos NVMe'
        nvme = disk(
            'nvme0n1',
            partition('nvme0n1p1', 'vfat', '4C04-67C7', EFI),
            partition('nvme0n1p2', 'ntfs', NTFS_UUID, WINDOWS_RECOVERY),
            partition('nvme0n1p3', 'swap', 'bb4c0a53-6a7a-41a5-b5c6-f4b94d7ff5df',
                      '0657fd6d-a4ab-43c4-84e5-0933c84b4f4f', mountpoints=['[SWAP]']),
            partition('nvme0n1p4', 'xfs', data_uuid, LINUX_DATA,
                      partflags='0x0000000000000000', mountpoints=[active_path]),
            tran='nvme', hotplug=True, pttype='gpt',
        )
        [(target, row)] = self.plan(nvme)
        self.assertEqual(target, active_path)
        self.assertEqual(row.split()[:3], ['UUID=' + data_uuid, r'/run/media/ana/Jogos\040NVMe', 'xfs'])

    def test_sata_system_and_windows_gpt_nvme_no_drive_letter(self):
        self.root = '/dev/sda2'
        self.system = disk(
            'sda',
            partition('sda1', 'vfat', '9921-6A78', EFI, mountpoints=['/boot']),
            partition('sda2', 'ext4', ROOT_UUID, LINUX_DATA, mountpoints=['/']),
            pttype='gpt',
        )
        flags = '0x8000000000000000'
        files = partition('nvme0n1p3', 'ntfs', NTFS_UUID, WINDOWS_DATA, partflags=flags)
        secondary = disk(
            'nvme0n1',
            partition('nvme0n1p1', 'vfat', '4C04-67C7', EFI, partflags=flags),
            partition('nvme0n1p2', None, None, WINDOWS_RESERVED, partflags=flags),
            files,
            tran='nvme', pttype='gpt',
        )
        previous_target = '/run/media/ana/' + NTFS_UUID
        for mounts, expected_target in (([], self.target), ([previous_target], previous_target)):
            with self.subTest(mounts=mounts):
                files['mountpoints'] = mounts
                planned = self.plan(secondary)
                self.assertEqual([target for target, _ in planned], [expected_target])
                self.assertEqual(planned[0][1].split()[:3],
                                 ['UUID=' + NTFS_UUID, expected_target, 'ntfs3'])

    def test_no_drive_letter_flag_is_specific_to_microsoft_data_filesystems(self):
        flags = '0X8000000000000000'
        for fstype, expected_type in (('ntfs', 'ntfs3'), ('ntfs3', 'ntfs3'), ('exfat', 'exfat')):
            with self.subTest(fstype=fstype):
                data = partition('sda1', fstype, NTFS_UUID, WINDOWS_DATA, partflags=flags)
                planned = self.plan(disk('sda', data, pttype='gpt'))
                self.assertEqual([row.split()[2] for _, row in planned], [expected_type])
        for fstype, guid in (('ntfs', LINUX_DATA), ('ntfs', WINDOWS_RESERVED),
                             ('ext4', WINDOWS_DATA), ('xfs', WINDOWS_DATA), ('ntfs', '0x7')):
            with self.subTest(fstype=fstype, guid=guid):
                data = partition('sda1', fstype, NTFS_UUID, guid, partflags=flags)
                pttype = 'dos' if guid == '0x7' else 'gpt'
                self.assertEqual(self.plan(disk('sda', data, pttype=pttype)), [])

    def test_no_drive_letter_flag_does_not_override_other_gpt_attributes(self):
        restricted = {
            'required': 0, 'no block IO': 1, 'legacy boot': 2, 'unknown': 7,
            'read-only': 60, 'shadow copy': 61, 'hidden': 62,
        }
        for attribute, bit in restricted.items():
            for bits in (1 << bit, (1 << 63) | (1 << bit)):
                with self.subTest(attribute=attribute, flags=hex(bits)):
                    data = partition('sda1', 'ntfs', NTFS_UUID, WINDOWS_DATA,
                                     partflags=f'0x{bits:016x}')
                    self.assertEqual(self.plan(disk('sda', data, pttype='gpt')), [])

    def test_raw_nvme_filesystem_and_stale_partition_table(self):
        raw = disk('nvme1n1', tran='nvme', hotplug=True, fstype='ntfs', uuid=NTFS_UUID, pttype=None)
        [(target, row)] = self.plan(raw)
        self.assertEqual(target, self.target)
        self.assertEqual(row.split()[2], 'ntfs3')
        self.assertEqual(self.plan(dict(raw, pttype='gpt')), [])

    def test_single_device_btrfs_only_and_root_member_protection(self):
        uuid = '753bdb13-9ba0-4fa2-8144-65ee70dbc117'
        self.root = '/dev/sda2'
        self.system = disk('sda', partition('sda2', 'ext4', ROOT_UUID, LINUX_DATA, mountpoints=['/']))
        local = disk('sdb', partition('sdb1', 'btrfs', uuid, LINUX_DATA))
        peer = disk('sdc', partition('sdc1', 'btrfs', uuid, LINUX_DATA))
        [(target, row)] = self.plan(local)
        self.assertEqual(target, '/mnt/callas-' + uuid)
        self.assertEqual(row.split()[2], 'btrfs')
        self.assertEqual(self.plan(local, peer), [])
        self.system['children'][0].update(fstype='btrfs', uuid=uuid)
        local['children'].append(partition('sdb2', 'ntfs', NTFS_UUID, WINDOWS_DATA))
        self.assertEqual(self.plan(local), [])

    def test_system_root_ancestry_across_encrypted_raid_members(self):
        root = {'name': '/dev/mapper/system', 'type': 'crypt', 'uuid': ROOT_UUID, 'mountpoints': ['/']}
        raid = {'name': '/dev/md0', 'type': 'raid1', 'children': [root]}
        members = [
            disk(f'sd{suffix}',
                 partition(f'sd{suffix}1', 'linux_raid_member', ROOT_UUID, '0xfd', children=[raid]),
                 partition(f'sd{suffix}2', 'ext4', str(index) + ROOT_UUID[1:], LINUX_DATA))
            for index, suffix in enumerate('ab', 1)
        ]
        messages = []
        secondary = disk('sdc', partition('sdc1', 'ntfs', NTFS_UUID, WINDOWS_DATA))
        entries = automount.plan_mounts([*members, secondary], root['name'], [],
                                        'ana', 1507, 1608, lambda *_: True, report=messages.append)
        self.assertEqual([target for target, _ in entries], [self.target])
        self.assertEqual(len([message for message in messages if 'montagem do sistema' in message]), 2)


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

        def plan(*args, **kwargs):
            # Use real discovery. Redirect only its destination to the fixture.
            return [(str(self.target), line.replace(target, str(self.target)))
                    for target, line in real_plan(*args, **kwargs)]

        self.enterContext(patch.object(automount, 'FSTAB', self.fstab))
        self.enterContext(patch.object(Path, 'lstat', root_owned))
        self.enterContext(patch.object(automount.os, 'geteuid', return_value=0))
        self.enterContext(patch.object(automount.os, 'fchown'))
        self.enterContext(patch.object(automount.pwd, 'getpwnam', return_value=SimpleNamespace(pw_uid=1507, pw_gid=1608)))
        self.enterContext(patch.object(automount, 'inventory', side_effect=self.inventory))
        self.enterContext(patch.object(automount, 'available_target', return_value=True))
        self.enterContext(patch.object(automount, 'plan_mounts', side_effect=plan))
        self.verify = self.enterContext(patch.object(automount, 'verify_candidate', side_effect=self.verify_fstab))

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

    def verify_fstab(self, staged):
        self.assertTrue(self.target.is_dir())
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

        def fail_verification(staged):
            self.verify_fstab(staged)
            raise subprocess.CalledProcessError(1, 'findmnt')

        self.verify.side_effect = fail_verification
        with self.assertRaises(subprocess.CalledProcessError):
            automount.apply('ana')
        self.assertEqual(self.fstab.read_bytes(), self.previous)
        self.assertEqual(self.fstab.stat().st_ino, before)
        self.assertCountEqual(self.directory.iterdir(), [self.fstab])

    def test_concurrent_edit_after_validation_is_preserved(self):
        edited = self.previous + b'\n# another administrator\n'

        def edit_during_verification(staged):
            self.verify_fstab(staged)
            self.fstab.write_bytes(edited)

        self.verify.side_effect = edit_during_verification
        with self.assertRaises(RuntimeError):
            automount.apply('ana')
        self.assertEqual(self.fstab.read_bytes(), edited)
        self.assertCountEqual(self.directory.iterdir(), [self.fstab])


class ExistingConfigurationTests(unittest.TestCase):
    def test_missing_old_optional_mount_does_not_block_a_new_valid_one(self):
        diagnostics = '/run/media/ana/Antigo\n   [E] unreachable on boot required target\n'
        summary = '\n0 parse errors, 1 error, 0 warnings\n'
        failed = subprocess.CompletedProcess('findmnt', 1, diagnostics, summary)
        with patch.object(automount.subprocess, 'run', side_effect=[failed, failed]) as check:
            automount.verify_candidate(Path('/etc/fstab.candidate'))
        self.assertEqual([args[0][0][-1] for args in check.call_args_list],
                         ['/etc/fstab.candidate', '/etc/fstab'])

    def test_new_fstab_error_and_old_parse_error_are_rejected(self):
        for candidate, original in (
            ('0 parse errors, 1 error, 0 warnings', '0 parse errors, 0 errors, 0 warnings'),
            ('1 parse error, 0 errors, 0 warnings', '1 parse error, 0 errors, 0 warnings'),
        ):
            with self.subTest(candidate=candidate), patch.object(
                automount.subprocess, 'run', side_effect=[
                    subprocess.CompletedProcess('findmnt', 1, '', candidate),
                    subprocess.CompletedProcess('findmnt', 1, '', original),
                ]
            ), self.assertRaises(subprocess.CalledProcessError):
                automount.verify_candidate(Path('/etc/fstab.candidate'))

    def test_existing_callas_mounts_can_be_activated_but_noauto_is_preserved(self):
        target = '/mnt/callas-' + NTFS_UUID.lower()
        options = 'nosuid,nodev,nofail,x-systemd.device-timeout=10s,x-systemd.before=display-manager.service'
        disks = [disk('sda', partition('sda1', 'ntfs', NTFS_UUID, '0x7'))]
        sources = automount.devices_by_uuid(automount.device_nodes(disks))
        entry = {'source': '/dev/sda1', 'target': target, 'options': options}
        self.assertEqual(automount.managed_mounts([entry], sources), {target: '/dev/sda1'})
        self.assertEqual(automount.managed_mounts([dict(entry, options=options + ',noauto')], sources), {})
        self.assertEqual(automount.managed_mounts([dict(entry, target='/mnt/pessoal')], sources), {})
        self.assertEqual(automount.managed_mounts([entry], {NTFS_UUID.lower(): {'/dev/sda1', '/dev/sdb1'}}), {})

    def test_recovery_is_read_only_and_never_uses_force(self):
        target = '/mnt/callas-' + NTFS_UUID.lower()
        options = ','.join(sorted(automount.MANAGED_OPTIONS)) + ',uid=1507,gid=1608,umask=0077,force,noexec'
        entry = f'{automount.MARKER}\nUUID={NTFS_UUID} {target} ntfs3 {options} 0 0\n'
        lsblk = {'blockdevices': [disk('sda', partition('sda1', 'ntfs', NTFS_UUID, '0x7'))]}
        with patch.object(automount.FSTAB.__class__, 'read_text', return_value=entry), patch.object(
            automount, 'inventory', side_effect=[lsblk, {'filesystems': []}],
        ), patch.object(automount, 'available_target', return_value=True), patch.object(
            automount, 'device_path', side_effect=lambda value: '/dev/sda1' if value else None,
        ), patch.object(automount, 'mount_unit', return_value='mnt-callas.mount'), patch.object(
            automount.subprocess, 'run',
            side_effect=[SimpleNamespace(returncode=0), SimpleNamespace(returncode=0)],
        ) as run:
            automount.recover_ntfs()
        argv = run.call_args.args[0]
        self.assertEqual(argv[-2:], ['/dev/disk/by-uuid/' + NTFS_UUID, target])
        self.assertEqual(argv[argv.index('-o') + 1], 'ro,nosuid,nodev,uid=1507,gid=1608,umask=0077,noexec')

    def test_live_mount_skips_occupied_targets_and_devices_mounted_elsewhere(self):
        active = {'filesystems': [
            {'source': '/dev/sdb1', 'target': '/mnt/callas-occupied'},
            {'source': '/dev/nvme1n1p1', 'target': '/run/media/ana/Jogos'},
        ]}
        mounts = {
            '/mnt/callas-occupied': '/dev/sdc1',
            '/mnt/callas-active-elsewhere': '/dev/nvme1n1p1',
            '/mnt/callas-unused': '/dev/nvme1n1p2',
        }
        with patch.object(Path, 'is_dir', return_value=True), patch.object(
            automount, 'inventory', return_value=active,
        ), patch.object(automount, 'available_target', return_value=True), patch.object(
            automount.subprocess, 'check_output', return_value='mnt-callas-unused.mount\n',
        ) as escape, patch.object(
            automount.subprocess, 'run', side_effect=[SimpleNamespace(returncode=1),
                                                     SimpleNamespace(returncode=0),
                                                     SimpleNamespace(returncode=0)],
        ) as run:
            automount.start_mounts(mounts)
        self.assertEqual(run.call_args_list, [
            call(['systemd-detect-virt', '--chroot', '--quiet']),
            call(['systemctl', 'daemon-reload']),
            call(['systemctl', 'start', '--', 'mnt-callas-unused.mount']),
        ])
        escape.assert_called_once_with(
            ['systemd-escape', '--path', '--suffix=mount', '--', '/mnt/callas-unused'], text=True,
        )


if __name__ == '__main__':
    unittest.main()
