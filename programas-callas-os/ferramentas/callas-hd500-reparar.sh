#!/usr/bin/env bash
# Somente o HD500G formatado, identificado por UUID, modelo, tipo e tamanho.
# --recriar: APAGA a particao, tenta liberar setor pendente, verifica superficie.
set -Eeuo pipefail
export LC_ALL=C
[[ $# -eq 1 && "${1:-}" == --recriar ]] || { echo 'Use --recriar: APAGA todo o conteudo do HD500G.' >&2; exit 2; }
OLD_UUID='e7c966bb-cf88-446e-bac7-ec1685d80b65'
OLD_NTFS_UUID='D4C63EEAC63ECC8C'
MNT='/mnt/hd-500'
OWNER="${SUDO_USER:-}"
[[ $EUID == 0 && -n "$OWNER" && "$OWNER" != root ]] && id "$OWNER" >/dev/null ||
  { echo 'Execute com sudo bash, a partir da sua conta normal.' >&2; exit 2; }
HOME_USER="$(getent passwd "$OWNER" | cut -d: -f6)"
LOG="$HOME_USER/callas-hd500-$(date +%Y%m%d-%H%M%S).log"
touch "$LOG"; chown "$OWNER":"$(id -gn "$OWNER")" "$LOG"
exec > >(tee -a "$LOG") 2>&1
fail(){ echo "FALHA: $*"; echo "Log: $LOG"; exit 1; }
phase(){ printf '\n==> %s\n' "$*"; }
trap 'echo "Erro na linha $LINENO; log: $LOG" >&2' ERR
phase 'Validando IDENTIDADE fisica antes de alterar qualquer dado.'
for bin in blkid lsblk findmnt smartctl e2fsck mount umount install awk cp mktemp systemctl blockdev dd mkfs.ext4 badblocks runuser udevadm; do
  command -v "$bin" >/dev/null || fail "Ferramenta ausente: $bin"
done
P="$(blkid -U "$OLD_UUID" 2>/dev/null || true)"
[[ -n "$P" && -b "$P" ]] || fail 'Nao achei o HD500G com seu UUID ext4 anterior; nada foi escrito.'
[[ "$(lsblk -dn -o TYPE "$P" | xargs)" == part ]] || fail 'Nao e particao.'
[[ "$(blkid -s TYPE -o value "$P")" == ext4 ]] || fail 'Nao e ext4.'
[[ "$(blkid -s LABEL -o value "$P")" == HD500G ]] || fail 'Rotulo incorreto.'
D="/dev/$(lsblk -dn -o PKNAME "$P" | xargs)"
[[ -b "$D" && "$(lsblk -dn -o TYPE "$D" | xargs)" == disk ]] || fail 'Disco pai invalido.'
MODEL="$(lsblk -dn -o MODEL "$D" | xargs)"
[[ "$MODEL" == *WD05PURX* ]] || fail "Modelo inesperado: $MODEL"
[[ "$(findmnt -n -o SOURCE /)" != "$P" ]] || fail 'Este disco contem o Arch.'
NBYTES="$(blockdev --getsize64 "$P")"
[[ "$NBYTES" =~ ^[0-9]+$ ]] && (( NBYTES > 400000000000 && NBYTES < 600000000000 )) ||
  fail 'Tamanho nao corresponde ao HD de 500GB.'
printf 'Confirmado: %s (%s), particao %s, %s bytes.\n' "$D" "$MODEL" "$P" "$NBYTES"
phase 'Lendo indicadores SMART.'
smartctl -H "$D" || true
smartctl -A "$D" | grep -E 'Reallocated_Sector_Ct|Current_Pending_Sector|Offline_Uncorrectable|UDMA_CRC_Error_Count' || true
PRE="$(smartctl -A "$D" | awk '$1==197{a=$NF}END{print a}')"
[[ "$PRE" =~ ^[0-9]+$ ]] || fail 'Nao consegui consultar setores pendentes; abortado.'
phase 'Desmontando com seguranca (nao interrompe jogos nem processos).'
if findmnt -rn -S "$P" >/dev/null 2>&1; then
  umount "$P" || fail 'Disco ocupado. Feche Steam/Dolphin usando o HD e repita o MESMO comando.'
fi
findmnt -rn -S "$P" >/dev/null 2>&1 && fail 'Disco continua montado.'
phase 'ZERANDO a particao para tentar provocar remapeamento do setor pendente.'
echo 'Esta operacao apaga todos os arquivos dessa particao. NAO toca o disco do Arch.'
BS=$((4*1024*1024))
BLOCKS=$((NBYTES/BS))
REMAIN=$((NBYTES%BS))
dd if=/dev/zero of="$P" bs=4M count="$BLOCKS" iflag=fullblock oflag=direct conv=fsync status=progress ||
  fail 'Erro de gravação no disco; hardware instavel.'
if (( REMAIN )); then
  (( REMAIN%512==0 )) || fail 'Tamanho final desalinhado.'
  dd if=/dev/zero of="$P" bs=512 seek="$((BLOCKS*8192))" count="$((REMAIN/512))" oflag=direct conv=fsync status=progress ||
    fail 'Falha escrevendo final da particao.'
fi
sync
phase 'Conferindo resultado SMART da escrita.'
smartctl -A "$D" | grep -E 'Reallocated_Sector_Ct|Current_Pending_Sector|Offline_Uncorrectable|UDMA_CRC_Error_Count' || true
MID="$(smartctl -A "$D" | awk '$1==197{a=$NF}END{print a}')"
[[ "$MID" =~ ^[0-9]+$ && "$MID" == 0 ]] ||
  fail "Ainda ha $MID setor(es) pendente(s); este HD precisa ser substituido."
phase 'Recriando ext4. O UUID anterior vai mudar.'
mkfs.ext4 -F -L HD500G "$P" || fail 'Falha no mkfs.ext4.'
udevadm settle || true
NEW_UUID="$(blkid -p -s UUID -o value "$P")"
[[ "$NEW_UUID" =~ ^[[:xdigit:]-]{36}$ ]] || fail 'Novo UUID invalido.'
phase 'Varredura COMPLETA de leitura, sem gravar arquivos no disco.'
BADS="$(mktemp /tmp/callas-badblocks.XXXXXXXX)"
badblocks -b 4096 -s -v -o "$BADS" "$P" || fail "Falha na leitura completa; lista: $BADS"
[[ ! -s "$BADS" ]] || fail "Foram encontrados setores defeituosos; lista: $BADS"
rm -f "$BADS"
phase 'Conferindo e corrigindo ext4 automaticamente.'
set +e
e2fsck -f -p "$P"
EC=$?
set -e
(( (EC & (4|8|16|32|128))==0 )) || fail "e2fsck nao pode deixar o ext4 consistente (codigo $EC)."
POST="$(smartctl -A "$D" | awk '$1==197{a=$NF}END{print a}')"
[[ "$POST" =~ ^[0-9]+$ && "$POST" == 0 ]] || fail "Persistem setores pendentes ($POST): HD nao confiavel."
phase 'Gravando montagem permanente por UUID, com backup do /etc/fstab.'
BK="/etc/fstab.callas-hd500.$(date +%Y%m%d-%H%M%S).bak"
cp -a /etc/fstab "$BK"
TMP="$(mktemp /etc/.callas-hd500.XXXXXX)"
trap 'rm -f "$TMP"' EXIT
awk -v uuid="$NEW_UUID" -v old="$OLD_NTFS_UUID" -v mountpoint="$MNT" '
  $1!~/^#/ && NF>=4 && ($2==mountpoint || ($1=="UUID="old && $2==mountpoint)) {next}
  {print}
  END {print "UUID="uuid" "mountpoint" ext4 defaults,nofail,x-systemd.device-timeout=10s 0 2"}
' /etc/fstab > "$TMP"
chmod --reference=/etc/fstab "$TMP"
chown --reference=/etc/fstab "$TMP"
mv -f "$TMP" /etc/fstab
trap - EXIT
install -d -m 755 "$MNT"
systemctl daemon-reload
mount "$MNT" || fail "Falhou montar ext4; backup do fstab: $BK"
SRC="$(findmnt -rn -M "$MNT" -o SOURCE)"
OPT="$(findmnt -rn -M "$MNT" -o OPTIONS)"
[[ "$(readlink -f "$SRC")" == "$(readlink -f "$P")" ]] || fail "Montou dispositivo inesperado: $SRC"
[[ ",$OPT," == *,rw,* && ",$OPT," != *,emergency_ro,* ]] || fail 'HD voltou a somente leitura.'
phase 'Criando SteamLibrary e verificando escrita com sua conta.'
install -d -o "$(id -u "$OWNER")" -g "$(id -g "$OWNER")" -m 755 "$MNT/SteamLibrary" ||
  fail 'Falha ao criar SteamLibrary.'
TEST="$MNT/SteamLibrary/.callas-test-$$"
runuser -u "$OWNER" -- touch "$TEST" || fail 'Nao foi possivel escrever no HD.'
rm -f "$TEST"
sync
if journalctl -k -b --since '-3 minutes' --no-pager |
   grep -Eiq 'I/O error, dev sda([, :]|$)|EXT4-fs error \(device sda1\)|Aborting journal on device sda1'; then
  fail 'Kernel voltou a detectar erro de leitura. HD nao confiavel.'
fi
printf '\nSUCESSO DE LEITURA/ESCRITA: %s/SteamLibrary\n' "$MNT"
echo 'Selecione esta pasta no Armazenamento da Steam para substituir a biblioteca antiga.'
echo "ATENCAO: um HD que ja teve setor pendente pode falhar novamente. Nao guarde arquivos importantes."
echo "Log: $LOG | Backup fstab: $BK"
