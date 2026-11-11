#!/usr/bin/env bash
# Compatibilidade: instalações antigas ainda consultam este endereço.
# O atualizador completo fica em programas-callas-os/atualizador/.
set -Eeuo pipefail
VERSAO="2026.11.11.21"
url="https://raw.githubusercontent.com/Callas157/arch-install/main/programas-callas-os/atualizador/callas-config-update.sh"
temporario=$(mktemp)
trap 'rm -f -- "$temporario"' EXIT
curl -fsSL --retry 2 --connect-timeout 10 --max-time 120 "$url" -o "$temporario"
bash -n "$temporario"
/usr/bin/bash "$temporario" "$@"

