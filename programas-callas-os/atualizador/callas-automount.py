#!/usr/bin/python3
"""Prepare boot mounts for local secondary data partitions."""
from collections import defaultdict
from contextlib import suppress
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys
import tempfile

FSTAB = Path('/etc/fstab')
INTERNAL_TRANSPORTS = {'ata', 'sata', 'nvme'}
MICROSOFT_BASIC_DATA = 'ebd0a0a2-b9e5-4433-87c0-68b6b72699c7'
NO_DEFAULT_DRIVE_LETTER = '0x8000000000000000'
DATA_PARTITIONS = {
    '0x7', '0x83',
    MICROSOFT_BASIC_DATA,
    '0fc63daf-8483-4772-8e79-3d69d8477de4',  # Linux filesystem
}
FILESYSTEMS = {
    'ntfs': 'ntfs3', 'ntfs3': 'ntfs3', 'exfat': 'exfat',
    'ext2': 'ext2', 'ext3': 'ext3', 'ext4': 'ext4', 'xfs': 'xfs', 'btrfs': 'btrfs',
}
UUID_PATTERN = re.compile(r'[0-9a-fA-F]+(?:-[0-9a-fA-F]+)*')


def device_nodes(devices):
    for device in devices:
        yield device
        yield from device_nodes(device.get('children') or [])


def device_path(name):
    return os.path.realpath(name) if name and name.startswith('/dev/') else None


def devices_by_uuid(devices):
    groups = defaultdict(set)
    for node in devices:
        if node.get('uuid') and (path := device_path(node.get('name'))):
            groups[node['uuid'].lower()].add(path)
    return groups


def data_target(target):
    return bool(target and (target in ('/mnt', '/media')
                            or target.startswith(('/mnt/', '/media/', '/run/media/'))))


def mountpoints(device):
    return [target for target in device.get('mountpoints') or [] if target]


def system_target(target):
    # Swap is protected by filesystem type; it need not exclude a data sibling.
    return bool(target and target.startswith('/') and not data_target(target))


def fstab_path(path):
    return path.replace('\\', r'\134').replace(' ', r'\040').replace('\t', r'\011')


def supported_partition(partition):
    parttype = (partition.get('parttype') or '').lower()
    if (partition.get('type') != 'part' or parttype not in DATA_PARTITIONS
            or partition.get('children')):
        return False
    flags = str(partition.get('partflags') or '').lower()
    if re.fullmatch(r'(?:0x)?0*', flags):
        return True
    # Linux mounts by path and need not apply a Windows drive letter policy.
    # Other GPT attributes, including combinations with this bit, stay excluded.
    return (parttype == MICROSOFT_BASIC_DATA
            and partition.get('fstype') in ('ntfs', 'ntfs3', 'exfat')
            and flags == NO_DEFAULT_DRIVE_LETTER)


def plan_mounts(disks, root_source, configured, user, uid, gid, available_target, *, report=None):
    """Return new fstab entries without changing existing mounts."""
    def skipped(device, reason):
        if report:
            report(f"Montagem automática: {device.get('name') or 'dispositivo'}: {reason}.")

    root_device = device_path(root_source)
    devices = list(device_nodes(disks))
    if not root_device or not any(device_path(node.get('name')) == root_device for node in devices):
        if report:
            report('Montagem automática: não foi possível identificar com segurança o disco do sistema.')
        return []

    configured_devices = set()
    protected_devices = {root_device}
    targets = set()
    for entry in configured:
        target = entry.get('target')
        targets.add(target)
        sources = [entry.get('source'), *(entry.get('sources') or [])]
        paths = {path for source in sources if (path := device_path(source))}
        configured_devices.update(paths)
        if system_target(target):
            protected_devices.update(paths)
    configured_uuids = {
        source[5:].lower() for entry in configured
        if (source := entry.get('source') or '').startswith('UUID=')
    }
    protected_uuids = {
        node['uuid'].lower() for node in devices if node.get('uuid')
        and (device_path(node.get('name')) in protected_devices
             or any(system_target(target) for target in mountpoints(node)))
    }
    # A device may be shown under several parents, such as a RAID array.
    # Count distinct devices so repeated references to one are not mistaken for clones.
    uuids = devices_by_uuid(devices)
    entries = []
    desktop_parent = Path('/run/media') / user
    for disk in disks:
        if disk.get('type') != 'disk':
            continue
        if (disk.get('tran') not in INTERNAL_TRANSPORTS or disk.get('ro') is not False
                or disk.get('rm') is not False):
            skipped(disk, 'transporte, mídia removível ou modo somente leitura fora do escopo')
            continue
        # PCIe/SATA controllers can advertise hot-plug for internal disks.
        if any(device_path(node.get('name')) in protected_devices
               or (node.get('uuid') or '').lower() in protected_uuids
               or any(system_target(target) for target in mountpoints(node))
               for node in device_nodes((disk,))):
            skipped(disk, 'disco vinculado a uma montagem do sistema')
            continue

        children = disk.get('children') or []
        # A filesystem can occupy the entire namespace, with no partition table.
        volumes = children if children or disk.get('pttype') else [disk]
        for volume in volumes:
            if volume is not disk and not supported_partition(volume):
                parttype = volume.get('parttype') or 'sem tipo'
                flags = volume.get('partflags') or 'sem atributos'
                skipped(volume, f'partição excluída pelo tipo, atributos ou camada ({parttype}; {flags})')
                continue
            uuid = volume.get('uuid') or ''
            fstype = volume.get('fstype')
            fs = FILESYSTEMS.get(fstype)
            name = device_path(volume.get('name'))
            if not fs or not name or volume.get('ro') is not False or volume.get('rm') is True:
                skipped(volume, f'sistema de arquivos não elegível ({fstype or "sem assinatura"})')
                continue
            if (len(uuid) > 64 or not UUID_PATTERN.fullmatch(uuid)
                    or len(uuids[uuid.lower()]) != 1):
                skipped(volume, 'UUID ausente, inválido ou compartilhado por mais de um dispositivo')
                continue
            if uuid.lower() in configured_uuids or name in configured_devices:
                skipped(volume, 'montagem já configurada')
                continue

            mounts = mountpoints(volume)
            if mounts:
                # Keep the Dolphin/UDisks path when it is already being used,
                # especially if a Steam library was registered there.
                if (len(mounts) != 1 or Path(mounts[0]).parent != desktop_parent
                        or any(ord(char) < 32 and char != '\t' for char in mounts[0])):
                    skipped(volume, 'montagem ativa em outro caminho')
                    continue
                target = mounts[0]
            else:
                target = '/mnt/callas-' + uuid.lower()
            if target in targets or not available_target(target, bool(mounts)):
                skipped(volume, 'ponto de montagem ocupado ou inseguro')
                continue
            options = [
                'nosuid', 'nodev', 'nofail', 'x-systemd.device-timeout=10s',
                'x-systemd.mount-timeout=15s', 'x-systemd.before=display-manager.service',
            ]
            if fs in ('ntfs3', 'exfat'):
                options.extend((f'uid={uid}', f'gid={gid}', 'umask=0077'))
            entries.append((target, f'UUID={uuid}\t{fstab_path(target)}\t{fs}\t{",".join(options)}\t0\t0'))
            targets.add(target)
    return entries


def protected_directory(path):
    info = path.lstat()
    return stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022


def available_target(target, mounted):
    path = Path(target)
    try:
        if not all(protected_directory(parent) for parent in path.parents):
            return False
        if mounted:
            return not path.is_symlink() and path.is_mount()
        if not os.path.lexists(path):
            return True
        # An empty root-owned destination can remain after an interrupted run.
        return protected_directory(path) and not path.is_mount() and not any(path.iterdir())
    except OSError:
        return False


def inventory(*args):
    result = subprocess.run(args, check=True, stdout=subprocess.PIPE, text=True)
    return json.loads(result.stdout)


def verify_candidate(candidate):
    # Existing optional mounts can be disconnected when applying the Update.
    # Keep unrelated preexisting diagnostics, while rejecting parse errors or
    # any new diagnostic in the complete table.
    def check(path):
        return subprocess.run(
            ['findmnt', '--verify', '--tab-file', str(path)],
            env={**os.environ, 'LC_ALL': 'C'}, capture_output=True, text=True,
        )

    result = check(candidate)
    if not result.returncode:
        return
    original = check(FSTAB)
    if (result.returncode == original.returncode
            and result.stdout == original.stdout and result.stderr == original.stderr
            and re.search(r'^0 parse errors,', result.stderr, re.M)):
        print('Montagem automática: diagnósticos preexistentes do fstab preservados.')
        return
    print(result.stdout + result.stderr, file=sys.stderr, end='')
    result.check_returncode()


def start_mounts(mounts):
    """Activate only selected, still-unmounted data volumes in the live OS."""
    if not mounts or not Path('/run/systemd/system').is_dir():
        return
    if subprocess.run(['systemd-detect-virt', '--chroot', '--quiet']).returncode == 0:
        return
    active = inventory('findmnt', '--kernel', '--json', '--list', '--nofsroot',
                       '-o', 'SOURCE,TARGET')['filesystems']
    active_sources = {device_path(item['source']) for item in active}
    occupied = {item['target'] for item in active}
    pending = {target: source for target, source in mounts.items()
               if source and source not in active_sources and target not in occupied
               and available_target(target, False)}
    if not pending:
        return
    if subprocess.run(['systemctl', 'daemon-reload']).returncode:
        print('Montagem automática: a configuração será ativada no próximo boot.')
        return
    for target in pending:
        unit = subprocess.check_output(
            ['systemd-escape', '--path', '--suffix=mount', '--', target], text=True,
        ).strip()
        result = subprocess.run(['systemctl', 'start', '--', unit])
        if result.returncode:
            print(f'Montagem automática: falha ao montar {target} nesta sessão. '
                  f'Consulte journalctl -u {unit}; a entrada permanece no fstab.')
        else:
            print(f'Montagem automática ativa em {target}.')


def managed_mounts(configured, sources):
    """Find the UUID-based destinations generated by 3.18.0 or this release."""
    base_options = {'nosuid', 'nodev', 'nofail', 'x-systemd.device-timeout=10s',
                    'x-systemd.before=display-manager.service'}
    result = {}
    for entry in configured:
        source = device_path(entry.get('source'))
        target = entry.get('target')
        uuid = target.removeprefix('/mnt/callas-') if target else ''
        options = set((entry.get('options') or '').split(','))
        if (source and UUID_PATTERN.fullmatch(uuid) and target == '/mnt/callas-' + uuid
                and sources.get(uuid) == {source}
                and base_options <= options and 'noauto' not in options):
            result[target] = source
    return result


def apply(user, live=False):
    account = pwd.getpwnam(user)
    if os.geteuid() != 0 or not account.pw_uid:
        raise ValueError('Requer root e uma conta de usuário normal.')
    original = FSTAB.lstat()
    if (not stat.S_ISREG(original.st_mode) or original.st_uid != 0
            or original.st_mode & 0o022):
        raise ValueError('/etc/fstab deve ser um arquivo regular protegido.')
    previous = FSTAB.read_bytes()

    root_mount = inventory('findmnt', '--kernel', '--json', '--list', '--nofsroot',
                           '--target', '/', '-o', 'SOURCE,TARGET')['filesystems']
    root_source = next((item['source'] for item in root_mount if item['target'] == '/'), None)
    disks = inventory('lsblk', '--json', '--paths', '--tree', '-o',
                      'NAME,TYPE,TRAN,RM,RO,HOTPLUG,FSTYPE,UUID,PTTYPE,PARTTYPE,PARTFLAGS,MOUNTPOINTS')['blockdevices']
    configured = inventory('findmnt', '--fstab', '--evaluate', '--json', '--list',
                           '-o', 'SOURCE,SOURCES,TARGET,OPTIONS')['filesystems']
    entries = plan_mounts(disks, root_source, configured, user, account.pw_uid,
                          account.pw_gid, available_target, report=print)
    sources = devices_by_uuid(device_nodes(disks))
    mounts = managed_mounts(configured, sources) if live else {}
    if not entries:
        print('Montagem automática: nenhuma nova partição de dados elegível.')
        if live:
            start_mounts(mounts)
        return

    created = []
    committed = False
    try:
        for target, _ in entries:
            path = Path(target)
            if not path.exists():
                path.mkdir(mode=0o700)
                created.append(path)
                path.chmod(0o755)
        separator = b'' if not previous or previous.endswith(b'\n') else b'\n'
        addition = '# Montagem de discos de dados — Callas OS\n'
        addition += ''.join(line + '\n' for _, line in entries)
        with tempfile.NamedTemporaryFile(dir=FSTAB.parent, prefix='.fstab.callas-',
                                         delete=False) as staged:
            temporary = Path(staged.name)
            try:
                os.fchown(staged.fileno(), original.st_uid, original.st_gid)
                os.fchmod(staged.fileno(), stat.S_IMODE(original.st_mode))
                staged.write(previous + separator + addition.encode('utf-8'))
                staged.flush()
                os.fsync(staged.fileno())
                verify_candidate(temporary)
                current = FSTAB.lstat()
                if ((current.st_dev, current.st_ino, current.st_ctime_ns)
                        != (original.st_dev, original.st_ino, original.st_ctime_ns)
                        or FSTAB.read_bytes() != previous):
                    raise RuntimeError('/etc/fstab mudou durante a atualização; reaplique a etapa.')
                os.replace(temporary, FSTAB)
                committed = True
            finally:
                temporary.unlink(missing_ok=True)
    finally:
        if not committed:
            for path in reversed(created):
                with suppress(OSError):
                    path.rmdir()
    for target, row in entries:
        print(f'Montagem no boot configurada em {target}.')
        if live:
            uuid = row.split('\t', 1)[0].removeprefix('UUID=').lower()
            mounts[target] = next(iter(sources[uuid]))
    if live:
        start_mounts(mounts)



def rescue_dirty_ntfs():
    """Fail closed: offer read-only access to configured dirty NTFS data volumes.

    Never repair metadata, clear the dirty bit, use force or change /etc/fstab.
    Only an existing, protected data mountpoint is eligible.
    """
    if os.geteuid() != 0:
        raise ValueError('Resgate NTFS requer root.')
    records = inventory('findmnt', '--fstab', '--evaluate', '--json',
                        '--list', '-o', 'SOURCE,TARGET,FSTYPE,OPTIONS').get('filesystems', [])
    journal = subprocess.run(
        ['journalctl', '--kernel', '--boot', '--no-pager', '--output=cat'],
        capture_output=True, text=True, check=False,
    )
    if journal.returncode:
        print('Resgate NTFS: sem mensagens verificáveis do kernel; nenhuma montagem forçada.')
        return
    driver = Path('/usr/bin/ntfs-3g')
    for entry in records:
        target = entry.get('target') or ''
        source = entry.get('source') or ''
        fstype = (entry.get('fstype') or '').lower()
        options = (entry.get('options') or '').split(',')
        if (fstype not in ('ntfs3', 'ntfs', 'ntfs-3g')
                or 'noauto' in options
                or not target.startswith(('/mnt/', '/media/', '/run/media/'))
                or not source.startswith('/dev/')):
            continue
        mountpoint = Path(target)
        device = Path(os.path.realpath(source))
        if (not device.is_block_device() or device.name.startswith(('dm-', 'loop'))
                or not available_target(target, False)):
            # This also rejects symlinks, occupied/mounted or unprotected directories.
            continue
        if subprocess.run(['findmnt', '--kernel', '--mountpoint', target],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
            continue
        signature = subprocess.run(
            ['blkid', '-s', 'TYPE', '-o', 'value', str(device)],
            capture_output=True, text=True, check=False,
        )
        if signature.returncode or signature.stdout.strip() != 'ntfs':
            continue
        # A dirty NTFS marker for this exact device must be present in this boot.
        pattern = r'ntfs3\(' + re.escape(device.name) + r'\):.*volume is dirty'
        if not re.search(pattern, journal.stdout, re.IGNORECASE):
            continue
        if not driver.is_file():
            print(f'Resgate NTFS: {device}: instale ntfs-3g; volume preservado.')
            continue
        owner_options = [
            option for key in ('uid', 'gid')
            for option in options
            if re.fullmatch(key + r'=[0-9]{1,10}', option)
        ]
        mount_options = ','.join(['ro', 'nosuid', 'nodev', 'noexec', 'umask=0077', *owner_options])
        print(f'Resgate NTFS: {device} inconsistente; tentando {target} SOMENTE LEITURA.')
        attempt = subprocess.run(
            ['/usr/bin/timeout', '15s', str(driver), '-o', mount_options,
             str(device), target],
            capture_output=True, text=True, check=False,
        )
        mounted = subprocess.run(
            ['findmnt', '--kernel', '--mountpoint', target, '--noheadings', '-o', 'OPTIONS'],
            capture_output=True, text=True, check=False,
        )
        mounted_options = set(mounted.stdout.strip().split(',')) if not mounted.returncode else set()
        if attempt.returncode == 0 and 'ro' in mounted_options:
            print(f'Resgate NTFS: {target} disponível SOMENTE PARA LEITURA. '
                  'Copie seus dados e repare no Windows com chkdsk.')
        else:
            detail = (attempt.stderr or attempt.stdout).strip().replace('\n', ' ')[:350]
            print(f'Resgate NTFS: {target} não recuperado: {detail or "montagem recusada"}. '
                  'Sem alterações no volume; considere recuperação especializada.')


if __name__ == '__main__':
    try:
        if sys.argv[1:] == ['--rescue']:
            rescue_dirty_ntfs()
        elif len(sys.argv) in (2, 3) and (len(sys.argv) == 2 or sys.argv[2] == '--live'):
            apply(sys.argv[1], live=len(sys.argv) == 3)
        else:
            raise ValueError('Uso interno: callas-automount USUARIO [--live] | --rescue')
    except (KeyError, OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'Montagem automática: {error}', file=sys.stderr)
        sys.exit(1)
