#!/usr/bin/python3
"""Shared Brave/Origin policies and visual defaults, preserving personal data."""
import argparse
import configparser
import json
import os
from pathlib import Path
import stat
import tempfile

VARIANTS = {'brave-bin': ('Brave-Browser', 'brave-flags.conf'),
            'brave-origin-bin': ('Brave-Origin', 'brave-origin-flags.conf')}
EXTENSIONS = {'ExtensionSettings': {name: {'installation_mode': 'normal_installed',
    'update_url': 'https://clients2.google.com/service/update2/crx'} for name in
    ('dlnejlppicbjfcfcedcflplfjajinajd', 'kdbmhfkmnlmbkgbabkdealhhbfhlmmon')}}
RECOMMENDED = dict(RestoreOnStartup=5, ShowHomeButton=True, HomepageIsNewTabPage=True, BookmarkBarEnabled=True)


def check_path(path):
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Caminho simbólico preservado: ' + str(path))


def atomic(path, data, before=None, guard=None, mode=0o644):
    check_path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.callas-browser-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno()); os.fchmod(stream.fileno(), mode)
        if before is not None:
            after = path.stat()
            if (before.st_ino, before.st_mtime_ns, before.st_size) != (after.st_ino, after.st_mtime_ns, after.st_size):
                raise RuntimeError('Preferências alteradas durante a configuração; arquivo preservado.')
        if guard and guard(): return False
        os.replace(temporary, path); return True
    finally: Path(temporary).unlink(missing_ok=True)


def visual(data):
    data.setdefault('browser', {})['custom_chrome_frame'] = False
    data['browser']['show_home_button'] = True; data['homepage_is_newtabpage'] = True
    data.setdefault('bookmark_bar', {})['show_on_all_tabs'] = True
    data.setdefault('intl', {})['accept_languages'] = 'pt-BR,pt,en-US,en'
    data['intl']['selected_languages'] = 'pt-BR,pt,en-US,en'
    data.setdefault('tab_search', {})['pinned_to_tabstrip'] = True
    data.setdefault('everything_menu', {})['pinned_to_tabstrip'] = True
    actions = data.setdefault('toolbar', {}).setdefault('pinned_actions', [])
    if 'kActionTabSearch' not in actions: actions.append('kActionTabSearch')
    return data


def repair(path, guard=None):
    check_path(path); before = path.stat() if path.exists() else None
    data = json.loads(path.read_text()) if before else {}
    if not isinstance(data, dict): raise ValueError('Preferências inválidas; arquivo preservado.')
    mode = stat.S_IMODE(before.st_mode) if before else 0o644
    return atomic(path, json.dumps(visual(data), ensure_ascii=False, separators=(',', ':')) + '\n', before, guard, mode)


def configure_system(root=Path('/')):
    # Both stable builds read this policy directory (including Origin).
    for relative, data in (('managed/callas-bonjourr.json', EXTENSIONS), ('recommended/callas-defaults.json', RECOMMENDED)):
        atomic(root / 'etc/brave/policies' / relative, json.dumps(data, indent=2) + '\n')
    for package in VARIANTS:
        folder = root / 'opt' / package
        if folder.is_dir(): repair(folder / 'initial_preferences')


def running(package, proc=Path('/proc')):
    for process in proc.iterdir():
        if not process.name.isdecimal(): continue
        try:
            if process.stat().st_uid != os.getuid(): continue
            args = (process / 'cmdline').read_bytes().split(b'\0')
            command = os.fsdecode(args[0]) if args else ''
        except (FileNotFoundError, ProcessLookupError, PermissionError): continue
        try: executable = os.readlink(process / 'exe')
        except (FileNotFoundError, ProcessLookupError, PermissionError): executable = command
        if any(value.startswith('/opt/' + package + '/') for value in (command, executable)): return True
        if executable.startswith(('/opt/brave-bin/', '/opt/brave-origin-bin/')): continue
        if command == 'brave' and not executable.startswith('/'): return True
        launcher = 'brave-origin' if package == 'brave-origin-bin' else 'brave'
        if not command.startswith('/opt/') and Path(command).name in (launcher, launcher + '-browser'): return True
    return False


def configure_user(home=None, config=None):
    home = home or Path.home(); config = config or home / '.config'; pending = False
    for package, (profile, flags) in VARIANTS.items():
        path = config / flags; check_path(path)
        lines = path.read_text().splitlines() if path.exists() else []
        lines = [line for line in lines if not line.startswith('--lang=')]
        if '--password-store=kwallet6' not in lines: lines.append('--password-store=kwallet6')
        lines.append('--lang=pt-BR'); atomic(path, '\n'.join(lines) + '\n', mode=0o600)
        folder = config / 'BraveSoftware' / profile
        preferences = [p / 'Preferences' for p in folder.iterdir()
                       if p.is_dir() and (p.name == 'Default' or p.name.startswith('Profile ')) and (p / 'Preferences').exists()] if folder.exists() else []
        if not preferences: continue
        if running(package):
            print(profile + ' aberto: perfil preservado; feche-o e repita o Update.'); pending = True; continue
        for pref in preferences:
            if not repair(pref, guard=lambda: running(package)): pending = True
    return pending


def default_origin(config):
    # Clean installation only; Update never changes the user's browser choice.
    for path, section, values in (
        (config / 'mimeapps.list', 'Default Applications', {key: 'brave-origin.desktop' for key in
            ('x-scheme-handler/http', 'x-scheme-handler/https', 'text/html', 'application/xhtml+xml')}),
        (config / 'kdeglobals', 'General', {'BrowserApplication': 'brave-origin.desktop'})):
        check_path(path)
        parser = configparser.ConfigParser(interpolation=None, strict=False); parser.optionxform = str
        if path.exists(): parser.read_string(path.read_text())
        if not parser.has_section(section): parser.add_section(section)
        for key, value in values.items(): parser.set(section, key, value)
        import io
        stream = io.StringIO(); parser.write(stream); atomic(path, stream.getvalue(), mode=0o600)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--system', action='store_true')
    parser.add_argument('--user', action='store_true'); parser.add_argument('--default-origin', action='store_true')
    args = parser.parse_args()
    if args.system and not args.user and not args.default_origin:
        if os.geteuid() != 0: raise ValueError('Requer autorização administrativa.')
        configure_system(); return 0
    if args.user and not args.system:
        if os.geteuid() == 0: raise ValueError('Configure o perfil como usuário normal.')
        config = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config')))
        pending = configure_user(config=config)
        if args.default_origin:
            if not Path('/usr/share/applications/brave-origin.desktop').is_file():
                raise RuntimeError('Brave Origin não está instalado; padrão anterior preservado.')
            default_origin(config)
        return 2 if pending else 0
    raise ValueError('Use --system ou --user [--default-origin]')


if __name__ == '__main__':
    try: raise SystemExit(main())
    except Exception as error:
        print(str(error)); raise SystemExit(1)
