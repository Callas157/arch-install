"""Offline storage/cleanup/native-update checks; never modifies host packages."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import pwd
import subprocess
import sys
import tarfile
import tempfile
import time
import types
import unittest
from unittest.mock import patch, mock_open

ROOT = Path(__file__).resolve().parents[1]
U = ROOT / 'atualizador'

def load(name):
    spec=importlib.util.spec_from_file_location(name, U/(name+'.py'))
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

store=load('callas-storage'); logs=load('callas-logs')
native=load('callas-native'); maint=load('callas-maintenance'); aur=load('callas-aur')

class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.base=Path(self.temp.name)
        self.account=pwd.getpwuid(os.getuid())
        self.uid=patch.object(store,'ROOT_UID',os.getuid()); self.uid.start()
        self.policy=patch.object(store,'POLICY',self.base/'policy.ini'); self.policy.start()
    def tearDown(self): self.uid.stop(); self.policy.stop(); self.temp.cleanup()
    def open(self, **kwargs): return store.Backups(self.account.pw_name, documents=self.base, **kwargs)
    def add(self, backups, category, serial, size, timestamp):
        name=f'20261111-120000-{serial:012x}.tar.gz'
        fd=backups.directories[category]
        out=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600,dir_fd=fd)
        os.write(out,b'x'*size); os.close(out)
        os.utime(name,(timestamp,timestamp),dir_fd=fd)
        return name
    def test_combined_quota_removes_oldest_across_categories(self):
        with self.open(limit=700,keep=3) as backups:
            oldest=self.add(backups,'Sistema',1,400,1)
            newest=self.add(backups,'Seguranca',2,400,2)
            self.assertEqual(backups.rotate(),400)
            self.assertFalse((backups.path/'Sistema'/oldest).exists())
            self.assertTrue((backups.path/'Seguranca'/newest).exists())
    def test_three_newest_per_type_are_kept(self):
        with self.open(limit=10000,keep=3) as backups:
            for i in range(5): self.add(backups,'Sistema',i,10,i)
            backups.rotate()
            self.assertEqual([row[2] for row in backups.entries()], [f'20261111-120000-{i:012x}.tar.gz' for i in (2,3,4)])
    def test_real_archive_is_private_and_readable_by_admin(self):
        source=self.base/'secret'; source.write_text('private recovery data')
        with self.open() as backups:
            name=backups.create('Sistema',[source]); target=backups.path/'Sistema'/name
            self.assertEqual(target.stat().st_mode&0o777,0o600)
            self.assertEqual((backups.path/'Sistema').stat().st_mode&0o777,0o755)
            with tarfile.open(target) as archive:
                member=next(m for m in archive.getmembers() if m.name.endswith('/secret'))
                self.assertEqual(archive.extractfile(member).read(),b'private recovery data')
    def test_oversized_archive_does_not_leave_partial_or_delete_previous(self):
        source=self.base/'random'; source.write_bytes(os.urandom(8192))
        with self.open(limit=300) as backups:
            previous=self.add(backups,'Sistema',1,100,1)
            self.assertIsNone(backups.create('Sistema',[source]))
            self.assertTrue((backups.path/'Sistema'/previous).exists())
            self.assertFalse(any(name.startswith('.partial') for name in os.listdir(backups.directories['Sistema'])))
    def test_migration_moves_only_recognized_legacy_snapshots(self):
        legacy=self.base/'legacy'; legacy.mkdir()
        snapshot=legacy/'20261110-101010'; snapshot.mkdir(); (snapshot/'config').write_text('data')
        unrelated=legacy/'do-not-delete'; unrelated.mkdir(); (unrelated/'keep').write_text('data')
        with patch.object(store,'LEGACY',{legacy:'Seguranca'}), self.open() as backups:
            backups.migrate(); backups.migrate()
            self.assertFalse(snapshot.exists()); self.assertTrue(unrelated.exists())
            self.assertEqual(len(backups.entries()),1)
    def test_failed_import_keeps_legacy_original(self):
        legacy=self.base/'legacy'; legacy.mkdir(); snapshot=legacy/'20261110-101010'; snapshot.mkdir()
        with patch.object(store,'LEGACY',{legacy:'Seguranca'}), self.open() as backups, patch.object(backups,'create',side_effect=OSError('disk full')):
            with self.assertRaises(OSError): backups.migrate()
        self.assertTrue(snapshot.exists())
    def test_symlink_category_is_rejected_without_writing_through_it(self):
        outside=self.base/'outside'; outside.mkdir()
        with self.open() as backups: path=backups.path
        (path/'Sistema').rmdir(); (path/'Sistema').symlink_to(outside,target_is_directory=True)
        with self.assertRaises(OSError): self.open()
        self.assertEqual(list(outside.iterdir()),[])
    def test_symlink_document_component_is_rejected(self):
        real=self.base/'real'; real.mkdir(); link=self.base/'link'; link.symlink_to(real,target_is_directory=True)
        with self.assertRaises(OSError): store.open_directory(link)
    def test_world_writable_backup_folder_is_rejected(self):
        with self.open() as backups: path=backups.path
        path.chmod(0o777)
        with self.assertRaises(ValueError): self.open()
    def test_quota_does_not_follow_symlink_archives(self):
        outside=self.base/'outside'; outside.write_text('keep')
        with self.open(limit=1) as backups:
            (backups.path/'Sistema'/'20261111-120000-000000000001.tar.gz').symlink_to(outside)
            backups.rotate(); self.assertEqual(outside.read_text(),'keep')
    def test_invalid_policy_cannot_trigger_deletions(self):
        store.POLICY.write_text('[Backups]\nlimit_bytes=0\ncopies_per_type=3\n')
        with self.assertRaises(ValueError): self.open()
    def test_package_lock_never_removes_an_existing_lock(self):
        database=self.base/'db'; database.mkdir(); lock=database/'db.lck'; lock.write_text('other process')
        with self.assertRaises(RuntimeError):
            with store.package_database_lock(database): pass
        self.assertEqual(lock.read_text(),'other process')
    def test_package_lock_is_released_on_failure(self):
        with self.assertRaises(RuntimeError):
            with store.package_database_lock(self.base): raise RuntimeError('backup failed')
        self.assertFalse((self.base/'db.lck').exists())

class LogTests(unittest.TestCase):
    def test_old_folder_is_migrated_without_losing_logs(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(logs,'documents',return_value=Path(temp)), patch.object(logs.os,'geteuid',return_value=1000):
            old=Path(temp)/'Logs do Callas OS'/'AUR'; old.mkdir(parents=True); (old/'old.log').write_text('previous')
            path=logs.write_log('AUR',b'new')
            self.assertEqual((Path(temp)/'Callas OS'/'Callas OS Logs'/'AUR'/'old.log').read_text(),'previous')
            self.assertTrue(path.exists()); self.assertFalse(old.exists())
    def test_same_origin_is_not_exported_twice(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(logs,'documents',return_value=Path(temp)), patch.object(logs.os,'geteuid',return_value=1000):
            a=logs.write_log('AUR',b'first',origin='source.log')
            b=logs.write_log('AUR',b'second',origin='source.log')
            self.assertEqual(a,b); self.assertEqual(a.read_bytes(),b'first')
            self.assertEqual(len(list(a.parent.glob('*.log'))),1)
    def test_log_size_and_total_retention_are_bounded(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(logs,'documents',return_value=Path(temp)), patch.object(logs.os,'geteuid',return_value=1000), patch.object(logs,'MAX_FILE',100), patch.object(logs,'MAX_TOTAL',180):
            for i in range(4): logs.write_log('AUR',b'x'*90)
            base=Path(temp)/'Callas OS'/'Callas OS Logs'
            self.assertLessEqual(sum(p.stat().st_size for p in base.rglob('*.log')),180)
            logs.write_log('AUR',b'y'*1000)
            self.assertLessEqual(max(p.stat().st_size for p in base.rglob('*.log')),100)
    def test_retention_does_not_traverse_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp)/'logs'; base.mkdir(); outside=Path(temp)/'outside'; outside.mkdir()
            file=outside/'keep.log'; file.write_text('keep'); os.utime(file,(1,1))
            (base/'link').symlink_to(outside,target_is_directory=True)
            logs.prune(base); self.assertTrue(file.exists())

class NativeTests(unittest.TestCase):
    def test_pretransaction_guard_blocks_kernel_and_boot(self):
        for packages, expected in (('qbittorrent\nqt6-base\n',0),('linux\n',1),('mkinitcpio\n',1),('grub\n',1),('amd-ucode\n',1)):
            with self.subTest(packages=packages):
                result=subprocess.run([sys.executable,'-c',native.pretransaction_code()],input=packages,text=True,capture_output=True)
                self.assertEqual(result.returncode,expected)
    def test_pending_base_defers_official_apps_without_calling_pacman(self):
        response=types.SimpleNamespace(returncode=0,stdout='linux 1 -> 2\nqbittorrent 1 -> 2\n',stderr='')
        with patch.object(native.subprocess,'run',return_value=response) as run:
            self.assertEqual(native.update(),2)
        self.assertEqual(run.call_count,1)
    def test_only_kernel_pending_is_left_to_general_without_false_app_failure(self):
        response=types.SimpleNamespace(returncode=0,stdout='linux 1 -> 2\n',stderr='')
        with patch.object(native.subprocess,'run',return_value=response) as run:
            self.assertEqual(native.update(),0)
        self.assertEqual(run.call_count,1)
    def test_allowed_transaction_uses_guard_and_complete_upgrade(self):
        responses=[types.SimpleNamespace(returncode=0,stdout='qbittorrent 1 -> 2\n',stderr=''),types.SimpleNamespace(returncode=0)]
        with patch.object(native.subprocess,'run',side_effect=responses) as run:
            self.assertEqual(native.update(),0)
            args=run.call_args.args[0]
            self.assertIn('-Syu',args); self.assertIn('--hookdir',args)
    def test_apps_only_aur_never_requests_native_dependency_install(self):
        with self.assertRaises(aur.RequiresGeneral): aur.plan('INSTALL DEP extra new-library\nAUR TARGET app app',apps_only=True)
        with self.assertRaises(aur.RequiresGeneral): aur.plan('AUR TARGET linux-custom linux-custom',apps_only=True)

class MaintenanceTests(unittest.TestCase):
    def test_stale_build_cleanup_preserves_recent_unknown_and_symlink_targets(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp); builds=base/'builds'; builds.mkdir()
            old=builds/'transaction-abcdefgh'; old.mkdir(); (old/'cache').write_text('old')
            recent=builds/'transaction-ijklmnop'; recent.mkdir()
            unknown=builds/'keep-this'; unknown.mkdir()
            target=base/'vm'; target.mkdir(); (target/'disk.qcow2').write_text('preserve')
            link=builds/'transaction-qrstuvwx'; link.symlink_to(target, target_is_directory=True)
            os.utime(old,(0,0)); os.utime(unknown,(0,0))
            with patch.object(maint,'BUILD_ROOT',builds), patch.object(maint,'ROOT_UID',os.getuid()), patch.object(maint,'storage',return_value=store):
                maint.prune_builds()
            self.assertFalse(old.exists()); self.assertTrue(recent.exists()); self.assertTrue(unknown.exists())
            self.assertTrue(link.is_symlink()); self.assertEqual((target/'disk.qcow2').read_text(),'preserve')
    def test_automatic_cleanup_never_removes_orphans_or_vm_files(self):
        fake=types.SimpleNamespace(Backups=unittest.mock.MagicMock(),as_user=unittest.mock.MagicMock(),package_database_lock=lambda path:contextlib.nullcontext())
        fake.Backups.return_value.__enter__.return_value.rotate.return_value=0
        with patch.object(maint,'storage',return_value=fake), patch.object(maint,'run',return_value='/fixture/db') as run, patch.object(maint,'prune_builds'), patch('builtins.open',mock_open()), patch.object(maint.fcntl,'flock'):
            maint.clean('user')
        calls=[c.args[0] for c in run.call_args_list]
        self.assertTrue(any('/usr/bin/paccache' in c and '3' in c and '--ignore' in c for c in calls))
        self.assertTrue(any(c==['/usr/bin/systemd-tmpfiles','--clean','--prefix=/tmp','--prefix=/var/tmp'] for c in calls))
        self.assertFalse(any('/usr/bin/pacman' in c or '-R' in c or 'rm' in c for c in calls))
    def test_orphan_candidates_preserve_core_and_default_apps(self):
        output='linux\nspotify\ngnome-boxes\nqbittorrent\nsome-unused-library\n'
        with patch.object(maint.subprocess,'run',return_value=types.SimpleNamespace(returncode=0,stdout=output,stderr='')):
            self.assertEqual(maint.orphans(),['some-unused-library'])
    def test_no_tty_means_report_only_for_orphans(self):
        with patch.object(maint,'orphans',return_value=['old-library']), patch.object(maint,'run') as run, patch.object(maint.sys.stdin,'isatty',return_value=False):
            maint.manage_orphans()
        self.assertEqual(run.call_count,1); self.assertIn('-Qi',run.call_args.args[0])
    def test_vm_inventory_preserves_disk_and_iso(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp); images=home/'.local/share/gnome-boxes/images'; images.mkdir(parents=True)
            disk=images/'test.qcow2'; disk.write_bytes(b'disk'); iso=images/'test.iso'; iso.write_bytes(b'iso')
            account=types.SimpleNamespace(pw_dir=temp)
            fake=types.SimpleNamespace(as_user=lambda *a,**k:types.SimpleNamespace(stdout=''))
            with patch.object(maint.pwd,'getpwnam',return_value=account), patch.object(maint,'storage',return_value=fake), contextlib.redirect_stdout(io.StringIO()):
                maint.vm_report('user')
            self.assertEqual(disk.read_bytes(),b'disk'); self.assertEqual(iso.read_bytes(),b'iso')

class CalendarTests(unittest.TestCase):
    def test_month_end_and_weekly_apps(self):
        text=(U/'put-update.sh').read_text(); function=text[text.index('proxima_data() {'):text.index('\nler_data_agenda()')]
        for mode, base, expected in (('sistema','2026-01-31','2026-02-28'),('sistema','2028-01-31','2028-02-29'),('sistema','2026-12-31','2027-01-31'),('apps','2026-11-11','2026-11-18')):
            result=subprocess.run(['bash','-c',function+f'\nproxima_data {mode} {base}'],capture_output=True,text=True,check=True)
            self.assertEqual(result.stdout.strip(),expected)
    def test_menu_labels_and_dispatch(self):
        text=(U/'put-update.sh').read_text()
        for value in ('1. Limpeza e manutenção','2. Atualizar aplicativos nativos','3. Atualizar Discord','4. Atualizar geral','5. Callas OS Update','6. Sair'):
            self.assertIn(value,text)
        start=text.index('            2) modo='); branch=text[start:text.index('            5)',start)]
        result=subprocess.run(['bash','-c','for opcao in 2 3 4; do case $opcao in\n'+branch+'\nesac; echo "$opcao:$modo"; done'],capture_output=True,text=True,check=True)
        self.assertEqual(result.stdout.splitlines(),['2:nativos','3:discord','4:sistema'])

if __name__=='__main__': unittest.main()
