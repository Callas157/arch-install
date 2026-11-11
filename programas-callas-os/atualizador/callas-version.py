#!/usr/bin/python3
"""Project identity, atomic migration state and the OS row of Nekofetch.

Does not change os-release, package versions, boot configuration or shell startup.
"""
import datetime
import json
import os
from pathlib import Path
import re
import sys
import tempfile

STATE = Path('/etc/callas-os/release.json')
SEMVER = re.compile(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z')
COMMAND = '/usr/local/libexec/callas-version --label'

def read_state():
    try:
        data = json.loads(STATE.read_text())
    except FileNotFoundError:
        return {'version': None, 'status': 'untracked'}
    for key in ('version', 'target'):
        if data.get(key) is not None and not SEMVER.fullmatch(data[key]):
            raise ValueError('Versão instalada inválida')
    return data

def write_state(data):
    created = not STATE.parent.exists()
    STATE.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    if created: STATE.parent.chmod(0o755)
    fd, temp = tempfile.mkstemp(prefix='.release-', dir=STATE.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
            os.fchmod(stream.fileno(), 0o644)
        os.replace(temp, STATE)
    finally:
        if os.path.exists(temp): os.unlink(temp)

def transition(action, version_file, release):
    version = Path(version_file).read_text().strip()
    if not SEMVER.fullmatch(version) or not re.fullmatch(r'[0-9a-f]{40}', release):
        raise ValueError('Versão ou referência inválida')
    state = read_state()
    if action == '--begin':
        state = {'version': state.get('version'), 'previous': state.get('version'),
                 'target': version, 'release': release, 'status': 'pending'}
    else:
        if (state.get('target'), state.get('release')) != (version, release):
            raise ValueError('Migração diferente da operação iniciada')
        state['status'] = {'--complete': 'complete', '--fail': 'incomplete', '--blocked': 'incompatible-boot'}[action]
        if action == '--complete': state['version'] = version
    state['updated_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    write_state(state)
    return state

def label(state=None):
    state = read_state() if state is None else state
    return 'Callas OS' + (' v' + state['version'] if state.get('version') else '') + ' (Arch Linux)'

def context():
    state = read_state()
    return label(state) + ' | estado: ' + state['status'] + (' | destino: v' + state['target'] if state.get('target') else '')

def configure_neko(path):
    if not path.is_file(): return False
    text = path.read_text(encoding='utf-8')
    tokens = r'("(?:\\.|[^"\\])*")|//[^\n]*|/\*[\s\S]*?\*/'
    text = re.sub(tokens, lambda match: match[1] or '', text)
    text = re.sub(r'("(?:\\.|[^"\\])*")|,(?=\s*[}\]])', lambda match: match[1] or '', text)
    layout = json.loads(text)
    found = False
    for index, item in enumerate(layout['modules']):
        if item == 'os': item = {'type': 'os'}
        if not isinstance(item, dict): continue
        if item.get('type') == 'os' or (item.get('type') == 'command' and item.get('text') == COMMAND):
            row = {key: value for key, value in item.items() if key in ('key', 'keyColor', 'keyIcon', 'keyWidth', 'outputColor', 'condition')}
            row.setdefault('key', 'OS')
            row.update(type='command', text=COMMAND)
            layout['modules'][index] = row; found = True
    if not found: raise ValueError('Nekofetch: linha OS não encontrada; layout preservado')
    output = json.dumps(layout, ensure_ascii=False, indent=2) + '\n'
    if output == path.read_text(): return True
    fd, temp = tempfile.mkstemp(prefix='.callas-layout-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream: stream.write(output)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp): os.unlink(temp)
    return True

def main():
    args = sys.argv[1:]
    if args == ['--label']: print(label())
    elif args == ['--context']: print(context())
    elif args == ['--json']: print(json.dumps(read_state(), ensure_ascii=False))
    elif len(args) == 2 and args[0] == '--is-installed':
        target = Path(args[1]).read_text().strip()
        if not SEMVER.fullmatch(target): raise ValueError('Versão de destino inválida')
        sys.exit(0 if read_state().get('version') == target else 1)
    elif args == ['--configure-neko'] and os.geteuid() != 0:
        path = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'nekofetch/layout.jsonc'
        if not configure_neko(path): print('Layout do Nekofetch ausente; será preparado na instalação/configuração do utilitário.')
    elif len(args) == 3 and args[0] in ('--begin', '--complete', '--fail', '--blocked') and os.geteuid() == 0:
        transition(*args)
        print(context())
    else: raise ValueError('Uso interno do Callas OS')

if __name__ == '__main__':
    try: main()
    except Exception as error:
        print('Identificação do Callas OS: ' + str(error), file=sys.stderr); sys.exit(1)
