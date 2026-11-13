#!/usr/bin/env bash
set -euo pipefail
export PATH=/usr/bin:/bin

program=/usr/local/libexec/put-update
atalho_menu=/usr/local/share/applications/io.github.Callas157.AtualizadorDoSistema.desktop
servico_check=put-update-check.service
timer_check=put-update-check.timer
agenda_dir=/var/lib/put-update/agenda
lock_atualizador=/run/put-update.lock
builder=put-aur
builder_home=/var/lib/put-update/aur
paru_conf=/etc/put-update-paru.conf
sudo_template=/etc/put-update-aur.sudoers
sudo_rule=/etc/sudoers.d/put-update
config_update_url=https://raw.githubusercontent.com/Callas157/arch-install/main/programas-callas-os/atualizador/callas-config-update.sh

erro() {
    printf 'Erro: %s\n' "$*" >&2
    exit 1
}

proxima_data() {
    local modo=$1 base=$2
    case $modo in
        apps) TZ=UTC0 date -d "$base +7 days" +%F ;;
        sistema) python - "$base" <<'MONTH'
import calendar, datetime, sys
d=datetime.date.fromisoformat(sys.argv[1]); y=d.year+(d.month==12); m=d.month%12+1
print(datetime.date(y,m,min(d.day,calendar.monthrange(y,m)[1])).isoformat())
MONTH
        ;;
        *) erro 'Agenda inválida.' ;;
    esac
}

ler_data_agenda() {
    local data
    read -r data < "$agenda_dir/$1" || erro "Não foi possível ler a agenda de $1."
    [[ $data =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || erro "Data inválida na agenda de $1."
    printf '%s\n' "$data"
}

gravar_data_agenda() {
    local temporario
    temporario=$(mktemp -- "$agenda_dir/.data.XXXXXXXX")
    printf '%s\n' "$2" > "$temporario"
    mv -fT -- "$temporario" "$agenda_dir/$1"
}

preparar_agenda() {
    local inicio modo data
    install -d -m 0700 -- "$agenda_dir"
    if [[ ! -e $agenda_dir/inicio ]]; then
        data=$(date +%F)
        gravar_data_agenda inicio "$data"
    fi
    inicio=$(ler_data_agenda inicio)
    for modo in sistema apps; do
        if [[ ! -e $agenda_dir/$modo ]]; then
            data=$(proxima_data "$modo" "$inicio")
            gravar_data_agenda "$modo" "$data"
        fi
    done
}

executar_agendado() {
    local usuario=$1 modo=$2 hoje vencimento proxima
    hoje=$(date +%F)
    vencimento=$(ler_data_agenda "$modo")

    # A data funciona como vencimento, não como uma janela de 24 horas.
    # Se o computador ficou desligado no dia previsto, a atualização roda
    # no primeiro boot/verificação seguinte.
    [[ $hoje < $vencimento ]] && return 0

    if registrar_atualizacao "$usuario" "$modo" automatico; then
        # O próximo ciclo começa no dia em que a atualização realmente terminou.
        proxima=$(proxima_data "$modo" "$hoje")
        gravar_data_agenda "$modo" "$proxima"
        [[ $modo != sistema ]] || gravar_data_agenda apps "$(proxima_data apps "$hoje")"
    else
        local codigo=$?
        if [[ $modo == apps && $codigo == 2 ]]; then
            # Expected deferral to the next General update; don't retry hourly.
            gravar_data_agenda apps "$(proxima_data apps "$hoje")"
            return 0
        fi
        return "$codigo"
    fi
}

verificar_agenda() {
    local usuario=$1 falhou=0
    executar_agendado "$usuario" sistema || return 1
    executar_agendado "$usuario" apps || falhou=1
    return "$falhou"
}

home_do_usuario() {
    local home
    home=$(getent passwd "$1" | cut -d: -f6) || erro "Usuário $1 indisponível."
    [[ -d "$home" ]] || erro "Pasta pessoal de $1 indisponível."
    printf '%s\n' "$home"
}

como_usuario() {
    local usuario=$1 home=$2
    shift 2
    runuser -u "$usuario" -- env -i PATH=/usr/bin HOME="$home" \
        USER="$usuario" LOGNAME="$usuario" LANG=C.UTF-8 "$@"
}

pasta_de_documentos() {
    local documentos
    documentos=$(xdg-user-dir DOCUMENTS 2>/dev/null) || documentos=
    if [[ "$documentos" != /* || "${documentos%/}" == "$HOME" ]]; then
        documentos="$HOME/Documentos"
        if [[ ! -d "$documentos" && -d "$HOME/Documents" ]]; then
            documentos="$HOME/Documents"
        fi
    fi
    printf '%s\n' "${documentos%/}"
}

pasta_de_logs() {
    /usr/local/libexec/callas-logs --prepare
}

etapa() {
    local nome=$1
    shift
    printf '\n==> %s\n' "$nome"
    if "$@"; then
        return 0
    else
        local codigo=$?
        printf 'Falha em %s (código %s).\n' "$nome" "$codigo" >&2
        return "$codigo"
    fi
}

atualizar_arch() {
    mountpoint -q /boot || { printf 'A partição /boot não está montada; atualização geral interrompida antes do pacman.\n' >&2; return 1; }
    local origem=$1 dbpath tentativa
    local -a dependencias=() confirmacao=(--noconfirm)
    dbpath=$(pacman-conf DBPath) || return
    for (( tentativa=0; tentativa<12; tentativa++ )); do
        [[ -e "${dbpath%/}/db.lck" ]] || break
        sleep 10
    done
    if [[ -e "${dbpath%/}/db.lck" ]]; then
        printf 'O pacman ainda está ocupado ou deixou um lock pendente.\n' >&2
        return 1
    fi

    if [[ -x /usr/bin/paru && -f "$paru_conf" ]]; then
        pacman -Qq base-devel >/dev/null 2>&1 || dependencias+=(base-devel)
        pacman -Qq git >/dev/null 2>&1 || dependencias+=(git)
    fi
    if [[ -r /etc/callas-nvidia-version ]]; then
        CALLAS_KERNEL_UPDATE_CONTEXT=general pacman -Syu --needed --ignore=nvidia-utils,nvidia-open-dkms,nvidia-open,nvidia-open-lts,lib32-nvidia-utils,nvidia-settings,libxnvctrl,opencl-nvidia,lib32-opencl-nvidia "${confirmacao[@]}" "${dependencias[@]}" || return

        # Antes de considerar a atualização concluída, garante que o NVIDIA
        # fixado ainda foi compilado para todos os kernels linux/linux-lts.
        local pkgbase release falhou_modulo=0
        for pkgbase in /usr/lib/modules/*/pkgbase; do
            [[ -f $pkgbase ]] || continue
            case $(<"$pkgbase") in
                linux|linux-lts) ;;
                *) continue ;;
            esac
            release=${pkgbase%/pkgbase}
            release=${release##*/}
            if ! dkms autoinstall -k "$release"; then
                printf 'DKMS falhou para o kernel instalado %s. Não reinicie antes de corrigir.\n' "$release" >&2
                falhou_modulo=1
            fi
            if ! modinfo -k "$release" nvidia >/dev/null 2>&1; then
                printf 'NVIDIA %s não está disponível para o kernel %s. Não reinicie antes de corrigir.\n'                     "$(< /etc/callas-nvidia-version)" "$release" >&2
                falhou_modulo=1
            fi
        done
        (( falhou_modulo == 0 )) || return 1
    else
        CALLAS_KERNEL_UPDATE_CONTEXT=general pacman -Syu --needed "${confirmacao[@]}" "${dependencias[@]}"
    fi
}

atualizar_aur() (
    local temporario codigo=0
    temporario=$(mktemp /var/tmp/callas-aur-log.XXXXXXXX)
    trap 'rm -f -- "$temporario"' EXIT
    /usr/local/libexec/callas-aur "$@" 2>&1 | tee "$temporario" || codigo=$?
    /usr/local/libexec/callas-logs --record AUR < "$temporario" || codigo=1
    exit "$codigo"
)

atualizar_discord_integrado() (
    falhar() {
        printf 'Erro: %s\n' "$*" >&2
        exit 1
    }

    case "${1:-}" in
        "") acao=atualizar ;;
        --pacman) acao=pacman ;;
        --agendado) acao=agendado ;;
        --sessao) acao=sessao ;;
        -h|--help)
            printf 'Uso: bash %s --discord [--pacman]\n' "${0##*/}"
            printf 'Atualiza somente o Discord nativo.\n'
            exit 0
            ;;
        *) falhar "Opção desconhecida: $1. Use --help." ;;
    esac
    [[ $# -le 1 ]] || falhar 'Passe apenas uma opção.'
    (( EUID != 0 )) || falhar 'Rode com seu usuário normal. O modo --pacman pede sudo quando necessário.'

    config_dir=${XDG_CONFIG_HOME:-"$HOME/.config"}
    discord_dir="$config_dir/discord"
    aviso_discord='Discord Stable nativo não encontrado no perfil. Abra o Discord pelo menu, aguarde a janela principal carregar e tente novamente.'
    [[ -d $discord_dir ]] || {
        [[ $acao == agendado ]] && { printf '%s\n' "$aviso_discord"; return 0; }
        falhar "$aviso_discord"
    }

    if ! lancador=$(command -v discord); then
        for candidato in /opt/Discord/Discord /opt/discord/Discord /usr/share/discord/Discord /usr/lib/discord/Discord; do
            [[ -x $candidato ]] && { lancador=$candidato; break; }
        done
    fi
    [[ -n ${lancador:-} ]] || falhar 'O lançador nativo discord não foi encontrado.'

    pids_discord() {
        pgrep -u "$EUID" -x 'Discord|discord' || true
    }

    estava_aberto=0
    if [[ -n $(pids_discord) ]]; then
        estava_aberto=1
        printf 'Fechando o Discord para atualizar...\n'
        kill -TERM $(pids_discord) 2>/dev/null || true
        for _ in {1..40}; do
            [[ -z $(pids_discord) ]] && break
            sleep 0.25
        done
        [[ -z $(pids_discord) ]] || falhar 'O Discord ainda está aberto.'
    fi

    reabrir() {
        (( estava_aberto )) || return 0
        printf 'Reabrindo o Discord...\n'
        if [[ $acao == agendado || $acao == sessao ]]; then
            systemd-run --user --collect --slice=app.slice --property=Type=exec \
                -- "$lancador" --start-minimized >/dev/null 2>&1 || return 1
        else
            nohup "$lancador" --start-minimized </dev/null >/dev/null 2>&1 &
        fi
    }
    trap reabrir EXIT

    if [[ $acao == pacman ]]; then
        pacman -Q discord >/dev/null || falhar 'O pacote discord não está instalado pelo pacman.'
        sudo /usr/local/libexec/callas-native --install discord || falhar 'Falha na instalação pontual do Discord; nenhuma atualização geral foi iniciada.'
    fi

    bootstrap=
    for candidato in "$(dirname -- "$(realpath -- "$lancador")")/updater_bootstrap" \
        /usr/share/discord/updater_bootstrap /opt/Discord/updater_bootstrap /opt/discord/updater_bootstrap; do
        [[ -x $candidato ]] && { bootstrap=$candidato; break; }
    done

    if [[ -n $bootstrap ]]; then
        printf 'Verificando atualização do Discord nativo...\n'
        timeout --kill-after=10s 10m "$bootstrap" --no-zenity \
            "$discord_dir" stable https://updates.discord.com/ >/dev/null ||
            falhar 'A atualização do Discord nativo falhou.'
    else
        printf 'Atualizador interno do Discord não encontrado; o pacote será mantido pelo pacman/AUR.\n'
    fi
)

criar_ponto_recuperacao() {
    /usr/local/libexec/callas-storage --system "$1"
}

notificar_reinicio_usuario() {
    local estado acao boot_pendente
    (( EUID != 0 )) || erro 'A notificação deve rodar na sessão do usuário.'
    estado="${XDG_STATE_HOME:-$HOME/.local/state}/callas/reinicio-pendente"
    [[ -f $estado ]] || return 0
    read -r boot_pendente < "$estado" || boot_pendente=
    if [[ $boot_pendente != "$(cat /proc/sys/kernel/random/boot_id)" ]]; then
        rm -f -- "$estado"
        return 0
    fi

    if command -v notify-send >/dev/null; then
        acao=$(notify-send -a 'Atualizador do sistema' -i system-reboot -u normal \
            -A reiniciar='Reiniciar agora' -A depois='Mais tarde' \
            'Atualização geral concluída' \
            'Sistema, AUR e aplicativos atualizados; verificações concluídas. Deseja reiniciar?' || true)
    else
        acao=
    fi
    rm -f -- "$estado"
    if [[ $acao == reiniciar ]]; then
        systemctl --quiet reboot --check-inhibitors=no --no-wall
    fi
}

marcar_reinicio_pendente() {
    local usuario=$1 home=$2 uid runtime estado grupo
    uid=$(id -u "$usuario") || return 1
    grupo=$(id -gn "$usuario") || return 1
    estado="$home/.local/state/callas"
    como_usuario "$usuario" "$home" /usr/bin/bash -c '
      umask 077
      mkdir -p -- "$1"
      cat /proc/sys/kernel/random/boot_id > "$1/reinicio-pendente"
    ' bash "$estado"

    runtime="/run/user/$uid"
    if [[ -S "$runtime/bus" ]]; then
        runuser -u "$usuario" -- env \
            HOME="$home" USER="$usuario" LOGNAME="$usuario" \
            XDG_RUNTIME_DIR="$runtime" DBUS_SESSION_BUS_ADDRESS="unix:path=$runtime/bus" \
            systemd-run --user --collect --unit=callas-update-reinicio \
            "$program" --notificar-reinicio >/dev/null 2>&1 || :
    fi
}

notificar_apps_usuario() {
    local usuario=$1 home=$2 uid runtime titulo='Aplicativos atualizados' mensagem='Os aplicativos foram atualizados com sucesso.'
    if [[ ${3:-apps} == flatpaks ]]; then
        titulo='Flatpaks atualizados'
        mensagem='Os Flatpaks foram atualizados com sucesso.'
    fi
    uid=$(id -u "$usuario") || return 1
    runtime="/run/user/$uid"
    [[ -S "$runtime/bus" ]] || return 0
    runuser -u "$usuario" -- env \
        HOME="$home" USER="$usuario" LOGNAME="$usuario" \
        XDG_RUNTIME_DIR="$runtime" DBUS_SESSION_BUS_ADDRESS="unix:path=$runtime/bus" \
        notify-send -a 'Atualizador do sistema' -i system-software-update \
        "$titulo" \
        "$mensagem" >/dev/null 2>&1 || :
}

atualizar_sistema() {
    local origem=$1 usuario=$2 home=$3 falhou=0
    etapa 'Ponto de recuperação pré-update' criar_ponto_recuperacao "$usuario" || return
    etapa 'Arch e aplicativos dos repositórios' atualizar_arch "$origem" || return
    etapa 'AUR e recompilações necessárias' atualizar_aur || falhou=1
    etapa 'Flatpaks e Discord' atualizar_apps "$usuario" "$home" || falhou=1
    # Always validate boot at the end, even if an application failed earlier.
    etapa 'Kernels padrão/LTS, DKMS e boot' /usr/local/libexec/callas-kernel-check || falhou=1
    return "$falhou"
}

atualizar_flatpaks() {
    local usuario=$1 home=$2 falhou=0

    if [[ -x /usr/bin/flatpak ]]; then
        etapa 'Flatpaks do sistema' flatpak update --system --noninteractive --assumeyes || falhou=1
        etapa "Flatpaks de $usuario" como_usuario "$usuario" "$home" \
            /usr/bin/dbus-run-session -- /usr/bin/flatpak update --user --noninteractive --assumeyes ||
            falhou=1
    else
        printf 'Flatpak ausente.\n'
    fi

    return "$falhou"
}

atualizar_apps() {
    local usuario=$1 home=$2 falhou=0
    atualizar_flatpaks "$usuario" "$home" || falhou=1
    etapa 'Discord nativo' como_usuario "$usuario" "$home" "$program" --discord-agendado ||
        falhou=1
    return "$falhou"
}

atualizar_nativos() {
    mountpoint -q /boot || { printf 'A partição /boot não está montada; manutenção de pacotes interrompida.\n' >&2; return 1; }
    local usuario=$1 home=$2 falhou=0 adiados=0 codigo
    etapa 'Backup de configurações' criar_ponto_recuperacao "$usuario" || return
    /usr/local/libexec/callas-native || {
        codigo=$?
        if (( codigo == 2 )); then adiados=1; else falhou=1; fi
    }
    etapa 'Aplicativos do AUR sem alterar a base' atualizar_aur --apps-only || {
        codigo=$?
        if (( codigo == 2 )); then adiados=1; else falhou=1; fi
    }
    etapa 'Discord nativo' como_usuario "$usuario" "$home" "$program" --discord-agendado || falhou=1
    (( falhou == 0 )) || return 1
    (( adiados == 0 )) || return 2
}

registrar_atualizacao() {
    local usuario=$1 modo=$2 origem=$3 home codigo=0 categoria
    case $modo in
      sistema) categoria='Sistema e Pacman' ;;
      *) categoria='Aplicativos' ;;
    esac
    home=$(home_do_usuario "$usuario")
    if {
        printf '\n===== Atualização (%s, %s) | %s =====\n' "$modo" "$origem" "$(date -Is)"
        case $modo in
            sistema) atualizar_sistema "$origem" "$usuario" "$home" || codigo=$? ;;
            apps|nativos) atualizar_nativos "$usuario" "$home" || codigo=$? ;;
            flatpaks) atualizar_flatpaks "$usuario" "$home" || codigo=$? ;;
            discord)
                etapa 'Discord nativo' como_usuario "$usuario" "$home" \
                    "$program" --discord-sessao || codigo=$?
                ;;
        esac
        printf '===== Fim da atualização | %s | código %s =====\n' "$(date -Is)" "$codigo"
        exit "$codigo"
    } 2>&1 | como_usuario "$usuario" "$home" "$program" --log "$categoria"; then
        if [[ $modo == sistema ]]; then
            local proxima
            proxima=$(proxima_data sistema "$(date +%F)") || return
            gravar_data_agenda sistema "$proxima" || return
            printf '%s\n' "$(date +%F)" > "$agenda_dir/ultima-sistema"
            gravar_data_agenda apps "$(proxima_data apps "$(date +%F)")" || return
            marcar_reinicio_pendente "$usuario" "$home" ||
                printf 'Aviso: não consegui mostrar a opção de reiniciar.\n' >&2
        elif [[ $modo == apps || $modo == nativos || $modo == flatpaks ]]; then
            [[ $modo == flatpaks ]] || gravar_data_agenda apps "$(proxima_data apps "$(date +%F)")" || return
            notificar_apps_usuario "$usuario" "$home" "$modo" || :
        fi
    else
        codigo=$?
        if (( codigo == 2 )); then
            printf 'Alguns aplicativos aguardam a opção 4 — Atualizar geral. Nenhum kernel foi atualizado pelo modo nativo.\n'
            notificar_adiamento_usuario "$usuario" "$home" || :
        else
            printf 'Atualização incompleta (código %s). Consulte os logs; reinício não solicitado.\n' "$codigo" >&2
            notificar_falha_usuario "$usuario" "$home" || :
        fi
        return "$codigo"
    fi
}

notificar_adiamento_usuario() {
    local usuario=$1 home=$2 uid runtime
    uid=$(id -u "$usuario") || return
    runtime="/run/user/$uid"
    [[ -S $runtime/bus ]] || return 0
    runuser -u "$usuario" -- env -i PATH=/usr/bin HOME="$home" USER="$usuario" \
      XDG_RUNTIME_DIR="$runtime" DBUS_SESSION_BUS_ADDRESS="unix:path=$runtime/bus" \
      notify-send -a 'Atualizador do sistema' 'Alguns aplicativos aguardam atualização geral' \
      'A opção 2 preservou kernel e base. Use a opção 4 para concluir as atualizações pendentes.'
}

notificar_falha_usuario() {
    local usuario=$1 home=$2 uid runtime
    uid=$(id -u "$usuario") || return
    runtime="/run/user/$uid"
    [[ -S $runtime/bus ]] || return 0
    runuser -u "$usuario" -- env -i PATH=/usr/bin HOME="$home" USER="$usuario" \
        XDG_RUNTIME_DIR="$runtime" DBUS_SESSION_BUS_ADDRESS="unix:path=$runtime/bus" \
        notify-send -u critical -a 'Atualizador do sistema' 'Atualização incompleta' \
        'Uma etapa falhou. Consulte Documentos/Callas OS/Callas OS Logs antes de reiniciar.'
}

instalar_atalhos() {
    local documentos pasta temporario antigo
    documentos=$(pasta_de_documentos)
    pasta="$documentos/Callas OS"
    [[ ! -L "$pasta" ]] || erro 'A pasta Callas OS não pode ser um link simbólico.'
    mkdir -p -- "$pasta"
    for antigo in "$pasta/atualizador-do-sistema.sh" "$pasta/Atualizador do sistema.desktop"; do
        [[ ! -L "$antigo" && ( ! -e "$antigo" || -f "$antigo" ) ]] ||
            erro "Destino de atalho inválido: $antigo"
    done
    # Prepare both copies before replacing them or retiring the old locations.
    temporario=$(mktemp -d "$pasta/.atalhos.XXXXXXXX")
    if ! install -m 0755 -T -- "$program" "$temporario/atualizador-do-sistema.sh" ||
       ! install -m 0755 -T -- "$atalho_menu" "$temporario/Atualizador do sistema.desktop"; then
        rm -rf -- "$temporario"
        erro 'Não foi possível preparar os atalhos; arquivos antigos preservados.'
    fi
    mv -fT -- "$temporario/atualizador-do-sistema.sh" "$pasta/atualizador-do-sistema.sh"
    mv -fT -- "$temporario/Atualizador do sistema.desktop" "$pasta/Atualizador do sistema.desktop"
    rmdir -- "$temporario"
    # Retire only recognized generated files; preserve custom files and symlinks.
    antigo="$documentos/atualizador-do-sistema.sh"
    if [[ -f "$antigo" && ! -L "$antigo" ]] &&
       grep -Fxq 'program=/usr/local/libexec/put-update' "$antigo" &&
       grep -Fxq 'servico_check=put-update-check.service' "$antigo"; then
        rm -- "$antigo"
    fi
    antigo="$documentos/Atualizador do sistema.desktop"
    if [[ -f "$antigo" && ! -L "$antigo" ]] &&
       grep -Fxq 'Type=Application' "$antigo" &&
       grep -Fxq 'Exec=/usr/local/libexec/put-update --menu' "$antigo"; then
        rm -- "$antigo"
    fi
    printf 'Atalho criado em %s/Atualizador do sistema.desktop\n' "$pasta"
}

instalar_entrada_menu() {
    local arquivo=$1
    cat > "$arquivo" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Atualizador do sistema
Comment=Atualizações automáticas e manuais do Arch, Flatpak e Discord
Exec=$program --menu
TryExec=$program
Icon=system-software-update
Terminal=true
Categories=System;
Keywords=atualizador;atualização;Arch;pacman;Flatpak;Discord;
DESKTOP
    install -D -m 0644 -T -- "$arquivo" "$atalho_menu"
    printf 'Atualizador do sistema disponível no menu de aplicativos.\n'
}

desativar_agendamento_antigo() {
    local em_chroot=$1 unidade estado
    local -a antigas=(
        put-update.timer put-update-sistema.timer put-update-apps.timer put-update-check.timer
    )

    if (( em_chroot )); then
        for unidade in "${antigas[@]}"; do
            systemctl --root=/ disable "$unidade" 2>/dev/null || :
        done
    else
        for unidade in "${antigas[@]}"; do
            estado=$(systemctl show -p LoadState --value "$unidade" 2>/dev/null || :)
            [[ $estado == not-found || -z $estado ]] || systemctl disable --now "$unidade" 2>/dev/null || :
        done
    fi

    rm -f -- \
        /etc/systemd/system/put-update.timer \
        /etc/systemd/system/put-update.service \
        /etc/systemd/system/put-update-sistema.timer \
        /etc/systemd/system/put-update-apps.timer \
        /etc/systemd/system/put-update@.service \
        /etc/systemd/system/put-update-check.timer \
        /etc/systemd/system/put-update-check.service
}

instalar() {
    local usuario=$1 origem temporario conta home modo timer hora pasta em_chroot=0
    [[ "$usuario" =~ ^[a-zA-Z_][a-zA-Z0-9_.-]*$ && "$usuario" != root ]] ||
        erro 'Informe um usuário normal do Arch.'
    [[ -f /etc/arch-release ]] || erro 'Este script requer Arch Linux.'
    if systemd-detect-virt --chroot; then
        em_chroot=1
    elif [[ ! -d /run/systemd/system ]]; then
        erro 'Este script requer o systemd em execução ou o arch-chroot do sistema de destino.'
    fi
    home=$(home_do_usuario "$usuario")
    origem=$(realpath -- "${BASH_SOURCE[0]}")
    exec 8>"$lock_atualizador"
    [[ ${CALLAS_UPDATE_LOCK_HELD:-0} == 1 ]] || flock -x 8
    temporario=$(mktemp -d)
    trap "rm -rf -- $(printf '%q' "$temporario")" EXIT

    cat > "$temporario/$servico_check" <<UNIT
[Unit]
Description=Verificar agenda de atualização do Callas OS
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
ExecStart=$program --check $usuario
StandardOutput=journal
StandardError=journal
UNIT

    cat > "$temporario/$timer_check" <<UNIT
[Unit]
Description=Verificar a agenda de atualização ao longo do dia

[Timer]
OnBootSec=2min
OnUnitInactiveSec=1h
AccuracySec=1min
Unit=$servico_check

[Install]
WantedBy=timers.target
UNIT

    desativar_agendamento_antigo "$em_chroot"
    rm -f -- "$sudo_rule"

    rm -f -- "$sudo_rule" "$sudo_template" "$paru_conf"
    # AUR builds use the isolated helper; no passwordless pacman rule is installed.

    preparar_agenda
    if [[ ! -f $agenda_dir/maintenance-monthly-v2 ]]; then
        base_agenda=$(ler_data_agenda inicio)
        [[ ! -r $agenda_dir/ultima-sistema ]] || read -r base_agenda < "$agenda_dir/ultima-sistema"
        gravar_data_agenda sistema "$(proxima_data sistema "$base_agenda")"
        touch "$agenda_dir/maintenance-monthly-v2"
    fi
    # O programa pode já ser a origem quando o automático é reconfigurado pelo atalho.
    if [[ $origem != "$program" ]]; then
        install -D -m 0755 -T -- "$origem" "$program"
    fi
    install -m 0644 -- "$temporario/$servico_check" "$temporario/$timer_check" /etc/systemd/system/
    instalar_entrada_menu "$temporario/${atalho_menu##*/}"

    como_usuario "$usuario" "$home" mkdir -p "$home/.config/autostart"
    como_usuario "$usuario" "$home" tee "$home/.config/autostart/callas-update-reinicio.desktop" >/dev/null <<'REBOOT_DESKTOP'
[Desktop Entry]
Type=Application
Name=Notificação de reinício do Callas OS
Exec=/usr/local/libexec/put-update --notificar-reinicio
OnlyShowIn=KDE;
NoDisplay=true
StartupNotify=false
X-KDE-AutostartScript=true
REBOOT_DESKTOP

    if (( em_chroot )); then
        systemctl --root=/ enable "$timer_check"
    else
        systemctl daemon-reload
        systemctl enable "$timer_check"
        systemctl restart "$timer_check"
    fi

    printf '\nAgendamento automático configurado.\n'
    printf 'Atualização mensal do sistema vence em: %s.\n' "$(ler_data_agenda sistema)"
    printf 'Atualização semanal dos aplicativos vence em: %s.\n' "$(ler_data_agenda apps)"
    printf 'Se o PC estiver desligado no vencimento, a atualização roda no primeiro boot/verificação seguinte.\n'
    como_usuario "$usuario" "$home" "$program" --instalar-atalhos
    if pasta=$(como_usuario "$usuario" "$home" "$program" --log-dir); then
        printf 'Logs por categoria em Documentos: %s\n' "$pasta"
    else
        printf 'Não foi possível criar a pasta de logs em Documentos.\n' >&2
    fi
}

perguntar_reinicio() {
    # O callas-config-update.sh pergunta Y/N imediatamente ao concluir.
    return 0
}

atualizar_config_callas() {
    # Root creates/downloads the stage; never sudo-execute a user-owned script.
    printf 'É necessária autorização administrativa para aplicar as configurações.\n'
    sudo /usr/local/libexec/callas-release
}

menu_manutencao() {
    local escolha
    while true; do
        printf '\n=== Limpeza e manutenção ===\n'
        printf '%s\n' '1. Limpeza segura agora' '2. Ver espaço, backups e arquivos de VMs' \
            '3. Verificar pacotes órfãos' '4. Reparar agendamento automático' '5. Coletar diagnóstico de jogo' '6. Voltar'
        read -r -p 'Escolha [1-6]: ' escolha || return 0
        [[ $escolha == 6 || -z $escolha ]] || printf 'É necessária autorização administrativa para esta ação.\n'
        case $escolha in
          1) sudo /usr/local/libexec/callas-maintenance --clean "$USER" || printf 'A limpeza registrou uma falha; consulte os logs.\n' ;;
          2) sudo /usr/local/libexec/callas-maintenance --report "$USER" || printf 'Não consegui concluir o relatório.\n' ;;
          3) sudo /usr/local/libexec/callas-maintenance --orphans "$USER" || printf 'Não consegui concluir a verificação de órfãos.\n' ;;
          4) sudo "$program" --instalar || printf 'Falha ao reparar o agendamento.\n' ;;
          5) sudo /usr/local/libexec/callas-game-logs --collect "$USER" || printf 'Não consegui concluir o diagnóstico do jogo.\n' ;;
          6|"") return 0 ;;
          *) printf 'Opção inválida.\n' ;;
        esac
    done
}

menu() {
    local origem opcao modo
    origem=$(realpath -- "${BASH_SOURCE[0]}")
    if [[ ! -t 0 ]]; then
        command -v konsole >/dev/null || erro 'Abra o arquivo com bash em um terminal.'
        exec konsole -e /usr/bin/bash "$origem" --menu
    fi
    while true; do
        printf '\n=== Atualizador do sistema ===\n'
        if [[ -x /usr/local/libexec/callas-version ]]; then
            /usr/local/libexec/callas-version --label || :
        fi
        printf '%s\n' \
            '1. Limpeza e manutenção' \
            '2. Atualizar aplicativos nativos' \
            '3. Atualizar Discord' \
            '4. Atualizar geral' \
            '5. Callas OS Update' \
            '6. Sair'
        read -r -p 'Escolha [1-6] ou digite reboot: ' opcao || return 0
        case $opcao in
            1)
                menu_manutencao
                continue
                ;;
            2) modo=nativos ;;
            3) modo=discord ;;
            4) modo=sistema ;;
            5)
                if atualizar_config_callas; then
                    perguntar_reinicio
                else
                    printf 'Falha ao atualizar as configurações do Callas OS.\n' >&2
                fi
                continue
                ;;
            6) return 0 ;;
            reboot|REBOOT|Reboot)
                systemctl --quiet reboot --check-inhibitors=no --no-wall
                return 0
                ;;
            *) printf 'Opção inválida. Digite 1-6 ou reboot.\n'; continue ;;
        esac

        if [[ $origem != "$program" ]] && ! cmp -s -- "$origem" "$program"; then
            printf 'Este arquivo difere do atualizador instalado. Use a opção 5 — Callas OS Update para migrar a versão instalada.\n'
            continue
        fi
        printf 'É necessária autorização administrativa para iniciar. Não serão pedidas senhas no meio da atualização.\n'
        if sudo "$program" --manual "$modo"; then
            : # The transaction itself offers reboot after every phase succeeds.
        else
            codigo_menu=$?
            if (( codigo_menu == 2 )); then
                printf 'Parte dos aplicativos aguarda Atualizar geral; os detalhes estão no log.\n'
            else
                printf 'Atualização com falha. Confira a mensagem acima e o log em Documentos.\n' >&2
            fi
        fi
    done
}

case ${1:-} in
    --discord-boot|--discord-agendado)
        (( EUID != 0 && $# == 1 )) || erro 'Esta opção é usada pelo serviço de atualização.'
        atualizar_discord_integrado --agendado
        ;;
    --discord-sessao)
        (( EUID != 0 && $# == 1 )) || erro 'Esta opção é usada pelo menu de atualização.'
        atualizar_discord_integrado --sessao
        ;;
    --discord)
        shift
        case ${1:-} in
            --boot|--agendado|--sessao) erro 'Use --discord para atualização manual.' ;;
        esac
        atualizar_discord_integrado "$@"
        ;;
    --check)
        (( EUID == 0 && $# == 2 )) || erro 'Esta opção é usada pelo serviço de atualização.'
        exec flock -x -o "$lock_atualizador" "$program" --verificar-agenda "$2"
        ;;
    --verificar-agenda)
        (( EUID == 0 && $# == 2 )) || erro 'Esta opção é interna.'
        rm -f -- "$sudo_rule"
        verificar_agenda "$2"
        ;;
    --manual)
        (( EUID == 0 && $# == 2 )) || erro 'Esta opção é usada pelo menu de atualização.'
        [[ -n ${SUDO_USER:-} && $SUDO_USER != root ]] || erro 'Abra o menu com seu usuário normal.'
        [[ $2 == sistema || $2 == apps || $2 == nativos || $2 == flatpaks || $2 == discord ]] || erro 'Modo manual inválido.'
        printf 'Preparando a atualização. Se outra estiver em andamento, ela vai terminar primeiro.\n'
        exec flock -x -o "$lock_atualizador" "$program" --registrar "$SUDO_USER" "$2" manual
        ;;
    --registrar)
        (( EUID == 0 && $# == 4 )) || erro 'Esta opção é interna.'
        rm -f -- "$sudo_rule"
        if [[ $4 == automatico ]]; then
            executar_agendado "$2" "$3"
        else
            registrar_atualizacao "$2" "$3" "$4"
        fi
        ;;
    --notificar-reinicio)
        (( EUID != 0 && $# == 1 )) || erro 'Esta opção é usada pela sessão gráfica do usuário.'
        notificar_reinicio_usuario
        ;;
    --instalar)
        (( EUID == 0 && $# == 1 )) || erro 'Escolha a opção 1 no menu para instalar.'
        instalar "${SUDO_USER:-}"
        ;;
    --instalar-para)
        (( EUID == 0 && $# == 2 )) || erro 'Use como root: bash atualizador-do-sistema.sh --instalar-para USUARIO.'
        instalar "$2"
        ;;
    --instalar-atalhos)
        (( EUID != 0 && $# == 1 )) || erro 'Esta opção é interna.'
        instalar_atalhos
        ;;
    --log-dir)
        (( EUID != 0 && $# == 1 )) || erro 'Use esta opção como usuário normal.'
        pasta_de_logs
        ;;
    --log)
        (( EUID != 0 && $# == 2 )) || erro 'Use esta opção como usuário normal.'
        /usr/bin/tee /dev/stderr | /usr/local/libexec/callas-logs --write "$2"
        ;;
    ''|--menu)
        (( EUID != 0 && $# <= 1 )) || erro 'Abra o atualizador com seu usuário normal, sem sudo.'
        menu
        ;;
    *) erro 'Use bash atualizador-do-sistema.sh para abrir o menu.' ;;
esac
