#!/usr/bin/bash
set -Eeuo pipefail
export PATH=/usr/bin:/bin
(( EUID == 0 )) || exit 1
umask 077
stage=$(mktemp -d /var/tmp/callas-kernel.XXXXXXXX)
status=0
exec 3>&1 4>&2
# Keep diagnostics even when an unexpected command aborts the check. The
# root-only last log also survives a failure of the normal log exporter.
finish() {
  local code=$?
  trap - EXIT ERR
  set +e
  exec 1>&3 2>&4
  (( code == 0 )) || status=$code
  install -d -m 0755 /var/lib/callas-os
  install -m 0600 "$stage/kernel.log" /var/lib/callas-os/kernel-check-last.log || status=1
  cat "$stage/kernel.log"
  /usr/local/libexec/callas-logs --record 'Kernel Linux' < "$stage/kernel.log" || status=1
  if [[ -r /etc/callas-nvidia-version ]]; then
    /usr/local/libexec/callas-logs --record 'Driver NVIDIA' < "$stage/kernel.log" || status=1
  fi
  if (( status )); then
    touch /var/lib/callas-os/kernel-check-failed
    printf 'FALHA: consulte o motivo acima ou /var/lib/callas-os/kernel-check-last.log. Não reinicie antes de corrigir.\n' >&2
  else
    rm -f /var/lib/callas-os/kernel-check-failed
  fi
  if [[ -r /etc/callas-os/log-user ]]; then
    read -r log_user < /etc/callas-os/log-user
    /usr/local/libexec/callas-logs --export "$log_user" || printf 'Não consegui exportar logs para Documentos.\n' >&2
  fi
  rm -rf -- "$stage"
  exit "$status"
}
trap finish EXIT
trap 'code=$?; printf "ERRO: checagem de kernel interrompida na linha %s (código %s).\n" "$LINENO" "$code" >&2; exit "$code"' ERR
falha() {
  status=1
  printf 'ERRO: %s\n' "$*" >&2
}
{
  printf 'Verificação de kernel/boot: %s\n' "$(date -Is)"
  if ! mountpoint -q /boot; then
    falha '/boot não está montado; nenhuma imagem ou configuração de boot foi alterada.'
    exit 1
  fi
  pacman -Q linux linux-lts linux-headers linux-lts-headers || falha 'Pacote de kernel ou headers obrigatório ausente.'
  if [[ -r /etc/callas-nvidia-version ]]; then
    printf 'NVIDIA preservada na versão: %s\n' "$(< /etc/callas-nvidia-version)"
    pacman -Q nvidia-open-dkms nvidia-utils lib32-nvidia-utils || falha 'A pilha NVIDIA está incompleta.'
  fi
  for kernel in linux linux-lts; do
    found=0
    for pkgbase in /usr/lib/modules/*/pkgbase; do
      [[ -f $pkgbase && $(< "$pkgbase") == "$kernel" ]] || continue
      found=1
      release=${pkgbase%/pkgbase}; release=${release##*/}
      printf '%s: %s\n' "$kernel" "$release"
      [[ -s /usr/lib/modules/$release/vmlinuz ]] || falha "Imagem do kernel $kernel ($release) ausente em /usr/lib/modules."
      # uname reports the ISO kernel inside arch-chroot, and the old running
      # kernel after an upgrade. Always target the installed releases explicitly.
      if command -v dkms >/dev/null; then
        dkms autoinstall -k "$release" || falha "DKMS não conseguiu preparar os módulos para $kernel ($release)."
      fi
      if [[ -r /etc/callas-nvidia-version ]]; then
        modinfo -k "$release" nvidia >/dev/null || falha "Módulo NVIDIA ausente para $kernel ($release)."
      fi
      if pacman -Qq xone-dkms >/dev/null 2>&1; then
        modinfo -k "$release" xone-dongle >/dev/null || falha "Módulo xone ausente para $kernel ($release)."
      fi
    done
    (( found )) || falha "Não encontrei o kernel instalado $kernel em /usr/lib/modules."
  done
  mkinitcpio -P || falha 'Falha ao gerar initramfs com mkinitcpio.'
  for kernel in linux linux-lts; do
    [[ -s /boot/initramfs-$kernel.img ]] || falha "Initramfs de $kernel ausente ou vazio em /boot."
    [[ -s /boot/vmlinuz-$kernel ]] || falha "Imagem de $kernel ausente ou vazia em /boot."
  done
  if [[ -x /usr/local/libexec/callas-grub-custom ]]; then
    /usr/local/libexec/callas-grub-custom || falha 'Falha ao gerar ou validar o GRUB Callas OS.'
  elif [[ -f /boot/grub/grub.cfg ]]; then
    temp_grub=$(mktemp /boot/grub/.callas-check.XXXXXXXX)
    if grub-mkconfig -o "$temp_grub" && grub-script-check "$temp_grub" &&
        grep -q 'menuentry ' "$temp_grub" &&
        grep -Eq '(^|[[:space:]/])vmlinuz-linux([[:space:]]|$)' "$temp_grub" &&
        grep -Eq '(^|[[:space:]/])vmlinuz-linux-lts([[:space:]]|$)' "$temp_grub"; then
      chmod 0600 "$temp_grub"
      mv -f -- "$temp_grub" /boot/grub/grub.cfg
    else
      rm -f -- "$temp_grub"
      falha 'GRUB gerado inválido ou sem os dois kernels; configuração anterior preservada.'
    fi
  fi
  if [[ -f /boot/grub/grub.cfg ]]; then
    grub-script-check /boot/grub/grub.cfg || falha 'Sintaxe inválida em /boot/grub/grub.cfg.'
    grep -Eq '(^|[[:space:]/])vmlinuz-linux-lts([[:space:]]|$)' /boot/grub/grub.cfg || falha 'Entrada do kernel LTS ausente no GRUB.'
    grep -Eq '(^|[[:space:]/])vmlinuz-linux([[:space:]]|$)' /boot/grub/grub.cfg || falha 'Entrada do kernel padrão ausente no GRUB.'
  else
    falha '/boot/grub/grub.cfg não existe.'
  fi
  if (( status == 0 )); then
    printf 'Kernels padrão e LTS, initramfs e boot verificados.\n'
  fi
} > "$stage/kernel.log" 2>&1
exit "$status"
