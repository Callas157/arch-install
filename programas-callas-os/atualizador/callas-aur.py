#!/usr/bin/python3
"""Unattended AUR maintenance: Paru resolves; isolated makepkg builds; root installs.

No sudo capability is granted to the build account. This is not a malware
review: AUR packages/install scripts remain trusted third-party code.
"""
import os
from pathlib import Path
import pwd
import re
import shutil
import stat
import subprocess
import sys
import tempfile

BUILD_USER = 'callas-aur'
BUILDS_ROOT = Path('/var/lib/callas-os/aur-builds')
PINNED = frozenset(('nvidia-utils', 'nvidia-open-dkms', 'nvidia-open', 'nvidia-open-lts',
                    'lib32-nvidia-utils', 'nvidia-settings', 'libxnvctrl', 'opencl-nvidia', 'lib32-opencl-nvidia'))
NAME = re.compile(r'[a-zA-Z0-9@_+][a-zA-Z0-9@_.+\-]*\Z')

class RequiresGeneral(ValueError):
    pass

def name(value):
    if not NAME.fullmatch(value) or value in ('.', '..'):
        raise ValueError('Nome de pacote inválido: ' + repr(value))
    return value

def plan(text, apps_only=False):
    result = []
    for line in text.splitlines():
        fields = line.split()
        if not fields:
            continue
        if fields[0] in ('MISSING', 'CONFLICT'):
            raise ValueError('Plano AUR não resolvido: ' + line)
        if len(fields) < 4 or fields[1] not in ('TARGET', 'DEP', 'MAKE'):
            raise ValueError('Formato inesperado no plano do Paru: ' + line)
        if fields[0] == 'INSTALL' and len(fields) == 4:
            if apps_only:
                raise RequiresGeneral('O aplicativo exige dependências dos repositórios: use Atualizar geral')
            repo, pkg = name(fields[2]), name(fields[3])
            if pkg in PINNED:
                raise ValueError('Dependência exigiria alterar a NVIDIA preservada: ' + pkg)
            result.append(('INSTALL', fields[1], repo, [pkg]))
        elif fields[0] == 'AUR':
            base, pkgs = name(fields[2]), [name(pkg) for pkg in fields[3:]]
            if apps_only and any(pkg.startswith(('linux', 'systemd', 'grub', 'pacman', 'glibc', 'mkinitcpio',
                                                'nvidia', 'lib32-nvidia', 'opencl-nvidia', 'lib32-opencl-nvidia', 'plasma', 'kwin')) for pkg in pkgs):
                raise RequiresGeneral('Pacote de base preservado; use Atualizar geral')
            if set(pkgs) & PINNED or base in PINNED:
                raise ValueError('O AUR não pode substituir a NVIDIA preservada')
            result.append(('AUR', fields[1], base, pkgs))
        else:
            raise ValueError('Ação não reconhecida no plano do Paru: ' + line)
    return result

def command(args, capture=False, empty_ok=False):
    print('+ ' + ' '.join(map(str, args)), flush=True)
    if empty_ok:
        result = subprocess.run(args, check=False, text=True, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode and not (result.returncode == 1 and not result.stdout and not result.stderr):
            raise subprocess.CalledProcessError(result.returncode, args, result.stdout, result.stderr)
        if result.stderr:
            print(result.stderr, file=sys.stderr, end='')
        return result
    return subprocess.run(args, check=True, text=True, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE if capture else None)

class Builder:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.work = self.directory / 'work'
        self.work.mkdir(mode=0o700)
        account = pwd.getpwnam(BUILD_USER)
        if account.pw_uid == 0 or account.pw_shell != '/usr/bin/nologin':
            raise ValueError('Conta de compilação inválida')
        self.uid = account.pw_uid
        os.chown(self.work, account.pw_uid, account.pw_gid)
        self.env = {'HOME': str(self.work / 'home'), 'PATH': '/usr/bin:/bin',
                    'LANG': 'C.UTF-8', 'USER': BUILD_USER, 'LOGNAME': BUILD_USER,
                    'XDG_CACHE_HOME': str(self.work / 'cache'),
                    'PKGDEST': str(self.work / 'out'), 'SRCDEST': str(self.work / 'sources')}
        for folder in ('home', 'cache', 'out', 'sources'):
            path = self.work / folder
            path.mkdir(mode=0o700)
            os.chown(path, account.pw_uid, account.pw_gid)

    def run(self, args, capture=False, cwd=None, empty_ok=False):
        if empty_ok:
            # Paru -Qu returns 1 when there are no upgrades. Normalize only an
            # entirely empty result inside the unit, before systemd adds its
            # own exit-status diagnostics. Network/query errors stay failures.
            args = ['/usr/bin/bash', '-c', '''out=$(mktemp); err=$(mktemp)
trap 'rm -f -- "$out" "$err"' EXIT
code=0
"$@" > "$out" 2> "$err" || code=$?
cat "$out"; cat "$err" >&2
if [[ $code == 1 && ! -s $out && ! -s $err ]]; then exit 0; fi
exit "$code"
''', 'callas-query', *args]
        invocation = ['/usr/bin/systemd-run', '--quiet', '--wait', '--pipe', '--collect',
                      '--service-type=exec', '--property=User=' + BUILD_USER,
                      '--property=Group=' + BUILD_USER, '--property=NoNewPrivileges=yes',
                      '--property=ProtectSystem=strict', '--property=ProtectHome=yes',
                      '--property=PrivateTmp=yes', '--property=PrivateDevices=yes',
                      '--property=RestrictSUIDSGID=yes', '--property=KillMode=control-group',
                      '--property=RuntimeMaxSec=2h', '--property=Nice=10',
                      '--property=IOSchedulingClass=idle',
                      '--property=ReadWritePaths=' + str(self.work),
                      '--working-directory=' + str(cwd or self.work)]
        invocation += ['--setenv=' + key + '=' + value for key, value in self.env.items()]
        return command(invocation + ['--', *args], capture=capture)

    def build(self, base, expected):
        checkout = self.work / ('src-' + base)
        # Fresh source tree; no cached user modifications are accepted.
        self.run(['/usr/bin/git', '-c', 'core.hooksPath=/dev/null', 'clone', '--depth=1',
                  'https://aur.archlinux.org/' + name(base) + '.git', str(checkout)])
        self.run(['/usr/bin/git', '-C', str(checkout), 'rev-parse', 'HEAD'])
        fd = os.open(checkout / '.SRCINFO', os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd) as stream:
            metadata = stream.read(1024 * 1024)
        keys = []
        for line in metadata.splitlines():
            key, sep, value = line.strip().partition(' = ')
            if sep and key == 'validpgpkeys':
                if not re.fullmatch(r'[0-9A-Fa-f]{40}|[0-9A-Fa-f]{64}', value):
                    raise ValueError('Fingerprint PGP inválido')
                keys.append(value)
        spotify_key = Path('/etc/callas/spotify-aur.gpg')
        if spotify_key.is_file():
            self.run(['/usr/bin/gpg', '--batch', '--import', str(spotify_key)])
        for fingerprint in keys:
            try:
                self.run(['/usr/bin/gpg', '--batch', '--list-keys', fingerprint], capture=True)
            except subprocess.CalledProcessError:
                self.run(['/usr/bin/gpg', '--batch', '--keyserver', 'hkps://keyserver.ubuntu.com', '--recv-keys', fingerprint])
        self.run(['/usr/bin/makepkg', '--cleanbuild', '--force', '--noconfirm', '--log'], cwd=checkout)
        # The unit/cgroup has exited before root reads outputs. Copy regular files
        # into a root-only directory before passing them to the package manager.
        archives = []
        produced = set()
        destination = self.directory / ('packages-' + base)
        destination.mkdir(mode=0o700)
        for source in sorted((self.work / 'out').glob('*.pkg.tar.*')):
            if source.name.endswith('.sig'):
                continue
            fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_uid != self.uid or info.st_size > 8 * 1024**3:
                    raise ValueError('Artefato de compilação inválido')
                target = destination / source.name
                with target.open('xb') as output:
                    shutil.copyfileobj(stream, output)
            fields = command(['/usr/bin/pacman', '-Qp', str(target)], capture=True).stdout.strip().split()
            if len(fields) != 2:
                raise ValueError('Metadados de pacote inesperados')
            pkg = name(fields[0])
            if pkg in PINNED:
                raise ValueError('Artefato tentaria substituir a NVIDIA')
            if pkg in expected:
                archives.append(str(target))
                produced.add(pkg)
            source.unlink()
        if produced != set(expected):
            raise ValueError('Compilação não produziu todos os pacotes esperados: ' + ', '.join(expected))
        return archives

def run_update(apps_only=False):
    foreign = set(command(['/usr/bin/pacman', '-Qmq'], capture=True, empty_ok=True).stdout.split())
    if not foreign:
        print('Nenhum pacote externo/AUR instalado.')
        return
    parent = BUILDS_ROOT
    parent.mkdir(mode=0o711, parents=True, exist_ok=True)
    os.chmod(parent, 0o711)
    with tempfile.TemporaryDirectory(prefix='transaction-', dir=parent) as temp:
        os.chmod(temp, 0o711)
        builder = Builder(temp)
        upgrades = set(builder.run(['/usr/bin/paru', '-Qua', '--quiet', '--color', 'never'], capture=True, empty_ok=True).stdout.split())
        broken = set(builder.run(['/usr/bin/checkrebuild'], capture=True).stdout.split()) & foreign
        devel = {pkg for pkg in foreign if pkg.endswith(('-git', '-svn', '-hg', '-bzr', '-darcs', '-cvs'))}
        targets = sorted((upgrades | broken | devel) - PINNED)
        for pkg in targets:
            name(pkg)
        if not targets:
            print('AUR atualizado; nenhum pacote sinalizado para recompilação.')
            return
        actions = plan(builder.run(['/usr/bin/paru', '-Po', '--aur', '--noconfirm', '--color', 'never', *targets], capture=True).stdout, apps_only=apps_only)
        planned = {pkg for kind, _, _, pkgs in actions if kind == 'AUR' for pkg in pkgs}
        if not set(targets) <= planned:
            raise ValueError('O plano não inclui todos os pacotes pendentes')
        for kind, reason, source, pkgs in actions:
            if kind == 'INSTALL':
                command(['/usr/bin/pacman', '-S', '--needed', '--asdeps', '--noconfirm', source + '/' + pkgs[0]])
            else:
                archives = builder.build(source, pkgs)
                command(['/usr/bin/pacman', '-U', '--noconfirm', *archives])
                new_dependencies = [pkg for pkg in pkgs if pkg not in foreign and reason != 'TARGET']
                if new_dependencies:
                    command(['/usr/bin/pacman', '-D', '--asdeps', *new_dependencies])
        remaining = set(builder.run(['/usr/bin/checkrebuild'], capture=True).stdout.split()) & foreign
        if remaining:
            raise ValueError('Ainda há pacotes sinalizados após recompilar: ' + ', '.join(sorted(remaining)))
        print('Atualização e recompilações necessárias do AUR concluídas.')

def main():
    if os.geteuid() != 0 or sys.argv[1:] not in ([], ['--apps-only']):
        raise SystemExit('Uso interno do Atualizador do sistema.')
    os.umask(0o077)
    run_update(apps_only=sys.argv[1:] == ['--apps-only'])

if __name__ == '__main__':
    try:
        main()
    except RequiresGeneral as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
    except Exception as error:
        print('Falha na etapa do AUR: ' + str(error), file=sys.stderr)
        sys.exit(1)
