#!/usr/bin/python3
"""Install the optional clock as the desktop user; never rewrite Plasma's rc file."""
import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path, PurePosixPath
import pwd
import stat
import subprocess
import sys
import tempfile
import time
import zipfile

PLUGIN = 'com.github.prayag2.modernclock'
PAYLOAD = Path('/usr/local/share/callas-os/relogio-moderno.plasmoid')
HELPER = Path('/usr/local/libexec/callas-widget')
CORNERS = ('top-left', 'top-right', 'bottom-left', 'bottom-right')
_qt_application = None


def user_path(variable, fallback):
    path = Path(os.environ.get(variable, str(Path.home() / fallback)))
    if not path.is_absolute(): raise ValueError(variable + ' precisa ser absoluto.')
    return path


def safe_directory(path):
    for parent in (*reversed(path.parents), path):
        if parent.is_symlink(): raise ValueError('Diretório simbólico não permitido: ' + str(parent))
    path.mkdir(parents=True, exist_ok=True)
    return path


def atomic(path, data):
    safe_directory(path.parent)
    if path.is_symlink(): raise ValueError('Arquivo simbólico não permitido.')
    fd, temporary = tempfile.mkstemp(prefix='.callas-widget-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno()); os.fchmod(stream.fileno(), 0o600)
        os.replace(temporary, path)
    finally: Path(temporary).unlink(missing_ok=True)


def state_directory(): return user_path('XDG_STATE_HOME', '.local/state') / 'callas-os'


@contextmanager
def user_lock():
    path = safe_directory(state_directory()) / 'widget.lock'
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def installed_package():
    bases = [user_path('XDG_DATA_HOME', '.local/share')]
    bases += [Path(p) for p in os.environ.get('XDG_DATA_DIRS', '/usr/local/share:/usr/share').split(':') if p.startswith('/')]
    for base in bases:
        for metadata in sorted((base / 'plasma/plasmoids').glob('*/metadata.json')):
            try:
                if (json.loads(metadata.read_text())['KPlugin']['Id'] == PLUGIN
                        and (metadata.parent / 'contents/ui/main.qml').is_file()):
                    return metadata.parent
            except (OSError, ValueError, KeyError, TypeError): continue
    return None


def package_installed(): return installed_package() is not None


def install_package(payload=PAYLOAD):
    existing = installed_package()
    if existing is not None: return existing
    # Validate the entire archive before creating any destination directory.
    files = {}
    with zipfile.ZipFile(payload) as archive:
        if len(archive.infolist()) > 200: raise ValueError('Pacote do relógio excedeu o limite.')
        total = 0
        for member in archive.infolist():
            path = PurePosixPath(member.filename)
            if (path.is_absolute() or '..' in path.parts or '\\' in member.filename
                    or not path.parts or stat.S_ISLNK(member.external_attr >> 16)):
                raise ValueError('Caminho inválido no pacote do relógio.')
            total += member.file_size
            if total > 4 * 1024 * 1024: raise ValueError('Pacote do relógio excedeu o limite.')
            if member.is_dir(): continue
            if len(path.parts) < 2: raise ValueError('Estrutura inválida do pacote do relógio.')
            relative = PurePosixPath(*path.parts[1:]).as_posix()
            if relative in files: raise ValueError('Arquivo duplicado no pacote do relógio.')
            files[relative] = archive.read(member)
    try: identity = json.loads(files['metadata.json'])['KPlugin']['Id']
    except (ValueError, KeyError, TypeError): raise ValueError('Metadados inválidos do relógio.')
    if identity != PLUGIN or 'contents/ui/main.qml' not in files:
        raise ValueError('Identidade inválida do relógio.')
    parent = safe_directory(user_path('XDG_DATA_HOME', '.local/share') / 'plasma/plasmoids')
    target = parent / PLUGIN
    if target.exists() or target.is_symlink(): raise ValueError('Pasta existente do relógio está incompleta; preserve-a antes de reinstalar.')
    with tempfile.TemporaryDirectory(prefix='.callas-clock-', dir=parent) as temporary:
        root = Path(temporary) / PLUGIN; root.mkdir(mode=0o755)
        for name, data in files.items():
            path = root / name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data); path.chmod(0o644)
        for path in root.rglob('*'):
            if path.is_dir(): path.chmod(0o755)
        os.rename(root, target)
    return target


def screens():
    from PySide6.QtGui import QGuiApplication
    global _qt_application
    _qt_application = QGuiApplication.instance() or QGuiApplication(['callas-widget'])
    app = _qt_application
    result = []
    for screen in app.screens():
        geometry, area = screen.geometry(), screen.availableGeometry()
        result.append(dict(name=screen.name(), primary=screen is app.primaryScreen(),
            width=geometry.width(), height=geometry.height(),
            area=dict(x=area.x()-geometry.x(), y=area.y()-geometry.y(), width=area.width(), height=area.height())))
    if not result: raise RuntimeError('Nenhum monitor ativo encontrado na sessão gráfica.')
    return result


def plasma_object():
    import dbus
    return dbus.SessionBus().get_object('org.kde.plasmashell', '/PlasmaShell')


def evaluate(script):
    import dbus
    result = str(dbus.Interface(plasma_object(), 'org.kde.PlasmaShell').evaluateScript(script, timeout=30))
    if 'CALLAS_WIDGET_OK:' not in result:
        raise RuntimeError('O Plasma não confirmou a operação do relógio: ' + result)
    return result


PLASMA_HELPERS = r'''
function clocks() {
    var ds=desktopsForActivity(currentActivity()), found=[];
    for(var i=0;i<ds.length;++i) {
        var ws=ds[i].widgets(p.plugin);
        for(var j=0;j<ws.length;++j) found.push({desktop:ds[i],widget:ws[j]});
    }
    return found;
}
function snapshot(widget,group) {
    widget.currentConfigGroup=group;
    var keys=widget.configKeys,groups=widget.configGroups,saved={path:group,values:{},children:[]};
    for(var k=0;k<keys.length;++k) saved.values[keys[k]]=widget.readConfig(keys[k]);
    for(var k=0;k<groups.length;++k) saved.children.push(snapshot(widget,group.concat([groups[k]])));
    return saved;
}
function restore(widget,saved) {
    widget.currentConfigGroup=saved.path;
    Object.keys(saved.values).forEach(function(key){ widget.writeConfig(key,saved.values[key]); });
    for(var k=0;k<saved.children.length;++k) restore(widget,saved.children[k]);
}
function reply(data) { print('CALLAS_WIDGET_OK:'+JSON.stringify(data)); }
'''


def script(body, params):
    return '(function(){var p='+json.dumps(dict(params,plugin=PLUGIN))+';\n'+PLASMA_HELPERS+body+'\n})();'


def result(script_text):
    output=evaluate(script_text)
    try: return json.loads(output.rsplit('CALLAS_WIDGET_OK:',1)[1].strip())
    except (ValueError,IndexError): raise RuntimeError('Resposta inválida do Plasma ao configurar o relógio.')


def position_script(connector, corner, area, *, initial=False):
    if corner not in CORNERS: raise ValueError('Canto inválido.')
    if (set(area) != {'x','y','width','height'} or any(type(n) is not int for n in area.values())
            or area['width'] < 96 or area['height'] < 96):
        raise ValueError('Área do monitor inválida.')
    return script(r'''
    var matches=clocks();
    if(p.initial && matches.length) { reply({preserve:true}); return; }
    if(matches.length>1) throw new Error('Há vários relógios nesta atividade. Use o modo de edição para escolher qual mover.');
    var screen=screenForConnector(p.connector),target=screen>=0?desktopForScreen(screen):null;
    if(!target || target.screen!==screen) throw new Error('Monitor desconectado. Atualize a lista.');
    var old=matches.length?matches[0].widget:null, g=old?old.geometry:null;
    var width=g&&g.width>0?g.width:656,height=g&&g.height>0?g.height:176;
    width=Math.min(width,p.area.width-48);height=Math.min(height,p.area.height-48);
    var x=p.area.x+24,y=p.area.y+24;
    if(p.corner.indexOf('right')>=0)x=p.area.x+p.area.width-width-24;
    if(p.corner.indexOf('bottom')===0)y=p.area.y+p.area.height-height-24;
    var config=old?snapshot(old,[]):null;
    // userBackgroundHints defaults to StandardBackground even when no user
    // preference exists. Only a saved key is an explicit background choice.
    var previous=old?{id:old.id,desktop:matches[0].desktop.id,geometry:g,
        config:config,shortcut:old.globalShortcut,locked:old.locked,hints:config.values.UserBackgroundHints||null}:null;
    reply({schema:1,activity:currentActivity(),connector:p.connector,target:target.id,
        geometry:{x:x,y:y,width:width,height:height},previous:previous});
''', dict(connector=connector,corner=corner,area=area,initial=initial))


def transaction_script(plan, operation, *, widget_id=None, rollback=False):
    return script(r'''
    if(currentActivity()!==p.plan.activity) throw new Error('A atividade mudou durante a operação. Volte à atividade anterior.');
    var found=clocks(),previous=p.plan.previous;
    if(p.operation==='live') {
        reply(found.map(function(a){ return {id:a.widget.id,desktop:a.desktop.id,geometry:a.widget.geometry}; }));return;
    }
    if(p.operation==='remove') {
        var item=found.find(function(a){return a.widget.id===p.id;});
        if(!item) {reply({removed:true});return;}
        if(previous && p.id===previous.id && JSON.stringify(snapshot(item.widget,[]))!==JSON.stringify(previous.config))
            throw new Error('As configurações do relógio mudaram. Tente novamente.');
        item.widget.remove();reply({removed:true});return;
    }
    if(p.operation==='create') {
        if(found.length) throw new Error('Aguarde a remoção anterior ou use o modo de edição para escolher o relógio.');
        var target=desktopById(p.rollback?previous.desktop:p.plan.target);
        if(!target || (!p.rollback && target.screen!==screenForConnector(p.plan.connector)))
            throw new Error('Monitor desconectado. Atualize a lista.');
        var g=p.rollback?previous.geometry:p.plan.geometry;
        var fresh=target.addWidget(p.plugin,g.x,g.y,g.width,g.height);
        if(!fresh || fresh.type!==p.plugin) throw new Error('Não foi possível criar o relógio.');
        try {
            if(previous) {
                restore(fresh,previous.config);
                var explicitHints=previous.config.values.UserBackgroundHints;
                fresh.userBackgroundHints=typeof explicitHints==='string' && explicitHints?explicitHints:'NoBackground';
                if(typeof previous.shortcut==='string') fresh.globalShortcut=previous.shortcut;
                if(typeof previous.locked==='boolean') fresh.locked=previous.locked;
            } else {
                fresh.currentConfigGroup=['Appearance'];fresh.writeConfig('day_font_size',50);
                fresh.userBackgroundHints='NoBackground';
            }
        } catch(error) {fresh.remove();throw error;}
        reply({id:fresh.id});return;
    }
    throw new Error('Operação inválida.');
''',dict(plan=plan,operation=operation,id=widget_id,rollback=rollback))


def live_widgets(plan): return result(transaction_script(plan,'live'))


def wait_empty(plan):
    for attempt in range(10):
        if not live_widgets(plan): return
        time.sleep(.05)
    raise RuntimeError('O Plasma ainda não liberou o relógio anterior. Tente novamente.')


def verify_position(plan, widget_id, *, rollback=False):
    expected=plan['previous']['geometry'] if rollback else plan['geometry']
    for attempt in range(10):
        widgets=live_widgets(plan)
        item=next((item for item in widgets if item['id']==widget_id),None)
        if item and all(abs(item['geometry'][key]-expected[key])<=32 for key in ('x','y','width','height')):
            return
        time.sleep(.05)
    raise RuntimeError('O canto está ocupado ou o Plasma não aplicou a posição. Libere espaço usando o modo de edição.')


def rollback_move(plan, recovery):
    widgets=live_widgets(plan)
    if len(widgets)==1 and widgets[0]['id']==plan['previous']['id']:
        recovery.unlink(missing_ok=True);return
    # Only remove an instance created by this recorded transaction.
    if widgets:
        if len(widgets)!=1 or widgets[0]['id']!=plan.get('created'):
            raise RuntimeError('Há outra instância do relógio. Preserve-a pelo modo de edição antes de recuperar a posição anterior.')
        result(transaction_script(plan,'remove',widget_id=plan['created']))
    wait_empty(plan)
    restored=result(transaction_script(plan,'create',rollback=True))
    plan['created']=restored['id'];atomic(recovery,json.dumps(plan).encode())
    verify_position(plan,restored['id'],rollback=True)
    recovery.unlink(missing_ok=True)


def leave_edit_mode():
    import dbus
    properties=dbus.Interface(plasma_object(),'org.freedesktop.DBus.Properties')
    if properties.Get('org.kde.PlasmaShell','editMode'):
        properties.Set('org.kde.PlasmaShell','editMode',dbus.Boolean(False))
        # Desktop views animate their scale when leaving the editor. Geometry
        # must be captured after that transition, in ordinary scene coordinates.
        time.sleep(.35)


def move(connector, corner, *, initial=False):
    screen=next((screen for screen in screens() if screen['name']==connector),None)
    if screen is None: raise ValueError('Monitor desconectado. Atualize a lista e escolha novamente.')
    if not package_installed(): raise ValueError('Instale o Relógio Moderno antes de configurar.')
    leave_edit_mode()
    recovery=state_directory()/'widget-recovery.json'
    if recovery.is_symlink(): raise ValueError('Registro de recuperação simbólico não permitido.')
    if recovery.exists(): rollback_move(json.loads(recovery.read_text()),recovery)
    plan=result(position_script(connector,corner,screen['area'],initial=initial))
    if plan.get('preserve'): return
    if plan['previous']: atomic(recovery,json.dumps(plan).encode())
    try:
        if plan['previous']:
            result(transaction_script(plan,'remove',widget_id=plan['previous']['id']))
            # destroy() uses deleteLater: separate calls and confirm layout release.
            wait_empty(plan)
        created=result(transaction_script(plan,'create'))
        plan['created']=created['id']
        if plan['previous']: atomic(recovery,json.dumps(plan).encode())
        verify_position(plan,created['id'])
    except Exception as error:
        if plan['previous']:
            try: rollback_move(plan,recovery)
            except Exception as recovery_error:
                raise RuntimeError(str(error)+' A recuperação ficou pendente; as configurações foram preservadas. '+str(recovery_error)) from error
            raise RuntimeError(str(error)+' O relógio foi restaurado na posição anterior.') from error
        if plan.get('created') is not None:
            result(transaction_script(plan,'remove',widget_id=plan['created']))
        raise
    recovery.unlink(missing_ok=True)


def install():
    install_package()
    available = screens()
    ordered = sorted(available, key=lambda screen: (not screen['primary'], screen['name']))
    target = ordered[1] if len(ordered) > 1 else ordered[0]
    move(target['name'], 'top-left', initial=True)


def appearance_script(*, apply=False):
    return script(r'''
    var ds=desktops(), found=[];
    for(var i=0;i<ds.length;++i) {
        var ws=ds[i].widgets(p.plugin);
        for(var j=0;j<ws.length;++j) {
            var w=ws[j];w.currentConfigGroup=[];
            if(p.apply) w.userBackgroundHints='NoBackground';
            found.push({id:w.id,desktop:ds[i].id,hints:w.userBackgroundHints,
                configured:w.readConfig('UserBackgroundHints',''),geometry:w.geometry});
        }
    }
    reply(found);
''',dict(apply=apply))


def repair_appearance(*, migrate=False):
    marker=state_directory()/'clock-background-v1.complete'
    if migrate and marker.exists(): return
    # Update offers the clock but never installs it just to repair its style.
    if not package_installed(): return
    autostart=user_path('XDG_CONFIG_HOME','.config')/'autostart/callas-clock-appearance.desktop'
    atomic(autostart, ('[Desktop Entry]\nType=Application\nName=Ajustar aparência do Relógio Moderno\n'
        'Exec=/usr/local/libexec/callas-widget --migrate-appearance\nIcon=clock\n'
        'OnlyShowIn=KDE;\nX-KDE-autostart-phase=2\n').encode())
    try:
        before=result(appearance_script())
        if any(item['hints']!='NoBackground' for item in before):
            record=state_directory()/'clock-appearance-before.json'
            if not record.exists(): atomic(record,json.dumps(before).encode())
            result(appearance_script(apply=True))
        after=result(appearance_script())
        if any(item['hints']!='NoBackground' for item in after):
            raise RuntimeError('O Plasma não confirmou a remoção do fundo do relógio.')
        atomic(marker,b'1\n');autostart.unlink(missing_ok=True)
        print('Relógio Moderno: fundo removido; instâncias e posições preservadas.')
    except Exception as error:
        if not migrate: raise
        print('Relógio Moderno: ajuste de fundo pendente para o próximo login. '+str(error))


def prepare_first_login():
    install_package()
    pending = state_directory() / 'clock-first-login.pending'
    if pending.exists(): return
    if (state_directory() / 'clock-first-login.complete').exists(): return
    atomic(pending, b'1\n')
    autostart = user_path('XDG_CONFIG_HOME', '.config') / 'autostart/callas-clock.desktop'
    atomic(autostart, ('[Desktop Entry]\nType=Application\nName=Relógio Moderno Callas OS\n'
        'Exec=/usr/local/libexec/callas-widget --first-login\nIcon=clock\n'
        'OnlyShowIn=KDE;\nX-KDE-autostart-phase=2\n').encode())


def first_login():
    pending = state_directory() / 'clock-first-login.pending'
    if not pending.exists(): return
    install()
    atomic(state_directory() / 'clock-first-login.complete', b'1\n')
    pending.unlink()
    (user_path('XDG_CONFIG_HOME', '.config') / 'autostart/callas-clock.desktop').unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description='Relógio Moderno Callas OS')
    action = parser.add_mutually_exclusive_group(required=True)
    for flag in ('install','screens','edit','first-login','prepare-first-login','repair-appearance','migrate-appearance'):
        action.add_argument('--'+flag, action='store_true')
    action.add_argument('--move', nargs=2, metavar=('MONITOR','CANTO'))
    action.add_argument('--prepare-clean', metavar='USUARIO')
    args = parser.parse_args()
    if args.prepare_clean:
        if os.geteuid() != 0: raise ValueError('Preparação da instalação requer root.')
        account = pwd.getpwnam(args.prepare_clean)
        if account.pw_uid == 0: raise ValueError('Usuário normal necessário.')
        subprocess.run(['/usr/bin/runuser','-u',account.pw_name,'--','/usr/bin/env',
            'HOME='+account.pw_dir,'XDG_DATA_HOME='+account.pw_dir+'/.local/share',
            'XDG_CONFIG_HOME='+account.pw_dir+'/.config','XDG_STATE_HOME='+account.pw_dir+'/.local/state',
            str(HELPER),'--prepare-first-login'], check=True)
        return
    if os.geteuid() == 0: raise ValueError('Execute esta função na sessão do usuário normal.')
    if args.screens:
        print(json.dumps(screens(), ensure_ascii=False)); return
    with user_lock():
        if args.install: install()
        elif args.move: move(*args.move)
        elif args.prepare_first_login: prepare_first_login()
        elif args.first_login: first_login()
        elif args.repair_appearance: repair_appearance()
        elif args.migrate_appearance: repair_appearance(migrate=True)
        elif args.edit:
            import dbus
            dbus.Interface(plasma_object(), 'org.freedesktop.DBus.Properties').Set('org.kde.PlasmaShell','editMode',dbus.Boolean(True))
        print('Relógio Moderno: operação concluída.')


if __name__ == '__main__':
    try: main()
    except Exception as error:
        print('Relógio Moderno: '+str(error), file=sys.stderr); sys.exit(1)
