#!/usr/bin/bash
set -euo pipefail
export UV_TOOL_BIN_DIR="$HOME/.local/bin"
export PATH="$UV_TOOL_BIN_DIR:$PATH"
config=${XDG_CONFIG_HOME:-$HOME/.config}/nekofetch
uv tool install --upgrade git+https://github.com/ArchitektApx/nekofetch
command -v nekofetch >/dev/null
mkdir -p "$config"

# O layout é do Fastfetch. Usa os valores dedicados do driver de cada GPU.
"$(uv tool dir)/nekofetch/bin/python" - "$config/layout.jsonc" <<'PY_LAYOUT'
from importlib.resources import files
from pathlib import Path
import json
import re
import sys

destino = Path(sys.argv[1])
origem = destino if destino.is_file() else files("nekofetch").joinpath("data", "layout.jsonc")
texto = origem.read_text(encoding="utf-8")
# Remove comentários JSONC sem tocar em URLs, escapes ou no texto dos comandos.
tokens = r'("(?:\\.|[^"\\])*")|//[^\n]*|/\*[\s\S]*?\*/'
texto = re.sub(tokens, lambda item: item[1] or "", texto)
texto = re.sub(r'("(?:\\.|[^"\\])*")|,(?=\s*[}\]])', lambda item: item[1] or "", texto)
layout = json.loads(texto)
modulos = layout["modules"]
sistema = "38;2;189;147;249"
hardware = "38;2;255;121;198"

def inserir(ancora, tipo, nome, icone, cor, formato, **opcoes):
    for modulo in modulos:
        if not isinstance(modulo, dict):
            continue
        if modulo.get("type") == tipo and (
            tipo != "gpu" or nome == "GPU" and modulo.get("format") == "{name}"
            or nome in modulo.get("key", "").split()
        ):
            if nome == "VRAM":
                modulo.update(format=formato, **opcoes)
            return
    for indice, modulo in enumerate(modulos):
        if isinstance(modulo, dict) and (
            modulo.get("type") == ancora or (ancora == "os" and modulo.get("text") == "/usr/local/libexec/callas-version --label") or ancora in modulo.get("key", "").split()
        ):
            modulos.insert(indice + 1, {
                "key": f"  {chr(icone)} {nome:9}",
                "keyColor": cor,
                "type": tipo,
                "format": formato,
                **opcoes,
            })
            return
    raise SystemExit(f"Nekofetch: módulo de referência ausente: {ancora}.")

inserir("os", "kernel", "Kernel", 0xF17C, sistema, "{release}")
inserir("kernel", "de", "Desktop", 0xF0379, sistema, "{pretty-name} {version}")
inserir("cpu", "display", "Display", 0xF0379, hardware, "{width}x{height} @ {refresh-rate}Hz")
inserir("cpu", "gpu", "GPU", 0xF08AE, hardware, "{name}")
inserir("GPU", "gpu", "Driver", 0xF061A, hardware, "{driver}")
inserir("Driver", "gpu", "VRAM", 0xF035B, hardware,
        "{?dedicated-total}{?dedicated-used}{dedicated-used} / {?}{dedicated-total}{?}"
        "{/dedicated-total}Indisponível{/}",
        driverSpecific=True)
novo = json.dumps(layout, ensure_ascii=False, indent=2) + "\n"
if not destino.exists() or destino.read_text(encoding="utf-8") != novo:
    temporario = destino.with_suffix(".tmp")
    temporario.write_text(novo, encoding="utf-8")
    temporario.replace(destino)
PY_LAYOUT
/usr/local/libexec/callas-version --configure-neko

bashrc="$HOME/.bashrc"
path_line='export PATH="$HOME/.local/bin:$PATH"'
startup='[[ $- == *i* ]] && command -v nekofetch >/dev/null 2>&1 && nekofetch'
comment='# Nekofetch automático ao abrir o terminal'
touch "$bashrc"
if ! grep -Fxq "$path_line" "$bashrc"; then
  printf '\n%s\n' "$path_line" >> "$bashrc"
fi
temp=$(mktemp)
trap 'rm -f -- "$temp"' EXIT
grep -Fvx -e "$startup" -e "$comment" \
  -e 'command -v nekofetch >/dev/null 2>&1 && nekofetch' "$bashrc" > "$temp" || :
cat "$temp" > "$bashrc"
printf '\n%s\n%s\n' "$comment" "$startup" >> "$bashrc"
