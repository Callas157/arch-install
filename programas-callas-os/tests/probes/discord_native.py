"""Opt-in real KWin virtual test: python programas-callas-os/tests/probes/discord_native.py.

Runs on a private D-Bus, virtual displays and temporary HOME/XDG directories.
The only app is a synthetic Qt window, with no Discord account or connection.
Only the match class is aliased in the generated production script to avoid a
headless compositor activation-token issue for registered desktop IDs.
No packages or live desktop settings are changed. Logs stay in the printed
isolated test artifact directory. This is not a real PC reboot or Discord test.
"""
import os,sys,subprocess,tempfile,time,importlib.util,json
from pathlib import Path
if sys.argv[1:]!=['--isolated']:
    raise SystemExit(subprocess.run(['dbus-run-session','--',sys.executable,__file__,'--isolated']).returncode)
if os.geteuid()==0:raise SystemExit('Execute como usuário normal.')
ROOT=Path(__file__).resolve().parents[3]
root=Path(tempfile.mkdtemp(prefix='discord-memory-native-'))
for folder in ('run','config','data','cache','state'):(root/folder).mkdir(mode=0o700)
env=dict(os.environ,HOME=str(root),XDG_RUNTIME_DIR=str(root/'run'),XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(root/'data'),XDG_CACHE_HOME=str(root/'cache'),XDG_STATE_HOME=str(root/'state'),QT_QPA_PLATFORM='offscreen',KWIN_COMPOSE='Q',LIBGL_ALWAYS_SOFTWARE='1',NO_AT_BRIDGE='1',XDG_SESSION_TYPE='wayland')
env.pop('DISPLAY',None);env.pop('WAYLAND_DISPLAY',None);os.environ.update(env)
import dbus
bus=dbus.SessionBus()
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
windows=load('window_snapshot',ROOT/'programas-callas-os/janelas/callas-janelas.py')
memory=load('discord_backend',ROOT/'programas-callas-os/janelas/callas-discord.py')
state=dict(schema=1,boot_id='previous-boot',window_id='previous-window',output='Virtual-1',rect=dict(x=1400,y=40,width=640,height=600),output_rect=dict(x=1280,y=0,width=1280,height=800),maxH=False,maxV=False,fullScreen=False)
memory.save_state(state)
log=(root/'processes.log').open('w');kwin=daemon=client=None;index=0
app=root/'app.py';flag=root/'close'
app.write_text('''import sys,os\nfrom pathlib import Path\nfrom PySide6.QtWidgets import QApplication,QWidget\nfrom PySide6.QtCore import QTimer\na=QApplication([]);a.setDesktopFileName('callas-discord-probe');w=QWidget();w.resize(600,500);w.show();t=QTimer();t.timeout.connect(lambda:w.close() if Path(os.environ['CLOSE_FLAG']).exists() else None);t.start(50);sys.exit(a.exec())\n''')
backend=root/'backend.py';backend.write_text('''import importlib.util\ns=importlib.util.spec_from_file_location('backend',%r);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);original=m.memory_script\nm.memory_script=lambda *a,**k:original(*a,**k).replace("==='discord'","==='callas-discord-probe'")\nm.watch_discord()\n'''%str(ROOT/'programas-callas-os/janelas/callas-discord.py'))
def start_kwin():
 global kwin
 kwin=subprocess.Popen(['kwin_wayland','--virtual','--output-count','2','--width','1280','--height','800','--socket','wayland-memory','--no-lockscreen','--no-global-shortcuts','--no-kactivities'],env=env,stdout=log,stderr=log)
 for _ in range(100):
  if bus.name_has_owner('org.kde.KWin') and (root/'run/wayland-memory').exists():time.sleep(.3);return
  if kwin.poll() is not None:raise RuntimeError('KWin exited '+str(kwin.returncode))
  time.sleep(.1)
 raise RuntimeError('KWin startup timeout')
def start_daemon():
 global daemon
 daemon=subprocess.Popen([sys.executable,str(backend)],env=env,stdout=log,stderr=log)
 for _ in range(80):
  if bus.name_has_owner(memory.SERVICE):time.sleep(.2);return
  if daemon.poll() is not None:raise RuntimeError('Memory service exited')
  time.sleep(.1)
 raise RuntimeError('Memory startup timeout')
def capture():
 rows=[w for w in windows.capture_windows() if w['app']=='callas-discord-probe'];return rows[0] if rows else None
def wait_for(predicate):
 value=None
 for _ in range(50):
  if kwin.poll() is not None or daemon.poll() is not None:raise RuntimeError('private process exited')
  value=capture()
  if value and predicate(value):return value
  time.sleep(.1)
 raise AssertionError('State did not restore: '+str(value)+'; '+(root/'processes.log').read_text()[-1200:])
def launch():
 global client
 flag.unlink(missing_ok=True)
 client=subprocess.Popen([sys.executable,str(app)],env=dict(env,QT_QPA_PLATFORM='wayland',WAYLAND_DISPLAY='wayland-memory',CLOSE_FLAG=str(flag)),stdout=log,stderr=log)
def close():
 global client
 flag.touch();client.wait(timeout=8);client=None;time.sleep(.4)
def change(code):
 global index
 index+=1;path=root/('action'+str(index)+'.js');path.write_text("const ws=typeof workspace.windowList==='function'?workspace.windowList():workspace.stackingOrder;ws.filter(w=>String(w.resourceClass)==='callas-discord-probe').forEach(function(w){"+code+'});')
 api=dbus.Interface(bus.get_object('org.kde.KWin','/Scripting'),'org.kde.kwin.Scripting');name='test-action-'+str(index)
 n=int(api.loadScript(str(path),name,signature='ss'))
 try:dbus.Interface(bus.get_object('org.kde.KWin','/Scripting/Script'+str(n)),'org.kde.kwin.Script').run()
 finally:api.unloadScript(name)
results=[]
try:
 start_kwin();start_daemon();launch()
 normal=wait_for(lambda w:w['output']=='Virtual-1' and w['x']==1400 and w['width']==640 and w['height']==600)
 time.sleep(.5);results.append({'normal':capture()});close();launch()
 results.append({'normal_reopened':wait_for(lambda w:w['output']=='Virtual-1' and w['width']==640 and w['height']==600)})
 time.sleep(1);change('w.setMaximize(true,true);');wait_for(lambda w:w['maxH'] and w['maxV']);time.sleep(.5)
 expected_normal=memory.read_state()['rect'];daemon.terminate();daemon.wait(timeout=8);daemon=None;start_daemon();time.sleep(.6)
 assert memory.read_state()['rect']==expected_normal,('normal geometry lost on observer restart',memory.read_state())
 results.append({'observer_restarted_while_maximized':memory.read_state()});close();launch()
 results.append({'maximized_reopened':wait_for(lambda w:w['maxH'] and w['maxV'] and w['output']=='Virtual-1')})
 time.sleep(1);change('w.fullScreen=true;');wait_for(lambda w:w['fullScreen']);time.sleep(.5);close();launch()
 results.append({'fullscreen_reopened':wait_for(lambda w:w['fullScreen'] and w['output']=='Virtual-1')});time.sleep(.5);close()
 daemon.terminate();daemon.wait(timeout=8);daemon=None;kwin.terminate();kwin.wait(timeout=10);kwin=None;time.sleep(.3)
 start_kwin();start_daemon();launch()
 results.append({'session_restarted':wait_for(lambda w:w['fullScreen'] and w['output']=='Virtual-1')});close()
 print('NATIVE_MEMORY_OK '+json.dumps(results),flush=True)
finally:
 for p in (client,daemon,kwin):
  if p and p.poll() is None:
   p.terminate()
   try:p.wait(timeout=8)
   except subprocess.TimeoutExpired:p.kill();p.wait()
 log.close();print('ARTIFACTS '+str(root),flush=True)
