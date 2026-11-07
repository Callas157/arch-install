#!/usr/bin/env bash
# =====================================================================
# Instalação automática do Arch Linux
# KDE Plasma (Wayland) + SDDM | pt-BR | UEFI | systemd-boot | ext4
# NVIDIA (nvidia-open) | microcódigo AMD/Intel detectado automaticamente
# Teclado: EUA Internacional | Steam, Discord, AUR (yay), Flatpak
#
# ATENÇÃO: APAGA TODO O DISCO ESCOLHIDO NO INÍCIO DO SCRIPT
# Rodar na ISO do Arch Linux, com internet por cabo.
# =====================================================================
set -euo pipefail

# ---------------- Configurações ----------------
DISCO="${DISCO:-}"   # se vazio, o script pergunta em qual disco instalar
HOSTNAME="arch"
FUSO="America/Sao_Paulo"
LOCALE="pt_BR.UTF-8"
TECLADO="us-acentos"   # console: EUA Internacional (com acentos)
# -----------------------------------------------

if [[ $EUID -ne 0 ]]; then
  echo "Rode como root (na ISO do Arch já é)."; exit 1
fi

if [[ ! -d /sys/firmware/efi/efivars ]]; then
  echo "ERRO: o PC não iniciou em modo UEFI. Ative UEFI na BIOS e desative o CSM."; exit 1
fi

if ! ping -c 1 -W 5 archlinux.org &>/dev/null; then
  echo "ERRO: sem internet. Confira o cabo de rede."; exit 1
fi

loadkeys "$TECLADO" || true

# ---------------- Detecção do processador ----------------
if grep -q "GenuineIntel" /proc/cpuinfo; then
  UCODE_PACKAGE="intel-ucode"
  UCODE_INITRD="intel-ucode.img"
  echo "Processador Intel detectado."
elif grep -q "AuthenticAMD" /proc/cpuinfo; then
  UCODE_PACKAGE="amd-ucode"
  UCODE_INITRD="amd-ucode.img"
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
  REDE_PACOTES+=(linux-headers dkms)
fi
if grep -qi 'ethernet controller' <<<"$PCI_REDE"; then echo "Placa de rede cabeada detectada."; fi
if (( TEM_WIFI )); then echo "Adaptador Wi-Fi detectado."; fi
if (( BROADCOM )); then echo "Wi-Fi Broadcom detectado: será instalado o driver broadcom-wl-dkms."; fi

# ---------------- Escolha do disco ----------------
if [[ -z "$DISCO" ]]; then
  BOOTPART="$(findmnt -no SOURCE /run/archiso/bootmnt 2>/dev/null || true)"
  BOOTDISK=""
  if [[ -n "$BOOTPART" ]]; then
    BOOTDISK="/dev/$(lsblk -no PKNAME "$BOOTPART" 2>/dev/null | head -n1)"
  fi
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
  if ! [[ "$ESCOLHA" =~ ^[0-9]+$ ]] || (( ESCOLHA < 1 || ESCOLHA > ${#LISTA[@]} )); then
    echo "Opção inválida."; exit 1
  fi
  DISCO="${LISTA[$((ESCOLHA-1))]}"
fi

if [[ ! -b "$DISCO" ]]; then
  echo "ERRO: disco $DISCO não encontrado."; lsblk -d -o NAME,SIZE,MODEL; exit 1
fi

echo
echo "=========================================================="
echo " Apagando e instalando no disco:"
lsblk -o NAME,SIZE,MODEL,FSTYPE "$DISCO"
echo "=========================================================="

read -rp "Nome do usuário (minúsculas, sem espaços): " USUARIO
[[ "$USUARIO" =~ ^[a-z_][a-z0-9_-]*$ ]] || { echo "Nome de usuário inválido."; exit 1; }

while true; do
  read -rsp "Senha do usuário (e do root): " SENHA; echo
  read -rsp "Repita a senha: " SENHA2; echo
  [[ -n "$SENHA" && "$SENHA" == "$SENHA2" ]] && break
  echo "As senhas não conferem, tente de novo."
done

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
sleep 2

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
  base linux linux-firmware "$UCODE_PACKAGE" base-devel sudo nano git \
  networkmanager "${REDE_PACOTES[@]}" \
  plasma-desktop sddm sddm-kcm plasma-nm plasma-pa kscreen powerdevil \
  konsole dolphin kate ark gwenview okular spectacle kdeplasma-addons \
  xdg-desktop-portal-kde xdg-user-dirs \
  kwallet-pam kwalletmanager \
  pipewire pipewire-alsa pipewire-pulse wireplumber \
  bluez bluez-utils \
  nvidia-open nvidia-utils nvidia-settings egl-wayland \
  noto-fonts noto-fonts-emoji ttf-dejavu ttf-liberation \
  flatpak \
  zram-generator

genfstab -U /mnt >> /mnt/etc/fstab

UUID_RAIZ="$(blkid -s UUID -o value "$RAIZ")"

# ---------------- Configuração dentro do sistema ----------------
echo ">>> Configurando o sistema"
arch-chroot /mnt /bin/bash <<EOF
set -e

# Fuso e relógio
ln -sf /usr/share/zoneinfo/$FUSO /etc/localtime
hwclock --systohc

# Idioma e teclado (EUA Internacional)
sed -i 's/^#pt_BR.UTF-8/pt_BR.UTF-8/; s/^#en_US.UTF-8/en_US.UTF-8/' /etc/locale.gen
locale-gen
echo "LANG=$LOCALE" > /etc/locale.conf
echo "KEYMAP=$TECLADO" > /etc/vconsole.conf
mkdir -p /etc/X11/xorg.conf.d
cat > /etc/X11/xorg.conf.d/00-keyboard.conf <<KBD
Section "InputClass"
    Identifier "teclado"
    MatchIsKeyboard "on"
    Option "XkbLayout" "us"
    Option "XkbVariant" "intl"
EndSection
KBD

# Nome da máquina
echo "$HOSTNAME" > /etc/hostname
cat > /etc/hosts <<HOSTS
127.0.0.1   localhost
::1         localhost
127.0.1.1   $HOSTNAME.localdomain $HOSTNAME
HOSTS

# Pacman: cores, downloads paralelos e multilib (necessário pro Steam)
sed -i 's/^#ParallelDownloads.*/ParallelDownloads = 10/; s/^#Color/Color/' /etc/pacman.conf
sed -i '/^#\[multilib\]/,/^#Include/ s/^#//' /etc/pacman.conf

# Usuário
useradd -m -G wheel -s /bin/bash $USUARIO
echo "%wheel ALL=(ALL:ALL) ALL" > /etc/sudoers.d/10-wheel
chmod 440 /etc/sudoers.d/10-wheel

# Carteira KDE: destravar sozinha no login (kwallet-pam)
# Garante as linhas do PAM no SDDM, caso o pacote do sddm não traga
if ! grep -q pam_kwallet /etc/pam.d/sddm; then
  echo "auth       optional   pam_kwallet5.so" >> /etc/pam.d/sddm
  echo "session    optional   pam_kwallet5.so auto_start kwalletd=/usr/bin/ksecretd" >> /etc/pam.d/sddm
fi

# No primeiro login, abre o assistente da carteira (criar a "kdewallet")
cat > /usr/local/bin/configurar-carteira <<'CARTEIRA'
#!/bin/bash
sleep 10
busctl --user call org.kde.kwalletd6 /modules/kwalletd6 org.kde.KWallet open sxs kdewallet 0 primeiro-login >/dev/null 2>&1 || true
rm -f "\$HOME/.config/autostart/configurar-carteira.desktop"
CARTEIRA
chmod +x /usr/local/bin/configurar-carteira
mkdir -p /home/$USUARIO/.config/autostart
cat > /home/$USUARIO/.config/kwalletrc <<'KWRC'
[Wallet]
Default Wallet=kdewallet
Leave Open=true
Close When Idle=false
KWRC
echo "--password-store=kwallet6" > /home/$USUARIO/.config/brave-flags.conf
cat > /home/$USUARIO/.config/autostart/configurar-carteira.desktop <<'AUTOSTART'
[Desktop Entry]
Type=Application
Name=Configurar carteira KDE
Exec=/usr/local/bin/configurar-carteira
AUTOSTART
chown -R $USUARIO:$USUARIO /home/$USUARIO/.config

# zram (swap na memória)
cat > /etc/systemd/zram-generator.conf <<ZRAM
[zram0]
zram-size = ram / 2
compression-algorithm = zstd
ZRAM

# NVIDIA carregando cedo (necessário pro Wayland)
sed -i 's/^MODULES=()/MODULES=(nvidia nvidia_modeset nvidia_uvm nvidia_drm)/' /etc/mkinitcpio.conf
mkinitcpio -P

# Bootloader systemd-boot
bootctl install
cat > /boot/loader/loader.conf <<LOADER
default arch.conf
timeout 3
console-mode max
editor no
LOADER
cat > /boot/loader/entries/arch.conf <<ENTRY
title   Arch Linux
linux   /vmlinuz-linux
initrd  /$UCODE_INITRD
initrd  /initramfs-linux.img
options root=UUID=$UUID_RAIZ rw nvidia_drm.modeset=1 nvidia_drm.fb_modeset=1
ENTRY

# SDDM em Wayland, sessão padrão Plasma (Wayland)
mkdir -p /etc/sddm.conf.d /var/lib/sddm
cat > /etc/sddm.conf.d/10-wayland.conf <<SDDM
[General]
DisplayServer=wayland
GreeterEnvironment=QT_WAYLAND_SHELL_INTEGRATION=layer-shell

[Wayland]
CompositorCommand=kwin_wayland --drm --no-lockscreen --no-global-shortcuts --locale1

[Theme]
Current=breeze
CursorTheme=breeze_cursors
SDDM
cat > /var/lib/sddm/state.conf <<ESTADO
[Last]
Session=/usr/share/wayland-sessions/plasma.desktop
ESTADO

# Steam, Discord e Shotcut (repositórios oficiais, multilib incluso)
pacman -Syu --noconfirm lib32-nvidia-utils lib32-vulkan-icd-loader vulkan-icd-loader
pacman -S --noconfirm steam discord shotcut

# Flatpak + Flathub
flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo || true

# AUR: yay
echo "$USUARIO ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/99-temp-yay
chmod 440 /etc/sudoers.d/99-temp-yay
runuser -l $USUARIO -c 'git clone https://aur.archlinux.org/yay-bin.git /tmp/yay-bin && cd /tmp/yay-bin && makepkg -si --noconfirm' || echo "Aviso: falha ao instalar o yay, instale depois manualmente."

# Brave (AUR)
runuser -l $USUARIO -c 'yay -S --noconfirm brave-bin' || echo "Aviso: falha ao instalar o Brave, instale depois com: yay -S brave-bin"

# GPU Screen Recorder com interface estilo ShadowPlay (AUR)
runuser -l $USUARIO -c 'yay -S --noconfirm gpu-screen-recorder gpu-screen-recorder-gtk' || echo "Aviso: falha ao instalar o GPU Screen Recorder, instale depois com: yay -S gpu-screen-recorder gpu-screen-recorder-gtk"

# Digital Vibrance para NVIDIA no Wayland (nvibrant, AUR)
runuser -l $USUARIO -c 'yay -S --noconfirm nvibrant-bin' || echo "Aviso: falha ao instalar o nvibrant, instale depois com: yay -S nvibrant-bin"

# Driver Wi-Fi Broadcom (só se detectado)
if [[ "$BROADCOM" == "1" ]]; then
  runuser -l $USUARIO -c 'yay -S --noconfirm broadcom-wl-dkms' || echo "Aviso: falha ao instalar o driver Broadcom, instale depois com: yay -S broadcom-wl-dkms"
fi
rm -f /etc/sudoers.d/99-temp-yay

# Início automático no KDE: Digital Vibrance, Steam e Discord
mkdir -p /home/$USUARIO/.local/bin /home/$USUARIO/.config/autostart
cat > /home/$USUARIO/.local/bin/DigitalVibrance.sh <<'VIBRANCE'
#!/bin/bash
nvibrant 1023 1023 1023 1023 1023 1023
VIBRANCE
chmod +x /home/$USUARIO/.local/bin/DigitalVibrance.sh
cat > /home/$USUARIO/.config/autostart/digital-vibrance.desktop <<'AUTO1'
[Desktop Entry]
Type=Application
Name=Digital Vibrance
Exec=/home/$USUARIO/.local/bin/DigitalVibrance.sh
AUTO1
cat > /home/$USUARIO/.config/autostart/steam.desktop <<'AUTO2'
[Desktop Entry]
Type=Application
Name=Steam
Exec=steam -silent
AUTO2
cat > /home/$USUARIO/.config/autostart/discord.desktop <<'AUTO3'
[Desktop Entry]
Type=Application
Name=Discord
Exec=discord --start-minimized
AUTO3
chown -R $USUARIO:$USUARIO /home/$USUARIO/.local /home/$USUARIO/.config

# Serviços
systemctl enable NetworkManager sddm bluetooth fstrim.timer systemd-timesyncd
EOF

# Senhas (fora do heredoc para não quebrar com caracteres especiais)
printf '%s:%s\n' "$USUARIO" "$SENHA" | arch-chroot /mnt chpasswd
printf '%s:%s\n' "root" "$SENHA" | arch-chroot /mnt chpasswd

# Pastas do usuário em português (Documentos, Downloads, etc.)
arch-chroot /mnt runuser -u "$USUARIO" -- env LANG="$LOCALE" xdg-user-dirs-update || true

echo
echo "=========================================================="
echo " Instalação concluída!"
echo " Remova o pendrive e digite: reboot"
echo "=========================================================="
