#!/usr/bin/env bash
set -Eeuo pipefail

VERSAO="2026.11.12.02"
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
if [[ ! -f $CALLAS_RELEASE_DIR/callas-update-state.py || ! -f $CALLAS_RELEASE_DIR/update-assets.json || ! -f $CALLAS_RELEASE_DIR/callas-spotify-permissions.sh || ! -f $CALLAS_RELEASE_DIR/callas-aur-install.py || ! -f $CALLAS_RELEASE_DIR/callas-autostart.py || ! -f $CALLAS_RELEASE_DIR/VERSION || ! -f $CALLAS_RELEASE_DIR/callas-version.py || ! -f $CALLAS_RELEASE_DIR/callas-nekofetch.sh || ! -f $CALLAS_RELEASE_DIR/callas-aur.py || ! -f $CALLAS_RELEASE_DIR/callas-storage.py || ! -f $CALLAS_RELEASE_DIR/callas-maintenance.py || ! -f $CALLAS_RELEASE_DIR/callas-native.py ]]; then
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
forcar=0
[[ ${1:-} != --force ]] || forcar=1
# Deploy verified helpers cheaply; policy/package/boot work is checkpointed below.
/usr/bin/bash "$CALLAS_RELEASE_DIR/callas-security.sh" "$usuario" --helpers-only
state_helper=(python "$CALLAS_RELEASE_DIR/callas-update-state.py")
force_args=()
(( ! forcar )) || force_args=(--force)
declare -A execute
has_work=0
for phase in security apps tools boot flatpaks browser desktop session; do
  if "${state_helper[@]}" --needed "$phase" "$CALLAS_RELEASE_DIR" "$usuario" "${force_args[@]}"; then
    execute[$phase]=1; has_work=1
  else
    code=$?; [[ $code == 1 ]] || erro "Não consegui planejar a etapa $phase."
    execute[$phase]=0
  fi
done
if (( has_work )); then
  python "$CALLAS_RELEASE_DIR/callas-storage.py" --config "$usuario"
fi
phase_needed() {
  if [[ ${execute[$1]} == 1 ]]; then
    printf '\n==> Aplicando etapa alterada: %s\n' "$1"
    return 0
  fi
  printf 'Etapa %s já aplicada; preservada.\n' "$1"
  return 1
}
phase_done() { "${state_helper[@]}" --complete "$1" "$CALLAS_RELEASE_DIR" "$usuario"; }
asset() {
  local result
  result=$("${state_helper[@]}" --asset "$CALLAS_RELEASE_DIR" "$1" "$2") || erro "Não consegui verificar/baixar o asset $1."
  asset_changed=0
  [[ $result != changed ]] || asset_changed=1
}
copy_changed() {
  if ! cmp -s "$1" "$2"; then
    install -m 0644 "$1" "$2"
    initramfs_changed=1
  fi
}
# CALLAS_PHASE_BEGIN security
if phase_needed security; then
  /usr/bin/bash "$CALLAS_RELEASE_DIR/callas-security.sh" "$usuario" --config-update
  phase_done security
fi
# CALLAS_PHASE_END security

# CALLAS_PHASE_BEGIN apps
if phase_needed apps; then
# Complete the native application set on existing installations as well.
# The initial AUR helper keeps checksum/PGP verification enabled and builds as
# the normal user, never via passwordless sudo. Existing Spotify is preserved.
printf '\n==> Verificando Spotify nativo\n'
if pacman -Q spotify >/dev/null 2>&1; then
  printf 'Spotify nativo já instalado.\n'
else
  consulta_spotify=$?
  [[ $consulta_spotify == 1 ]] || erro 'Não consegui consultar o Spotify no banco de pacotes.'
  /usr/local/libexec/callas-aur-install "$usuario" spotify ||
    erro 'Não consegui instalar o Spotify nativo. Consulte o log do Callas OS Update.'
  pacman -Q spotify >/dev/null 2>&1 ||
    erro 'O Spotify não foi encontrado após a instalação; atualização não concluída.'
fi

/usr/local/libexec/callas-spotify-permissions "$usuario"
# End native Spotify preparation.


phase_done apps
fi
# CALLAS_PHASE_END apps

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

# CALLAS_PHASE_BEGIN tools
if phase_needed tools; then
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
# Organiza os acessos do usuário sem alterar o caminho do menu e do agendador.
como_usuario /usr/local/libexec/put-update --instalar-atalhos
# O atualizador já usa System; garante a categoria também em instalações existentes.
updater_desktop=/usr/local/share/applications/io.github.Callas157.AtualizadorDoSistema.desktop
if [[ -f $updater_desktop ]]; then
  sed -i 's/^Categories=.*/Categories=System;/' "$updater_desktop"
fi
rm -rf -- "$monitor_stage"
# NVIDIA: versão e trava existentes preservadas por solicitação do usuário.

phase_done tools
fi
# CALLAS_PHASE_END tools

# CALLAS_PHASE_BEGIN boot
if phase_needed boot; then
# GRUB: restaura apenas o tema estável do Callas OS.
# Não altera terminal-box nem tenta forçar transparência.
install -d /boot/grub/themes/callas

grub_changed=0
initramfs_changed=0
asset grub/theme.txt /boot/grub/themes/callas/theme.txt
(( asset_changed == 0 )) || grub_changed=1
asset grub/background.png /boot/grub/themes/callas/background.png
(( asset_changed == 0 )) || grub_changed=1
[[ -s /boot/grub/grub.cfg ]] || grub_changed=1

rm -f /boot/grub/themes/callas/terminal_box_c.png
rm -f /usr/local/libexec/callas-grub-silencioso
rm -f /etc/pacman.d/hooks/99-callas-grub-silencioso.hook


if (( grub_changed )); then
grub_tmp=$(mktemp /boot/grub/.grub.cfg.callas.XXXXXX)
if grub-mkconfig -o "$grub_tmp" && [[ -s "$grub_tmp" ]] &&
   grub-script-check "$grub_tmp" &&
   grep -q 'menuentry ' "$grub_tmp" &&
   grep -Eq '(^|[[:space:]/])vmlinuz-linux([[:space:]]|$)' "$grub_tmp" &&
   grep -Eq '(^|[[:space:]/])vmlinuz-linux-lts([[:space:]]|$)' "$grub_tmp"; then
  chmod 0600 "$grub_tmp"
  mv -f "$grub_tmp" /boot/grub/grub.cfg
else
  rm -f "$grub_tmp"
  erro "Falha ao validar a configuração do GRUB; o grub.cfg anterior foi preservado."
fi

fi

# Plymouth do Callas OS.
# Atualização segura: troca apenas os arquivos do tema e reconstrói o initramfs.
plymouth_dir=/usr/share/plymouth/themes/callas
install -d "$plymouth_dir"

copy_changed "$CALLAS_RELEASE_DIR/callas.plymouth" "$plymouth_dir/callas.plymouth"
copy_changed "$CALLAS_RELEASE_DIR/callas.script" "$plymouth_dir/callas.script"
asset plymouth/callas/background.jpg "$plymouth_dir/background.jpg"
(( asset_changed == 0 )) || initramfs_changed=1

# Usa os assets PNG oficiais do tema script instalado pelo pacote Plymouth.
[[ -f /usr/share/plymouth/themes/script/progress_box.png ]] ||
  erro "progress_box.png do Plymouth não foi encontrado."
[[ -f /usr/share/plymouth/themes/script/progress_bar.png ]] ||
  erro "progress_bar.png do Plymouth não foi encontrado."
copy_changed /usr/share/plymouth/themes/script/progress_box.png \
  "$plymouth_dir/progress_box.png"
copy_changed /usr/share/plymouth/themes/script/progress_bar.png \
  "$plymouth_dir/progress_bar.png"

cat > "$logstage/plymouthd.conf" <<'PLYMOUTH_CONF'
[Daemon]
Theme=callas
ShowDelay=0
UseFirmwareBackground=false
PLYMOUTH_CONF
copy_changed "$logstage/plymouthd.conf" /etc/plymouth/plymouthd.conf
for kernel in linux linux-lts; do
  [[ -s /boot/initramfs-$kernel.img ]] || initramfs_changed=1
done
if (( initramfs_changed )); then
if command -v plymouth-set-default-theme >/dev/null 2>&1; then
  plymouth-set-default-theme callas ||
    erro "Não consegui definir o tema Callas OS como Plymouth padrão."
fi

mkinitcpio -P || erro "Falha ao reconstruir o initramfs com o novo Plymouth."
[[ -s /boot/initramfs-linux.img ]] ||
  erro "O initramfs do kernel principal ficou ausente após atualizar o Plymouth."
[[ -s /boot/initramfs-linux-lts.img ]] ||
  erro "O initramfs do kernel LTS ficou ausente após atualizar o Plymouth."

fi
/usr/local/libexec/callas-kernel-check --verify-only
phase_done boot
fi
# CALLAS_PHASE_END boot

# CALLAS_PHASE_BEGIN flatpaks
if phase_needed flatpaks; then
# Flatpaks padrão do Callas OS.
if command -v flatpak >/dev/null; then
  flatpak remote-add --system --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo || :
  for app in com.vysp3r.ProtonPlus io.github.kolunmi.Bazaar io.missioncenter.MissionCenter; do
    if ! flatpak info --system "$app" >/dev/null 2>&1; then
      flatpak install --system --noninteractive --assumeyes flathub "$app" ||
        erro "Não consegui instalar $app."
    fi
  done
fi


phase_done flatpaks
fi
# CALLAS_PHASE_END flatpaks

# CALLAS_PHASE_BEGIN browser
if phase_needed browser; then
browser_pending=0
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

asset bonjourr/callas-profile.json /usr/share/callas-os/bonjourr-profile.json

# Reaplica apenas as preferências visuais conhecidas, sem recriar o perfil.
# Com o navegador aberto, preserva Preferences para evitar concorrência.
brave_pref="$home/.config/BraveSoftware/Brave-Browser/Default/Preferences"
if ! pgrep -u "$usuario" -f '(^|/)(brave|brave-browser)( |$)' >/dev/null 2>&1; then
  if [[ -f "$brave_pref" ]]; then
    como_usuario python3 - "$brave_pref" <<'BRAVE_REPAIR'
import json, os, sys, tempfile
from pathlib import Path
path = Path(sys.argv[1])
# Never substitute an empty object for an unreadable/corrupt existing profile.
before = path.stat()
with path.open(encoding='utf-8') as stream: data = json.load(stream)
if not isinstance(data, dict): raise ValueError('Preferences não contém objeto JSON; arquivo preservado')
data.setdefault('browser', {})['custom_chrome_frame'] = False
data['browser']['show_home_button'] = True
data['homepage_is_newtabpage'] = True
data.setdefault('bookmark_bar', {})['show_on_all_tabs'] = True
data.setdefault('intl', {})['accept_languages'] = 'pt-BR,pt,en-US,en'
data['intl']['selected_languages'] = 'pt-BR,pt,en-US,en'
data.setdefault('tab_search', {})['pinned_to_tabstrip'] = True
data.setdefault('everything_menu', {})['pinned_to_tabstrip'] = True
actions = data.setdefault('toolbar', {}).setdefault('pinned_actions', [])
if 'kActionTabSearch' not in actions: actions.append('kActionTabSearch')
fd, temp = tempfile.mkstemp(prefix='.callas-preferences-', dir=path.parent)
try:
    with os.fdopen(fd, 'w') as stream:
        json.dump(data, stream, ensure_ascii=False, separators=(',', ':'))
        stream.flush(); os.fsync(stream.fileno())
    after = path.stat()
    if (before.st_ino, before.st_mtime_ns, before.st_size) != (after.st_ino, after.st_mtime_ns, after.st_size):
        raise RuntimeError('Preferences mudou durante a migração; arquivo preservado')
    os.replace(temp, path)
finally:
    if os.path.exists(temp): os.unlink(temp)
BRAVE_REPAIR
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
  browser_pending=1
  aviso 'Brave aberto: perfil preservado. Feche o navegador e reaplique a opção 5 para reparar as preferências visuais.'
fi

if (( ! browser_pending )); then
  phase_done browser
else
  printf 'Preferências do Brave pendentes; os demais passos foram aplicados.\n'
fi
fi
# CALLAS_PHASE_END browser

# CALLAS_PHASE_BEGIN desktop
if phase_needed desktop; then
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
  asset "wallpapers/$wallpaper" "$destino/contents/images/1920x1080.jpg"
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

phase_done desktop
fi
# CALLAS_PHASE_END desktop

# CALLAS_PHASE_BEGIN session
if phase_needed session; then
session_pending=0
# Repair the persistent theme without depending on a running graphical session.
como_usuario kwriteconfig6 --file kdeglobals --group KDE --key LookAndFeelPackage org.kde.breezedark.desktop
como_usuario kwriteconfig6 --file kdeglobals --group General --key ColorScheme BreezeDark

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
  if ! "${sessao_systemctl[@]}" start callas-janelas.service; then
    runuser -u "$usuario" -- env -i PATH=/usr/bin:/bin HOME="$home" XDG_RUNTIME_DIR="$runtime_sessao" \
      DBUS_SESSION_BUS_ADDRESS="unix:path=$runtime_sessao/bus" \
      journalctl --user -u callas-janelas.service -n 40 --no-pager || :
    erro 'A memória de janelas falhou; o diagnóstico foi incluído neste log. As etapas concluídas não serão repetidas na próxima tentativa.'
  fi
  printf 'Memória de janelas ativada automaticamente. Não depende do configurador de monitores.\n'
else
  session_pending=1
  printf 'Sem sessão gráfica ativa: a memória será ativada automaticamente no próximo login KDE.\n'
fi

como_usuario kbuildsycoca6 --noincremental || aviso 'O menu será atualizado no próximo login.'

(( session_pending )) || phase_done session
fi
# CALLAS_PHASE_END session

pending_file="$ESTADO_DIR/update-pending-$(id -u "$usuario")"
rm -f -- "$pending_file"
for phase in security apps tools boot flatpaks browser desktop session; do
  if "${state_helper[@]}" --needed "$phase" "$CALLAS_RELEASE_DIR" "$usuario"; then
    printf '%s\n' "$phase" >> "$pending_file"
  else
    code=$?; [[ $code == 1 ]] || erro "Não consegui confirmar a etapa $phase."
  fi
done

printf '%s\n' "$VERSAO" > "$VERSAO_ARQ"
/usr/local/libexec/callas-version --complete "$CALLAS_RELEASE_DIR/VERSION" "$CALLAS_RELEASE_REF"
migration_closed=1
rm -f /var/lib/callas-os/installation-failed

printf '\nConfigurações atualizadas: '
/usr/local/libexec/callas-version --label
printf 'Backups em Documentos/Callas OS/Callas OS Backups (leitura administrativa).\n'
printf 'Abra Callas OS — Monitores no menu Sistema para escolher sua tela principal.\n'
printf 'Algumas mudanças do KDE podem aparecer por completo após encerrar e iniciar a sessão.\n'

printf 'Consulte os logs em Documentos/Callas OS/Callas OS Logs.\n'
