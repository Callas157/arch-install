#!/usr/bin/python3
"""Validate Callas entries and order the main kernel, the LTS and diagnostics."""
import argparse
import os
from pathlib import Path
import re
import shlex
import tempfile

TRANSITION = '    if [ -f $prefix/themes/callas/loading.cfg ]; then source $prefix/themes/callas/loading.cfg; fi'
TITLES = ('Callas OS Linux', 'Callas OS (kernel LTS - recuperação)',
          'Callas OS (diagnóstico sem splash)')


def commands(body):
    """Parse only boot command lines; never execute a shell/GRUB script."""
    offset = 0; pending = ''; start = 0
    for physical in body.splitlines(keepends=True):
        if not pending: start = offset
        offset += len(physical)
        text = physical.rstrip('\r\n')
        continued = text.endswith('\\')
        pending += text[:-1] + ' ' if continued else text
        if continued: continue
        match = re.match(r'^[ \t]*(linux(?:efi|16)?|initrd(?:efi|16)?)[ \t]+', pending)
        if match:
            tokens = shlex.split(pending, comments=True, posix=True)
            yield tokens[0], tokens[1:], start, re.match(r'[ \t]*', pending)[0]
        pending = ''
    if pending: raise ValueError('Comando de boot com continuação incompleta')


def entry_pattern(title):
    return re.compile(r"(?m)^(?P<indent>[ \t]*)menuentry[ \t]+(?P<quote>['\"])" + re.escape(title)
        + r"(?P=quote)[^\r\n]*\{\r?\n(?P<body>.*?)^(?P=indent)\}[ \t]*(?:#[^\r\n]*)?(?=\r?$)", re.S)


def migrate(source):
    result = source
    for title in TITLES:
        matches = list(entry_pattern(title).finditer(result))
        if len(matches) != 1:
            raise ValueError('Layout GRUB desconhecido: ' + title)
        match = matches[0]; body = match['body']
        parsed = list(commands(body))
        linux = [command for command in parsed if command[0].startswith('linux')]
        initrd = [command for command in parsed if command[0].startswith('initrd')]
        kernel = 'linux-lts' if title == TITLES[1] else 'linux'
        if len(linux) != 1 or len(initrd) != 1 or not linux[0][1] or not initrd[0][1]:
            raise ValueError(f'Entrada incompleta: {title} (esperado um comando linux e um initrd; encontrados {len(linux)} e {len(initrd)})')
        kernel_name = linux[0][1][0].rsplit('/', 1)[-1]
        images = [path.rsplit('/', 1)[-1] for path in initrd[0][1]]
        expected = {'initramfs-' + kernel + '.img', 'initramfs-' + kernel + '-fallback.img'}
        if (kernel_name != 'vmlinuz-' + kernel or sum(name in expected for name in images) != 1
                or any(name.startswith('initramfs-linux') and name not in expected for name in images)):
            raise ValueError(f'Par kernel/initramfs incompatível na entrada: {title}; arquivos originais preservados')
        # Microcode, extra initrds, paths, flags, whitespace and comments remain
        # byte-for-byte intact. Only insert a guarded graphical transition.
        if not any(line.strip() == TRANSITION.strip() for line in body.splitlines()):
            position = linux[0][2]; indent = linux[0][3]
            ending = '\r\n' if '\r\n' in body else '\n'
            body = body[:position] + indent + TRANSITION.strip() + ending + body[position:]
            result = result[:match.start('body')] + body + result[match.end('body'):]
    entries = [entry_pattern(title).search(result) for title in TITLES]
    ordered = sorted(entries, key=lambda entry: entry.start())
    parts = []
    offset = 0
    for slot, entry in zip(ordered, entries):
        parts.extend((result[offset:slot.start()], entry.group()))
        offset = slot.end()
    parts.append(result[offset:])
    return ''.join(parts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--entries', required=True, type=Path)
    parser.add_argument('--check', action='store_true', help='Validar sem gravar alterações')
    args = parser.parse_args()
    path = args.entries
    if path.is_symlink():
        raise ValueError('Entradas GRUB não podem ser link simbólico')
    before = path.stat()
    with path.open(newline='') as stream: original = stream.read()
    updated = migrate(original)
    if updated == original:
        print('unchanged')
        return
    if args.check:
        print('changed'); return
    fd, temporary = tempfile.mkstemp(prefix='.callas-boot-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', newline='') as stream:
            stream.write(updated)
            stream.flush()
            os.fchmod(stream.fileno(), before.st_mode & 0o777)
            os.fsync(stream.fileno())
        after = path.stat()
        if (before.st_ino, before.st_mtime_ns, before.st_size) != (after.st_ino, after.st_mtime_ns, after.st_size):
            raise RuntimeError('Entradas GRUB mudaram durante a migração; arquivo preservado')
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    print('changed')


if __name__ == '__main__':
    main()
