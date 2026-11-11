#!/usr/bin/bash
# Shared by clean installation and the existing-system migration.
set -Eeuo pipefail
export PATH=/usr/bin:/bin
umask 077
(( EUID == 0 )) || { echo 'Requer root.' >&2; exit 1; }
usuario=${SUDO_USER:-${1:-}}
[[ -n $usuario && $usuario != root ]] && id "$usuario" >/dev/null || exit 1
stage=${CALLAS_RELEASE_DIR:?Arquivos de atualização não preparados}
[[ -d $stage && ! -L $stage && $(stat -c %u "$stage") == 0 ]] || exit 1
for name in callas-version.py callas-nekofetch.sh callas-release.py callas-logs.py callas-kernel-check.sh put-update.sh callas-aur.py callas-storage.py callas-maintenance.py callas-native.py; do
  [[ -f $stage/$name && ! -L $stage/$name && $(stat -c %u "$stage/$name") == 0 ]] || {
    echo "Arquivo verificado ausente/inseguro: $name" >&2; exit 1;
  }
done
install -d -m 0755 /etc/callas-os /usr/local/libexec /etc/pacman.d/hooks
install -d -m 0700 /var/log/callas-os
if [[ ! -f /etc/callas-os/maintenance.ini ]]; then
  cat > /etc/callas-os/maintenance.ini <<'POLICY'
[Backups]
limit_bytes = 1000000000
copies_per_type = 3
POLICY
  chmod 0644 /etc/callas-os/maintenance.ini
fi

# Back up before any settings are changed. Files stay root-only in Documents.
python "$stage/callas-storage.py" --migrate "$usuario"
python "$stage/callas-storage.py" --security "$usuario"

# No lingering passwordless pacman access, even after an interrupted old update.
rm -f /etc/sudoers.d/put-update /etc/sudoers.d/99-callas-instalacao
rm -f /etc/put-update-aur.sudoers /etc/put-update-paru.conf
for name in callas-version.py callas-nekofetch.sh callas-release.py callas-logs.py callas-kernel-check.sh put-update.sh callas-aur.py callas-storage.py callas-maintenance.py callas-native.py; do
  source_file="$stage/$name"
  [[ -f $source_file && ! -L $source_file && $(stat -c %u "$source_file") == 0 ]] || exit 1
  case $name in
    callas-version.py) target=callas-version ;;
    callas-nekofetch.sh) target=callas-nekofetch ;;
    callas-release.py) target=callas-release ;;
    callas-logs.py) target=callas-logs ;;
    callas-kernel-check.sh) target=callas-kernel-check ;;
    put-update.sh) target=put-update ;;
    callas-aur.py) target=callas-aur ;;
    callas-storage.py) target=callas-storage ;;
    callas-maintenance.py) target=callas-maintenance ;;
    callas-native.py) target=callas-native ;;
  esac
  install -o root -g root -m 0755 "$source_file" "/usr/local/libexec/$target"
done
printf '%s\n' "$usuario" > /etc/callas-os/log-user
printf '%s\n' "${CALLAS_RELEASE_REF:-installation}" > /etc/callas-os/security-release

logdir=$(mktemp -d /var/tmp/callas-security.XXXXXXXX)
finish() {
  local code=$?
  trap - EXIT
  exec 1>&3 2>&4
  wait "$logpid" || :
  /usr/local/libexec/callas-logs --record 'Seguranca e Firewall' < "$logdir/security.log" || :
  /usr/local/libexec/callas-logs --export "$usuario" || :
  rm -rf -- "$logdir"
  exit "$code"
}
exec 3>&1 4>&2
exec > >(tee "$logdir/security.log") 2>&1
logpid=$!
trap finish EXIT
# Process substitution preserves live progress without a pipeline subshell.
seguranca() {
  printf 'Segurança do Callas OS: %s\n' "$(date -Is)"
  # Preserve local-package policy for reviewed AUR packages; require trusted
  # signatures on repository packages, including old per-repository overrides.
  python - <<'PY'
from pathlib import Path
p = Path('/etc/pacman.conf')
lines = p.read_text().splitlines()
out, options, done = [], False, False
for line in lines:
    if line.strip().startswith('['):
        if options and not done:
            out.append('SigLevel = Required DatabaseOptional')
            done = True
        options = line.strip() == '[options]'
    if line.lstrip().startswith('SigLevel') and '=' in line:
        if not done:
            out.append('SigLevel = Required DatabaseOptional')
            done = True
        continue
    out.append(line)
if options and not done:
    out.append('SigLevel = Required DatabaseOptional')
p.write_text('\n'.join(out) + '\n')
PY
  nvidia_before=$(pacman -Q nvidia-utils nvidia-open-dkms lib32-nvidia-utils nvidia-settings libxnvctrl 2>/dev/null || :)
  if [[ -n $nvidia_before ]]; then
    if [[ ! -f /etc/callas-nvidia-version ]]; then
      pacman -Q nvidia-utils | awk '{sub(/-[^-]*$/, "", $2); print $2}' > /etc/callas-nvidia-version
    fi
    # Keep the existing driver, even if this machine predates the marker file.
    sed -i '/^# CALLAS_NVIDIA_610_BEGIN$/,/^# CALLAS_NVIDIA_610_END$/d' /etc/pacman.conf
    sed -i '/^\[options\]$/a # CALLAS_NVIDIA_610_BEGIN\nIgnorePkg = nvidia-utils nvidia-open-dkms nvidia-open nvidia-open-lts lib32-nvidia-utils nvidia-settings libxnvctrl opencl-nvidia lib32-opencl-nvidia\n# CALLAS_NVIDIA_610_END' /etc/pacman.conf
  fi
  # Apply the signature policy before the first network transaction.
  if [[ ${2:-} != --installation ]]; then
    mountpoint -q /boot || { echo '/boot não está montado; pacman não foi executado.' >&2; return 1; }
    # Full upgrade, with the user-requested NVIDIA hold kept intact.
    pacman -Syu --needed --noconfirm \
      --ignore=nvidia-utils,nvidia-open-dkms,nvidia-open,nvidia-open-lts,lib32-nvidia-utils,nvidia-settings,libxnvctrl,opencl-nvidia,lib32-opencl-nvidia \
      linux linux-lts linux-headers linux-lts-headers ufw plasma-firewall python python-dbus python-gobject kscreen base-devel git rebuild-detector pacman-contrib
  fi
  nvidia_after=$(pacman -Q nvidia-utils nvidia-open-dkms lib32-nvidia-utils nvidia-settings libxnvctrl 2>/dev/null || :)
  [[ $nvidia_before == "$nvidia_after" ]] || { echo 'A pilha NVIDIA mudou inesperadamente.' >&2; return 1; }

  cat > /etc/sudoers.d/20-callas-security <<'SUDO'
Defaults use_pty
Defaults timestamp_timeout=5
SUDO
  chmod 0440 /etc/sudoers.d/20-callas-security
  visudo -cf /etc/sudoers.d/20-callas-security

  cat > /etc/sysctl.d/60-callas-security.conf <<'SYSCTL'
fs.protected_hardlinks = 1
fs.protected_symlinks = 1
fs.protected_fifos = 2
fs.protected_regular = 2
kernel.kptr_restrict = 2
kernel.dmesg_restrict = 1
SYSCTL
  if ! systemd-detect-virt --chroot >/dev/null; then
    sysctl -p /etc/sysctl.d/60-callas-security.conf
  fi

  # Keep another configured firewall rather than install competing live rules.
  if systemctl is-active --quiet firewalld || systemctl is-active --quiet nftables; then
    printf 'Outro firewall ativo: regras existentes preservadas; UFW não ativado.\n'
  elif [[ -n ${SSH_CONNECTION:-} ]]; then
    printf 'Sessão SSH detectada: ativação do UFW pendente de revisão local.\n'
  else
    sed -i 's/^IPV6=.*/IPV6=yes/' /etc/default/ufw
    ufw default deny incoming
    ufw default allow outgoing
    ufw logging low
    if ! grep -q '^ENABLED=yes' /etc/ufw/ufw.conf; then
      if systemd-detect-virt --chroot >/dev/null; then
        sed -i 's/^ENABLED=.*/ENABLED=yes/' /etc/ufw/ufw.conf
      else
        ufw --force enable
      fi
    elif ! systemd-detect-virt --chroot >/dev/null; then
      ufw reload
    fi
    systemctl enable ufw
    printf 'UFW configurado; IPv4 e IPv6, entrada bloqueada por padrão.\n'
  fi

  # No server is enabled by this migration. If SSH is installed, disallow root.
  if [[ -d /etc/ssh/sshd_config.d ]]; then
    printf 'PermitRootLogin no\n' > /etc/ssh/sshd_config.d/00-callas-no-root.conf
    if command -v sshd >/dev/null; then
      sshd -t
      if systemctl is-active --quiet sshd; then systemctl reload sshd; fi
    fi
  fi

  if [[ -f /etc/systemd/system/risemode-driver.service ]]; then
    id callas-hw >/dev/null 2>&1 || useradd --system --user-group --no-create-home --shell /usr/bin/nologin callas-hw
    install -d -m 0755 /etc/systemd/system/risemode-driver.service.d
    cat > /etc/systemd/system/risemode-driver.service.d/security.conf <<'HARDWARE'
[Service]
User=callas-hw
Group=callas-hw
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
RestrictSUIDSGID=true
HARDWARE
    cat > /etc/udev/rules.d/99-risemode.rules <<'UDEV'
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="aa88", ATTRS{idProduct}=="8666", GROUP="callas-hw", MODE="0660", TAG+="uaccess"
SUBSYSTEM=="usb", ATTRS{idVendor}=="aa88", ATTRS{idProduct}=="8666", GROUP="callas-hw", MODE="0660", TAG+="uaccess"
UDEV
    if ! systemd-detect-virt --chroot >/dev/null; then
      systemctl daemon-reload
      udevadm control --reload-rules
      udevadm trigger --subsystem-match=hidraw
      if systemctl is-active --quiet risemode-driver; then systemctl restart risemode-driver; fi
    fi
  fi

  cat > /etc/pacman.d/hooks/99-zz-callas-kernels.hook <<'HOOK'
[Trigger]
Operation = Install
Operation = Upgrade
Type = Package
Target = linux
Target = linux-lts
Target = linux-headers
Target = linux-lts-headers
Target = nvidia-open-dkms
Target = nvidia-utils
Target = lib32-nvidia-utils
Target = xone-dkms

[Action]
Description = Validar kernels padrão/LTS, DKMS e boot; guardar logs Callas OS
When = PostTransaction
Exec = /usr/local/libexec/callas-kernel-check
HOOK

  if ! id callas-aur >/dev/null 2>&1; then
    useradd --system --user-group --no-create-home --home-dir /var/empty/callas-aur --shell /usr/bin/nologin callas-aur
  fi
  [[ $(getent passwd callas-aur | cut -d: -f6-7) == /var/empty/callas-aur:/usr/bin/nologin ]] || {
    echo 'A conta callas-aur já existe com uma configuração inesperada.' >&2; return 1;
  }
  [[ $(id -nG callas-aur) == callas-aur ]] || { echo 'Grupos da conta de compilação inesperados.' >&2; return 1; }

  cat > /etc/systemd/system/callas-maintenance.service <<UNIT
[Unit]
Description=Limpeza conservadora e rotação dos backups Callas OS
[Service]
Type=oneshot
ExecStart=/usr/local/libexec/callas-maintenance --clean $usuario
Nice=10
IOSchedulingClass=idle
NoNewPrivileges=true
UNIT
  cat > /etc/systemd/system/callas-maintenance.timer <<'TIMER'
[Unit]
Description=Manutenção automática diária do Callas OS
[Timer]
OnBootSec=15min
OnUnitInactiveSec=1d
Unit=callas-maintenance.service
[Install]
WantedBy=timers.target
TIMER
  if systemd-detect-virt --chroot >/dev/null; then
    systemctl --root=/ enable callas-maintenance.timer
  else
    systemctl daemon-reload
    systemctl enable --now callas-maintenance.timer
  fi

  /usr/local/libexec/put-update --instalar-para "$usuario"
  /usr/local/libexec/callas-kernel-check
  printf '%s\n' '2026.11.11.security3' > /etc/callas-os/security-version
  printf 'Segurança aplicada. NVIDIA e senhas preservadas.\n'
}
# Do not place this function in an if/|| condition: Bash would suppress
# errexit for every command inside it and allow a failed transaction to continue.
seguranca "$@"
