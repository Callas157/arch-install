#!/usr/bin/python3
"""Per-user, content-based update checkpoints and verified visual assets."""
import hashlib
import importlib.util
from importlib.machinery import SourceFileLoader
import json
import os
from pathlib import Path
import pwd
import re
import sys
import tempfile
import urllib.request

STATE=Path('/var/lib/callas-os')
DEPENDENCIES={
    'security':('callas-uninstall.py','callas-apps.py','callas-apps.json','callas-update-gui.py','callas-update-gui-install.py','callas-baterias-install.py','callas-baterias.tar.gz','callas-security.sh','callas-game-logs.py','callas-native.py','callas-kernel-policy.py'),
    'apps':('callas-apps.py','callas-apps.json','callas-spotify-permissions.sh','callas-aur-install.py','callas-native.py','callas-kernel-check.sh'),
    'tools':('callas-monitores.py','callas-janelas.py','callas-inicio-kde.sh','callas-kde-desligamento-login.sh'),
    'boot':('callas.script','callas.plymouth','callas-boot-theme.py'),
    'flatpaks':('callas-apps.py','callas-apps.json'), 'browser':(), 'desktop':(),
    'session':('callas-game-logs.py','callas-inicio-kde.sh','callas-janelas.py','callas-nekofetch.sh','callas-version.py'),
}
REQUIRED={
    'security':('/usr/local/lib/callas-update/callas-update-gui.py','/usr/local/libexec/callas-update-gui-install','/usr/local/share/callas-os/baterias/callas_baterias.py','/usr/local/libexec/callas-baterias-install','/etc/systemd/user/callas-baterias.service','/etc/udev/rules.d/71-callas-baterias.rules','/etc/xdg/autostart/callas-baterias.desktop','/etc/callas-os/security-version','/etc/systemd/system/callas-game-events.service','/etc/sudoers.d/20-callas-security','/etc/udev/rules.d/70-callas-g920.rules','/etc/pacman.d/hooks/00-callas-kernel-policy.hook','/etc/pacman.d/hooks/00-callas-kernel-deny-remove.hook'),
    'apps':(),
    'tools':('/usr/local/share/applications/io.github.Callas157.Monitores.desktop','/etc/systemd/user/callas-janelas.service'),
    'boot':('/etc/grub.d/09_callas','/boot/grub/themes/callas/loading.cfg','/boot/grub/themes/callas/background.png','/boot/grub/grub.cfg','/boot/initramfs-linux.img','/boot/initramfs-linux-lts.img'),
    'flatpaks':(), 'browser':('/etc/brave/policies/managed/callas-bonjourr.json',), 'desktop':('/etc/xdg/kicker-extra-favoritesrc',), 'session':('/etc/systemd/user/callas-game-logs.service',),
}


# Check the deployed helpers too, so a missing/changed helper cannot be hidden
# by an unchanged release SHA or by otherwise intact desktop anchors.
REQUIRED['security'] += tuple('/usr/local/libexec/' + name for name in (
    'callas-uninstall', 'callas-apps', 'callas-apps.json', 'callas-update-state', 'callas-native',
    'callas-aur', 'callas-aur-install', 'callas-autostart', 'callas-kernel-policy',
    'callas-game-logs', 'callas-spotify-permissions', 'callas-version',
    'callas-nekofetch', 'callas-release', 'callas-logs', 'callas-kernel-check',
    'put-update', 'callas-storage', 'callas-maintenance'))
REQUIRED['tools'] += tuple('/usr/local/libexec/' + name for name in (
    'callas-monitores', 'callas-janelas', 'callas-inicio-kde', 'callas-kde-desligamento-login'))
for application_phase in ('security', 'apps', 'flatpaks'):
    REQUIRED[application_phase] += ('/var/lib/callas-os/apps-managed-' + application_phase + '.json',)


def atomic(path,data,mode=0o600):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix='.callas-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno());os.fchmod(stream.fileno(),mode)
        os.replace(temp,path)
    finally:Path(temp).unlink(missing_ok=True)

def assets(stage):
    data=json.loads((stage/'update-assets.json').read_text())
    if not re.fullmatch('[0-9a-f]{40}',data['commit']):raise ValueError('Commit de assets inválido')
    return data

def fingerprint(phase,stage):
    if phase not in DEPENDENCIES:raise ValueError('Etapa desconhecida')
    source=(stage/'callas-config-update.sh').read_text()
    begin='# CALLAS_PHASE_BEGIN '+phase+'\n';end='# CALLAS_PHASE_END '+phase+'\n'
    if source.count(begin)!=1 or source.count(end)!=1:raise ValueError('Delimitadores de etapa inválidos')
    content=source.split(begin,1)[1].split(end,1)[0].encode()
    h=hashlib.sha256(b'callas-checkpoint-1\0'+content)
    for name in DEPENDENCIES[phase]:h.update(name.encode()+b'\0'+(stage/name).read_bytes())
    if phase in ('boot','browser','desktop'):
        for path,sha in sorted(assets(stage)['assets'].items()):
            if (phase=='boot' and path.startswith(('grub/','plymouth/'))) or (phase=='desktop' and path.startswith('wallpapers/')) or (phase=='browser' and path.startswith('bonjourr/')):
                h.update((path+'\0'+sha).encode())
    return h.hexdigest()

def state_file(user):
    account=pwd.getpwnam(user)
    if account.pw_uid==0:raise ValueError('Usuário normal necessário')
    return STATE/('update-state-'+str(account.pw_uid)+'.json')

def state(user):
    try:return json.loads(state_file(user).read_text())
    except FileNotFoundError:return {}

def application_status(phase):
    if phase not in ('security', 'apps', 'flatpaks'):
        return {}
    path = Path(__file__).with_name('callas-apps.py')
    if not path.exists(): path = path.with_suffix('')
    loader = SourceFileLoader('state_apps', str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    helper = importlib.util.module_from_spec(spec); loader.exec_module(helper)
    entries = [entry for entry in helper.catalog() if entry['phase'] == phase]
    managed = helper.previous(phase)
    installed = helper.inventory()
    names = {(helper.family(entry), entry['name']) for entry in [*entries, *managed]}
    return {'installed': {source + ':' + name: installed[source].get(name) for source, name in sorted(names)},
            'pending': helper.plan(entries, installed, managed)}


def installed_files(phase):
    """Observe managed anchors without hashing user data or volatile directories."""
    result = {'_applications': application_status(phase)}
    for name in REQUIRED[phase]:
        path = Path(name)
        if path.is_symlink():
            result[name] = {'link': os.readlink(path)}
        elif path.is_file():
            result[name] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                            'mode': path.stat().st_mode & 0o777}
        elif path.is_dir():
            result[name] = {'directory': True}
        else:
            result[name] = None
    if phase == 'security':
        for folder in ('/usr/local/share/callas-os/baterias',
                       '/usr/local/share/plasma/plasmoids/br.com.callas.ordem-baterias'):
            tree = Path(folder)
            result[folder] = {
                str(p.relative_to(tree)): ('link:' + os.readlink(p) if p.is_symlink()
                    else hashlib.sha256(p.read_bytes()).hexdigest())
                for p in sorted(tree.rglob('*'))
                if (p.is_file() or p.is_symlink()) and '__pycache__' not in p.parts
            }
    return result

def intact(user):
    data = state(user)
    observed = data.get('_installed', {})
    return all(phase in data and phase in observed
               and observed[phase] == installed_files(phase)
               and not application_status(phase).get('pending')
               and all(Path(p).exists() for p in REQUIRED[phase])
               for phase in DEPENDENCIES)


def needed(phase,stage,user,force=False):
    data = state(user)
    recorded = data.get('_installed', {})
    return (force or data.get(phase) != fingerprint(phase,stage)
            or phase not in recorded or recorded[phase] != installed_files(phase)
            or bool(application_status(phase).get('pending'))
            or any(not Path(p).exists() for p in REQUIRED[phase]))

def complete(phase,stage,user):
    data=state(user);data[phase]=fingerprint(phase,stage)
    data.setdefault('_installed', {})[phase]=installed_files(phase)
    atomic(state_file(user),(json.dumps(data,sort_keys=True)+'\n').encode())

def blob(data):return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()

def asset(stage,relative,destination):
    if relative.startswith('/') or '..' in Path(relative).parts:raise ValueError('Caminho de asset inválido')
    manifest=assets(stage);expected=manifest['assets'][relative]
    if not re.fullmatch('[0-9a-f]{40}',expected):raise ValueError('Blob de asset inválido')
    destination=Path(destination)
    if not destination.is_absolute() or destination.is_symlink():raise ValueError('Destino de asset inválido')
    if destination.is_file() and blob(destination.read_bytes())==expected:return False
    url='https://raw.githubusercontent.com/Callas157/arch-install/'+manifest['commit']+'/assets/'+relative
    request=urllib.request.Request(url,headers={'User-Agent':'CallasOS-Updater'})
    with urllib.request.urlopen(request,timeout=120) as response:
        if not response.url.startswith('https://'):raise ValueError('Redirecionamento de asset inválido')
        data=response.read(32*1024**2+1)
    if len(data)>32*1024**2 or blob(data)!=expected:raise ValueError('Asset diferente do blob verificado: '+relative)
    atomic(destination,data,0o644)
    return True

def main():
    if os.geteuid()!=0:raise ValueError('Uso administrativo interno')
    args=sys.argv[1:]
    if len(args)==2 and args[0]=='--intact':
        return 0 if intact(args[1]) else 1
    if len(args)==4 and args[0]=='--asset':
        print('changed' if asset(Path(args[1]),args[2],args[3]) else 'unchanged');return 0
    if len(args) not in (4,5) or args[0] not in ('--needed','--complete'):raise ValueError('Argumentos inválidos')
    action,phase,stage,user=args[:4]
    if len(args)==5 and args[4]!='--force':raise ValueError('Argumento inválido')
    if action=='--needed':return 0 if needed(phase,Path(stage),user,len(args)==5) else 1
    complete(phase,Path(stage),user);return 0

if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:print('Erro no controle de atualização: '+str(exc),file=sys.stderr);sys.exit(2)
