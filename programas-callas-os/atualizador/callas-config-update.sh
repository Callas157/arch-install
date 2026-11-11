#!/usr/bin/env bash
set -Eeuo pipefail

VERSAO="2026.11.11.20"
export PATH=/usr/bin:/bin
umask 077
BASE_RAW="https://raw.githubusercontent.com/Callas157/arch-install/${CALLAS_RELEASE_REF:-main}"
ASSET_BASE="$BASE_RAW/assets"
PROGRAMAS_BASE="$BASE_RAW/programas-callas-os"
ESTADO_DIR="/var/lib/callas-os"
VERSAO_ARQ="$ESTADO_DIR/config-version"

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

# Legacy clients bootstrap once through their existing trusted URL. Subsequent
# launches use the installed root-owned staging runner and one immutable commit.
if [[ -z ${CALLAS_RELEASE_DIR:-} ]]; then
  CALLAS_RELEASE_REF=$(python - <<'REF'
import json, urllib.request
req=urllib.request.Request('https://api.github.com/repos/Callas157/arch-install/git/ref/heads/main', headers={'User-Agent':'CallasOS-Updater'})
with urllib.request.urlopen(req, timeout=60) as response: print(json.load(response)['object']['sha'])
REF
  )
  [[ $CALLAS_RELEASE_REF =~ ^[0-9a-f]{40}$ ]] || erro 'Commit inválido.'
  CALLAS_RELEASE_DIR=$(mktemp -d /var/tmp/callas-bootstrap.XXXXXXXX)
  trap 'rm -rf -- "$CALLAS_RELEASE_DIR"' EXIT
  curl --proto '=https' --proto-redir '=https' -fsSL --retry 2 \
    "https://raw.githubusercontent.com/Callas157/arch-install/$CALLAS_RELEASE_REF/programas-callas-os/atualizador/callas-release.py" \
    -o "$CALLAS_RELEASE_DIR/callas-release.py"
  python - "$CALLAS_RELEASE_DIR" "$CALLAS_RELEASE_REF" <<'STAGE'
import importlib.util, sys
spec=importlib.util.spec_from_file_location('callas_release', sys.argv[1]+'/callas-release.py')
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
module.stage_files(sys.argv[1], sys.argv[2])
STAGE
  export CALLAS_RELEASE_REF CALLAS_RELEASE_DIR
  # Restart using the exact staged version, preserving the cleanup trap.
  /usr/bin/bash "$CALLAS_RELEASE_DIR/callas-config-update.sh" "$@"
  exit $?
fi

BASE_RAW="https://raw.githubusercontent.com/Callas157/arch-install/$CALLAS_RELEASE_REF"
ASSET_BASE="$BASE_RAW/assets"
PROGRAMAS_BASE="$BASE_RAW/programas-callas-os"
logstage=$(mktemp -d /var/tmp/callas-config-log.XXXXXXXX)
exec 3>&1 4>&2
exec > >(tee "$logstage/update.log") 2>&1
logpid=$!
finalizar() {
  local codigo=$?
  trap - EXIT
  exec 1>&3 2>&4
  if [[ ${migration_active:-0} == 1 && ${migration_closed:-0} != 1 ]]; then
    python "$CALLAS_RELEASE_DIR/callas-version.py" --fail "$CALLAS_RELEASE_DIR/VERSION" "$CALLAS_RELEASE_REF" || :
  fi
  wait "$logpid" || :
  if [[ -x /usr/local/libexec/callas-logs ]]; then
    /usr/local/libexec/callas-logs --record 'Callas OS Update' < "$logstage/update.log" || :
    /usr/local/libexec/callas-logs --export "$usuario" || :
  fi
  rm -rf -- "$logstage"
  [[ -z ${monitor_stage:-} ]] || rm -rf -- "$monitor_stage"
  exit "$codigo"
}
trap finalizar EXIT

# Older installed launchers know a shorter file list. The verified launcher
# staged from this same commit can fetch newly introduced helpers on first use.
if [[ ! -f $CALLAS_RELEASE_DIR/callas-autostart.py || ! -f $CALLAS_RELEASE_DIR/VERSION || ! -f $CALLAS_RELEASE_DIR/callas-version.py || ! -f $CALLAS_RELEASE_DIR/callas-nekofetch.sh || ! -f $CALLAS_RELEASE_DIR/callas-aur.py || ! -f $CALLAS_RELEASE_DIR/callas-storage.py || ! -f $CALLAS_RELEASE_DIR/callas-maintenance.py || ! -f $CALLAS_RELEASE_DIR/callas-native.py ]]; then
  python - "$CALLAS_RELEASE_DIR" "$CALLAS_RELEASE_REF" <<'EXPAND_STAGE'
import importlib.util, sys
spec=importlib.util.spec_from_file_location('callas_release', sys.argv[1]+'/callas-release.py')
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
module.stage_files(sys.argv[1], sys.argv[2])
EXPAND_STAGE
fi

exec 8>/run/put-update.lock
flock -x 8
export CALLAS_UPDATE_LOCK_HELD=1
python "$CALLAS_RELEASE_DIR/callas-version.py" --begin "$CALLAS_RELEASE_DIR/VERSION" "$CALLAS_RELEASE_REF"
migration_active=1
python "$CALLAS_RELEASE_DIR/callas-storage.py" --config "$usuario"
/usr/bin/bash "$CALLAS_RELEASE_DIR/callas-security.sh" "$usuario"

# Browser extensions also apply to installations with the older boot layout.
# Use the same extension IDs; existing profiles and extension settings stay intact.
install -d /etc/brave/policies/managed
cat > /etc/brave/policies/managed/callas-bonjourr.json <<'EOF'
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
EOF
chmod 0644 /etc/brave/policies/managed/callas-bonjourr.json

grub_compativel=0
if [[ -x /etc/grub.d/09_callas && -f /etc/grub.d/10_linux && ! -x /etc/grub.d/10_linux ]]; then
  grub_compativel=1
fi
if (( ! grub_compativel )); then
  como_usuario /usr/local/libexec/callas-version --configure-neko
  /usr/local/libexec/callas-version --blocked "$CALLAS_RELEASE_DIR/VERSION" "$CALLAS_RELEASE_REF"
  migration_closed=1
  printf 'Segurança e atualizador migrados. Personalizações de boot antigas foram preservadas.\n'
  printf 'A versão completa do projeto não foi avançada: arquitetura de boot anterior.\n'
  exit 0
fi
printf '%s\n' 'grub-custom-v2' > /etc/callas-os/grub-layout

install -d -m 0755 "$ESTADO_DIR"
forcar=0
[[ ${1:-} == --force ]] && forcar=1

atual=0
[[ -r "$VERSAO_ARQ" ]] && atual=$(<"$VERSAO_ARQ")
if [[ "$atual" == "$VERSAO" && $forcar -eq 0 ]] && python "$CALLAS_RELEASE_DIR/callas-version.py" --is-installed "$CALLAS_RELEASE_DIR/VERSION"; then
  printf 'Configurações já aplicadas: '
  /usr/local/libexec/callas-version --label
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

# Instala o utilitário sem modificar monitores nem posições de janelas via root.
# Todos os downloads são validados antes de substituir os auxiliares instalados.
monitor_stage=$(mktemp -d)
for nome in callas-monitores.py callas-janelas.py callas-inicio-kde.sh callas-kde-desligamento-login.sh; do
  case $nome in
    callas-monitores.py|callas-kde-desligamento-login.sh) subpasta=monitores ;;
    callas-janelas.py) subpasta=janelas ;;
    callas-inicio-kde.sh) subpasta=sessao ;;
  esac
  install -m 0600 "$CALLAS_RELEASE_DIR/$nome" "$monitor_stage/$nome" ||
    erro "Auxiliar verificado ausente: $nome."
done
python - "$monitor_stage/callas-monitores.py" "$monitor_stage/callas-janelas.py" <<'CALLAS_MONITOR_CHECK'
import ast, sys
for path in sys.argv[1:]:
    ast.parse(open(path, encoding="utf-8").read())
CALLAS_MONITOR_CHECK
bash -n "$monitor_stage/callas-inicio-kde.sh"
bash -n "$monitor_stage/callas-kde-desligamento-login.sh"
install -d /usr/local/libexec
for nome in callas-inicio-kde callas-kde-desligamento-login; do
  install -m 0755 "$monitor_stage/$nome.sh" "/usr/local/libexec/$nome"
done
install -m 0755 "$monitor_stage/callas-monitores.py" /usr/local/libexec/callas-monitores
/usr/local/libexec/callas-monitores --install-system
install -m 0755 "$monitor_stage/callas-janelas.py" /usr/local/libexec/callas-janelas
/usr/local/libexec/callas-janelas --install-system
# O atualizador já usa System; garante a categoria também em instalações existentes.
updater_desktop=/usr/local/share/applications/io.github.Callas157.AtualizadorDoSistema.desktop
if [[ -f $updater_desktop ]]; then
  sed -i 's/^Categories=.*/Categories=System;/' "$updater_desktop"
fi
rm -rf -- "$monitor_stage"
# NVIDIA: versão e trava existentes preservadas por solicitação do usuário.

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

install -m 0644 "$CALLAS_RELEASE_DIR/callas.plymouth" "$plymouth_dir/callas.plymouth"
install -m 0644 "$CALLAS_RELEASE_DIR/callas.script" "$plymouth_dir/callas.script"
curl -fsSL --retry 2 "$ASSET_BASE/plymouth/callas/background.jpg" \
  -o "$plymouth_dir/background.jpg" ||
  erro "Não consegui atualizar a arte do Plymouth."

# Usa os assets PNG oficiais do tema script instalado pelo pacote Plymouth.
[[ -f /usr/share/plymouth/themes/script/progress_box.png ]] ||
  erro "progress_box.png do Plymouth não foi encontrado."
[[ -f /usr/share/plymouth/themes/script/progress_bar.png ]] ||
  erro "progress_bar.png do Plymouth não foi encontrado."
install -m 0644 /usr/share/plymouth/themes/script/progress_box.png \
  "$plymouth_dir/progress_box.png"
install -m 0644 /usr/share/plymouth/themes/script/progress_bar.png \
  "$plymouth_dir/progress_bar.png"

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
como_usuario python3 - <<'FLAGS'
from pathlib import Path
p=Path.home()/'.config/brave-flags.conf'
p.parent.mkdir(parents=True, exist_ok=True)
lines=p.read_text().splitlines() if p.exists() else []
lines=[line for line in lines if not line.startswith('--lang=')]
if '--password-store=kwallet6' not in lines: lines.append('--password-store=kwallet6')
lines.append('--lang=pt-BR')
p.write_text('\n'.join(lines)+'\n')
FLAGS

# Brave + Bonjourr + SteamDB
install -d /etc/brave/policies/managed /etc/brave/policies/recommended /usr/share/callas-os

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

# Perfis existentes ficam intactos, com o Brave aberto ou fechado. Somente o
# arquivo de preferências iniciais para futuros perfis recebe os padrões visuais.
brave_pref="$home/.config/BraveSoftware/Brave-Browser/Default/Preferences"
if ! pgrep -u "$usuario" -f '(^|/)(brave|brave-browser)( |$)' >/dev/null 2>&1; then
  if [[ -f "$brave_pref" ]]; then
    printf 'Perfil existente do Brave preservado; extensões serão processadas pelo navegador quando ele for aberto.\n'
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
  printf 'Brave aberto: perfil preservado; políticas disponíveis para o navegador.\n'
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
Prepend=io.github.Callas157.Monitores.desktop;systemsettings.desktop;io.github.Callas157.AtualizadorDoSistema.desktop;steam.desktop;org.kde.konsole.desktop;io.github.kolunmi.Bazaar.desktop;com.vysp3r.ProtonPlus.desktop;io.missioncenter.MissionCenter.desktop;org.qbittorrent.qBittorrent.desktop;spotify.desktop;solaar.desktop;
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
  if [[ -f $home/.config/nekofetch/layout.jsonc ]]; then
    como_usuario /usr/local/libexec/callas-version --configure-neko
  else
    como_usuario /usr/local/libexec/callas-nekofetch
  fi
fi

# Patch independente: ativa a memória automaticamente na sessão Plasma existente.
# O systemd do usuário fornece o ambiente gráfico; sudo/root não grava kwinrulesrc.
uid_sessao=$(id -u "$usuario")
runtime_sessao="/run/user/$uid_sessao"
if [[ -S "$runtime_sessao/bus" ]]; then
  sessao_systemctl=(runuser -u "$usuario" -- env -i PATH=/usr/bin:/bin HOME="$home"
    USER="$usuario" LOGNAME="$usuario" LANG=C.UTF-8 XDG_RUNTIME_DIR="$runtime_sessao"
    DBUS_SESSION_BUS_ADDRESS="unix:path=$runtime_sessao/bus" systemctl --user)
  "${sessao_systemctl[@]}" daemon-reload
  "${sessao_systemctl[@]}" start callas-janelas.service ||
    erro 'Não consegui ativar a memória de janelas na sessão. Consulte journalctl --user -u callas-janelas.service.'
  printf 'Memória de janelas ativada automaticamente. Não depende do configurador de monitores.\n'
else
  printf 'Sem sessão gráfica ativa: a memória será ativada automaticamente no próximo login KDE.\n'
fi

como_usuario kbuildsycoca6 --noincremental || aviso 'O menu será atualizado no próximo login.'

printf '%s\n' "$VERSAO" > "$VERSAO_ARQ"
/usr/local/libexec/callas-version --complete "$CALLAS_RELEASE_DIR/VERSION" "$CALLAS_RELEASE_REF"
migration_closed=1

printf '\nConfigurações atualizadas: '
/usr/local/libexec/callas-version --label
printf 'Backups em Documentos/Callas OS/Callas OS Backups (leitura administrativa).\n'
printf 'Abra Callas OS — Monitores no menu Sistema para escolher sua tela principal.\n'
printf 'Algumas mudanças do KDE podem aparecer por completo após encerrar e iniciar a sessão.\n'

printf 'Consulte os logs em Documentos/Callas OS/Callas OS Logs.\n'
