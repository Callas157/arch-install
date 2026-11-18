# Discord: memória de janela e regressão do Update

O usuário relatou abertura no principal e com dimensões diferentes após reiniciar.
A janela preferida fica no secundário HDMI-A-1, na metade direita: posição 961,0,
tamanho 959×1080, normal. A captura real coincidiu com um backup anterior.

As entregas 3.16.0/3.16.1 não editaram diretamente sessão/janelas, mas o Update
reexecuta auxiliares compartilhados. O auxiliar antigo escrevia General/rules
sem reconhecer General/Order. Ao acrescentar variantes do navegador, gerava lista
completa apenas dos novos IDs: o KWin 6.8 migra essa lista e apaga grupos ausentes.
Os backups locais mostraram regras completas antigas, depois grupos ausentes e
recriados sem geometria no início da sessão.

Referência primária: `KDE/kwin`, tag v6.8.2, `src/rulebooksettings.cpp`, usrRead.
O teste nativo também mostrou restauração parcial e ausência de gravação durável
dos valores Remember no formato observado. Por isso a correção não depende apenas
dessas regras: o Discord recebe um observador próprio, sem interferir nas outras
janelas ou em seu arquivo settings.json.

Estado privado: XDG_STATE_HOME/callas-os/discord-window.json, esquema 1, modo 0600.
Registra somente conector, retângulos, flags, boot ID e ID da janela, sem títulos,
conversas, login ou tokens. Migra valores válidos de regras antigas quando ainda
não há registro. Serviço de usuário: callas-discord-memory.service. Sua prontidão
é confirmada pelo próprio KWin; perda do compositor encerra o observador para o
systemd retomar. Falha/corrupção não apaga o registro anterior.

## Reprodução isolada

Execute como usuário normal:

    python programas-callas-os/tests/probes/discord_native.py

O probe abre seu próprio D-Bus, KWin virtual e perfil temporário. A janela é Qt,
sem conta Discord ou conexão à rede. A classe é sintética para evitar o problema
de token de ativação de aplicativos registrados no compositor virtual sem efeitos.
Não altera a sessão principal. Confirmou janela normal 640×600 no Virtual-1 em
1400,40; reabertura no mesmo lugar; maximização; tela cheia; e retomada após
reiniciar compositor e observador. O roteiro fica versionado para repetir.

Na máquina principal foi aplicada apenas a reparação das regras pelo usuário;
a janela permaneceu aberta, no mesmo monitor, posição e tamanho. O serviço novo
chega pelo Callas OS Update. Não foi feito reboot real nem reiniciado o Discord.
