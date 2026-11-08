# Arch Install Callas

Instalador automático do **Arch Linux com KDE Plasma em Wayland**, em português do Brasil, com tema escuro e programas de jogos, gravação e uso diário. A instalação é voltada pra PCs com processador **AMD ou Intel** e placa de vídeo **NVIDIA compatível com `nvidia-open`**.

## Como usar

> [!CAUTION]
> **O instalador apaga todas as partições e todos os dados do disco escolhido.** Faça backup antes e confira o tamanho e o modelo do disco na tela. Este script faz uma instalação limpa no disco inteiro.

Inicie o PC pela **ISO oficial do Arch Linux**, em modo **UEFI**, com internet. De preferência, use cabo de rede. No terminal da ISO, como `root`, rode o comando com o **link curto**.

```bash
bash <(curl -sL is.gd/archcallas157)
```

**Plano B com o link direto do GitHub.** Use este comando se o link curto falhar.

```bash
bash <(curl -sL https://raw.githubusercontent.com/Callas157/arch-install/main/instalar-arch.sh)
```

## O que o script pergunta

1. **Em qual disco instalar.** Ele lista os discos com tamanho e modelo pra facilitar a identificação.
2. **Nome do usuário.** Use minúsculas e evite espaços.
3. **Senha.** Digite duas vezes pra confirmar. A mesma senha inicial será usada para o seu usuário e para a conta `root`. É normal o terminal ficar em branco enquanto você digita.

Quando aparecer **Instalação concluída**, remova o pendrive e digite `reboot`.

## O que o instalador faz

### 1. Verifica a ISO, o processador e a rede

- Confere se o script foi executado como `root`, se o PC iniciou em **UEFI** e se consegue alcançar `archlinux.org`.
- Tenta carregar o teclado **EUA Internacional com acentos** no console da ISO antes de pedir o usuário e a senha.
- Detecta se o processador é **AMD** ou **Intel** e seleciona o microcódigo correspondente, `amd-ucode` ou `intel-ucode`.
- Procura adaptadores de rede por PCI e USB. Quando detecta Wi-Fi, inclui `wpa_supplicant`, `iw` e `wireless-regdb` na instalação.
- Para os modelos Broadcom identificados pela regra do script, tenta instalar o driver **`broadcom-wl-dkms`** pelo AUR.
- Ativa a sincronização de horário na ISO e atualiza o `archlinux-keyring` antes de instalar o sistema base.

### 2. Particiona o disco e configura o boot

O script limpa as partições do disco escolhido e cria uma tabela **GPT** com duas partições.

| Partição | Tamanho | Formato | Montagem |
| --- | --- | --- | --- |
| EFI | 1 GiB | FAT32 | `/boot` |
| Raiz | Restante do disco | ext4 | `/` |

- Instala o sistema base, o kernel **`linux`**, o firmware e os cabeçalhos usados pra compilar módulos DKMS.
- Gera o `/etc/fstab` com UUIDs e instala o **systemd-boot**. A entrada padrão é **Arch Linux**, com três segundos de espera no menu.
- Configura o **zram** como swap comprimida em memória, com tamanho definido em metade da RAM e compressão **Zstandard (`zstd`)**.

### 3. Configura o sistema em português

- Define **Português do Brasil (`pt_BR.UTF-8`)** como idioma padrão e também gera `en_US.UTF-8`.
- Ajusta o fuso para **`America/Sao_Paulo`** e sincroniza o relógio de hardware durante a instalação.
- Configura **EUA Internacional com acentos** no console e grava a variante `us(intl)` na configuração do Xorg.
- Define **`arch`** como nome inicial do computador.
- Cria o usuário com **Bash** e libera o `sudo` pelo grupo `wheel`.
- Ativa cores e downloads paralelos no `pacman`. Habilita o repositório **`multilib`** pra instalar a Steam e as bibliotecas de 32 bits.
- Prepara as pastas do usuário em português, como **Documentos** e **Imagens**.
- Habilita **NetworkManager**, **SDDM**, **Bluetooth**, **sincronização de horário** e **TRIM periódico** para SSDs compatíveis.

### 4. Prepara o KDE Plasma em Wayland com tema escuro

- Instala o **KDE Plasma** e o **SDDM**, a tela de login.
- Configura o **Plasma em Wayland** como sessão padrão e o SDDM pra usar Wayland com o KWin.
- Aplica o tema global **Brisa Escuro (Breeze Dark)** ao usuário antes do primeiro login.
- Instala as ferramentas do KDE pra gerenciar rede, áudio, monitores e energia, além do portal de integração com aplicativos Flatpak.
- Instala **PipeWire** e **WirePlumber**, com as camadas de compatibilidade com ALSA e PulseAudio.
- Configura a integração do **KDE Wallet** com o login via PAM e tenta abrir a carteira `kdewallet` no primeiro acesso. Se ela ainda precisar ser criada, o KDE pode abrir o assistente. O Brave fica configurado pra usar a carteira como armazenamento de senhas.

### 5. Instala o driver NVIDIA e os programas pra jogos e gravação

| Componente | O que o script faz |
| --- | --- |
| **NVIDIA** | Instala `nvidia-open`, `nvidia-utils`, `nvidia-settings` e `egl-wayland`. Inclui os módulos NVIDIA no initramfs e configura os parâmetros de DRM no boot. |
| **Vulkan** | Instala os carregadores Vulkan de 64 e 32 bits e as bibliotecas NVIDIA de 32 bits. |
| **Steam** | Instala a versão nativa dos repositórios do Arch e configura a abertura silenciosa no login. |
| **Discord** | Instala a versão nativa dos repositórios do Arch e configura a abertura minimizada. |
| **ProtonPlus** | Tenta instalar pelo Flathub. Serve pra gerenciar ferramentas de compatibilidade da Steam, como versões alternativas do Proton. |
| **GPU Screen Recorder** | Tenta instalar o gravador e a interface GTK pelo AUR. A interface oferece controles no estilo ShadowPlay. |
| **Digital Vibrance** | Tenta instalar `nvibrant-bin` pelo AUR e prepara o perfil de cores da NVIDIA pra aplicar ao entrar no KDE. |
| **Shotcut** | Instala o editor de vídeo pelos repositórios do Arch. |

A detecção **AMD ou Intel** serve pra escolher o microcódigo do **processador**. A configuração gráfica usa **`nvidia-open`** em todas as instalações. PCs com GPU AMD, Intel ou NVIDIA que precise de driver legado exigem adaptação dessa etapa.

### 6. Instala suporte a periféricos e programas de uso diário

- **Solaar** pra gerenciar dispositivos Logitech compatíveis, como o headset **G733**. O programa fica configurado pra iniciar oculto, na bandeja do sistema. As informações e controles disponíveis dependem do dispositivo.
- **Receptor USB Xbox Wireless** com tentativa de instalação do **`xone-dkms`** e do **`xone-dongle-firmware`** pelo AUR. Depois, o script confere se o DKMS marcou o módulo como instalado e avisa se ele ficou pendente.
- **Brave** pelo pacote `brave-bin` do AUR e **qBittorrent** pelos repositórios do Arch.
- **Dolphin**, **Konsole**, **Kate**, **Ark**, **Gwenview**, **Okular** e **Spectacle** pra arquivos, terminal, edição de texto, compactados, imagens, PDFs e capturas de tela.
- Ferramentas de compactação e extração pra formatos como **RAR**, **ZIP**, **7z** e **CPIO**.
- **Flatpak** com o **Flathub** configurado no sistema. O script também tenta instalar o **Bazaar**, uma loja gráfica de aplicativos Flatpak.
- Fontes **Noto**, **Noto Emoji**, **DejaVu**, **Liberation** e **JetBrains Mono Nerd Font**.

### 7. Prepara o AUR, o Fastfetch e o Nekofetch

O script tenta instalar o **`yay`** a partir do pacote `yay-bin`. A compilação roda com o usuário criado durante a instalação. O script cria uma regra temporária de `sudo` sem senha pra essa etapa e remove a regra ao terminar o bloco de instalação dos pacotes do AUR.

O **Fastfetch** vem dos repositórios do Arch. O **Nekofetch** é instalado via `uv` no perfil do usuário e configurado pra aparecer automaticamente ao abrir um terminal interativo do **Bash**, como o Konsole. O script usa o layout da versão instalada e tenta complementar os campos abaixo.

- Versão do **kernel**.
- Nome e versão do **ambiente gráfico**.
- Resolução e taxa de atualização do **monitor**.
- Nome da **GPU** e **driver** em uso.
- **VRAM** dedicada e em uso, quando o driver disponibiliza esses dados.

## O que inicia junto com o KDE

- **Steam** em modo silencioso.
- **Discord** minimizado.
- **Solaar** na bandeja do sistema.
- **Digital Vibrance** pra aplicar o perfil de cores configurado.
- A rotina de abertura da **Carteira KDE** roda no primeiro login. O **Nekofetch** roda ao abrir o terminal interativo.

## Como o instalador trata falhas

Erros em etapas essenciais, como o particionamento, a instalação da base ou a configuração do boot, normalmente interrompem o script. Se uma etapa opcional falhar, como um pacote do AUR, um aplicativo do Flathub, o tema escuro ou o Nekofetch, o script emite um aviso e segue quando possível. Se aparecer **Instalação concluída** depois de um desses avisos, confira a saída do terminal pra ver o que ficou pendente.
