#!/usr/bin/python3
"""Rebuild the deterministic bundle consumed by the verified release stage."""
import gzip
import io
from pathlib import Path
import tarfile

base = Path(__file__).resolve().parent
buffer = io.BytesIO()
with tarfile.open(fileobj=buffer, mode='w', format=tarfile.PAX_FORMAT) as archive:
    for folder in ('app', 'painel'):
        for path in sorted((base / folder).rglob('*')):
            if not path.is_file() or '__pycache__' in path.parts or path.suffix == '.pyc':
                continue
            info = tarfile.TarInfo(str(path.relative_to(base)))
            content = path.read_bytes()
            info.size = len(content)
            info.mode = 0o644
            info.mtime = 0
            archive.addfile(info, io.BytesIO(content))
(base / 'callas-baterias.tar.gz').write_bytes(gzip.compress(buffer.getvalue(), mtime=0))
