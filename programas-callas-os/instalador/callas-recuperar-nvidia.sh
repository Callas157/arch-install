#!/usr/bin/env bash
# Retoma SOMENTE a configuração interna do instalador que parou no mkinitcpio.
# Nunca formata, particiona, reinstala o sistema ou pergunta sobre discos.
set -Eeuo pipefail
export PATH=/usr/bin:/bin
umask 077
(( EUID == 0 )) || { echo 'Execute como root na ISO oficial do Arch.' >&2; exit 1; }
[[ -f /run/archiso/bootmnt/loader/entries/archiso-x86_64-linux.conf || -d /run/archiso/bootmnt ]] || {
  echo 'Este reparo foi feito exclusivamente para a ISO do Arch Linux.' >&2; exit 1;
}
mountpoint -q /mnt || { echo 'ERRO: /mnt não está montado. Não vou montar nem formatar nada.' >&2; exit 1; }
mountpoint -q /mnt/boot || { echo 'ERRO: /mnt/boot não está montado. Não mexi nos discos.' >&2; exit 1; }
[[ $(findmnt -no FSTYPE /mnt/boot) == vfat ]] || { echo 'ERRO: /mnt/boot não contém a partição EFI FAT32.' >&2; exit 1; }
[[ -f /mnt/etc/arch-release && -f /mnt/etc/callas-nvidia-version ]] || { echo 'ERRO: não encontrei o Callas OS NVIDIA instalado em /mnt.' >&2; exit 1; }
versao_nvidia=$(< /mnt/etc/callas-nvidia-version)
[[ $versao_nvidia == 595.* || $versao_nvidia == 610.57.04 ]] || { echo 'ERRO: versão NVIDIA não reconhecida para esta recuperação.' >&2; exit 1; }
[[ -f /mnt/usr/local/share/callas-os/install-config.sh ]] || { echo 'ERRO: o script de configuração interrompido não foi encontrado.' >&2; exit 1; }
[[ -d /mnt/usr/local/share/callas-os/security-stage ]] || { echo 'ERRO: arquivos verificados da instalação não estão presentes.' >&2; exit 1; }
[[ -f /mnt/usr/local/share/callas-os/security-stage/callas-security.sh ]] || { echo 'ERRO: fase interna da instalação ausente; não é seguro retomar.' >&2; exit 1; }

# Verifica a árvore do GitHub e o SHA do auxiliar de preparo dos módulos antes
# de copiá-lo ao sistema; nunca troca a versão do driver nem atualiza kernels.
python - <<'CALLAS_RECOVERY_PREPARE'
import hashlib, json, pathlib, re, urllib.request
base = 'https://api.github.com/repos/Callas157/arch-install'
headers = {'User-Agent': 'CallasOS-Arch-Rescue'}
def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
        return response.read()
head = json.loads(fetch(base + '/git/ref/heads/main'))['object']['sha']
if not re.fullmatch(r'[0-9a-f]{40}', head):
    raise RuntimeError('Referência GitHub inválida.')
tree = json.loads(fetch(base + '/git/trees/' + head + '?recursive=1'))
if tree.get('truncated'):
    raise RuntimeError('Árvore GitHub incompleta.')
installed = pathlib.Path('/mnt/etc/callas-nvidia-version').read_text().strip()
helper = 'callas-nvidia-prepare.py' if installed.startswith('595.') else 'callas-nvidia-610-prepare.py'
name = 'programas-callas-os/instalador/' + helper
match = [row for row in tree['tree'] if row.get('path') == name and row.get('type') == 'blob']
if len(match) != 1:
    raise RuntimeError('Preparador NVIDIA não encontrado.')
payload = fetch('https://raw.githubusercontent.com/Callas157/arch-install/' + head + '/' + name)
digest = hashlib.sha1(b'blob ' + str(len(payload)).encode() + b'\0' + payload).hexdigest()
if digest != match[0]['sha']:
    raise RuntimeError('Integridade do preparador NVIDIA não confere com GitHub.')
compile(payload, name, 'exec')
target = pathlib.Path('/mnt/usr/local/libexec') / helper.removesuffix('.py')
if not target.parent.is_dir() or target.is_symlink():
    raise RuntimeError('Diretório auxiliar não é seguro.')
tmp = target.with_name('.callas-nvidia-prepare-new')
tmp.write_bytes(payload)
tmp.chmod(0o755)
tmp.replace(target)
print('Preparador NVIDIA validado, commit ' + head[:12])
CALLAS_RECOVERY_PREPARE

# Repara e valida os quatro módulos para CADA kernel instalado, antes de GRUB.
if [[ $versao_nvidia == 595.* ]]; then
  arch-chroot /mnt /usr/local/libexec/callas-nvidia-prepare
else
  arch-chroot /mnt /usr/local/libexec/callas-nvidia-610-prepare
fi
arch-chroot /mnt /usr/bin/mkinitcpio -P

# Constrói uma continuação somente a partir da etapa seguinte ao mkinitcpio
# do instalador interrompido. Não reexecuta pacstrap, wipefs, mkfs nem pacman.
python - <<'CALLAS_RECOVERY_RESUME'
import json, pathlib, re, subprocess
root = pathlib.Path('/mnt')
original = root / 'usr/local/share/callas-os/install-config.sh'
if original.is_symlink() or not original.is_file():
    raise RuntimeError('Configuração interna ausente ou caminho inseguro.')
source = original.read_text()
anchor = '\nmkinitcpio -P\n'
if source.count(anchor) != 1:
    raise RuntimeError('Ponto de retomada não identificado com segurança.')
remaining = source.split(anchor, 1)[1]
for required in ('# Tema gráfico Callas OS.', 'grub-install --target=x86_64-efi',
                 'CALLAS_RELEASE_DIR=/usr/local/share/callas-os/security-stage',
                 'callas-storage-setup', 'callas-version'):
    if required not in remaining:
        raise RuntimeError('Configuração interna inesperada; não executarei continuação parcial.')
# Somente o usuário local criado na instalação é candidato.
accounts = []
for line in (root / 'etc/passwd').read_text().splitlines():
    cells = line.split(':')
    if len(cells) >= 7 and cells[2].isdigit() and 1000 <= int(cells[2]) < 60000 and cells[5] == '/home/' + cells[0]:
        accounts.append(cells[0])
if len(accounts) != 1 or not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', accounts[0]):
    raise RuntimeError('Não foi possível identificar um único usuário da instalação.')
username = accounts[0]
locale = 'pt_BR.UTF-8'
for line in (root / 'etc/locale.conf').read_text().splitlines():
    if line.startswith('LANG='):
        locale = line[5:].strip().strip('"')
if not re.fullmatch(r'[A-Za-z0-9_.@-]{2,40}', locale):
    raise RuntimeError('Locale da instalação inválido.')
ref = (root / 'usr/local/share/callas-os/security-stage/commit').read_text().strip()
if not re.fullmatch(r'[0-9a-f]{40}', ref):
    raise RuntimeError('Referência dos arquivos de configuração não é imutável.')
mount = subprocess.run(('findmnt', '-no', 'UUID', '/mnt'), capture_output=True, text=True, check=True)
root_uuid = mount.stdout.strip()
if not re.fullmatch(r'[a-fA-F0-9-]{8,64}', root_uuid):
    raise RuntimeError('Não consegui verificar o UUID do sistema montado em /mnt.')
header = '''#!/usr/bin/bash
set -Eeuo pipefail
trap 'code=$?; printf "ERRO: retomada do Callas OS falhou na linha %s (código %s).\\n" "$LINENO" "$code" >&2; exit "$code"' ERR
usuario=''' + json.dumps(username) + '''
home=/home/$usuario
locale=''' + json.dumps(locale) + '''
uuid_raiz=''' + json.dumps(root_uuid) + '''
libexec=/usr/local/libexec
nvidia=1
broadcom=0
risemode=0
nvidia_args=' nvidia_drm.modeset=1 nvidia_drm.fbdev=1'
asset_base=''' + json.dumps('https://raw.githubusercontent.com/Callas157/arch-install/' + ref + '/assets') + '''
avisos=/var/log/callas-instalacao-avisos.log
aviso() { printf 'Aviso: %s\\n' "$*" | tee -a "$avisos" >&2; }
como_usuario() { runuser -u "$usuario" -- env HOME="$home" USER="$usuario" LOGNAME="$usuario" "$@"; }
'''
path = root / 'usr/local/share/callas-os/continuar-config-apos-nvidia.sh'
if path.is_symlink():
    raise RuntimeError('Caminho de continuação não é seguro.')
path.write_text(header + remaining)
path.chmod(0o700)
print('Recuperação preparada para o usuário', username, 'e UUID', root_uuid)
CALLAS_RECOVERY_RESUME
bash -n /mnt/usr/local/share/callas-os/continuar-config-apos-nvidia.sh
arch-chroot /mnt /usr/bin/bash /usr/local/share/callas-os/continuar-config-apos-nvidia.sh
printf '\nOK: Configuração interna concluída sem formatar discos. Retire a ISO e reinicie quando quiser.\n'
