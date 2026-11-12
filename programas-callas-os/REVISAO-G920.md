# Revisão do instalador, Callas OS Update e Logitech G920

Base: commit `1c57506`, revisão em 12/11/2026.

## Resultado

O Linux já contém o driver `hid_logitech_hidpp` do G920, incluindo force
feedback, nos kernels oficiais `linux` e `linux-lts`. O `xone` existente é
destinado ao receptor Xbox Wireless e não substitui a preparação do volante.

Faltava `usb_modeswitch`: o G920 pode iniciar como `046d:c261` (Xbox) e precisa
passar para HID, `046d:c262`. O pacote oficial do Arch já inclui perfil e regra
udev dessa troca. Ele passa a ser instalado pelo pacstrap e pelas dependências
da migração da opção 5, mesmo sem o volante conectado, preparando uso futuro.
Não foi criada uma regra concorrente de troca de modo.

A configuração compartilhada cria `70-callas-g920.rules`, restrita aos nós
de entrada de `046d:c262`, com `0660` e `uaccess` antes de `73-seat-late.rules`.
Isso permite leitura/escrita, inclusive force feedback, à sessão local ativa.
Não adiciona grupos, não libera todos os dispositivos e não altera a regra
hidraw existente do Solaar/headset. O pacote é protegido na revisão de órfãos.

As regras são recarregadas fora do chroot. Na instalação, ficam prontas para
o primeiro boot. Após o Update, reconecte um volante já conectado ou use-o
após o próximo boot: não se força reset USB durante um jogo.

## Instalador e Update

Foram preservados prompts, seleção de discos, particionamento, contas,
senha compartilhada de usuário/root, AUR, estrutura de boot, links, menus,
agendamento e programas embutidos. Nenhum driver foi substituído.

Observação: o código atual pede o número do disco mesmo com somente um
destino, se `DISCO` não foi informado. Foi mantido conforme o pedido de
não modificar o fluxo existente.

A migração mantém commit imutável, verificação de blobs, checkpoints por
conteúdo e propagação de falhas. A mudança da fase de segurança exige sua
reaplicação; a ausência da nova regra também invalida o checkpoint. A fase
ocorre antes da barreira de boot antigo, sem converter sua arquitetura.

Como já fazia, a migração executa uma transação completa `pacman -Syu` se
faltam dependências, preservando a pilha NVIDIA; não realiza atualização
parcial do Arch. Se todas existem, não inicia outra atualização geral.

Não foi feita auditoria exaustiva de segurança nem instalação Arch real.
Testes offline verificam o provisionamento e regressões, sem validar o
volante, os jogos ou o boot físico.

Resultado: 172 testes offline aprovados, sem testes ignorados, incluindo
execução da configuração completa em filesystem isolado com comandos de
pacotes/hardware simulados. Sintaxe de 9 scripts Bash e 29 arquivos Python
aprovada, além de `udevadm verify` para a regra e `git diff --check`.

## Aceitação no hardware

Depois da instalação ou da opção 5 com estas mudanças publicadas:

1. Conecte fonte, pedais e USB; reconecte o USB após o Update. Confira
   `lsusb`: estado final esperado `046d:c262`, não `046d:c261`.
2. Confira `journalctl -k -b` para reconhecimento por `logitech-hidpp-device`
   sem erros. `modinfo hid_logitech_hidpp` consulta o módulo instalado.
3. Na sessão KDE local, como usuário normal, teste direção, acelerador,
   freio, embreagem, botões, direcional, borboletas e força de retorno.
   Teste marchas se houver câmbio opcional conectado à base.
4. Teste um jogo nativo e os jogos usados via Proton. Se o jogo precisar
   acessar o volante diretamente, desative Steam Input nas propriedades
   desse jogo e configure eixos/botões nele. Os botões Xbox não garantem
   reconhecimento automático em todos os jogos.
5. Reconecte o volante e repita com o kernel padrão e o LTS.

Não são necessários G Hub ou um driver proprietário para o suporte nativo.
Oversteer é configurador opcional; `new-lg4ff` não é o driver HID++ do G920.
Não há promessa de compatibilidade universal de jogos ou de recursos de
outros modelos.

## Referências

- Driver: https://github.com/torvalds/linux/blob/master/drivers/hid/hid-logitech-hidpp.c
- Pacote oficial e arquivos: https://archlinux.org/packages/extra/x86_64/usb_modeswitch/files/
- Perfil upstream: https://github.com/NetworkManager/usb_modeswitch-data/blob/master/usb_modeswitch.d/046d:c261
- ArchWiki: https://wiki.archlinux.org/title/Logitech_Racing_Wheel
