# Arch Install Callas Os

> [!CAUTION]
Ainda experimental e passando por mudanças constantes podendo passar por momentos de instabilidades teste por sua conta e risco

Instalador automático do **Arch Linux com KDE Plasma em Wayland**, em português do Brasil, com tema escuro e programas de jogos, gravação e uso diário. Funciona com processadores **AMD ou Intel** e seleciona a configuração gráfica conforme o hardware detectado.

## Como usar

> [!CAUTION]
> **O instalador apaga todas as partições e todos os dados do disco escolhido.** Faça backup antes e confira o tamanho e o modelo do disco na tela. A instalação usa o disco inteiro.

Inicie pela **ISO oficial do Arch Linux**, em modo **UEFI**, com internet. De preferência, use cabo de rede. No terminal da ISO, como `root`, rode o comando com o **link curto**.

```bash
bash <(curl -sL is.gd/archcallas157)
```

Se o link curto falhar, use o link direto do GitHub.

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Callas157/arch-install/main/instalar-arch.sh)
```

> [!NOTE]
> Em uma máquina virtual, habilite **EFI** nas configurações da VM e inicie pela ISO do Arch. Para placas NVIDIA detectadas, o instalador usa `nvidia-open`, que exige uma GPU compatível com esse driver.

## O que o script pergunta

1. **Em qual disco instalar.** Ele lista os discos com tamanho e modelo pra facilitar a identificação.
2. **Nome do usuário.** Use minúsculas e evite espaços.
3. **Senha.** Digite duas vezes pra confirmar. A mesma senha inicial será usada para o seu usuário e para a conta `root`. É normal o terminal ficar em branco enquanto você digita.

Quando aparecer **Instalação concluída**, remova o pendrive ou desmonte a ISO da VM e digite `reboot`.

## O que o instalador configura

### Boot e sistema

- Cria uma tabela **GPT** com uma partição EFI de **1 GiB** em FAT32, montada em `/boot`, e uma partição **ext4** para o sistema no restante do disco.
- Instala o kernel `linux`, o firmware, os cabeçalhos para DKMS e o microcódigo correspondente ao processador AMD ou Intel.
- Configura o **systemd-boot** com **3 segundos** de menu. Depois que o Arch começa a carregar, o **Plymouth** exibe o escudo do dragão azul do projeto. O menu também oferece uma entrada de diagnóstico com inicialização em texto.
- Define português do Brasil, fuso de São Paulo, teclado EUA Internacional, pastas do usuário em português e acesso ao `sudo` pelo grupo `wheel`.
- Habilita NetworkManager, Bluetooth, sincronização de horário, TRIM periódico e swap comprimida com **zram**. Inclui suporte a Wi-Fi conforme o adaptador detectado.

### KDE Plasma

- Aplica o **Brisa Escuro**, configura o **SDDM em Wayland** e ativa a integração da **Carteira KDE** com o login. Se a carteira precisar ser criada, o assistente pode aparecer no primeiro acesso.
- Configura o formulário de login na tela principal, com o wallpaper nas outras telas. A contagem de desligamento e reinício do KDE é ajustada para **5 segundos**.
- Inicia uma sessão vazia. **Steam** abre em modo silencioso, **Discord** minimizado e **Solaar** na bandeja. O perfil do **Digital Vibrance** é aplicado quando o utilitário está disponível. Brave e Spotify ficam fechados no login.
- Usa o escudo Callas no menu Super e fixa Dolphin e Brave no painel, conforme a disponibilidade.

### Gráficos, jogos e gravação

| Componente | Configuração |
| --- | --- |
| **NVIDIA** | Instala `nvidia-open` e os utilitários NVIDIA quando detecta uma GPU da marca. Carrega os módulos gráficos no initramfs e tenta instalar o Digital Vibrance. |
| **Mesa e máquinas virtuais** | Em sistemas sem NVIDIA detectada, usa Mesa. O driver Vulkan acompanha a GPU detectada, com renderização por software disponível para configurações sem driver Vulkan específico. |
| **Steam e ProtonPlus** | Instala a Steam nativa com suporte a bibliotecas de 32 bits via `multilib` e tenta instalar o ProtonPlus pelo Flathub. |
| **GPU Screen Recorder** | Tenta instalar o gravador e a interface GTK via Paru. O início automático do overlay depende de a rotina encontrar a interface separada `gsr-ui` (pacote `gpu-screen-recorder-ui`) ou a versão Flatpak. |
| **Shotcut** | Instalado pelos repositórios do Arch. |

### Periféricos e aplicativos

- **Solaar nativo**, com tema escuro e permissões para dispositivos Logitech compatíveis, como o G733. A variante Flatpak fica com os ajustes de tema e acesso preparados para quem instalar essa versão.
- **Receptor USB Xbox Wireless** com `xone-dkms` e `xone-dongle-firmware`. O script confere o módulo no kernel instalado e tenta recompilá-lo se necessário.
- **Discord nativo** com configuração automática do **BetterDiscord** quando o perfil estiver pronto. O atualizador reabre o Discord minimizado se precisar fechá-lo durante a atualização.
- **Spotify nativo** com **Spicetify** e **Marketplace**. A personalização é aplicada automaticamente depois que o Spotify cria o perfil e o app está fechado.
- **Brave**, **qBittorrent**, **Flatpak** com Flathub e tentativa de instalação do **Bazaar**. O **Ark** recebe suporte a RAR, ZIP e 7z, entre outros formatos.

### Paru, Fastfetch e Nekofetch

- **Paru** é preparado a partir do pacote `paru-bin` e usado tanto na instalação inicial quanto na etapa de atualização dos pacotes do AUR. A permissão temporária de instalação é removida ao terminar essa etapa.
- **Fastfetch** vem dos repositórios do Arch. O **Nekofetch** é instalado com `uv` e aparece ao abrir um terminal Bash interativo. O layout inclui kernel, ambiente gráfico, resolução, taxa de atualização, GPU, driver e **VRAM dedicada usada e total** quando o driver fornece esses dados.

## Atualizador do sistema

Procure por **Atualizador do sistema** no menu do KDE. Ele já entra nos favoritos iniciais, e você pode remover o favorito e continuar encontrando o atualizador pela busca.

| Atualização automática | Frequência | O que atualiza |
| --- | --- | --- |
| **Aplicativos** | Semanal, às **13h** | Flatpaks, Discord nativo e BetterDiscord. |
| **Sistema** | Mensal, às **14h** | Pacotes oficiais do Arch e pacotes do AUR via Paru. |

Se o PC perder o horário, a execução fica para a próxima tarde em que estiver ligado no horário previsto. Pelo menu, também dá pra atualizar manualmente o sistema, os aplicativos ou só Discord e BetterDiscord. Os registros são acrescentados ao arquivo `Documentos/Logs de Atualizações/atualizacoes.log`.

## Se algo ficar pendente

Erros em etapas essenciais, como particionamento, instalação da base ou configuração do boot, interrompem a instalação. Se uma etapa opcional falhar, confira os avisos do terminal e o arquivo `/var/log/callas-instalacao-avisos.log`, quando ele estiver presente no sistema instalado.
