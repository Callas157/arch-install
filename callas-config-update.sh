#!/usr/bin/env bash
set -Eeuo pipefail

VERSAO="2026.11.11.5"
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

# Compatibilidade de arquitetura do GRUB.
# O Callas Config atual só é suportado em instalações que já usam as entradas
# próprias do Callas OS. Instalações antigas, geradas pelo 10_linux padrão,
# são bloqueadas antes de qualquer alteração.
grub_compativel=0
if [[ -x /etc/grub.d/09_callas && -f /etc/grub.d/10_linux && ! -x /etc/grub.d/10_linux ]]; then
  grub_compativel=1
fi

if (( ! grub_compativel )); then
  cat >&2 <<'EOF'
ERRO: esta instalação do Callas OS usa uma arquitetura antiga do GRUB.

O Callas Config Update atual não será executado nesta máquina por segurança.
Nenhuma configuração foi alterada.

Para usar as atualizações atuais, faça uma instalação limpa com a versão
mais recente do instalar-arch.sh, que cria o GRUB personalizado do Callas OS.
EOF
  exit 42
fi

install -d -m 0755 /etc/callas-os
printf '%s\n' 'grub-custom-v2' > /etc/callas-os/grub-layout

como_usuario() {
  runuser -u "$usuario" -- env -i PATH=/usr/bin:/bin HOME="$home" USER="$usuario" LOGNAME="$usuario" LANG=C.UTF-8 "$@"
}

install -d -m 0755 "$ESTADO_DIR" "$BACKUP_DIR"
forcar=0
[[ ${1:-} == --force ]] && forcar=1

atual=0
[[ -r "$VERSAO_ARQ" ]] && atual=$(<"$VERSAO_ARQ")
if [[ "$atual" == "$VERSAO" && $forcar -eq 0 ]]; then
  printf 'Configurações do Callas OS já estão na versão %s.\n' "$VERSAO"
  printf '\nDeseja reaplicar esta mesma versão à força?\n'
  printf '1. Sim, reaplicar agora\n'
  printf '2. Não\n'
  read -r -p 'Escolha [1-2]: ' resposta_reaplicar || exit 0
  case $resposta_reaplicar in
    1) forcar=1 ;;
    2|"") exit 0 ;;
    *) printf 'Opção inválida. Nenhuma alteração foi feita.\n'; exit 0 ;;
  esac
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

# NVIDIA 610.57.04
# Só faz a migração pesada quando a pilha ainda não estiver correta.
if lspci -Dn 2>/dev/null | grep -qi '10de:'; then
  nvidia_ok=1
  for pkg in nvidia-utils nvidia-open-dkms lib32-nvidia-utils nvidia-settings libxnvctrl; do
    versao_pkg=$(pacman -Q "$pkg" 2>/dev/null | awk '{print $2}') || versao_pkg=
    [[ $versao_pkg == 610.57.04-* ]] || nvidia_ok=0
  done

  if (( ! nvidia_ok )); then
    nvidia_dir=/tmp/callas-nvidia-610
    rm -rf "$nvidia_dir"
    install -d "$nvidia_dir"

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
        erro "Não foi possível baixar ${url##*/} do Arch Linux Archive."
      curl -fL --retry 3 --connect-timeout 15 --max-time 60 "$url.sig" -o "$arquivo.sig" ||
        erro "Assinatura ausente para ${url##*/}."
      nvidia_pkgs+=("$arquivo")
    done

    remover=()
    pacman -Qq nvidia-open >/dev/null 2>&1 && remover+=(nvidia-open)
    pacman -Qq nvidia-open-lts >/dev/null 2>&1 && remover+=(nvidia-open-lts)
    (( ${#remover[@]} == 0 )) || pacman -R --noconfirm "${remover[@]}"

    pacman -U --noconfirm "${nvidia_pkgs[@]}" ||
      erro "Falha ao instalar a pilha NVIDIA 610.57.04."

    dkms autoinstall || erro "O DKMS não conseguiu preparar o NVIDIA 610 para os kernels instalados."
    mkinitcpio -P || erro "Falha ao reconstruir o initramfs após a migração NVIDIA."
    rm -rf "$nvidia_dir"
  else
    printf 'NVIDIA 610.57.04 já está instalada; pulando reinstalação do driver.\n'
  fi

  # Garante a trava mesmo quando o driver já estava correto.
  sed -i '/^# CALLAS_NVIDIA_610_BEGIN$/,/^# CALLAS_NVIDIA_610_END$/d' /etc/pacman.conf
  sed -i '/^\[options\]$/a # CALLAS_NVIDIA_610_BEGIN\nIgnorePkg = nvidia-utils nvidia-open-dkms nvidia-open nvidia-open-lts lib32-nvidia-utils nvidia-settings libxnvctrl opencl-nvidia lib32-opencl-nvidia\n# CALLAS_NVIDIA_610_END' /etc/pacman.conf
  printf '%s\n' '610.57.04' > /etc/callas-nvidia-version
fi

# GRUB: restaura apenas o tema estável do Callas OS.
# Não altera terminal-box nem tenta forçar transparência.
install -d /boot/grub/themes/callas

curl -fsSL --retry 2 "$ASSET_BASE/grub/theme.txt" \
  -o /boot/grub/themes/callas/theme.txt ||
  erro "Não consegui atualizar o tema do GRUB."
curl -fsSL --retry 2 "$ASSET_BASE/grub/background.png" \
  -o /boot/grub/themes/callas/background.png ||
  erro "Não consegui atualizar o wallpaper do GRUB."

rm -f /boot/grub/themes/callas/terminal_box_c.png
rm -f /usr/local/libexec/callas-grub-silencioso
rm -f /etc/pacman.d/hooks/99-callas-grub-silencioso.hook

cp -a /etc/default/grub "$backup/etc__default__grub" 2>/dev/null || true
cp -a /boot/grub/grub.cfg "$backup/boot__grub__grub.cfg" 2>/dev/null || true

grub_tmp=$(mktemp /boot/grub/.grub.cfg.callas.XXXXXX)
if grub-mkconfig -o "$grub_tmp" && [[ -s "$grub_tmp" ]] &&
   grep -q 'menuentry ' "$grub_tmp"; then
  chmod 0600 "$grub_tmp"
  mv -f "$grub_tmp" /boot/grub/grub.cfg
else
  rm -f "$grub_tmp"
  erro "Falha ao validar a configuração do GRUB; o grub.cfg anterior foi preservado."
fi

# Plymouth do Callas OS.
# Atualização segura: troca apenas os arquivos do tema e reconstrói o initramfs.
plymouth_dir=/usr/share/plymouth/themes/callas
install -d "$plymouth_dir"

curl -fsSL --retry 2 "$ASSET_BASE/plymouth/callas/callas.plymouth" \
  -o "$plymouth_dir/callas.plymouth" ||
  erro "Não consegui atualizar o arquivo do tema Plymouth."
curl -fsSL --retry 2 "$ASSET_BASE/plymouth/callas/callas.script" \
  -o "$plymouth_dir/callas.script" ||
  erro "Não consegui atualizar o script do Plymouth."
curl -fsSL --retry 2 "$ASSET_BASE/plymouth/callas/background.jpg" \
  -o "$plymouth_dir/background.jpg" ||
  erro "Não consegui atualizar a arte do Plymouth."

cat > /etc/plymouth/plymouthd.conf <<'PLYMOUTH_CONF'
[Daemon]
Theme=callas
ShowDelay=0
UseFirmwareBackground=false
PLYMOUTH_CONF

if command -v plymouth-set-default-theme >/dev/null 2>&1; then
  plymouth-set-default-theme callas ||
    erro "Não consegui definir o tema Callas OS como Plymouth padrão."
fi

mkinitcpio -P || erro "Falha ao reconstruir o initramfs com o novo Plymouth."
[[ -s /boot/initramfs-linux.img ]] ||
  erro "O initramfs do kernel principal ficou ausente após atualizar o Plymouth."
[[ -s /boot/initramfs-linux-lts.img ]] ||
  erro "O initramfs do kernel LTS ficou ausente após atualizar o Plymouth."

# Flatpaks padrão do Callas OS.
if command -v flatpak >/dev/null; then
  flatpak remote-add --system --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo || :
  for app in com.vysp3r.ProtonPlus io.github.kolunmi.Bazaar io.missioncenter.MissionCenter; do
    flatpak install --system --noninteractive --assumeyes flathub "$app" ||
      aviso "Não consegui instalar/confirmar $app."
  done
fi


# KDE Plasma: painel translúcido + blur.
# A migração em /usr/share/plasma/.../updates é executada uma vez pelo Plasma
# no próximo login, usando a API oficial de scripting do painel.
plasma_updates=/usr/share/plasma/shells/org.kde.plasma.desktop/contents/updates
install -d "$plasma_updates"
cat > "$plasma_updates/callas-panel-translucent-v2.js" <<'EOF'
panels().forEach(function (panel) {
    panel.opacity = "translucent";
});
EOF

if command -v kwriteconfig6 >/dev/null; then
  como_usuario kwriteconfig6 --file kwinrc --group Plugins --key blurEnabled true ||
    aviso "Não consegui garantir o efeito de blur do KWin."
fi

# Brave em Português do Brasil. O Bonjourr usa navigator.language no
# primeiro carregamento para escolher o idioma padrão.
install -d -o "$usuario" -g "$grupo" "$home/.config"
brave_flags="$home/.config/brave-flags.conf"
touch "$brave_flags"
chown "$usuario:$grupo" "$brave_flags"
grep -Fxq -- '--password-store=kwallet6' "$brave_flags" ||
  printf '%s\n' '--password-store=kwallet6' >> "$brave_flags"
if grep -Eq '^--lang=' "$brave_flags"; then
  sed -i 's/^--lang=.*/--lang=pt-BR/' "$brave_flags"
else
  printf '%s\n' '--lang=pt-BR' >> "$brave_flags"
fi
chown "$usuario:$grupo" "$brave_flags"

# Brave + Bonjourr
install -d /etc/brave/policies/managed /etc/brave/policies/recommended /usr/share/callas-os
cat > /etc/brave/policies/managed/callas-bonjourr.json <<'EOF'
{
  "ExtensionSettings": {
    "dlnejlppicbjfcfcedcflplfjajinajd": {
      "installation_mode": "normal_installed",
      "update_url": "https://clients2.google.com/service/update2/crx"
    }
  }
}
EOF

cat > /etc/brave/policies/recommended/callas-defaults.json <<'EOF'
{
  "RestoreOnStartup": 5,
  "ShowHomeButton": true,
  "HomepageIsNewTabPage": true,
  "BookmarkBarEnabled": true
}
EOF

curl -fsSL --retry 2 "$ASSET_BASE/bonjourr/callas-profile.json"   -o /usr/share/callas-os/bonjourr-profile.json ||
  aviso "Não consegui atualizar o perfil padrão do Bonjourr."

# Se o Brave estiver fechado, também reaplica preferências que não têm política
# própria. Se estiver aberto, não mexe diretamente em Preferences para evitar
# perda/corrupção de dados.
brave_pref="$home/.config/BraveSoftware/Brave-Browser/Default/Preferences"
if ! pgrep -u "$usuario" -f '(^|/)(brave|brave-browser)( |$)' >/dev/null 2>&1; then
  if [[ -f "$brave_pref" ]]; then
    cp -a "$brave_pref" "$backup/Brave-Preferences" 2>/dev/null || true
    python3 - "$brave_pref" <<'EOF'
import json, os, sys
path=sys.argv[1]
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
    json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
EOF
    chown "$usuario:$grupo" "$brave_pref" 2>/dev/null || true
  elif [[ -d /opt/brave-bin ]]; then
    initial=/opt/brave-bin/initial_preferences
    python3 - "$initial" <<'EOF'
import json, os, sys
path=sys.argv[1]
data={}
try:
    with open(path, "r", encoding="utf-8") as f:
        data=json.load(f)
except Exception:
    pass
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
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
EOF
  fi
else
  aviso "Brave está aberto: as políticas foram atualizadas, mas barra de título/botões visuais serão reaplicados quando o Brave estiver fechado em uma próxima atualização."
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

printf '\n'
read -r -p 'Deseja reiniciar o sistema agora? [Y/N]: ' resposta_reboot || resposta_reboot=N
case $resposta_reboot in
  Y|y|S|s)
    printf 'Reiniciando agora...\n'
    exec systemctl --quiet reboot --check-inhibitors=no --no-wall
    ;;
  *) printf 'Reinicialização adiada.\n' ;;
esac
