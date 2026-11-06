#!/usr/bin/env bash
# =====================================================================
# Instalação automática do Arch Linux
# KDE Plasma (Wayland) + SDDM | pt-BR | UEFI | systemd-boot | ext4
# NVIDIA RTX 3060 | Ryzen 5 5700X | SSD NVMe 1 TB (único disco)
# Teclado: EUA Internacional | Steam, Discord, AUR (yay), Flatpak
#
# ATENÇÃO: APAGA TODO O DISCO /dev/nvme0n1
# Rodar na ISO do Arch Linux, com internet por cabo.
# =====================================================================
set -euo pipefail

# ---------------- Configurações ----------------
DISCO="/dev/nvme0n1"
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

if [[ ! -b "$DISCO" ]]; then
  echo "ERRO: disco $DISCO não encontrado. Discos disponíveis:"; lsblk -d -o NAME,SIZE,MODEL; exit 1
fi

if ! ping -c 1 -W 5 archlinux.org &>/dev/null; then
  echo "ERRO: sem internet. Confira o cabo de rede."; exit 1
fi

loadkeys "$TECLADO" || true

echo
echo "=========================================================="
echo " O disco abaixo será TOTALMENTE APAGADO:"
lsblk -o NAME,SIZE,MODEL,FSTYPE "$DISCO"
echo "=========================================================="
read -rp "Digite SIM para continuar: " CONFIRMA
[[ "$CONFIRMA" == "SIM" ]] || { echo "Cancelado."; exit 1; }

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

EFI="${DISCO}p1"
RAIZ="${DISCO}p2"

mkfs.fat -F32 "$EFI"
mkfs.ext4 -F "$RAIZ"

mount "$RAIZ" /mnt
mount --mkdir -o fmask=0077,dmask=0077 "$EFI" /mnt/boot

# ---------------- Instalação base ----------------
echo ">>> Instalando pacotes (isso demora)"
pacstrap -K /mnt \
  base linux linux-firmware amd-ucode base-devel sudo nano git \
  networkmanager \
  plasma-desktop sddm sddm-kcm plasma-nm plasma-pa kscreen powerdevil \
  konsole dolphin kate ark gwenview okular spectacle kdeplasma-addons \
  xdg-desktop-portal-kde xdg-user-dirs \
  pipewire pipewire-alsa pipewire-pulse wireplumber \
  bluez bluez-utils \
  nvidia-open nvidia-utils nvidia-settings egl-wayland \
  noto-fonts noto-fonts-emoji ttf-dejavu ttf-liberation \
  firefox firefox-i18n-pt-br hunspell-pt-br \
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
initrd  /amd-ucode.img
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
SDDM
cat > /var/lib/sddm/state.conf <<ESTADO
[Last]
Session=/usr/share/wayland-sessions/plasma.desktop
ESTADO

# Steam e Discord (repositórios oficiais, multilib incluso)
pacman -Syu --noconfirm lib32-nvidia-utils lib32-vulkan-icd-loader vulkan-icd-loader
pacman -S --noconfirm steam discord

# Flatpak + Flathub
flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo || true

# AUR: yay
echo "$USUARIO ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/99-temp-yay
chmod 440 /etc/sudoers.d/99-temp-yay
runuser -l $USUARIO -c 'git clone https://aur.archlinux.org/yay-bin.git /tmp/yay-bin && cd /tmp/yay-bin && makepkg -si --noconfirm' || echo "Aviso: falha ao instalar o yay, instale depois manualmente."

# Brave (AUR)
runuser -l $USUARIO -c 'yay -S --noconfirm brave-bin' || echo "Aviso: falha ao instalar o Brave, instale depois com: yay -S brave-bin"
rm -f /etc/sudoers.d/99-temp-yay

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
