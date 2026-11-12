#!/usr/bin/env bash
# =====================================================================
# Instalação automática do Arch Linux
# KDE Plasma (Wayland) + SDDM | pt-BR | UEFI | GRUB Callas OS | ext4
# NVIDIA compatível com nvidia-open ou Mesa | microcódigo AMD/Intel
# Teclado: EUA Internacional | Steam, Discord, AUR (Paru), Flatpak
# ProtonPlus (Flathub) | Nekofetch + Fastfetch | Ark (RAR, ZIP e 7z)
# Solaar na bandeja | xone para receptor Xbox Wireless | qBittorrent | Spotify (AUR)
#
# ATENÇÃO: APAGA TODO O DISCO ESCOLHIDO NO INÍCIO DO SCRIPT
# Tema GRUB + Plymouth Callas OS | atualizador do KDE | Spotify
# Rodar na ISO do Arch Linux, com internet por cabo.
# =====================================================================
set -Eeuo pipefail
trap 'printf "ERRO: instalação interrompida na linha %s.\n" "$LINENO" >&2' ERR

# ---------------- Configurações ----------------
DISCO="${DISCO:-}"   # se vazio, o script pergunta em qual disco instalar
HOSTNAME="arch"
FUSO="America/Sao_Paulo"
LOCALE="pt_BR.UTF-8"
TECLADO="us-acentos"   # console: EUA Internacional (com acentos)
command -v python >/dev/null || { echo 'Python ausente na ISO oficial.' >&2; exit 1; }
CALLAS_ASSET_REF="${CALLAS_ASSET_REF:-main}"
if [[ $CALLAS_ASSET_REF == main ]]; then
  CALLAS_ASSET_REF=$(python - <<'CALLAS_REF'
import json, urllib.request
req=urllib.request.Request('https://api.github.com/repos/Callas157/arch-install/git/ref/heads/main', headers={'User-Agent':'CallasOS-Installer'})
with urllib.request.urlopen(req, timeout=60) as response:
    print(json.load(response)['object']['sha'])
CALLAS_REF
  )
fi
[[ $CALLAS_ASSET_REF =~ ^[0-9a-f]{40}$ ]] || { echo 'Referência de instalação inválida.' >&2; exit 1; }
CALLAS_ASSET_BASE="https://raw.githubusercontent.com/Callas157/arch-install/${CALLAS_ASSET_REF}/assets"
CALLAS_PROGRAMAS_BASE="https://raw.githubusercontent.com/Callas157/arch-install/${CALLAS_ASSET_REF}/programas-callas-os"
# -----------------------------------------------

if [[ $EUID -ne 0 ]]; then
  echo "Rode como root (na ISO do Arch já é)."; exit 1
fi

if [[ ! -d /sys/firmware/efi/efivars ]]; then
  echo "ERRO: inicie a ISO em UEFI. Em uma VM, habilite EFI no virtualizador."; exit 1
fi

if ! curl -fsSL --connect-timeout 10 --max-time 20 https://archlinux.org/ -o /dev/null; then
  echo "ERRO: sem internet. Confira o cabo de rede."; exit 1
fi

loadkeys "$TECLADO" || true

# ---------------- Detecção do processador ----------------
if grep -q "GenuineIntel" /proc/cpuinfo; then
  UCODE_PACKAGE="intel-ucode"
  echo "Processador Intel detectado."
elif grep -q "AuthenticAMD" /proc/cpuinfo; then
  UCODE_PACKAGE="amd-ucode"
  echo "Processador AMD detectado."
else
  echo "ERRO: não foi possível identificar o fabricante do processador."
  exit 1
fi

# ---------------- Detecção da rede (Wi-Fi / cabo) ----------------
# A maioria dos adaptadores (Intel, Realtek, Qualcomm, MediaTek) já funciona
# com o kernel + linux-firmware. Aqui entram só os pacotes extras necessários.
REDE_PACOTES=()
BROADCOM=0
PCI_REDE="$(lspci -nn 2>/dev/null | grep -Ei 'ethernet controller|network controller|802\.11' || true)"
USB_REDE="$(lsusb 2>/dev/null | grep -Ei 'wireless|wlan|802\.11|wi-?fi' || true)"
TEM_WIFI=0
if grep -Eiq 'network controller|802\.11|wireless|wi-?fi' <<<"$PCI_REDE"$'\n'"$USB_REDE" \
   || compgen -G "/sys/class/net/*/wireless" >/dev/null; then
  TEM_WIFI=1
  REDE_PACOTES+=(wpa_supplicant iw wireless-regdb)
fi
# Broadcom Wi-Fi que precisa do driver proprietário wl
if grep -Eiq 'broadcom.*BCM(4311|4312|4321|4322|43142|43227|43228|4331|4352|4360)\b' <<<"$PCI_REDE"; then
  BROADCOM=1
fi
if grep -qi 'ethernet controller' <<<"$PCI_REDE"; then echo "Placa de rede cabeada detectada."; fi
if (( TEM_WIFI )); then echo "Adaptador Wi-Fi detectado."; fi
if (( BROADCOM )); then echo "Wi-Fi Broadcom detectado: será instalado o driver broadcom-wl-dkms."; fi

# ---------------- Detecção gráfica ----------------
# Suporta também máquinas com mais de uma GPU: cada fabricante encontrado
# acrescenta somente o conjunto de pacotes correspondente.
GPU_PCI="$(lspci -Dn | awk '$2 ~ /^03[[:xdigit:]][[:xdigit:]]:$/ {print $3}')"
NVIDIA=0
AMD_GPU=0
INTEL_GPU=0
VM="$(systemd-detect-virt --vm || true)"
GPU_PACOTES=(mesa)

if grep -q '^10de:' <<<"$GPU_PCI"; then
  NVIDIA=1
  GPU_PACOTES+=(egl-wayland)
  echo "GPU NVIDIA detectada: usando NVIDIA 610.57.04 fixado pelo Callas OS."
fi
if grep -q '^1002:' <<<"$GPU_PCI"; then
  AMD_GPU=1
  GPU_PACOTES+=(vulkan-radeon)
  echo "GPU AMD Radeon detectada: usando Mesa + RADV."
fi
if grep -q '^8086:' <<<"$GPU_PCI"; then
  INTEL_GPU=1
  GPU_PACOTES+=(vulkan-intel)
  echo "GPU Intel detectada: usando Mesa + ANV."
fi
if (( ! NVIDIA && ! AMD_GPU && ! INTEL_GPU )); then
  echo "GPU sem perfil específico; usando Mesa (ambiente: ${VM:-nativo})."
fi

# ---------------- Detecção do water cooler Rise Mode ----------------
# O driver abaixo é específico do dispositivo USB aa88:8666. Se ele não
# estiver presente, a instalação segue normalmente sem baixar ou compilar nada.
RISEMODE=0
RISEMODE_PACOTES=()
for usbdev in /sys/bus/usb/devices/*; do
  [[ -r "$usbdev/idVendor" && -r "$usbdev/idProduct" ]] || continue
  if [[ "$(<"$usbdev/idVendor")" == "aa88" && "$(<"$usbdev/idProduct")" == "8666" ]]; then
    RISEMODE=1
    break
  fi
done
if (( ! RISEMODE )) && command -v lsusb >/dev/null 2>&1 &&
   lsusb 2>/dev/null | grep -qi 'aa88:8666'; then
  RISEMODE=1
fi
if (( RISEMODE )); then
  echo "Water cooler Rise Mode aa88:8666 detectado: o driver será instalado automaticamente."
  RISEMODE_PACOTES=(rustup pkgconf hidapi libusb clang)
else
  echo "Water cooler Rise Mode aa88:8666 não detectado: integração será ignorada."
fi

# ---------------- Pré-verificação NVIDIA ----------------
# Em máquinas NVIDIA, confirma a disponibilidade da pilha 610 antes de qualquer
# operação destrutiva no disco.
if (( NVIDIA )); then
  NVIDIA_610_URLS=(
    "https://archive.archlinux.org/packages/n/nvidia-utils/nvidia-utils-610.57.04-1-x86_64.pkg.tar.zst"
    "https://archive.archlinux.org/packages/n/nvidia-open-dkms/nvidia-open-dkms-610.57.04-1-x86_64.pkg.tar.zst"
    "https://archive.archlinux.org/packages/l/lib32-nvidia-utils/lib32-nvidia-utils-610.57.04-1-x86_64.pkg.tar.zst"
    "https://archive.archlinux.org/packages/l/libxnvctrl/libxnvctrl-610.57.04-1-x86_64.pkg.tar.zst"
    "https://archive.archlinux.org/packages/n/nvidia-settings/nvidia-settings-610.57.04-1-x86_64.pkg.tar.zst"
  )
  echo ">>> Verificando NVIDIA 610.57.04 no Arch Linux Archive"
  for url in "${NVIDIA_610_URLS[@]}"; do
    curl -fIsSL --retry 2 --connect-timeout 10 --max-time 30 "$url" >/dev/null ||
      { echo "ERRO: pacote NVIDIA indisponível: ${url##*/}" >&2; exit 1; }
    curl -fIsSL --retry 2 --connect-timeout 10 --max-time 30 "$url.sig" >/dev/null ||
      { echo "ERRO: assinatura NVIDIA indisponível: ${url##*/}.sig" >&2; exit 1; }
  done
  echo "NVIDIA 610.57.04 disponível e pronta para a instalação."
fi

# Valida a ferramenta adicional antes de apagar o disco.
command -v python >/dev/null || { echo "ERRO: Python ausente na ISO. Instale com pacman -Sy python antes de continuar."; exit 1; }
CALLAS_MONITOR_TMP=$(mktemp)
curl -fsSL --retry 2 --connect-timeout 10 --max-time 120 \
  "$CALLAS_PROGRAMAS_BASE/monitores/callas-monitores.py" \
  -o "$CALLAS_MONITOR_TMP"
python - "$CALLAS_MONITOR_TMP" <<'CALLAS_MONITOR_CHECK'
import ast, sys
ast.parse(open(sys.argv[1], encoding="utf-8").read())
CALLAS_MONITOR_CHECK
CALLAS_WINDOW_TMP=$(mktemp)
curl -fsSL --retry 2 --connect-timeout 10 --max-time 120 \
  "$CALLAS_PROGRAMAS_BASE/janelas/callas-janelas.py" \
  -o "$CALLAS_WINDOW_TMP"
python - "$CALLAS_WINDOW_TMP" <<'CALLAS_WINDOW_CHECK'
import ast, sys
ast.parse(open(sys.argv[1], encoding="utf-8").read())
CALLAS_WINDOW_CHECK

# Security helpers are staged before the destructive installation starts.
CALLAS_SECURITY_TMP=$(mktemp -d)
curl --proto '=https' --proto-redir '=https' -fsSL --retry 2 \
  "https://raw.githubusercontent.com/Callas157/arch-install/$CALLAS_ASSET_REF/programas-callas-os/atualizador/callas-release.py" \
  -o "$CALLAS_SECURITY_TMP/callas-release.py"
python - "$CALLAS_SECURITY_TMP" "$CALLAS_ASSET_REF" <<'CALLAS_STAGE'
import importlib.util, sys
spec=importlib.util.spec_from_file_location('callas_release', sys.argv[1]+'/callas-release.py')
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
module.stage_files(sys.argv[1], sys.argv[2])
CALLAS_STAGE

# ---------------- Escolha do disco ----------------
BOOTPART="$(findmnt -no SOURCE /run/archiso/bootmnt 2>/dev/null || true)"
BOOTDISK=""
if [[ -b "$BOOTPART" ]]; then
  BOOTDISK="$(lsblk -npro NAME,TYPE -s "$BOOTPART" | awk '$2 == "disk" && !found++ {print $1}')"
fi
if [[ -z "$DISCO" ]]; then
  mapfile -t LISTA < <(lsblk -dpno NAME,TYPE,RO | awk '$2=="disk" && $3==0 {print $1}' | grep -v '/zram' | grep -vx "$BOOTDISK" || true)
  if (( ${#LISTA[@]} == 0 )); then
    echo "ERRO: nenhum disco encontrado."; exit 1
  fi
  echo
  echo "Discos encontrados:"
  for i in "${!LISTA[@]}"; do
    INFO="$(lsblk -dno SIZE,MODEL "${LISTA[$i]}")"
    echo "  $((i+1))) ${LISTA[$i]}  -  $INFO"
  done
  echo
  read -rp "Em qual disco instalar o sistema? (digite o número): " ESCOLHA
  if ! [[ "$ESCOLHA" =~ ^[1-9][0-9]{0,5}$ ]] || (( ESCOLHA > ${#LISTA[@]} )); then
    echo "Opção inválida."; exit 1
  fi
  DISCO="${LISTA[$((ESCOLHA-1))]}"
fi

DISCO="$(readlink -f -- "$DISCO")"
if [[ ! -b "$DISCO" || "$(lsblk -dnro TYPE,RO "$DISCO")" != "disk 0" ]]; then
  echo "ERRO: destino $DISCO não é um disco gravável."
  exit 1
fi
if [[ "$DISCO" == "$BOOTDISK" ]] ||
   [[ -n "$(lsblk -nr -o MOUNTPOINTS "$DISCO" | sed '/^$/d')" ]]; then
  echo "ERRO: o disco selecionado tem partições em uso ou é a mídia de instalação."
  exit 1
fi

echo
echo "=========================================================="
echo " TODOS OS DADOS DESTE DISCO SERÃO APAGADOS:"
lsblk -o NAME,SIZE,MODEL,FSTYPE "$DISCO"
echo "=========================================================="

read -rp "Nome do usuário (minúsculas, sem espaços): " USUARIO
[[ "$USUARIO" =~ ^[a-z_][a-z0-9_-]{0,31}$ && "$USUARIO" != root && "$USUARIO" != put-aur ]] || { echo "Nome de usuário inválido."; exit 1; }

while true; do
  read -rsp "Senha do usuário (e do root): " SENHA; echo
  read -rsp "Repita a senha: " SENHA2; echo
  [[ -n "$SENHA" && "$SENHA" == "$SENHA2" ]] && break
  echo "As senhas não conferem, tente de novo."
done

# Full installation output, excluding hidden password input and without shell tracing.
CALLAS_INSTALL_LOG=$(mktemp /var/tmp/callas-install.XXXXXXXX.log)
finish_installation() {
  local code=$?
  trap - EXIT
  exec 1>&3 2>&4
  wait "$CALLAS_INSTALL_LOG_PID" || :
  if mountpoint -q /mnt; then
    install -d -m 0700 /mnt/var/log/callas-os/Instalacao
    install -d -m 0755 /mnt/var/lib/callas-os
    install -m 0600 "$CALLAS_INSTALL_LOG" "/mnt/var/log/callas-os/Instalacao/$(date +%Y-%m-%d_%Hh%Mm%Ss).log"
    if (( code )); then
      printf 'Instalação incompleta: código %s. Veja /var/log/callas-os/Instalacao.\n' "$code" > /mnt/var/lib/callas-os/installation-failed
    else
      rm -f /mnt/var/lib/callas-os/installation-failed
    fi
    if [[ -x /mnt/usr/local/libexec/callas-logs ]] && arch-chroot /mnt id "$USUARIO" >/dev/null 2>&1; then
      arch-chroot /mnt /usr/local/libexec/callas-logs --export "$USUARIO" || :
    fi
  fi
  printf 'Log desta execução na ISO: %s\n' "$CALLAS_INSTALL_LOG"
  exit "$code"
}
exec 3>&1 4>&2
exec > >(tee "$CALLAS_INSTALL_LOG") 2>&1
CALLAS_INSTALL_LOG_PID=$!
trap finish_installation EXIT

# ---------------- Preparação da ISO ----------------
timedatectl set-ntp true
sed -i 's/^#ParallelDownloads.*/ParallelDownloads = 10/' /etc/pacman.conf
pacman -Sy --noconfirm archlinux-keyring

# ---------------- Particionamento ----------------
echo ">>> Particionando $DISCO"
umount -R /mnt 2>/dev/null || true
wipefs -af "$DISCO"
sgdisk --zap-all "$DISCO"
sgdisk -n 1:0:+1G -t 1:ef00 -c 1:"EFI" "$DISCO"
sgdisk -n 2:0:0   -t 2:8300 -c 2:"ARCH" "$DISCO"
partprobe "$DISCO"
udevadm settle

if [[ "$DISCO" =~ [0-9]$ ]]; then SEP="p"; else SEP=""; fi
EFI="${DISCO}${SEP}1"
RAIZ="${DISCO}${SEP}2"

mkfs.fat -F32 "$EFI"
mkfs.ext4 -F "$RAIZ"

mount "$RAIZ" /mnt
mount --mkdir -o fmask=0077,dmask=0077 "$EFI" /mnt/boot

# ---------------- Instalação base ----------------
echo ">>> Instalando pacotes (isso demora)"
pacstrap -K /mnt \
  base linux linux-lts linux-firmware "$UCODE_PACKAGE" base-devel sudo nano git curl gnupg acl grub efibootmgr \
  linux-headers linux-lts-headers dkms pciutils usbutils libnotify \
  networkmanager "${REDE_PACOTES[@]}" \
  plasma-desktop sddm sddm-kcm plasma-nm plasma-pa kscreen powerdevil xorg-xwayland \
  konsole dolphin kate ark gwenview okular spectacle kdeplasma-addons \
  unrar unarchiver zip unzip libarchive 7zip lrzip lzop arj cpio \
  uv fastfetch chafa python python-dbus python-gobject ttf-jetbrains-mono-nerd \
  solaar libappindicator qbittorrent \
  xdg-desktop-portal-kde xdg-user-dirs \
  kwallet-pam kwalletmanager \
  pipewire pipewire-alsa pipewire-pulse wireplumber \
  bluez bluez-utils \
  "${GPU_PACOTES[@]}" "${RISEMODE_PACOTES[@]}" plymouth \
  noto-fonts noto-fonts-emoji ttf-dejavu ttf-liberation \
  flatpak \
  zram-generator ufw plasma-firewall rebuild-detector pacman-contrib gpu-screen-recorder-ui

genfstab -U /mnt > /mnt/etc/fstab

UUID_RAIZ="$(blkid -s UUID -o value "$RAIZ")"

# ---------------- Arquivos integrados ----------------
install -d /mnt/usr/local/libexec /mnt/usr/share/plymouth/themes/callas
install -m 0755 "$CALLAS_SECURITY_TMP/callas-monitores.py" /mnt/usr/local/libexec/callas-monitores
install -m 0755 "$CALLAS_SECURITY_TMP/callas-janelas.py" /mnt/usr/local/libexec/callas-janelas
install -m 0755 "$CALLAS_SECURITY_TMP/callas-autostart.py" /mnt/usr/local/libexec/callas-autostart
install -m 0755 "$CALLAS_SECURITY_TMP/callas-aur-install.py" /mnt/usr/local/libexec/callas-aur-install
install -m 0755 "$CALLAS_SECURITY_TMP/callas-logs.py" /mnt/usr/local/libexec/callas-logs
install -m 0755 "$CALLAS_SECURITY_TMP/callas-version.py" /mnt/usr/local/libexec/callas-version
rm -f -- "$CALLAS_MONITOR_TMP" "$CALLAS_WINDOW_TMP"
install -d -m 0700 /mnt/usr/local/share/callas-os/security-stage
for security_file in "$CALLAS_SECURITY_TMP/"*; do
  [[ -f $security_file ]] || continue
  install -m 0600 "$security_file" /mnt/usr/local/share/callas-os/security-stage/
done
printf '%s\n' "$CALLAS_ASSET_REF" > /mnt/usr/local/share/callas-os/security-stage/commit
rm -rf -- "$CALLAS_SECURITY_TMP"
install -d /mnt/usr/share/icons/hicolor/256x256/apps
# Assets visuais do Callas OS ficam organizados no repositório.
# Isso reduz bastante o tamanho do instalador e evita duplicar imagens em base64.
install -d \
  /mnt/usr/share/callas-os/grub \
  /mnt/usr/share/callas-os/login \
  /mnt/usr/share/callas-os/lockscreen \
  /mnt/usr/share/wallpapers

curl -fsSL "$CALLAS_ASSET_BASE/logo/callas-plasma-icon.png" \
  -o /mnt/usr/share/plymouth/themes/callas/logo.png
install -m 0644 /mnt/usr/share/plymouth/themes/callas/logo.png \
  /mnt/usr/share/icons/hicolor/256x256/apps/callas-plasma-icon.png
install -m 0644 /mnt/usr/share/plymouth/themes/callas/logo.png \
  /mnt/usr/share/callas-os/grub/logo.png

# GRUB
curl -fsSL "$CALLAS_ASSET_BASE/grub/theme.txt" \
  -o /mnt/usr/share/callas-os/grub/theme.txt
curl -fsSL "$CALLAS_ASSET_BASE/grub/background.png" \
  -o /mnt/usr/share/callas-os/grub/background.png

# Plymouth
curl -fsSL "$CALLAS_ASSET_BASE/plymouth/callas/callas.plymouth" \
  -o /mnt/usr/share/plymouth/themes/callas/callas.plymouth
curl -fsSL "$CALLAS_ASSET_BASE/plymouth/callas/callas.script" \
  -o /mnt/usr/share/plymouth/themes/callas/callas.script
curl -fsSL "$CALLAS_ASSET_BASE/plymouth/callas/background.jpg" \
  -o /mnt/usr/share/plymouth/themes/callas/background.jpg

# A barra gráfica usa os PNGs oficiais do tema script do Plymouth.
install -m 0644 /mnt/usr/share/plymouth/themes/script/progress_box.png \
  /mnt/usr/share/plymouth/themes/callas/progress_box.png
install -m 0644 /mnt/usr/share/plymouth/themes/script/progress_bar.png \
  /mnt/usr/share/plymouth/themes/callas/progress_bar.png

# Login e tela de bloqueio
curl -fsSL "$CALLAS_ASSET_BASE/login/background.png" \
  -o /mnt/usr/share/callas-os/login/background.png
curl -fsSL "$CALLAS_ASSET_BASE/lockscreen/background.jpg" \
  -o /mnt/usr/share/callas-os/lockscreen/background.jpg

# Coleção de wallpapers de desktop do Callas OS. Artes exclusivas de boot/login não entram no seletor do KDE.
CALLAS_WALLPAPERS=(
  callas-wallpaper-02-city-neon.jpg
  callas-wallpaper-03-cosmic.jpg
  callas-wallpaper-04-cyber-shield.jpg
  callas-wallpaper-05-dark-minimal.jpg
  callas-wallpaper-06-futuristic.jpg
  callas-wallpaper-07-gamer-corridor.jpg
  callas-wallpaper-09-hardware-tech.jpg
  callas-wallpaper-12-moon-lake.jpg
  callas-wallpaper-13-mountains-crest.jpg
  callas-wallpaper-14-mountains-moon.jpg
  callas-wallpaper-15-neon-city.jpg
  callas-wallpaper-16-neon-default.jpg
  callas-wallpaper-17-neon-horizon.jpg
  callas-wallpaper-18-sanctuary.jpg
  callas-wallpaper-19-waves.jpg
)
for wallpaper in "${CALLAS_WALLPAPERS[@]}"; do
  id="CallasOS-${wallpaper%.jpg}"
  destino="/mnt/usr/share/wallpapers/$id"
  install -d "$destino/contents/images"
  curl -fsSL "$CALLAS_ASSET_BASE/wallpapers/$wallpaper" \
    -o "$destino/contents/images/1920x1080.jpg"
  cat > "$destino/metadata.json" <<EOF
{
  "KPackageStructure": "Plasma/Wallpaper",
  "KPlugin": {
    "Id": "$id",
    "Name": "Callas OS - ${wallpaper%.jpg}",
    "Description": "Wallpaper oficial do Callas OS",
    "License": "CC0-1.0"
  }
}
EOF
done

# O Breeze usa este arquivo para o fundo do SDDM.
if [[ -d /mnt/usr/share/sddm/themes/breeze ]]; then
  cat > /mnt/usr/share/sddm/themes/breeze/theme.conf.user <<'CALLAS_SDDM_BACKGROUND'
[General]
background=/usr/share/callas-os/login/background.png
CALLAS_SDDM_BACKGROUND
fi

cat > "/mnt/usr/local/libexec/put-update" <<'CALLAS_UPDATER'
#!/usr/bin/env bash
set -euo pipefail
export PATH=/usr/bin:/bin

program=/usr/local/libexec/put-update
atalho_menu=/usr/local/share/applications/io.github.Callas157.AtualizadorDoSistema.desktop
servico_check=put-update-check.service
timer_check=put-update-check.timer
agenda_dir=/var/lib/put-update/agenda
lock_atualizador=/run/put-update.lock
builder=put-aur
builder_home=/var/lib/put-update/aur
paru_conf=/etc/put-update-paru.conf
sudo_template=/etc/put-update-aur.sudoers
sudo_rule=/etc/sudoers.d/put-update
config_update_url=https://raw.githubusercontent.com/Callas157/arch-install/main/programas-callas-os/atualizador/callas-config-update.sh

erro() {
    printf 'Erro: %s\n' "$*" >&2
    exit 1
}

proxima_data() {
    local modo=$1 base=$2
    case $modo in
        apps) TZ=UTC0 date -d "$base +7 days" +%F ;;
        sistema) python - "$base" <<'MONTH'
import calendar, datetime, sys
d=datetime.date.fromisoformat(sys.argv[1]); y=d.year+(d.month==12); m=d.month%12+1
print(datetime.date(y,m,min(d.day,calendar.monthrange(y,m)[1])).isoformat())
MONTH
        ;;
        *) erro 'Agenda inválida.' ;;
    esac
}

ler_data_agenda() {
    local data
    read -r data < "$agenda_dir/$1" || erro "Não foi possível ler a agenda de $1."
    [[ $data =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || erro "Data inválida na agenda de $1."
    printf '%s\n' "$data"
}

gravar_data_agenda() {
    local temporario
    temporario=$(mktemp -- "$agenda_dir/.data.XXXXXXXX")
    printf '%s\n' "$2" > "$temporario"
    mv -fT -- "$temporario" "$agenda_dir/$1"
}

preparar_agenda() {
    local inicio modo data
    install -d -m 0700 -- "$agenda_dir"
    if [[ ! -e $agenda_dir/inicio ]]; then
        data=$(date +%F)
        gravar_data_agenda inicio "$data"
    fi
    inicio=$(ler_data_agenda inicio)
    for modo in sistema apps; do
        if [[ ! -e $agenda_dir/$modo ]]; then
            data=$(proxima_data "$modo" "$inicio")
            gravar_data_agenda "$modo" "$data"
        fi
    done
}

executar_agendado() {
    local usuario=$1 modo=$2 hoje vencimento proxima
    hoje=$(date +%F)
    vencimento=$(ler_data_agenda "$modo")

    # A data funciona como vencimento, não como uma janela de 24 horas.
    # Se o computador ficou desligado no dia previsto, a atualização roda
    # no primeiro boot/verificação seguinte.
    [[ $hoje < $vencimento ]] && return 0

    if registrar_atualizacao "$usuario" "$modo" automatico; then
        # O próximo ciclo começa no dia em que a atualização realmente terminou.
        proxima=$(proxima_data "$modo" "$hoje")
        gravar_data_agenda "$modo" "$proxima"
        [[ $modo != sistema ]] || gravar_data_agenda apps "$(proxima_data apps "$hoje")"
    else
        local codigo=$?
        if [[ $modo == apps && $codigo == 2 ]]; then
            # Expected deferral to the next General update; don't retry hourly.
            gravar_data_agenda apps "$(proxima_data apps "$hoje")"
            return 0
        fi
        return "$codigo"
    fi
}

verificar_agenda() {
    local usuario=$1 falhou=0
    executar_agendado "$usuario" sistema || return 1
    executar_agendado "$usuario" apps || falhou=1
    return "$falhou"
}

home_do_usuario() {
    local home
    home=$(getent passwd "$1" | cut -d: -f6) || erro "Usuário $1 indisponível."
    [[ -d "$home" ]] || erro "Pasta pessoal de $1 indisponível."
    printf '%s\n' "$home"
}

como_usuario() {
    local usuario=$1 home=$2
    shift 2
    runuser -u "$usuario" -- env -i PATH=/usr/bin HOME="$home" \
        USER="$usuario" LOGNAME="$usuario" LANG=C.UTF-8 "$@"
}

pasta_de_documentos() {
    local documentos
    documentos=$(xdg-user-dir DOCUMENTS 2>/dev/null) || documentos=
    if [[ "$documentos" != /* || "${documentos%/}" == "$HOME" ]]; then
        documentos="$HOME/Documentos"
        if [[ ! -d "$documentos" && -d "$HOME/Documents" ]]; then
            documentos="$HOME/Documents"
        fi
    fi
    printf '%s\n' "${documentos%/}"
}

pasta_de_logs() {
    /usr/local/libexec/callas-logs --prepare
}

etapa() {
    local nome=$1
    shift
    printf '\n==> %s\n' "$nome"
    if "$@"; then
        return 0
    else
        local codigo=$?
        printf 'Falha em %s (código %s).\n' "$nome" "$codigo" >&2
        return "$codigo"
    fi
}

atualizar_arch() {
    mountpoint -q /boot || { printf 'A partição /boot não está montada; atualização geral interrompida antes do pacman.\n' >&2; return 1; }
    local origem=$1 dbpath tentativa
    local -a dependencias=() confirmacao=(--noconfirm)
    dbpath=$(pacman-conf DBPath) || return
    for (( tentativa=0; tentativa<12; tentativa++ )); do
        [[ -e "${dbpath%/}/db.lck" ]] || break
        sleep 10
    done
    if [[ -e "${dbpath%/}/db.lck" ]]; then
        printf 'O pacman ainda está ocupado ou deixou um lock pendente.\n' >&2
        return 1
    fi

    if [[ -x /usr/bin/paru && -f "$paru_conf" ]]; then
        pacman -Qq base-devel >/dev/null 2>&1 || dependencias+=(base-devel)
        pacman -Qq git >/dev/null 2>&1 || dependencias+=(git)
    fi
    if [[ -r /etc/callas-nvidia-version ]]; then
        pacman -Syu --needed --ignore=nvidia-utils,nvidia-open-dkms,nvidia-open,nvidia-open-lts,lib32-nvidia-utils,nvidia-settings,libxnvctrl,opencl-nvidia,lib32-opencl-nvidia "${confirmacao[@]}" "${dependencias[@]}" || return

        # Antes de considerar a atualização concluída, garante que o NVIDIA
        # fixado ainda foi compilado para todos os kernels linux/linux-lts.
        local pkgbase release falhou_modulo=0
        for pkgbase in /usr/lib/modules/*/pkgbase; do
            [[ -f $pkgbase ]] || continue
            case $(<"$pkgbase") in
                linux|linux-lts) ;;
                *) continue ;;
            esac
            release=${pkgbase%/pkgbase}
            release=${release##*/}
            if ! dkms autoinstall -k "$release"; then
                printf 'DKMS falhou para o kernel instalado %s. Não reinicie antes de corrigir.\n' "$release" >&2
                falhou_modulo=1
            fi
            if ! modinfo -k "$release" nvidia >/dev/null 2>&1; then
                printf 'NVIDIA %s não está disponível para o kernel %s. Não reinicie antes de corrigir.\n'                     "$(< /etc/callas-nvidia-version)" "$release" >&2
                falhou_modulo=1
            fi
        done
        (( falhou_modulo == 0 )) || return 1
    else
        pacman -Syu --needed "${confirmacao[@]}" "${dependencias[@]}"
    fi
}

atualizar_aur() (
    local temporario codigo=0
    temporario=$(mktemp /var/tmp/callas-aur-log.XXXXXXXX)
    trap 'rm -f -- "$temporario"' EXIT
    /usr/local/libexec/callas-aur "$@" 2>&1 | tee "$temporario" || codigo=$?
    /usr/local/libexec/callas-logs --record AUR < "$temporario" || codigo=1
    exit "$codigo"
)

atualizar_discord_integrado() (
    falhar() {
        printf 'Erro: %s\n' "$*" >&2
        exit 1
    }

    case "${1:-}" in
        "") acao=atualizar ;;
        --pacman) acao=pacman ;;
        --agendado) acao=agendado ;;
        --sessao) acao=sessao ;;
        -h|--help)
            printf 'Uso: bash %s --discord [--pacman]\n' "${0##*/}"
            printf 'Atualiza somente o Discord nativo.\n'
            exit 0
            ;;
        *) falhar "Opção desconhecida: $1. Use --help." ;;
    esac
    [[ $# -le 1 ]] || falhar 'Passe apenas uma opção.'
    (( EUID != 0 )) || falhar 'Rode com seu usuário normal. O modo --pacman pede sudo quando necessário.'

    config_dir=${XDG_CONFIG_HOME:-"$HOME/.config"}
    discord_dir="$config_dir/discord"
    aviso_discord='Discord Stable nativo não encontrado no perfil. Abra o Discord pelo menu, aguarde a janela principal carregar e tente novamente.'
    [[ -d $discord_dir ]] || {
        [[ $acao == agendado ]] && { printf '%s\n' "$aviso_discord"; return 0; }
        falhar "$aviso_discord"
    }

    if ! lancador=$(command -v discord); then
        for candidato in /opt/Discord/Discord /opt/discord/Discord /usr/share/discord/Discord /usr/lib/discord/Discord; do
            [[ -x $candidato ]] && { lancador=$candidato; break; }
        done
    fi
    [[ -n ${lancador:-} ]] || falhar 'O lançador nativo discord não foi encontrado.'

    pids_discord() {
        pgrep -u "$EUID" -x 'Discord|discord' || true
    }

    estava_aberto=0
    if [[ -n $(pids_discord) ]]; then
        estava_aberto=1
        printf 'Fechando o Discord para atualizar...\n'
        kill -TERM $(pids_discord) 2>/dev/null || true
        for _ in {1..40}; do
            [[ -z $(pids_discord) ]] && break
            sleep 0.25
        done
        [[ -z $(pids_discord) ]] || falhar 'O Discord ainda está aberto.'
    fi

    reabrir() {
        (( estava_aberto )) || return 0
        printf 'Reabrindo o Discord...\n'
        if [[ $acao == agendado || $acao == sessao ]]; then
            systemd-run --user --collect --slice=app.slice --property=Type=exec \
                -- "$lancador" --start-minimized >/dev/null 2>&1 || return 1
        else
            nohup "$lancador" --start-minimized </dev/null >/dev/null 2>&1 &
        fi
    }
    trap reabrir EXIT

    if [[ $acao == pacman ]]; then
        pacman -Q discord >/dev/null || falhar 'O pacote discord não está instalado pelo pacman.'
        sudo pacman -Syu --needed discord || falhar 'Falha ao atualizar o Discord pelo pacman.'
    fi

    bootstrap=
    for candidato in "$(dirname -- "$(realpath -- "$lancador")")/updater_bootstrap" \
        /usr/share/discord/updater_bootstrap /opt/Discord/updater_bootstrap /opt/discord/updater_bootstrap; do
        [[ -x $candidato ]] && { bootstrap=$candidato; break; }
    done

    if [[ -n $bootstrap ]]; then
        printf 'Verificando atualização do Discord nativo...\n'
        timeout --kill-after=10s 10m "$bootstrap" --no-zenity \
            "$discord_dir" stable https://updates.discord.com/ >/dev/null ||
            falhar 'A atualização do Discord nativo falhou.'
    else
        printf 'Atualizador interno do Discord não encontrado; o pacote será mantido pelo pacman/AUR.\n'
    fi
)

criar_ponto_recuperacao() {
    /usr/local/libexec/callas-storage --system "$1"
}

notificar_reinicio_usuario() {
    local estado acao boot_pendente
    (( EUID != 0 )) || erro 'A notificação deve rodar na sessão do usuário.'
    estado="${XDG_STATE_HOME:-$HOME/.local/state}/callas/reinicio-pendente"
    [[ -f $estado ]] || return 0
    read -r boot_pendente < "$estado" || boot_pendente=
    if [[ $boot_pendente != "$(cat /proc/sys/kernel/random/boot_id)" ]]; then
        rm -f -- "$estado"
        return 0
    fi

    if command -v notify-send >/dev/null; then
        acao=$(notify-send -a 'Atualizador do sistema' -i system-reboot -u normal \
            -A reiniciar='Reiniciar agora' -A depois='Mais tarde' \
            'Atualização geral concluída' \
            'Sistema, AUR e aplicativos atualizados; verificações concluídas. Deseja reiniciar?' || true)
    else
        acao=
    fi
    rm -f -- "$estado"
    if [[ $acao == reiniciar ]]; then
        systemctl --quiet reboot --check-inhibitors=no --no-wall
    fi
}

marcar_reinicio_pendente() {
    local usuario=$1 home=$2 uid runtime estado grupo
    uid=$(id -u "$usuario") || return 1
    grupo=$(id -gn "$usuario") || return 1
    estado="$home/.local/state/callas"
    como_usuario "$usuario" "$home" /usr/bin/bash -c '
      umask 077
      mkdir -p -- "$1"
      cat /proc/sys/kernel/random/boot_id > "$1/reinicio-pendente"
    ' bash "$estado"

    runtime="/run/user/$uid"
    if [[ -S "$runtime/bus" ]]; then
        runuser -u "$usuario" -- env \
            HOME="$home" USER="$usuario" LOGNAME="$usuario" \
            XDG_RUNTIME_DIR="$runtime" DBUS_SESSION_BUS_ADDRESS="unix:path=$runtime/bus" \
            systemd-run --user --collect --unit=callas-update-reinicio \
            "$program" --notificar-reinicio >/dev/null 2>&1 || :
    fi
}

notificar_apps_usuario() {
    local usuario=$1 home=$2 uid runtime titulo='Aplicativos atualizados' mensagem='Os aplicativos foram atualizados com sucesso.'
    if [[ ${3:-apps} == flatpaks ]]; then
        titulo='Flatpaks atualizados'
        mensagem='Os Flatpaks foram atualizados com sucesso.'
    fi
    uid=$(id -u "$usuario") || return 1
    runtime="/run/user/$uid"
    [[ -S "$runtime/bus" ]] || return 0
    runuser -u "$usuario" -- env \
        HOME="$home" USER="$usuario" LOGNAME="$usuario" \
        XDG_RUNTIME_DIR="$runtime" DBUS_SESSION_BUS_ADDRESS="unix:path=$runtime/bus" \
        notify-send -a 'Atualizador do sistema' -i system-software-update \
        "$titulo" \
        "$mensagem" >/dev/null 2>&1 || :
}

atualizar_sistema() {
    local origem=$1 usuario=$2 home=$3 falhou=0
    etapa 'Ponto de recuperação pré-update' criar_ponto_recuperacao "$usuario" || return
    etapa 'Arch e aplicativos dos repositórios' atualizar_arch "$origem" || return
    etapa 'AUR e recompilações necessárias' atualizar_aur || falhou=1
    etapa 'Flatpaks e Discord' atualizar_apps "$usuario" "$home" || falhou=1
    # Always validate boot at the end, even if an application failed earlier.
    etapa 'Kernels padrão/LTS, DKMS e boot' /usr/local/libexec/callas-kernel-check || falhou=1
    return "$falhou"
}

atualizar_flatpaks() {
    local usuario=$1 home=$2 falhou=0

    if [[ -x /usr/bin/flatpak ]]; then
        etapa 'Flatpaks do sistema' flatpak update --system --noninteractive --assumeyes || falhou=1
        etapa "Flatpaks de $usuario" como_usuario "$usuario" "$home" \
            /usr/bin/dbus-run-session -- /usr/bin/flatpak update --user --noninteractive --assumeyes ||
            falhou=1
    else
        printf 'Flatpak ausente.\n'
    fi

    return "$falhou"
}

atualizar_apps() {
    local usuario=$1 home=$2 falhou=0
    atualizar_flatpaks "$usuario" "$home" || falhou=1
    etapa 'Discord nativo' como_usuario "$usuario" "$home" "$program" --discord-agendado ||
        falhou=1
    return "$falhou"
}

atualizar_nativos() {
    mountpoint -q /boot || { printf 'A partição /boot não está montada; manutenção de pacotes interrompida.\n' >&2; return 1; }
    local usuario=$1 home=$2 falhou=0 adiados=0 codigo
    etapa 'Backup de configurações' criar_ponto_recuperacao "$usuario" || return
    /usr/local/libexec/callas-native || {
        codigo=$?
        if (( codigo == 2 )); then adiados=1; else falhou=1; fi
    }
    etapa 'Aplicativos do AUR sem alterar a base' atualizar_aur --apps-only || {
        codigo=$?
        if (( codigo == 2 )); then adiados=1; else falhou=1; fi
    }
    etapa 'Discord nativo' como_usuario "$usuario" "$home" "$program" --discord-agendado || falhou=1
    (( falhou == 0 )) || return 1
    (( adiados == 0 )) || return 2
}

registrar_atualizacao() {
    local usuario=$1 modo=$2 origem=$3 home codigo=0 categoria
    case $modo in
      sistema) categoria='Sistema e Pacman' ;;
      *) categoria='Aplicativos' ;;
    esac
    home=$(home_do_usuario "$usuario")
    if {
        printf '\n===== Atualização (%s, %s) | %s =====\n' "$modo" "$origem" "$(date -Is)"
        case $modo in
            sistema) atualizar_sistema "$origem" "$usuario" "$home" || codigo=$? ;;
            apps|nativos) atualizar_nativos "$usuario" "$home" || codigo=$? ;;
            flatpaks) atualizar_flatpaks "$usuario" "$home" || codigo=$? ;;
            discord)
                etapa 'Discord nativo' como_usuario "$usuario" "$home" \
                    "$program" --discord-sessao || codigo=$?
                ;;
        esac
        printf '===== Fim da atualização | %s | código %s =====\n' "$(date -Is)" "$codigo"
        exit "$codigo"
    } 2>&1 | como_usuario "$usuario" "$home" "$program" --log "$categoria"; then
        if [[ $modo == sistema ]]; then
            local proxima
            proxima=$(proxima_data sistema "$(date +%F)") || return
            gravar_data_agenda sistema "$proxima" || return
            printf '%s\n' "$(date +%F)" > "$agenda_dir/ultima-sistema"
            gravar_data_agenda apps "$(proxima_data apps "$(date +%F)")" || return
            marcar_reinicio_pendente "$usuario" "$home" ||
                printf 'Aviso: não consegui mostrar a opção de reiniciar.\n' >&2
        elif [[ $modo == apps || $modo == nativos || $modo == flatpaks ]]; then
            [[ $modo == flatpaks ]] || gravar_data_agenda apps "$(proxima_data apps "$(date +%F)")" || return
            notificar_apps_usuario "$usuario" "$home" "$modo" || :
        fi
    else
        codigo=$?
        if (( codigo == 2 )); then
            printf 'Alguns aplicativos aguardam a opção 4 — Atualizar geral. Nenhum kernel foi atualizado pelo modo nativo.\n'
            notificar_adiamento_usuario "$usuario" "$home" || :
        else
            printf 'Atualização incompleta (código %s). Consulte os logs; reinício não solicitado.\n' "$codigo" >&2
            notificar_falha_usuario "$usuario" "$home" || :
        fi
        return "$codigo"
    fi
}

notificar_adiamento_usuario() {
    local usuario=$1 home=$2 uid runtime
    uid=$(id -u "$usuario") || return
    runtime="/run/user/$uid"
    [[ -S $runtime/bus ]] || return 0
    runuser -u "$usuario" -- env -i PATH=/usr/bin HOME="$home" USER="$usuario" \
      XDG_RUNTIME_DIR="$runtime" DBUS_SESSION_BUS_ADDRESS="unix:path=$runtime/bus" \
      notify-send -a 'Atualizador do sistema' 'Alguns aplicativos aguardam atualização geral' \
      'A opção 2 preservou kernel e base. Use a opção 4 para concluir as atualizações pendentes.'
}

notificar_falha_usuario() {
    local usuario=$1 home=$2 uid runtime
    uid=$(id -u "$usuario") || return
    runtime="/run/user/$uid"
    [[ -S $runtime/bus ]] || return 0
    runuser -u "$usuario" -- env -i PATH=/usr/bin HOME="$home" USER="$usuario" \
        XDG_RUNTIME_DIR="$runtime" DBUS_SESSION_BUS_ADDRESS="unix:path=$runtime/bus" \
        notify-send -u critical -a 'Atualizador do sistema' 'Atualização incompleta' \
        'Uma etapa falhou. Consulte Documentos/Callas OS/Callas OS Logs antes de reiniciar.'
}

instalar_atalhos() {
    local documentos
    documentos=$(pasta_de_documentos)
    mkdir -p -- "$documentos"
    install -m 0755 -T -- "$program" "$documentos/atualizador-do-sistema.sh"
    install -m 0755 -T -- "$atalho_menu" "$documentos/Atualizador do sistema.desktop"
    printf 'Atalho criado em %s/Atualizador do sistema.desktop\n' "$documentos"
}

instalar_entrada_menu() {
    local arquivo=$1
    cat > "$arquivo" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Atualizador do sistema
Comment=Atualizações automáticas e manuais do Arch, Flatpak e Discord
Exec=$program --menu
TryExec=$program
Icon=system-software-update
Terminal=true
Categories=System;
Keywords=atualizador;atualização;Arch;pacman;Flatpak;Discord;
DESKTOP
    install -D -m 0644 -T -- "$arquivo" "$atalho_menu"
    printf 'Atualizador do sistema disponível no menu de aplicativos.\n'
}

desativar_agendamento_antigo() {
    local em_chroot=$1 unidade estado
    local -a antigas=(
        put-update.timer put-update-sistema.timer put-update-apps.timer put-update-check.timer
    )

    if (( em_chroot )); then
        for unidade in "${antigas[@]}"; do
            systemctl --root=/ disable "$unidade" 2>/dev/null || :
        done
    else
        for unidade in "${antigas[@]}"; do
            estado=$(systemctl show -p LoadState --value "$unidade" 2>/dev/null || :)
            [[ $estado == not-found || -z $estado ]] || systemctl disable --now "$unidade" 2>/dev/null || :
        done
    fi

    rm -f -- \
        /etc/systemd/system/put-update.timer \
        /etc/systemd/system/put-update.service \
        /etc/systemd/system/put-update-sistema.timer \
        /etc/systemd/system/put-update-apps.timer \
        /etc/systemd/system/put-update@.service \
        /etc/systemd/system/put-update-check.timer \
        /etc/systemd/system/put-update-check.service
}

instalar() {
    local usuario=$1 origem temporario conta home modo timer hora pasta em_chroot=0
    [[ "$usuario" =~ ^[a-zA-Z_][a-zA-Z0-9_.-]*$ && "$usuario" != root ]] ||
        erro 'Informe um usuário normal do Arch.'
    [[ -f /etc/arch-release ]] || erro 'Este script requer Arch Linux.'
    if systemd-detect-virt --chroot; then
        em_chroot=1
    elif [[ ! -d /run/systemd/system ]]; then
        erro 'Este script requer o systemd em execução ou o arch-chroot do sistema de destino.'
    fi
    home=$(home_do_usuario "$usuario")
    origem=$(realpath -- "${BASH_SOURCE[0]}")
    exec 8>"$lock_atualizador"
    [[ ${CALLAS_UPDATE_LOCK_HELD:-0} == 1 ]] || flock -x 8
    temporario=$(mktemp -d)
    trap "rm -rf -- $(printf '%q' "$temporario")" EXIT

    cat > "$temporario/$servico_check" <<UNIT
[Unit]
Description=Verificar agenda de atualização do Callas OS
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
ExecStart=$program --check $usuario
StandardOutput=journal
StandardError=journal
UNIT

    cat > "$temporario/$timer_check" <<UNIT
[Unit]
Description=Verificar a agenda de atualização ao longo do dia

[Timer]
OnBootSec=2min
OnUnitInactiveSec=1h
AccuracySec=1min
Unit=$servico_check

[Install]
WantedBy=timers.target
UNIT

    desativar_agendamento_antigo "$em_chroot"
    rm -f -- "$sudo_rule"

    rm -f -- "$sudo_rule" "$sudo_template" "$paru_conf"
    # AUR builds use the isolated helper; no passwordless pacman rule is installed.

    preparar_agenda
    if [[ ! -f $agenda_dir/maintenance-monthly-v2 ]]; then
        base_agenda=$(ler_data_agenda inicio)
        [[ ! -r $agenda_dir/ultima-sistema ]] || read -r base_agenda < "$agenda_dir/ultima-sistema"
        gravar_data_agenda sistema "$(proxima_data sistema "$base_agenda")"
        touch "$agenda_dir/maintenance-monthly-v2"
    fi
    # O programa pode já ser a origem quando o automático é reconfigurado pelo atalho.
    if [[ $origem != "$program" ]]; then
        install -D -m 0755 -T -- "$origem" "$program"
    fi
    install -m 0644 -- "$temporario/$servico_check" "$temporario/$timer_check" /etc/systemd/system/
    instalar_entrada_menu "$temporario/${atalho_menu##*/}"

    como_usuario "$usuario" "$home" mkdir -p "$home/.config/autostart"
    como_usuario "$usuario" "$home" tee "$home/.config/autostart/callas-update-reinicio.desktop" >/dev/null <<'REBOOT_DESKTOP'
[Desktop Entry]
Type=Application
Name=Notificação de reinício do Callas OS
Exec=/usr/local/libexec/put-update --notificar-reinicio
OnlyShowIn=KDE;
NoDisplay=true
StartupNotify=false
X-KDE-AutostartScript=true
REBOOT_DESKTOP

    if (( em_chroot )); then
        systemctl --root=/ enable "$timer_check"
    else
        systemctl daemon-reload
        systemctl enable "$timer_check"
        systemctl restart "$timer_check"
    fi

    printf '\nAgendamento automático configurado.\n'
    printf 'Atualização mensal do sistema vence em: %s.\n' "$(ler_data_agenda sistema)"
    printf 'Atualização semanal dos aplicativos vence em: %s.\n' "$(ler_data_agenda apps)"
    printf 'Se o PC estiver desligado no vencimento, a atualização roda no primeiro boot/verificação seguinte.\n'
    como_usuario "$usuario" "$home" "$program" --instalar-atalhos
    if pasta=$(como_usuario "$usuario" "$home" "$program" --log-dir); then
        printf 'Logs por categoria em Documentos: %s\n' "$pasta"
    else
        printf 'Não foi possível criar a pasta de logs em Documentos.\n' >&2
    fi
}

perguntar_reinicio() {
    # O callas-config-update.sh pergunta Y/N imediatamente ao concluir.
    return 0
}

atualizar_config_callas() {
    # Root creates/downloads the stage; never sudo-execute a user-owned script.
    printf 'É necessária autorização administrativa para aplicar as configurações.\n'
    sudo /usr/local/libexec/callas-release
}

menu_manutencao() {
    local escolha
    while true; do
        printf '\n=== Limpeza e manutenção ===\n'
        printf '%s\n' '1. Limpeza segura agora' '2. Ver espaço, backups e arquivos de VMs' \
            '3. Verificar pacotes órfãos' '4. Reparar agendamento automático' '5. Voltar'
        read -r -p 'Escolha [1-5]: ' escolha || return 0
        [[ $escolha == 5 || -z $escolha ]] || printf 'É necessária autorização administrativa para esta ação.\n'
        case $escolha in
          1) sudo /usr/local/libexec/callas-maintenance --clean "$USER" || printf 'A limpeza registrou uma falha; consulte os logs.\n' ;;
          2) sudo /usr/local/libexec/callas-maintenance --report "$USER" || printf 'Não consegui concluir o relatório.\n' ;;
          3) sudo /usr/local/libexec/callas-maintenance --orphans "$USER" || printf 'Não consegui concluir a verificação de órfãos.\n' ;;
          4) sudo "$program" --instalar || printf 'Falha ao reparar o agendamento.\n' ;;
          5|"") return 0 ;;
          *) printf 'Opção inválida.\n' ;;
        esac
    done
}

menu() {
    local origem opcao modo
    origem=$(realpath -- "${BASH_SOURCE[0]}")
    if [[ ! -t 0 ]]; then
        command -v konsole >/dev/null || erro 'Abra o arquivo com bash em um terminal.'
        exec konsole -e /usr/bin/bash "$origem" --menu
    fi
    while true; do
        printf '\n=== Atualizador do sistema ===\n'
        if [[ -x /usr/local/libexec/callas-version ]]; then
            /usr/local/libexec/callas-version --label || :
        fi
        printf '%s\n' \
            '1. Limpeza e manutenção' \
            '2. Atualizar aplicativos nativos' \
            '3. Atualizar Discord' \
            '4. Atualizar geral' \
            '5. Callas OS Update' \
            '6. Sair'
        read -r -p 'Escolha [1-6] ou digite reboot: ' opcao || return 0
        case $opcao in
            1)
                menu_manutencao
                continue
                ;;
            2) modo=nativos ;;
            3) modo=discord ;;
            4) modo=sistema ;;
            5)
                if atualizar_config_callas; then
                    perguntar_reinicio
                else
                    printf 'Falha ao atualizar as configurações do Callas OS.\n' >&2
                fi
                continue
                ;;
            6) return 0 ;;
            reboot|REBOOT|Reboot)
                systemctl --quiet reboot --check-inhibitors=no --no-wall
                return 0
                ;;
            *) printf 'Opção inválida. Digite 1-6 ou reboot.\n'; continue ;;
        esac

        if [[ $origem != "$program" ]] && ! cmp -s -- "$origem" "$program"; then
            printf 'Este arquivo difere do atualizador instalado. Use a opção 5 — Callas OS Update para migrar a versão instalada.\n'
            continue
        fi
        printf 'É necessária autorização administrativa para iniciar. Não serão pedidas senhas no meio da atualização.\n'
        if sudo "$program" --manual "$modo"; then
            : # The transaction itself offers reboot after every phase succeeds.
        else
            codigo_menu=$?
            if (( codigo_menu == 2 )); then
                printf 'Parte dos aplicativos aguarda Atualizar geral; os detalhes estão no log.\n'
            else
                printf 'Atualização com falha. Confira a mensagem acima e o log em Documentos.\n' >&2
            fi
        fi
    done
}

case ${1:-} in
    --discord-boot|--discord-agendado)
        (( EUID != 0 && $# == 1 )) || erro 'Esta opção é usada pelo serviço de atualização.'
        atualizar_discord_integrado --agendado
        ;;
    --discord-sessao)
        (( EUID != 0 && $# == 1 )) || erro 'Esta opção é usada pelo menu de atualização.'
        atualizar_discord_integrado --sessao
        ;;
    --discord)
        shift
        case ${1:-} in
            --boot|--agendado|--sessao) erro 'Use --discord para atualização manual.' ;;
        esac
        atualizar_discord_integrado "$@"
        ;;
    --check)
        (( EUID == 0 && $# == 2 )) || erro 'Esta opção é usada pelo serviço de atualização.'
        exec flock -x -o "$lock_atualizador" "$program" --verificar-agenda "$2"
        ;;
    --verificar-agenda)
        (( EUID == 0 && $# == 2 )) || erro 'Esta opção é interna.'
        rm -f -- "$sudo_rule"
        verificar_agenda "$2"
        ;;
    --manual)
        (( EUID == 0 && $# == 2 )) || erro 'Esta opção é usada pelo menu de atualização.'
        [[ -n ${SUDO_USER:-} && $SUDO_USER != root ]] || erro 'Abra o menu com seu usuário normal.'
        [[ $2 == sistema || $2 == apps || $2 == nativos || $2 == flatpaks || $2 == discord ]] || erro 'Modo manual inválido.'
        printf 'Preparando a atualização. Se outra estiver em andamento, ela vai terminar primeiro.\n'
        exec flock -x -o "$lock_atualizador" "$program" --registrar "$SUDO_USER" "$2" manual
        ;;
    --registrar)
        (( EUID == 0 && $# == 4 )) || erro 'Esta opção é interna.'
        rm -f -- "$sudo_rule"
        if [[ $4 == automatico ]]; then
            executar_agendado "$2" "$3"
        else
            registrar_atualizacao "$2" "$3" "$4"
        fi
        ;;
    --notificar-reinicio)
        (( EUID != 0 && $# == 1 )) || erro 'Esta opção é usada pela sessão gráfica do usuário.'
        notificar_reinicio_usuario
        ;;
    --instalar)
        (( EUID == 0 && $# == 1 )) || erro 'Escolha a opção 1 no menu para instalar.'
        instalar "${SUDO_USER:-}"
        ;;
    --instalar-para)
        (( EUID == 0 && $# == 2 )) || erro 'Use como root: bash atualizador-do-sistema.sh --instalar-para USUARIO.'
        instalar "$2"
        ;;
    --instalar-atalhos)
        (( EUID != 0 && $# == 1 )) || erro 'Esta opção é interna.'
        instalar_atalhos
        ;;
    --log-dir)
        (( EUID != 0 && $# == 1 )) || erro 'Use esta opção como usuário normal.'
        pasta_de_logs
        ;;
    --log)
        (( EUID != 0 && $# == 2 )) || erro 'Use esta opção como usuário normal.'
        /usr/bin/tee /dev/stderr | /usr/local/libexec/callas-logs --write "$2"
        ;;
    ''|--menu)
        (( EUID != 0 && $# <= 1 )) || erro 'Abra o atualizador com seu usuário normal, sem sudo.'
        menu
        ;;
    *) erro 'Use bash atualizador-do-sistema.sh para abrir o menu.' ;;
esac
CALLAS_UPDATER
cat > "/mnt/usr/local/libexec/callas-inicio-kde" <<'CALLAS_KDE_START'
#!/usr/bin/env bash
set -euo pipefail

if (( EUID == 0 )); then
    printf '%s\n' 'Rode este arquivo no Konsole com seu usuário normal. Ele pede sudo só para corrigir o atualizador.' >&2
    exit 1
fi

# Only the clean installer arms the one-time autostart suppression. Repairs and
# existing-system migrations never create/reset these markers.
case ${1:-} in
    '') export CALLAS_PREPARE_FIRST_LOGIN=0 ;;
    --preparar-primeiro-login) export CALLAS_PREPARE_FIRST_LOGIN=1 ;;
    *) printf 'Argumento inválido.\n' >&2; exit 1 ;;
esac
(( $# <= 1 )) || exit 1

for programa in kwriteconfig6 kreadconfig6 python3; do
    if ! command -v "$programa" >/dev/null; then
        printf 'Comando necessário ausente: %s\n' "$programa" >&2
        exit 1
    fi
done

# O KDE passa a iniciar uma sessão vazia, com o autostart funcionando normalmente.
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
if [[ $XDG_CONFIG_HOME != /* ]]; then
    printf '%s\n' 'XDG_CONFIG_HOME precisa ser um caminho absoluto.' >&2
    exit 1
fi

python3 - <<'PY'
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

home = Path.home()
config = Path(os.environ["XDG_CONFIG_HOME"])
auto = config / "autostart"
auto.mkdir(parents=True, exist_ok=True)
backup = Path(tempfile.mkdtemp(prefix="callas-inicio-backup-", dir=config))
avisos = []

def guardar(path):
    if path.is_file():
        destino = backup / path.relative_to(config)
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destino)

def gravar(path, texto, modo=0o644):
    if not path.is_symlink() and path.is_file() and path.read_text(encoding="utf-8", errors="replace") == texto:
        return
    guardar(path)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as temp:
        try:
            temp.write(texto)
            temp.close()
            os.chmod(temp.name, modo)
            os.replace(temp.name, path)
        finally:
            Path(temp.name).unlink(missing_ok=True)

def chamar(*args):
    return subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False).returncode == 0

def dados(path):
    campos = {}
    ativo = False
    for linha in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if linha.startswith("["):
            ativo = linha == "[Desktop Entry]"
        elif ativo and "=" in linha and not linha.startswith("#"):
            chave, valor = linha.split("=", 1)
            campos[chave] = valor
    return campos

def aplicativo(nome, campos):
    texto = " ".join([nome, campos.get("Name", ""), campos.get("Exec", "")]).lower()
    for app, padrao in (
        ("vibrance", r"vibran[ct]|digital[ _.-]*vibrance"),
        ("discord", r"(?<![\w-])discord(?![\w-])|com\.discordapp\.discord"),
        ("steam", r"(?<![\w-])steam(?![\w-])|com\.valvesoftware\.steam"),
        ("solaar", r"solaar"),
        ("gsr", r"gpu[ ._-]*screen[ ._-]*recorder|gsr-ui"),
        ("extra", r"spotify|brave(?:-browser|-bin)?"),
    ):
        if re.search(padrao, texto):
            return app
    return ""

def desktop(nome, comando, icone=""):
    return (
        f"[Desktop Entry]\nType=Application\nName={nome}\nExec={comando}\n"
        f"StartupNotify=false\nOnlyShowIn=KDE;\n"
        + (f"Icon={icone}\n" if icone else "")
    )

def argumento(valor):
    # Exec usa dois níveis de escape. Percentuais são códigos de campo.
    valor = str(valor).replace("%", "%%")
    if re.fullmatch(r"[a-zA-Z0-9_./@:=+-]+", valor):
        return valor
    valor = re.sub(r'(["`$\\])', r'\\\1', valor)
    return '"' + valor.replace("\\", "\\\\") + '"'

def launcher(*args):
    return " ".join(map(argumento, args))

def flatpak(app):
    return bool(shutil.which("flatpak")) and chamar("flatpak", "info", app)

# Os arquivos do usuário têm precedência sobre os equivalentes do sistema.
locais = {p.name: p for p in sorted(auto.glob("*.desktop")) if p.is_file()}
globais = {}
for pasta in (os.environ.get("XDG_CONFIG_DIRS") or "/etc/xdg").split(":"):
    if Path(pasta).is_absolute():
        for path in sorted((Path(pasta) / "autostart").glob("*.desktop")):
            if path.is_file():
                globais.setdefault(path.name, path)

entradas = {nome: (path, dados(path)) for nome, path in (globais | locais).items()}
tipos = {nome: aplicativo(nome, campos) for nome, (_, campos) in entradas.items()}
planos = {}

discord = shutil.which("discord")
if not discord:
    discord = next((p for p in ("/opt/Discord/Discord", "/opt/discord/Discord") if os.access(p, os.X_OK)), None)
if discord:
    planos["discord"] = ("callas-discord.desktop", desktop("Discord", launcher("/usr/local/libexec/callas-autostart", "discord", discord), "discord"))
    perfil = config / "discord"
    if not perfil.exists():
        perfil.mkdir(mode=0o700)
    if perfil.is_dir():
        try:
            arquivo = perfil / "settings.json"
            ajustes = json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.exists() else {}
            if not isinstance(ajustes, dict):
                raise ValueError("settings.json não contém um objeto")
            novos = dict(ajustes, OPEN_ON_STARTUP=False)
            if novos != ajustes:
                gravar(arquivo, json.dumps(novos, indent=2, ensure_ascii=False) + "\n", 0o600)
        except (OSError, ValueError) as erro:
            avisos.append(f"Discord: não consegui ajustar a preferência da bandeja ({erro}).")
else:
    avisos.append("Discord nativo não encontrado. Mantive as entradas dele.")

steam = shutil.which("steam")
if steam:
    planos["steam"] = ("steam.desktop", desktop("Steam", launcher("/usr/local/libexec/callas-autostart", "steam", steam, "-silent"), "steam"))
else:
    avisos.append("Steam nativa não encontrada. Mantive as entradas dela.")

solaar_id = "io.github.pwr_solaar.solaar"
solaar = shutil.which("solaar")
if solaar:
    comando_solaar = launcher("/usr/bin/env", "GTK_THEME=Adwaita:dark", solaar, "--window=hide")
elif flatpak(solaar_id):
    comando_solaar = launcher("flatpak", "run", solaar_id, "--window=hide")
else:
    comando_solaar = ""
if comando_solaar:
    planos["solaar"] = ("solaar.desktop", desktop("Solaar", comando_solaar, "solaar"))
else:
    avisos.append("Solaar não encontrado. Mantive as entradas dele.")

gsr_id = "com.dec05eba.gpu_screen_recorder"
gsr = shutil.which("gsr-ui")
if gsr:
    comando_gsr = launcher(gsr, "launch-daemon")
elif flatpak(gsr_id):
    comando_gsr = launcher("flatpak", "run", gsr_id, "gsr-ui")
else:
    comando_gsr = ""
if comando_gsr:
    gsr_service = "gpu-screen-recorder-ui.service"
    if chamar("systemctl", "--user", "is-enabled", "--quiet", gsr_service) and not chamar(
        "systemctl", "--user", "disable", gsr_service
    ):
        avisos.append("GPU Screen Recorder: o serviço de usuário já inicia o overlay. Mantive esse serviço.")
        planos["gsr"] = (None, None)
    else:
        planos["gsr"] = ("gpu-screen-recorder-ui.desktop", desktop("GPU Screen Recorder", comando_gsr, gsr_id))
else:
    avisos.append("Overlay do GPU Screen Recorder não encontrado. Mantive as entradas dele.")

vibrance_ativo = any(
    tipos[nome] == "vibrance"
    and campos.get("Hidden", "").lower() != "true"
    and campos.get("X-GNOME-Autostart-enabled", "").lower() != "false"
    and bool(campos.get("Exec"))
    for nome, (_, campos) in entradas.items()
)
if not vibrance_ativo:
    script = home / ".local/bin/DigitalVibrance.sh"
    if script.is_file():
        planos["vibrance"] = ("digital-vibrance.desktop", desktop("Digital Vibrance", launcher("/usr/bin/bash", script)))
    else:
        avisos.append("Digital Vibrance: não localizei a entrada pelo nome. Os scripts do KDE foram preservados.")

sessao = config / "ksmserverrc"
login_args = ("--file", str(sessao), "--group", "General", "--key", "loginMode")
if subprocess.check_output(("kreadconfig6", *login_args), text=True).strip() != "emptySession":
    guardar(sessao)
    subprocess.run(("kwriteconfig6", *login_args, "emptySession"), check=True)
    if subprocess.check_output(("kreadconfig6", *login_args), text=True).strip() != "emptySession":
        raise SystemExit("O KDE não gravou a configuração de sessão vazia.")

destinos = {nome for nome, _ in planos.values() if nome is not None}
for nome, (_, campos) in entradas.items():
    if nome in destinos:
        continue
    app = tipos[nome]
    # Preserva scripts auxiliares do KDE, como os ajustes de monitor e de cores.
    if app == "extra" or app in planos:
        if campos.get("Hidden", "").lower() == "true":
            continue
        gravar(auto / nome, "[Desktop Entry]\nType=Application\nHidden=true\n")
        print(f"Entrada desativada: {nome}")

for nome, conteudo in planos.values():
    if nome is not None:
        gravar(auto / nome, conteudo)

if os.environ.get("CALLAS_PREPARE_FIRST_LOGIN") == "1":
    state = Path(os.environ.get("XDG_STATE_HOME", str(home / ".local/state")))
    if not state.is_absolute(): raise SystemExit("XDG_STATE_HOME precisa ser absoluto")
    state = state / "callas-os"
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    for app in ("steam", "discord"):
        if app in planos:
            marker = state / ("first-login-" + app + ".pending")
            marker.touch(mode=0o600, exist_ok=True)
    print("Primeiro login: Steam e Discord aguardam abertura manual; autostart normal nos próximos logins.")

if any(backup.iterdir()):
    print(f"Backup das configurações: {backup}")
else:
    backup.rmdir()
for aviso in avisos:
    print(f"Aviso: {aviso}")
print("Sessão vazia configurada para o próximo login no KDE.")
PY
CALLAS_KDE_START

cat > "/mnt/usr/local/libexec/callas-limpar-atalhos-desktop" <<'CALLAS_DESKTOP_CLEAN'
#!/usr/bin/env bash
set -u

desktop=$(xdg-user-dir DESKTOP 2>/dev/null || true)
[[ $desktop == /* ]] || desktop="$HOME/Desktop"

# Alguns aplicativos podem recriar lançadores na Área de Trabalho após o login.
# Remove somente esses atalhos da Área de Trabalho; as entradas do menu KDE
# em ~/.local/share/applications ou /usr/share/applications são preservadas.
for _ in {1..6}; do
    if [[ -d $desktop ]]; then
        find "$desktop" -maxdepth 1 -type f \( \
            -iname '*ixin*.desktop' -o \
            -iname '*ixlauncher*.desktop' -o \
            -iname 'steam.desktop' -o \
            -iname 'com.valvesoftware.Steam.desktop' \
        \) -delete 2>/dev/null || true
    fi
    sleep 10
done
CALLAS_DESKTOP_CLEAN
chmod 0755 /mnt/usr/local/libexec/callas-limpar-atalhos-desktop

cat > "/mnt/etc/xdg/autostart/callas-limpar-atalhos-desktop.desktop" <<'CALLAS_DESKTOP_AUTOSTART'
[Desktop Entry]
Type=Application
Name=Limpar atalhos automáticos da área de trabalho
Exec=/usr/local/libexec/callas-limpar-atalhos-desktop
OnlyShowIn=KDE;
NoDisplay=true
StartupNotify=false
CALLAS_DESKTOP_AUTOSTART

cat > "/mnt/usr/local/libexec/callas-kde-desligamento-login" <<'CALLAS_KDE_LOGIN'
#!/usr/bin/env bash
# Arch Linux e Plasma Wayland, com Plasma Login Manager ou SDDM.
set -euo pipefail

erro() { printf 'Erro: %s\n' "$*" >&2; exit 1; }

# Esta função também é instalada como a ação do hook do pacman.
ajustar_contagem() {
    local acao=$1 arquivo quantidade reconhecidos=0 falhas=0
    local inicio='^([[:blank:]]*(readonly[[:blank:]]+)?property[[:blank:]]+(real|int)[[:blank:]]+timeout[[:blank:]]*:[[:blank:]]*)'
    local fim='([[:blank:]]*;?[[:blank:]]*(//.*)?)$'
    local original="${inicio}30${fim}"
    local valor='(sdtype === ShutdownType.ShutdownTypeHalt || sdtype === ShutdownType.ShutdownTypeReboot) ? 5 : 30 /* Callas KDE */'
    local nosso="${inicio}.* /\\* Callas KDE \\*/${fim}"
    for arquivo in \
        /usr/share/plasma/shells/org.kde.plasma.desktop/contents/logout/Logout.qml \
        /usr/share/plasma/shells/org.kde.plasma.desktop/contents/logout/LogoutControls.qml \
        /usr/share/plasma/look-and-feel/org.kde.breeze.desktop/contents/logout/Logout.qml; do
        [[ -f $arquivo && ! -L $arquivo ]] || continue
        if [[ $acao == desfazer ]]; then
            if grep -Eq "$nosso" "$arquivo"; then
                sed -Ei "s@${nosso}@\\130\\4@" "$arquivo" || falhas=1
            fi
            continue
        fi
        quantidade=$(grep -Ec "$original" "$arquivo") || :
        if [[ $quantidade == 1 ]] && grep -wq 'sdtype' "$arquivo" &&
            grep -Fq 'ShutdownType.ShutdownTypeHalt' "$arquivo" &&
            grep -Fq 'ShutdownType.ShutdownTypeReboot' "$arquivo"; then
            if sed -Ei "s@${original}@\\1${valor}\\4@" "$arquivo"; then
                reconhecidos=$((reconhecidos + 1))
            else
                falhas=1
            fi
        elif grep -Eq "${inicio}5${fim}" "$arquivo" || grep -Eq "$nosso" "$arquivo"; then
            reconhecidos=$((reconhecidos + 1))
        fi
    done
    if [[ $acao == aplicar && $reconhecidos == 0 ]]; then
        printf 'Callas KDE: formato da contagem não reconhecido no Plasma instalado.\n' >&2
        return 1
    fi
    return "$falhas"
}

como_login() { /usr/bin/runuser -u "$usuario_login" -- "$@"; }

localizar_config_login() {
    local conta pasta_login uid
    case $usuario_login in
        plasmalogin|sddm) ;;
        *) erro 'conta de login inválida no backup.' ;;
    esac
    conta=$(/usr/bin/getent passwd "$usuario_login") || erro "conta $usuario_login não encontrada."
    IFS=: read -r _ _ uid _ _ pasta_login _ <<< "$conta"
    [[ $uid =~ ^[1-9][0-9]*$ && $pasta_login == "/var/lib/$usuario_login" ]] ||
        erro "pasta ou conta de sistema inesperada para $usuario_login."
    destino=$pasta_login/.config/kwinoutputconfig.json
}

ler_sddm() {
    local arquivo
    for arquivo in /usr/lib/sddm/sddm.conf.d/*.conf /etc/sddm.conf.d/*.conf /etc/sddm.conf; do
        [[ -f $arquivo ]] || continue
        printf '\n[General]\n'
        cat -- "$arquivo"
    done | awk -v secao="$1" -v chave="$2" -v valor="$3" '
        /^[[:space:]]*[#;]/ { next }
        { sub(/^[[:space:]]+/, ""); sub(/[[:space:]]+$/, "") }
        /^\[/ { grupo = $0; next }
        grupo == "[" secao "]" && $0 ~ ("^" chave "[[:space:]]*=") {
            sub(/^[^=]*=[[:space:]]*/, "")
            sub(/^"/, "")
            sub(/"$/, "")
            valor = $0
        }
        END { print valor }
    '
}

configurar_sddm_x11() {
    local principal=$1 caminho edid='' encontrado anterior
    [[ -x /usr/bin/xrandr ]] || erro 'SDDM em X11 precisa do pacote xorg-xrandr. Instale com sudo pacman -S --needed xorg-xrandr.'
    for caminho in /sys/class/drm/card*-"$principal"/edid; do
        [[ -r $caminho ]] || continue
        encontrado=$(od -An -v -tx1 -- "$caminho" | tr -d '[:space:]')
        [[ -n $encontrado ]] || continue
        [[ -z $edid || $edid == "$encontrado" ]] || erro 'há duas telas com esse nome. O login foi preservado.'
        edid=$encontrado
    done
    [[ -n $edid ]] || erro "identificação física do monitor $principal indisponível."

    anterior=$(ler_sddm X11 DisplayCommand /usr/share/sddm/scripts/Xsetup)
    if [[ $anterior == "$xsetup" && -f $estado/sddm-comando-original ]]; then
        anterior=$(< "$estado/sddm-comando-original")
    fi
    [[ $anterior == /* && $anterior != "$xsetup" && -x $anterior ]] ||
        erro "o comando de tela do SDDM é incompatível ($anterior)."
    if [[ -e $sddm_conf ]] && ! grep -Fxq '# Gerenciado por Callas KDE' "$sddm_conf"; then
        erro "já existe um arquivo personalizado em $sddm_conf."
    fi
    install -d -m 0755 "${xsetup%/*}" "${sddm_conf%/*}"
    printf '%s\n' "$anterior" > "$estado/sddm-comando-original"
    {
        printf '#!/usr/bin/bash\ncomando_original=%q\nedid_alvo=%q\n' "$anterior" "$edid"
        cat <<'XSETUP'
"$comando_original" "$@" || exit $?
saidas=$(/usr/bin/xrandr --prop) || exit 0
monitor=$(awk -v alvo="$edid_alvo" '
    function guardar() {
        if (saida != "" && edid == alvo) { principal = saida; quantidade++ }
    }
    /^[^[:space:]]/ {
        guardar()
        saida = ($2 == "connected") ? $1 : ""
        edid = ""
        lendo = 0
        next
    }
    $1 == "EDID:" { lendo = 1; next }
    lendo && NF == 1 && $1 ~ /^[[:xdigit:]]+$/ { edid = edid tolower($1); next }
    { lendo = 0 }
    END { guardar(); if (quantidade == 1) print principal }
' <<< "$saidas")
[[ -n $monitor ]] || exit 0
args=(--output "$monitor" --auto --primary --pos 0x0)
anterior=$monitor
while read -r saida; do
    [[ $saida != "$monitor" ]] || continue
    args+=(--output "$saida" --auto --right-of "$anterior")
    anterior=$saida
done < <(awk '$2 == "connected" { print $1 }' <<< "$saidas")
/usr/bin/xrandr "${args[@]}" || /usr/bin/xrandr --output "$monitor" --primary || :
XSETUP
    } > "$estado/sddm-xsetup"
    install -m 0755 "$estado/sddm-xsetup" "$xsetup"
    printf '# Gerenciado por Callas KDE\n[X11]\nDisplayCommand=%s\n' "$xsetup" > "$estado/sddm-conf"
    install -m 0644 "$estado/sddm-conf" "$sddm_conf"
    if [[ $(ler_sddm X11 DisplayCommand /usr/share/sddm/scripts/Xsetup) != "$xsetup" ]]; then
        rm -f -- "$sddm_conf" "$xsetup"
        erro 'uma configuração do SDDM tem prioridade sobre o ajuste. O login foi preservado.'
    fi
    rm -f -- "$estado/sddm-conf" "$estado/sddm-xsetup"
}

remover_xsetup() {
    if [[ -f $sddm_conf ]] && grep -Fxq '# Gerenciado por Callas KDE' "$sddm_conf"; then
        rm -f -- "$sddm_conf"
    fi
    if [[ -f $estado/sddm-comando-original ]]; then
        rm -f -- "$xsetup" "$estado/sddm-comando-original"
    fi
}

# O Breeze desenha o wallpaper fora do MouseArea que contém os controles.
# A marca permite reaplicar e desfazer sem restaurar versões antigas do tema.
ajustar_tema_sddm() {
    local acao=$1 arquivo=$2 alvo=${3:-} temporario
    [[ -f $arquivo && ! -L $arquivo ]] || return 1
    if [[ $acao == aplicar ]] && ! awk '
        /^[[:space:]]*id:[[:space:]]*wallpaper[[:space:]]*$/ { wallpaper = 1 }
        /^[[:space:]]*id:[[:space:]]*loginScreenRoot[[:space:]]*$/ {
            total++
            if (wallpaper && anterior ~ /^[[:space:]]*MouseArea[[:space:]]*\{[[:space:]]*$/) valido++
        }
        { anterior = $0 }
        END { exit !(total == 1 && valido == 1) }
    ' "$arquivo"; then
        printf 'Callas KDE: não reconheci o formato do tema %s.\n' "$arquivo" >&2
        return 1
    fi
    temporario=$(mktemp -- "${arquivo%/*}/.callas-tema.XXXXXXXX") || return 1
    if ! awk -v acao="$acao" -v alvo="$alvo" '
        /^[[:space:]]*\/\/ Callas KDE: inicio do login por tela[[:space:]]*$/ { bloco = 1; next }
        /^[[:space:]]*\/\/ Callas KDE: fim do login por tela[[:space:]]*$/ { bloco = 0; next }
        bloco || /^import QtQuick.Window \/\/ Callas KDE$/ { next }

        # O Breeze usa WallpaperFader para escurecer/desfocar o fundo enquanto
        # os controles de login estão visíveis. Mantemos a imagem original nítida.
        /^[[:space:]]*WallpaperFader[[:space:]]*\{/ { fader = 1 }
        acao == "desfazer" && /visible:[[:space:]]*false[[:space:]]*\/\/ Callas KDE: wallpaper nitido/ {
            sub(/visible:[[:space:]]*false[[:space:]]*\/\/ Callas KDE: wallpaper nitido/,
                "visible: config.type == \"image\"")
            print
            fader = 0
            next
        }
        acao == "aplicar" && fader && /^[[:space:]]*visible:[[:space:]]*config\.type[[:space:]]*={2,3}[[:space:]]*"image"/ {
            sub(/visible:.*/, "visible: false // Callas KDE: wallpaper nitido")
            print
            fader = 0
            next
        }

        {
            if (acao == "aplicar" && ! importado && /^import QtQuick([[:space:]]|$)/) {
                print "import QtQuick.Window // Callas KDE"
                importado = 1
            }
            print
        }
        acao == "aplicar" && /^[[:space:]]*id:[[:space:]]*loginScreenRoot[[:space:]]*$/ {
            print "        // Callas KDE: inicio do login por tela"
            print "        visible: {"
            print "            const telas = Qt.application.screens"
            print "            const atual = Screen.name"
            print "            if (telas.length < 2 || atual === \"\") return true"
            print "            const alvo = \"" alvo "\""
            print "            for (let i = 0; alvo !== \"\" && i < telas.length; ++i) {"
            print "                if (telas[i].name === alvo) return atual === alvo"
            print "            }"
            print "            return atual === telas[0].name"
            print "        }"
            print "        enabled: visible"
            print "        // Callas KDE: fim do login por tela"
        }
        END { if (bloco || (acao == "aplicar" && !importado)) exit 1 }
    ' "$arquivo" > "$temporario" ||
        ! chmod --reference="$arquivo" "$temporario" ||
        ! chown --reference="$arquivo" "$temporario" ||
        ! mv -fT -- "$temporario" "$arquivo"; then
        rm -f -- "$temporario"
        return 1
    fi
}

instalar_tema_sddm() {
    local alvo=$1 tema pasta arquivo anterior selecionar_breeze=0
    tema=$(ler_sddm Theme Current '')
    pasta=$(ler_sddm Theme ThemeDir /usr/share/sddm/themes)
    if [[ -z $tema ]]; then
        tema=breeze
        selecionar_breeze=1
    fi
    [[ $tema =~ ^[[:alnum:]_.-]+$ && $pasta == /usr/share/sddm/themes ]] ||
        erro 'o SDDM precisa estar usando um tema Breeze instalado para aplicar este ajuste.'
    arquivo=$(realpath -e -- "$pasta/$tema/Main.qml") || erro "não encontrei o Main.qml do tema $tema."
    [[ $arquivo =~ ^/usr/share/sddm/themes/[[:alnum:]_.-]+/Main\.qml$ ]] ||
        erro "local inesperado do tema $tema."
    if [[ -f $estado/sddm-tema ]]; then
        anterior=$(< "$estado/sddm-tema")
        if [[ $anterior != "$arquivo" && -f $anterior ]]; then
            ajustar_tema_sddm desfazer "$anterior"
        fi
    fi
    ajustar_tema_sddm aplicar "$arquivo" "$alvo" || erro 'o tema do SDDM ficou com seu comportamento original.'
    printf '%s\n' "$arquivo" > "$estado/sddm-tema"
    if (( selecionar_breeze )); then
        install -d -m 0755 "${sddm_breeze%/*}"
        if [[ -e $sddm_breeze ]] && ! grep -Fxq '# Tema gerenciado por Callas KDE' "$sddm_breeze"; then
            erro "já existe uma configuração de tema em $sddm_breeze."
        fi
        printf '# Tema gerenciado por Callas KDE\n[Theme]\nCurrent=breeze\n' > "$estado/breeze-conf"
        install -m 0644 "$estado/breeze-conf" "$sddm_breeze"
        rm -f -- "$estado/breeze-conf"
        if [[ $(ler_sddm Theme Current '') != breeze ]]; then
            rm -f -- "$sddm_breeze"
            ajustar_tema_sddm desfazer "$arquivo"
            rm -f -- "$estado/sddm-tema"
            erro 'o SDDM tem uma configuração de tema com prioridade. Selecione Breeze no KDE e rode novamente.'
        fi
    fi
    {
        printf '#!/usr/bin/env bash\nset -u\n'
        declare -f ajustar_tema_sddm
        printf 'ajustar_tema_sddm aplicar %q %q\n' "$arquivo" "$alvo"
    } > "$estado/auxiliar-tema"
    install -m 0755 "$estado/auxiliar-tema" /usr/local/lib/callas-kde/ajustar-tema-sddm
    cat > "$estado/hook-tema" <<HOOK_TEMA
[Trigger]
Operation = Install
Operation = Upgrade
Type = Path
Target = ${arquivo#/}

[Action]
Description = Reaplicando o login do KDE no monitor principal...
When = PostTransaction
Exec = /usr/local/lib/callas-kde/ajustar-tema-sddm
HOOK_TEMA
    install -m 0644 "$estado/hook-tema" /etc/pacman.d/hooks/99-callas-kde-tema-sddm.hook
    rm -f -- "$estado/auxiliar-tema" "$estado/hook-tema"
}

restaurar_layout_login() {
    [[ -f $estado/login-original.json || -f $estado/login-ausente ]] || return 0
    local usuario_login=plasmalogin destino
    if [[ -f $estado/login-conta ]]; then
        usuario_login=$(< "$estado/login-conta")
    fi
    localizar_config_login
    if [[ -f $estado/login-original.json ]]; then
        gravar_login < "$estado/login-original.json"
    else
        como_login /usr/bin/rm -f -- "$destino"
    fi
    rm -f -- "$estado/login-original.json" "$estado/login-ausente" "$estado/login-conta"
}

gravar_login() {
    # A pasta pertence ao greeter. A gravação também roda como greeter.
    como_login /usr/bin/bash -eu -c '
        umask 077
        destino=$1
        mkdir -p -- "${destino%/*}"
        temporario=$(mktemp -- "${destino%/*}/.callas-kwin.XXXXXXXX")
        trap '\''rm -f -- "$temporario"'\'' EXIT
        cat > "$temporario"
        mv -fT -- "$temporario" "$destino"
    ' bash "$destino"
}

modo_sistema() (
    local acao=$1 principal=${2:-} usuario_login=plasmalogin destino modo compositor
    local resultado=0 somente_monitor=0
    if [[ $acao == monitor ]]; then somente_monitor=1; acao=aplicar; fi
    local estado=/var/lib/callas-kde-desligamento-login
    local auxiliar=/usr/local/lib/callas-kde/ajustar-contagem
    local hook=/etc/pacman.d/hooks/99-callas-kde-contagem.hook
    local sddm_conf=/etc/sddm.conf.d/99-callas-kde-monitor.conf
    local sddm_breeze=/etc/sddm.conf.d/99-callas-kde-breeze.conf
    local xsetup=/usr/local/lib/callas-kde/sddm-xsetup

    /usr/bin/install -d -m 0700 "$estado"
    exec 9>"$estado/lock"
    /usr/bin/flock -x 9

    if [[ $acao == desfazer ]]; then
        rm -f -- "$hook"
        ajustar_contagem desfazer
        rm -f -- "$auxiliar"
        remover_xsetup
        if [[ -f $sddm_breeze ]] && grep -Fxq '# Tema gerenciado por Callas KDE' "$sddm_breeze"; then
            rm -f -- "$sddm_breeze"
        fi
        rm -f -- /etc/pacman.d/hooks/99-callas-kde-tema-sddm.hook /usr/local/lib/callas-kde/ajustar-tema-sddm
        if [[ -f $estado/sddm-tema ]]; then
            local tema_anterior
            tema_anterior=$(< "$estado/sddm-tema")
            if [[ -f $tema_anterior ]]; then
                ajustar_tema_sddm desfazer "$tema_anterior"
            fi
            rm -f -- "$estado/sddm-tema"
        fi
        restaurar_layout_login
        printf 'Ajustes desfeitos. O login usa a configuração restaurada na próxima vez.\n'
        return
    fi

    local novo
    novo=$(mktemp -- "$estado/.novo.XXXXXXXX")
    trap 'rm -f -- "$novo"' EXIT
    cat > "$novo"
    remover_xsetup

    if (( ! somente_monitor )); then
    ajustar_contagem aplicar || resultado=1
    install -d -m 0755 /usr/local/lib/callas-kde /etc/pacman.d/hooks
    {
        printf '#!/usr/bin/env bash\nset -u\n'
        declare -f ajustar_contagem
        printf 'ajustar_contagem aplicar\n'
    } > "$estado/auxiliar"
    install -m 0755 "$estado/auxiliar" "$auxiliar"
    cat > "$estado/hook" <<'HOOK'
[Trigger]
Operation = Install
Operation = Upgrade
Type = Path
Target = usr/share/plasma/shells/org.kde.plasma.desktop/contents/logout/Logout.qml
Target = usr/share/plasma/shells/org.kde.plasma.desktop/contents/logout/LogoutControls.qml
Target = usr/share/plasma/look-and-feel/org.kde.breeze.desktop/contents/logout/Logout.qml

[Action]
Description = Reaplicando a contagem de 5 segundos do KDE...
When = PostTransaction
Exec = /usr/local/lib/callas-kde/ajustar-contagem
HOOK
    install -m 0644 "$estado/hook" "$hook"
    rm -f -- "$estado/auxiliar" "$estado/hook"
    if (( resultado == 0 )); then
        printf 'Contagem do KDE ajustada para 5 segundos.\n'
    fi

    fi

    if [[ $acao == instalar ]]; then
        instalar_tema_sddm "$principal"
        printf 'SDDM preparado. O formulário fica na saída principal e as outras exibem o wallpaper.\n'
        return "$resultado"
    fi

    if systemctl is-active --quiet plasmalogin.service; then
        if ! /usr/bin/getent passwd plasmalogin >/dev/null; then
            [[ -f /usr/lib/sysusers.d/plasmalogin.conf ]] ||
                erro 'o Plasma Login está ativo, mas a definição da conta do pacote está ausente.'
            systemd-sysusers plasmalogin.conf
            if [[ -f /usr/lib/tmpfiles.d/plasmalogin.conf ]]; then
                systemd-tmpfiles --create plasmalogin.conf
            fi
        fi
    elif systemctl is-active --quiet sddm.service; then
        modo=$(ler_sddm General DisplayServer x11)
        case $modo in
            x11|x11-user)
                restaurar_layout_login
                configurar_sddm_x11 "$principal"
                instalar_tema_sddm ''
                printf 'SDDM: formulário no %s e wallpaper nas duas telas. Confira no próximo login.\n' "$principal"
                return "$resultado"
                ;;
            wayland)
                compositor=$(ler_sddm Wayland CompositorCommand '')
                [[ ${compositor%% *} == kwin_wayland || ${compositor%% *} == /usr/bin/kwin_wayland ]] ||
                    erro 'o SDDM em Wayland usa um compositor diferente do KWin.'
                usuario_login=sddm
                ;;
            *) erro "modo do SDDM desconhecido ($modo)." ;;
        esac
    else
        erro 'gerenciador de login ativo diferente de Plasma Login e SDDM. Rode systemctl status display-manager para identificá-lo.'
    fi

    if [[ ! -s $novo ]]; then
        restaurar_layout_login
        erro 'restaurei o layout anterior. Para aplicar o novo, deixe as duas telas ligadas e ativas na sessão Plasma.'
    fi
    localizar_config_login
    if [[ -f $estado/login-original.json || -f $estado/login-ausente ]]; then
        local conta_backup=plasmalogin
        if [[ -f $estado/login-conta ]]; then
            conta_backup=$(< "$estado/login-conta")
        fi
        [[ $conta_backup == "$usuario_login" ]] || erro 'o gerenciador mudou desde a última aplicação. Desfaça o ajuste anterior antes de reaplicar.'
    else
        printf '%s\n' "$usuario_login" > "$estado/login-conta"
        if como_login /usr/bin/test -e "$destino"; then
            como_login /usr/bin/cat -- "$destino" > "$estado/login-backup.tmp"
            mv -fT -- "$estado/login-backup.tmp" "$estado/login-original.json"
        else
            touch "$estado/login-ausente"
        fi
    fi
    gravar_login < "$novo"
    if [[ $usuario_login == sddm ]]; then
        instalar_tema_sddm "$principal"
        printf 'SDDM: formulário no %s e wallpaper nas duas telas. Confira no próximo login.\n' "$principal"
    else
        printf 'Plasma Login: %s como principal, com as duas telas ligadas. O formulário nativo pode acompanhar o ponteiro.\n' "$principal"
    fi
    return "$resultado"
)

preparar_login() {
    /usr/bin/python3 - "${XDG_CONFIG_HOME:-$HOME/.config}/kwinoutputconfig.json" "$1" <<'PYTHON'
import json
from pathlib import Path
import re
import sys


def normalizar(nome):
    return re.sub(r"^HDMI-A-(?=\d+$)", "HDMI-", nome)


def configurar(origem, principal):
    principal = normalizar(principal)
    conectados = {
        normalizar(status.parent.name.split("-", 1)[1])
        for status in Path("/sys/class/drm").glob("card*-*/status")
        if status.read_text().strip() == "connected"
    }
    if principal not in conectados or len(conectados) < 2:
        raise ValueError("conecte os dois monitores e confira o nome da saída principal.")

    config = json.loads(origem.read_text())
    secoes = {secao["name"]: secao["data"] for secao in config}
    saidas = secoes["outputs"]
    perfis_ajustados = 0
    for perfil in secoes["setups"]:
        monitores = perfil["outputs"]
        indices = [monitor["outputIndex"] for monitor in monitores]
        if any(type(indice) is not int or not 0 <= indice < len(saidas) for indice in indices):
            raise ValueError("o KWin salvou um índice de monitor inválido.")
        nomes = [normalizar(saidas[indice].get("connectorName", "")) for indice in indices]
        if len(nomes) != len(conectados) or set(nomes) != conectados:
            continue
        if not all(monitor.get("enabled") for monitor in monitores):
            continue
        if any(monitor.get("replicationSource") for monitor in monitores):
            continue
        ordenados = sorted(zip(monitores, nomes), key=lambda par: par[1] != principal)
        for prioridade, (monitor, _) in enumerate(ordenados):
            monitor["priority"] = prioridade
        perfis_ajustados += 1

    if not perfis_ajustados:
        raise ValueError("nenhum perfil do KWin corresponde aos monitores conectados.")
    return config


try:
    config = configurar(Path(sys.argv[1]), sys.argv[2])
except (OSError, ValueError, TypeError, KeyError) as erro:
    sys.exit(f"Erro ao preparar o login: {erro}")
json.dump(config, sys.stdout, indent=4)
print()
PYTHON
}

if [[ ${1:-} == --preparar-instalacao && $EUID == 0 && $# == 1 ]]; then
    modo_sistema instalar '' </dev/null
    exit
fi

if [[ ${1:-} == --sistema && $EUID == 0 && $# -ge 2 ]]; then
    case $2 in
        aplicar|monitor)
            [[ $# == 3 && $3 =~ ^[[:alnum:]]+(-[[:alnum:]]+)+$ ]] || erro 'saída inválida.'
            modo_sistema "$2" "$3"
            exit
            ;;
        desfazer) modo_sistema desfazer; exit ;;
    esac
fi
[[ $EUID != 0 ]] || erro 'rode com bash no Konsole, como seu usuário. O script pede sudo quando precisar.'
acao_usuario=aplicar
if [[ ${1:-} == --monitor ]]; then acao_usuario=monitor; shift; fi
[[ $# -le 1 ]] || erro 'use bash callas-kde-desligamento-login.sh [DP-3|--desfazer].'
[[ -f /etc/arch-release ]] || erro 'este script é para Arch Linux.'
script=$(realpath -- "${BASH_SOURCE[0]}")
if [[ ${1:-} == --desfazer ]]; then
    exec sudo /usr/bin/bash -- "$script" --sistema desfazer
fi
[[ ${XDG_SESSION_TYPE:-} == wayland ]] || erro 'rode dentro da sessão Plasma Wayland.'
principal=${1:-DP-3}
[[ $principal =~ ^[[:alnum:]]+(-[[:alnum:]]+)+$ ]] || erro 'informe uma saída como DP-3.'
novo_login=$(mktemp)
trap 'rm -f -- "$novo_login"' EXIT
if [[ -x /usr/bin/python3 ]]; then
    if ! preparar_login "$principal" > "$novo_login"; then
        : > "$novo_login"
    fi
fi
printf 'Monitor escolhido para o login: %s\n' "$principal"
sudo -v
sudo /usr/bin/bash -- "$script" --sistema "$acao_usuario" "$principal" < "$novo_login"
CALLAS_KDE_LOGIN
cat > "/mnt/usr/local/libexec/callas-nekofetch" <<'CALLAS_NEKO'
#!/usr/bin/bash
set -euo pipefail
export UV_TOOL_BIN_DIR="$HOME/.local/bin"
export PATH="$UV_TOOL_BIN_DIR:$PATH"
config=${XDG_CONFIG_HOME:-$HOME/.config}/nekofetch
uv tool install --upgrade git+https://github.com/ArchitektApx/nekofetch
command -v nekofetch >/dev/null
mkdir -p "$config"

# O layout é do Fastfetch. Usa os valores dedicados do driver de cada GPU.
"$(uv tool dir)/nekofetch/bin/python" - "$config/layout.jsonc" <<'PY_LAYOUT'
from importlib.resources import files
from pathlib import Path
import json
import re
import sys

destino = Path(sys.argv[1])
origem = destino if destino.is_file() else files("nekofetch").joinpath("data", "layout.jsonc")
texto = origem.read_text(encoding="utf-8")
# Remove comentários JSONC sem tocar em URLs, escapes ou no texto dos comandos.
tokens = r'("(?:\\.|[^"\\])*")|//[^\n]*|/\*[\s\S]*?\*/'
texto = re.sub(tokens, lambda item: item[1] or "", texto)
texto = re.sub(r'("(?:\\.|[^"\\])*")|,(?=\s*[}\]])', lambda item: item[1] or "", texto)
layout = json.loads(texto)
modulos = layout["modules"]
sistema = "38;2;189;147;249"
hardware = "38;2;255;121;198"

def inserir(ancora, tipo, nome, icone, cor, formato, **opcoes):
    for modulo in modulos:
        if not isinstance(modulo, dict):
            continue
        if modulo.get("type") == tipo and (
            tipo != "gpu" or nome == "GPU" and modulo.get("format") == "{name}"
            or nome in modulo.get("key", "").split()
        ):
            if nome == "VRAM":
                modulo.update(format=formato, **opcoes)
            return
    for indice, modulo in enumerate(modulos):
        if isinstance(modulo, dict) and (
            modulo.get("type") == ancora or (ancora == "os" and modulo.get("text") == "/usr/local/libexec/callas-version --label") or ancora in modulo.get("key", "").split()
        ):
            modulos.insert(indice + 1, {
                "key": f"  {chr(icone)} {nome:9}",
                "keyColor": cor,
                "type": tipo,
                "format": formato,
                **opcoes,
            })
            return
    raise SystemExit(f"Nekofetch: módulo de referência ausente: {ancora}.")

inserir("os", "kernel", "Kernel", 0xF17C, sistema, "{release}")
inserir("kernel", "de", "Desktop", 0xF0379, sistema, "{pretty-name} {version}")
inserir("cpu", "display", "Display", 0xF0379, hardware, "{width}x{height} @ {refresh-rate}Hz")
inserir("cpu", "gpu", "GPU", 0xF08AE, hardware, "{name}")
inserir("GPU", "gpu", "Driver", 0xF061A, hardware, "{driver}")
inserir("Driver", "gpu", "VRAM", 0xF035B, hardware,
        "{?dedicated-total}{?dedicated-used}{dedicated-used} / {?}{dedicated-total}{?}"
        "{/dedicated-total}Indisponível{/}",
        driverSpecific=True)
novo = json.dumps(layout, ensure_ascii=False, indent=2) + "\n"
if not destino.exists() or destino.read_text(encoding="utf-8") != novo:
    temporario = destino.with_suffix(".tmp")
    temporario.write_text(novo, encoding="utf-8")
    temporario.replace(destino)
PY_LAYOUT
/usr/local/libexec/callas-version --configure-neko

bashrc="$HOME/.bashrc"
path_line='export PATH="$HOME/.local/bin:$PATH"'
startup='[[ $- == *i* ]] && command -v nekofetch >/dev/null 2>&1 && nekofetch'
comment='# Nekofetch automático ao abrir o terminal'
touch "$bashrc"
if ! grep -Fxq "$path_line" "$bashrc"; then
  printf '\n%s\n' "$path_line" >> "$bashrc"
fi
temp=$(mktemp)
trap 'rm -f -- "$temp"' EXIT
grep -Fvx -e "$startup" -e "$comment" \
  -e 'command -v nekofetch >/dev/null 2>&1 && nekofetch' "$bashrc" > "$temp" || :
cat "$temp" > "$bashrc"
printf '\n%s\n%s\n' "$comment" "$startup" >> "$bashrc"
CALLAS_NEKO
chmod 0755 /mnt/usr/local/libexec/{put-update,callas-inicio-kde,callas-kde-desligamento-login,callas-nekofetch}
install -d /mnt/etc/xdg
cat > /mnt/etc/xdg/kicker-extra-favoritesrc <<'KICKER_FAVORITES'
[General]
IgnoreDefaults=true
Prepend=io.github.Callas157.Monitores.desktop;systemsettings.desktop;io.github.Callas157.AtualizadorDoSistema.desktop;steam.desktop;org.kde.konsole.desktop;io.github.kolunmi.Bazaar.desktop;com.vysp3r.ProtonPlus.desktop;io.missioncenter.MissionCenter.desktop;org.qbittorrent.qBittorrent.desktop;spotify.desktop;solaar.desktop;
KICKER_FAVORITES

# O Plasma executa esta configuração uma vez, depois de criar o painel.
plasma_updates=/mnt/usr/share/plasma/shells/org.kde.plasma.desktop/contents/updates
if ! install -d "$plasma_updates" ||
   ! cat > "$plasma_updates/callas-panel-v1.js" <<'PLASMA_PANEL'
const callasIcon = fileExists("/usr/share/icons/hicolor/256x256/apps/callas-plasma-icon.png");
const callasLaunchers = ["applications:org.kde.dolphin.desktop"];
if (fileExists("/usr/share/applications/brave-browser.desktop")) {
    callasLaunchers.push("applications:brave-browser.desktop");
}

panels().forEach(function (panel) {
    // Altura e transparência padrão do painel Callas OS.
    panel.height = 60;
    panel.opacity = "translucent";

    panel.widgets("org.kde.plasma.icontasks").forEach(function (tasks) {
        tasks.currentConfigGroup = ["General"];
        tasks.writeConfig("launchers", callasLaunchers);
        tasks.reloadConfig();
    });

    if (callasIcon) {
        panel.widgets("org.kde.plasma.kickoff").forEach(function (menu) {
            menu.currentConfigGroup = ["General"];
            menu.writeConfig("icon", "callas-plasma-icon");
            menu.reloadConfig();
        });
    }
});

// Define o wallpaper antes da área de trabalho terminar de aparecer.
// Assim evitamos o flash do wallpaper padrão do KDE no primeiro login.
desktops().forEach(function (desktop) {
    desktop.wallpaperPlugin = "org.kde.image";
    desktop.currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];
    desktop.writeConfig(
        "Image",
        "file:///usr/share/wallpapers/CallasOS-callas-wallpaper-14-mountains-moon/contents/images/1920x1080.jpg"
    );
    desktop.reloadConfig();
});
PLASMA_PANEL
then
  echo "Aviso: não consegui preparar o painel do KDE. Seguindo com a instalação." >&2
fi

# ---------------- Configuração dentro do sistema ----------------
# Create accounts and set passwords before the noninteractive configuration.
arch-chroot /mnt useradd -m -U -G wheel -s /bin/bash "$USUARIO"
printf '%s:%s\n%s:%s\n' "$USUARIO" "$SENHA" root "$SENHA" | arch-chroot /mnt chpasswd
unset SENHA SENHA2

echo ">>> Configurando o sistema"
cat > /mnt/usr/local/share/callas-os/install-config.sh <<'CALLAS_CHROOT'
#!/usr/bin/bash
set -Eeuo pipefail
trap 'code=$?; printf "ERRO: configuração interna interrompida na linha %s (código %s).\n" "$LINENO" "$code" >&2; exit "$code"' ERR
usuario=$1
fuso=$2
locale=$3
teclado=$4
hostname=$5
uuid_raiz=$6
nvidia=$7
vm=$8
broadcom=$9
gpu_pci=${10}
risemode=${11}
amd_gpu=${12}
intel_gpu=${13}
asset_base=${14:?Endereço dos assets não recebido pelo chroot}
home=/home/$usuario
libexec=/usr/local/libexec
avisos=/var/log/callas-instalacao-avisos.log

aviso() {
  printf 'Aviso: %s\n' "$*" | tee -a "$avisos" >&2
}

ln -sf "/usr/share/zoneinfo/$fuso" /etc/localtime
hwclock --systohc || aviso 'Relógio de hardware indisponível.'
sed -i 's/^#pt_BR.UTF-8/pt_BR.UTF-8/; s/^#en_US.UTF-8/en_US.UTF-8/' /etc/locale.gen
locale-gen
printf 'LANG=%s\n' "$locale" > /etc/locale.conf
printf 'KEYMAP=%s\nXKBLAYOUT=us\nXKBVARIANT=intl\n' "$teclado" > /etc/vconsole.conf
install -d /etc/X11/xorg.conf.d
cat > /etc/X11/xorg.conf.d/00-keyboard.conf <<'KBD'
Section "InputClass"
    Identifier "teclado"
    MatchIsKeyboard "on"
    Option "XkbLayout" "us"
    Option "XkbVariant" "intl"
EndSection
KBD
printf '%s\n' "$hostname" > /etc/hostname
printf '127.0.0.1 localhost\n::1 localhost\n127.0.1.1 %s.localdomain %s\n' "$hostname" "$hostname" > /etc/hosts

sed -i 's/^#ParallelDownloads.*/ParallelDownloads = 10/; s/^#Color/Color/' /etc/pacman.conf
sed -i '/^#\[multilib\]/,/^#Include/ s/^#//' /etc/pacman.conf

# NVIDIA: o Callas OS fixa a série 610.57.04 por estabilidade em jogos/Vulkan.
# Usa nvidia-open-dkms para atender os kernels linux e linux-lts com a mesma
# versão de módulo. A pilha inteira é mantida alinhada.
if (( nvidia )); then
  pacman -Syu --needed --noconfirm lib32-libglvnd egl-wayland

  nvidia_dir=$(mktemp -d /var/tmp/callas-nvidia.XXXXXXXX)

  nvidia_urls=(
    "https://archive.archlinux.org/packages/n/nvidia-utils/nvidia-utils-610.57.04-1-x86_64.pkg.tar.zst"
    "https://archive.archlinux.org/packages/n/nvidia-open-dkms/nvidia-open-dkms-610.57.04-1-x86_64.pkg.tar.zst"
    "https://archive.archlinux.org/packages/l/lib32-nvidia-utils/lib32-nvidia-utils-610.57.04-1-x86_64.pkg.tar.zst"
    "https://archive.archlinux.org/packages/l/libxnvctrl/libxnvctrl-610.57.04-1-x86_64.pkg.tar.zst"
    "https://archive.archlinux.org/packages/n/nvidia-settings/nvidia-settings-610.57.04-1-x86_64.pkg.tar.zst"
  )

  nvidia_pkgs=()
  for url in "${nvidia_urls[@]}"; do
    arquivo="$nvidia_dir/${url##*/}"
    curl -fL --retry 3 --connect-timeout 15 --max-time 300 "$url" -o "$arquivo" ||
      { echo "ERRO: não foi possível baixar ${url##*/} do Arch Linux Archive." >&2; exit 1; }
    curl -fL --retry 3 --connect-timeout 15 --max-time 60 "$url.sig" -o "$arquivo.sig" ||
      { echo "ERRO: assinatura ausente para ${url##*/}." >&2; exit 1; }
    pacman-key --verify "$arquivo.sig" "$arquivo" || {
      echo 'ERRO: assinatura NVIDIA inválida.' >&2; exit 1;
    }
    nvidia_pkgs+=("$arquivo")
  done

  pacman -U --noconfirm "${nvidia_pkgs[@]}"

  # Evita que pacman/Paru troquem apenas parte da pilha NVIDIA em um update.
  sed -i '/^# CALLAS_NVIDIA_610_BEGIN$/,/^# CALLAS_NVIDIA_610_END$/d' /etc/pacman.conf
  sed -i '/^\[options\]$/a # CALLAS_NVIDIA_610_BEGIN\nIgnorePkg = nvidia-utils nvidia-open-dkms nvidia-open nvidia-open-lts lib32-nvidia-utils nvidia-settings libxnvctrl opencl-nvidia lib32-opencl-nvidia\n# CALLAS_NVIDIA_610_END' /etc/pacman.conf

  printf '%s\n' '610.57.04' > /etc/callas-nvidia-version
  rm -rf "$nvidia_dir"
fi

printf '%%wheel ALL=(ALL:ALL) ALL\n' > /etc/sudoers.d/10-wheel
chmod 0440 /etc/sudoers.d/10-wheel
visudo -cf /etc/sudoers.d/10-wheel >/dev/null

como_usuario() {
  runuser -u "$usuario" -- env HOME="$home" USER="$usuario" LOGNAME="$usuario" "$@"
}

# O SDDM inicia o Plasma em Wayland. Os monitores permanecem ativos no greeter.
install -d /etc/sddm.conf.d /var/lib/sddm
cat > /etc/sddm.conf.d/10-wayland.conf <<'SDDM'
[General]
DisplayServer=wayland
GreeterEnvironment=QT_WAYLAND_SHELL_INTEGRATION=layer-shell

[Wayland]
CompositorCommand=kwin_wayland --drm --no-lockscreen --no-global-shortcuts --locale1

[Theme]
Current=breeze
CursorTheme=breeze_cursors
SDDM
cat > /var/lib/sddm/state.conf <<'SDDM_STATE'
[Last]
Session=/usr/share/wayland-sessions/plasma.desktop
SDDM_STATE
chown sddm:sddm /var/lib/sddm/state.conf

# O PAM abre a carteira KDE com a senha do login.
if ! grep -q 'pam_kwallet' /etc/pam.d/sddm; then
  printf '%s\n' 'auth optional pam_kwallet5.so' \
    'session optional pam_kwallet5.so auto_start kwalletd=/usr/bin/ksecretd' >> /etc/pam.d/sddm
fi
install -d -o "$usuario" -g "$usuario" "$home/.config" "$home/.config/autostart" "$home/.local" "$home/.local/bin"
cat > "$home/.config/kwalletrc" <<'KWRC'
[Wallet]
Default Wallet=kdewallet
Leave Open=true
Close When Idle=false
KWRC
printf '%s\n' '--password-store=kwallet6' '--lang=pt-BR' > "$home/.config/brave-flags.conf"
cat > /usr/local/bin/configurar-carteira <<'CARTEIRA'
#!/usr/bin/bash
sleep 10
if busctl --user call org.kde.kwalletd6 /modules/kwalletd6 org.kde.KWallet open sxs kdewallet 0 primeiro-login >/dev/null 2>&1; then
  rm -f "$HOME/.config/autostart/configurar-carteira.desktop"
fi
CARTEIRA
chmod 0755 /usr/local/bin/configurar-carteira
cat > "$home/.config/autostart/configurar-carteira.desktop" <<'AUTOSTART'
[Desktop Entry]
Type=Application
Name=Configurar carteira KDE
Exec=/usr/local/bin/configurar-carteira
AUTOSTART

cat > /etc/systemd/zram-generator.conf <<'ZRAM'
[zram0]
zram-size = ram / 2
compression-algorithm = zstd
ZRAM

# Dependências gráficas do Steam. O driver virtual ou de software evita
# puxar NVIDIA em uma VM que apresenta apenas VMSVGA, Virtio ou VGA.
gpu_multilib=(lib32-mesa)
# Em NVIDIA, lib32-nvidia-utils 610.57.04 já foi instalado e fixado acima.
if (( amd_gpu )); then
  gpu_multilib+=(vulkan-radeon lib32-vulkan-radeon)
fi
if (( intel_gpu )); then
  gpu_multilib+=(vulkan-intel lib32-vulkan-intel)
fi
if [[ $vm != none && -n $vm ]] && grep -q '^1af4:' <<<"$gpu_pci"; then
  gpu_multilib+=(vulkan-virtio lib32-vulkan-virtio)
fi
if (( ! nvidia && ! amd_gpu && ! intel_gpu )); then
  gpu_multilib+=(vulkan-swrast lib32-vulkan-swrast)
fi
pacman -Syu --needed --noconfirm "${gpu_multilib[@]}" vulkan-icd-loader lib32-vulkan-icd-loader steam discord shotcut

# O KMS padrão cobre Mesa e GPUs virtuais. Só antecipa os módulos da NVIDIA
# quando ela foi detectada e o pacote correspondente está instalado.
install -d /etc/plymouth
cat > /etc/plymouth/plymouthd.conf <<'PLYMOUTH_CONF'
[Daemon]
Theme=callas
ShowDelay=0
UseFirmwareBackground=false
PLYMOUTH_CONF
plymouth-set-default-theme callas
# O hook microcode incorpora o microcódigo Intel ou AMD no initramfs.
sed -i 's/^HOOKS=.*/HOOKS=(base systemd autodetect microcode modconf kms plymouth keyboard sd-vconsole block filesystems fsck)/' /etc/mkinitcpio.conf
nvidia_args=
if (( nvidia )); then
  sed -i 's/^MODULES=().*/MODULES=(nvidia nvidia_modeset nvidia_uvm nvidia_drm)/' /etc/mkinitcpio.conf
  nvidia_args=' nvidia_drm.modeset=1 nvidia_drm.fbdev=1'
fi
mkinitcpio -P
test -s /boot/vmlinuz-linux && test -s /boot/initramfs-linux.img
test -s /boot/vmlinuz-linux-lts && test -s /boot/initramfs-linux-lts.img

# Tema gráfico Callas OS.
install -d /boot/grub/themes/callas
install -m 0644 /usr/share/callas-os/grub/theme.txt /boot/grub/themes/callas/theme.txt
install -m 0644 /usr/share/callas-os/grub/background.png /boot/grub/themes/callas/background.png

# GRUB UEFI: instalação limpa experimental, preservando a partição EFI em /boot.
# Plymouth permanece integrado ao initramfs; sem atrasos artificiais no carregamento.
cat > /etc/default/grub <<GRUB_DEFAULTS
GRUB_DEFAULT=0
GRUB_TIMEOUT=3
GRUB_TIMEOUT_STYLE=menu
GRUB_DISTRIBUTOR="Callas OS"
GRUB_CMDLINE_LINUX_DEFAULT="quiet splash$nvidia_args"
GRUB_CMDLINE_LINUX=""
GRUB_TERMINAL_OUTPUT=gfxterm
GRUB_GFXMODE=auto
GRUB_GFXPAYLOAD_LINUX=keep
GRUB_THEME="/boot/grub/themes/callas/theme.txt"
# Mantém o mesmo wallpaper também no terminal gráfico usado pelo GRUB
# durante "Loading Linux" / "Loading initial ramdisk", evitando o bloco preto.
GRUB_BACKGROUND="/boot/grub/themes/callas/background.png"
GRUB_DISABLE_OS_PROBER=true
GRUB_DEFAULTS

# Confere a ESP antes de instalar o bootloader.
[[ "$(findmnt -no FSTYPE /boot)" == vfat ]] || {
  echo "ERRO: /boot não está montado como FAT32 (ESP)." >&2
  exit 1
}
efi_uuid="$(findmnt -no UUID /boot)"
[[ -n "$efi_uuid" ]] || { echo "ERRO: não consegui obter o UUID da ESP." >&2; exit 1; }

# Entradas de boot próprias do Callas OS.
# Não usamos o 10_linux automático porque ele injeta mensagens "Loading Linux"
# antes do kernel, o que abre o grande terminal preto sobre o wallpaper.
rm -f /etc/grub.d/42_callas_diagnostico /etc/grub.d/43_callas_recuperacao_lts

cat > /etc/grub.d/09_callas <<'GRUB_CALLAS'
#!/bin/sh
cat <<'MENU'
menuentry 'Callas OS Linux' --class gnu-linux --class callas {
    search --no-floppy --fs-uuid --set=root CALLAS_EFI_UUID
    linux /vmlinuz-linux root=UUID=CALLAS_ROOT_UUID rw quiet splashCALLAS_NVIDIA_ARGS
    initrd /initramfs-linux.img
}

menuentry 'Callas OS (kernel LTS - recuperação)' --class gnu-linux --class callas {
    search --no-floppy --fs-uuid --set=root CALLAS_EFI_UUID
    linux /vmlinuz-linux-lts root=UUID=CALLAS_ROOT_UUID rw quiet splashCALLAS_NVIDIA_ARGS
    initrd /initramfs-linux-lts.img
}

menuentry 'Callas OS (diagnóstico sem splash)' --class gnu-linux --class callas {
    search --no-floppy --fs-uuid --set=root CALLAS_EFI_UUID
    linux /vmlinuz-linux root=UUID=CALLAS_ROOT_UUID rw plymouth.enable=0 disablehooks=plymouthCALLAS_NVIDIA_ARGS
    initrd /initramfs-linux.img
}
MENU
GRUB_CALLAS

sed -i "s/CALLAS_EFI_UUID/$efi_uuid/g" /etc/grub.d/09_callas
sed -i "s/CALLAS_ROOT_UUID/$uuid_raiz/g" /etc/grub.d/09_callas
sed -i "s|CALLAS_NVIDIA_ARGS|$nvidia_args|g" /etc/grub.d/09_callas
chmod 0755 /etc/grub.d/09_callas

# Desativa a geração automática do Arch. O arquivo permanece no sistema e pode
# ser reativado manualmente em recuperação, mas não entra no grub.cfg normal.
chmod -x /etc/grub.d/10_linux

# Marca a arquitetura de GRUB compatível com o Callas Config Update atual.
install -d /etc/callas-os
printf '%s\n' 'grub-custom-v2' > /etc/callas-os/grub-layout

# Mantém essa arquitetura após futuras atualizações do pacote grub.
install -d /usr/local/libexec /etc/pacman.d/hooks
cat > /usr/local/libexec/callas-grub-custom <<'CALLAS_GRUB_CUSTOM'
#!/usr/bin/env bash
set -Eeuo pipefail

[[ -x /etc/grub.d/09_callas ]] || {
    echo "Callas OS: /etc/grub.d/09_callas não está disponível; GRUB não será regenerado." >&2
    exit 1
}

[[ -f /etc/grub.d/10_linux ]] && chmod -x /etc/grub.d/10_linux

tmp=$(mktemp /boot/grub/.grub.cfg.callas.XXXXXX)
trap 'rm -f "$tmp"' EXIT

grub-mkconfig -o "$tmp"
[[ -s "$tmp" ]]
grub-script-check "$tmp"
grep -Eq '(^|[[:space:]/])vmlinuz-linux([[:space:]]|$)' "$tmp"
grep -Eq '(^|[[:space:]/])vmlinuz-linux-lts([[:space:]]|$)' "$tmp"
grep -q "menuentry 'Callas OS Linux'" "$tmp"
grep -q "menuentry 'Callas OS (kernel LTS - recuperação)'" "$tmp"
grep -q "menuentry 'Callas OS (diagnóstico sem splash)'" "$tmp"

chmod 0600 "$tmp"
mv -f "$tmp" /boot/grub/grub.cfg
trap - EXIT
CALLAS_GRUB_CUSTOM
chmod 0755 /usr/local/libexec/callas-grub-custom

cat > /etc/pacman.d/hooks/99-callas-grub-custom.hook <<'CALLAS_GRUB_CUSTOM_HOOK'
[Trigger]
Operation = Install
Operation = Upgrade
Type = Package
Target = grub

[Action]
Description = Restaurando entradas personalizadas do GRUB do Callas OS...
When = PostTransaction
Exec = /usr/local/libexec/callas-grub-custom
CALLAS_GRUB_CUSTOM_HOOK

# Instala a entrada UEFI normal. Alguns firmwares/VMs recusam gravar NVRAM;
# isso não deve impedir a instalação porque também criamos o caminho fallback.
if ! grub-install --target=x86_64-efi --efi-directory=/boot --bootloader-id=CallasOS --recheck; then
  aviso 'Não consegui gravar a entrada UEFI na NVRAM; usando o caminho de boot fallback.'
fi

# Instala SEMPRE o fallback UEFI padrão (EFI/BOOT/BOOTX64.EFI).
# Não adiciona espera ao boot e aumenta a chance de iniciar em firmwares/VMs chatos.
grub-install --target=x86_64-efi --efi-directory=/boot --removable --no-nvram --recheck

/usr/local/libexec/callas-grub-custom
[[ -s /boot/grub/grub.cfg && -f /boot/grub/x86_64-efi/normal.mod ]]
[[ -f /boot/EFI/BOOT/BOOTX64.EFI ]] || {
  echo "ERRO: o executável fallback do GRUB não foi criado." >&2
  exit 1
}

systemctl --root=/ enable NetworkManager sddm bluetooth fstrim.timer systemd-timesyncd

# Rise Mode Aura Ice Black (USB aa88:8666).
# Só entra neste bloco quando o dispositivo foi encontrado ainda na ISO.
if (( risemode )); then
  echo ">>> Instalando driver do water cooler Rise Mode"
  risemode_src="$home/.local/src/risemode-driver"
  rm -rf -- "$risemode_src"
  install -d -o "$usuario" -g "$usuario" "$home/.local/src"

  if como_usuario rustup default stable &&
     como_usuario git clone --depth 1 https://github.com/evozniak/risemode-driver.git "$risemode_src" &&
     como_usuario env PATH="$home/.cargo/bin:/usr/bin:/bin" \
       bash -c 'cd "$1" && cargo build --release' bash "$risemode_src" &&
     [[ -x "$risemode_src/target/release/risemode-driver" ]]; then

    install -Dm755 "$risemode_src/target/release/risemode-driver" /usr/local/bin/risemode-driver

    cat > /etc/udev/rules.d/99-risemode.rules <<'RISEMODE_UDEV'
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="aa88", ATTRS{idProduct}=="8666", MODE="0660", TAG+="uaccess"
SUBSYSTEM=="usb", ATTRS{idVendor}=="aa88", ATTRS{idProduct}=="8666", MODE="0660", TAG+="uaccess"
RISEMODE_UDEV

    cat > /etc/systemd/system/risemode-driver.service <<'RISEMODE_SERVICE'
[Unit]
Description=Rise Mode Aura Ice Black - temperatura da CPU no display
After=multi-user.target systemd-udev-settle.service

[Service]
Type=simple
ExecStart=/usr/local/bin/risemode-driver
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
RISEMODE_SERVICE

    systemctl enable risemode-driver.service
    echo 'Driver Rise Mode preparado; o ajuste de segurança cria conta dedicada antes do primeiro boot.'
  else
    aviso 'O water cooler Rise Mode foi detectado, mas o driver não pôde ser compilado. A instalação do Callas OS continuará.'
    rm -f /usr/local/bin/risemode-driver /etc/udev/rules.d/99-risemode.rules /etc/systemd/system/risemode-driver.service
    systemctl daemon-reload || :
  fi
fi

# Solaar nativo como padrão. Os overrides também deixam pronta a versão Flatpak
# para quem a instalar no futuro. Somente o usuário da sessão ganha o acesso udev.
install -d /etc/udev/rules.d
cat > /etc/udev/rules.d/59-callas-logitech-hidraw.rules <<'UDEV'
SUBSYSTEM=="hidraw", KERNEL=="hidraw*", ATTRS{idVendor}=="046d", MODE="0660", TAG+="uaccess"
SUBSYSTEM=="hidraw", KERNEL=="hidraw*", KERNELS=="*046D:*", MODE="0660", TAG+="uaccess"
UDEV
como_usuario flatpak override --user --device=all --env=GTK_THEME=Adwaita:dark io.github.pwr_solaar.solaar ||
  aviso 'Não consegui preparar os ajustes do Solaar Flatpak.'
if [[ -f /usr/share/applications/solaar.desktop ]]; then
  install -d /usr/local/share/applications
  sed 's|^Exec=|Exec=env GTK_THEME=Adwaita:dark |' /usr/share/applications/solaar.desktop \
    > /usr/local/share/applications/solaar.desktop
fi

if flatpak remote-add --system --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo; then
  for app in com.vysp3r.ProtonPlus io.github.kolunmi.Bazaar io.missioncenter.MissionCenter; do
    flatpak install --system --noninteractive --assumeyes flathub "$app" || aviso "Falha ao instalar $app."
  done
else
  aviso 'Não consegui configurar o Flathub.'
fi

# Unattended initial AUR installation. Recipes build without root/sudo;
# the root orchestrator installs dependencies and finished packages.
instalar_aur() {
  /usr/local/libexec/callas-aur-install "$usuario" "$@" || {
    aviso "Falha ao instalar via AUR: $*. Consulte o log da instalação."; return 1;
  }
}
instalar_aur paru-bin || :
instalar_aur brave-bin || :
if (( nvidia )); then instalar_aur nvibrant-bin || :; fi
# The AUR helper resolves the current recipe's validpgpkeys and verifies the
# package; avoid an outdated hardcoded Spotify signing-key URL.
instalar_aur spotify
if instalar_aur xone-dkms xone-dongle-firmware; then
  for pkgbase in /usr/lib/modules/*/pkgbase; do
    [[ -f $pkgbase && $(< "$pkgbase") == linux ]] || continue
    release=${pkgbase%/pkgbase}; release=${release##*/}
    if ! modinfo -k "$release" xone-dongle >/dev/null; then
      dkms autoinstall -k "$release" && modinfo -k "$release" xone-dongle >/dev/null ||
        aviso "O DKMS não preparou o xone para o kernel $release."
    fi
  done
fi
if (( broadcom )); then instalar_aur broadcom-wl-dkms || :; fi

# ---------------- Brave + Bonjourr + SteamDB ----------------
# Bonjourr é pré-instalado pela política do Brave. As preferências abaixo
# funcionam como padrão do Callas OS e continuam alteráveis pelo usuário.
install -d /etc/brave/policies/managed /etc/brave/policies/recommended /usr/share/callas-os

cat > /etc/brave/policies/managed/callas-bonjourr.json <<'CALLAS_BRAVE_EXTENSION'
{
  "ExtensionSettings": {
    "dlnejlppicbjfcfcedcflplfjajinajd": {
      "installation_mode": "normal_installed",
      "update_url": "https://clients2.google.com/service/update2/crx"
    },
    "kdbmhfkmnlmbkgbabkdealhhbfhlmmon": {
      "installation_mode": "normal_installed",
      "update_url": "https://clients2.google.com/service/update2/crx"
    }
  }
}
CALLAS_BRAVE_EXTENSION
chmod 0644 /etc/brave/policies/managed/callas-bonjourr.json

cat > /etc/brave/policies/recommended/callas-defaults.json <<'CALLAS_BRAVE_DEFAULTS'
{
  "RestoreOnStartup": 5,
  "ShowHomeButton": true,
  "HomepageIsNewTabPage": true,
  "BookmarkBarEnabled": true
}
CALLAS_BRAVE_DEFAULTS

curl -fsSL --retry 2 "$asset_base/bonjourr/callas-profile.json" \
  -o /usr/share/callas-os/bonjourr-profile.json ||
  aviso 'Não consegui baixar o perfil padrão do Bonjourr.'

# Preferências que não possuem política própria no Brave são pré-carregadas no
# primeiro perfil. No Linux, false em browser.custom_chrome_frame significa
# usar barra de título e bordas do sistema.
if [[ -d /opt/brave-bin ]]; then
  BRAVE_INITIAL=/opt/brave-bin/initial_preferences
  python3 - "$BRAVE_INITIAL" <<'CALLAS_BRAVE_PREFS'
import json, os, sys
path=sys.argv[1]
data={}
try:
    with open(path, "r", encoding="utf-8") as f:
        data=json.load(f)
except Exception:
    data={}
data.setdefault("browser", {})["custom_chrome_frame"]=False
data["browser"]["show_home_button"]=True
data["homepage_is_newtabpage"]=True
data.setdefault("bookmark_bar", {})["show_on_all_tabs"]=True
data.setdefault("intl", {})["accept_languages"]="pt-BR,pt,en-US,en"
data["intl"]["selected_languages"]="pt-BR,pt,en-US,en"
data.setdefault("tab_search", {})["pinned_to_tabstrip"]=True
data.setdefault("everything_menu", {})["pinned_to_tabstrip"]=True
actions=data.setdefault("toolbar", {}).setdefault("pinned_actions", [])
if "kActionTabSearch" not in actions:
    actions.append("kActionTabSearch")
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
CALLAS_BRAVE_PREFS
fi

if command -v nvibrant >/dev/null; then
  cat > "$home/.local/bin/DigitalVibrance.sh" <<'VIBRANCE'
#!/usr/bin/bash
exec nvibrant 1023 1023 1023 1023 1023 1023
VIBRANCE
  chmod 0755 "$home/.local/bin/DigitalVibrance.sh"
fi
chown -R "$usuario:$usuario" "$home/.local" "$home/.config"
como_usuario env LANG="$locale" xdg-user-dirs-update || aviso 'Não consegui preparar as pastas do usuário.'
como_usuario kwriteconfig6 --file kdeglobals --group KDE --key LookAndFeelPackage org.kde.breezedark.desktop
como_usuario kwriteconfig6 --file kdeglobals --group General --key ColorScheme BreezeDark
como_usuario env QT_QPA_PLATFORM=offscreen dbus-run-session -- plasma-apply-lookandfeel --apply org.kde.breezedark.desktop ||
  aviso 'Não consegui aplicar o tema Brisa Escuro.'

# Por padrão o Callas OS não suspende, escurece ou desliga a tela por inatividade.
# O usuário continua podendo alterar tudo normalmente nas Configurações do Sistema.
for perfil in AC Battery LowBattery; do
  como_usuario kwriteconfig6 --file powerdevilrc --group "$perfil" --group Display     --key DimDisplayWhenIdle false ||
    aviso "Não consegui desativar o escurecimento automático no perfil $perfil."
  como_usuario kwriteconfig6 --file powerdevilrc --group "$perfil" --group Display     --key TurnOffDisplayWhenIdle false ||
    aviso "Não consegui desativar o desligamento automático da tela no perfil $perfil."
  como_usuario kwriteconfig6 --file powerdevilrc --group "$perfil" --group SuspendAndShutdown     --key AutoSuspendAction 0 ||
    aviso "Não consegui desativar a suspensão automática no perfil $perfil."
done

# Mantém o efeito de transparência/blur usado pelo painel e menus do Plasma.
como_usuario kwriteconfig6 --file kwinrc --group Plugins --key blurEnabled true ||
  aviso 'Não consegui garantir o efeito de blur do KWin.'

# Captura estilo Windows: Super+Shift+S abre a seleção retangular do Spectacle.
# O modo de região do Spectacle pode atravessar todos os monitores.
como_usuario kwriteconfig6 --file kglobalshortcutsrc \
  --group org.kde.spectacle.desktop \
  --key RectangularRegionScreenShot \
  'Meta+Shift+S,Meta+Shift+Print,Capture Rectangular Region' ||
  aviso 'Não consegui configurar Super+Shift+S para o Spectacle.'

# Fundo padrão da tela de bloqueio do Callas OS.
como_usuario kwriteconfig6 --file kscreenlockerrc \
  --group Greeter --group Wallpaper --group org.kde.image --group General \
  --key Image "file:///usr/share/callas-os/lockscreen/background.jpg" ||
  aviso 'Não consegui definir o wallpaper da tela de bloqueio.'

# A configuração de sessão vazia é preparada ainda no chroot.
"$libexec/callas-monitores" --install-system
"$libexec/callas-janelas" --install-system
como_usuario "$libexec/callas-inicio-kde" --preparar-primeiro-login

"$libexec/callas-kde-desligamento-login" --preparar-instalacao ||
  aviso 'O ajuste de desligamento ou do tema de login precisa ser conferido.'
export CALLAS_RELEASE_DIR=/usr/local/share/callas-os/security-stage
export CALLAS_RELEASE_REF=$(< "$CALLAS_RELEASE_DIR/commit")
python "$CALLAS_RELEASE_DIR/callas-version.py" --begin "$CALLAS_RELEASE_DIR/VERSION" "$CALLAS_RELEASE_REF"
SUDO_USER="$usuario" bash "$CALLAS_RELEASE_DIR/callas-security.sh" "$usuario" --installation
como_usuario "$libexec/callas-nekofetch"
"$libexec/callas-version" --complete "$CALLAS_RELEASE_DIR/VERSION" "$CALLAS_RELEASE_REF"
rm -rf -- "$CALLAS_RELEASE_DIR"

CALLAS_CHROOT
chmod 0700 /mnt/usr/local/share/callas-os/install-config.sh
bash -n /mnt/usr/local/share/callas-os/install-config.sh
arch-chroot /mnt /usr/bin/bash /usr/local/share/callas-os/install-config.sh \
  "$USUARIO" "$FUSO" "$LOCALE" "$TECLADO" "$HOSTNAME" "$UUID_RAIZ" \
  "$NVIDIA" "$VM" "$BROADCOM" "$GPU_PCI" "$RISEMODE" "$AMD_GPU" "$INTEL_GPU" "$CALLAS_ASSET_BASE"

# The EXIT handler exports the complete log on success and on failure.

echo
echo "=========================================================="
echo " Instalação concluída!"
if [[ -s /mnt/var/log/callas-instalacao-avisos.log ]]; then
  echo " Avisos no sistema instalado: /var/log/callas-instalacao-avisos.log"
fi
echo " Remova o pendrive e digite: reboot"
echo "=========================================================="


