"""Native overlay and Spotify ACL regressions; package/ACL tools are simulated."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
UPDATER=ROOT/'atualizador'

class MediaAppsTests(unittest.TestCase):
    def spotify_fixture(self, root, *, package_status=0, uid=1000, acl_status=0):
        for name in ('opt/spotify/Apps','etc/callas-os','bin'):
            (root/name).mkdir(parents=True,exist_ok=True)
        (root/'etc/callas-os/log-user').write_text('fixture\n')
        commands={
            'id':f'printf "%s\\n" {uid}',
            'pacman':f'exit {package_status}',
            'setfacl':f'printf "%s\\n" "$*" >> "$STATE/acl-calls"\nexit {acl_status}',
        }
        for name,body in commands.items():
            path=root/'bin'/name;path.write_text('#!/bin/bash\n'+body+'\n');path.chmod(0o755)
        source=(UPDATER/'callas-spotify-permissions.sh').read_text()
        source=source.replace('(( EUID == 0 )) ||', 'true ||')
        source=source.replace('export PATH=/usr/bin:/bin','export PATH='+shlex.quote(str(root/'bin'))+':/usr/bin:/bin')
        for prefix in ('/opt/spotify','/etc/callas-os'):
            source=source.replace(prefix,str(root)+prefix)
        return source

    def run_permissions(self,root,source,*args):
        return subprocess.run(['bash','-c',source,'spotify-fixture',*args],env=dict(os.environ,STATE=str(root)),capture_output=True,text=True)

    def test_permissions_are_per_user_and_reapplied_without_a_separate_user_script(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=self.spotify_fixture(root)
            for args in (('fixture',),()):
                result=self.run_permissions(root,source,*args)
                self.assertEqual(result.returncode,0,result.stderr)
            calls=(root/'acl-calls').read_text().splitlines()
            expected=[f'-m u:1000:rwx {root}/opt/spotify',f'-R -P -m u:1000:rwX {root}/opt/spotify/Apps']
            self.assertEqual(calls,expected*2)
            self.assertNotIn('chmod',source)
            self.assertNotIn('spicetify backup apply',source)

    def test_missing_spotify_defers_but_database_and_acl_errors_are_not_hidden(self):
        for package_status,acl_status,expected in ((1,0,0),(2,0,1),(0,1,1)):
            with self.subTest(package_status=package_status,acl_status=acl_status),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);source=self.spotify_fixture(root,package_status=package_status,acl_status=acl_status)
                result=self.run_permissions(root,source,'fixture')
                self.assertEqual(result.returncode,expected,result.stdout+result.stderr)
                if package_status:self.assertFalse((root/'acl-calls').exists())

    def test_root_or_symbolic_spotify_directory_is_rejected_before_acl(self):
        for invalid in ('root','symlink'):
            with self.subTest(invalid=invalid),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);source=self.spotify_fixture(root,uid=0 if invalid=='root' else 1000)
                if invalid=='symlink':
                    (root/'opt/spotify/Apps').rmdir()
                    (root/'outside').mkdir()
                    (root/'opt/spotify/Apps').symlink_to(root/'outside',target_is_directory=True)
                result=self.run_permissions(root,source,'fixture')
                self.assertNotEqual(result.returncode,0)
                self.assertFalse((root/'acl-calls').exists())

    def test_hook_reapplies_permissions_after_spotify_install_or_upgrade(self):
        security=(UPDATER/'callas-security.sh').read_text()
        hook=security.split("<<'SPOTIFY_HOOK'\n",1)[1].split('\nSPOTIFY_HOOK',1)[0]
        self.assertIn('Operation = Install',hook)
        self.assertIn('Operation = Upgrade',hook)
        self.assertIn('Target = spotify',hook)
        self.assertIn('When = PostTransaction',hook)
        self.assertIn('Exec = /usr/local/libexec/callas-spotify-permissions',hook)
        release=(UPDATER/'callas-release.py').read_text()
        self.assertIn('programas-callas-os/atualizador/callas-spotify-permissions.sh',release)
        self.assertIn('callas-spotify-permissions.sh) target=callas-spotify-permissions',security)

    def test_overlay_installed_for_clean_and_existing_systems(self):
        installer=(ROOT.parent/'instalar-arch.sh').read_text()
        packages=installer.split('pacstrap -K /mnt',1)[1].split('\ngenfstab',1)[0]
        self.assertIn('gpu-screen-recorder-ui',packages)
        self.assertNotIn('instalar_aur gpu-screen-recorder gpu-screen-recorder-gtk',installer)
        self.assertIn('\ninstalar_aur spotify\n',installer)
        self.assertNotIn('pubkey_5384CE82BA52C83A.gpg',installer)
        security=(UPDATER/'callas-security.sh').read_text()
        self.assertIn('gpu-screen-recorder-ui',security[security.index('for package in '):security.index('missing+=("$package")')])
        self.assertIn('acl',security[security.index('for package in '):security.index('missing+=("$package")')])
        updater=(UPDATER/'callas-config-update.sh').read_text()
        self.assertLess(updater.index('/usr/local/libexec/callas-spotify-permissions "$usuario"'),updater.index('/usr/local/libexec/callas-version --complete'))

    def test_native_overlay_is_preferred_when_flatpak_is_also_present(self):
        session=(ROOT/'sessao/callas-inicio-kde.sh').read_text()
        section=session[session.index('gsr_id = '):session.index('\nvibrance_ativo = ')]
        for native in (True,False):
            with self.subTest(native=native):
                class Finder:
                    @staticmethod
                    def which(name):return '/usr/bin/gsr-ui' if native else None
                namespace={'shutil':Finder,'flatpak':lambda app:True,'launcher':lambda *args:shlex.join(args),
                           'chamar':lambda *args:False,'desktop':lambda label,cmd,icon:cmd,'planos':{},'avisos':[]}
                exec(compile(section,'gsr-fixture','exec'),namespace)
                command=namespace['planos']['gsr'][1]
                self.assertEqual(command,'/usr/bin/gsr-ui launch-daemon' if native else 'flatpak run com.dec05eba.gpu_screen_recorder gsr-ui')
        installer=(ROOT.parent/'instalar-arch.sh').read_text()
        embedded=installer.split("<<'CALLAS_KDE_START'\n",1)[1].split('\nCALLAS_KDE_START',1)[0]+'\n'
        self.assertEqual(embedded,session)

if __name__=='__main__':unittest.main()
