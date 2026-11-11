<p align="center">
  <img src="assets/logo/callas-plasma-icon.png" alt="Callas OS" width="150">
</p>

<h1 align="center">Callas OS v3.2.1</h1>

<p align="center">
  Instalador automatizado de <strong>Arch Linux + KDE Plasma Wayland</strong>, em português do Brasil, preparado para jogos, uso diário, gravação, periféricos e manutenção simplificada.
</p>

---

## O que é o Callas OS

O **Callas OS** é um projeto de instalação e configuração automatizada baseado no **Arch Linux**. Ele parte da ISO oficial do Arch, prepara o disco escolhido, instala o sistema, configura o KDE Plasma em Wayland, instala os aplicativos definidos pelo projeto e aplica a identidade visual e os ajustes do Callas OS.

Ele não é uma ISO independente: a instalação começa pela **ISO oficial do Arch Linux** e o script deste repositório monta o sistema automaticamente.

O projeto está em desenvolvimento contínuo. Configurações, aplicativos, drivers, boot, aparência e rotinas de manutenção podem mudar conforme o Callas OS evolui.

> [!IMPORTANT]
> A opção **5. Callas OS Update** também migra a segurança e o atualizador de instalações existentes. Ela instala dependências e preserva a NVIDIA instalada, suas senhas e a arquitetura de boot.
>
> Se uma instalação usar GRUB antigo, as correções de segurança são aplicadas, mas as novas personalizações visuais de boot ficam bloqueadas. Mudanças estruturais de boot ainda podem exigir instalação limpa.

---

## Instalação

> [!CAUTION]
> **O instalador apaga todas as partições e todos os dados do disco escolhido.**
>
> Faça backup antes de começar e confira com atenção o modelo e o tamanho do disco selecionado.

Inicie o computador pela **ISO oficial do Arch Linux**, em modo **UEFI**, com conexão à internet. De preferência, utilize cabo de rede durante a instalação.

No terminal da ISO, como `root`, execute:

```bash
bash <(curl -sL bit.ly/archcallas157)
```

Se o link curto estiver indisponível, use o endereço direto do GitHub:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Callas157/arch-install/main/instalar-arch.sh)
```

Em máquinas virtuais, habilite **EFI/UEFI** antes de iniciar a ISO.

O instalador solicitará o disco de destino, usuário e senhas necessárias. Quando a instalação terminar, remova a mídia de instalação e reinicie o computador.

---

## Visual do sistema

### GRUB

<p align="center">
  <img src="assets/grub/background.png" alt="GRUB do Callas OS" width="850">
</p>

O Callas OS utiliza um GRUB personalizado em instalações novas, com entradas próprias do projeto:

- **Callas OS Linux**
- **Callas OS (kernel LTS - recuperação)**
- **Callas OS (diagnóstico sem splash)**

O menu usa contagem regressiva de **3 segundos** e mantém uma entrada de recuperação com kernel LTS para situações em que o kernel principal ou algum módulo DKMS apresente problema.

### Tela de login

<p align="center">
  <img src="assets/login/background.png" alt="Tela de login do Callas OS" width="850">
</p>

O KDE Plasma utiliza SDDM em Wayland. Em configurações com múltiplos monitores, o login é concentrado no monitor principal enquanto o monitor secundário permanece ativo exibindo o fundo.

### Desktop

<p align="center">
  <img src="assets/wallpapers/callas-wallpaper-14-mountains-moon.jpg" alt="Wallpaper do Callas OS" width="850">
</p>

O sistema inclui a coleção de wallpapers do projeto e aplica o visual preparado pelo Callas OS no primeiro login.

### Plymouth

<p align="center">
  <img src="assets/plymouth/callas/background.jpg" alt="Tela de carregamento do Callas OS" width="850">
</p>

O Plymouth é integrado ao initramfs para manter uma transição visual durante a inicialização normal.

---

## Base do sistema

A instalação prepara, entre outros componentes:

- **Arch Linux** em sistema de arquivos `ext4`;
- tabela de partição **GPT**;
- partição EFI em FAT32;
- kernel principal `linux`;
- kernel de recuperação `linux-lts`;
- KDE Plasma em **Wayland**;
- **NetworkManager**;
- Bluetooth;
- zram;
- TRIM periódico;
- sincronização automática de horário;
- idioma **Português do Brasil**;
- fuso horário **America/Sao_Paulo**;
- teclado **EUA Internacional**;
- pastas pessoais em português;
- sudo para o grupo `wheel`.

O instalador detecta automaticamente processadores AMD e Intel e instala o microcódigo correspondente.

---

## Placas de vídeo

| Hardware | Configuração |
| --- | --- |
| **NVIDIA** | `nvidia-open-dkms` **610.57.04**, utilitários NVIDIA 610, Vulkan e bibliotecas de 32 bits |
| **AMD Radeon** | Mesa, RADV e Vulkan Radeon |
| **Intel** | Mesa, ANV e Vulkan Intel |
| **VM / GPU genérica** | Mesa e renderização Vulkan compatível quando necessário |

Em máquinas NVIDIA, a versão **610.57.04** é mantida pelo projeto e não é substituída automaticamente pela atualização mensal do sistema. A troca de versão só deve acontecer quando o Callas OS definir uma nova pilha validada.

Após atualizações do sistema, a rotina de manutenção verifica os módulos NVIDIA/DKMS para os kernels instalados antes de considerar a atualização segura para reinicialização.

---

## KDE Plasma

Entre os padrões aplicados pelo Callas OS estão:

- tema **Brisa Escuro**;
- painel configurado pelo projeto;
- transparência e blur do Plasma;
- sessão vazia ao entrar no sistema;
- Steam iniciando silenciosamente a partir do segundo login;
- Discord iniciando visível, sem forçar minimização, a partir do segundo login;
- Solaar disponível na bandeja;
- Digital Vibrance quando compatível;
- atalho **Super + Shift + S** para captura retangular;
- integração da Carteira KDE com o login;
- suspensão automática, escurecimento e desligamento da tela por inatividade desativados por padrão;
- redução do tempo de desligamento e reinicialização.

Esses ajustes continuam disponíveis para alteração manual pelo usuário nas configurações do KDE.

### Callas OS — Monitores

O instalador inclui **Callas OS — Monitores** no menu **Sistema**. Em uma instalação existente compatível, abra **Atualizador do sistema → 5. Callas OS Update** para receber a ferramenta. Os dois utilitários ficam em Sistema; os favoritos são adicionados uma vez na sessão KDE, inclusive em perfis existentes, e podem ser removidos manualmente depois.

Após o primeiro login, abra a ferramenta e escolha **1. Escolher monitor principal**. Ela lista as saídas ativas, como `DP-3` e `HDMI-A-1`, e pede sua escolha; não presume que HDMI, DisplayPort ou a primeira saída detectada seja a desejada. O primeiro login anterior à escolha ainda pode aparecer em outra tela.

A escolha altera a prioridade pelo KScreen, move o painel padrão com menu/barra de tarefas para o principal e mantém os dois monitores ativos. Resolução, frequência, escala e posições físicas das telas são preservadas. O SDDM recebe a seleção para o próximo login: formulário no escolhido e wallpaper no outro. Não é necessário reiniciar o gerenciador de login durante a configuração.

A Área de Trabalho principal exibe a pasta padrão de atalhos. Nas outras telas, a exibição padrão dessa mesma pasta passa a usar uma pasta vazia dedicada. Isso faz os novos atalhos criados por Steam ou outros launchers **na pasta Área de Trabalho** aparecerem no principal. Arquivos não são apagados; pastas personalizadas de outros desktops e widgets são preservados. A ferramenta não obriga um launcher a criar atalhos se essa opção estiver desativada nele.

### Memória de janelas — patch automático

A memória de janelas é um ajuste independente do configurador de monitores. A opção **5. Callas OS Update** instala `programas-callas-os/janelas/callas-janelas.py` e ativa as regras nativas **Lembrar** do KWin automaticamente na sessão Plasma do usuário. Não é necessário abrir o configurador, escolher uma tela ou ativar uma opção manual de aprendizado. A ativação usa o serviço de usuário `callas-janelas.service`; o script de monitores não instala nem inicializa regras de aprendizado.

Em instalações novas, esse ajuste também é instalado e ativado silenciosamente no login KDE. A rotina pode executar novamente para completar atributos ainda não aprendidos, mas preserva os valores já salvos. Se não houver sessão gráfica ativa durante a atualização, a ativação ocorre no próximo login. A ferramenta de monitores continua sendo aberta manualmente; não foi adicionada uma janela automática no primeiro login.

As regras cobrem Discord, Spotify e Brave. Janelas abertas na primeira ativação têm posição, tamanho, tela e maximização capturados; aplicativos fechados começam a aprender posição/tamanho no uso normal. Atributos adicionais ausentes são completados nas ativações seguintes quando o aplicativo estiver aberto, preservando as coordenadas aprendidas. Depois de mover/redimensionar, feche o aplicativo normalmente para o KWin persistir o estado. Não há regra global de centralizar ou enviar programas ao principal. Outros aplicativos ou várias janelas equivalentes do mesmo navegador podem exigir correspondências específicas em **Configurações do Sistema → Gerenciamento de janelas → Regras de janelas**.

As posições aprendidas ficam no arquivo do KDE `~/.config/kwinrulesrc`; backups das alterações desse patch ficam em `~/.config/callas-os/window-backups/`. O configurador apenas conserva a associação das regras existentes à mesma tela física se a escolha do principal mudar a ordem das saídas.

A sessão KDE permanece vazia ao entrar: após o primeiro login de uma instalação limpa, Discord e os aplicativos de autostart continuam iniciando; Brave e Spotify não são reabertos por restauração da sessão. Outras entradas de autostart escolhidas pelo usuário são preservadas. O utilitário não restaura processos fechados para recuperar geometria.

Backups locais das configurações alteradas ficam em `~/.config/callas-os/monitor-backups/`. Se uma etapa falhar, o terminal informa a falha; etapas já confirmadas podem ter sido aplicadas. A seleção do login requer sudo. O utilitário é destinado a **Plasma Wayland**, com SDDM/KWin conforme o instalador atual.

### Validação de monitores

Verificações automatizadas: `python -m unittest discover -s programas-callas-os/tests -v`. Elas cobrem seleção, cancelamento, desconexão durante a escolha, prioridades sem alteração de modos, preservação de regras, favoritos e scripts do Plasma. Também é necessário validar em uma sessão gráfica real; os testes automatizados não simulam a GPU, os painéis físicos ou o greeter.

Roteiro de aceitação em instalação limpa ou atualizada:

1. Execute a opção 5 do atualizador e confira ambos os utilitários em Sistema/favoritos. Desfixe um favorito e confirme que ele não volta em cada login.
2. Confira que a opção 5 ativou a memória automaticamente, antes de abrir o configurador. Organize Discord e Brave lado a lado no HDMI. Escolha o DisplayPort como principal na ferramenta, sem mudar a posição física das telas.
3. Confira painel, notificações e um novo atalho de jogo no DisplayPort, com wallpaper no HDMI. Confirme que os programas abertos continuam onde estavam.
4. Mova/redimensione e feche os aplicativos normalmente uma vez; reabra e confira a geometria. Reinicie: Discord deve iniciar visível no lugar aprendido; Brave e Spotify devem continuar fechados até serem abertos manualmente.
5. Confira o formulário do SDDM no DisplayPort e wallpaper no HDMI. Teste uma janela maximizada e uma configuração com somente uma tela conectada; reconecte e confira a preferência do KScreen.

**Limite de validação:** mudanças de escala/disposição física, desconexões e múltiplas janelas indistinguíveis podem exigir ajustes nas Regras de janelas. Não se promete ausência de bugs sem os testes no hardware real.

---

## Primeiro login após instalação limpa

Steam e Discord não são abertos automaticamente no primeiro login. O instalador prepara um marcador independente para cada aplicativo, consumido pelo seu autostart sem abrir o programa. Os atalhos normais continuam disponíveis: o usuário pode abrir os aplicativos manualmente desde o primeiro login. Nos logins seguintes, Steam volta a iniciar com `-silent` e Discord com o comportamento habitual. Solaar e os outros autostarts mantêm suas configurações.

A opção 5 e o reparo de sessão não criam nem reiniciam esses marcadores em PCs existentes. Eles não encerram Steam/Discord nem removem contas ou dados desses aplicativos. O perfil existente do Brave não é reescrito pela migração; as políticas de extensões permanecem separadas do perfil. O instalador e o atualizador não abrem Brave para instalar Bonjourr ou SteamDB. O navegador processa as políticas quando o usuário o abre; abas de boas-vindas dependem de cada extensão, sem garantia de quantidade ou ordem.

O configurador de monitores continua nos favoritos; nenhuma janela de seleção de monitores foi adicionada ao primeiro login.

## Aplicativos

O Callas OS instala ou prepara os principais aplicativos abaixo:

| Categoria | Aplicativos |
| --- | --- |
| Navegação | **Brave** |
| Comunicação | **Discord** |
| Jogos | **Steam**, **ProtonPlus** |
| Gravação | **GPU Screen Recorder** |
| Vídeo | **Shotcut** |
| Downloads | **qBittorrent** |
| Música | **Spotify** |
| Periféricos | **Solaar** |
| Sistema | **Mission Center**, **Fastfetch**, **Nekofetch** |
| Loja de aplicativos | **Bazaar** |
| Arquivos | **Dolphin**, **Ark** |

O Brave é preparado pelo projeto com as extensões **Bonjourr** e **[SteamDB](https://steamdb.info/extension/)** e com as preferências do navegador em **Português do Brasil**. O idioma do Bonjourr pode precisar de ajuste na própria extensão.

O SteamDB também é disponibilizado em instalações existentes pela opção **5 — Callas OS Update**, usando a política de extensões do Brave. Se já estiver instalado, a mesma extensão é aproveitada, sem duplicação nem redefinição de suas configurações. A instalação é processada pelo Brave ao carregar a política; se necessário, feche e abra o navegador.

---

## Versão do projeto

A versão pública atual é **Callas OS v3.2.1**. O arquivo [`VERSION`](programas-callas-os/atualizador/VERSION) é a fonte do número publicado; o [histórico](programas-callas-os/atualizador/CHANGELOG.md) descreve os marcos anteriores e a regra para as próximas versões.

Instalador e opção **5 — Callas OS Update** registram a versão instalada em `/etc/callas-os/release.json`. Esse arquivo contém apenas identificação e estado, é legível pelo usuário e só pode ser alterado pelo administrador. A versão avança ao concluir as etapas obrigatórias; uma falha preserva a última versão concluída e registra a tentativa incompleta. Um boot antigo incompatível não recebe uma identificação falsa de migração completa. Instalações anteriores sem registro ficam como versão não identificada até uma migração completa ou instalação nova.

A linha OS do NekoFetch lê esse registro e mostra **`Callas OS v3.2.1 (Arch Linux)`**, com o estilo e a arte atuais. O número novo aparece na próxima execução, sem editar o layout a cada versão. Isso não altera `/etc/os-release` nem faz o NekoFetch aparecer dentro dos programas de manutenção. A atualização migra o layout existente; uma instalação nova prepara o layout pelo utilitário habitual.

Novos logs gravados pelo utilitário incluem contexto de versão/estado. Novos arquivos de backup guardam `callas-release.json`, identificando a versão registrada e, durante uma migração, o destino pretendido. Logs e backups antigos não recebem retroativamente uma versão histórica presumida. Atualizações comuns de pacotes, kernels ou aplicativos não mudam a versão do projeto. A revisão interna por data continua existindo para compatibilidade com clientes antigos.

## Atualizações do sistema

O Callas OS possui um **Atualizador do sistema** integrado ao KDE.

Existem duas rotinas automáticas principais; a geral já inclui a etapa de aplicativos e avança as duas agendas, evitando uma segunda execução seguida:

| Rotina | Frequência | O que atualiza |
| --- | --- | --- |
| Aplicativos nativos | A cada **7 dias** | Pacotes oficiais em transação compatível, AUR sem novas dependências de base e rotina própria do Discord; sem Flatpaks e sem atualizar kernel/boot |
| Atualização geral | A cada **1 mês**, ou pela opção **4** | Arch, AUR, recompilações sinalizadas, Flatpaks, Discord e validação final dos kernels/boot; NVIDIA preservada |

Não existe um horário ou dia fixo. Os vencimentos são calculados a partir da instalação e da última execução concluída com sucesso.

Se o computador estiver desligado quando uma atualização vencer, ela permanece pendente e será executada numa verificação posterior.

Os registros de cada execução ficam em **Documentos/Callas OS/Callas OS Logs**, usando a pasta Documentos configurada no KDE (inclusive quando ela se chama Documents):

| Subpasta | Conteúdo |
| --- | --- |
| `Callas OS Update` | Migração de configurações e falhas de download do atualizador novo |
| `Sistema e Pacman` | Atualizações completas e extrato do histórico do pacman |
| `Kernel Linux` | Kernels padrão/LTS, headers, initramfs, DKMS e GRUB |
| `Driver NVIDIA` | Versões e verificação dos módulos; a migração não troca o driver |
| `Aplicativos` | Rotina de aplicativos nativos, Discord e Flatpaks da atualização geral |
| `AUR` | Plano de dependências do Paru, compilação isolada, instalação e recompilações |
| `Seguranca e Firewall` | Aplicação das proteções e resultado do firewall |
| `Instalacao` | Saída da instalação nova e avisos disponíveis |
| `Manutencao` | Limpeza, espaço ocupado, backups e inventário de VMs |

Os arquivos têm data/hora. A migração reúne as antigas pastas de logs de Documentos em `Callas OS/Callas OS Logs`, preservando os arquivos. Havendo duas origens, guarda a segunda em uma subpasta de legado sem sobrescrever registros. A antiga `Callas OS Backup` também é migrada para `Callas OS/Callas OS Backups`; conflitos e arquivos não gerenciados são preservados na origem e informados. A exportação dos diagnósticos administrativos é idempotente: o mesmo registro não gera outra cópia em cada execução.

Cada arquivo novo é limitado a 2 MiB; cada árvore de logs, em Documentos e em `/var/log/callas-os`, mantém até 128 MiB no total, 60 arquivos por pasta e 30 dias de histórico. Logs do journal e o histórico original do pacman continuam nos seus locais padrão; não são apagados indiscriminadamente. Os logs de limpeza e os relatórios ficam em `Manutencao`.

As cópias administrativas de recuperação ficam em **Documentos/Callas OS/Callas OS Backups**, separadas em `Sistema`, `Callas OS Update` e `Seguranca`. O padrão é **1 GB combinado (1.000.000.000 bytes)** de arquivos concluídos, com até três cópias por categoria. A rotação remove primeiro as cópias mais antigas. O limite e a quantidade podem ser ajustados com autorização administrativa em `/etc/callas-os/maintenance.ini`; a opção **1 → 2** mostra o caminho, limite e ocupação.

Os três pools antigos (`/var/lib/put-update/recuperacao`, `/var/lib/callas-os/config-backups` e `/var/lib/callas-os/security-backups`) são importados antes de remover suas cópias antigas. Uma cópia incompleta ou que não pôde ser importada é preservada na origem com aviso. Uma única cópia nova maior que o limite não é mantida; isso fica registrado. Temporários de criação podem ocupar espaço adicional durante a operação; temporários incompletos antigos são limpos posteriormente.

**Privacidade dos backups:** os arquivos podem incluir `/etc` e informações administrativas. As pastas permitem ver nomes e tamanhos, mas os arquivos `.tar.gz` pertencem a root e têm permissão `0600`. Abrir/restaurar exige autorização administrativa. Escritas e rotação usam descritores de diretório e recusam caminhos simbólicos ou pastas com proprietário/permissões inesperados. Não são snapshots completos, não copiam jogos nem discos de VMs e não fazem restauração automática. Os estados locais necessários ao desfazer dos utilitários de monitores/janelas continuam nos locais documentados acima.

---

## Organização do repositório

| Caminho | Conteúdo |
| --- | --- |
| `programas-callas-os/atualizador/VERSION` | Número público do projeto |
| `programas-callas-os/atualizador/CHANGELOG.md` | Histórico e marcos retrospectivos |
| `instalar-arch.sh` | Instalador principal, no mesmo endereço de sempre |
| `assets/` | Recursos visuais e arquivos de temas existentes |
| `programas-callas-os/monitores/` | Configurador de monitores e auxiliar do login |
| `programas-callas-os/janelas/` | Memória automática das janelas |
| `programas-callas-os/sessao/` | Configuração de inicialização do KDE |
| `programas-callas-os/atualizador/` | Código completo do Callas OS Update |
| `programas-callas-os/tests/` | Testes dos programas |
| `callas-config-update.sh` na raiz | Ponte de compatibilidade para atualizadores antigos |

A raiz mantém somente `assets/`, `programas-callas-os/`, `instalar-arch.sh`, este README e a ponte histórica `callas-config-update.sh`. Código, testes, histórico e metadados novos ficam dentro de `programas-callas-os/`; artes ficam em `assets/`.

A ponte da raiz baixa e confere a sintaxe do atualizador no caminho novo. Ao atualizar, o programa instalado passa a consultar diretamente esse caminho. A ponte permanece para instalações que ainda não receberam a migração; removê-la quebraria o endereço usado por essas máquinas. Não há mudança nos links do instalador nem nos caminhos dos recursos visuais.

Lançadores já instalados especificamente pelas versões 3.2.0/3.2.1 buscavam `VERSION` na raiz. Com a reorganização, esses lançadores antigos podem parar com erro `VERSION` antes da migração: nesse caso, é necessário iniciar a atualização pela ponte histórica acima para receber o lançador atual. Instalações anteriores a esse esquema de versão continuam pelo bootstrap/ponte existente. Não é necessário reinstalar o sistema por essa mudança.

## Callas OS Update

Além das atualizações normais do Arch Linux e dos aplicativos, existe a opção de atualizar as **configurações do Callas OS**.

O arquivo responsável por isso é:

`programas-callas-os/atualizador/callas-config-update.sh`

Essa rotina pode distribuir mudanças consideradas seguras para sistemas já instalados, por exemplo:

- ajustes do KDE;
- atalhos;
- autostart;
- wallpapers;
- configurações do Brave;
- Flatpaks;
- scripts auxiliares;
- integrações e pequenos refinamentos do Callas OS.

O atualizador mantém controle da versão aplicada e cria backups das configurações afetadas antes das migrações.

### Compatibilidade

A migração instala primeiro as proteções de segurança e o novo atualizador. Em seguida, verifica a compatibilidade das personalizações do GRUB. Instalações com a arquitetura antiga recebem as correções de segurança e mantêm a arquitetura de boot anterior; somente as novas personalizações visuais ficam bloqueadas.

A instalação nova continua usando `grub-custom-v2`. Uma migração de segurança não promete converter todas as arquiteturas antigas nem substituir reinstalações necessárias para mudanças profundas no boot.

### Segurança implementada

- Remoção das regras antigas de `pacman` sem senha. O automático oficial roda como serviço administrativo; isso é diferente de conceder ao usuário/compilador permissão irrestrita de sudo sem senha.
- A atualização completa inclui AUR automaticamente, conforme a preferência do projeto. Paru consulta as versões e resolve a ordem de dependências; makepkg compila em uma unidade systemd com conta dedicada, sem sudo, sem novos privilégios, sem acesso às pastas pessoais e com escrita restrita à área de trabalho. O serviço administrativo instala os arquivos prontos após conferir os nomes esperados e rejeitar links simbólicos. A instalação inicial pela ISO continua tendo sua própria revisão interativa dos pacotes AUR.
- UFW com entrada bloqueada por padrão, saída permitida, IPv4/IPv6 e integração ao KDE. Regras existentes são preservadas. Outro firewall ativo é preservado para evitar regras concorrentes. Serviços que precisem receber conexões, como compartilhamentos, transmissão e portas de torrent, podem precisar de uma regra específica.
- Pacotes dos repositórios exigem assinatura confiável; arquivos locais do AUR continuam sujeitos à política própria de pacotes locais. NVIDIA baixada do Archive na instalação nova tem sua assinatura explicitamente verificada.
- Downloads de código de uma atualização usam um único commit imutável. Os IDs dos blobs são conferidos antes da execução, e o estágio é privado e pertence a root. A opção 5 nova executa somente o lançador instalado de propriedade de root, sem executar com sudo um arquivo temporário gravável pelo usuário.
- Proteções conservadoras de links/arquivos temporários e ocultação de endereços/mensagens do kernel para usuários comuns; sudo usa terminal dedicado e cache de autenticação de cinco minutos.
- Caso SSH esteja instalado, o acesso direto como root é desabilitado. Nenhum servidor SSH é habilitado pela migração.
- Driver opcional do Rise Mode passa a usar conta dedicada, permissões de dispositivo restritas e isolamento do serviço, se esse hardware estiver configurado.
- Senhas existentes e versão NVIDIA preservadas. A senha de usuário/root continua compartilhada conforme a preferência do projeto. Senhas curtas continuam fracas; essas proteções não aumentam sua entropia.

**Limite de confiança:** GitHub e as contas com permissão de escrita continuam sendo a autoridade da atualização. Commit imutável e verificação de blob não são assinatura independente e não protegem contra uma publicação maliciosa feita por uma conta autorizada comprometida. Uma assinatura independente precisa de uma chave administrada separadamente do repositório. Assinatura independente, proteção da conta/repositório e criptografia de um disco já instalado exigem configuração adicional; não estão sendo anunciadas como concluídas.

A primeira migração de um cliente antigo ainda passa pelo mecanismo de download antigo. Depois dela, as execuções seguintes usam o lançador novo. O link curto e o nome do instalador permanecem os mesmos.

### Atualização completa sem perguntas intermediárias

A opção **4. Atualizar geral** e a rotina mensal executam, em ordem:

1. Backup de recuperação e atualização completa do Arch, incluindo os aplicativos oficiais.
2. Consulta do AUR pelo Paru, resolução de dependências e atualização dos pacotes externos. `rebuild-detector` sinaliza recompilações; pacotes de desenvolvimento com sufixo `-git`, `-svn`, `-hg`, `-bzr`, `-darcs` ou `-cvs` são recompilados nessa rotina para acompanhar suas fontes.
3. Atualização dos Flatpaks do sistema/usuário e do Discord, mantendo seu comportamento de fechar e reabrir quando necessário.
4. Verificação final dos kernels padrão/LTS, DKMS, initramfs e GRUB.
5. Depois de salvar o resultado e a agenda, notificação com **Reiniciar agora** ou **Mais tarde**. Não há reinício forçado; uma notificação de um boot anterior é descartada.

O menu principal mantém seis entradas:

| Opção | Ação |
| --- | --- |
| 1 | Limpeza e manutenção |
| 2 | Atualizar aplicativos nativos |
| 3 | Atualizar Discord |
| 4 | Atualizar geral |
| 5 | Callas OS Update |
| 6 | Sair |

A opção **2** não executa Flatpak nem atualiza kernel, boot ou componentes centrais. Ela consulta os repositórios em um banco isolado. Só aplica a fase oficial quando toda a transação pendente é compatível com esse escopo; um hook antes da instalação bloqueia mudanças de base caso o repositório mude entre a consulta e a execução. Se houver aplicativos oficiais junto de alterações de base, informa que a opção **4** é necessária. Não promete atualizar todos os aplicativos oficiais mantendo uma base congelada.

Nessa mesma opção, AUR só é compilado/instalado com as dependências já disponíveis; não instala dependências novas dos repositórios nem pacotes de kernel/base. Se alguma receita exigir essas mudanças, ela fica pendente para Atualizar geral. A rotina própria do Discord continua incluída. A opção **3** permite atualizar somente o Discord a qualquer momento, mantendo o comportamento de fechar e reabrir quando necessário.

O automático já é ativado pelo instalador e pela migração: geral mensal, aplicativos nativos semanal. O submenu de manutenção permite reparar o agendamento. A migração mantém um marcador para não reiniciar os prazos a cada reparo; usa a data inicial/última geral concluída como base e trata corretamente meses com menos dias. Uma fase nativa adiada por precisar da geral fica registrada, sem instalar partes incompatíveis nem repetir a tentativa a cada hora.

Uma execução manual informa a necessidade de autorização administrativa no início; o serviço trabalha com essa autorização durante a rotina, sem pedir senhas de pacote no meio. A rotina automática não pede senha. Não foi criada uma regra global para roubar foco de navegadores ou jogos. Ao terminar a geral com sucesso e salvar os logs/agenda, há notificação para reiniciar ou adiar; nunca há reinício forçado.

### Limpeza e manutenção

A opção **1** oferece limpeza segura, relatório de espaço/backups/VMs, revisão de órfãos e reparo do agendamento. Uma manutenção automática diária também roda, aguardando a atualização se ela estiver em execução.

- Cache do Pacman: conserva três versões e exclui a pilha NVIDIA da rotação. Não desinstala aplicativos. A limpeza usa o bloqueio do Pacman, evitando conflito com outra transação.
- Temporários: segue as regras de idade do `systemd-tmpfiles --clean`, restritas a `/tmp` e `/var/tmp`; não apaga a pasta `.cache` do usuário. Arquivos nesses diretórios temporários continuam sujeitos às regras normais do Linux. Restos conhecidos de compilações interrompidas do atualizador, com mais de sete dias, também são removidos.
- Logs/backups: aplica os limites documentados e remove os mais antigos.
- Órfãos: somente revisão manual. Mostra os candidatos e seus detalhes, pede confirmação e consulta novamente antes de remover. Preserva componentes essenciais/aplicativos padrão; não faz remoção recursiva de dependências.
- VMs: relatório de discos/ISOs e espaço realmente ocupado. Consulta a associação visível do libvirt quando possível, mas não considera ausência nessa consulta como prova de abandono. Não apaga máquinas, snapshots, discos nem ISOs, inclusive do GNOME Boxes.

A limpeza não apaga caches de shaders da Steam, arquivos de jogos, dados do navegador ou perfis pessoais. Não existe reparador genérico que prometa corrigir qualquer defeito do Linux.

**Consequência da automação:** não existe revisão humana dos PKGBUILDs durante a rotina completa. O isolamento limita a compilação, mas não certifica que um pacote é benigno: scripts de instalação de um pacote AUR ainda podem rodar como root. Não se afirma que o automático faz uma auditoria de malware. Checksums e assinaturas de fontes continuam sendo verificados; chaves declaradas pela receita podem ser obtidas automaticamente pelo fingerprint, sem desativar a verificação.

Erros de rede, dependências não resolvidas, assinatura inválida, Paru indisponível, falha de compilação ou pacote ainda incompatível ficam nos logs e impedem que a atualização completa seja anunciada como bem-sucedida. O detector não identifica toda incompatibilidade possível, e recompilar um pacote binário não corrige necessariamente uma biblioteca ausente. A validação dos kernels/boot ainda é tentada ao final se uma etapa de aplicativos falhar. Uma falha não desfaz automaticamente as etapas já instaladas.

### Kernels padrão e LTS

Ambos já existiam no instalador. A migração garante `linux`, `linux-lts` e seus headers, sem fixar suas versões. Após transações relevantes, um hook verifica módulos NVIDIA/xone quando instalados, recompõe o initramfs e verifica as entradas de ambos no GRUB. Não muda a versão do driver NVIDIA nem força o boot pelo LTS.

Se `/boot` não estiver montado ou alguma validação falhar, o procedimento registra falha e cria `/var/lib/callas-os/kernel-check-failed`. Uma atualização com erro não é marcada como concluída. Uma falha em um hook ocorre depois da transação do pacman: não é rollback de pacotes e não impede fisicamente que o usuário reinicie.

### Validação de segurança

Testes offline: `python -m unittest discover -s programas-callas-os/tests -v`, mais sintaxe dos scripts Bash/Python. Incluem rejeição de download alterado/árvore incompleta, migração de lançadores antigos, agendas mensal/semanal, logs privados, plano AUR e saídas de consulta vazias, isolamento da compilação, rejeição de links em artefatos, sequência completa e bloqueio da notificação de sucesso após falhas, além da verificação simulada dos dois kernels.

Antes de considerar validado no hardware, testar numa VM Arch e depois na máquina real:

1. Migrar pela opção 5 a partir do atualizador antigo, inclusive pelo endereço da ponte. Conferir logs em Documentos e ausência das regras antigas de sudo sem senha.
2. Confirmar que a lista de versões NVIDIA antes/depois é idêntica; testar Overwatch manualmente. A versão 610.57.04 permanece uma tentativa de contornar regressões, sem promessa de resultado no jogo.
3. Confirmar `ufw status verbose`, IPv6, navegação, Steam e os serviços locais usados. O firewall não bloqueia uma aplicação maliciosa que já tenha permissão para iniciar conexões de saída.
4. Atualizar o sistema; iniciar uma vez pelo kernel padrão e outra pelo LTS. Conferir DKMS, initramfs, GRUB e os logs. Testar uma falha simulada de DKMS antes de confiar na detecção.
5. Conferir a sequência da atualização completa: Arch, AUR/recompilações, Flatpaks/Discord e validação dos kernels/boot. O aviso para reiniciar só deve aparecer depois de todas as etapas e do log terminarem com sucesso. Simular erro de pacman, AUR e validação; deve aparecer falha, sem sucesso falso nem reinício automático. Confirmar que os aplicativos não são atualizados duas vezes seguidas e que não há pedido redundante de reinício após já reiniciar.

Os testes offline não executam uma instalação real nem simulam o driver gráfico, Secure Boot ou o funcionamento do Overwatch. O ambiente desta revisão não tem uma instalação Arch/VM em execução; a validação real permanece necessária.

Roteiro adicional para a VM antes da máquina principal:

1. Rodar a opção 5 a partir do atualizador antigo; conferir a primeira migração e executar novamente para verificar idempotência.
2. Conferir `Documentos/Callas OS/Callas OS Logs` e `Documentos/Callas OS/Callas OS Backups`, migração dos pools antigos, limites, permissões e ausência de exportações duplicadas.
3. Usar **1 → 2** para ver ocupação e limite; executar **1 → 1**. Conferir que VMs, ISOs, aplicativos e shaders permanecem preservados.
4. Conferir o relatório de órfãos, cancelar a remoção e confirmar que nenhum pacote mudou. Reparar o agendamento e verificar que as datas não são reiniciadas em cada reparo.
5. Conferir mensal/semanal com `systemctl list-timers` e com as datas em `/var/lib/put-update/agenda`. A primeira migração usa a data inicial como referência; uma agenda já vencida pode executar na próxima verificação.
6. Testar a opção 2 com somente aplicativos pendentes e com atualização de kernel/base pendente. O segundo cenário deve adiar a fase oficial para a geral e preservar as versões do kernel/boot. Flatpaks não devem ser executados nessa opção.
7. Testar a geral, reiniciar pelos kernels padrão e LTS e conferir logs/DKMS. Com `/boot` desmontado, a atualização de pacotes deve ser interrompida antes do Pacman.
8. Só depois avaliar o uso na máquina principal. A NVIDIA continua travada e o Overwatch continua dependente do teste real.

---

## Boot e recuperação

As instalações atuais utilizam entradas próprias do Callas OS em vez da geração automática padrão do `10_linux`.

Isso permite ao projeto controlar diretamente as entradas de boot e manter separadas as opções normal, LTS e diagnóstico.

Também é instalado o caminho UEFI de fallback:

`EFI/BOOT/BOOTX64.EFI`

Se o kernel principal não iniciar após alguma atualização, utilize no GRUB:

**Callas OS (kernel LTS - recuperação)**

Para diagnóstico com mensagens visíveis e sem Plymouth, utilize:

**Callas OS (diagnóstico sem splash)**

Mudanças profundas nessa estrutura de boot não são distribuídas automaticamente para instalações antigas quando houver risco de deixar a máquina sem inicialização.

---

## Hardware e periféricos

O instalador também prepara suporte para rede, Bluetooth e periféricos definidos pelo projeto.

Quando o dispositivo **Rise Mode Aura Ice Black `aa88:8666`** é detectado, o instalador compila e configura automaticamente o driver correspondente. Se o hardware não estiver presente, essa etapa é ignorada.

O suporte a determinados adaptadores de rede e outros componentes também é aplicado de forma condicional conforme o hardware detectado.

---

## Falhas durante a instalação

Etapas críticas interrompem a instalação quando ocorre um erro que possa comprometer o sistema, incluindo:

- particionamento;
- criação dos sistemas de arquivos;
- instalação do sistema base;
- geração do initramfs;
- instalação do bootloader;
- validação do GRUB.

Componentes opcionais podem apenas gerar um aviso e permitir que a instalação principal continue.

Os avisos ficam registrados em:

`/var/log/callas-instalacao-avisos.log`

---

## Aviso sobre o desenvolvimento do projeto

O Callas OS é um projeto em evolução. Uma configuração que funciona hoje pode ser substituída no futuro por uma abordagem diferente, mais segura ou mais adequada ao Arch Linux atual.

Por isso:

- mantenha backup dos seus arquivos importantes;
- leia os avisos mostrados pelo atualizador;
- não force uma migração bloqueada por incompatibilidade;
- quando o projeto indicar instalação limpa, trate isso como uma mudança de geração do Callas OS e não como uma atualização comum.

A prioridade do projeto é preservar a possibilidade de recuperação e informar falhas, sem prometer ausência de vulnerabilidades.

---

<p align="center">
  <strong>Callas OS</strong><br>
  Arch Linux preparado para instalar, iniciar e usar.
</p>


