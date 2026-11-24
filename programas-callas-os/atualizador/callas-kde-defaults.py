#!/usr/bin/python3
"""Install Callas OS defaults for Kickoff and the KDE avatar picker."""
import argparse
import os
from pathlib import Path
import re
import tempfile


FAVORITES = (
    'io.github.Callas157.AtualizadorDoSistema.desktop',
    'steam.desktop',
    'discord.desktop',
    'systemsettings.desktop',
    'org.kde.konsole.desktop',
)
ACCOUNTS = Path('var/lib/AccountsService')


def write_file(path, content, mode=0o644, *, preserve=False):
    if (not preserve and not path.is_symlink() and path.is_file()
            and path.stat().st_mode & 0o777 == mode and path.read_bytes() == content):
        return
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.callas-kde-', delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(content)
            stream.flush()
            os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
            if preserve:
                try:
                    os.link(temporary, path)
                except FileExistsError:
                    pass
            else:
                temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def seed_initial_avatar(root, user, image):
    directory = root / ACCOUNTS
    icons, users = directory / 'icons', directory / 'users'
    icon, record = icons / user, users / user
    if record.exists() or record.is_symlink() or icon.is_symlink():
        return

    icons.mkdir(parents=True, exist_ok=True)
    users.mkdir(mode=0o700, parents=True, exist_ok=True)
    write_file(icon, image, preserve=True)
    # Finish an interrupted copy of our avatar while preserving any other icon.
    if icon.is_file() and not icon.is_symlink() and icon.read_bytes() == image:
        icon_path = Path('/') / ACCOUNTS / 'icons' / user
        write_file(record, f'[User]\nIcon={icon_path}\n'.encode(), 0o600, preserve=True)


def provision(avatar, *, root=Path('/'), initial_user=None):
    if initial_user is not None and (initial_user == 'root' or not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', initial_user)):
        raise ValueError('Nome inválido para a foto da conta inicial.')
    image = avatar.read_bytes()
    if not image.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('A imagem de perfil do Callas OS precisa estar em PNG.')

    config = root / 'etc/xdg/kicker-extra-favoritesrc'
    config.parent.mkdir(parents=True, exist_ok=True)
    write_file(config, ('[General]\nIgnoreDefaults=true\nPrepend=' + ';'.join(FAVORITES) + ';\n').encode())

    gallery = root / 'usr/share/plasma/avatars/callas-profile.png'
    gallery.parent.mkdir(parents=True, exist_ok=True)
    write_file(gallery, image)

    if initial_user is not None:
        seed_initial_avatar(root, initial_user, image)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('avatar', type=Path)
    parser.add_argument('--initial-user')
    args = parser.parse_args()
    # The verified install stage uses 077. KDE and SDDM must read public images.
    os.umask(0o022)
    provision(args.avatar, initial_user=args.initial_user)
