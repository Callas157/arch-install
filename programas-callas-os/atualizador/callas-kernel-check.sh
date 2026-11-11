#!/usr/bin/bash
set -Eeuo pipefail
export PATH=/usr/bin:/bin
(( EUID == 0 )) || exit 1
umask 077
stage=$(mktemp -d /var/tmp/callas-kernel.XXXXXXXX)
trap 'rm -rf -- "$stage"' EXIT
status=0
{
  printf 'Verificação de kernel/boot: %s\n' "$(date -Is)"
  if ! mountpoint -q /boot; then
    printf 'ERRO: a partição /boot não está montada. Não gerar arquivos no local errado.\n'
    install -d -m 0755 /var/lib/callas-os
    touch /var/lib/callas-os/kernel-check-failed
    /usr/local/libexec/callas-logs --record 'Kernel Linux' <<< 'FALHA: /boot não está montado; verificação interrompida.'
    exit 1
  fi
  pacman -Q linux linux-lts linux-headers linux-lts-headers || status=1
  if [[ -r /etc/callas-nvidia-version ]]; then
    printf 'NVIDIA preservada na versão: %s\n' "$(< /etc/callas-nvidia-version)"
    pacman -Q nvidia-open-dkms nvidia-utils lib32-nvidia-utils || status=1
  fi
  if command -v dkms >/dev/null; then
    dkms autoinstall || status=1
  fi
  for kernel in linux linux-lts; do
    found=0
    for pkgbase in /usr/lib/modules/*/pkgbase; do
      [[ -f $pkgbase && $(< "$pkgbase") == "$kernel" ]] || continue
      found=1
      release=${pkgbase%/pkgbase}; release=${release##*/}
      printf '%s: %s\n' "$kernel" "$release"
      [[ -s /usr/lib/modules/$release/vmlinuz ]] || status=1
      if [[ -r /etc/callas-nvidia-version ]]; then
        modinfo -k "$release" nvidia >/dev/null || status=1
      fi
      if pacman -Qq xone-dkms >/dev/null 2>&1; then
        modinfo -k "$release" xone-dongle >/dev/null || status=1
      fi
    done
    (( found )) || status=1
  done
  mkinitcpio -P || status=1
  for kernel in linux linux-lts; do
    [[ -s /boot/initramfs-$kernel.img ]] || status=1
    [[ -s /boot/vmlinuz-$kernel ]] || status=1
  done
  if [[ -x /usr/local/libexec/callas-grub-custom ]]; then
    /usr/local/libexec/callas-grub-custom || status=1
  elif [[ -f /boot/grub/grub.cfg ]]; then
    temp_grub=$(mktemp /boot/grub/.callas-check.XXXXXXXX)
    if grub-mkconfig -o "$temp_grub" && grub-script-check "$temp_grub" &&
        grep -q 'menuentry ' "$temp_grub"; then
      chmod 0600 "$temp_grub"
      mv -f -- "$temp_grub" /boot/grub/grub.cfg
    else
      rm -f -- "$temp_grub"
      status=1
    fi
  fi
  if [[ -f /boot/grub/grub.cfg ]]; then
    grub-script-check /boot/grub/grub.cfg || status=1
    grep -q 'vmlinuz-linux-lts' /boot/grub/grub.cfg || status=1
    grep -q 'vmlinuz-linux' /boot/grub/grub.cfg || status=1
  else
    status=1
  fi
  if (( status )); then
    printf 'FALHA: verifique este log antes de reiniciar.\n'
    install -d -m 0755 /var/lib/callas-os
    touch /var/lib/callas-os/kernel-check-failed
  else
    rm -f /var/lib/callas-os/kernel-check-failed
    printf 'Kernels padrão e LTS, initramfs e boot verificados.\n'
  fi
} > "$stage/kernel.log" 2>&1
cat "$stage/kernel.log"
/usr/local/libexec/callas-logs --record 'Kernel Linux' < "$stage/kernel.log"
if [[ -r /etc/callas-nvidia-version ]]; then
  /usr/local/libexec/callas-logs --record 'Driver NVIDIA' < "$stage/kernel.log"
fi
if [[ -r /etc/callas-os/log-user ]]; then
  read -r log_user < /etc/callas-os/log-user
  /usr/local/libexec/callas-logs --export "$log_user" || printf 'Não consegui exportar logs para Documentos.\n' >&2
fi
exit "$status"
