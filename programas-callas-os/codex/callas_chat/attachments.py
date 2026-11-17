"""Prepare text or persistent local binary attachments without extracting packages."""
import hashlib
import json
import os
from pathlib import Path
import uuid

TEXT_LIMIT = 1024 * 1024
BINARY_LIMIT = 100 * 1024 * 1024


def prepare_document(path):
    path = Path(path)
    if not path.is_file():
        raise ValueError('Selecione um arquivo.')
    with path.open('rb') as source:
        raw = source.read(TEXT_LIMIT + 1)
        try:
            if raw.startswith((b'\xff\xfe', b'\xfe\xff')):
                content = raw.decode('utf-16')
            else:
                if b'\x00' in raw:
                    raise UnicodeError()
                try:
                    content = raw.decode('utf-8-sig')
                except UnicodeDecodeError:
                    content = raw.decode('cp1252')
            if any(ord(c) < 32 and c not in '\n\r\t\x1b' for c in content):
                raise UnicodeError()
        except UnicodeError:
            content = None
        if content is not None:
            if len(raw) > TEXT_LIMIT:
                raise ValueError('O limite por arquivo de texto é 1 MB.')
            return content
        if os.fstat(source.fileno()).st_size > BINARY_LIMIT:
            raise ValueError('O limite por arquivo binário é 100 MB.')
        root = Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share')))/'callas-chat/attachments'
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        destination = root/(uuid.uuid4().hex + path.suffix)
        digest = hashlib.sha256()
        size = 0
        source.seek(0)
        try:
            fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, 'wb') as target:
                while chunk := source.read(1024 * 1024):
                    size += len(chunk)
                    if size > BINARY_LIMIT:
                        raise ValueError('O limite por arquivo binário é 100 MB.')
                    target.write(chunk)
                    digest.update(chunk)
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
    return ('Arquivo binário disponível no computador local. Use as ferramentas de leitura para analisar esta cópia; '
            'não execute nem instale o conteúdo automaticamente.\n'
            + json.dumps({'caminho_local': str(destination), 'nome_original': path.name,
                          'tamanho_bytes': size, 'sha256': digest.hexdigest()}, ensure_ascii=False))
