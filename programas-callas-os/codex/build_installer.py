"""Build the single-file installer; the archive contains only reviewed app files."""
import base64
import hashlib
import io
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parent


def package_bytes():
    payload = io.BytesIO()
    files = [ROOT/name for name in ('installer.py', 'setup_voice.py', 'LEIA-ME.txt')]
    files += [p for folder in ('callas_chat', 'assets') for p in (ROOT/folder).rglob('*')
              if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc']
    with tarfile.open(fileobj=payload, mode='w:gz') as archive:
        for path in files: archive.add(path, arcname=str(path.relative_to(ROOT)))
    return payload.getvalue()


def build(destination):
    content = package_bytes()
    digest = hashlib.sha256(content).hexdigest()
    header = r'''#!/usr/bin/env bash
set -euo pipefail
if (( EUID == 0 )); then
    printf 'Execute este instalador como seu usuário normal, sem sudo.\n' >&2
    exit 1
fi
mode=${1:-}
command -v python3 >/dev/null || { printf 'Python 3 não encontrado.\n' >&2; exit 1; }
stage=$(mktemp -d -t callas-chat.XXXXXXXX)
trap 'rm -rf -- "$stage"' EXIT
target=$stage
if [[ $mode == --extrair ]]; then
    [[ $# == 2 ]] || { printf 'Uso: %s --extrair PASTA\n' "$0" >&2; exit 1; }
    target=$2
fi
python3 - "$0" "$target" <<'CALLAS_EXTRACT'
import base64,hashlib,io,sys,tarfile
from pathlib import Path
source=Path(sys.argv[1]).read_text()
encoded=source.split('\n__CALLAS_CHAT_ARCHIVE__\n',1)[1]
data=base64.b64decode(encoded)
if hashlib.sha256(data).hexdigest()!='PAYLOAD_SHA256':
    raise SystemExit('O instalador não passou na verificação de integridade. Copie novamente o arquivo.')
target=Path(sys.argv[2])
if target.is_symlink(): raise SystemExit('Destino simbólico recusado.')
target.mkdir(parents=True,exist_ok=True)
with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
    for item in archive.getmembers():
        path=Path(item.name)
        if path.is_absolute() or '..' in path.parts or not (item.isfile() or item.isdir()):
            raise SystemExit('Conteúdo de instalação inválido.')
        destination=target/path
        if destination.exists() or destination.is_symlink():
            raise SystemExit('Extraia o aplicativo em uma pasta vazia.')
    archive.extractall(target,filter='data')
CALLAS_EXTRACT
if [[ $mode == --extrair ]]; then
    printf 'Arquivos verificados e extraídos em: %s\n' "$target"
    exit 0
fi
python3 "$stage/installer.py" "$@"
exit 0
__CALLAS_CHAT_ARCHIVE__
'''
    Path(destination).write_text(header.replace('PAYLOAD_SHA256', digest)+base64.encodebytes(content).decode())
    Path(destination).chmod(0o755)
    return digest


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        destination = sys.argv[1]
        print('Instalador criado:', destination)
        print('SHA-256 do conteúdo:', build(destination))
    else:
        destination = ROOT/'codex.tar.gz'
        content = package_bytes()
        destination.write_bytes(content)
        print('Pacote para publicar no GitHub:', destination)
        print('SHA-256:', hashlib.sha256(content).hexdigest())
