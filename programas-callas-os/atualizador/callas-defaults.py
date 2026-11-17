#!/usr/bin/python3
"""Offer clean-install desktop applications without provisioning unchecked apps."""
from concurrent.futures import ThreadPoolExecutor
import fcntl
import importlib.util
from importlib.machinery import SourceFileLoader
import json
import os
from pathlib import Path
import pwd
import re
import subprocess
import sys
import urllib.parse
import urllib.request

CATALOG = Path(__file__).with_name('callas-apps.json')


def apps_module():
    path = Path(__file__).with_name('callas-apps.py')
    if not path.exists(): path = path.with_suffix('')
    loader = SourceFileLoader('defaults_apps', str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec); loader.exec_module(module); return module


def widget_module():
    path = Path(__file__).with_name('callas-widget.py')
    if not path.exists(): path = path.with_suffix('')
    loader = SourceFileLoader('defaults_widget', str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec); loader.exec_module(module); return module


def identity(entry):
    kind = entry['source'] if entry['source'] in ('flatpak', 'plasmoid') else 'native'
    return kind + ':' + entry['name']


def defaults():
    data = json.loads(CATALOG.read_text())
    if data.get('schema') != 1 or not isinstance(data.get('defaults'), list):
        raise ValueError('Catálogo de aplicativos padrão inválido. Atualize a Central.')
    apps = apps_module(); seen = set()
    for entry in data['defaults']:
        if (not isinstance(entry, dict) or set(entry) != {'name', 'source', 'title', 'icon', 'description'}
                or any(not isinstance(value, str) or not value or len(value) > 500 for value in entry.values())
                or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9@_.+\-]*', entry['name'])
                or entry['source'] not in ('repo', 'aur', 'flatpak', 'plasmoid')
                or (entry['source'] == 'plasmoid' and entry['name'] != 'com.github.prayag2.modernclock')
                or not re.fullmatch(r'[a-zA-Z0-9_.\-]+', entry['icon'])
                or (entry['source'] != 'flatpak' and apps.native().frozen(entry['name']))
                or identity(entry) in seen):
            raise ValueError('Aplicativo padrão fora do escopo')
        # A retired managed app cannot be offered as a restoration option.
        if any(e['name'] == entry['name'] and apps.family(e) == identity(entry).split(':')[0]
               and e['state'] == 'absent' for e in apps.catalog()):
            raise ValueError('Aplicativo retirado da distribuição não pode ser restaurado')
        seen.add(identity(entry))
    return data['defaults']


def query(argv):
    result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                            timeout=18, env=dict(os.environ, LC_ALL='C', CALLAS_KERNEL_UPDATE_CONTEXT='apps'))
    if result.returncode: raise RuntimeError(result.stderr.strip() or 'Metadados indisponíveis')
    return result.stdout


def fields(text):
    result = {}
    for line in text.splitlines():
        key, sep, value = line.strip().partition(':')
        if sep: result[key.strip()] = value.strip()
    return result


def metadata(entry, installed):
    kind, name = identity(entry).split(':', 1)
    if kind == 'plasmoid':
        widget = widget_module()
        size = f'{widget.PAYLOAD.stat().st_size / 1024:.1f} KiB' if widget.PAYLOAD.is_file() else 'Não informado'
        return dict(entry, id=identity(entry), installed=widget.package_installed(), version='1.0.0',
                    size=size, download='Incluído no Callas OS', available='1.0.0',
                    notice='Arraste livremente no modo de edição ou escolha um canto em Configurar.')
    row = dict(entry, id=identity(entry), installed=name in installed[kind],
               version=installed[kind].get(name) or 'Não informada', size='Não informado',
               download='Não informado', available='Não informada', notice='')
    if row['installed'] and entry['source'] != 'flatpak':
        try:
            local = fields(query(['/usr/bin/pacman', '-Qi', '--', name]))
            row['size'] = local.get('Installed Size', 'Não informado')
        except (OSError, subprocess.SubprocessError, RuntimeError): pass
    try:
        if entry['source'] == 'repo':
            info = fields(query(['/usr/bin/pacman', '-Si', '--', name]))
            row.update(available=info.get('Version', 'Não informada'),
                       download=info.get('Download Size', 'Não informado'),
                       size=row['size'] if row['installed'] else info.get('Installed Size', 'Não informado'))
            if not row['installed']: row['version'] = row['available']

        elif entry['source'] == 'aur':
            request = urllib.request.Request('https://aur.archlinux.org/rpc/v5/info?' +
                urllib.parse.urlencode({'arg[]': name}), headers={'User-Agent': 'CallasOS-Central'})
            with urllib.request.urlopen(request, timeout=15) as response:
                raw = response.read(1024 * 1024 + 1)
                if not response.url.startswith('https://') or len(raw) > 1024 * 1024:
                    raise ValueError('Resposta AUR inválida')
            data = json.loads(raw)
            info = next(item for item in data.get('results', []) if item.get('Name') == name)
            row['available'] = info['Version']
            if not row['installed']: row['version'] = row['available']
            row['notice'] = 'O AUR não informa o tamanho do download antecipadamente.'
        else:
            if row['installed']:
                info = fields(query(['/usr/bin/flatpak', 'info', '--system', name]))
            else:
                info = fields(query(['/usr/bin/flatpak', 'remote-info', '--system', 'flathub', name]))
            row.update(size=info.get('Installed Size', 'Não informado'),
                       download=info.get('Download', info.get('Download Size', 'Não informado')),
                       available=info.get('Version', 'Não informada'))
            if not row['installed']: row['version'] = row['available']
    except (OSError, subprocess.SubprocessError, ValueError, RuntimeError, KeyError, StopIteration) as error:
        row['notice'] = 'Alguns metadados estão indisponíveis. ' + str(error)[:200]
    return row


def list_defaults():
    entries = defaults(); installed = apps_module().inventory()
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(lambda entry: metadata(entry, installed), entries))


def restore(user, ids):
    choices = {identity(entry): entry for entry in defaults()}
    if not ids or len(ids) != len(set(ids)) or any(key not in choices for key in ids):
        raise ValueError('Seleção inválida. Nenhum aplicativo foi instalado.')
    apps = None
    for key in ids:
        entry = choices[key]; kind, name = key.split(':', 1)
        if kind == 'plasmoid':
            if os.geteuid() == 0:
                account = pwd.getpwnam(user)
                subprocess.run(['/usr/bin/runuser', '-u', user, '--', '/usr/bin/env',
                    'HOME='+account.pw_dir, 'XDG_RUNTIME_DIR=/run/user/'+str(account.pw_uid),
                    'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/'+str(account.pw_uid)+'/bus',
                    '/usr/local/libexec/callas-widget', '--install'], check=True)
            else:
                with widget_module().user_lock(): widget_module().install()
            print(entry['title'] + ': instalado na área de trabalho.', flush=True)
            continue
        if apps is None: apps = apps_module()
        if name not in apps.inventory()[kind]:
            print('==> Instalando ' + entry['title'], flush=True)
            apps.install(entry, user)
        if name not in apps.inventory()[kind]: raise RuntimeError('Instalação não confirmada: ' + entry['title'])
        apps.forget_removal(kind, name)
        print(entry['title'] + ': instalado; escolha de desinstalação desfeita.', flush=True)
    print('Aplicativos selecionados restaurados. Os demais foram preservados.', flush=True)


def main():
    os.environ.pop('CALLAS_KERNEL_UPDATE_CONTEXT', None)
    if sys.argv[1:] == ['--list']:
        if os.geteuid() == 0: raise ValueError('Consulte os aplicativos como usuário normal.')
        print(json.dumps(list_defaults(), ensure_ascii=False)); return
    if len(sys.argv) > 3 and sys.argv[1] == '--restore':
        user = sys.argv[2]
        if os.geteuid() != 0:
            if user != pwd.getpwuid(os.getuid()).pw_name or any(not key.startswith('plasmoid:') for key in sys.argv[3:]):
                raise ValueError('A instalação de pacotes requer autorização administrativa.')
            restore(user, sys.argv[3:]); return
        # Do not let a caller select an unrelated account as the AUR build user.
        if pwd.getpwnam(user).pw_uid == 0 or os.environ.get('SUDO_USER') != user:
            raise ValueError('Usuário de instalação inválido.')
        with Path('/run/put-update.lock').open('a') as lock:
            try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: raise RuntimeError('Outra operação da Central está em andamento. Aguarde e tente novamente.')
            with apps_module().application_lock(): restore(user, sys.argv[3:])
        return
    raise ValueError('Use --list ou --restore USUARIO ID...')


if __name__ == '__main__':
    try: main()
    except Exception as error:
        print(str(error), file=sys.stderr); sys.exit(1)
