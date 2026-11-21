"""Metadados de conversas fixadas: somente IDs e nomes, nunca mensagens nem chaves."""
import json
import os
from pathlib import Path
import tempfile


def pins_path():
    home = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share')))
    return home / 'callas-chat' / 'pinned.json'


def load_pins(provider, path=None):
    path = Path(path) if path else pins_path()
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        value = data.get(provider, {})
        return {str(k): str(v)[:120] for k, v in value.items()} if isinstance(value, dict) else {}
    except (OSError, ValueError, AttributeError):
        return {}


def save_pins(provider, pins, path=None):
    path = Path(path) if path else pins_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise ValueError('O arquivo de conversas fixadas não pode ser um link.')
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict): data = {}
    except (OSError, ValueError):
        data = {}
    data[provider] = {str(k): str(v)[:120] for k, v in pins.items()}
    descriptor, temporary = tempfile.mkstemp(prefix='.pinned-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
