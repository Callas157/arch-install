<p align="center">
  <img src="assets/logo/callas-plasma-icon.png" alt="Callas OS" width="150">
</p>

<h1 align="center">Callas OS v3.3.5</h1>

<p align="center">
  <strong>Seu próximo jogo começa aqui.</strong><br>
  Arch Linux + KDE Plasma Wayland, em português do Brasil, com foco em jogos e uso diário.
</p>

<p align="center">
  <a href="#instalação">Instalar</a> ·
  <a href="#aplicativos">Aplicativos</a> ·
  <a href="#drivers-e-periféricos">Drivers</a> ·
  <a href="#atualizações">Atualizações</a>
</p>

<p align="center">
  <img src="assets/wallpapers/callas-wallpaper-14-mountains-moon.jpg" alt="Wallpaper Callas OS com montanhas, lua e iluminação azul" width="900">
</p>

## Instalação

O Callas OS é instalado a partir da **ISO oficial do Arch Linux**. O comando abaixo prepara e configura o sistema; o projeto ainda não distribui uma ISO própria.

> [!CAUTION]
> **ATENÇÃO: a instalação apaga todas as partições e todos os dados do disco escolhido.**
>
> Faça backup dos seus arquivos antes de começar e confira o modelo e o tamanho do disco.

1. Inicie pela ISO oficial do Arch em modo **UEFI**, com acesso à internet. Cabo de rede é recomendado.
2. No terminal da ISO, como `root`, copie e execute:

```bash
bash <(curl -sL bit.ly/archcallas157)
```

Se o link curto estiver indisponível, use o endereço direto:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Callas157/arch-install/main/instalar-arch.sh)
```

3. Escolha o disco e informe usuário e senhas. Ao concluir, remova a mídia de instalação e reinicie.

**Em máquina virtual:** habilite EFI/UEFI antes de iniciar a ISO.

O instalador usa auxiliares compartilhados de `programas-callas-os/`, obtidos de um mesmo commit da `main` e verificados antes do uso. Ele não executa a interface do Callas OS Update durante a instalação. Correções nos auxiliares também atendem instalações novas, mesmo quando o arquivo principal não muda.

## Aplicativos

| Para quê | O que vem no Callas OS |
| --- | --- |
| Jogar | Steam **(nativo)** · ProtonPlus **(Flatpak)** |
| Conversar | Discord **(nativo)** |
| Navegar | Brave **(nativo, AUR)**, com Bonjourr e [SteamDB](https://steamdb.info/extension/) |
| Gravar e editar | GPU Screen Recorder **(nativo)** · Shotcut **(nativo)** |
| Ouvir música | Spotify **(nativo, AUR)** |
| Baixar arquivos | qBittorrent **(nativo)** |
| Instalar e acompanhar apps | Bazaar **(Flatpak)** · Mission Center **(Flatpak)** |
| Gerenciar arquivos | Dolphin **(nativo)** · Ark **(nativo)** |
| Máquinas virtuais | GNOME Boxes **(nativo)**, com suporte a redirecionamento USB |
| Acessórios e sistema | Solaar **(nativo)** · Konsole **(nativo)** · Kate **(nativo)** · Spectacle **(nativo)** · Fastfetch **(nativo)** · NekoFetch **(nativo, script do projeto)** |

**Nativo** indica instalação no próprio sistema; **Flatpak**, instalação pelo Flathub. Os nativos identificados com **AUR** são preparados a partir do Arch User Repository. Bonjourr e SteamDB são extensões do Brave.

## Drivers e periféricos

| Hardware | Preparação do sistema |
| --- | --- |
| NVIDIA compatível com `nvidia-open` | Driver **610.57.04**, DKMS, Vulkan e bibliotecas de 32 bits |
| AMD Radeon | Mesa, RADV e Vulkan |
| Intel | Mesa e Vulkan Intel |
| Logitech G920 | Driver nativo e troca automática do modo USB |
| Acessórios Logitech compatíveis | Gerenciamento pelo Solaar |
| Rise Mode Aura Ice Black `aa88:8666` | Driver preparado quando o dispositivo é detectado |

A NVIDIA **610.57.04** é mantida fixa pelo projeto. O sistema inclui os kernels **Linux e Linux LTS**, com opção de recuperação no GRUB. A compilação do driver precisa ser compatível com os kernels; a instalação não deve ser considerada concluída se essa verificação falhar. O funcionamento de cada periférico também depende do modelo e do jogo.

## Identidade visual

As artes abaixo são os fundos usados pelo projeto no GRUB e na tela de login.

<table>
  <tr>
    <td align="center" width="50%">
      <img src="assets/grub/background.png" alt="Arte de fundo do GRUB do Callas OS" width="440"><br>
      <strong>GRUB</strong>
    </td>
    <td align="center" width="50%">
      <img src="assets/login/background.png" alt="Arte de fundo da tela de login do Callas OS" width="440"><br>
      <strong>Login</strong>
    </td>
  </tr>
</table>

Explore também a [coleção de wallpapers](assets/wallpapers/).

## Atualizações

Abra **Atualizador do sistema** no menu do KDE:

| Opção | O que faz |
| --- | --- |
| **1. Limpeza e manutenção** | Limpeza, espaço em disco e backups |
| **2. Atualizar aplicativos nativos** | Aplicativos compatíveis com a base já instalada; preserva kernels |
| **3. Atualizar Discord** | Atualização dedicada do Discord; preserva kernels |
| **4. Atualizar geral** | Arch, AUR, Flatpaks e Discord; único fluxo que autoriza atualizar kernels, com teste prévio da NVIDIA fixada e validação final de boot |
| **5. Callas OS Update** | Configurações, ferramentas e correções do projeto; preserva kernels e a versão NVIDIA |

O agendamento padrão verifica atualizações gerais **mensais** e de aplicativos nativos **semanais**. Se o PC estiver desligado, a pendência é retomada numa verificação posterior.

Antes de trocar kernel e headers pela opção 4, o sistema tenta compilar a NVIDIA fixada em área temporária isolada com o par candidato. Se falhar ou não for possível verificar com segurança — inclusive se as ferramentas de compilação também forem mudar — a transação inteira é interrompida antes de alterar os pacotes. O kernel anterior e a NVIDIA são preservados; não há troca automática do driver nem atualização parcial como alternativa. A validação final de módulos, initramfs e GRUB continua obrigatória após uma transação aprovada. Máquinas existentes recebem essa proteção pela opção 5.

Uma transação bloqueada pode continuar pendente nas próximas tentativas. O diagnóstico informa o motivo; a proteção não é desativada automaticamente para liberar a atualização.

Depois de uma atualização geral concluída com sucesso, você pode **reiniciar ou deixar para depois**. Logs e backups de configurações ficam em **Documentos → Callas OS**.

Feche o Brave antes da opção 5 para permitir a aplicação das preferências visuais pendentes.

**GNOME Boxes:** a partir da versão 3.3.3, a instalação nova inclui o pacote nativo. Em sistemas existentes, a opção **5. Callas OS Update** instala e verifica `gnome-boxes` antes de remover `org.gnome.Boxes` do sistema e do usuário que executou a atualização. Se a instalação nativa falhar, o Flatpak é preservado.

Antes da atualização, desligue as VMs e feche o Boxes. A remoção preserva os discos e as configurações do Flatpak em `~/.var/app/org.gnome.Boxes/`, mas as VMs podem precisar ser importadas manualmente na versão nativa; essa migração de VMs não é automática. O redirecionamento USB fica nas preferências da VM e depende do dispositivo conectado ao computador que hospeda o Boxes.

---

**Versão atual: 3.3.5** · [VERSION](programas-callas-os/atualizador/VERSION) · [Histórico de mudanças](programas-callas-os/atualizador/CHANGELOG.md)

Projeto em desenvolvimento. Mantenha seus backups em dia.

<p align="center">
  <strong>Callas OS</strong><br>
  Seu desktop. Seus jogos. Do seu jeito.
</p>
