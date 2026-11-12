#!/usr/bin/python3
"""Per-user, content-based update checkpoints and verified visual assets."""
import hashlib
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
    'security':('callas-security.sh',),
    'apps':('callas-spotify-permissions.sh','callas-aur-install.py'),
    'tools':('callas-monitores.py','callas-janelas.py','callas-inicio-kde.sh','callas-kde-desligamento-login.sh'),
    'boot':('callas.script','callas.plymouth'),
    'flatpaks':(), 'browser':(), 'desktop':(),
    'session':('callas-inicio-kde.sh','callas-janelas.py','callas-nekofetch.sh','callas-version.py'),
}
REQUIRED={
    'security':('/etc/callas-os/security-version','/etc/sudoers.d/20-callas-security'),
    'apps':('/opt/spotify/Apps',),
    'tools':('/usr/local/share/applications/io.github.Callas157.Monitores.desktop','/etc/systemd/user/callas-janelas.service'),
    'boot':('/boot/grub/grub.cfg','/boot/initramfs-linux.img','/boot/initramfs-linux-lts.img'),
    'flatpaks':(), 'browser':('/etc/brave/policies/managed/callas-bonjourr.json',), 'desktop':('/etc/xdg/kicker-extra-favoritesrc',), 'session':(),
}

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

def needed(phase,stage,user,force=False):
    return force or state(user).get(phase)!=fingerprint(phase,stage) or any(not Path(p).exists() for p in REQUIRED[phase])

def complete(phase,stage,user):
    data=state(user);data[phase]=fingerprint(phase,stage)
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
