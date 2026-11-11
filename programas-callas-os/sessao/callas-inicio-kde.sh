#!/usr/bin/env bash
set -euo pipefail

if (( EUID == 0 )); then
    printf '%s\n' 'Rode este arquivo no Konsole com seu usuário normal. Ele pede sudo só para corrigir o atualizador.' >&2
    exit 1
fi

# Only the clean installer arms the one-time autostart suppression. Repairs and
# existing-system migrations never create/reset these markers.
case ${1:-} in
    '') export CALLAS_PREPARE_FIRST_LOGIN=0 ;;
    --preparar-primeiro-login) export CALLAS_PREPARE_FIRST_LOGIN=1 ;;
    *) printf 'Argumento inválido.\n' >&2; exit 1 ;;
esac
(( $# <= 1 )) || exit 1

for programa in kwriteconfig6 kreadconfig6 python3; do
    if ! command -v "$programa" >/dev/null; then
        printf 'Comando necessário ausente: %s\n' "$programa" >&2
        exit 1
    fi
done

# O KDE passa a iniciar uma sessão vazia, com o autostart funcionando normalmente.
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
if [[ $XDG_CONFIG_HOME != /* ]]; then
    printf '%s\n' 'XDG_CONFIG_HOME precisa ser um caminho absoluto.' >&2
    exit 1
fi

python3 - <<'PY'
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

home = Path.home()
config = Path(os.environ["XDG_CONFIG_HOME"])
auto = config / "autostart"
auto.mkdir(parents=True, exist_ok=True)
backup = Path(tempfile.mkdtemp(prefix="callas-inicio-backup-", dir=config))
avisos = []

def guardar(path):
    if path.is_file():
        destino = backup / path.relative_to(config)
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destino)

def gravar(path, texto, modo=0o644):
    if not path.is_symlink() and path.is_file() and path.read_text(encoding="utf-8", errors="replace") == texto:
        return
    guardar(path)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as temp:
        try:
            temp.write(texto)
            temp.close()
            os.chmod(temp.name, modo)
            os.replace(temp.name, path)
        finally:
            Path(temp.name).unlink(missing_ok=True)

def chamar(*args):
    return subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False).returncode == 0

def dados(path):
    campos = {}
    ativo = False
    for linha in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if linha.startswith("["):
            ativo = linha == "[Desktop Entry]"
        elif ativo and "=" in linha and not linha.startswith("#"):
            chave, valor = linha.split("=", 1)
            campos[chave] = valor
    return campos

def aplicativo(nome, campos):
    texto = " ".join([nome, campos.get("Name", ""), campos.get("Exec", "")]).lower()
    for app, padrao in (
        ("vibrance", r"vibran[ct]|digital[ _.-]*vibrance"),
        ("discord", r"(?<![\w-])discord(?![\w-])|com\.discordapp\.discord"),
        ("steam", r"(?<![\w-])steam(?![\w-])|com\.valvesoftware\.steam"),
        ("solaar", r"solaar"),
        ("gsr", r"gpu[ ._-]*screen[ ._-]*recorder|gsr-ui"),
        ("extra", r"spotify|brave(?:-browser|-bin)?"),
    ):
        if re.search(padrao, texto):
            return app
    return ""

def desktop(nome, comando, icone=""):
    return (
        f"[Desktop Entry]\nType=Application\nName={nome}\nExec={comando}\n"
        f"StartupNotify=false\nOnlyShowIn=KDE;\n"
        + (f"Icon={icone}\n" if icone else "")
    )

def argumento(valor):
    # Exec usa dois níveis de escape. Percentuais são códigos de campo.
    valor = str(valor).replace("%", "%%")
    if re.fullmatch(r"[a-zA-Z0-9_./@:=+-]+", valor):
        return valor
    valor = re.sub(r'(["`$\\])', r'\\\1', valor)
    return '"' + valor.replace("\\", "\\\\") + '"'

def launcher(*args):
    return " ".join(map(argumento, args))

def flatpak(app):
    return bool(shutil.which("flatpak")) and chamar("flatpak", "info", app)

# Os arquivos do usuário têm precedência sobre os equivalentes do sistema.
locais = {p.name: p for p in sorted(auto.glob("*.desktop")) if p.is_file()}
globais = {}
for pasta in (os.environ.get("XDG_CONFIG_DIRS") or "/etc/xdg").split(":"):
    if Path(pasta).is_absolute():
        for path in sorted((Path(pasta) / "autostart").glob("*.desktop")):
            if path.is_file():
                globais.setdefault(path.name, path)

entradas = {nome: (path, dados(path)) for nome, path in (globais | locais).items()}
tipos = {nome: aplicativo(nome, campos) for nome, (_, campos) in entradas.items()}
planos = {}

discord = shutil.which("discord")
if not discord:
    discord = next((p for p in ("/opt/Discord/Discord", "/opt/discord/Discord") if os.access(p, os.X_OK)), None)
if discord:
    planos["discord"] = ("callas-discord.desktop", desktop("Discord", launcher("/usr/local/libexec/callas-autostart", "discord", discord), "discord"))
    perfil = config / "discord"
    if not perfil.exists():
        perfil.mkdir(mode=0o700)
    if perfil.is_dir():
        try:
            arquivo = perfil / "settings.json"
            ajustes = json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.exists() else {}
            if not isinstance(ajustes, dict):
                raise ValueError("settings.json não contém um objeto")
            novos = dict(ajustes, OPEN_ON_STARTUP=False)
            if novos != ajustes:
                gravar(arquivo, json.dumps(novos, indent=2, ensure_ascii=False) + "\n", 0o600)
        except (OSError, ValueError) as erro:
            avisos.append(f"Discord: não consegui ajustar a preferência da bandeja ({erro}).")
else:
    avisos.append("Discord nativo não encontrado. Mantive as entradas dele.")

steam = shutil.which("steam")
if steam:
    planos["steam"] = ("steam.desktop", desktop("Steam", launcher("/usr/local/libexec/callas-autostart", "steam", steam, "-silent"), "steam"))
else:
    avisos.append("Steam nativa não encontrada. Mantive as entradas dela.")

solaar_id = "io.github.pwr_solaar.solaar"
solaar = shutil.which("solaar")
if solaar:
    comando_solaar = launcher("/usr/bin/env", "GTK_THEME=Adwaita:dark", solaar, "--window=hide")
elif flatpak(solaar_id):
    comando_solaar = launcher("flatpak", "run", solaar_id, "--window=hide")
else:
    comando_solaar = ""
if comando_solaar:
    planos["solaar"] = ("solaar.desktop", desktop("Solaar", comando_solaar, "solaar"))
else:
    avisos.append("Solaar não encontrado. Mantive as entradas dele.")

gsr_id = "com.dec05eba.gpu_screen_recorder"
gsr = shutil.which("gsr-ui")
if flatpak(gsr_id):
    comando_gsr = launcher("flatpak", "run", gsr_id, "gsr-ui")
elif gsr:
    comando_gsr = launcher(gsr, "launch-daemon")
else:
    comando_gsr = ""
if comando_gsr:
    gsr_service = "gpu-screen-recorder-ui.service"
    if chamar("systemctl", "--user", "is-enabled", "--quiet", gsr_service) and not chamar(
        "systemctl", "--user", "disable", gsr_service
    ):
        avisos.append("GPU Screen Recorder: o serviço de usuário já inicia o overlay. Mantive esse serviço.")
        planos["gsr"] = (None, None)
    else:
        planos["gsr"] = ("gpu-screen-recorder-ui.desktop", desktop("GPU Screen Recorder", comando_gsr, gsr_id))
else:
    avisos.append("Overlay do GPU Screen Recorder não encontrado. Mantive as entradas dele.")

vibrance_ativo = any(
    tipos[nome] == "vibrance"
    and campos.get("Hidden", "").lower() != "true"
    and campos.get("X-GNOME-Autostart-enabled", "").lower() != "false"
    and bool(campos.get("Exec"))
    for nome, (_, campos) in entradas.items()
)
if not vibrance_ativo:
    script = home / ".local/bin/DigitalVibrance.sh"
    if script.is_file():
        planos["vibrance"] = ("digital-vibrance.desktop", desktop("Digital Vibrance", launcher("/usr/bin/bash", script)))
    else:
        avisos.append("Digital Vibrance: não localizei a entrada pelo nome. Os scripts do KDE foram preservados.")

sessao = config / "ksmserverrc"
login_args = ("--file", str(sessao), "--group", "General", "--key", "loginMode")
if subprocess.check_output(("kreadconfig6", *login_args), text=True).strip() != "emptySession":
    guardar(sessao)
    subprocess.run(("kwriteconfig6", *login_args, "emptySession"), check=True)
    if subprocess.check_output(("kreadconfig6", *login_args), text=True).strip() != "emptySession":
        raise SystemExit("O KDE não gravou a configuração de sessão vazia.")

destinos = {nome for nome, _ in planos.values() if nome is not None}
for nome, (_, campos) in entradas.items():
    if nome in destinos:
        continue
    app = tipos[nome]
    # Preserva scripts auxiliares do KDE, como os ajustes de monitor e de cores.
    if app == "extra" or app in planos:
        if campos.get("Hidden", "").lower() == "true":
            continue
        gravar(auto / nome, "[Desktop Entry]\nType=Application\nHidden=true\n")
        print(f"Entrada desativada: {nome}")

for nome, conteudo in planos.values():
    if nome is not None:
        gravar(auto / nome, conteudo)

if os.environ.get("CALLAS_PREPARE_FIRST_LOGIN") == "1":
    state = Path(os.environ.get("XDG_STATE_HOME", str(home / ".local/state")))
    if not state.is_absolute(): raise SystemExit("XDG_STATE_HOME precisa ser absoluto")
    state = state / "callas-os"
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    for app in ("steam", "discord"):
        if app in planos:
            marker = state / ("first-login-" + app + ".pending")
            marker.touch(mode=0o600, exist_ok=True)
    print("Primeiro login: Steam e Discord aguardam abertura manual; autostart normal nos próximos logins.")

if any(backup.iterdir()):
    print(f"Backup das configurações: {backup}")
else:
    backup.rmdir()
for aviso in avisos:
    print(f"Aviso: {aviso}")
print("Sessão vazia configurada para o próximo login no KDE.")
PY
