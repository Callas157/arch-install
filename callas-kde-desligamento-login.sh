#!/usr/bin/env bash
# Arch Linux e Plasma Wayland, com Plasma Login Manager ou SDDM.
set -euo pipefail

erro() { printf 'Erro: %s\n' "$*" >&2; exit 1; }

# Esta função também é instalada como a ação do hook do pacman.
ajustar_contagem() {
    local acao=$1 arquivo quantidade reconhecidos=0 falhas=0
    local inicio='^([[:blank:]]*(readonly[[:blank:]]+)?property[[:blank:]]+(real|int)[[:blank:]]+timeout[[:blank:]]*:[[:blank:]]*)'
    local fim='([[:blank:]]*;?[[:blank:]]*(//.*)?)$'
    local original="${inicio}30${fim}"
    local valor='(sdtype === ShutdownType.ShutdownTypeHalt || sdtype === ShutdownType.ShutdownTypeReboot) ? 5 : 30 /* Callas KDE */'
    local nosso="${inicio}.* /\\* Callas KDE \\*/${fim}"
    for arquivo in \
        /usr/share/plasma/shells/org.kde.plasma.desktop/contents/logout/Logout.qml \
        /usr/share/plasma/shells/org.kde.plasma.desktop/contents/logout/LogoutControls.qml \
        /usr/share/plasma/look-and-feel/org.kde.breeze.desktop/contents/logout/Logout.qml; do
        [[ -f $arquivo && ! -L $arquivo ]] || continue
        if [[ $acao == desfazer ]]; then
            if grep -Eq "$nosso" "$arquivo"; then
                sed -Ei "s@${nosso}@\\130\\4@" "$arquivo" || falhas=1
            fi
            continue
        fi
        quantidade=$(grep -Ec "$original" "$arquivo") || :
        if [[ $quantidade == 1 ]] && grep -wq 'sdtype' "$arquivo" &&
            grep -Fq 'ShutdownType.ShutdownTypeHalt' "$arquivo" &&
            grep -Fq 'ShutdownType.ShutdownTypeReboot' "$arquivo"; then
            if sed -Ei "s@${original}@\\1${valor}\\4@" "$arquivo"; then
                reconhecidos=$((reconhecidos + 1))
            else
                falhas=1
            fi
        elif grep -Eq "${inicio}5${fim}" "$arquivo" || grep -Eq "$nosso" "$arquivo"; then
            reconhecidos=$((reconhecidos + 1))
        fi
    done
    if [[ $acao == aplicar && $reconhecidos == 0 ]]; then
        printf 'Callas KDE: formato da contagem não reconhecido no Plasma instalado.\n' >&2
        return 1
    fi
    return "$falhas"
}

como_login() { /usr/bin/runuser -u "$usuario_login" -- "$@"; }

localizar_config_login() {
    local conta pasta_login uid
    case $usuario_login in
        plasmalogin|sddm) ;;
        *) erro 'conta de login inválida no backup.' ;;
    esac
    conta=$(/usr/bin/getent passwd "$usuario_login") || erro "conta $usuario_login não encontrada."
    IFS=: read -r _ _ uid _ _ pasta_login _ <<< "$conta"
    [[ $uid =~ ^[1-9][0-9]*$ && $pasta_login == "/var/lib/$usuario_login" ]] ||
        erro "pasta ou conta de sistema inesperada para $usuario_login."
    destino=$pasta_login/.config/kwinoutputconfig.json
}

ler_sddm() {
    local arquivo
    for arquivo in /usr/lib/sddm/sddm.conf.d/*.conf /etc/sddm.conf.d/*.conf /etc/sddm.conf; do
        [[ -f $arquivo ]] || continue
        printf '\n[General]\n'
        cat -- "$arquivo"
    done | awk -v secao="$1" -v chave="$2" -v valor="$3" '
        /^[[:space:]]*[#;]/ { next }
        { sub(/^[[:space:]]+/, ""); sub(/[[:space:]]+$/, "") }
        /^\[/ { grupo = $0; next }
        grupo == "[" secao "]" && $0 ~ ("^" chave "[[:space:]]*=") {
            sub(/^[^=]*=[[:space:]]*/, "")
            sub(/^"/, "")
            sub(/"$/, "")
            valor = $0
        }
        END { print valor }
    '
}

configurar_sddm_x11() {
    local principal=$1 caminho edid='' encontrado anterior
    [[ -x /usr/bin/xrandr ]] || erro 'SDDM em X11 precisa do pacote xorg-xrandr. Instale com sudo pacman -S --needed xorg-xrandr.'
    for caminho in /sys/class/drm/card*-"$principal"/edid; do
        [[ -r $caminho ]] || continue
        encontrado=$(od -An -v -tx1 -- "$caminho" | tr -d '[:space:]')
        [[ -n $encontrado ]] || continue
        [[ -z $edid || $edid == "$encontrado" ]] || erro 'há duas telas com esse nome. O login foi preservado.'
        edid=$encontrado
    done
    [[ -n $edid ]] || erro "identificação física do monitor $principal indisponível."

    anterior=$(ler_sddm X11 DisplayCommand /usr/share/sddm/scripts/Xsetup)
    if [[ $anterior == "$xsetup" && -f $estado/sddm-comando-original ]]; then
        anterior=$(< "$estado/sddm-comando-original")
    fi
    [[ $anterior == /* && $anterior != "$xsetup" && -x $anterior ]] ||
        erro "o comando de tela do SDDM é incompatível ($anterior)."
    if [[ -e $sddm_conf ]] && ! grep -Fxq '# Gerenciado por Callas KDE' "$sddm_conf"; then
        erro "já existe um arquivo personalizado em $sddm_conf."
    fi
    install -d -m 0755 "${xsetup%/*}" "${sddm_conf%/*}"
    printf '%s\n' "$anterior" > "$estado/sddm-comando-original"
    {
        printf '#!/usr/bin/bash\ncomando_original=%q\nedid_alvo=%q\n' "$anterior" "$edid"
        cat <<'XSETUP'
"$comando_original" "$@" || exit $?
saidas=$(/usr/bin/xrandr --prop) || exit 0
monitor=$(awk -v alvo="$edid_alvo" '
    function guardar() {
        if (saida != "" && edid == alvo) { principal = saida; quantidade++ }
    }
    /^[^[:space:]]/ {
        guardar()
        saida = ($2 == "connected") ? $1 : ""
        edid = ""
        lendo = 0
        next
    }
    $1 == "EDID:" { lendo = 1; next }
    lendo && NF == 1 && $1 ~ /^[[:xdigit:]]+$/ { edid = edid tolower($1); next }
    { lendo = 0 }
    END { guardar(); if (quantidade == 1) print principal }
' <<< "$saidas")
[[ -n $monitor ]] || exit 0
args=(--output "$monitor" --auto --primary --pos 0x0)
anterior=$monitor
while read -r saida; do
    [[ $saida != "$monitor" ]] || continue
    args+=(--output "$saida" --auto --right-of "$anterior")
    anterior=$saida
done < <(awk '$2 == "connected" { print $1 }' <<< "$saidas")
/usr/bin/xrandr "${args[@]}" || /usr/bin/xrandr --output "$monitor" --primary || :
XSETUP
    } > "$estado/sddm-xsetup"
    install -m 0755 "$estado/sddm-xsetup" "$xsetup"
    printf '# Gerenciado por Callas KDE\n[X11]\nDisplayCommand=%s\n' "$xsetup" > "$estado/sddm-conf"
    install -m 0644 "$estado/sddm-conf" "$sddm_conf"
    if [[ $(ler_sddm X11 DisplayCommand /usr/share/sddm/scripts/Xsetup) != "$xsetup" ]]; then
        rm -f -- "$sddm_conf" "$xsetup"
        erro 'uma configuração do SDDM tem prioridade sobre o ajuste. O login foi preservado.'
    fi
    rm -f -- "$estado/sddm-conf" "$estado/sddm-xsetup"
}

remover_xsetup() {
    if [[ -f $sddm_conf ]] && grep -Fxq '# Gerenciado por Callas KDE' "$sddm_conf"; then
        rm -f -- "$sddm_conf"
    fi
    if [[ -f $estado/sddm-comando-original ]]; then
        rm -f -- "$xsetup" "$estado/sddm-comando-original"
    fi
}

# O Breeze desenha o wallpaper fora do MouseArea que contém os controles.
# A marca permite reaplicar e desfazer sem restaurar versões antigas do tema.
ajustar_tema_sddm() {
    local acao=$1 arquivo=$2 alvo=${3:-} temporario
    [[ -f $arquivo && ! -L $arquivo ]] || return 1
    if [[ $acao == aplicar ]] && ! awk '
        /^[[:space:]]*id:[[:space:]]*wallpaper[[:space:]]*$/ { wallpaper = 1 }
        /^[[:space:]]*id:[[:space:]]*loginScreenRoot[[:space:]]*$/ {
            total++
            if (wallpaper && anterior ~ /^[[:space:]]*MouseArea[[:space:]]*\{[[:space:]]*$/) valido++
        }
        { anterior = $0 }
        END { exit !(total == 1 && valido == 1) }
    ' "$arquivo"; then
        printf 'Callas KDE: não reconheci o formato do tema %s.\n' "$arquivo" >&2
        return 1
    fi
    temporario=$(mktemp -- "${arquivo%/*}/.callas-tema.XXXXXXXX") || return 1
    if ! awk -v acao="$acao" -v alvo="$alvo" '
        /^[[:space:]]*\/\/ Callas KDE: inicio do login por tela[[:space:]]*$/ { bloco = 1; next }
        /^[[:space:]]*\/\/ Callas KDE: fim do login por tela[[:space:]]*$/ { bloco = 0; next }
        bloco || /^import QtQuick.Window \/\/ Callas KDE$/ { next }

        # O Breeze usa WallpaperFader para escurecer/desfocar o fundo enquanto
        # os controles de login estão visíveis. Mantemos a imagem original nítida.
        /^[[:space:]]*WallpaperFader[[:space:]]*\{/ { fader = 1 }
        acao == "desfazer" && /visible:[[:space:]]*false[[:space:]]*\/\/ Callas KDE: wallpaper nitido/ {
            sub(/visible:[[:space:]]*false[[:space:]]*\/\/ Callas KDE: wallpaper nitido/,
                "visible: config.type == \"image\"")
            print
            fader = 0
            next
        }
        acao == "aplicar" && fader && /^[[:space:]]*visible:[[:space:]]*config\.type[[:space:]]*={2,3}[[:space:]]*"image"/ {
            sub(/visible:.*/, "visible: false // Callas KDE: wallpaper nitido")
            print
            fader = 0
            next
        }

        {
            if (acao == "aplicar" && ! importado && /^import QtQuick([[:space:]]|$)/) {
                print "import QtQuick.Window // Callas KDE"
                importado = 1
            }
            print
        }
        acao == "aplicar" && /^[[:space:]]*id:[[:space:]]*loginScreenRoot[[:space:]]*$/ {
            print "        // Callas KDE: inicio do login por tela"
            print "        visible: {"
            print "            const telas = Qt.application.screens"
            print "            const atual = Screen.name"
            print "            if (telas.length < 2 || atual === \"\") return true"
            print "            const alvo = \"" alvo "\""
            print "            for (let i = 0; alvo !== \"\" && i < telas.length; ++i) {"
            print "                if (telas[i].name === alvo) return atual === alvo"
            print "            }"
            print "            return atual === telas[0].name"
            print "        }"
            print "        enabled: visible"
            print "        // Callas KDE: fim do login por tela"
        }
        END { if (bloco || (acao == "aplicar" && !importado)) exit 1 }
    ' "$arquivo" > "$temporario" ||
        ! chmod --reference="$arquivo" "$temporario" ||
        ! chown --reference="$arquivo" "$temporario" ||
        ! mv -fT -- "$temporario" "$arquivo"; then
        rm -f -- "$temporario"
        return 1
    fi
}

instalar_tema_sddm() {
    local alvo=$1 tema pasta arquivo anterior selecionar_breeze=0
    tema=$(ler_sddm Theme Current '')
    pasta=$(ler_sddm Theme ThemeDir /usr/share/sddm/themes)
    if [[ -z $tema ]]; then
        tema=breeze
        selecionar_breeze=1
    fi
    [[ $tema =~ ^[[:alnum:]_.-]+$ && $pasta == /usr/share/sddm/themes ]] ||
        erro 'o SDDM precisa estar usando um tema Breeze instalado para aplicar este ajuste.'
    arquivo=$(realpath -e -- "$pasta/$tema/Main.qml") || erro "não encontrei o Main.qml do tema $tema."
    [[ $arquivo =~ ^/usr/share/sddm/themes/[[:alnum:]_.-]+/Main\.qml$ ]] ||
        erro "local inesperado do tema $tema."
    if [[ -f $estado/sddm-tema ]]; then
        anterior=$(< "$estado/sddm-tema")
        if [[ $anterior != "$arquivo" && -f $anterior ]]; then
            ajustar_tema_sddm desfazer "$anterior"
        fi
    fi
    ajustar_tema_sddm aplicar "$arquivo" "$alvo" || erro 'o tema do SDDM ficou com seu comportamento original.'
    printf '%s\n' "$arquivo" > "$estado/sddm-tema"
    if (( selecionar_breeze )); then
        install -d -m 0755 "${sddm_breeze%/*}"
        if [[ -e $sddm_breeze ]] && ! grep -Fxq '# Tema gerenciado por Callas KDE' "$sddm_breeze"; then
            erro "já existe uma configuração de tema em $sddm_breeze."
        fi
        printf '# Tema gerenciado por Callas KDE\n[Theme]\nCurrent=breeze\n' > "$estado/breeze-conf"
        install -m 0644 "$estado/breeze-conf" "$sddm_breeze"
        rm -f -- "$estado/breeze-conf"
        if [[ $(ler_sddm Theme Current '') != breeze ]]; then
            rm -f -- "$sddm_breeze"
            ajustar_tema_sddm desfazer "$arquivo"
            rm -f -- "$estado/sddm-tema"
            erro 'o SDDM tem uma configuração de tema com prioridade. Selecione Breeze no KDE e rode novamente.'
        fi
    fi
    {
        printf '#!/usr/bin/env bash\nset -u\n'
        declare -f ajustar_tema_sddm
        printf 'ajustar_tema_sddm aplicar %q %q\n' "$arquivo" "$alvo"
    } > "$estado/auxiliar-tema"
    install -m 0755 "$estado/auxiliar-tema" /usr/local/lib/callas-kde/ajustar-tema-sddm
    cat > "$estado/hook-tema" <<HOOK_TEMA
[Trigger]
Operation = Install
Operation = Upgrade
Type = Path
Target = ${arquivo#/}

[Action]
Description = Reaplicando o login do KDE no monitor principal...
When = PostTransaction
Exec = /usr/local/lib/callas-kde/ajustar-tema-sddm
HOOK_TEMA
    install -m 0644 "$estado/hook-tema" /etc/pacman.d/hooks/99-callas-kde-tema-sddm.hook
    rm -f -- "$estado/auxiliar-tema" "$estado/hook-tema"
}

restaurar_layout_login() {
    [[ -f $estado/login-original.json || -f $estado/login-ausente ]] || return 0
    local usuario_login=plasmalogin destino
    if [[ -f $estado/login-conta ]]; then
        usuario_login=$(< "$estado/login-conta")
    fi
    localizar_config_login
    if [[ -f $estado/login-original.json ]]; then
        gravar_login < "$estado/login-original.json"
    else
        como_login /usr/bin/rm -f -- "$destino"
    fi
    rm -f -- "$estado/login-original.json" "$estado/login-ausente" "$estado/login-conta"
}

gravar_login() {
    # A pasta pertence ao greeter. A gravação também roda como greeter.
    como_login /usr/bin/bash -eu -c '
        umask 077
        destino=$1
        mkdir -p -- "${destino%/*}"
        temporario=$(mktemp -- "${destino%/*}/.callas-kwin.XXXXXXXX")
        trap '\''rm -f -- "$temporario"'\'' EXIT
        cat > "$temporario"
        mv -fT -- "$temporario" "$destino"
    ' bash "$destino"
}

modo_sistema() (
    local acao=$1 principal=${2:-} usuario_login=plasmalogin destino modo compositor
    local resultado=0 somente_monitor=0
    if [[ $acao == monitor ]]; then somente_monitor=1; acao=aplicar; fi
    local estado=/var/lib/callas-kde-desligamento-login
    local auxiliar=/usr/local/lib/callas-kde/ajustar-contagem
    local hook=/etc/pacman.d/hooks/99-callas-kde-contagem.hook
    local sddm_conf=/etc/sddm.conf.d/99-callas-kde-monitor.conf
    local sddm_breeze=/etc/sddm.conf.d/99-callas-kde-breeze.conf
    local xsetup=/usr/local/lib/callas-kde/sddm-xsetup

    /usr/bin/install -d -m 0700 "$estado"
    exec 9>"$estado/lock"
    /usr/bin/flock -x 9

    if [[ $acao == desfazer ]]; then
        rm -f -- "$hook"
        ajustar_contagem desfazer
        rm -f -- "$auxiliar"
        remover_xsetup
        if [[ -f $sddm_breeze ]] && grep -Fxq '# Tema gerenciado por Callas KDE' "$sddm_breeze"; then
            rm -f -- "$sddm_breeze"
        fi
        rm -f -- /etc/pacman.d/hooks/99-callas-kde-tema-sddm.hook /usr/local/lib/callas-kde/ajustar-tema-sddm
        if [[ -f $estado/sddm-tema ]]; then
            local tema_anterior
            tema_anterior=$(< "$estado/sddm-tema")
            if [[ -f $tema_anterior ]]; then
                ajustar_tema_sddm desfazer "$tema_anterior"
            fi
            rm -f -- "$estado/sddm-tema"
        fi
        restaurar_layout_login
        printf 'Ajustes desfeitos. O login usa a configuração restaurada na próxima vez.\n'
        return
    fi

    local novo
    novo=$(mktemp -- "$estado/.novo.XXXXXXXX")
    trap 'rm -f -- "$novo"' EXIT
    cat > "$novo"
    remover_xsetup

    if (( ! somente_monitor )); then
    ajustar_contagem aplicar || resultado=1
    install -d -m 0755 /usr/local/lib/callas-kde /etc/pacman.d/hooks
    {
        printf '#!/usr/bin/env bash\nset -u\n'
        declare -f ajustar_contagem
        printf 'ajustar_contagem aplicar\n'
    } > "$estado/auxiliar"
    install -m 0755 "$estado/auxiliar" "$auxiliar"
    cat > "$estado/hook" <<'HOOK'
[Trigger]
Operation = Install
Operation = Upgrade
Type = Path
Target = usr/share/plasma/shells/org.kde.plasma.desktop/contents/logout/Logout.qml
Target = usr/share/plasma/shells/org.kde.plasma.desktop/contents/logout/LogoutControls.qml
Target = usr/share/plasma/look-and-feel/org.kde.breeze.desktop/contents/logout/Logout.qml

[Action]
Description = Reaplicando a contagem de 5 segundos do KDE...
When = PostTransaction
Exec = /usr/local/lib/callas-kde/ajustar-contagem
HOOK
    install -m 0644 "$estado/hook" "$hook"
    rm -f -- "$estado/auxiliar" "$estado/hook"
    if (( resultado == 0 )); then
        printf 'Contagem do KDE ajustada para 5 segundos.\n'
    fi

    fi

    if [[ $acao == instalar ]]; then
        instalar_tema_sddm "$principal"
        printf 'SDDM preparado. O formulário fica na saída principal e as outras exibem o wallpaper.\n'
        return "$resultado"
    fi

    if systemctl is-active --quiet plasmalogin.service; then
        if ! /usr/bin/getent passwd plasmalogin >/dev/null; then
            [[ -f /usr/lib/sysusers.d/plasmalogin.conf ]] ||
                erro 'o Plasma Login está ativo, mas a definição da conta do pacote está ausente.'
            systemd-sysusers plasmalogin.conf
            if [[ -f /usr/lib/tmpfiles.d/plasmalogin.conf ]]; then
                systemd-tmpfiles --create plasmalogin.conf
            fi
        fi
    elif systemctl is-active --quiet sddm.service; then
        modo=$(ler_sddm General DisplayServer x11)
        case $modo in
            x11|x11-user)
                restaurar_layout_login
                configurar_sddm_x11 "$principal"
                instalar_tema_sddm ''
                printf 'SDDM: formulário no %s e wallpaper nas duas telas. Confira no próximo login.\n' "$principal"
                return "$resultado"
                ;;
            wayland)
                compositor=$(ler_sddm Wayland CompositorCommand '')
                [[ ${compositor%% *} == kwin_wayland || ${compositor%% *} == /usr/bin/kwin_wayland ]] ||
                    erro 'o SDDM em Wayland usa um compositor diferente do KWin.'
                usuario_login=sddm
                ;;
            *) erro "modo do SDDM desconhecido ($modo)." ;;
        esac
    else
        erro 'gerenciador de login ativo diferente de Plasma Login e SDDM. Rode systemctl status display-manager para identificá-lo.'
    fi

    if [[ ! -s $novo ]]; then
        restaurar_layout_login
        erro 'restaurei o layout anterior. Para aplicar o novo, deixe as duas telas ligadas e ativas na sessão Plasma.'
    fi
    localizar_config_login
    if [[ -f $estado/login-original.json || -f $estado/login-ausente ]]; then
        local conta_backup=plasmalogin
        if [[ -f $estado/login-conta ]]; then
            conta_backup=$(< "$estado/login-conta")
        fi
        [[ $conta_backup == "$usuario_login" ]] || erro 'o gerenciador mudou desde a última aplicação. Desfaça o ajuste anterior antes de reaplicar.'
    else
        printf '%s\n' "$usuario_login" > "$estado/login-conta"
        if como_login /usr/bin/test -e "$destino"; then
            como_login /usr/bin/cat -- "$destino" > "$estado/login-backup.tmp"
            mv -fT -- "$estado/login-backup.tmp" "$estado/login-original.json"
        else
            touch "$estado/login-ausente"
        fi
    fi
    gravar_login < "$novo"
    if [[ $usuario_login == sddm ]]; then
        instalar_tema_sddm "$principal"
        printf 'SDDM: formulário no %s e wallpaper nas duas telas. Confira no próximo login.\n' "$principal"
    else
        printf 'Plasma Login: %s como principal, com as duas telas ligadas. O formulário nativo pode acompanhar o ponteiro.\n' "$principal"
    fi
    return "$resultado"
)

preparar_login() {
    /usr/bin/python3 - "${XDG_CONFIG_HOME:-$HOME/.config}/kwinoutputconfig.json" "$1" <<'PYTHON'
import json
from pathlib import Path
import re
import sys


def normalizar(nome):
    return re.sub(r"^HDMI-A-(?=\d+$)", "HDMI-", nome)


def configurar(origem, principal):
    principal = normalizar(principal)
    conectados = {
        normalizar(status.parent.name.split("-", 1)[1])
        for status in Path("/sys/class/drm").glob("card*-*/status")
        if status.read_text().strip() == "connected"
    }
    if principal not in conectados or len(conectados) < 2:
        raise ValueError("conecte os dois monitores e confira o nome da saída principal.")

    config = json.loads(origem.read_text())
    secoes = {secao["name"]: secao["data"] for secao in config}
    saidas = secoes["outputs"]
    perfis_ajustados = 0
    for perfil in secoes["setups"]:
        monitores = perfil["outputs"]
        indices = [monitor["outputIndex"] for monitor in monitores]
        if any(type(indice) is not int or not 0 <= indice < len(saidas) for indice in indices):
            raise ValueError("o KWin salvou um índice de monitor inválido.")
        nomes = [normalizar(saidas[indice].get("connectorName", "")) for indice in indices]
        if len(nomes) != len(conectados) or set(nomes) != conectados:
            continue
        if not all(monitor.get("enabled") for monitor in monitores):
            continue
        if any(monitor.get("replicationSource") for monitor in monitores):
            continue
        ordenados = sorted(zip(monitores, nomes), key=lambda par: par[1] != principal)
        for prioridade, (monitor, _) in enumerate(ordenados):
            monitor["priority"] = prioridade
        perfis_ajustados += 1

    if not perfis_ajustados:
        raise ValueError("nenhum perfil do KWin corresponde aos monitores conectados.")
    return config


try:
    config = configurar(Path(sys.argv[1]), sys.argv[2])
except (OSError, ValueError, TypeError, KeyError) as erro:
    sys.exit(f"Erro ao preparar o login: {erro}")
json.dump(config, sys.stdout, indent=4)
print()
PYTHON
}

if [[ ${1:-} == --preparar-instalacao && $EUID == 0 && $# == 1 ]]; then
    modo_sistema instalar '' </dev/null
    exit
fi

if [[ ${1:-} == --sistema && $EUID == 0 && $# -ge 2 ]]; then
    case $2 in
        aplicar|monitor)
            [[ $# == 3 && $3 =~ ^[[:alnum:]]+(-[[:alnum:]]+)+$ ]] || erro 'saída inválida.'
            modo_sistema "$2" "$3"
            exit
            ;;
        desfazer) modo_sistema desfazer; exit ;;
    esac
fi
[[ $EUID != 0 ]] || erro 'rode com bash no Konsole, como seu usuário. O script pede sudo quando precisar.'
acao_usuario=aplicar
if [[ ${1:-} == --monitor ]]; then acao_usuario=monitor; shift; fi
[[ $# -le 1 ]] || erro 'use bash callas-kde-desligamento-login.sh [DP-3|--desfazer].'
[[ -f /etc/arch-release ]] || erro 'este script é para Arch Linux.'
script=$(realpath -- "${BASH_SOURCE[0]}")
if [[ ${1:-} == --desfazer ]]; then
    exec sudo /usr/bin/bash -- "$script" --sistema desfazer
fi
[[ ${XDG_SESSION_TYPE:-} == wayland ]] || erro 'rode dentro da sessão Plasma Wayland.'
principal=${1:-DP-3}
[[ $principal =~ ^[[:alnum:]]+(-[[:alnum:]]+)+$ ]] || erro 'informe uma saída como DP-3.'
novo_login=$(mktemp)
trap 'rm -f -- "$novo_login"' EXIT
if [[ -x /usr/bin/python3 ]]; then
    if ! preparar_login "$principal" > "$novo_login"; then
        : > "$novo_login"
    fi
fi
printf 'Monitor escolhido para o login: %s\n' "$principal"
sudo -v
sudo /usr/bin/bash -- "$script" --sistema "$acao_usuario" "$principal" < "$novo_login"
