#!/usr/bin/python3
"""Persist only Discord's main-window placement across KWin/session restarts."""
import configparser
import fcntl
import json
import os
from pathlib import Path
import socket
import sys
import tempfile

STATE=Path(os.environ.get('XDG_STATE_HOME',str(Path.home()/'.local/state')))/'callas-os/discord-window.json'
SERVICE='io.github.Callas157.DiscordPlacement'


def validate(state):
    if not isinstance(state,dict) or set(state)!={'schema','boot_id','window_id','output','rect','output_rect','maxH','maxV','fullScreen'}:
        raise ValueError('Estado de janela do Discord inválido; arquivo preservado.')
    if state['schema']!=1:raise ValueError('Versão da memória do Discord incompatível.')
    for key in ('boot_id','window_id','output'):
        if not isinstance(state[key],str) or not state[key] or len(state[key])>180:raise ValueError('Identidade de janela inválida.')
    for key in ('maxH','maxV','fullScreen'):
        if type(state[key]) is not bool:raise ValueError('Formato de janela inválido.')
    for name in ('rect','output_rect'):
        rect=state[name]
        if not isinstance(rect,dict) or set(rect)!={'x','y','width','height'}:raise ValueError('Geometria inválida.')
        if any(type(v) is not int or abs(v)>1000000 for v in rect.values()) or min(rect['width'],rect['height'])<1:
            raise ValueError('Dimensão de janela inválida.')
    return state


def read_state():
    if STATE.is_symlink():raise ValueError('Registro simbólico não permitido.')
    try:
        if STATE.stat().st_size>16384:raise ValueError('Registro do Discord excedeu o limite.')
        return validate(json.loads(STATE.read_text()))
    except FileNotFoundError:return None


def save_state(state):
    validate(state)
    if not STATE.is_absolute():raise ValueError('Pasta de estado precisa ser absoluta.')
    for parent in (*reversed(STATE.parents),STATE):
        if parent.is_symlink():raise ValueError('Caminho simbólico não permitido na memória do Discord.')
    STATE.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd,name=tempfile.mkstemp(prefix='.discord-',dir=STATE.parent)
    try:
        with os.fdopen(fd,'w') as stream:
            json.dump(state,stream);stream.write('\n');stream.flush();os.fsync(stream.fileno());os.fchmod(stream.fileno(),0o600)
        os.replace(name,STATE)
    finally:Path(name).unlink(missing_ok=True)


def legacy_rule(path=None):
    path=path or Path(os.environ.get('XDG_CONFIG_HOME',str(Path.home()/'.config')))/'kwinrulesrc'
    cfg=configparser.ConfigParser(interpolation=None);cfg.optionxform=str
    cfg.read(path)
    if not cfg.has_section('General'):return None
    general=cfg['General'];order=general.get('Order',general.get('rules','')).split(',')
    for section in order:
        if not cfg.has_section(section):continue
        rule=cfg[section]
        if rule.get('wmclass','').lower()!='discord' or rule.get('windowrole'):continue
        if not rule.get('Description','').startswith('Callas OS: lembrar '):return None
        try:
            x,y=map(int,rule['position'].split(','));width,height=map(int,rule['size'].split(','))
            if any(rule.get(key)!='4' for key in ('positionrule','sizerule','screenrule')):return None
            screen=int(rule['screen'])
            if min(width,height)<=0 or screen<0:return None
            return dict(screen=screen,rect=dict(x=x,y=y,width=width,height=height),
                maxH=rule.get('maximizehoriz','false').lower()=='true',
                maxV=rule.get('maximizevert','false').lower()=='true',fullScreen=rule.get('fullscreen','false').lower()=='true')
        except (KeyError,ValueError):return None
    return None


def memory_script(saved,boot_id,legacy=None):
    if saved is not None:validate(saved)
    return r'''(function(){
let saved=INITIAL;const bootId=BOOT,SERVICE='io.github.Callas157.DiscordPlacement';
const records=Object.create(null);
function rect(g){return {x:Math.round(g.x),y:Math.round(g.y),width:Math.round(g.width),height:Math.round(g.height)};}
const legacy=LEGACY;
if(!saved&&legacy){const o=(workspace.screenOrder||workspace.screens||[])[legacy.screen];if(o)saved={schema:1,boot_id:'kwin-migration',window_id:'kwin-migration',output:String(o.name),rect:legacy.rect,output_rect:rect(o.geometry),maxH:legacy.maxH,maxV:legacy.maxV,fullScreen:legacy.fullScreen};}
function windows(){return typeof workspace.windowList==='function'?workspace.windowList():workspace.stackingOrder;}
function main(w){return w && w.normalWindow && !w.transient && !w.splash && !w.windowRole
    && String(w.resourceClass).toLowerCase()==='discord' && w.frameGeometry.width>=480 && w.frameGeometry.height>=300;}
function single(){return (windows()||[]).filter(main).length===1;}
function send(state){saved=state;callDBus(SERVICE,'/Placement',SERVICE,'save',JSON.stringify(state));}
function persist(r,closing){
    const w=r.w;if(r.restoring||r.blocked||!main(w)||(!closing&&!single())||!w.output)return false;
    if(saved&&!r.userChoice&&!(workspace.screenOrder||workspace.screens||[]).some(o=>String(o.name)===saved.output)){
        r.blocked=true;r.missingOutput=true;return false;
    }
    const maxH=(Number(w.maximizeMode)&2)!==0,maxV=(Number(w.maximizeMode)&1)!==0;
    if(!w.fullScreen){
        const g=rect(w.frameGeometry);r.normal=r.normal||g;
        if(!maxH){r.normal.x=g.x;r.normal.width=g.width;}
        if(!maxV){r.normal.y=g.y;r.normal.height=g.height;}
    }
    const state={schema:1,boot_id:bootId,window_id:String(w.internalId),output:String(w.output.name),
        rect:r.normal||rect(w.frameGeometry),output_rect:rect(w.output.geometry),maxH:maxH,maxV:maxV,fullScreen:Boolean(w.fullScreen)};
    r.last=state;send(state);return true;
}
function schedule(r){r.timer.start();}
function restore(r){
    if(!main(r.w)||!single())return;
    const w=r.w,outputs=workspace.screenOrder||workspace.screens||[];
    const target=outputs.find(o=>String(o.name)===saved.output);
    if(!target){r.restoring=false;r.blocked=true;r.missingOutput=true;print('CallasDiscord: monitor salvo ausente; preferência preservada.');return;}
    const bounds=target.geometry;
    const g={x:saved.rect.x-saved.output_rect.x+bounds.x,y:saved.rect.y-saved.output_rect.y+bounds.y,
        width:Math.min(saved.rect.width,bounds.width),height:Math.min(saved.rect.height,bounds.height)};
    g.x=Math.max(bounds.x,Math.min(g.x,bounds.x+bounds.width-g.width));
    g.y=Math.max(bounds.y,Math.min(g.y,bounds.y+bounds.height-g.height));
    if(r.step===0){w.fullScreen=false;w.setMaximize(false,false);if(String(w.output.name)!==saved.output)workspace.sendClientToScreen(w,target);}
    else if(r.step===1){w.frameGeometry=g;r.normal=g;}
    else if(r.step===2){w.setMaximize(saved.maxH,saved.maxV);w.fullScreen=saved.fullScreen;}
    else {
        const actual=w.frameGeometry;
        const sizeOK=saved.maxH||saved.maxV||saved.fullScreen||['x','y','width','height'].every(k=>Math.abs(actual[k]-g[k])<=32);
        const stateOK=((Number(w.maximizeMode)&2)!==0)===saved.maxH&&((Number(w.maximizeMode)&1)!==0)===saved.maxV&&Boolean(w.fullScreen)===saved.fullScreen;
        if(String(w.output.name)===saved.output&&sizeOK&&stateOK){r.restoring=false;persist(r);return;}
        if(++r.attempt>=3){r.restoring=false;r.blocked=true;print('CallasDiscord: restauração não confirmada; estado anterior preservado.');return;}
        r.step=-1;
    }
    ++r.step;schedule(r);
}
function watch(w){
    if(!w||!w.internalId||records[String(w.internalId)])return;
    const timer=new QTimer();timer.interval=220;timer.singleShot=true;
    let normal=null;
    if(saved){normal={x:saved.rect.x,y:saved.rect.y,width:saved.rect.width,height:saved.rect.height};
        if(w.output&&String(w.output.name)!==saved.output){normal.x+=w.output.geometry.x-saved.output_rect.x;normal.y+=w.output.geometry.y-saved.output_rect.y;}
    }
    const r={w:w,timer:timer,normal:normal,last:null,blocked:false,step:0,attempt:0,
        restoring:Boolean(saved&&(saved.boot_id!==bootId||saved.window_id!==String(w.internalId)))};
    records[String(w.internalId)]=r;
    timer.timeout.connect(function(){if(r.restoring)restore(r);else persist(r);});
    [w.frameGeometryChanged,w.outputChanged,w.maximizedChanged,w.maximizeModeChanged,w.fullScreenChanged,w.windowClassChanged].forEach(function(s){
        if(s&&typeof s.connect==='function')s.connect(function(){schedule(r);});
    });
    if(w.interactiveMoveResizeStarted)w.interactiveMoveResizeStarted.connect(function(){r.restoring=false;r.blocked=false;r.missingOutput=false;r.userChoice=true;r.timer.stop();});
    if(w.interactiveMoveResizeFinished)w.interactiveMoveResizeFinished.connect(function(){r.restoring=false;r.blocked=false;persist(r);r.userChoice=false;});
    schedule(r);
}
workspace.windowAdded.connect(watch);
[workspace.screensChanged,workspace.screenOrderChanged].forEach(function(signal){if(signal&&typeof signal.connect==='function')signal.connect(function(){
    Object.keys(records).forEach(function(id){const r=records[id];if(!saved||r.userChoice||!main(r.w))return;
        if(!(workspace.screenOrder||workspace.screens||[]).some(o=>String(o.name)===saved.output)){
            r.restoring=false;r.blocked=true;r.missingOutput=true;r.timer.stop();
        } else if(r.missingOutput){r.missingOutput=false;r.restoring=true;r.blocked=false;r.step=0;r.attempt=0;schedule(r);}
    });
});});
workspace.windowRemoved.connect(function(w){const id=String(w.internalId),r=records[id];if(r){r.timer.stop();if(!r.restoring&&!r.blocked&&!persist(r,true)&&r.last)send(r.last);delete records[id];}});
(windows()||[]).forEach(watch);
print('CallasDiscord: memória persistente da janela principal ativada.');
callDBus(SERVICE,'/Placement',SERVICE,'ready',bootId);
})();'''.replace('INITIAL',json.dumps(saved)).replace('BOOT',json.dumps(boot_id)).replace('LEGACY',json.dumps(legacy))


def notify_ready():
    address=os.environ.get('NOTIFY_SOCKET')
    if address:
        with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as sock:
            sock.connect('\0'+address[1:] if address.startswith('@') else address)
            sock.sendall(b'READY=1\nSTATUS=Memoria persistente do Discord ativa')


def watch_discord():
    if os.geteuid()==0:raise ValueError('A memória do Discord deve rodar como usuário normal.')
    saved=read_state()
    STATE.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(STATE.parent/'discord-memory.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        import dbus
        import dbus.service
        from dbus.mainloop.glib import DBusGMainLoop
        from gi.repository import GLib
        DBusGMainLoop(set_as_default=True)
        session=dbus.SessionBus(private=True)
        owner=dbus.service.BusName(SERVICE,session,do_not_queue=True)
        loop=GLib.MainLoop();ready={'confirmed':False}
        class Receiver(dbus.service.Object):
            @dbus.service.method(SERVICE,in_signature='s',out_signature='b',sender_keyword='sender')
            def save(self,payload,sender=None):
                if sender!=session.get_name_owner('org.kde.KWin'):raise ValueError('Somente o KWin pode registrar esta janela.')
                if len(payload)>16384:raise ValueError('Registro de janela excedeu o limite.')
                save_state(json.loads(str(payload)));return True
            @dbus.service.method(SERVICE,in_signature='s',out_signature='b',sender_keyword='sender')
            def ready(self,boot_id,sender=None):
                if sender!=session.get_name_owner('org.kde.KWin'):raise ValueError('Confirmação fora do KWin.')
                ready['confirmed']=True;notify_ready();return True
        receiver=Receiver(owner,'/Placement')
        api=dbus.Interface(session.get_object('org.kde.KWin','/Scripting'),'org.kde.kwin.Scripting')
        name='callas-discord-memory'
        path=STATE.parent/'discord-memory.js'
        try:
            if api.isScriptLoaded(name) and not api.unloadScript(name):raise RuntimeError('Não foi possível substituir a memória anterior do Discord.')
            code=memory_script(saved,Path('/proc/sys/kernel/random/boot_id').read_text().strip(),None if saved else legacy_rule())
            path.write_text(code);path.chmod(0o600)
            number=int(api.loadScript(str(path),name,signature='ss'))
            if number<0:raise RuntimeError('KWin não carregou a memória do Discord.')
            dbus.Interface(session.get_object('org.kde.KWin','/Scripting/Script'+str(number)),'org.kde.kwin.Script').run()
            def startup_timeout():
                if not ready['confirmed']:loop.quit()
                return False
            GLib.timeout_add_seconds(12,startup_timeout)
            initial_owner=session.get_name_owner('org.kde.KWin')
            owner_watch=session.watch_name_owner('org.kde.KWin',lambda current:loop.quit() if str(current)!=str(initial_owner) else None)
            loop.run()
            raise RuntimeError('KWin encerrou ou não confirmou a memória do Discord; o serviço tentará novamente.')
        finally:
            try:api.unloadScript(name)
            finally:
                receiver.remove_from_connection();del receiver;del owner;session.close()


if __name__=='__main__':
    try:
        if sys.argv[1:]!=['--watch']:raise ValueError('Uso: callas-discord --watch')
        watch_discord()
    except Exception as error:
        print('Memória do Discord: '+str(error),file=sys.stderr);sys.exit(1)
