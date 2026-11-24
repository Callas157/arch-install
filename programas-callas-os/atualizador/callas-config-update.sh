#!/usr/bin/env bash
set -Eeuo pipefail

VERSAO="2026.11.15.03"
export PATH=/usr/bin:/bin
export CALLAS_KERNEL_UPDATE_CONTEXT=config
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
  local log_failed=0
  trap - EXIT
  exec 1>&3 2>&4
  if [[ ${migration_active:-0} == 1 && ${migration_closed:-0} != 1 ]]; then
    python "$CALLAS_RELEASE_DIR/callas-version.py" --fail "$CALLAS_RELEASE_DIR/VERSION" "$CALLAS_RELEASE_REF" || :
  fi
  wait "$logpid" || log_failed=1
  if [[ -x /usr/local/libexec/callas-logs ]]; then
    /usr/local/libexec/callas-logs --record 'Callas OS Update' < "$logstage/update.log" || log_failed=1
    /usr/local/libexec/callas-logs --export "$usuario" || log_failed=1
  else
    log_failed=1
  fi
  if (( log_failed )); then
    aviso "Falha ao gravar/exportar o log. Captura preservada em $logstage/update.log (leitura com sudo)."
    (( codigo != 0 )) || codigo=1
  else
    rm -rf -- "$logstage"
  fi
  [[ -z ${monitor_stage:-} ]] || rm -rf -- "$monitor_stage"
  exit "$codigo"
}
trap finalizar EXIT

# Older installed launchers know a shorter file list. The verified launcher
# staged from this same commit can fetch newly introduced helpers on first use.
if python - "$CALLAS_RELEASE_DIR" <<'CHECK_STAGE'
import importlib.util, sys
try:
    spec=importlib.util.spec_from_file_location('callas_release', sys.argv[1]+'/callas-release.py')
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    complete=module.stage_complete(sys.argv[1])
except Exception as exc:
    print('Falha ao verificar arquivos preparados: '+str(exc), file=sys.stderr)
    sys.exit(2)
sys.exit(0 if complete else 1)
CHECK_STAGE
then
  : # Current release is fully staged; no repeated downloads.
else
  stage_status=$?
  [[ $stage_status == 1 ]] || erro 'Preparação insegura ou inválida; atualização interrompida.'
  printf 'Completando arquivos da atualização para o lançador instalado.\n'
  python - "$CALLAS_RELEASE_DIR" "$CALLAS_RELEASE_REF" <<'EXPAND_STAGE'
import importlib.util, sys
spec=importlib.util.spec_from_file_location('callas_release', sys.argv[1]+'/callas-release.py')
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
module.stage_files(sys.argv[1], sys.argv[2])
EXPAND_STAGE
fi

exec 8>/run/put-update.lock
if ! flock -n -x 8; then
  printf 'Outra atualização está em andamento; aguardando sua conclusão...\n'
  flock -x 8
fi
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
backup_created=0
printf 'Verificando etapas alteradas e pendências; etapas concluídas serão preservadas.\n'
plan_phase() {
  local phase=$1 code
  if "${state_helper[@]}" --needed "$phase" "$CALLAS_RELEASE_DIR" "$usuario" "${force_args[@]}"; then
    execute[$phase]=1; has_work=1
  else
    code=$?; [[ $code == 1 ]] || erro "Não consegui planejar a etapa $phase."
    execute[$phase]=0
  fi
}
backup_config() {
  if (( ! backup_created )); then
    python "$CALLAS_RELEASE_DIR/callas-storage.py" --config "$usuario"
    backup_created=1
  fi
}
phase_needed() {
  if [[ ${execute[$1]} == 1 ]]; then
    printf '\n==> Aplicando etapa alterada: %s\n' "$1"
    return 0
  fi
  printf 'Etapa %s já aplicada; preservada.\n' "$1"
  return 1
}
phase_done() { "${state_helper[@]}" --complete "$1" "$CALLAS_RELEASE_DIR" "$usuario"; }

plan_phase storage
# CALLAS_PHASE_BEGIN storage
if phase_needed storage; then
  backup_config
  python "$CALLAS_RELEASE_DIR/callas-automount.py" "$usuario" --live
  como_usuario /usr/bin/timeout 12s /usr/local/libexec/callas-steam-libraries ||
    aviso 'A Steam poderá verificar as bibliotecas no próximo login.'
  phase_done storage
fi
# CALLAS_PHASE_END storage

python "$CALLAS_RELEASE_DIR/callas-apps.py" --scan
for phase in security apps tools boot flatpaks browser desktop session; do
  plan_phase "$phase"
done
if (( has_work )); then
  backup_config
fi
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
python "$CALLAS_RELEASE_DIR/callas-apps.py" --apply apps "$usuario"
if python "$CALLAS_RELEASE_DIR/callas-apps.py" --wants spotify; then
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
fi

if python "$CALLAS_RELEASE_DIR/callas-apps.py" --wants haruna; then
# BEGIN native Haruna preparation
printf '\n==> Verificando Haruna nativo (reprodutor de vídeo)\n'
if pacman -Q haruna >/dev/null 2>&1; then
  printf 'Haruna nativo já instalado.\n'
else
  consulta_haruna=$?
  [[ $consulta_haruna == 1 ]] || erro 'Não consegui consultar o Haruna no banco de pacotes.'
  /usr/local/libexec/callas-native --install haruna ||
    erro 'Não consegui instalar o Haruna nativo. Consulte o log do Callas OS Update.'
fi
pacman -Q haruna >/dev/null 2>&1 ||
  erro 'Haruna nativo não encontrado após a instalação; atualização não concluída.'
# END native Haruna preparation
fi

if python "$CALLAS_RELEASE_DIR/callas-apps.py" --wants gnome-boxes; then
# BEGIN native Boxes migration
printf '\n==> Verificando GNOME Boxes nativo (redirecionamento USB)\n'
if pacman -Q gnome-boxes >/dev/null 2>&1; then
  printf 'GNOME Boxes nativo já instalado.\n'
else
  consulta_boxes=$?
  [[ $consulta_boxes == 1 ]] || erro 'Não consegui consultar o GNOME Boxes no banco de pacotes.'
  /usr/local/libexec/callas-native --install gnome-boxes ||
    erro 'Não consegui instalar o GNOME Boxes nativo; o Flatpak foi preservado.'
fi
pacman -Q gnome-boxes >/dev/null 2>&1 ||
  erro 'GNOME Boxes nativo não encontrado após a instalação; o Flatpak foi preservado.'
/usr/local/libexec/callas-kernel-check --verify-only ||
  erro 'A verificação de kernel/boot falhou. A remoção do Flatpak não será executada nesta tentativa; não reinicie antes de corrigir.'

# Remove only the application, never --delete-data or VM disks/configurations.
# Per-user Flatpaks must be queried/removed as the desktop user, not as root.
if command -v flatpak >/dev/null; then
  for boxes_scope in system user; do
    boxes_flatpak=(flatpak)
    [[ $boxes_scope != user ]] || boxes_flatpak=(como_usuario flatpak)
    boxes_apps=$("${boxes_flatpak[@]}" list "--$boxes_scope" --app --columns=application) ||
      erro "Não consegui consultar os Flatpaks ($boxes_scope); atualização não concluída."
    if grep -Fxq org.gnome.Boxes <<< "$boxes_apps"; then
      "${boxes_flatpak[@]}" uninstall "--$boxes_scope" --noninteractive --assumeyes org.gnome.Boxes ||
        erro "Não consegui remover o GNOME Boxes Flatpak ($boxes_scope); dados preservados."
      boxes_apps=$("${boxes_flatpak[@]}" list "--$boxes_scope" --app --columns=application) ||
        erro "Não consegui verificar a remoção do GNOME Boxes Flatpak ($boxes_scope)."
      if grep -Fxq org.gnome.Boxes <<< "$boxes_apps"; then
        erro "O GNOME Boxes Flatpak ($boxes_scope) ainda está instalado; atualização não concluída."
      fi
    fi
  done
fi
printf 'GNOME Boxes nativo preparado. Dados das VMs preservados; VMs do Flatpak podem precisar de importação manual.\n'
# END native Boxes migration
fi

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
como_usuario /usr/local/libexec/callas-update-gui-install --configure-user
# O atualizador já usa System; garante a categoria também em instalações existentes.
updater_desktop=/usr/local/share/applications/io.github.Callas157.AtualizadorDoSistema.desktop
if [[ -f $updater_desktop ]]; then
  sed -i 's/^Categories=.*/Categories=System;/' "$updater_desktop"
fi
rm -rf -- "$monitor_stage"
# A versão NVIDIA instalada é preservada por esta atualização de configurações.

phase_done tools
fi
# CALLAS_PHASE_END tools

# CALLAS_PHASE_BEGIN boot
if phase_needed boot; then
# Primeiro reparar apenas módulos da versão NVIDIA escolhida. Divergência
# entre a versão fixada e a instalada exige confirmação explícita na Central;
# não tocar em Plymouth, initramfs ou GRUB antes desta verificação.
if pacman -Qq nvidia-utils >/dev/null 2>&1; then
  /usr/local/libexec/callas-kernel-policy --nvidia-repair ||
    erro 'NVIDIA inconsistente. Na Central > Driver NVIDIA, confirme "Reparar versão instalada"; depois execute o Callas OS Update novamente. Não reinicie enquanto houver falhas.'
fi
# GRUB: transição em tela cheia; não abre janela de terminal sobre o tema.
# Validate legacy entries before changing any boot assets. The helper supports
# microcode, old indentation/paths and EFI command variants without rewriting them.
python "$CALLAS_RELEASE_DIR/callas-boot-theme.py" --entries /etc/grub.d/09_callas --check >/dev/null ||
  erro "Não consegui validar as entradas de boot existentes; arquivos de boot preservados."
install -d /boot/grub/themes/callas

grub_changed=0
initramfs_changed=0
[[ ! -e /boot/grub/.callas-theme-pending ]] || grub_changed=1
[[ ! -e /boot/.callas-initramfs-pending ]] || initramfs_changed=1
asset grub/theme.txt /boot/grub/themes/callas/theme.txt
(( asset_changed == 0 )) || { grub_changed=1; touch /boot/grub/.callas-theme-pending; }
asset grub/background.png /boot/grub/themes/callas/background.png
(( asset_changed == 0 )) || { grub_changed=1; touch /boot/grub/.callas-theme-pending; }
asset grub/loading.cfg /boot/grub/themes/callas/loading.cfg
(( asset_changed == 0 )) || { grub_changed=1; touch /boot/grub/.callas-theme-pending; }
touch /boot/grub/.callas-theme-pending
boot_entries_result=$(python "$CALLAS_RELEASE_DIR/callas-boot-theme.py" --entries /etc/grub.d/09_callas) ||
  erro "Entradas GRUB incompatíveis; configuração de boot não foi regenerada."
[[ $boot_entries_result != changed ]] || grub_changed=1
(( grub_changed )) || rm -f /boot/grub/.callas-theme-pending
[[ -s /boot/grub/grub.cfg ]] || grub_changed=1

rm -f /boot/grub/themes/callas/terminal_box_c.png
rm -f /usr/local/libexec/callas-grub-silencioso
rm -f /etc/pacman.d/hooks/99-callas-grub-silencioso.hook


if (( grub_changed )); then
touch /boot/grub/.callas-theme-pending
grub_tmp=$(mktemp /boot/grub/.grub.cfg.callas.XXXXXX)
if grub-mkconfig -o "$grub_tmp" && [[ -s "$grub_tmp" ]] &&
   grub-script-check "$grub_tmp" &&
   grep -q 'menuentry ' "$grub_tmp" &&
   grep -Eq "(^|[[:space:]/'\"])vmlinuz-linux([[:space:]'\"]|$)" "$grub_tmp" &&
   grep -Eq "(^|[[:space:]/'\"])vmlinuz-linux-lts([[:space:]'\"]|$)" "$grub_tmp"; then
  chmod 0600 "$grub_tmp"
  mv -f "$grub_tmp" /boot/grub/grub.cfg
  rm -f /boot/grub/.callas-theme-pending
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
asset logo/callas-plasma-icon.png "$plymouth_dir/logo.png"
(( asset_changed == 0 )) || initramfs_changed=1
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
touch /boot/.callas-initramfs-pending
if command -v plymouth-set-default-theme >/dev/null 2>&1; then
  plymouth-set-default-theme callas ||
    erro "Não consegui definir o tema Callas OS como Plymouth padrão."
fi

mkinitcpio -P || erro "Falha ao reconstruir o initramfs com o novo Plymouth."
[[ -s /boot/initramfs-linux.img ]] ||
  erro "O initramfs do kernel principal ficou ausente após atualizar o Plymouth."
[[ -s /boot/initramfs-linux-lts.img ]] ||
  erro "O initramfs do kernel LTS ficou ausente após atualizar o Plymouth."
rm -f /boot/.callas-initramfs-pending

fi
/usr/local/libexec/callas-kernel-check --verify-only
phase_done boot
fi
# CALLAS_PHASE_END boot

# CALLAS_PHASE_BEGIN flatpaks
if phase_needed flatpaks; then
# Catálogo compartilhado com a instalação limpa; dados pessoais preservados.
python "$CALLAS_RELEASE_DIR/callas-apps.py" --apply flatpaks "$usuario"

phase_done flatpaks
fi
# CALLAS_PHASE_END flatpaks

# CALLAS_PHASE_BEGIN browser
if phase_needed browser; then
browser_pending=0
# Browser extensions also apply to installations with the older boot layout.
# Use the same extension IDs; existing profiles and extension settings stay intact.
# Stable Brave and Origin share policies; profile/flags remain separate.
asset bonjourr/callas-profile.json /usr/share/callas-os/bonjourr-profile.json
python "$CALLAS_RELEASE_DIR/callas-browser.py" --system
if como_usuario /usr/local/libexec/callas-browser --user; then
  :
else
  browser_status=$?
  if [[ $browser_status == 2 ]]; then
    browser_pending=1
    aviso 'Um navegador Brave está aberto: perfil preservado. Feche-o e repita o Update.'
  else
    erro 'Não consegui configurar os navegadores Brave; preferências inválidas ou alteradas foram preservadas.'
  fi
fi

if (( ! browser_pending )); then
  phase_done browser
else
  printf 'Preferências do Brave/Origin pendentes; os demais passos foram aplicados.\n'
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
Prepend=io.github.Callas157.AtualizadorDoSistema.desktop;steam.desktop;discord.desktop;systemsettings.desktop;
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
# Em atualizações de aplicativos/periféricos, não reconfigurar janelas nem
# preferências de autostart: o Discord, Steam, KWin e seus estados permanecem
# intocados. O instalador e o login KDE cuidam do primeiro provisionamento.
# Não iniciar callas-janelas: esse serviço reinicia a memória do Discord.
# Os auxiliares e arquivos systemd já são preparados na etapa tools.
if [[ -x /usr/local/libexec/callas-nekofetch ]]; then
  if [[ -f $home/.config/nekofetch/layout.jsonc ]]; then
    como_usuario /usr/local/libexec/callas-version --configure-neko
  else
    como_usuario /usr/local/libexec/callas-nekofetch
  fi
fi

# Atualiza apenas definições do systemd do usuário, SEM restart de serviços.
# Se não há sessão ativa, as definições valem no próximo login KDE.
uid_sessao=$(id -u "$usuario")
runtime_sessao="/run/user/$uid_sessao"
if [[ -S "$runtime_sessao/bus" ]]; then
  sessao_systemctl=(runuser -u "$usuario" -- env -i PATH=/usr/bin:/bin HOME="$home"
    USER="$usuario" LOGNAME="$usuario" LANG=C.UTF-8 XDG_RUNTIME_DIR="$runtime_sessao"
    DBUS_SESSION_BUS_ADDRESS="unix:path=$runtime_sessao/bus" systemctl --user)
  "${sessao_systemctl[@]}" daemon-reload ||
    aviso 'Não consegui recarregar definições do usuário; o próximo login KDE fará isso.'
fi
printf 'Discord e memória de janelas preservados. Nenhum serviço de sessão reiniciado.\n'
printf 'Configurações de serviços serão usadas normalmente no próximo login KDE.\n'
como_usuario kbuildsycoca6 --noincremental || aviso 'O menu será atualizado no próximo login.'
phase_done session
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

# BEGIN completion boot gate
# Pacman can return success after a failed PostTransaction hook. Always verify
# installed modules/images read-only before advancing the project identity.
/usr/local/libexec/callas-kernel-check --verify-only ||
  erro 'Kernel/boot com falha; atualização não concluída. Não reinicie antes de corrigir.'
# END completion boot gate

# CALLAS OPTIONAL CODEX UPDATE
# Nunca instalar o chat durante uma instalação limpa ou em usuário sem Codex.
# Verificação rápida no perfil comum, sem sudo para arquivos de usuário.
# Se estiver aberto, nenhuma janela ou processo é interrompido; a próxima
# execução do Callas OS Update verificará novamente, mesmo com release igual.
codex_updater=/usr/local/lib/callas-update/callas-update-gui.py
if [[ -f "$codex_updater" && ! -L "$codex_updater" ]]; then
  if ! como_usuario /usr/bin/python3 "$codex_updater" --update-installed-codex; then
    aviso 'Codex opcional não atualizado nesta execução; será verificado novamente no próximo Callas OS Update.'
  fi
fi

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
