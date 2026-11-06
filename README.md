# arch-install

Instalação 100% automática do Arch Linux com KDE Plasma (Wayland), já configurado em português do Brasil, teclado EUA Internacional e driver NVIDIA. Feito com Claude.

## Como usar

Dê boot na ISO do Arch Linux (modo UEFI, com internet por cabo) e rode:

```bash
bash <(curl -sL https://is.gd/archcallas157)
```

O script só pergunta o nome de usuário e a senha. O resto é automático.

## O que vem instalado

- KDE Plasma (Wayland) com tela de login SDDM
- Brave
- Discord
- Steam
- Shotcut (editor de vídeo)
- GPU Screen Recorder (gravador de tela estilo ShadowPlay)
- Driver NVIDIA (nvidia-open)
- yay (AUR) e Flatpak com Flathub

## Atenção

O script apaga todo o disco `/dev/nvme0n1` sem pedir confirmação. Use só se não houver nada importante nele.
