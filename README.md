<p align="center">
  <img src="assets/logo/callas-plasma-icon.png" alt="Callas OS" width="150">
</p>

<h1 align="center">Callas OS v3.3.2</h1>

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

## Pronto para sua biblioteca

O **Callas OS** reúne uma base Arch com ambiente KDE, Steam, ferramentas para gerenciar Proton, gravação de gameplay e aplicativos para o dia a dia. Tema escuro, wallpapers e integração com o desktop já fazem parte da instalação.

- **Jogos:** Steam e ProtonPlus para gerenciar versões do Proton.
- **Gravação:** GPU Screen Recorder para capturar suas partidas.
- **Desktop:** KDE Plasma Wayland com a identidade visual do Callas OS.
- **Manutenção:** atualizador integrado, limpeza e backups de configurações.

A compatibilidade de cada jogo depende do Proton, dos drivers e do anticheat utilizado pelo título.

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

## Aplicativos

| Para quê | O que vem no Callas OS |
| --- | --- |
| Jogar | Steam · ProtonPlus |
| Conversar | Discord |
| Navegar | Brave, com Bonjourr e [SteamDB](https://steamdb.info/extension/) |
| Gravar e editar | GPU Screen Recorder · Shotcut |
| Ouvir música | Spotify |
| Baixar arquivos | qBittorrent |
| Instalar e acompanhar apps | Bazaar · Mission Center |
| Gerenciar arquivos | Dolphin · Ark |
| Acessórios e sistema | Solaar · Konsole · Kate · Spectacle · Fastfetch · NekoFetch |

## Drivers e periféricos

| Hardware | Preparação do sistema |
| --- | --- |
| NVIDIA compatível com `nvidia-open` | Driver **610.57.04**, DKMS, Vulkan e bibliotecas de 32 bits |
| AMD Radeon | Mesa, RADV e Vulkan |
| Intel | Mesa e Vulkan Intel |
| Logitech G920 | Driver nativo e troca automática do modo USB |
| Acessórios Logitech compatíveis | Gerenciamento pelo Solaar |
| Rise Mode Aura Ice Black `aa88:8666` | Driver preparado quando o dispositivo é detectado |

A versão NVIDIA é mantida fixa pelo projeto. O sistema inclui os kernels **Linux e Linux LTS**, com opção de recuperação no GRUB. O funcionamento de cada periférico também depende do modelo e do jogo.

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
| **2. Atualizar aplicativos nativos** | Aplicativos compatíveis com a base já instalada |
| **3. Atualizar Discord** | Atualização dedicada do Discord |
| **4. Atualizar geral** | Arch, AUR, Flatpaks, Discord e verificação dos kernels e boot |
| **5. Callas OS Update** | Configurações, ferramentas e correções do projeto |

O agendamento padrão verifica atualizações gerais **mensais** e de aplicativos nativos **semanais**. Se o PC estiver desligado, a pendência é retomada numa verificação posterior.

Depois de uma atualização geral concluída com sucesso, você pode **reiniciar ou deixar para depois**. Logs e backups de configurações ficam em **Documentos → Callas OS**.

Feche o Brave antes da opção 5 para permitir a aplicação das preferências visuais pendentes.

---

**Versão atual: 3.3.2** · [VERSION](programas-callas-os/atualizador/VERSION) · [Histórico de mudanças](programas-callas-os/atualizador/CHANGELOG.md)

Projeto em desenvolvimento. Mantenha seus backups em dia.

<p align="center">
  <strong>Callas OS</strong><br>
  Seu desktop. Seus jogos. Do seu jeito.
</p>
