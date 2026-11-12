#!/usr/bin/bash
# Prepare native Spotify for user-run Spicetify. Never run Spicetify as root.
set -Eeuo pipefail
export PATH=/usr/bin:/bin
(( EUID == 0 )) || { printf 'Este ajuste de permissões requer root.\n' >&2; exit 1; }
(( $# <= 1 )) || exit 1
usuario=${1:-}
if [[ -z $usuario ]]; then
  [[ -r /etc/callas-os/log-user ]] || { echo 'Usuário do Callas OS não configurado.' >&2; exit 1; }
  read -r usuario < /etc/callas-os/log-user
fi
uid=$(id -u -- "$usuario")
[[ $uid =~ ^[0-9]+$ && $uid != 0 ]] || { echo 'É necessário um usuário normal.' >&2; exit 1; }
if pacman -Q spotify >/dev/null 2>&1; then
  :
else
  codigo=$?
  [[ $codigo == 1 ]] || { echo 'Não consegui consultar o banco de pacotes do Spotify.' >&2; exit 1; }
  # No Spotify is normal before the migration installs the missing package.
  printf 'Spotify nativo ainda não instalado; permissões serão aplicadas após instalar.\n'
  exit 0
fi
for pasta in /opt/spotify /opt/spotify/Apps; do
  [[ -d $pasta && ! -L $pasta ]] || { printf 'Pasta Spotify ausente ou simbólica: %s\n' "$pasta" >&2; exit 1; }
done
# Access is granted only to this user's UID, not every account. Physical
# recursion avoids following symlinks from customized application resources.
setfacl -m "u:$uid:rwx" /opt/spotify
setfacl -R -P -m "u:$uid:rwX" /opt/spotify/Apps
printf 'Spotify: permissões para Spicetify preparadas para %s.\n' "$usuario"
