# Callas OS

> [!CAUTION]
> Projeto experimental, em evolução constante e sujeito a mudanças. Use por sua conta e risco e mantenha backup dos seus arquivos importantes.

O **Callas OS** é uma instalação automatizada do **Arch Linux com KDE Plasma em Wayland**, em português do Brasil, voltada para jogos, uso diário, gravação, periféricos e personalização do sistema.

O instalador parte da **ISO oficial do Arch Linux**, detecta o hardware disponível e monta o sistema automaticamente com o conjunto de drivers, aplicativos, serviços e personalizações compatíveis com a máquina.

## Como usar

> [!CAUTION]
> **O instalador apaga todas as partições e todos os dados do disco escolhido.** Faça backup antes de começar e confira com atenção o tamanho e o modelo do disco exibido na tela. A instalação usa o disco inteiro.

Inicie o computador pela **ISO oficial do Arch Linux**, em modo **UEFI**, com acesso à internet. De preferência, use cabo de rede.

No terminal da ISO, como `root`, rode:

```bash
bash <(curl -sL is.gd/archcallas157)
```

Se o link curto falhar, use o link direto do GitHub:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Callas157/arch-install/main/instalar-arch.sh)
```

> [!NOTE]
> Em uma máquina virtual, habilite **EFI/UEFI** nas configurações da VM antes de iniciar pela ISO do Arch.

## O que o instalador pergunta

Durante a instalação, o script pede apenas as informações essenciais:

1. **Disco de destino** — mostra os discos disponíveis com tamanho e modelo.
2. **Nome do usuário** — use letras minúsculas e sem espaços.
3. **Senha** — digitada duas vezes para confirmação. A mesma senha inicial é aplicada ao usuário criado e à conta `root`.

É normal o terminal não mostrar caracteres enquanto a senha está sendo digitada.

Quando aparecer **Instalação concluída**, remova o pendrive ou desmonte a ISO da máquina virtual e execute `reboot`.

## Detecção automática de hardware

O instalador identifica o hardware antes de montar o sistema e adapta a instalação automaticamente.

### Processador

- Detecta processadores **AMD** e **Intel**.
- Instala automaticamente o microcódigo correspondente:
  - `amd-ucode`
  - `intel-ucode`

### Placa de vídeo

O Callas OS identifica o fabricante da GPU e prepara os drivers e bibliotecas adequados.

| GPU detectada | Configuração aplicada |
| --- | --- |
| **NVIDIA** | Instala `nvidia-open`, `nvidia-utils`, `nvidia-settings`, `egl-wayland`, suporte Vulkan e bibliotecas de 32 bits para jogos. |
| **AMD Radeon** | Usa **Mesa + RADV**, com `vulkan-radeon` e bibliotecas Vulkan de 32 bits. |
| **Intel** | Usa **Mesa + ANV**, com `vulkan-intel` e bibliotecas Vulkan de 32 bits. |
| **Máquina virtual / GPU genérica** | Usa Mesa e seleciona Vulkan virtual ou renderização por software quando necessário. |

O instalador também consegue lidar com máquinas que apresentam **mais de uma GPU**, adicionando os componentes compatíveis com cada fabricante encontrado.

### Water cooler Rise Mode

O instalador procura automaticamente o dispositivo USB **Rise Mode Aura Ice Black**, identificado por `aa88:8666`.

- **Se o dispositivo for encontrado:** instala as dependências necessárias, configura Rust, baixa o `risemode-driver`, compila o driver, instala a regra udev e habilita o serviço `risemode-driver.service` para iniciar automaticamente com o sistema.
- **Se o dispositivo não for encontrado:** essa etapa é totalmente ignorada e a instalação continua normalmente.
- **Se o dispositivo for detectado, mas a compilação falhar:** o erro é registrado como aviso e a instalação principal continua.

## Particionamento, boot e sistema base

O instalador:

- cria uma tabela de partição **GPT**;
- cria uma partição EFI de **1 GiB** em FAT32, montada em `/boot`;
- usa **ext4** no restante do disco;
- instala o kernel `linux`, firmware e cabeçalhos necessários para DKMS;
- configura português do Brasil;
- usa o fuso horário **America/Sao_Paulo**;
- configura teclado **EUA Internacional**;
- prepara as pastas do usuário em português;
- habilita `sudo` para o grupo `wheel`;
- habilita **NetworkManager**;
- habilita **Bluetooth**;
- ativa sincronização automática de horário;
- ativa **TRIM periódico**;
- configura **zram** com compressão;
- adiciona os pacotes de rede necessários conforme o hardware detectado.

## GRUB Callas OS

O sistema usa **GRUB em UEFI** com identidade visual própria do Callas OS.

O instalador:

- instala o GRUB na partição EFI;
- cria também o caminho UEFI de fallback `EFI/BOOT/BOOTX64.EFI`;
- usa menu com **3 segundos**;
- aplica o tema visual do Callas OS;
- carrega logo e background próprios;
- mantém uma entrada de **diagnóstico sem splash**, útil caso seja necessário iniciar com mensagens visíveis;
- preserva os parâmetros necessários para NVIDIA quando a placa é detectada.

## Plymouth e carregamento

Depois do GRUB, o **Plymouth** assume a tela de carregamento.

O tema Callas OS inclui:

- identidade visual própria;
- logo do projeto;
- background dedicado;
- indicador de progresso;
- integração ao `initramfs`;
- carregamento sem atraso artificial adicionado pelo tema.

## KDE Plasma

O sistema é instalado com **KDE Plasma em Wayland** e tema escuro.

O instalador prepara:

- **Brisa Escuro**;
- login pelo **SDDM em Wayland**;
- formulário de login concentrado no monitor principal;
- demais monitores mantendo o wallpaper visível;
- integração da **Carteira KDE** com o login;
- sessão vazia ao entrar no Plasma;
- tempo reduzido de desligamento e reinicialização;
- ícone oficial do Callas OS no menu;
- painel e atalhos iniciais personalizados.

Na inicialização da sessão:

- **Steam** abre silenciosamente;
- **Discord** inicia minimizado;
- **Solaar** fica disponível na bandeja;
- **Digital Vibrance** é aplicado quando o utilitário está instalado;
- **Brave** e **Spotify** não são restaurados automaticamente apenas porque estavam abertos antes do desligamento.

## Identidade visual e wallpapers

O instalador baixa os assets visuais diretamente do repositório do projeto.

São instalados:

- background próprio do **GRUB**;
- background próprio do **Plymouth**;
- background da **tela de login**;
- background da **tela de bloqueio**;
- coleção com **19 wallpapers Callas OS**.

Os wallpapers ficam instalados em estrutura reconhecida pelo KDE e aparecem junto das opções de papel de parede do sistema.

O instalador tenta aplicar o **Callas OS Dark Minimal** como wallpaper inicial, sem remover os wallpapers originais do KDE.

## Jogos e gravação

### Steam

- Instala a **Steam nativa**.
- Ativa o repositório `multilib`.
- Instala bibliotecas gráficas de 32 bits adequadas à GPU detectada.
- Instala suporte Vulkan correspondente ao hardware.

### ProtonPlus

O instalador tenta instalar o **ProtonPlus** pelo Flathub para facilitar o gerenciamento de versões do Proton e ferramentas relacionadas.

### GPU Screen Recorder

O instalador tenta instalar:

- `gpu-screen-recorder`
- `gpu-screen-recorder-gtk`

Quando a interface compatível está disponível, os ajustes de integração são preparados para o ambiente KDE.

### Shotcut

O **Shotcut** é instalado pelos repositórios do Arch.

## Periféricos

### Logitech / Solaar

O instalador inclui **Solaar nativo** e prepara permissões udev para dispositivos Logitech compatíveis.

Também aplica o tema escuro e deixa ajustes preparados para a variante Flatpak caso ela seja utilizada no futuro.

### Xbox Wireless

Para receptor USB Xbox Wireless, o instalador tenta instalar:

- `xone-dkms`
- `xone-dongle-firmware`

O módulo é conferido no kernel instalado e recompilado via DKMS quando necessário.

## Aplicativos

O Callas OS prepara um conjunto de aplicativos voltado a uso diário, jogos e multimídia.

Entre eles:

- **Brave**
- **Discord**
- **Spotify**
- **Steam**
- **qBittorrent**
- **Shotcut**
- **Solaar**
- **Ark**
- **Fastfetch**
- **Nekofetch**
- **ProtonPlus**
- **Bazaar**
- **GPU Screen Recorder**

Também ficam disponíveis os componentes necessários para Flatpak e Flathub.

## Discord e BetterDiscord

O **Discord nativo** é instalado no sistema.

O instalador também prepara a automação do **BetterDiscord**. Quando o perfil necessário já existe, a personalização pode ser aplicada automaticamente.

O atualizador do sistema também consegue atualizar Discord e BetterDiscord e, quando necessário, fechar o Discord, aplicar a atualização e reabri-lo minimizado.

## Spotify e Spicetify

O instalador prepara:

- **Spotify nativo**
- **Spicetify**
- **Marketplace**

A personalização é aplicada quando o Spotify já criou os arquivos necessários para o perfil.

Também existe uma rotina para reaplicar permissões necessárias após atualizações do Spotify.

## Paru e AUR

O **Paru** é preparado a partir do `paru-bin`.

Ele é usado para instalar e atualizar pacotes disponíveis no AUR, incluindo componentes opcionais do ambiente.

As permissões temporárias usadas durante a instalação são removidas depois da etapa correspondente.

## Fastfetch e Nekofetch

O sistema inclui **Fastfetch** e prepara o **Nekofetch** para aparecer automaticamente ao abrir um terminal Bash interativo.

O layout pode exibir informações como:

- sistema;
- kernel;
- KDE Plasma;
- resolução;
- taxa de atualização;
- CPU;
- GPU;
- driver;
- VRAM dedicada usada e total, quando o driver disponibiliza esses dados.

## Digital Vibrance

Em sistemas NVIDIA, o instalador tenta instalar o `nvibrant-bin`.

Quando disponível, o Callas OS prepara o script de Digital Vibrance e sua execução junto da sessão.

## Atualizador do sistema

O Callas OS instala um **Atualizador do sistema** pesquisável pelo menu do KDE.

Ele também entra nos favoritos iniciais e pode ser removido dos favoritos sem perder o acesso pela pesquisa.

| Atualização automática | Frequência | O que atualiza |
| --- | --- | --- |
| **Aplicativos** | Semanal, às **13h** | Flatpaks, Discord nativo e BetterDiscord. |
| **Sistema** | Mensal, às **14h** | Pacotes oficiais do Arch e pacotes do AUR via Paru. |

Também é possível iniciar atualizações manualmente pelo menu.

Os registros são adicionados em:

`Documentos/Logs de Atualizações/atualizacoes.log`

Se o computador estiver desligado no horário previsto, a rotina aguarda uma próxima oportunidade válida em vez de interromper o uso normal do sistema.

## Segurança da instalação

Etapas essenciais, como:

- particionamento;
- criação do sistema de arquivos;
- instalação da base;
- configuração do boot;
- criação do GRUB;

interrompem a instalação caso ocorram erros graves.

Componentes opcionais, como determinados programas, integrações ou drivers adicionais, podem apenas registrar um aviso e permitir que a instalação principal continue.

Os avisos da instalação ficam disponíveis, quando necessário, em:

`/var/log/callas-instalacao-avisos.log`

## Resumo

O Callas OS automatiza uma instalação limpa do Arch Linux com foco em:

- **KDE Plasma Wayland**
- **GRUB personalizado**
- **Plymouth personalizado**
- **NVIDIA, AMD e Intel**
- **Steam e jogos**
- **Vulkan e bibliotecas de 32 bits**
- **GPU Screen Recorder**
- **Logitech / Solaar**
- **Xbox Wireless / xone**
- **Rise Mode automático**
- **Discord + BetterDiscord**
- **Spotify + Spicetify**
- **Fastfetch + Nekofetch**
- **atualizações automáticas**
- **wallpapers e identidade visual Callas OS**
