#!/usr/bin/python3
"""Add a graphical transition only to the three recognized Callas boot entries."""
import argparse
import os
from pathlib import Path
import re
import tempfile

TRANSITION = '    if [ -f $prefix/themes/callas/loading.cfg ]; then source $prefix/themes/callas/loading.cfg; fi'
TITLES = ('Callas OS Linux', 'Callas OS (kernel LTS - recuperação)',
          'Callas OS (diagnóstico sem splash)')


def migrate(source):
    result = source
    for title in TITLES:
        pattern = re.compile(r"(?m)^menuentry '" + re.escape(title) + r"'[^\n]*\{\n(?P<body>.*?)^\}", re.S)
        matches = list(pattern.finditer(result))
        if len(matches) != 1:
            raise ValueError('Layout GRUB desconhecido: ' + title)
        match = matches[0]
        body = match['body']
        linux = re.findall(r'(?m)^    linux /vmlinuz-linux(?:-lts)? .+$', body)
        initrd = re.findall(r'(?m)^    initrd /initramfs-linux(?:-lts)?\.img$', body)
        if len(linux) != 1 or len(initrd) != 1:
            raise ValueError('Entrada incompleta: ' + title)
        if TRANSITION not in body:
            body = body.replace(linux[0], TRANSITION + '\n' + linux[0], 1)
            result = result[:match.start('body')] + body + result[match.end('body'):]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--entries', required=True, type=Path)
    args = parser.parse_args()
    path = args.entries
    if path.is_symlink():
        raise ValueError('Entradas GRUB não podem ser link simbólico')
    original = path.read_text()
    updated = migrate(original)
    if updated == original:
        print('unchanged')
        return
    fd, temporary = tempfile.mkstemp(prefix='.callas-boot-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(updated)
            stream.flush()
            os.fchmod(stream.fileno(), path.stat().st_mode & 0o777)
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    print('changed')


if __name__ == '__main__':
    main()
