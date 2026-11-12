"""Content checkpoints, interrupted runs, asset caching, logs and window fallback."""
import datetime
import importlib.util
import io
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
UP=ROOT/'atualizador'
def load(path,name):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
state=load(UP/'callas-update-state.py','incremental')
logs=load(UP/'callas-logs.py','friendlylogs')
windows=load(ROOT/'janelas/callas-janelas.py','fallbackwindows')
release=load(UP/'callas-release.py','incrementalrelease')

class IncrementalTests(unittest.TestCase):
 def stage(self,root):
  stage=root/'stage';stage.mkdir()
  for name in set(sum((list(v) for v in state.DEPENDENCIES.values()),[]))|{'callas-config-update.sh'}:
   paths=list(ROOT.rglob(name))+list((ROOT.parent/'assets').rglob(name))
   if paths:shutil.copyfile(paths[0],stage/name)
   else:(stage/name).write_text('# fixture theme asset\n')
  (stage/'update-assets.json').write_text(json.dumps({'commit':'a'*40,'assets':{'grub/theme.txt':'b'*40,'wallpapers/test.jpg':'c'*40,'bonjourr/profile.json':'d'*40}}))
  return stage
 def test_content_changes_touch_only_related_phases_and_resume_after_failure(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);stage=self.stage(root);user=pwd.getpwuid(os.getuid()).pw_name
   with patch.object(state,'STATE',root/'receipts'),patch.object(state,'REQUIRED',{k:() for k in state.DEPENDENCIES}):
    completed=[]
    # A simulated window-service failure happens after all other phases succeed.
    for phase in state.DEPENDENCIES:
     self.assertTrue(state.needed(phase,stage,user))
     if phase!='session':state.complete(phase,stage,user);completed.append(phase)
    self.assertEqual([p for p in state.DEPENDENCIES if state.needed(p,stage,user)],['session'])
    state.complete('session',stage,user)
    self.assertFalse(any(state.needed(p,stage,user) for p in state.DEPENDENCIES))
    # A different Git commit with identical files does not invalidate receipts.
    manifest=json.loads((stage/'update-assets.json').read_text());manifest['commit']='e'*40
    (stage/'update-assets.json').write_text(json.dumps(manifest))
    self.assertFalse(any(state.needed(p,stage,user) for p in state.DEPENDENCIES))
    (stage/'callas-janelas.py').write_text((stage/'callas-janelas.py').read_text()+'\n# new window fix\n')
    self.assertEqual({p for p in state.DEPENDENCIES if state.needed(p,stage,user)},{'tools','session'})
    self.assertTrue(state.needed('boot',stage,user,force=True))
 def test_changed_artwork_or_missing_required_file_invalidates_only_its_phase(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);stage=self.stage(root);user=pwd.getpwuid(os.getuid()).pw_name
   required=root/'required';required.touch()
   rules={k:() for k in state.DEPENDENCIES};rules['boot']=(str(required),)
   with patch.object(state,'STATE',root/'receipts'),patch.object(state,'REQUIRED',rules):
    for phase in state.DEPENDENCIES:state.complete(phase,stage,user)
    manifest=json.loads((stage/'update-assets.json').read_text());manifest['assets']['wallpapers/test.jpg']='e'*40
    (stage/'update-assets.json').write_text(json.dumps(manifest))
    self.assertEqual([p for p in state.DEPENDENCIES if state.needed(p,stage,user)],['desktop'])
    required.unlink();self.assertTrue(state.needed('boot',stage,user))
 def test_asset_download_is_verified_atomic_and_skipped_when_unchanged(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);stage=self.stage(root);dest=root/'wallpaper.jpg';dest.write_bytes(b'old')
   good=b'new official image';manifest={'commit':'a'*40,'assets':{'wallpapers/test.jpg':state.blob(good)}}
   (stage/'update-assets.json').write_text(json.dumps(manifest))
   response=types.SimpleNamespace(url='https://raw.githubusercontent.com/expected',read=lambda size:good)
   manager=unittest.mock.MagicMock();manager.__enter__.return_value=response
   with patch.object(state.urllib.request,'urlopen',return_value=manager) as request:
    self.assertTrue(state.asset(stage,'wallpapers/test.jpg',dest))
    self.assertIn('/'+'a'*40+'/',request.call_args.args[0].full_url)
    self.assertEqual(dest.read_bytes(),good)
   with patch.object(state.urllib.request,'urlopen',side_effect=AssertionError('download repeated')):
    self.assertFalse(state.asset(stage,'wallpapers/test.jpg',dest))
   manifest['assets']['wallpapers/test.jpg']=state.blob(b'other');(stage/'update-assets.json').write_text(json.dumps(manifest))
   with patch.object(state.urllib.request,'urlopen',return_value=manager),self.assertRaises(ValueError):
    state.asset(stage,'wallpapers/test.jpg',dest)
   self.assertEqual(dest.read_bytes(),good)
 def test_logs_have_local_completion_time_and_never_overwrite_same_second(self):
  class Clock(datetime.datetime):
   @classmethod
   def now(cls,tz=None):return cls(2026,11,12,8,31,38,tzinfo=tz)
  with tempfile.TemporaryDirectory() as temp,patch.object(logs,'prepare',return_value=Path(temp)),patch.object(logs.os,'geteuid',return_value=1000),patch.object(logs.datetime,'datetime',Clock),patch.object(logs,'identified',side_effect=lambda data:data):
   (Path(temp)/'Janelas').mkdir()
   first=logs.write_log('Janelas',b'first\n');second=logs.write_log('Janelas',b'second\n')
   self.assertEqual(first.name,'2026-11-12_08h31m38s.log')
   self.assertEqual(second.name,'2026-11-12_08h31m38s__parte-02.log')
   self.assertIn('Encerrado em: 12/11/2026 às 08:31:38',first.read_text())
   self.assertTrue(first.read_bytes().endswith(b'first\n'))
   self.assertEqual(first.stat().st_mode & 0o777,0o600)
   imported=logs.write_log('Janelas',b'original\n','legacy.log')
   logs.write_log('Janelas',b'different\n','legacy.log')
   self.assertEqual(imported.read_bytes(),b'original\n')
 def test_snapshot_failure_uses_native_rules_but_rule_failures_stay_fatal(self):
  with patch.object(windows,'capture_windows',side_effect=RuntimeError('KWin timeout')),patch.object(windows,'remember_rules') as rules,patch.object(windows.Path,'is_file',return_value=False):
   windows.remember_windows();rules.assert_called_once_with([])
  with patch.object(windows,'capture_windows',return_value=[]),patch.object(windows,'remember_rules',side_effect=PermissionError('cannot save')):
   with self.assertRaises(PermissionError):windows.remember_windows()
 def test_snapshot_js_supports_both_kwin_window_apis_and_missing_output(self):
  if not shutil.which('node'):self.skipTest('node unavailable')
  source=(ROOT/'janelas/callas-janelas.py').read_text()
  js=source.split("js = '''",1)[1].split("'''.replace",1)[0].replace('SERVICE',json.dumps('fixture'))
  sample={'normalWindow':True,'transient':False,'resourceClass':'spotify','frameGeometry':{'x':1,'y':2,'width':3,'height':4},'maximizeMode':0,'output':None}
  for modern in (True,False):
   prefix='const item='+json.dumps(sample)+'; const workspace='+('{stackingOrder:[item]}' if modern else '{windowList:()=>[item]}')+'; const callDBus=(s,p,i,m,data)=>console.log(data);\n'
   result=subprocess.run(['node','-e',prefix+js],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stderr)
   self.assertEqual(json.loads(result.stdout)[0]['output'],'')
 def test_verify_only_does_not_run_dkms_initramfs_or_grub_generation(self):
  mod=load(Path(__file__).with_name('test_kernel_check.py'),'kernel_fixture_only')
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);test=mod.KernelCheckTests();source=test.fixture(root)
   for cmd in ('mkinitcpio','grub-mkconfig'):(root/'bin'/cmd).write_text('#!/bin/bash\nexit 88\n')
   result=test.run_check(root,'set -- --verify-only\n'+source)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
   self.assertFalse((root/'dkms-calls').exists())
 def test_security_skips_full_upgrade_when_requirements_are_present(self):
  text=(UP/'callas-security.sh').read_text();prefix=text[text.index('seguranca() {'):text.index('  nvidia_after=')]
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);(root/'etc').mkdir();(root/'etc/pacman.conf').write_text('[options]\nSigLevel = Required DatabaseOptional\n')
   code='''set -Eeuo pipefail
pacman() { [[ $1 != -Syu ]] || exit 88; return 0; }
'''+prefix.replace('/etc/',str(root)+'/etc/')+'}\nseguranca fixture\n'
   result=subprocess.run(['bash','-c',code],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stderr)
   self.assertIn('atualização geral do Arch não executada',result.stdout)

 def test_completed_commit_skips_downloads_but_pending_work_and_force_do_not(self):
  user=pwd.getpwuid(os.getuid()).pw_name
  original_read=Path.read_text;original_exists=Path.exists
  def read(path,*args,**kwargs):
   if str(path)=='/etc/callas-os/release.json':return json.dumps({'release':'a'*40,'status':'complete'})
   return original_read(path,*args,**kwargs)
  for pending,force,expected in ((False,False,0),(True,False,1),(False,True,1)):
   with self.subTest(pending=pending,force=force):
    def exists(path):
     if path.name.startswith('update-pending-'):return pending
     return original_exists(path)
    with patch.object(release.os,'geteuid',return_value=0),patch.dict(os.environ,{'SUDO_USER':user}),patch.object(release.sys,'argv',['callas-release']+(['--force'] if force else [])),patch.object(release,'resolve_ref',return_value='a'*40),patch.object(release,'stage_files') as download,patch.object(release.subprocess,'run',return_value=types.SimpleNamespace(returncode=0)),patch.object(Path,'read_text',read),patch.object(Path,'exists',exists):
     previous=os.umask(0o077)
     try:self.assertEqual(release.main(),0)
     finally:os.umask(previous)
     self.assertEqual(download.call_count,expected)
 def test_real_boot_phase_rebuilds_only_changed_components_once(self):
  text=(UP/'callas-config-update.sh').read_text()
  phase=text.split('# CALLAS_PHASE_BEGIN boot\n',1)[1].split('# CALLAS_PHASE_END boot\n',1)[0]
  copy=text[text.index('copy_changed() {'):text.index('# CALLAS_PHASE_BEGIN security')]
  for changed,fail,expected_init,expected_grub in (('',False,0,0),('grub/background.png',False,0,1),('plymouth/callas/background.jpg',False,1,0),('plymouth/callas/background.jpg',True,1,0)):
   with self.subTest(changed=changed,fail=fail),tempfile.TemporaryDirectory() as temp:
    root=Path(temp)
    for path in ('boot/grub/themes/callas','usr/share/plymouth/themes/callas','usr/share/plymouth/themes/script','usr/local/libexec','etc/plymouth','stage','logs','bin'):(root/path).mkdir(parents=True,exist_ok=True)
    for name in ('callas.script','callas.plymouth'):
     (root/'stage'/name).write_text('theme')
     (root/'usr/share/plymouth/themes/callas'/name).write_text('theme')
    for name in ('progress_box.png','progress_bar.png'):
     (root/'usr/share/plymouth/themes/script'/name).write_text('image')
     (root/'usr/share/plymouth/themes/callas'/name).write_text('image')
    (root/'etc/plymouth/plymouthd.conf').write_text('[Daemon]\nTheme=callas\nShowDelay=0\nUseFirmwareBackground=false\n')
    (root/'boot/grub/grub.cfg').write_text('menuentry Callas\nlinux /vmlinuz-linux root=x\nlinux /vmlinuz-linux-lts root=x\n')
    for name in ('initramfs-linux.img','initramfs-linux-lts.img'):(root/'boot'/name).write_text('initramfs')
    fake='''#!/bin/bash
printf '%s\n' "${0##*/}" >> "$TEST_ROOT/calls"
case ${0##*/} in
mkinitcpio) [[ $FAIL_INIT != 1 ]] ;;
grub-mkconfig) cp "$TEST_ROOT/boot/grub/grub.cfg" "$2" ;;
*) exit 0 ;;
esac
'''
    for name in ('mkinitcpio','grub-mkconfig','grub-script-check','plymouth-set-default-theme'):
     p=root/'bin'/name;p.write_text(fake);p.chmod(0o755)
    check=root/'usr/local/libexec/callas-kernel-check';check.write_text(fake);check.chmod(0o755)
    prefix='''set -euo pipefail
phase_needed() { return 0; }
phase_done() { echo completed > "$TEST_ROOT/completed"; }
erro() { echo "$*" >&2; exit 1; }
asset() { asset_changed=0; [[ $1 != "$CHANGE_ASSET" ]] || asset_changed=1; }
'''
    code=prefix+copy+phase
    for path in ('/boot/','/usr/share/','/usr/local/','/etc/'):code=code.replace(path,str(root)+path)
    env=dict(os.environ,TEST_ROOT=str(root),CHANGE_ASSET=changed,FAIL_INIT='1' if fail else '0',PATH=str(root/'bin')+':'+os.environ['PATH'],CALLAS_RELEASE_DIR=str(root/'stage'),logstage=str(root/'logs'))
    result=subprocess.run(['bash','-c',code],env=env,capture_output=True,text=True)
    self.assertEqual(result.returncode==0,not fail,result.stdout+result.stderr)
    calls=(root/'calls').read_text().splitlines()
    self.assertEqual(calls.count('mkinitcpio'),expected_init)
    self.assertEqual(calls.count('grub-mkconfig'),expected_grub)
    self.assertEqual((root/'completed').exists(),not fail)

if __name__=='__main__':unittest.main()
