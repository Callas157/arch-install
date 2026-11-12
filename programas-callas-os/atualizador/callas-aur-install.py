#!/usr/bin/python3
"""Unattended initial AUR installation inside arch-chroot (no systemd/sudo).

Root resolves/installs dependencies and copies packages; recipes execute as the
new normal user. Checksums/PGP remain enabled. AUR install scripts remain trusted
third-party code; this does not certify packages as benign.
"""
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

NAME = re.compile(r'[A-Za-z0-9@_+][A-Za-z0-9@_.+\-]*\Z')
DEPENDENCY = re.compile(r'[A-Za-z0-9@_+][A-Za-z0-9@_.+\-]*(?:[<>=]+[A-Za-z0-9.:_+~\-]+)?\Z')
PINNED = {'nvidia-utils','nvidia-open-dkms','nvidia-open','nvidia-open-lts','lib32-nvidia-utils','nvidia-settings','libxnvctrl','opencl-nvidia','lib32-opencl-nvidia'}

def run(args, capture=False, check=True, cwd=None):
    print('+ ' + ' '.join(map(str,args)), flush=True)
    return subprocess.run(args, cwd=cwd, stdin=subprocess.DEVNULL, text=True,
                          stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.PIPE if capture else None, check=check)

def metadata(text):
    dependencies, packages, keys = [], [], []
    for line in text.splitlines():
        key, sep, value = line.strip().partition(' = ')
        if not sep: continue
        if key in ('depends','makedepends','checkdepends','depends_x86_64','makedepends_x86_64','checkdepends_x86_64'):
            if not DEPENDENCY.fullmatch(value): raise ValueError('Dependência inválida')
            if value not in dependencies: dependencies.append(value)
        elif key == 'pkgname':
            if not NAME.fullmatch(value): raise ValueError('Nome de pacote inválido')
            packages.append(value)
        elif key == 'validpgpkeys':
            if not re.fullmatch(r'[0-9A-Fa-f]{40}|[0-9A-Fa-f]{64}',value): raise ValueError('Fingerprint inválido')
            keys.append(value)
    if not packages: raise ValueError('.SRCINFO sem pacotes')
    return dependencies, packages, keys

class Installer:
    def __init__(self,user):
        self.account = pwd.getpwnam(user)
        if self.account.pw_uid == 0: raise ValueError('Compilação requer usuário normal')
        self.user = user; self.visiting = set()
    def as_user(self,args,**kwargs):
        env = ['PATH=/usr/bin:/bin','HOME='+self.account.pw_dir,'USER='+self.user,
               'LOGNAME='+self.user,'LANG=C.UTF-8','GIT_TERMINAL_PROMPT=0']
        return run(['/usr/bin/runuser','-u',self.user,'--','/usr/bin/setpriv','--no-new-privs','/usr/bin/env','-i',*env,*args],**kwargs)
    def missing(self,dependency):
        if not DEPENDENCY.fullmatch(dependency): raise ValueError('Dependência inválida')
        result = run(['/usr/bin/pacman','-T',dependency],capture=True,check=False)
        if result.returncode not in (0,127): raise RuntimeError(result.stderr or 'Consulta de dependência falhou')
        return result.returncode != 0
    def install(self,package,dependency=False):
        if not NAME.fullmatch(package) or package in PINNED: raise ValueError('Pacote inválido ou NVIDIA bloqueada')
        if not self.missing(package): return
        if package in self.visiting or len(self.visiting) >= 16: raise ValueError('Ciclo de dependências no AUR')
        self.visiting.add(package)
        try:
            query = 'https://aur.archlinux.org/rpc/v5/info?' + urllib.parse.urlencode({'arg[]':package})
            request = urllib.request.Request(query,headers={'User-Agent':'CallasOS-Installer'})
            with urllib.request.urlopen(request,timeout=60) as response:
                data = response.read(1024*1024+1)
            if len(data)>1024*1024: raise ValueError('Resposta AUR excedeu o limite')
            info = json.loads(data)
            result = next((item for item in info.get('results',[]) if item.get('Name')==package),None)
            if not result or not NAME.fullmatch(result.get('PackageBase','')): raise ValueError('Pacote não encontrado no AUR: '+package)
            base = result['PackageBase']
            with tempfile.TemporaryDirectory(prefix='callas-aur-install-',dir='/var/tmp') as temp:
                directory = Path(temp); directory.chmod(0o711)
                work = directory/'work'; work.mkdir(mode=0o700); os.chown(work,self.account.pw_uid,self.account.pw_gid)
                checkout=work/'source'
                self.as_user(['/usr/bin/git','-c','core.hooksPath=/dev/null','clone','--depth=1','https://aur.archlinux.org/'+base+'.git',str(checkout)])
                self.as_user(['/usr/bin/git','-C',str(checkout),'rev-parse','HEAD'])
                fd=os.open(checkout/'.SRCINFO',os.O_RDONLY|os.O_NOFOLLOW)
                with os.fdopen(fd) as stream: text=stream.read(1024*1024)
                dependencies, expected, keys = metadata(text)
                for requirement in dependencies:
                    if not self.missing(requirement): continue
                    name=re.split(r'[<>=]',requirement,maxsplit=1)[0]
                    if name in PINNED: raise ValueError('Dependência exigiria mudar a NVIDIA')
                    repo=run(['/usr/bin/pacman','-Si',name],capture=True,check=False)
                    if repo.returncode == 0:
                        run(['/usr/bin/pacman','-S','--needed','--noconfirm','--asdeps',requirement])
                    else: self.install(name,dependency=True)
                    if self.missing(requirement): raise ValueError('Versão de dependência não satisfeita: '+requirement)
                for key in keys:
                    available=self.as_user(['/usr/bin/gpg','--batch','--list-keys',key],capture=True,check=False)
                    if available.returncode:
                        self.as_user(['/usr/bin/gpg','--batch','--keyserver','hkps://keyserver.ubuntu.com','--recv-keys',key])
                # No -s/-i: makepkg never invokes sudo/pacman. Root handles those steps.
                self.as_user(['/usr/bin/makepkg','--cleanbuild','--force','--noconfirm','--log'],cwd=checkout)
                destination=directory/'packages'; destination.mkdir(mode=0o700)
                archives=[]; produced=set()
                for source in sorted(checkout.glob('*.pkg.tar.*')):
                    if source.name.endswith('.sig'): continue
                    fd=os.open(source,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
                    with os.fdopen(fd,'rb') as stream:
                        info=os.fstat(stream.fileno())
                        if not stat.S_ISREG(info.st_mode) or info.st_uid!=self.account.pw_uid or info.st_size>8*1024**3: raise ValueError('Artefato inválido')
                        target=destination/source.name
                        with target.open('xb') as output: shutil.copyfileobj(stream,output)
                    fields=run(['/usr/bin/pacman','-Qp',str(target)],capture=True).stdout.split()
                    if len(fields)==2 and fields[0].endswith('-debug') and fields[0][:-6] in expected: continue
                    if len(fields)!=2 or fields[0] not in expected or fields[0] in PINNED: raise ValueError('Pacote produzido inesperado')
                    archives.append(str(target)); produced.add(fields[0])
                if package not in produced: raise ValueError('Pacote solicitado não foi produzido')
                run(['/usr/bin/pacman','-U','--needed','--noconfirm',*(['--asdeps'] if dependency else []),*archives])
        finally: self.visiting.remove(package)

def main():
    if os.geteuid()!=0 or len(sys.argv)<3: raise ValueError('Uso interno: callas-aur-install USUARIO PACOTE...')
    installer=Installer(sys.argv[1])
    for package in sys.argv[2:]: installer.install(package)

if __name__=='__main__':
    try: main()
    except Exception as error:
        print('Instalação AUR interrompida: '+str(error),file=sys.stderr); sys.exit(1)
