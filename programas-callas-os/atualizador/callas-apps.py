#!/usr/bin/python3
"""Reconcile the release's application catalog, preserving unrelated user apps.

The verified catalog manages application presence, not Arch version upgrades.
Project helpers/configurations are compared by the existing content checkpoints.
"""
from contextlib import contextmanager
import fcntl
import importlib.util
from importlib.machinery import SourceFileLoader
import json
import os
import pwd
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

STATE = Path('/var/lib/callas-os')
CATALOG = Path(__file__).with_name('callas-apps.json')
PHASES = ('security', 'apps', 'flatpaks')


def native():
    path = Path(__file__).with_name('callas-native.py')
    if not path.exists():
        path = path.with_suffix('')
    loader = SourceFileLoader('catalog_native', str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def validate(data):
    if data.get('schema') != 1 or not isinstance(data.get('applications'), list):
        raise ValueError('Catálogo de aplicativos inválido')
    seen = set()
    policy = native()
    for entry in data['applications']:
        if not isinstance(entry, dict) or set(entry) - {'name', 'source', 'state', 'phase', 'replacement'}:
            raise ValueError('Campos de aplicativo inválidos')
        name = entry.get('name', '')
        source = entry.get('source')
        if (not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9@_.+\-]*', name)
                or source not in ('repo', 'aur', 'flatpak')
                or entry.get('state') not in ('present', 'absent')
                or entry.get('phase') not in PHASES
                or (source != 'flatpak' and policy.frozen(name))
                or (source == 'flatpak' and entry['phase'] != 'flatpaks')
                or (source != 'flatpak' and entry['phase'] == 'flatpaks')):
            raise ValueError('Aplicativo fora do escopo: ' + name)
        key = ('flatpak' if source == 'flatpak' else 'native', name)
        if key in seen:
            raise ValueError('Aplicativo repetido no catálogo: ' + name)
        seen.add(key)
    for entry in data['applications']:
        if 'replacement' in entry and not any(
                other['name'] == entry['replacement'] and other['state'] == 'present'
                and other['phase'] == entry['phase'] for other in data['applications']):
            raise ValueError('Substituição sem destino instalado no mesmo fluxo')
    return data['applications']


def catalog():
    return validate(json.loads(CATALOG.read_text()))


def command(args):
    result = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                            env=dict(os.environ, LC_ALL='C', CALLAS_KERNEL_UPDATE_CONTEXT='apps'))
    if result.returncode:
        raise RuntimeError('Falha em ' + args[0] + ': ' + result.stderr.strip())
    return result.stdout


def inventory():
    packages = {}
    for line in command(['/usr/bin/pacman', '-Q']).splitlines():
        name, version = line.split(maxsplit=1)
        packages[name] = version
    flatpaks = {}
    if shutil.which('flatpak'):
        for line in command(['flatpak', 'list', '--system', '--app', '--columns=application,version']).splitlines():
            fields = line.split('\t', 1)
            flatpaks[fields[0]] = fields[1] if len(fields) == 2 else ''
    return {'native': packages, 'flatpak': flatpaks}


def hardware(cpuinfo=Path('/proc/cpuinfo'), pci=Path('/sys/bus/pci/devices')):
    cpu_text = cpuinfo.read_text()
    cpu = [label for vendor, label in (('AuthenticAMD', 'AMD'), ('GenuineIntel', 'Intel')) if vendor in cpu_text]
    vendors = {'0x10de': 'NVIDIA', '0x1002': 'AMD', '0x8086': 'Intel'}
    gpu = set()
    for device in pci.iterdir():
        if (device / 'class').read_text().strip().startswith('0x03'):
            vendor = (device / 'vendor').read_text().strip()
            gpu.add(vendors.get(vendor, vendor))
    return {'cpu': cpu or ['Outro'], 'gpu': sorted(gpu)}


def previous(phase):
    try:
        return validate(json.loads((STATE / ('apps-managed-' + phase + '.json')).read_text()))
    except FileNotFoundError:
        return []


def family(entry):
    return 'flatpak' if entry['source'] == 'flatpak' else 'native'


@contextmanager
def application_lock():
    """Serialize catalog reconciliation and interactive machine-wide removals."""
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / 'apps-operation.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def removed_choices():
    """Machine-local opt-outs, written only after explicit Central removal."""
    path = STATE / 'apps-user-removed.json'
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return set()
    if (not isinstance(data, list) or any(not isinstance(key, str) or not
            re.fullmatch(r'(native|flatpak):[a-zA-Z0-9][a-zA-Z0-9@_.+\-]*', key) for key in data)):
        raise ValueError('Registro de desinstalações inválido; aplicativos preservados.')
    return set(data)


def remember_removal(source, name):
    key = source + ':' + name
    if not re.fullmatch(r'(native|flatpak):[a-zA-Z0-9][a-zA-Z0-9@_.+\-]*', key):
        raise ValueError('Escolha de remoção inválida')
    save_removed_choices(removed_choices() | {key})


def forget_removal(source, name):
    save_removed_choices(removed_choices() - {source + ':' + name})


def save_removed_choices(choices):
    STATE.mkdir(parents=True, exist_ok=True)
    target = STATE / 'apps-user-removed.json'
    fd, temporary = tempfile.mkstemp(prefix='.removed-', dir=STATE)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(sorted(choices), stream); stream.write('\n')
            stream.flush(); os.fsync(stream.fileno()); os.fchmod(stream.fileno(), 0o644)
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def plan(entries, installed, managed):
    actions = []
    choices = removed_choices()
    current = {(family(entry), entry['name']) for entry in entries}
    # Only previously managed present applications become removals by omission.
    # An explicit absent entry also handles machines predating these receipts.
    retired = [dict(entry, state='absent') for entry in managed
               if entry['state'] == 'present' and (family(entry), entry['name']) not in current]
    for entry in [*entries, *retired]:
        present = entry['name'] in installed[family(entry)]
        if (entry['state'] == 'present' and not present
                and family(entry) + ':' + entry['name'] not in choices):
            actions.append(dict(entry, action='install'))
        elif entry['state'] == 'absent' and present:
            actions.append(dict(entry, action='remove'))
    return sorted(actions, key=lambda entry: entry['action'] == 'remove')


def pending(phase):
    entries = [entry for entry in catalog() if entry['phase'] == phase]
    return plan(entries, inventory(), previous(phase))


def install(entry, user):
    name = entry['name']
    if entry['source'] == 'flatpak':
        command(['flatpak', 'remote-add', '--system', '--if-not-exists', 'flathub',
                 'https://dl.flathub.org/repo/flathub.flatpakrepo'])
        command(['flatpak', 'install', '--system', '--noninteractive', '--assumeyes', 'flathub', name])
    elif entry['source'] == 'aur':
        command(['/usr/local/libexec/callas-aur-install', user, name])
    elif native().install_packages([name]):
        raise RuntimeError('Instalação não concluída: ' + name)


def active_native(name, proc=Path('/proc')):
    paths = set(command(['/usr/bin/pacman', '-Qlq', name]).splitlines())
    for process in proc.iterdir():
        if not process.name.isdecimal():
            continue
        try:
            executable = os.readlink(process / 'exe').removesuffix(' (deleted)')
            argv = (process / 'cmdline').read_bytes().split(b'\0')
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError as error:
            raise RuntimeError('Não consegui confirmar os processos ativos') from error
        if executable in paths or any(os.fsdecode(arg) in paths for arg in argv[:2]):
            return True
    return False


def remove(entry, user):
    name = entry['name']
    if entry['source'] == 'flatpak':
        # Root's flatpak ps does not describe desktop users' instances.
        users = {user}
        for runtime in Path('/run/user').iterdir():
            if runtime.name.isdecimal():
                try: users.add(pwd.getpwuid(int(runtime.name)).pw_name)
                except KeyError: continue
        for account_name in sorted(users):
            account = pwd.getpwnam(account_name)
            running = command(['/usr/bin/runuser', '-u', account_name, '--', '/usr/bin/env', '-i',
                'PATH=/usr/bin:/bin', 'HOME=' + account.pw_dir,
                'XDG_RUNTIME_DIR=/run/user/' + str(account.pw_uid),
                'flatpak', 'ps', '--columns=application']).splitlines()
            if name in running:
                raise RuntimeError(name + ' em uso; feche-o e repita o Update')
        command(['flatpak', 'uninstall', '--system', '--noninteractive', '--assumeyes', name])
    else:
        if active_native(name):
            raise RuntimeError(name + ' em uso; feche-o e repita o Update')
        if native().guarded_transaction(['-R', '--noconfirm', name]).returncode:
            raise RuntimeError('Remoção não concluída: ' + name)


def apply(phase, user):
    entries = [entry for entry in catalog() if entry['phase'] == phase]
    managed = previous(phase)
    for entry in plan(entries, inventory(), managed):
        print(('Instalando: ' if entry['action'] == 'install' else 'Removendo: ') + entry['name'], flush=True)
        if entry['action'] == 'remove' and entry.get('replacement'):
            if not any(e['name'] == entry['replacement'] and e['name'] in inventory()[family(e)] for e in entries):
                raise RuntimeError('Substituto não encontrado; aplicativo anterior preservado')
        (install if entry['action'] == 'install' else remove)(entry, user)
        present = entry['name'] in inventory()[family(entry)]
        if present != (entry['action'] == 'install'):
            raise RuntimeError('Resultado não confirmado: ' + entry['name'])
        if entry['action'] == 'install':
            # Keep ownership even if a later action fails or the next release
            # removes this app from the catalog before the phase is retried.
            managed = [e for e in managed if (family(e), e['name']) != (family(entry), entry['name'])]
            managed.append({k: v for k, v in entry.items() if k != 'action'})
            record(phase, managed)
    if plan(entries, inventory(), managed):
        raise RuntimeError('Catálogo ainda tem pendências; atualização não concluída')
    record(phase, entries)


def record(phase, entries):
    STATE.mkdir(parents=True, exist_ok=True)
    target = STATE / ('apps-managed-' + phase + '.json')
    fd, temporary = tempfile.mkstemp(prefix='.apps-', dir=STATE)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump({'schema': 1, 'applications': entries}, stream, sort_keys=True)
            stream.write('\n')
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def scan():
    installed = inventory()
    detected = hardware()
    print('Inventário local: CPU ' + ', '.join(detected['cpu']) + '; GPU ' + ', '.join(detected['gpu']))
    print(f"Instalados: {len(installed['native'])} pacotes nativos e {len(installed['flatpak'])} aplicativos Flatpak de sistema.")
    entries = catalog()
    for phase in PHASES:
        actions = plan([entry for entry in entries if entry['phase'] == phase], installed, previous(phase))
        for entry in actions:
            print(f"  {phase}: {entry['action']} {entry['name']}")
        if not actions:
            print(f'  {phase}: aplicativos já correspondem ao catálogo do GitHub.')


def main():
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == '--wants':
        return 0 if any(e['name'] == args[1] and e['state'] == 'present'
                        and family(e) + ':' + e['name'] not in removed_choices() for e in catalog()) else 1
    if args == ['--scan']:
        scan(); return 0
    if len(args) == 3 and args[0] == '--apply' and args[1] in (*PHASES, 'all'):
        if os.geteuid() != 0:
            raise ValueError('Requer root')
        with application_lock():
            for phase in PHASES if args[1] == 'all' else (args[1],):
                apply(phase, args[2])
        return 0
    raise ValueError('Argumentos inválidos')


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        print('Catálogo de aplicativos: ' + str(error), file=sys.stderr)
        sys.exit(2)
