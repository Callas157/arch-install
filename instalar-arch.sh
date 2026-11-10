#!/usr/bin/env bash
# =====================================================================
# Instalação automática do Arch Linux
# KDE Plasma (Wayland) + SDDM | pt-BR | UEFI | GRUB experimental | ext4
# NVIDIA compatível com nvidia-open ou Mesa | microcódigo AMD/Intel
# Teclado: EUA Internacional | Steam, Discord, AUR (Paru), Flatpak
# ProtonPlus (Flathub) | Nekofetch + Fastfetch | Ark (RAR, ZIP e 7z)
# Solaar na bandeja | xone para receptor Xbox Wireless | qBittorrent | Spotify (AUR)
#
# ATENÇÃO: APAGA TODO O DISCO ESCOLHIDO NO INÍCIO DO SCRIPT
# Plymouth com escudo Callas | atualizador do KDE | Spotify + Spicetify
# Rodar na ISO do Arch Linux, com internet por cabo.
# =====================================================================
set -Eeuo pipefail
trap 'printf "ERRO: instalação interrompida na linha %s.\n" "$LINENO" >&2' ERR

# ---------------- Configurações ----------------
DISCO="${DISCO:-}"   # se vazio, o script pergunta em qual disco instalar
HOSTNAME="arch"
FUSO="America/Sao_Paulo"
LOCALE="pt_BR.UTF-8"
TECLADO="us-acentos"   # console: EUA Internacional (com acentos)
# -----------------------------------------------

if [[ $EUID -ne 0 ]]; then
  echo "Rode como root (na ISO do Arch já é)."; exit 1
fi

if [[ ! -d /sys/firmware/efi/efivars ]]; then
  echo "ERRO: inicie a ISO em UEFI. Em uma VM, habilite EFI no virtualizador."; exit 1
fi

if ! curl -fsSL --connect-timeout 10 --max-time 20 https://archlinux.org/ -o /dev/null; then
  echo "ERRO: sem internet. Confira o cabo de rede."; exit 1
fi

loadkeys "$TECLADO" || true

# ---------------- Detecção do processador ----------------
if grep -q "GenuineIntel" /proc/cpuinfo; then
  UCODE_PACKAGE="intel-ucode"
  echo "Processador Intel detectado."
elif grep -q "AuthenticAMD" /proc/cpuinfo; then
  UCODE_PACKAGE="amd-ucode"
  echo "Processador AMD detectado."
else
  echo "ERRO: não foi possível identificar o fabricante do processador."
  exit 1
fi

# ---------------- Detecção da rede (Wi-Fi / cabo) ----------------
# A maioria dos adaptadores (Intel, Realtek, Qualcomm, MediaTek) já funciona
# com o kernel + linux-firmware. Aqui entram só os pacotes extras necessários.
REDE_PACOTES=()
BROADCOM=0
PCI_REDE="$(lspci -nn 2>/dev/null | grep -Ei 'ethernet controller|network controller|802\.11' || true)"
USB_REDE="$(lsusb 2>/dev/null | grep -Ei 'wireless|wlan|802\.11|wi-?fi' || true)"
TEM_WIFI=0
if grep -Eiq 'network controller|802\.11|wireless|wi-?fi' <<<"$PCI_REDE"$'\n'"$USB_REDE" \
   || compgen -G "/sys/class/net/*/wireless" >/dev/null; then
  TEM_WIFI=1
  REDE_PACOTES+=(wpa_supplicant iw wireless-regdb)
fi
# Broadcom Wi-Fi que precisa do driver proprietário wl
if grep -Eiq 'broadcom.*BCM(4311|4312|4321|4322|43142|43227|43228|4331|4352|4360)\b' <<<"$PCI_REDE"; then
  BROADCOM=1
fi
if grep -qi 'ethernet controller' <<<"$PCI_REDE"; then echo "Placa de rede cabeada detectada."; fi
if (( TEM_WIFI )); then echo "Adaptador Wi-Fi detectado."; fi
if (( BROADCOM )); then echo "Wi-Fi Broadcom detectado: será instalado o driver broadcom-wl-dkms."; fi

# ---------------- Detecção gráfica ----------------
GPU_PCI="$(lspci -Dn | awk '$2 ~ /^03[[:xdigit:]][[:xdigit:]]:$/ {print $3}')"
NVIDIA=0
VM="$(systemd-detect-virt --vm || true)"
GPU_PACOTES=(mesa)
if grep -q '^10de:' <<<"$GPU_PCI"; then
  NVIDIA=1
  GPU_PACOTES+=(nvidia-open nvidia-utils nvidia-settings egl-wayland)
  echo "GPU NVIDIA detectada. Instalando nvidia-open."
else
  echo "Gráficos via Mesa (ambiente: ${VM:-nativo})."
fi

# ---------------- Escolha do disco ----------------
BOOTPART="$(findmnt -no SOURCE /run/archiso/bootmnt 2>/dev/null || true)"
BOOTDISK=""
if [[ -b "$BOOTPART" ]]; then
  BOOTDISK="$(lsblk -npro NAME,TYPE -s "$BOOTPART" | awk '$2 == "disk" && !found++ {print $1}')"
fi
if [[ -z "$DISCO" ]]; then
  mapfile -t LISTA < <(lsblk -dpno NAME,TYPE,RO | awk '$2=="disk" && $3==0 {print $1}' | grep -v '/zram' | grep -vx "$BOOTDISK" || true)
  if (( ${#LISTA[@]} == 0 )); then
    echo "ERRO: nenhum disco encontrado."; exit 1
  fi
  echo
  echo "Discos encontrados:"
  for i in "${!LISTA[@]}"; do
    INFO="$(lsblk -dno SIZE,MODEL "${LISTA[$i]}")"
    echo "  $((i+1))) ${LISTA[$i]}  -  $INFO"
  done
  echo
  read -rp "Em qual disco instalar o sistema? (digite o número): " ESCOLHA
  if ! [[ "$ESCOLHA" =~ ^[1-9][0-9]{0,5}$ ]] || (( ESCOLHA > ${#LISTA[@]} )); then
    echo "Opção inválida."; exit 1
  fi
  DISCO="${LISTA[$((ESCOLHA-1))]}"
fi

DISCO="$(readlink -f -- "$DISCO")"
if [[ ! -b "$DISCO" || "$(lsblk -dnro TYPE,RO "$DISCO")" != "disk 0" ]]; then
  echo "ERRO: destino $DISCO não é um disco gravável."
  exit 1
fi
if [[ "$DISCO" == "$BOOTDISK" ]] ||
   [[ -n "$(lsblk -nr -o MOUNTPOINTS "$DISCO" | sed '/^$/d')" ]]; then
  echo "ERRO: o disco selecionado tem partições em uso ou é a mídia de instalação."
  exit 1
fi

echo
echo "=========================================================="
echo " TODOS OS DADOS DESTE DISCO SERÃO APAGADOS:"
lsblk -o NAME,SIZE,MODEL,FSTYPE "$DISCO"
echo "=========================================================="

read -rp "Nome do usuário (minúsculas, sem espaços): " USUARIO
[[ "$USUARIO" =~ ^[a-z_][a-z0-9_-]{0,31}$ && "$USUARIO" != root && "$USUARIO" != put-aur ]] || { echo "Nome de usuário inválido."; exit 1; }

while true; do
  read -rsp "Senha do usuário (e do root): " SENHA; echo
  read -rsp "Repita a senha: " SENHA2; echo
  [[ -n "$SENHA" && "$SENHA" == "$SENHA2" ]] && break
  echo "As senhas não conferem, tente de novo."
done

# ---------------- Preparação da ISO ----------------
timedatectl set-ntp true
sed -i 's/^#ParallelDownloads.*/ParallelDownloads = 10/' /etc/pacman.conf
pacman -Sy --noconfirm archlinux-keyring

# ---------------- Particionamento ----------------
echo ">>> Particionando $DISCO"
umount -R /mnt 2>/dev/null || true
wipefs -af "$DISCO"
sgdisk --zap-all "$DISCO"
sgdisk -n 1:0:+1G -t 1:ef00 -c 1:"EFI" "$DISCO"
sgdisk -n 2:0:0   -t 2:8300 -c 2:"ARCH" "$DISCO"
partprobe "$DISCO"
udevadm settle

if [[ "$DISCO" =~ [0-9]$ ]]; then SEP="p"; else SEP=""; fi
EFI="${DISCO}${SEP}1"
RAIZ="${DISCO}${SEP}2"

mkfs.fat -F32 "$EFI"
mkfs.ext4 -F "$RAIZ"

mount "$RAIZ" /mnt
mount --mkdir -o fmask=0077,dmask=0077 "$EFI" /mnt/boot

# ---------------- Instalação base ----------------
echo ">>> Instalando pacotes (isso demora)"
pacstrap -K /mnt \
  base linux linux-firmware "$UCODE_PACKAGE" base-devel sudo nano git curl gnupg acl grub efibootmgr \
  linux-headers dkms pciutils usbutils \
  networkmanager "${REDE_PACOTES[@]}" \
  plasma-desktop sddm sddm-kcm plasma-nm plasma-pa kscreen powerdevil xorg-xwayland \
  konsole dolphin kate ark gwenview okular spectacle kdeplasma-addons \
  unrar unarchiver zip unzip libarchive 7zip lrzip lzop arj cpio \
  uv fastfetch chafa python ttf-jetbrains-mono-nerd \
  solaar libappindicator qbittorrent \
  xdg-desktop-portal-kde xdg-user-dirs \
  kwallet-pam kwalletmanager \
  pipewire pipewire-alsa pipewire-pulse wireplumber \
  bluez bluez-utils \
  "${GPU_PACOTES[@]}" plymouth \
  noto-fonts noto-fonts-emoji ttf-dejavu ttf-liberation \
  flatpak \
  zram-generator

genfstab -U /mnt > /mnt/etc/fstab

UUID_RAIZ="$(blkid -s UUID -o value "$RAIZ")"

# ---------------- Arquivos integrados ----------------
install -d /mnt/usr/local/libexec /mnt/usr/share/plymouth/themes/callas
install -d /mnt/usr/share/icons/hicolor/256x256/apps
# Imagem original do projeto (assets/callas-plasma-icon.png), incorporada para uso no boot.
base64 -d > /mnt/usr/share/plymouth/themes/callas/callas.png <<'CALLAS_PNG'
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
Jpr4ueP/ASbjLst3c/oNAAAAAElFTkSuQmCC
CALLAS_PNG
printf '%s  %s\n' \
  '5fbfd40b160befa349c502e92f363fe061143b12e576eb819b072b6f3786ac02' \
  '/mnt/usr/share/plymouth/themes/callas/callas.png' | sha256sum --check --status
install -m 0644 /mnt/usr/share/plymouth/themes/callas/callas.png \
  /mnt/usr/share/icons/hicolor/256x256/apps/callas-plasma-icon.png

cat > /mnt/usr/share/plymouth/themes/callas/callas.plymouth <<'PLYMOUTH_THEME'
[Plymouth Theme]
Name=Callas
Description=Escudo do Arch Install Callas
ModuleName=script

[script]
ImageDir=/usr/share/plymouth/themes/callas
ScriptFile=/usr/share/plymouth/themes/callas/callas.script
PLYMOUTH_THEME

cat > /mnt/usr/share/plymouth/themes/callas/callas.script <<'PLYMOUTH_SCRIPT'
Window.SetBackgroundTopColor(0.015, 0.022, 0.043);
Window.SetBackgroundBottomColor(0.015, 0.022, 0.043);
escudo = Image("callas.png");
logo = Sprite(escudo);

fun posicionar() {
    logo.SetX(Window.GetX() + (Window.GetWidth() - escudo.GetWidth()) / 2);
    logo.SetY(Window.GetY() + (Window.GetHeight() - escudo.GetHeight()) / 2);
}
posicionar();
Plymouth.SetRefreshFunction(posicionar);
PLYMOUTH_SCRIPT

cat > "/mnt/usr/local/libexec/put-update" <<'CALLAS_UPDATER'
#!/usr/bin/env bash
set -euo pipefail
export PATH=/usr/bin:/bin

program=/usr/local/libexec/put-update
atalho_menu=/usr/local/share/applications/io.github.Callas157.AtualizadorDoSistema.desktop
servico=put-update@.service
timer_sistema=put-update-sistema.timer
timer_apps=put-update-apps.timer
hora_sistema=14
hora_apps=13
agenda_dir=/var/lib/put-update/agenda
lock_atualizador=/run/put-update.lock
builder=put-aur
builder_home=/var/lib/put-update/aur
paru_conf=/etc/put-update-paru.conf
sudo_template=/etc/put-update-aur.sudoers
sudo_rule=/etc/sudoers.d/put-update

erro() {
    printf 'Erro: %s\n' "$*" >&2
    exit 1
}

hora_agendada() {
    case $1 in
        sistema) printf '%s\n' "$hora_sistema" ;;
        apps) printf '%s\n' "$hora_apps" ;;
        *) erro 'Agenda inválida.' ;;
    esac
}

proxima_data() {
    local modo=$1 inicio=$2 hoje=$3 mes ultimo dia
    if [[ $modo == apps ]]; then
        TZ=UTC0 date -d "$hoje +7 days" +%F
        return
    fi

    # Usa o primeiro dia do próximo mês para preservar a referência nos meses curtos.
    mes=$(TZ=UTC0 date -d "${hoje:0:7}-01 +1 month" +%Y-%m) || return
    ultimo=$(TZ=UTC0 date -d "$mes-01 +1 month -1 day" +%d) || return
    dia=${inicio:8:2}
    if (( 10#$dia > 10#$ultimo )); then
        dia=$ultimo
    fi
    printf '%s-%s\n' "$mes" "$dia"
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
            data=$(proxima_data "$modo" "$inicio" "$inicio")
            gravar_data_agenda "$modo" "$data"
        fi
    done
}

executar_agendado() {
    local usuario=$1 modo=$2 hoje hora agora vencimento inicio data
    agora=$(date '+%F %H')
    read -r hoje hora <<< "$agora"
    # Se o PC acordar da suspensão depois do horário, aguarda a próxima tarde.
    if [[ $hora != "$(hora_agendada "$modo")" ]]; then
        return 0
    fi
    vencimento=$(ler_data_agenda "$modo")
    if [[ $hoje < $vencimento ]]; then
        return 0
    fi

    inicio=$(ler_data_agenda inicio)
    data=$(proxima_data "$modo" "$inicio" "$hoje")
    # Registra a tentativa antes de atualizar para evitar repetições automáticas após falhas.
    gravar_data_agenda "$modo" "$data"
    registrar_atualizacao "$usuario" "$modo" automatico
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
    local pasta
    pasta="$(pasta_de_documentos)/Logs de Atualizações"
    umask 077
    mkdir -p -- "$pasta" || return
    printf '%s\n' "$pasta"
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
    local origem=$1 dbpath tentativa
    local -a dependencias=() confirmacao=()
    if [[ $origem == automatico ]]; then
        confirmacao+=(--noconfirm)
    fi
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
    pacman -Syu --needed "${confirmacao[@]}" "${dependencias[@]}"
}

atualizar_aur() (
    if [[ ! -x /usr/bin/paru || ! -f "$paru_conf" || ! -f "$sudo_template" ]]; then
        printf 'Atualização do AUR indisponível. Instale o Paru e rode bash atualizador-do-sistema.sh para configurar.\n' >&2
        return 1
    fi

    # A conta de compilação só pode chamar o pacman durante esta etapa.
    trap 'rm -f -- "$sudo_rule"' EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    install -D -m 0440 "$sudo_template" "$sudo_rule" || return
    runuser -u "$builder" -- env -i PATH=/usr/bin HOME="$builder_home" \
        USER="$builder" LOGNAME="$builder" LANG=C.UTF-8 PARU_CONF="$paru_conf" \
        /usr/bin/paru -Su --aur --noconfirm --skipreview --devel
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
        --desinstalar) acao=desinstalar ;;
        -h|--help)
            printf 'Uso: bash %s --discord [--pacman | --desinstalar]\n' "${0##*/}"
            printf 'Com --discord: atualiza o Discord pelo atualizador oficial e instala ou atualiza o BetterDiscord.\n'
            printf '%s\n' '--pacman: inclui a atualização completa do Arch e do pacote discord pelo pacman.' \
                '--desinstalar: remove o carregador do BetterDiscord, preservando plugins e temas.'
            exit 0
            ;;
        *) falhar "Opção desconhecida: $1. Use --help." ;;
    esac
    [[ $# -le 1 ]] || falhar 'Passe apenas uma opção.'
    (( EUID != 0 )) || falhar 'Rode com seu usuário normal. O modo --pacman pede sudo quando necessário.'
    [[ $(uname -sm) == 'Linux x86_64' ]] || falhar 'Este arquivo foi preparado para Linux x86_64.'

    via_servico=0
    if [[ $acao == agendado || $acao == sessao ]]; then
        via_servico=1
    fi

    config_dir=${XDG_CONFIG_HOME:-"$HOME/.config"}
    [[ $config_dir == /* ]] || falhar 'XDG_CONFIG_HOME precisa ser um caminho absoluto.'
    discord_dir="$config_dir/discord"
    aviso_discord='Discord Stable nativo não encontrado no perfil. Abra o Discord pelo menu, aguarde a janela principal carregar e tente novamente.'
    if [[ ! -d $discord_dir ]]; then
        if [[ $acao == agendado ]]; then
            printf '%s\n' "$aviso_discord"
            return 0
        fi
        falhar "$aviso_discord"
    fi
    discord_real=$(realpath -e -- "$discord_dir")
    export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"
    if ! lancador=$(command -v discord); then
        for candidato in /opt/Discord/Discord /opt/discord/Discord; do
            if [[ -x $candidato ]]; then
                lancador=$candidato
                break
            fi
        done
        if [[ -z $lancador ]]; then
            if [[ $acao == agendado ]]; then
                printf 'Lançador do Discord nativo ausente.\n'
                return 0
            fi
            falhar 'O lançador nativo discord não foi encontrado.'
        fi
    fi
    lancador_real=$(realpath -- "$lancador")
    runtime_dir=${XDG_RUNTIME_DIR:-/run/user/$EUID}
    if (( via_servico )); then
        export XDG_RUNTIME_DIR="$runtime_dir"
    fi
    [[ -d $runtime_dir ]] || runtime_dir=$config_dir
    log_reabertura="$runtime_dir/callas-discord-reabertura.log"

    exec 9>"$discord_dir/callas-betterdiscord.lock"
    if ! flock -n 9; then
        if [[ $acao == agendado ]]; then
            printf 'O atualizador do Discord já está em execução.\n'
            return 0
        fi
        falhar 'Já existe outra execução do script em andamento.'
    fi

    shopt -s nullglob

    tem_arquivo_discord() {
        [[ -s $1/app.asar || -s $1/betterdiscord.app.asar ]]
    }

    descobrir_recursos() {
        local pasta versao
        local -a pastas=("$discord_dir"/app-*/resources)
        (( ${#pastas[@]} )) || return 1
        while IFS= read -r -d '' pasta; do
            versao=${pasta%/resources}
            [[ ${versao##*/} =~ ^app-[0-9]+\.[0-9]+\.[0-9]+$ ]] || continue
            if tem_arquivo_discord "$pasta"; then
                printf '%s\n' "$pasta"
                return 0
            fi
        done < <(printf '%s\0' "${pastas[@]}" | sort -zVr)
        return 1
    }

    verificar_recursos() {
        [[ -w $recursos ]] || falhar "Sem permissão de escrita em $recursos."
        carregador="$recursos/app"
        if [[ -e $carregador || -L $carregador ]]; then
            if [[ -L $carregador || ! -f $carregador/index.js ]] ||
                ! grep -Fq '../betterdiscord.app.asar' "$carregador/index.js"; then
                falhar "Já existe um carregador diferente em $carregador."
            fi
        fi
    }

    pids_discord() {
        local pid exe
        while IFS= read -r pid; do
            exe=$(readlink -- "/proc/$pid/exe") || continue
            exe=${exe% (deleted)}
            if [[ $exe == "$discord_real"/app-*/Discord || $exe == "$discord_real/Discord" ||
                $exe == "$lancador_real" || $exe == /opt/Discord/Discord ||
                $exe == /opt/discord/Discord || $exe == /usr/share/discord/Discord ||
                $exe == /usr/lib/discord/Discord ]]; then
                printf '%s\n' "$pid"
            fi
        done < <(pgrep -u "$EUID" -x 'Discord|discord' || true)
    }

    discord_em_execucao() {
        pgrep -u "$EUID" -x 'Discord|discord' >/dev/null
    }

    betterdiscord_injetado() {
        [[ ! -e $recursos/app.asar && -s $recursos/betterdiscord.app.asar &&
            -s $carregador/index.js && -s $carregador/package.json && -s $mod_asar ]]
    }

    reabrir_discord() {
        if [[ -n $(pids_discord) ]]; then
            return 0
        fi
        printf 'Reabrindo o Discord pelo lançador do sistema...\n'
        local tentativa unidade="app-discord-callas@$$.service"
        if (( via_servico )); then
            # O processo precisa da sessão gráfica e deve sobreviver ao fim do serviço de atualização.
            systemd-run --user --collect --unit="$unidade" --slice=app.slice \
                --property=Type=exec --property=PartOf=graphical-session.target \
                -- "$lancador" --start-minimized 9>&- || return 1
        else
            nohup "$lancador" --start-minimized </dev/null >"$log_reabertura" 2>&1 9>&- &
        fi
        for ((tentativa=0; tentativa<60; tentativa++)); do
            if [[ -n $(pids_discord) ]]; then
                printf 'Discord reaberto.\n'
                return 0
            fi
            sleep 0.25
        done
        if (( via_servico )); then
            printf 'O Discord não iniciou a tempo. Confira com journalctl --user -u %s\n' "$unidade" >&2
        else
            printf 'O Discord não iniciou a tempo. Abra pelo menu e confira o log em %s\n' "$log_reabertura" >&2
        fi
        return 1
    }

    limpar() {
        local codigo=$?
        trap - EXIT
        if (( mod_em_alteracao )) && [[ -f $temp_dir/betterdiscord.anterior.asar ]]; then
            cp -p -- "$temp_dir/betterdiscord.anterior.asar" "$mod_asar" ||
                printf 'Não foi possível restaurar o arquivo anterior do BetterDiscord.\n' >&2
        fi
        rm -rf -- "$temp_dir" || true
        if (( reabrir )); then
            reabrir_discord || { (( codigo != 0 )) || codigo=1; }
        fi
        exit "$codigo"
    }

    fechar_discord() {
        local -a pids=()
        local tentativa
        mapfile -t pids < <(pids_discord)
        (( ${#pids[@]} )) || return 0
        if (( via_servico )) && ! systemctl --user is-active --quiet graphical-session.target; then
            falhar 'O Discord está aberto, mas a sessão gráfica não está acessível para reabri-lo.'
        fi
        reabrir=1
        printf 'Fechando o Discord para atualizar...\n'
        kill -TERM "${pids[@]}" 2>/dev/null || true
        for ((tentativa=0; tentativa<40; tentativa++)); do
            if [[ -z $(pids_discord) ]]; then
                return 0
            fi
            sleep 0.25
        done
        falhar 'O Discord ainda está aberto. Encerre-o pelo ícone da bandeja e tente novamente.'
    }

    atualizar_discord() {
        local bootstrap candidato saida pasta_nova versao anterior=$recursos
        for candidato in "$(dirname -- "$(realpath -- "$lancador")")/updater_bootstrap" \
            /usr/share/discord/updater_bootstrap /opt/Discord/updater_bootstrap \
            /opt/discord/updater_bootstrap; do
            if [[ -x $candidato ]]; then
                bootstrap=$candidato
                break
            fi
        done
        if [[ -z ${bootstrap:-} ]]; then
            printf 'O atualizador oficial do Discord não foi encontrado.\n' >&2
            return 1
        fi

        printf 'Verificando a atualização do Discord nativo...\n'
        if ! saida=$(timeout --kill-after=10s 10m "$bootstrap" --no-zenity \
            "$discord_dir" stable https://updates.discord.com/ 9>&-); then
            printf 'A atualização do Discord falhou.\n' >&2
            return 1
        fi

        pasta_nova=${saida##*$'\n'}
        if [[ $pasta_nova =~ ^app-[0-9]+\.[0-9]+\.[0-9]+$ ]] &&
            tem_arquivo_discord "$discord_dir/$pasta_nova/resources"; then
            recursos="$discord_dir/$pasta_nova/resources"
        else
            recursos=$(descobrir_recursos) || falhar "$aviso_discord"
        fi
        if [[ $recursos == "$anterior" ]]; then
            printf 'O Discord já está na versão atual.\n'
        else
            versao=${recursos%/resources}
            printf 'Discord atualizado para %s.\n' "${versao##*/app-}"
        fi
    }

    if ! recursos=$(descobrir_recursos); then
        if [[ $acao == agendado ]]; then
            printf '%s\n' "$aviso_discord"
            return 0
        fi
        falhar "$aviso_discord"
    fi
    verificar_recursos
    mod_asar="$config_dir/BetterDiscord/data/betterdiscord.asar"
    mod_desativado="$discord_dir/.callas-betterdiscord-desativado"
    atualizar_mod=1
    if [[ $acao == desinstalar && ! -e $recursos/betterdiscord.app.asar && ! -e $carregador ]]; then
        touch -- "$mod_desativado"
        printf 'O BetterDiscord já está desativado nesta versão do Discord.\n'
        return 0
    elif [[ $acao == agendado && -e $mod_desativado ]]; then
        atualizar_mod=0
    fi

    # A CLI é fixa para conferir o SHA-256. O mod é baixado na versão estável atual.
    versao_cli=1.0.0
    arquivo="bdcli_${versao_cli}_linux_amd64.tar.gz"
    sha256=df0a97f64be42abed3bb534c7770207ca78f79e5f82eaeb6027f2cbd46e0df44

    temp_dir=$(mktemp -d)
    reabrir=0
    mod_em_alteracao=0
    trap limpar EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    baixar_cli() {
        printf 'Baixando o instalador oficial do BetterDiscord...\n'
        curl --fail --silent --show-error --location --retry 2 \
            --proto '=https' --proto-redir '=https' --connect-timeout 10 --max-time 90 \
            --output "$temp_dir/$arquivo" \
            "https://github.com/BetterDiscord/cli/releases/download/v$versao_cli/$arquivo" ||
            return 1
        printf '%s  %s\n' "$sha256" "$temp_dir/$arquivo" | sha256sum --check --status ||
            { printf 'O arquivo baixado não confere com o SHA-256 esperado.\n' >&2; return 1; }
        tar -xzf "$temp_dir/$arquivo" -C "$temp_dir" -- bdcli
    }

    falha_mod=0
    if (( atualizar_mod )) && ! baixar_cli; then
        if [[ $acao != agendado ]]; then
            falhar 'Não foi possível preparar a CLI do BetterDiscord.'
        fi
        falha_mod=1
        printf 'Não foi possível preparar a CLI do BetterDiscord.\n' >&2
    fi

    falha_discord=0
    if [[ $acao == pacman ]]; then
        pacman -Q discord >/dev/null || falhar 'O pacote discord não está instalado pelo pacman.'
        printf 'Verificando o pacote discord e as atualizações do Arch pelo pacman...\n'
        sudo pacman -Syu --needed discord 9>&- || falha_discord=1
    fi

    fechar_discord
    if [[ $acao != desinstalar ]]; then
        if ! atualizar_discord; then
            falha_discord=1
            recursos=$(descobrir_recursos) || falhar "$aviso_discord"
            printf 'Continuando com o BetterDiscord na versão disponível do Discord.\n'
        fi
        verificar_recursos
    fi

    if (( ! atualizar_mod )); then
        printf 'BetterDiscord desativado no perfil.\n'
        return "$falha_discord"
    fi
    (( ! falha_mod )) || return 1

    unset BDCLI_DEV_BUILD
    if [[ $acao == desinstalar ]]; then
        comando_cli=(uninstall --path "$recursos")
    elif betterdiscord_injetado; then
        comando_cli=(update)
    else
        comando_cli=(install --path "$recursos")
    fi

    # A CLI v1.0.0 tenta encerrar qualquer processo chamado Discord em install/uninstall.
    fechar_discord
    if [[ ${comando_cli[0]} != update ]] && discord_em_execucao; then
        falhar 'Outra instância do Discord está aberta e impede a aplicação segura do carregador.'
    fi
    if [[ $acao != desinstalar && -s $mod_asar ]]; then
        cp -p -- "$mod_asar" "$temp_dir/betterdiscord.anterior.asar"
        mod_em_alteracao=1
    fi
    timeout --kill-after=10s 5m "$temp_dir/bdcli" "${comando_cli[@]}" 9>&- ||
        falhar 'A CLI do BetterDiscord não concluiu a operação. Confira a mensagem acima.'
    mod_em_alteracao=0

    if [[ $acao == desinstalar ]]; then
        touch -- "$mod_desativado"
        printf '\nBetterDiscord desativado. Os plugins e temas continuam guardados.\n'
    elif [[ $acao != agendado ]]; then
        rm -f -- "$mod_desativado"
        printf '\nNo Discord, vá em Configurações → BetterDiscord → Plugins ou Temas.\n'
    fi
    if (( falha_discord )); then
        falhar 'A etapa do BetterDiscord terminou, mas uma atualização do Discord falhou.'
    fi
)

atualizar_sistema() {
    local origem=$1

    if ! etapa 'Arch e aplicativos dos repositórios' atualizar_arch "$origem"; then
        printf 'A etapa do AUR aguarda uma atualização bem-sucedida do Arch.\n'
        return 1
    fi
    if [[ -n $(pacman -Qmq) ]]; then
        etapa 'Aplicativos do AUR' atualizar_aur || return
    fi
}

atualizar_apps() {
    local usuario=$1 home=$2 falhou=0

    if [[ -x /usr/bin/flatpak ]]; then
        etapa 'Flatpaks do sistema' flatpak update --system --noninteractive --assumeyes || falhou=1
        etapa "Flatpaks de $usuario" como_usuario "$usuario" "$home" \
            /usr/bin/dbus-run-session -- /usr/bin/flatpak update --user --noninteractive --assumeyes ||
            falhou=1
    else
        printf 'Flatpak ausente.\n'
    fi

    etapa 'Discord nativo e BetterDiscord' como_usuario "$usuario" "$home" "$program" --discord-agendado ||
        falhou=1
    return "$falhou"
}

registrar_atualizacao() {
    local usuario=$1 modo=$2 origem=$3 home codigo=0
    home=$(home_do_usuario "$usuario")
    {
        printf '\n===== Atualização (%s, %s) | %s =====\n' "$modo" "$origem" "$(date -Is)"
        case $modo in
            sistema) atualizar_sistema "$origem" || codigo=$? ;;
            apps) atualizar_apps "$usuario" "$home" || codigo=$? ;;
            discord)
                etapa 'Discord nativo e BetterDiscord' como_usuario "$usuario" "$home" \
                    "$program" --discord-sessao || codigo=$?
                ;;
        esac
        printf '===== Fim da atualização | %s | código %s =====\n' "$(date -Is)" "$codigo"
        return "$codigo"
    } 2>&1 | {
        # O log é aberto com as permissões do usuário. O journal recebe a mesma saída.
        como_usuario "$usuario" "$home" "$program" --log ||
            { printf 'Não foi possível gravar o log em Documentos.\n' >&2; return 1; }
    }
}

instalar_atalhos() {
    local documentos
    documentos=$(pasta_de_documentos)
    mkdir -p -- "$documentos"
    install -m 0755 -T -- "$program" "$documentos/atualizador-do-sistema.sh"
    install -m 0755 -T -- "$atalho_menu" "$documentos/Atualizador do sistema.desktop"
    printf 'Atalho criado em %s/Atualizador do sistema.desktop\n' "$documentos"
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
Keywords=atualizador;atualização;Arch;pacman;Flatpak;Discord;BetterDiscord;
DESKTOP
    install -D -m 0644 -T -- "$arquivo" "$atalho_menu"
    printf 'Atualizador do sistema disponível no menu de aplicativos.\n'
}

desativar_agendamento_antigo() {
    local em_chroot=$1 estado

    if (( em_chroot )); then
        if [[ -f /etc/systemd/system/put-update.timer ]]; then
            systemctl --root=/ disable put-update.timer
        fi
        rm -f -- /etc/systemd/system/put-update.timer /etc/systemd/system/put-update.service
        return
    fi

    estado=$(systemctl show -p LoadState --value put-update.timer)
    if [[ $estado != not-found ]]; then
        systemctl disable --now put-update.timer
    fi

    # Deixa uma atualização antiga em andamento terminar antes de trocar o programa.
    estado=$(systemctl show -p ActiveState --value put-update.service)
    if [[ $estado != inactive && $estado != failed ]]; then
        printf 'Aguardando a atualização antiga terminar para fazer a troca...\n'
        while [[ $estado != inactive && $estado != failed ]]; do
            sleep 5
            estado=$(systemctl show -p ActiveState --value put-update.service)
        done
    fi
    rm -f -- /etc/systemd/system/put-update.timer /etc/systemd/system/put-update.service
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
    flock -x 8
    temporario=$(mktemp -d)
    trap "rm -rf -- $(printf '%q' "$temporario")" EXIT

    cat > "$temporario/$servico" <<UNIT
[Unit]
Description=Atualizador Callas (%i)
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
ExecStart=$program --run $usuario %i
ExecStopPost=/usr/bin/flock -n -E 0 $lock_atualizador /usr/bin/rm -f -- $sudo_rule
StandardOutput=journal
StandardError=journal
UNIT

    for modo in sistema apps; do
        timer=put-update-$modo.timer
        hora=$(hora_agendada "$modo")
        cat > "$temporario/$timer" <<UNIT
[Unit]
Description=Atualização agendada ($modo)

[Timer]
OnCalendar=*-*-* $hora:00:00
Persistent=false
Unit=put-update@$modo.service

[Install]
WantedBy=timers.target
UNIT
    done

    desativar_agendamento_antigo "$em_chroot"
    rm -f -- "$sudo_rule"

    if [[ -x /usr/bin/paru ]]; then
        install -d -m 0755 /var/lib/put-update
        if ! getent passwd "$builder" >/dev/null; then
            useradd --system --create-home --user-group --home-dir "$builder_home" \
                --shell /usr/bin/nologin "$builder"
        fi
        conta=$(getent passwd "$builder" | cut -d: -f6-7)
        [[ "$conta" == "$builder_home:/usr/bin/nologin" ]] ||
            erro "A conta $builder já existe com outra configuração."
        [[ -d "$builder_home" && ! -L "$builder_home" &&
            "$(stat -c '%U' -- "$builder_home")" == "$builder" ]] ||
            erro "Pasta da conta $builder inválida."
        chmod 0700 "$builder_home"
        if [[ -r /etc/callas/spotify-aur.gpg ]]; then
            como_usuario "$builder" "$builder_home" /usr/bin/gpg --batch --import /etc/callas/spotify-aur.gpg ||
                printf 'A chave do Spotify não foi importada para a conta que atualiza o AUR.\n' >&2
        fi

        cat > "$temporario/put-update-makepkg" <<'MAKEPKG'
#!/usr/bin/bash
exec /usr/bin/setpriv --no-new-privs -- /usr/bin/makepkg "$@"
MAKEPKG
        cat > "$temporario/put-update-paru.conf" <<'PARU'
[bin]
Makepkg = /usr/local/libexec/put-update-makepkg
Sudo = /usr/bin/sudo
SudoFlags = -n
PARU
        printf '%s ALL=(root) NOPASSWD: /usr/bin/pacman\n' "$builder" > "$temporario/put-update"
        chmod 0440 "$temporario/put-update"
        visudo -cf "$temporario/put-update" >/dev/null
        install -D -m 0755 "$temporario/put-update-makepkg" /usr/local/libexec/put-update-makepkg
        install -m 0644 "$temporario/put-update-paru.conf" "$paru_conf"
        install -m 0440 "$temporario/put-update" "$sudo_template"
    else
        printf 'Paru ausente. A atualização do AUR ainda não foi configurada.\n'
    fi

    preparar_agenda
    # O programa pode já ser a origem quando o automático é reconfigurado pelo atalho.
    if [[ $origem != "$program" ]]; then
        install -D -m 0755 -T -- "$origem" "$program"
    fi
    install -m 0644 -- "$temporario/$servico" "$temporario/$timer_sistema" \
        "$temporario/$timer_apps" /etc/systemd/system/
    instalar_entrada_menu "$temporario/${atalho_menu##*/}"
    if (( em_chroot )); then
        systemctl --root=/ enable "$timer_sistema" "$timer_apps"
    else
        systemctl daemon-reload
        systemctl enable "$timer_sistema" "$timer_apps"
        systemctl restart "$timer_sistema" "$timer_apps"
    fi

    printf '\nAgendamento automático configurado.\n'
    printf 'Próxima atualização do sistema: %s às %sh.\n' "$(ler_data_agenda sistema)" "$hora_sistema"
    printf 'Próxima atualização dos aplicativos: %s às %sh.\n' "$(ler_data_agenda apps)" "$hora_apps"
    printf 'Se perder o horário, a atualização fica para a próxima tarde com o PC ligado.\n'
    como_usuario "$usuario" "$home" "$program" --instalar-atalhos
    if pasta=$(como_usuario "$usuario" "$home" "$program" --log-dir); then
        printf 'Log em Documentos: %s/atualizacoes.log\n' "$pasta"
    else
        printf 'Não foi possível criar a pasta de logs em Documentos.\n' >&2
    fi
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
        printf '%s\n' \
            '1. Ativar ou reparar o automático (sistema mensal e aplicativos semanais)' \
            '2. Atualizar só os aplicativos agora (Flatpak, Discord e BetterDiscord)' \
            '3. Atualizar só o sistema agora (Arch, pacman e AUR)' \
            '4. Atualizar só o Discord e o BetterDiscord agora' \
            '5. Sair'
        read -r -p 'Escolha [1-5]: ' opcao || return 0
        case $opcao in
            1)
                sudo /usr/bin/bash "$origem" --instalar ||
                    printf 'Falha ao configurar o automático. Confira a mensagem acima.\n' >&2
                continue
                ;;
            2) modo=apps ;;
            3) modo=sistema ;;
            4) modo=discord ;;
            5) return 0 ;;
            *) printf 'Opção inválida.\n'; continue ;;
        esac

        if [[ $origem != "$program" ]] && ! cmp -s -- "$origem" "$program"; then
            printf 'Escolha a opção 1 para instalar esta versão antes de atualizar.\n'
            continue
        fi
        sudo "$program" --manual "$modo" ||
            printf 'Atualização com falha. Confira a mensagem acima e o log em Documentos.\n' >&2
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
    --run)
        (( EUID == 0 && $# == 3 )) || erro 'Esta opção é usada pelo serviço de atualização.'
        [[ $3 == sistema || $3 == apps ]] || erro 'Modo automático inválido.'
        exec flock -x -o "$lock_atualizador" "$program" --registrar "$2" "$3" automatico
        ;;
    --manual)
        (( EUID == 0 && $# == 2 )) || erro 'Esta opção é usada pelo menu de atualização.'
        [[ -n ${SUDO_USER:-} && $SUDO_USER != root ]] || erro 'Abra o menu com seu usuário normal.'
        [[ $2 == sistema || $2 == apps || $2 == discord ]] || erro 'Modo manual inválido.'
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
        (( EUID != 0 && $# == 1 )) || erro 'Use esta opção como usuário normal.'
        pasta=$(pasta_de_logs)
        umask 077
        exec tee --output-error=warn -a -- "$pasta/atualizacoes.log"
        ;;
    ''|--menu)
        (( EUID != 0 && $# <= 1 )) || erro 'Abra o atualizador com seu usuário normal, sem sudo.'
        menu
        ;;
    *) erro 'Use bash atualizador-do-sistema.sh para abrir o menu.' ;;
esac
CALLAS_UPDATER
cat > "/mnt/usr/local/libexec/callas-inicio-kde" <<'CALLAS_KDE_START'
#!/usr/bin/env bash
set -euo pipefail

if (( EUID == 0 )); then
    printf '%s\n' 'Rode este arquivo no Konsole com seu usuário normal. Ele pede sudo só para corrigir o atualizador.' >&2
    exit 1
fi

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
    planos["discord"] = ("callas-discord.desktop", desktop("Discord", launcher(discord, "--start-minimized"), "discord"))
    perfil = config / "discord"
    if not perfil.exists():
        perfil.mkdir(mode=0o700)
    if perfil.is_dir():
        try:
            arquivo = perfil / "settings.json"
            ajustes = json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.exists() else {}
            if not isinstance(ajustes, dict):
                raise ValueError("settings.json não contém um objeto")
            novos = dict(ajustes, OPEN_ON_STARTUP=False, MINIMIZE_TO_TRAY=True)
            if novos != ajustes:
                gravar(arquivo, json.dumps(novos, indent=2, ensure_ascii=False) + "\n", 0o600)
        except (OSError, ValueError) as erro:
            avisos.append(f"Discord: não consegui ajustar a preferência da bandeja ({erro}).")
else:
    avisos.append("Discord nativo não encontrado. Mantive as entradas dele.")

steam = shutil.which("steam")
if steam:
    planos["steam"] = ("steam.desktop", desktop("Steam", launcher(steam, "-silent"), "steam"))
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
    script_kde = campos.get("X-KDE-AutostartScript", "").lower() == "true"
    script_shell = bool(re.search(r"\.sh(?:[\s\"']|$)", campos.get("Exec", "")))
    outro_app_do_usuario = (
        nome in locais and not app and campos.get("Type") == "Application"
        and not script_kde and not script_shell
    )
    if app == "extra" or app in planos or outro_app_do_usuario:
        if campos.get("Hidden", "").lower() == "true":
            continue
        gravar(auto / nome, "[Desktop Entry]\nType=Application\nHidden=true\n")
        print(f"Entrada desativada: {nome}")

for nome, conteudo in planos.values():
    if nome is not None:
        gravar(auto / nome, conteudo)

if any(backup.iterdir()):
    print(f"Backup das configurações: {backup}")
else:
    backup.rmdir()
for aviso in avisos:
    print(f"Aviso: {aviso}")
print("Sessão vazia configurada para o próximo login no KDE.")
PY
CALLAS_KDE_START
cat > "/mnt/usr/local/libexec/callas-kde-desligamento-login" <<'CALLAS_KDE_LOGIN'
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
    local resultado=0
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
        aplicar)
            [[ $# == 3 && $3 =~ ^[[:alnum:]]+(-[[:alnum:]]+)+$ ]] || erro 'saída inválida.'
            modo_sistema aplicar "$3"
            exit
            ;;
        desfazer) modo_sistema desfazer; exit ;;
    esac
fi
[[ $EUID != 0 ]] || erro 'rode com bash no Konsole, como seu usuário. O script pede sudo quando precisar.'
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
sudo /usr/bin/bash -- "$script" --sistema aplicar "$principal" < "$novo_login"
CALLAS_KDE_LOGIN
cat > "/mnt/usr/local/libexec/callas-nekofetch" <<'CALLAS_NEKO'
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
            modulo.get("type") == ancora or ancora in modulo.get("key", "").split()
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
CALLAS_NEKO
cat > "/mnt/usr/local/libexec/callas-apps-pos-login" <<'CALLAS_APPS'
#!/usr/bin/bash
set -uo pipefail
config=${XDG_CONFIG_HOME:-$HOME/.config}
estado=${XDG_STATE_HOME:-$HOME/.local/state}/callas
mkdir -p "$estado" || exit 1

preparar_betterdiscord() {
  local perfil="$config/discord" recursos
  [[ ! -e "$estado/betterdiscord-inicial" && ! -e "$perfil/.callas-betterdiscord-desativado" ]] || return 0
  # O Discord gera os recursos locais só na primeira execução.
  for recursos in "$perfil"/app-*/resources; do
    if [[ -s "$recursos/app.asar" || -s "$recursos/betterdiscord.app.asar" ]]; then
      # A mesma trava por perfil impede alterações simultâneas pelo atualizador.
      /usr/local/libexec/put-update --discord-sessao &&
        touch "$estado/betterdiscord-inicial"
      return
    fi
  done
}

instalar_marketplace() (
  set -e
  local raiz="$config/spicetify"
  local apps="$raiz/CustomApps" tmp
  install -d "$apps" || return 1
  tmp=$(mktemp -d -- "$apps/.callas-marketplace.XXXXXXXX") || return 1
  trap 'rm -rf -- "$tmp"' EXIT
  curl -fsSL --retry 2 --max-time 90 \
    https://github.com/spicetify/marketplace/releases/latest/download/marketplace.zip \
    -o "$tmp/marketplace.zip" || return 1
  unzip -q "$tmp/marketplace.zip" -d "$tmp" || return 1
  [[ -s "$tmp/marketplace-dist/manifest.json" ]] || return 1
  install -d "$apps/marketplace" || return 1
  cp -a "$tmp/marketplace-dist/." "$apps/marketplace/" || return 1
)

preparar_spicetify() {
  local prefs="$config/spotify/prefs" versao
  command -v spicetify >/dev/null && [[ -s $prefs && -w /opt/spotify/Apps ]] || return 0
  # Aplica quando o Spotify estiver fechado, sem abri-lo junto com a sessão.
  pgrep -u "$EUID" -x spotify >/dev/null && return 0
  versao=$(pacman -Q spotify spicetify-cli) || return 1
  if [[ -f "$estado/spotify-versao" && $(< "$estado/spotify-versao") == "$versao" ]]; then
    return 0
  fi
  spicetify config spotify_path /opt/spotify || return 1
  spicetify config prefs_path "$prefs" || return 1
  spicetify backup apply || return 1
  if [[ ! -s "$config/spicetify/CustomApps/marketplace/manifest.json" ]]; then
    instalar_marketplace || return 1
  fi
  spicetify config inject_css 1 replace_colors 1 || return 1
  spicetify config custom_apps marketplace || return 1
  spicetify apply && printf '%s\n' "$versao" > "$estado/spotify-versao"
}

resultado=0
preparar_betterdiscord || resultado=1
preparar_spicetify || resultado=1
exit "$resultado"
CALLAS_APPS
cat > /mnt/usr/local/libexec/callas-spotify-permissoes <<'CALLAS_SPOTIFY_ACL'
#!/usr/bin/bash
set -euo pipefail
usuario=$1
[[ -d /opt/spotify/Apps && ! -L /opt/spotify && ! -L /opt/spotify/Apps ]]
setfacl -m "u:$usuario:rwx" /opt/spotify
setfacl -R -m "u:$usuario:rwX" /opt/spotify/Apps
CALLAS_SPOTIFY_ACL
chmod 0755 /mnt/usr/local/libexec/{put-update,callas-inicio-kde,callas-kde-desligamento-login,callas-nekofetch,callas-apps-pos-login,callas-spotify-permissoes}

install -d /mnt/usr/lib/systemd/user
cat > /mnt/usr/lib/systemd/user/callas-apps-pos-login.service <<'APPS_SERVICE'
[Unit]
Description=Preparar BetterDiscord e Spicetify nos perfis dos aplicativos
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=oneshot
ExecStart=/usr/local/libexec/callas-apps-pos-login
TimeoutStartSec=25min
APPS_SERVICE

cat > /mnt/usr/lib/systemd/user/callas-apps-pos-login.timer <<'APPS_TIMER'
[Unit]
Description=Verificar os complementos dos aplicativos durante a sessão
PartOf=graphical-session.target

[Timer]
OnActiveSec=3min
OnUnitInactiveSec=5min
APPS_TIMER

install -d /mnt/etc/xdg
cat > /mnt/etc/xdg/kicker-extra-favoritesrc <<'KICKER_FAVORITES'
[General]
IgnoreDefaults=true
Prepend=org.kde.kontact.desktop;systemsettings.desktop;org.kde.dolphin.desktop;org.kde.discover.desktop;io.github.Callas157.AtualizadorDoSistema.desktop;
KICKER_FAVORITES

# O Plasma executa esta configuração uma vez, depois de criar o painel.
plasma_updates=/mnt/usr/share/plasma/shells/org.kde.plasma.desktop/contents/updates
if ! install -d "$plasma_updates" ||
   ! cat > "$plasma_updates/callas-panel-v1.js" <<'PLASMA_PANEL'
const callasIcon = fileExists("/usr/share/icons/hicolor/256x256/apps/callas-plasma-icon.png");
const callasLaunchers = ["applications:org.kde.dolphin.desktop"];
if (fileExists("/usr/share/applications/brave-browser.desktop")) {
    callasLaunchers.push("applications:brave-browser.desktop");
}

panels().forEach(function (panel) {
    panel.widgets("org.kde.plasma.icontasks").forEach(function (tasks) {
        tasks.currentConfigGroup = ["General"];
        tasks.writeConfig("launchers", callasLaunchers);
        tasks.reloadConfig();
    });

    if (callasIcon) {
        panel.widgets("org.kde.plasma.kickoff").forEach(function (menu) {
            menu.currentConfigGroup = ["General"];
            menu.writeConfig("icon", "callas-plasma-icon");
            menu.reloadConfig();
        });
    }
});
PLASMA_PANEL
then
  echo "Aviso: não consegui preparar o painel do KDE. Seguindo com a instalação." >&2
fi

# ---------------- Configuração dentro do sistema ----------------
echo ">>> Configurando o sistema"
arch-chroot /mnt /bin/bash -s -- "$USUARIO" "$FUSO" "$LOCALE" "$TECLADO" \
  "$HOSTNAME" "$UUID_RAIZ" "$NVIDIA" "$VM" "$BROADCOM" "$GPU_PCI" <<'CALLAS_CHROOT'
set -Eeuo pipefail
usuario=$1
fuso=$2
locale=$3
teclado=$4
hostname=$5
uuid_raiz=$6
nvidia=$7
vm=$8
broadcom=$9
gpu_pci=${10}
home=/home/$usuario
libexec=/usr/local/libexec
avisos=/var/log/callas-instalacao-avisos.log

aviso() {
  printf 'Aviso: %s\n' "$*" | tee -a "$avisos" >&2
}

ln -sf "/usr/share/zoneinfo/$fuso" /etc/localtime
hwclock --systohc || aviso 'Relógio de hardware indisponível.'
sed -i 's/^#pt_BR.UTF-8/pt_BR.UTF-8/; s/^#en_US.UTF-8/en_US.UTF-8/' /etc/locale.gen
locale-gen
printf 'LANG=%s\n' "$locale" > /etc/locale.conf
printf 'KEYMAP=%s\nXKBLAYOUT=us\nXKBVARIANT=intl\n' "$teclado" > /etc/vconsole.conf
install -d /etc/X11/xorg.conf.d
cat > /etc/X11/xorg.conf.d/00-keyboard.conf <<'KBD'
Section "InputClass"
    Identifier "teclado"
    MatchIsKeyboard "on"
    Option "XkbLayout" "us"
    Option "XkbVariant" "intl"
EndSection
KBD
printf '%s\n' "$hostname" > /etc/hostname
printf '127.0.0.1 localhost\n::1 localhost\n127.0.1.1 %s.localdomain %s\n' "$hostname" "$hostname" > /etc/hosts

sed -i 's/^#ParallelDownloads.*/ParallelDownloads = 10/; s/^#Color/Color/' /etc/pacman.conf
sed -i '/^#\[multilib\]/,/^#Include/ s/^#//' /etc/pacman.conf
useradd -m -U -G wheel -s /bin/bash "$usuario"
printf '%%wheel ALL=(ALL:ALL) ALL\n' > /etc/sudoers.d/10-wheel
chmod 0440 /etc/sudoers.d/10-wheel
visudo -cf /etc/sudoers.d/10-wheel >/dev/null

como_usuario() {
  runuser -u "$usuario" -- env HOME="$home" USER="$usuario" LOGNAME="$usuario" "$@"
}

# O SDDM inicia o Plasma em Wayland. Os monitores permanecem ativos no greeter.
install -d /etc/sddm.conf.d /var/lib/sddm
cat > /etc/sddm.conf.d/10-wayland.conf <<'SDDM'
[General]
DisplayServer=wayland
GreeterEnvironment=QT_WAYLAND_SHELL_INTEGRATION=layer-shell

[Wayland]
CompositorCommand=kwin_wayland --drm --no-lockscreen --no-global-shortcuts --locale1

[Theme]
Current=breeze
CursorTheme=breeze_cursors
SDDM
cat > /var/lib/sddm/state.conf <<'SDDM_STATE'
[Last]
Session=/usr/share/wayland-sessions/plasma.desktop
SDDM_STATE
chown sddm:sddm /var/lib/sddm/state.conf

# O PAM abre a carteira KDE com a senha do login.
if ! grep -q 'pam_kwallet' /etc/pam.d/sddm; then
  printf '%s\n' 'auth optional pam_kwallet5.so' \
    'session optional pam_kwallet5.so auto_start kwalletd=/usr/bin/ksecretd' >> /etc/pam.d/sddm
fi
install -d -o "$usuario" -g "$usuario" "$home/.config" "$home/.config/autostart" "$home/.local" "$home/.local/bin"
cat > "$home/.config/kwalletrc" <<'KWRC'
[Wallet]
Default Wallet=kdewallet
Leave Open=true
Close When Idle=false
KWRC
printf '%s\n' '--password-store=kwallet6' > "$home/.config/brave-flags.conf"
cat > /usr/local/bin/configurar-carteira <<'CARTEIRA'
#!/usr/bin/bash
sleep 10
if busctl --user call org.kde.kwalletd6 /modules/kwalletd6 org.kde.KWallet open sxs kdewallet 0 primeiro-login >/dev/null 2>&1; then
  rm -f "$HOME/.config/autostart/configurar-carteira.desktop"
fi
CARTEIRA
chmod 0755 /usr/local/bin/configurar-carteira
cat > "$home/.config/autostart/configurar-carteira.desktop" <<'AUTOSTART'
[Desktop Entry]
Type=Application
Name=Configurar carteira KDE
Exec=/usr/local/bin/configurar-carteira
AUTOSTART

cat > /etc/systemd/zram-generator.conf <<'ZRAM'
[zram0]
zram-size = ram / 2
compression-algorithm = zstd
ZRAM

# Dependências gráficas do Steam. O driver virtual ou de software evita
# puxar NVIDIA em uma VM que apresenta apenas VMSVGA, Virtio ou VGA.
gpu_multilib=(lib32-mesa)
if (( nvidia )); then
  gpu_multilib+=(lib32-nvidia-utils)
fi
if grep -q '^1002:' <<<"$gpu_pci"; then
  gpu_multilib+=(vulkan-radeon lib32-vulkan-radeon)
fi
if grep -q '^8086:' <<<"$gpu_pci"; then
  gpu_multilib+=(vulkan-intel lib32-vulkan-intel)
fi
if [[ $vm != none && -n $vm ]] && grep -q '^1af4:' <<<"$gpu_pci"; then
  gpu_multilib+=(vulkan-virtio lib32-vulkan-virtio)
fi
if (( ${#gpu_multilib[@]} == 1 )); then
  gpu_multilib+=(vulkan-swrast lib32-vulkan-swrast)
fi
pacman -Syu --needed --noconfirm "${gpu_multilib[@]}" vulkan-icd-loader lib32-vulkan-icd-loader steam discord shotcut

# O KMS padrão cobre Mesa e GPUs virtuais. Só antecipa os módulos da NVIDIA
# quando ela foi detectada e o pacote correspondente está instalado.
install -d /etc/plymouth
cat > /etc/plymouth/plymouthd.conf <<'PLYMOUTH_CONF'
[Daemon]
Theme=callas
ShowDelay=0
UseFirmwareBackground=false
PLYMOUTH_CONF
# O hook microcode incorpora o microcódigo Intel ou AMD no initramfs.
sed -i 's/^HOOKS=.*/HOOKS=(base systemd autodetect microcode modconf kms plymouth keyboard sd-vconsole block filesystems fsck)/' /etc/mkinitcpio.conf
nvidia_args=
if (( nvidia )); then
  sed -i 's/^MODULES=().*/MODULES=(nvidia nvidia_modeset nvidia_uvm nvidia_drm)/' /etc/mkinitcpio.conf
  nvidia_args=' nvidia_drm.modeset=1 nvidia_drm.fbdev=1'
fi
mkinitcpio -P
test -s /boot/vmlinuz-linux && test -s /boot/initramfs-linux.img

# GRUB UEFI: instalação limpa experimental, preservando a partição EFI em /boot.
# Plymouth permanece integrado ao initramfs; sem atrasos artificiais no carregamento.
cat > /etc/default/grub <<GRUB_DEFAULTS
GRUB_DEFAULT=0
GRUB_TIMEOUT=3
GRUB_TIMEOUT_STYLE=menu
GRUB_DISTRIBUTOR="Callas OS"
GRUB_CMDLINE_LINUX_DEFAULT="quiet splash$nvidia_args"
GRUB_CMDLINE_LINUX=""
GRUB_TERMINAL_OUTPUT=gfxterm
GRUB_GFXMODE=auto
GRUB_GFXPAYLOAD_LINUX=keep
GRUB_DISABLE_OS_PROBER=true
GRUB_DEFAULTS

# Segunda opção para diagnóstico, sem Plymouth e com mensagens visíveis.
cat > /etc/grub.d/42_callas_diagnostico <<'GRUB_DIAG'
#!/bin/sh
cat <<'MENU'
menuentry 'Callas OS (diagnóstico sem splash)' --class gnu-linux {
    search --no-floppy --fs-uuid --set=root CALLAS_EFI_UUID
    linux /vmlinuz-linux root=UUID=CALLAS_ROOT_UUID rw plymouth.enable=0
    initrd /initramfs-linux.img
}
MENU
GRUB_DIAG
sed -i "s/CALLAS_EFI_UUID/$(findmnt -no UUID /boot)/" /etc/grub.d/42_callas_diagnostico
sed -i "s/CALLAS_ROOT_UUID/$uuid_raiz/" /etc/grub.d/42_callas_diagnostico
chmod 0755 /etc/grub.d/42_callas_diagnostico

# Caminho de recuperação UEFI, útil quando o firmware não grava entradas NVRAM.
grub-install --target=x86_64-efi --efi-directory=/boot --bootloader-id=CallasOS --recheck || \
  grub-install --target=x86_64-efi --efi-directory=/boot --removable --no-nvram --recheck
grub-mkconfig -o /boot/grub/grub.cfg
[[ -s /boot/grub/grub.cfg && -f /boot/grub/x86_64-efi/normal.mod ]]

systemctl --root=/ enable NetworkManager sddm bluetooth fstrim.timer systemd-timesyncd

# Solaar nativo como padrão. Os overrides também deixam pronta a versão Flatpak
# para quem a instalar no futuro. Somente o usuário da sessão ganha o acesso udev.
install -d /etc/udev/rules.d
cat > /etc/udev/rules.d/59-callas-logitech-hidraw.rules <<'UDEV'
SUBSYSTEM=="hidraw", KERNEL=="hidraw*", ATTRS{idVendor}=="046d", MODE="0660", TAG+="uaccess"
SUBSYSTEM=="hidraw", KERNEL=="hidraw*", KERNELS=="*046D:*", MODE="0660", TAG+="uaccess"
UDEV
como_usuario flatpak override --user --device=all --env=GTK_THEME=Adwaita:dark io.github.pwr_solaar.solaar ||
  aviso 'Não consegui preparar os ajustes do Solaar Flatpak.'
if [[ -f /usr/share/applications/solaar.desktop ]]; then
  install -d /usr/local/share/applications
  sed 's|^Exec=|Exec=env GTK_THEME=Adwaita:dark |' /usr/share/applications/solaar.desktop \
    > /usr/local/share/applications/solaar.desktop
fi

if flatpak remote-add --system --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo; then
  for app in com.vysp3r.ProtonPlus io.github.kolunmi.Bazaar; do
    flatpak install --system --noninteractive --assumeyes flathub "$app" || aviso "Falha ao instalar $app."
  done
else
  aviso 'Não consegui configurar o Flathub.'
fi

# O mesmo Paru serve para a instalação inicial e para o atualizador.
temporario_aur=$(mktemp -d)
chown "$usuario:$usuario" "$temporario_aur"
sudo_temporario=/etc/sudoers.d/99-callas-instalacao
limpar_aur() {
  rm -f -- "$sudo_temporario"
  rm -rf -- "$temporario_aur"
}
trap limpar_aur EXIT
printf '%s ALL=(root) NOPASSWD: /usr/bin/pacman\n' "$usuario" > "$sudo_temporario"
chmod 0440 "$sudo_temporario"
visudo -cf "$sudo_temporario" >/dev/null
if como_usuario git clone --depth 1 https://aur.archlinux.org/paru-bin.git "$temporario_aur/paru-bin" &&
   como_usuario bash -c 'cd "$1" && makepkg -si --needed --noconfirm' bash "$temporario_aur/paru-bin" </dev/null; then
  instalar_aur() {
    como_usuario paru -S --needed --noconfirm --skipreview "$@" </dev/null ||
      { aviso "Falha ao instalar via AUR: $*."; return 1; }
  }
  instalar_aur brave-bin || :
  instalar_aur gpu-screen-recorder gpu-screen-recorder-gtk || :
  if (( nvidia )); then
    instalar_aur nvibrant-bin || :
  fi
  # A chave pública é conferida pelo fingerprint do PKGBUILD do Spotify.
  chave_spotify=/etc/callas/spotify-aur.gpg
  install -d /etc/callas
  if curl -fsSL --retry 2 --max-time 45 https://download.spotify.com/debian/pubkey_5384CE82BA52C83A.gpg -o "$chave_spotify" &&
     gpg --batch --no-options --with-colons --show-keys "$chave_spotify" |
       awk -F: '$1 == "fpr" && $10 == "E1096BCBFF6D418796DE78515384CE82BA52C83A" {ok=1} END {exit !ok}' &&
     como_usuario gpg --batch --import "$chave_spotify"; then
    instalar_aur spotify || :
  else
    rm -f -- "$chave_spotify"
    aviso 'A chave do Spotify não pôde ser verificada ou importada.'
  fi
  instalar_aur spicetify-cli || :
  if instalar_aur xone-dkms xone-dongle-firmware; then
    # O uname do chroot ainda retorna o kernel da ISO. Verifica o kernel do disco.
    for pkgbase in /usr/lib/modules/*/pkgbase; do
      [[ -f $pkgbase && $(< "$pkgbase") == linux ]] || continue
      release=${pkgbase%/pkgbase}
      release=${release##*/}
      if ! modinfo -k "$release" xone-dongle >/dev/null; then
        dkms autoinstall -k "$release" &&
          modinfo -k "$release" xone-dongle >/dev/null ||
          aviso "O DKMS não preparou o xone para o kernel $release."
      fi
    done
  fi
  if (( broadcom )); then
    instalar_aur broadcom-wl-dkms || :
  fi
else
  aviso 'Falha ao instalar o Paru. Os pacotes opcionais do AUR ficaram pendentes.'
fi
limpar_aur
trap - EXIT

if command -v nvibrant >/dev/null; then
  cat > "$home/.local/bin/DigitalVibrance.sh" <<'VIBRANCE'
#!/usr/bin/bash
exec nvibrant 1023 1023 1023 1023 1023 1023
VIBRANCE
  chmod 0755 "$home/.local/bin/DigitalVibrance.sh"
fi
chown -R "$usuario:$usuario" "$home/.local" "$home/.config"
como_usuario env LANG="$locale" xdg-user-dirs-update || aviso 'Não consegui preparar as pastas do usuário.'
como_usuario env QT_QPA_PLATFORM=offscreen dbus-run-session -- plasma-apply-lookandfeel --apply org.kde.breezedark.desktop ||
  aviso 'Não consegui aplicar o tema Brisa Escuro.'
como_usuario "$libexec/callas-inicio-kde" || aviso 'Não consegui aplicar o início de sessão do KDE.'
"$libexec/callas-kde-desligamento-login" --preparar-instalacao ||
  aviso 'O ajuste de desligamento ou do tema de login precisa ser conferido.'
"$libexec/put-update" --instalar-para "$usuario" || aviso 'Não consegui instalar o atualizador do sistema.'
como_usuario "$libexec/callas-nekofetch" || aviso 'Não consegui configurar o Nekofetch.'

# Apenas o usuário da instalação ganha acesso para o Spicetify modificar os recursos.
if pacman -Qq spotify >/dev/null && [[ -d /opt/spotify/Apps ]]; then
  install -d /etc/pacman.d/hooks
  cat > /etc/pacman.d/hooks/99-callas-spotify.hook <<SPOTIFY_HOOK
[Trigger]
Operation = Install
Operation = Upgrade
Type = Package
Target = spotify

[Action]
Description = Ajustando permissões dos recursos do Spotify para Spicetify...
When = PostTransaction
Exec = /usr/local/libexec/callas-spotify-permissoes $usuario
SPOTIFY_HOOK
  "$libexec/callas-spotify-permissoes" "$usuario" || aviso 'Não consegui configurar as permissões do Spotify.'
fi

# A ativação de BetterDiscord e Spicetify depende dos perfis gerados pelos apps.
install -d "$home/.config/systemd/user/graphical-session.target.wants"
ln -sfn /usr/lib/systemd/user/callas-apps-pos-login.timer \
  "$home/.config/systemd/user/graphical-session.target.wants/callas-apps-pos-login.timer"
chown -R "$usuario:$usuario" "$home/.config/systemd"
CALLAS_CHROOT

# Senhas pelo stdin, sem interpolar em código ou passar na linha de comando.
printf '%s:%s\n%s:%s\n' "$USUARIO" "$SENHA" root "$SENHA" | arch-chroot /mnt chpasswd
unset SENHA SENHA2

echo
echo "=========================================================="
echo " Instalação concluída!"
if [[ -s /mnt/var/log/callas-instalacao-avisos.log ]]; then
  echo " Avisos no sistema instalado: /var/log/callas-instalacao-avisos.log"
fi
echo " Remova o pendrive e digite: reboot"
echo "=========================================================="
