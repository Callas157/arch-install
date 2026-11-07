# arch-install

Instalação 100% automática do Arch Linux com KDE Plasma (Wayland), já configurado em português do Brasil, teclado EUA Internacional e driver NVIDIA. Feito com Claude.

## Como usar

Dê boot na ISO do Arch Linux (modo UEFI, com internet) e rode:

```bash
bash <(curl -sL is.gd/archcallas157)
```

Plano B, com o endereço completo:

```bash
bash <(curl -sL https://raw.githubusercontent.com/Callas157/arch-install/main/instalar-arch.sh)
```

## O que o script pergunta

Só três coisas, o resto é automático:

1. Em qual disco instalar o sistema (ele lista os discos com tamanho e modelo)
2. Nome de usuário
3. Senha (vale para o usuário e para o root)

## O que vem instalado

- KDE Plasma (Wayland) com tela de login SDDM no tema Breeze
- Brave (navegador)
- Discord
- Steam
- Shotcut (editor de vídeo)
- GPU Screen Recorder (gravador de tela estilo ShadowPlay)
- Driver NVIDIA (nvidia-open)
- yay (AUR) e Flatpak com Flathub
- Áudio PipeWire, Bluetooth e NetworkManager

## Detecção automática

O script foi feito para rodar em qualquer PC. Ele detecta sozinho:

- **Processador:** instala o microcódigo certo (`amd-ucode` ou `intel-ucode`)
- **Rede cabeada:** funciona direto pelo NetworkManager
- **Wi-Fi:** se houver adaptador, instala `wpa_supplicant`, `iw` e `wireless-regdb`
- **Wi-Fi Broadcom:** nos modelos que precisam do driver proprietário, instala o `broadcom-wl-dkms`
- **Disco:** escolha pelo número, sem precisar saber o nome do dispositivo (`sda`, `nvme0n1`...)

A maioria dos adaptadores (Intel, Realtek, Qualcomm, MediaTek) já funciona com o kernel e o `linux-firmware`. Alguns adaptadores Wi-Fi USB da Realtek podem precisar de driver extra do AUR, instalado depois com o `yay`.

## Carteira KDE (KWallet)

O script instala e configura o `kwallet-pam`, para a carteira destravar sozinha com a senha do login. No **primeiro login**, o assistente da carteira abre sozinho:

1. Escolha **Configuração básica**
2. Digite **a mesma senha do login**

Isso é feito uma única vez. Depois disso, o KDE e o Brave não pedem mais senha da carteira.

## Configurações aplicadas

- Idioma pt-BR, fuso `America/Sao_Paulo`
- Teclado EUA Internacional (console e KDE)
- Boot UEFI com systemd-boot, partição EFI de 1 GB e o resto em ext4
- Swap em zram
- NVIDIA carregando cedo no boot, necessário para o Wayland

## Atualizações

- Escolha do disco por menu numerado
- Detecção automática de processador (AMD/Intel)
- Detecção automática de rede (cabo, Wi-Fi e Broadcom)
- Carteira KDE configurada com a senha do login
- Tela de login com o tema Breeze do KDE
- Brave no lugar do Firefox
- Adicionados Shotcut e GPU Screen Recorder
- Removida a confirmação antes de apagar o disco

## Atenção

- O script **apaga todo o disco escolhido, sem pedir confirmação**. Confira o número do disco antes de apertar Enter.
- O driver `nvidia-open` serve para placas NVIDIA RTX 20 em diante. GTX 10 e mais antigas não são suportadas por este script.
- Não é testado em todos os modelos de hardware. Teste primeiro numa máquina virtual (EFI ativado e disco NVMe).
