#!/usr/bin/env bash
set -Eeuo pipefail

VERSAO="2026.11.10.1"
BASE_RAW="https://raw.githubusercontent.com/Callas157/arch-install/main"
ASSET_BASE="$BASE_RAW/assets"
ESTADO_DIR="/var/lib/callas-os"
VERSAO_ARQ="$ESTADO_DIR/config-version"
BACKUP_DIR="$ESTADO_DIR/config-backups"

erro(){ printf 'Erro: %s\n' "$*" >&2; exit 1; }
aviso(){ printf 'Aviso: %s\n' "$*" >&2; }

[[ ${EUID} -eq 0 ]] || erro "Execute este script com sudo."
usuario=${SUDO_USER:-${1:-}}
[[ -n "$usuario" && "$usuario" != root ]] || erro "Não consegui identificar o usuário da sessão."
home=$(getent passwd "$usuario" | cut -d: -f6)
grupo=$(id -gn "$usuario")
[[ -d "$home" ]] || erro "Pasta pessoal de $usuario não encontrada."
[[ -f /etc/arch-release ]] || erro "Este atualizador foi preparado para Arch Linux."

como_usuario() {
  runuser -u "$usuario" -- env -i PATH=/usr/bin:/bin HOME="$home" USER="$usuario" LOGNAME="$usuario" LANG=C.UTF-8 "$@"
}

install -d -m 0755 "$ESTADO_DIR" "$BACKUP_DIR"
atual=0
[[ -r "$VERSAO_ARQ" ]] && atual=$(<"$VERSAO_ARQ")
if [[ "$atual" == "$VERSAO" ]]; then
  printf 'Configurações do Callas OS já estão na versão %s.\n' "$VERSAO"
  exit 0
fi

stamp=$(date +%Y%m%d-%H%M%S)
backup="$BACKUP_DIR/$stamp"
install -d -m 0700 "$backup"
for arq in   "$home/.config/powerdevilrc"   "$home/.config/ksmserverrc"   /etc/xdg/kicker-extra-favoritesrc   /etc/xdg/autostart/callas-limpar-atalhos-desktop.desktop; do
  [[ -f "$arq" ]] || continue
  nome=$(printf '%s' "$arq" | sed 's#^/##; s#/#__#g')
  cp -a -- "$arq" "$backup/$nome"
done
chown -R "$usuario:$grupo" "$backup" 2>/dev/null || true

# Flatpaks padrão do Callas OS.
if command -v flatpak >/dev/null; then
  flatpak remote-add --system --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo || :
  for app in com.vysp3r.ProtonPlus io.github.kolunmi.Bazaar io.missioncenter.MissionCenter; do
    flatpak install --system --noninteractive --assumeyes flathub "$app" ||
      aviso "Não consegui instalar/confirmar $app."
  done
fi

# Coleção atual de wallpapers do Callas OS.
wallpapers=(
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
for wallpaper in "${wallpapers[@]}"; do
  id="CallasOS-${wallpaper%.jpg}"
  destino="/usr/share/wallpapers/$id"
  install -d "$destino/contents/images"
  curl -fsSL --retry 2 "$ASSET_BASE/wallpapers/$wallpaper" -o "$destino/contents/images/1920x1080.jpg" ||
    aviso "Falha ao atualizar wallpaper $wallpaper."
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

# Favoritos padrão do Kickoff.
install -d /etc/xdg
cat > /etc/xdg/kicker-extra-favoritesrc <<'EOF'
[General]
IgnoreDefaults=true
Prepend=systemsettings.desktop;io.github.Callas157.AtualizadorDoSistema.desktop;steam.desktop;org.kde.konsole.desktop;io.github.kolunmi.Bazaar.desktop;com.vysp3r.ProtonPlus.desktop;io.missioncenter.MissionCenter.desktop;org.qbittorrent.qBittorrent.desktop;spotify.desktop;solaar.desktop;
EOF

# Energia: sem suspensão, escurecimento ou desligamento automático de tela.
if command -v kwriteconfig6 >/dev/null; then
  for perfil in AC Battery LowBattery; do
    como_usuario kwriteconfig6 --file powerdevilrc --group "$perfil" --group Display --key DimDisplayWhenIdle false || :
    como_usuario kwriteconfig6 --file powerdevilrc --group "$perfil" --group Display --key TurnOffDisplayWhenIdle false || :
    como_usuario kwriteconfig6 --file powerdevilrc --group "$perfil" --group SuspendAndShutdown --key AutoSuspendAction 0 || :
  done
fi

# Remove somente atalhos automáticos indesejados da Área de Trabalho.
cat > /usr/local/libexec/callas-limpar-atalhos-desktop <<'EOF'
#!/usr/bin/env bash
set -u
desktop=$(xdg-user-dir DESKTOP 2>/dev/null || true)
[[ $desktop == /* ]] || desktop="$HOME/Desktop"
for _ in {1..6}; do
  if [[ -d $desktop ]]; then
    find "$desktop" -maxdepth 1 -type f \(       -iname '*ixin*.desktop' -o       -iname '*ixlauncher*.desktop' -o       -iname 'steam.desktop' -o       -iname 'com.valvesoftware.Steam.desktop'     \) -delete 2>/dev/null || true
  fi
  sleep 10
done
EOF
chmod 0755 /usr/local/libexec/callas-limpar-atalhos-desktop
install -d /etc/xdg/autostart
cat > /etc/xdg/autostart/callas-limpar-atalhos-desktop.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=Limpar atalhos automáticos da área de trabalho
Exec=/usr/local/libexec/callas-limpar-atalhos-desktop
OnlyShowIn=KDE;
NoDisplay=true
StartupNotify=false
EOF

# Reaplica somente os ajustes seguros de sessão já existentes na instalação.
if [[ -x /usr/local/libexec/callas-inicio-kde ]]; then
  como_usuario /usr/local/libexec/callas-inicio-kde || aviso "Alguns ajustes de sessão KDE não puderam ser reaplicados."
fi
if [[ -x /usr/local/libexec/callas-nekofetch ]]; then
  como_usuario /usr/local/libexec/callas-nekofetch || aviso "O Nekofetch não pôde ser atualizado."
fi

printf '%s\n' "$VERSAO" > "$VERSAO_ARQ"

# Conserva apenas os três backups mais recentes.
mapfile -t antigos < <(find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort -r)
if (( ${#antigos[@]} > 3 )); then
  for antigo in "${antigos[@]:3}"; do rm -rf -- "$BACKUP_DIR/$antigo"; done
fi

printf '\nConfigurações do Callas OS atualizadas para %s.\n' "$VERSAO"
printf 'Backup desta aplicação: %s\n' "$backup"
printf 'Algumas mudanças do KDE podem aparecer por completo após encerrar e iniciar a sessão.\n'
