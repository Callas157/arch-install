"""Execute the chroot configuration in a disposable filesystem.

Uses real Bash/Python/file operations and source scripts; Arch package/hardware
commands are simulated. This is not an Arch installation or a graphical test.
"""
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
UPDATER=ROOT/'programas-callas-os/atualizador'

def child_script():
    return (ROOT/'instalar-arch.sh').read_text().split("<<'CALLAS_CHROOT'\n",1)[1].split('\nCALLAS_CHROOT\n',1)[0]

class InstallerFlowTests(unittest.TestCase):
    def test_assets_are_passed_explicitly_with_an_empty_environment(self):
        child=child_script(); header=child[:child.index('ln -sf ')]
        start=child.index('curl -fsSL --retry 2 "$asset_base/bonjourr/')
        call=child[start:child.index("aviso 'Não consegui baixar o perfil padrão do Bonjourr.'",start)]
        code=header+'\ncurl() { printf "%s\\n" "$@"; }\n'+call+'printf "fallback\\n"\n'
        result=subprocess.run(['bash','-c',code,'fixture','fixture','UTC','pt_BR.UTF-8','us','host','rootuuid','0','kvm','0','1af4:1050','0','0','0','https://example.org/assets'],env={'PATH':os.environ['PATH']},capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('https://example.org/assets/bonjourr/callas-profile.json',result.stdout)
        self.assertNotIn('CALLAS_ASSET_BASE',child)
    def test_no_interactive_aur_commands_in_initial_configuration(self):
        child=child_script()
        self.assertNotIn('/dev/tty',child)
        self.assertNotIn('--review',child)
        self.assertNotIn('makepkg -si',child)
        self.assertIn('callas-aur-install "$usuario"',child)
    def test_outer_error_handler_keeps_log_and_marks_incomplete_installation(self):
        text=(ROOT/'instalar-arch.sh').read_text()
        handler=text[text.index('finish_installation() {'):text.index('exec 3>&1 4>&2')]
        self.assertIn('installation-failed',handler)
        self.assertIn('callas-logs --export',handler)
        self.assertIn('"$CALLAS_INSTALL_LOG"',handler)
        self.assertIn('trap finish_installation EXIT',text)
    def test_exit_handler_exports_failure_log_and_preserves_exit_status(self):
        text=(ROOT/'instalar-arch.sh').read_text()
        handler=text[text.index('finish_installation() {'):text.index('exec 3>&1 4>&2')]
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'target'; logger=root/'usr/local/libexec/callas-logs';logger.parent.mkdir(parents=True)
            logger.write_text('#!/bin/sh\nexit 0\n');logger.chmod(0o755)
            log=Path(temp)/'installer.log';log.write_text('Exact failure diagnostic\n')
            export=Path(temp)/'exported'
            for status in (17,0):
                code='''mountpoint() { return 0; }
arch-chroot() { printf 'exported\\n' >> "$EXPORT_MARKER"; }
USUARIO=fixture
true &
CALLAS_INSTALL_LOG_PID=$!
exec 3>&1 4>&2
'''+handler.replace('/mnt',str(root))+f'\ntrap finish_installation EXIT\nexit {status}\n'
                result=subprocess.run(['bash','-eu','-c',code],env=dict(os.environ,CALLAS_INSTALL_LOG=str(log),EXPORT_MARKER=str(export)),capture_output=True,text=True)
                self.assertEqual(result.returncode,status,result.stderr)
                self.assertEqual((root/'var/lib/callas-os/installation-failed').exists(),status!=0)
                self.assertTrue(export.exists())
                files=list((root/'var/log/callas-os/Instalacao').glob('*.log'))
                self.assertTrue(files);self.assertEqual(files[0].read_text(),log.read_text())
    def test_full_configuration_reaches_theme_brave_session_and_tools(self):
        if not shutil.which('bwrap'): self.skipTest('bwrap unavailable')
        probe=subprocess.run(['bwrap','--unshare-user','--uid','0','--gid','0','--ro-bind','/','/','--','true'],capture_output=True)
        if probe.returncode: self.skipTest('user namespace unavailable')
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp)
            for name in ('etc','etc/sudoers.d','etc/systemd','etc/default','var/tmp','var/log','boot/grub','home/fixture/.config','home/fixture/.local/bin','opt/brave-bin','share/callas-os/grub','share/plymouth/themes','local/bin','local/libexec','local/share/callas-os/security-stage','fakebin'):
                (base/name).mkdir(parents=True,exist_ok=True)
            for name,content in {'etc/locale.gen':'#pt_BR.UTF-8 UTF-8\n#en_US.UTF-8 UTF-8\n','etc/pacman.conf':'[options]\n#[multilib]\n#Include = /etc/pacman.d/mirrorlist\n','etc/pam.d/sddm':'pam_kwallet\n','etc/mkinitcpio.conf':'HOOKS=()\nMODULES=()\n','etc/grub.d/10_linux':'placeholder','share/callas-os/grub/theme.txt':'theme','share/callas-os/grub/background.png':'image'}.items():
                path=base/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content)
            (base/'etc/passwd').write_text('root:x:0:0:root:/root:/bin/bash\nfixture:x:0:0:test:/home/fixture:/bin/bash\nsddm:x:0:0:test:/var/lib/sddm:/bin/bash\n')
            (base/'etc/group').write_text('root:x:0:\nfixture:x:0:\nsddm:x:0:\n')
            for name in ('vmlinuz-linux','vmlinuz-linux-lts','initramfs-linux.img','initramfs-linux-lts.img'): (base/'boot'/name).write_text('data')
            fake='''#!/usr/bin/python3
import os,sys,json
from pathlib import Path
name=Path(sys.argv[0]).name;a=sys.argv[1:]
with open('/var/log/events','a') as f: f.write(name+' '+repr(a)+'\\n')
if name=='runuser': os.execvp(a[a.index('--')+1],a[a.index('--')+1:])
if name=='findmnt': print('vfat' if 'FSTYPE' in a else 'EFI-UUID')
elif name=='gpg' and '--show-keys' in a: print('fpr:::::::::E1096BCBFF6D418796DE78515384CE82BA52C83A:')
elif name=='curl' and '-o' in a:
 p=Path(a[a.index('-o')+1]);p.parent.mkdir(parents=True,exist_ok=True);p.write_text('{}')
elif name=='grub-mkconfig':
 p=Path(a[a.index('-o')+1]);p.write_text("menuentry 'Callas OS Linux' {}\\nmenuentry 'Callas OS (kernel LTS - recuperação)' {}\\nmenuentry 'Callas OS (diagnóstico sem splash)' {}\\n")
elif name=='grub-install':
 for name in ('/boot/grub/x86_64-efi/normal.mod','/boot/EFI/BOOT/BOOTX64.EFI'):
  p=Path(name);p.parent.mkdir(parents=True,exist_ok=True);p.write_text('boot')
elif name=='kreadconfig6': print('emptySession')
elif name=='kwriteconfig6':
 p=Path(os.environ['HOME'])/'.config'/a[a.index('--file')+1];p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('a') as f: f.write(' '.join(a)+'\\n')
'''
            for command in ('pacman','pacman-key','locale-gen','hwclock','visudo','chown','systemctl','udevadm','runuser','flatpak','findmnt','grub-mkconfig','grub-install','grub-script-check','plymouth-set-default-theme','mkinitcpio','modinfo','dkms','curl','gpg','xdg-user-dirs-update','plasma-apply-lookandfeel','kwriteconfig6','kreadconfig6','steam','discord','solaar','dbus-run-session'):
                path=base/'fakebin'/command;path.write_text(fake);path.chmod(0o755)
            (base/'fakebin/python').symlink_to('/usr/bin/python3')
            (base/'fakebin/awk').symlink_to('/usr/bin/mawk')
            for command in ('callas-aur-install','callas-kde-desligamento-login','callas-nekofetch'):
                path=base/'local/libexec'/command;path.write_text('#!/bin/sh\nprintf "%s\\n" "'+command+' $*" >> /var/log/events\n');path.chmod(0o755)
            for name,source in [('callas-monitores','monitores/callas-monitores.py'),('callas-janelas','janelas/callas-janelas.py'),('callas-inicio-kde','sessao/callas-inicio-kde.sh')]:
                text=(ROOT/'programas-callas-os'/source).read_text()
                # Simulated runuser remains UID 0 in a single-UID user namespace.
                if name=='callas-inicio-kde': text=text.replace('if (( EUID == 0 )); then','if false; then')
                path=base/'local/libexec'/name;path.write_text(text);path.chmod(0o755)
            stage=base/'local/share/callas-os/security-stage'
            shutil.copy(UPDATER/'callas-version.py',stage/'callas-version.py')
            shutil.copy(UPDATER/'callas-version.py',base/'local/libexec/callas-version');(base/'local/libexec/callas-version').chmod(0o755)
            (stage/'VERSION').write_text('3.2.2\n');(stage/'commit').write_text('a'*40+'\n')
            (stage/'callas-security.sh').write_text('mkdir -p /usr/local/share/applications\nprintf "[Desktop Entry]\\nExec=/usr/local/libexec/put-update --menu\\n" > /usr/local/share/applications/io.github.Callas157.AtualizadorDoSistema.desktop\n')
            (base/'child.sh').write_text(child_script())
            invocation=['bwrap','--unshare-user','--uid','0','--gid','0','--unshare-pid','--unshare-ipc','--unshare-uts','--die-with-parent','--tmpfs','/','--ro-bind','/usr','/usr','--symlink','usr/bin','/bin','--ro-bind','/lib','/lib','--ro-bind','/lib64','/lib64','--tmpfs','/tmp','--dir','/root','--dir','/run','--proc','/proc','--dev','/dev']
            for source,target in [('etc','/etc'),('var','/var'),('boot','/boot'),('home','/home'),('opt','/opt'),('share','/usr/share'),('local','/usr/local'),('fakebin','/callas-test-bin')]:
                invocation+=['--bind',str(base/source),target]
            invocation+=['--ro-bind',str(base/'child.sh'),'/child.sh','--setenv','PATH','/callas-test-bin:/usr/bin:/bin','--setenv','XDG_CONFIG_HOME','/home/fixture/.config','--setenv','HOME','/root','--','/usr/bin/bash','/child.sh','fixture','UTC','pt_BR.UTF-8','us','host','rootuuid','0','kvm','0','1af4:1050','0','0','0','https://example.org/assets']
            # Reproduce the reported interruption at the old unexported asset
            # reference, then run the corrected source through its final phase.
            (base/'child.sh').write_text(child_script().replace('$asset_base/bonjourr/','${CALLAS_ASSET_BASE}/bonjourr/'))
            broken=subprocess.run(invocation,capture_output=True,text=True,timeout=30)
            self.assertNotEqual(broken.returncode,0)
            self.assertIn('CALLAS_ASSET_BASE',broken.stderr)
            self.assertFalse((base/'opt/brave-bin/initial_preferences').exists())
            self.assertFalse((base/'local/share/applications/io.github.Callas157.Monitores.desktop').exists())
            # Namespace root cannot override host-inode DAC on this replay.
            (base/'etc/sudoers.d/10-wheel').chmod(0o640)
            (base/'child.sh').write_text(child_script())
            result=subprocess.run(invocation,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
            self.assertIn('BreezeDark',(base/'home/fixture/.config/kdeglobals').read_text())
            preferences=json.loads((base/'opt/brave-bin/initial_preferences').read_text())
            self.assertFalse(preferences['browser']['custom_chrome_frame'])
            self.assertIn('kActionTabSearch',preferences['toolbar']['pinned_actions'])
            self.assertTrue((base/'local/share/applications/io.github.Callas157.Monitores.desktop').exists())
            self.assertTrue((base/'local/share/applications/io.github.Callas157.AtualizadorDoSistema.desktop').exists())
            self.assertEqual(json.loads((base/'etc/callas-os/release.json').read_text())['status'],'complete')

spec=importlib.util.spec_from_file_location('initial_aur',UPDATER/'callas-aur-install.py')
aur=importlib.util.module_from_spec(spec);spec.loader.exec_module(aur)

class InitialAurTests(unittest.TestCase):
    def test_complete_initial_build_installs_dependencies_as_root_without_prompts(self):
        account=types.SimpleNamespace(pw_uid=os.getuid(),pw_gid=os.getgid(),pw_dir='/home/fixture')
        if account.pw_uid==0: self.skipTest('test needs an unprivileged fixture owner')
        installed=set(); calls=[]
        recipe='pkgname = app\ndepends = native-lib>=2\n'
        def simulate(args,**kwargs):
            calls.append(args)
            if args[0]=='/usr/bin/runuser':
                position=args.index('-i')+1
                while '=' in args[position] and not args[position].startswith('/'): position+=1
                command=args[position:]
                if command[0]=='/usr/bin/git' and 'clone' in command:
                    source=Path(command[-1]); source.mkdir(); (source/'.SRCINFO').write_text(recipe)
                if command[0]=='/usr/bin/makepkg':
                    self.assertNotIn('--syncdeps',command);self.assertNotIn('--install',command)
                    self.assertIn('--noconfirm',command)
                    (Path(kwargs['cwd'])/'app-1-1-x86_64.pkg.tar.zst').write_bytes(b'package')
                    (Path(kwargs['cwd'])/'app-debug-1-1-x86_64.pkg.tar.zst').write_bytes(b'debug')
                return types.SimpleNamespace(returncode=0,stdout='',stderr='')
            if args[1]=='-T':
                name=args[2].split('>=')[0]
                return types.SimpleNamespace(returncode=0 if name in installed else 127,stdout='',stderr='')
            if args[1]=='-Si': return types.SimpleNamespace(returncode=0,stdout='',stderr='')
            if args[1]=='-S': installed.add('native-lib')
            if args[1]=='-Qp': return types.SimpleNamespace(returncode=0,stdout=('app-debug' if 'app-debug' in args[-1] else 'app')+' 1-1\n',stderr='')
            if args[1]=='-U':
                self.assertIn('--noconfirm',args);self.assertFalse(any('app-debug-' in a for a in args))
                installed.add('app')
            return types.SimpleNamespace(returncode=0,stdout='',stderr='')
        response=json.dumps({'results':[{'Name':'app','PackageBase':'app'}]}).encode()
        with patch.object(aur.pwd,'getpwnam',return_value=account),patch.object(aur,'run',side_effect=simulate),patch.object(aur.urllib.request,'urlopen',return_value=io.BytesIO(response)):
            aur.Installer('fixture').install('app')
        self.assertEqual(installed,{'native-lib','app'})
        self.assertFalse(any('sudo' in arg or '--review'==arg for call in calls for arg in call))
    def test_metadata_keeps_dependencies_and_checks_pgp(self):
        deps,packages,keys=aur.metadata('pkgname = app\ndepends = libfoo>=2\nmakedepends_x86_64 = git\nvalidpgpkeys = '+'A'*40)
        self.assertEqual(deps,['libfoo>=2','git']);self.assertEqual(packages,['app']);self.assertEqual(keys,['A'*40])
        with self.assertRaises(ValueError): aur.metadata('pkgname = app\ndepends = --overwrite\n')
    def test_build_commands_have_no_sudo_and_no_new_privileges(self):
        account=types.SimpleNamespace(pw_uid=1000,pw_gid=1000,pw_dir='/home/fixture')
        with patch.object(aur.pwd,'getpwnam',return_value=account): installer=aur.Installer('fixture')
        with patch.object(aur,'run') as run:
            installer.as_user(['/usr/bin/makepkg','--noconfirm'])
        command=run.call_args.args[0]
        self.assertIn('--no-new-privs',command);self.assertNotIn('sudo',command)
    def test_package_query_failures_are_not_treated_as_missing_dependencies(self):
        account=types.SimpleNamespace(pw_uid=1000,pw_gid=1000,pw_dir='/home/fixture')
        with patch.object(aur.pwd,'getpwnam',return_value=account): installer=aur.Installer('fixture')
        with patch.object(aur,'run',return_value=types.SimpleNamespace(returncode=1,stderr='broken database')):
            with self.assertRaises(RuntimeError): installer.missing('app')

if __name__=='__main__':unittest.main()
