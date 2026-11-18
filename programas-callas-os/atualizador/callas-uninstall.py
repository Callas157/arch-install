#!/usr/bin/python3
"""Application-only removal. No dependency cleanup, shell commands or upgrades."""
import argparse
import configparser
import fcntl
import importlib.util
from importlib.machinery import SourceFileLoader
import json
import os
from pathlib import Path
import pwd
import re
import shlex
import shutil
import subprocess
import sys

ESSENTIAL = frozenset(('dolphin', 'konsole', 'kate', 'kdialog', 'polkit', 'polkit-kde-agent',
    'pyside6', 'python', 'flatpak', 'xdg-utils', 'xdg-desktop-portal', 'kio', 'kservice',
    'qt6-base', 'qt6-declarative', 'pipewire', 'wireplumber', 'fontconfig', 'callas-os'))
ESSENTIAL_PREFIXES = ('callas-', 'xdg-desktop-portal-', 'qt6-', 'kf6-', 'pipewire-', 'gst-')
COMMON_SYSTEM_APPS = frozenset(('gnome-boxes',))
APP_CATEGORIES = {'AudioVideo', 'Audio', 'Video', 'Network', 'Office', 'Graphics',
                  'Game', 'Education', 'Development', 'Utility'}


def module(name):
    path = Path(__file__).with_name(name + '.py')
    if not path.exists(): path = path.with_suffix('')
    loader = SourceFileLoader(name.replace('-', '_'), str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    result = importlib.util.module_from_spec(spec); loader.exec_module(result)
    return result


def policy(): return module('callas-native')
def catalog_module(): return module('callas-apps')
def active_native(name): return catalog_module().active_native(name)


def command(args):
    result = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                            env=dict(os.environ, LC_ALL='C', CALLAS_KERNEL_UPDATE_CONTEXT='apps'))
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or 'Falha ao executar ' + args[0])
    return result.stdout


def desktop_entry(path):
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    try:
        parser.read_string(path.read_text())
        entry = dict(parser['Desktop Entry'])
        if entry.get('Type') != 'Application' or entry.get('Hidden') == 'true' or entry.get('NoDisplay') == 'true':
            return None
        return entry
    except (OSError, UnicodeError, configparser.Error, KeyError): return None


def blocked_native(name, entry):
    categories = set(entry.get('Categories', '').split(';'))
    return (policy().frozen(name) or name in ESSENTIAL or name.startswith(ESSENTIAL_PREFIXES)
            or (name not in COMMON_SYSTEM_APPS and
                (bool(categories & {'Settings', 'System'}) or not bool(categories & APP_CATEGORIES))))


def native_apps():
    paths = sorted(Path('/usr/share/applications').glob('*.desktop'))
    if not paths: return []
    # pacman owns package identity; desktop names/Exec never become root commands.
    owned = subprocess.run(['/usr/bin/pacman', '-Qo', '--', *map(str, paths)],
                           capture_output=True, text=True, env=dict(os.environ, LC_ALL='C'))
    if owned.returncode not in (0, 1): raise RuntimeError('Não foi possível consultar os pacotes nativos.')
    apps = {}
    for line in owned.stdout.splitlines():
        match = re.fullmatch(r'(.+) is owned by (\S+) (\S+)', line)
        if not match: continue
        path, name, version = match.groups()
        entry = desktop_entry(Path(path))
        if not entry: continue
        blocked = blocked_native(name, entry)
        app = dict(kind='native', id=name, name=entry.get('Name[pt_BR]', entry.get('Name', name)),
                   version=version, icon=entry.get('Icon', ''), source='Nativo / AUR', blocked=blocked,
                   reason='Componente do sistema ou ferramenta administrativa: remoção bloqueada.' if blocked else
                          'Remove somente este pacote; dependências necessárias a outros programas bloqueiam a operação.')
        if name not in apps or (apps[name]['blocked'] and not blocked): apps[name] = app
    # If ANY desktop entry in a package is administrative, protect the package.
    for line in owned.stdout.splitlines():
        match = re.fullmatch(r'(.+) is owned by (\S+) (\S+)', line)
        if match and match[2] in apps:
            entry = desktop_entry(Path(match[1]))
            if entry and blocked_native(match[2], entry):
                apps[match[2]].update(blocked=True, reason='Pacote contém ferramentas do sistema: remoção bloqueada.')
    return sorted(apps.values(), key=lambda app: app['name'].casefold())


def native_installed(name):
    result = subprocess.run(['/usr/bin/pacman', '-Q', '--', name], capture_output=True, text=True)
    if result.returncode not in (0, 1): raise RuntimeError('Não foi possível verificar a remoção.')
    return result.returncode == 0


def flatpak_apps(scope):
    if not shutil.which('flatpak'): return []
    apps = []
    for line in command(['/usr/bin/flatpak', 'list', '--' + scope, '--app', '--columns=ref,name,version']).splitlines():
        fields = line.split('\t')
        if len(fields) != 3: raise RuntimeError('Inventário Flatpak incompleto.')
        ref, name, version = fields
        if not ref.startswith('app/'): ref = 'app/' + ref
        if not re.fullmatch(r'app/[\w.\-]+/[\w\-]+/[\w.\-]+', ref):
            raise RuntimeError('Referência Flatpak inválida.')
        apps.append(dict(kind='flatpak-' + scope, id=ref, name=name, version=version, icon=ref.split('/')[1],
                         source='Flatpak — ' + ('usuário' if scope == 'user' else 'sistema'),
                         blocked=False, reason='Remove só o aplicativo. Dados pessoais e runtimes são preservados.'))
    return apps


def flatpak_active(ref, system=False):
    appid = ref.split('/')[1]
    if not system:
        return appid in command(['/usr/bin/flatpak', 'ps', '--columns=application']).splitlines()
    # System apps may be running in another logged-in user's session.
    for runtime in Path('/run/user').iterdir():
        if not runtime.name.isdecimal() or int(runtime.name) == 0: continue
        account = pwd.getpwuid(int(runtime.name))
        running = command(['/usr/bin/runuser', '-u', account.pw_name, '--', '/usr/bin/env', '-i',
            'PATH=/usr/bin:/bin', 'HOME=' + account.pw_dir, 'XDG_RUNTIME_DIR=' + str(runtime),
            '/usr/bin/flatpak', 'ps', '--columns=application'])
        if appid in running.splitlines(): return True
    return False


def find_app(apps, identity):
    app = next((app for app in apps if app['id'] == identity), None)
    if app is None: raise RuntimeError('Aplicativo ausente ou não reconhecido. Atualize a lista.')
    if app['blocked']: raise RuntimeError(app['reason'])
    return app


def remove_system(kind, identity):
    if kind == 'native':
        find_app(native_apps(), identity)
        if active_native(identity): raise RuntimeError('Aplicativo em uso. Feche-o antes de desinstalar.')
        if policy().guarded_transaction(['-R', '--noconfirm', identity]).returncode:
            raise RuntimeError('Remoção bloqueada ou cancelada. O pacote pode ser necessário a outro programa; consulte os detalhes.')
        if native_installed(identity): raise RuntimeError('A remoção do pacote não foi confirmada.')
        catalog_module().remember_removal('native', identity)
    elif kind == 'flatpak-system':
        find_app(flatpak_apps('system'), identity)
        if flatpak_active(identity, system=True): raise RuntimeError('Aplicativo em uso. Feche-o antes de desinstalar.')
        command(['/usr/bin/flatpak', 'uninstall', '--system', '--noninteractive', '--assumeyes', identity])
        remaining = flatpak_apps('system')
        if any(app['id'] == identity for app in remaining):
            raise RuntimeError('A remoção do Flatpak não foi confirmada.')
        # Another architecture/branch of the same catalog app remains installed.
        if not any(app['id'].split('/')[1] == identity.split('/')[1] for app in remaining):
            catalog_module().remember_removal('flatpak', identity.split('/')[1])
    else: raise ValueError('Tipo de aplicativo administrativo inválido.')


def safe_path(path, home):
    path = Path(os.path.abspath(path)); home = Path(os.path.abspath(home))
    if path == home or not path.is_relative_to(home): return False
    return not any(part.is_symlink() for part in (path, *path.parents) if part.is_relative_to(home))


def safe_image(path, home):
    path = Path(path)
    return (path.is_absolute() and path.suffix.casefold() == '.appimage' and path.is_file()
            and path.stat().st_uid == os.getuid() and safe_path(path, home))


def data_home(): return Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share')))


def user_apps():
    home = Path.home(); data = data_home(); apps = []
    base = data / 'callas-chat'
    launcher = home / '.local/bin/callas-chat'
    desktop = data / 'applications/io.github.callasos.CallasChat.desktop'
    package = base / 'app/callas_chat/__init__.py'
    if any(path.is_file() or path.is_symlink() for path in (launcher, desktop, package)):
        blocked = any(not safe_path(path, home) for path in (launcher, desktop, package))
        version = ''
        if not blocked and package.is_file():
            try:
                match = re.search(r"""(?m)^__version__\s*=\s*['"]([0-9.]+)['"]""", package.read_text())
                if match:
                    version = match[1]
            except (OSError, UnicodeError):
                pass
        apps.append(dict(kind='codex', id='callas-chat', name='Codex', version=version, icon='codex', source='Perfil do usuário',
                         blocked=blocked,
                         reason='Remove o cliente da Central. Preserva login, conversas e preferências.'))
    images = {}
    for folder in (home / 'Applications', home / 'Downloads'):
        if safe_path(folder, home) and folder.is_dir():
            for path in folder.iterdir():
                if safe_image(path, home): images[str(path)] = (path.stem, '')
    for path in (data / 'applications').glob('*.desktop'):
        entry = desktop_entry(path)
        if not entry: continue
        try: executable = Path(shlex.split(entry.get('Exec', ''))[0])
        except (ValueError, IndexError): continue
        if safe_image(executable, home): images[str(executable)] = (entry.get('Name', executable.stem), entry.get('Icon', ''))
    apps.extend(dict(kind='appimage', id=path, name=name, icon=icon, version='', source='AppImage — usuário',
                     blocked=False, reason='Remove o arquivo AppImage e seus atalhos pessoais; preserva configurações.')
                for path, (name, icon) in images.items())
    return apps


def user_active(paths, modules=()):
    paths = {str(path) for path in paths}
    directories = [Path(path) for path in paths if Path(path).is_dir()]
    def matches(value):
        return value in paths or (value.startswith('/') and any(Path(value).is_relative_to(root) for root in directories))
    for process in Path('/proc').iterdir():
        if not process.name.isdecimal() or process.name == str(os.getpid()): continue
        try:
            if process.stat().st_uid != os.getuid(): continue
        except (FileNotFoundError, ProcessLookupError): continue
        # Same-user system services may be nondumpable: read each source
        # independently, so an inaccessible exe does not hide readable cmdline.
        try:
            args = (process / 'cmdline').read_bytes().split(b'\0')
            if (any(matches(os.fsdecode(arg)) for arg in args if arg)
                    or any(os.fsencode(name) in args for name in modules)): return True
        except (FileNotFoundError, ProcessLookupError, PermissionError): pass
        try:
            if matches(os.readlink(process / 'exe').removesuffix(' (deleted)')): return True
        except (FileNotFoundError, ProcessLookupError, PermissionError): pass
        try:
            environment = (process / 'environ').read_bytes().split(b'\0')
            if any(b'APPIMAGE=' + os.fsencode(path) in environment for path in paths): return True
        except (FileNotFoundError, ProcessLookupError, PermissionError): pass
    return False


def refresh_menu():
    if shutil.which('kbuildsycoca6'):
        subprocess.run(['kbuildsycoca6', '--noincremental'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def remove_user(kind, identity):
    if os.geteuid() == 0: raise ValueError('Remoções pessoais exigem usuário normal.')
    if kind == 'flatpak-user':
        find_app(flatpak_apps('user'), identity)
        if flatpak_active(identity): raise RuntimeError('Aplicativo em uso. Feche-o antes de desinstalar.')
        command(['/usr/bin/flatpak', 'uninstall', '--user', '--noninteractive', '--assumeyes', identity])
        if any(app['id'] == identity for app in flatpak_apps('user')): raise RuntimeError('Remoção não confirmada.')
    elif kind == 'appimage':
        find_app([app for app in user_apps() if app['kind'] == kind], identity)
        if user_active([identity]): raise RuntimeError('Aplicativo em uso. Feche-o antes de desinstalar.')
        # Revalidate immediately before unlink; never execute an uninstaller from a download.
        if not safe_image(Path(identity), Path.home()): raise RuntimeError('Arquivo inseguro ou alterado.')
        Path(identity).unlink()
        for path in (data_home() / 'applications').glob('*.desktop'):
            entry = desktop_entry(path)
            if not entry or not safe_path(path, Path.home()): continue
            try: executable = shlex.split(entry.get('Exec', ''))[0]
            except (ValueError, IndexError): continue
            if executable == identity: path.unlink()
    elif kind == 'codex' and identity == 'callas-chat':
        find_app([app for app in user_apps() if app['kind'] == kind], identity)
        home = Path.home(); data = data_home(); base = data / 'callas-chat'
        # Installation files only. Never remove the base (it also stores user data).
        paths = [base / name for name in ('app', 'app.previous', 'venv', 'runtime')]
        paths += [home / '.local/bin/callas-chat', home / '.local/bin/codex-askpass',
                  data / 'applications/io.github.callasos.CallasChat.desktop',
                  data / 'icons/hicolor/scalable/apps/codex.svg']
        if any(not safe_path(path, home) for path in paths): raise RuntimeError('Caminho simbólico ou fora do perfil: remoção bloqueada.')
        if user_active([home / '.local/bin/callas-chat', base / 'app', base / 'venv', base / 'runtime'],
                       modules=('callas_chat',)):
            raise RuntimeError('Codex em uso. Feche-o antes de desinstalar.')
        for path in paths:
            if path.is_dir(): shutil.rmtree(path)
            else: path.unlink(missing_ok=True)
    else: raise ValueError('Aplicativo pessoal não reconhecido.')
    refresh_menu()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--remove', nargs=2, metavar=('TYPE', 'ID'))
    args = parser.parse_args()
    os.environ.pop('CALLAS_KERNEL_UPDATE_CONTEXT', None)
    if args.list:
        if os.geteuid() == 0: raise ValueError('Abra a lista como usuário normal.')
        apps = native_apps() + flatpak_apps('system') + flatpak_apps('user') + user_apps()
        print(json.dumps(sorted(apps, key=lambda app: app['name'].casefold()), ensure_ascii=False))
    elif args.remove:
        kind, identity = args.remove
        if kind in ('native', 'flatpak-system'):
            if os.geteuid() != 0: raise ValueError('Esta operação precisa de autorização administrativa.')
            with Path('/run/put-update.lock').open('a') as lock:
                try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise RuntimeError('Outra operação da Central está em andamento. Aguarde e tente novamente.')
                with catalog_module().application_lock():
                    remove_system(kind, identity)
        else: remove_user(kind, identity)
        print('Aplicativo desinstalado. Dados pessoais preservados.', flush=True)
    else: parser.error('Escolha --list ou --remove TYPE ID')


if __name__ == '__main__':
    try: main()
    except Exception as error:
        print(str(error), file=sys.stderr); sys.exit(1)
