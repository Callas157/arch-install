# Histórico do Callas OS

## 3.25.1 — 2026-11-24

- **Callas OS Linux** aparece primeiro no GRUB. Em instalações novas, o Linux **7.2.15** inicia após **três segundos**. O **LTS** fica em segundo e a entrada de diagnóstico fica em terceiro.
- A instalação limpa e o Callas OS Update usam o mesmo auxiliar para ordenar as entradas reconhecidas. A atualização conserva os kernels, drivers, argumentos de boot e entradas personalizadas já presentes.
- A suíte offline voltou a exercitar a instalação opcional do Codex e deixou de depender de serviços e diretórios reais da máquina para testar bateria, widgets, aplicativos, instalação e atualização. Os testes de sessão agora verificam a preparação dos serviços sem reativá-los durante o Update.

## 3.25.0 — 2026-11-24

- O instalador usa Linux **7.2.15.arch1-1** e os headers assinados do Arquivo do Arch. Linux LTS e seus headers vêm dos repositórios atuais. O LTS fica no topo do GRUB e inicia por padrão em instalações novas.
- A versão inicial em GPUs compatíveis é **NVIDIA Open DKMS 610.57.04**. As assinaturas dos pacotes arquivados são conferidas antes de formatar e o instalador verifica DKMS e initramfs nos dois kernels.
- **Kernel Linux**, na Central, permite trocar ou reverter o par principal. **Driver NVIDIA** permite trocar a versão mesmo se o módulo atual estiver descarregado. As trocas usam pacotes assinados, validam o boot e tentam restaurar os pacotes anteriores se a etapa posterior à transação falhar.
- O Callas OS Update remove os blocos `IgnorePkg` antigos criados pelo projeto e coloca o LTS primeiro nas entradas Callas reconhecidas. A migração preserva os pacotes instalados.

## 3.24.3 — 2026-11-21

- **Instalação limpa NVIDIA:** o instalador oficial prepara a fonte DKMS da NVIDIA 595.71.05 em hook temporário PostTransaction `30-callas-nvidia-initial-compat.hook` antes do hook `70-dkms-install`. A versão escolhida é registrada antes da transação para que o preparador identifique o alvo correto. Depois, a instalação confirma os três pacotes essenciais (`nvidia-open-dkms`, `nvidia-utils`, `lib32-nvidia-utils`), executa o preparador nos dois kernels e só gera initramfs/GRUB depois da validação de módulos. Qualquer falha interrompe a instalação; não substitui silenciosamente por outra série.
- **Compatibilidade NVIDIA 595.71.05 em kernels Linux 7.2/7.3:** além do mapeamento DRM atomic, foram restaurados os caminhos corretos dos callbacks DRM quando os testes `conftest` não reconheciam a API nova, e corrigidas as chamadas `strncpy` removidas do Linux em `nvidia-modeset`, `nvidia-uvm` e `os-interface`. O patch preserva a API antiga do Linux LTS em tempo de compilação e mantém verificação exata das assinaturas da fonte.
- **Troca manual da Central:** continua usando pacotes do arquivo oficial com assinatura, compilação isolada antes da troca, hook de compatibilidade antes do DKMS instalado, validação de módulos dos dois kernels, logs e tentativa de rollback. Reparo da versão já instalada requer confirmação; o Callas OS Update não troca 610 por 595 automaticamente.
- **Diagnóstico:** botão `Copiar detalhes` na Central para enviar erros e logs sem transcrever capturas.
- **Testes e limite:** sintaxe Bash do instalador validada em cópia byte a byte correspondente à `main`; regressões offline adicionadas para a ordem dos hooks, compilação antes do initramfs, detecção dos dois layouts de fonte e assinaturas da NVIDIA. `bash -n` e testes simulados não comprovam compilação real, KMS/Wayland nem primeiro boot na RTX 3060 com Linux 7.3.5. Instalação limpa ainda exige ensaio real antes de ser considerada garantida.
- **Backup:** instalador original v3.24.2, verificado por comparação binária e SHA-256, salvo no Google Drive em `CallasOS/CallasOS 3.24.2/instalar-arch.sh`, junto com metadados. Link curto e nome do instalador preservados.

## 3.24.2 — 2026-11-21

- **Correção do preparador NVIDIA 595.71.05 no Arch:** os arquivos DRM, conftest e NVSwitch estão dentro de `/usr/src/nvidia-595.71.05/kernel-open/` no empacotamento Arch; a adaptação anterior pesquisava apenas `/usr/src/nvidia-595.71.05/nvidia-drm/` e poderia falhar antes de compilar. O preparador passa a reconhecer a estrutura real do Arch e preserva compatibilidade com a estrutura sem `kernel-open/` usada em outras distribuições.
- Aplicada a mesma detecção às cópias independentes do DKMS `source`/`build`, incluindo os testes offline de reconhecimento, idempotência e proteção contra estruturas não reconhecidas. O Callas OS Update continua bloqueando propositalmente a fase boot quando a NVIDIA instalada (595) diverge da versão fixada (610); somente a reparação manual na Central pode autorizar a correção da fixação.
- **Validação pendente:** esta correção de caminho foi verificada contra a listagem oficial do pacote DKMS Arch e as fontes upstream. Não houve compilação real da 595 no Linux 7.3.5 nem teste de reinicialização em RTX 3060; caso o reparo falhe, não reiniciar e preservar o log.

## 3.24.1 — 2026-11-21

- **Compatibilidade NVIDIA 595.71.05 ↔ Linux 7.3:** adaptação da fonte Open DKMS baseada no relato Deepin 25 com RTX 3060 (https://bbs.deepin.org.cn/en/post/302605), conferida contra os arquivos da tag 595.71.05 do repositório NVIDIA/open-gpu-kernel-modules. Corrige o nome `struct drm_atomic_state` → `struct drm_atomic_commit`, a família de funções `drm_atomic_state_*`, e os dois testes `conftest.sh` de callbacks CRTC/plano. Trata também as chamadas `strncpy` NVSwitch com cópia/zero-padding equivalente.
- Ao contrário de uma substituição global, as adaptações DRM são condicionadas a Linux 7.2+, preservando os caminhos antigos quando o DKMS compilar para o kernel LTS 6.x. A alteração é idempotente e limitada à versão 595.71.05 e às assinaturas de código reconhecidas; recusa fontes inesperadas em vez de aplicar mudanças genéricas.
- **Reparação da Central e instalação limpa:** o preparador detecta o kernel instalado e aplica o patch antes de executar o DKMS. Também verifica cópias reconhecidas da fonte em diretórios DKMS sem remover módulos existentes do LTS; falha permanece bloqueada com logs. O instalador compartilha esse mesmo preparador verificado, sem alterar nome/link do instalador.
- **Troca manual de versão:** a validação prévia de 595.71.05 altera somente a cópia temporária do código; quando o pacman instala a versão selecionada, um hook PostTransaction aplica a compatibilidade à fonte recém-instalada antes do hook de compilação DKMS. Nenhum kernel, headers ou driver é instalado pelo Callas OS Update sem escolha explícita.
- Verificações estáticas das assinaturas dos três arquivos de origem NVIDIA 595.71.05 e testes simulados adicionados para idempotência e interrupção segura. **Pendente:** teste real do DKMS em Arch Linux 7.3.5, boot KDE/Wayland e RTX 3060. Resultado de compilação não foi presumido; reinicialização só deve ser liberada após o verificador passar.

## 3.24.0 — 2026-11-21

- **Central → Driver NVIDIA → Reparar versão instalada:** nova opção manual para divergências entre os pacotes já instalados e a versão fixada. A Central apresenta o estado dos módulos para ambos os kernels, pede confirmação explícita antes de adotar a versão instalada e não baixa/atualiza drivers nesse reparo.
- O preparador DKMS compartilhado com a instalação limpa preserva os módulos corretos e recompila apenas kernels com módulos NVIDIA ausentes/incorretos. Se reconhecida, aplica a adaptação da API dmem do Linux 7.3 somente à fonte DKMS local; falhas interrompem o processo sem afirmar que o driver funciona.
- **Callas OS Update:** na etapa boot, detecta a divergência antes de alterar temas/GRUB e orienta a usar a Central para o reparo. Se versão instalada e fixada coincidirem, pode reconstruir módulos faltantes sem trocar pacotes ou atualizar kernel/headers, verificando módulos, initramfs e boot antes de concluir. Sem autorização do usuário, não converte 610 em 595.
- Diagnóstico persistido em `/var/lib/callas-os/nvidia-repair-last.log` (root). A versão fixada só é ajustada após verificação de quatro módulos NVIDIA para `linux` e `linux-lts`, reconstrução de initramfs e passagem no verificador de boot.
- **Limite de validação:** testes de integração no hardware RTX 3060 e compilação real de NVIDIA 595.71.05 contra Linux 7.3.5 ainda são necessários. Se essa combinação não compilar, o reparo falha e preserva o estado para diagnóstico; o patch conhecido de dmem não comprova compatibilidade total com Linux 7.3.

## 3.23.0 — 2026-11-21

- **Instalação limpa NVIDIA:** a série **595** passa a ser o padrão. Antes de qualquer formatação, o instalador consulta a versão mais nova da série com os três pacotes essenciais Open DKMS (nvidia-open-dkms, nvidia-utils, lib32-nvidia-utils) e respectivas assinaturas disponíveis no Arch Linux Archive. Se o conjunto 595 estiver indisponível, interrompe antes de apagar discos; não substitui silenciosamente por 610 ou 620.
- Os kernels **linux e linux-lts** e seus headers continuam vindo dos repositórios atuais do Arch. O preparador novo confere a versão escolhida e recompila/testa os quatro módulos NVIDIA via DKMS em ambos os kernels antes de criar initramfs/GRUB. Aplica adaptação específica da API dmem somente quando reconhecida; fontes não reconhecidas dependem da compilação real e falham sem anunciar instalação concluída.
- **Central Callas OS → Driver NVIDIA:** o catálogo agora considera essenciais somente os três pacotes do driver, permitindo exibir versões que antes desapareciam por indisponibilidade de utilitários opcionais. Complementos são atualizados quando existem versões correspondentes assinadas; a versão anterior dos componentes substituídos é removida pelo pacman, com download prévio assinado para possível restauração. Driver escolhido fica fixado para as atualizações gerais, sem impedir a troca manual deliberada.
- Preservadas as regras PreTransaction e a validação final de boot. O resgate de uma instalação interrompida passa a reconhecer a série 595 sem remover compatibilidade de resgate com o 610 anterior. O Callas OS Update não muda o driver em máquinas existentes.
- Verificações offline: sintaxe Bash do instalador e do resgate, compilação de fontes Python e testes simulados do catálogo com pacotes opcionais ausentes e versão 595 incompleta. **Ainda não houve instalação limpa real, troca efetiva em uma RTX, compilação DKMS no kernel Arch mais recente ou reinicialização física**. Uma falha de compatibilidade com kernel ou dependência deve ser registrada e bloquear a troca, nunca ignorada.
- Backup integral do instalador original da versão **3.22.3** salvo e conferido no Google Drive em CallasOS/CallasOS 3.22.3/instalar-arch.sh, SHA-256 1de58d4fc6e851d4ff233478f5d11036c30c218ed7037e973d6f11f2dc2b44af.

## 3.22.3 — 2026-11-21

- O **Callas OS Update** agora verifica o Codex opcional já instalado durante a atualização do sistema. Versões 1.3.x conhecidas são atualizadas automaticamente para o cliente 1.4.0, sem novo clique no botão Codex e sem reinstalar Whisper, Node ou dependências existentes.
- Em instalação limpa ou perfis sem Codex, não ocorre download, instalação, criação de conta nem modificação de arquivos do chat. Versões já atuais, futuras ou sem marcador identificável são preservadas sem reescrita.
- Se o Codex estiver aberto, não é fechado nem reiniciado; a atualização é adiada e a próxima execução do Callas OS Update verifica novamente, mesmo que o sistema já esteja na última release.
- Instalação roda com as permissões normais do usuário, reutiliza pacote 1.3.3 com SHA-256 e overlay 1.4.0 fixado e verificado por blob Git. O instalador continua preservando contas, conversas, anexos e backup do código anterior em app.previous.
- Testes adicionados para perfis não instalados, versão desconhecida/mais nova, sessão aberta, instalação somente dos arquivos do aplicativo e repetição sem nova release. Publicação no repositório sem ensaio de atualização física KDE neste atendimento.

## 3.22.2 — 2026-11-21

- Cliente Codex opcional 1.4.0: menu contextual para fixar e excluir conversas, limpeza paginada de histórico que não seleciona fixadas, seletor de modelo e nível de raciocínio na barra de envio.
- Integração GPT via API OpenAI com perfil isolado de autenticação e histórico. Modelo GPT-6.1 Sol, GPT-6 ou GPT-5.5 quando autorizado pelo projeto API. O motor de execução continua o Codex app-server local com acesso ao PC, sem modificar a conta ChatGPT do Codex. A chave é cadastrada pelo próprio usuário, sem ser escrita no repositório ou nas preferências Qt; o Codex pode armazená-la no keyring ou em auth.json local restrito.
- A Central preserva o pacote 1.3.3 com checksum SHA-256 e aplica as fontes 1.4.0 de um commit fixo com verificação de blob Git antes da instalação. O botão Codex oferece atualização quando encontra 1.3.x, e não reinstala versões locais mais novas ou desconhecidas, para evitar regressões e perda de personalizações. Reutiliza os dados, login e Whisper existentes.
- Testes de regressão adicionados; não foi executada instalação física KDE, autenticação real na API ou teste de modelo nesta conversa. Sem mudanças em kernel, NVIDIA, GRUB, discos ou políticas de update geral.

## 3.22.1 — 2026-11-21

- Corrigido o Callas OS Update para preservar janelas, regras do KWin e autostart da sessão durante atualizações de periféricos e aplicativos. A etapa session não reaplica callas-inicio-kde nem inicia callas-janelas.service, que reiniciava a memória persistente do Discord e podia bloquear a migração do G920. Também não reinicia callas-game-logs.service. Serviços em execução e preferências do usuário ficam intactos; arquivos já provisionados serão usados normalmente no próximo login KDE. A instalação limpa não muda.
- Com ou sem sessão gráfica ativa, a fase é concluída após preparar seus arquivos. O daemon-reload opcional somente atualiza definições, sem iniciar ou reiniciar serviços. O driver nativo do G920, o teste de marchas e o pacote python-evdev da 3.22.0 continuam mantidos. A etapa independente do Brave aberto continua com o comportamento anterior.
- Teste offline de regressão adicionado para a sessão ativa e sem sessão; não houve teste físico KDE ou do volante.

## 3.22.0 — 2026-11-21

- **G920 e câmbio Driving Force Shifter opcional:** adicionada tela **Central Callas OS → Volante G920 e câmbio** para reconhecer a base HID `046d:c262`, exibir sinais do volante/pedais e testar individualmente as seis marchas e a ré. O shifter é conectado à base e envia entradas como botões, sem dispositivo USB separado. O resultado diferencia sinal recebido pelo Linux de configuração do ETS2/Steam; falta de sinal não comprova defeito físico.
- O pacote oficial `python-evdev` é instalado por transação nativa protegida do Callas OS Update, via catálogo de aplicativos na fase `security`. A instalação limpa reaproveita o mesmo estágio e catálogo verificados. Permanecem o driver nativo `hid_logitech_hidpp`, `usb_modeswitch` e as regras udev; não foi adicionado módulo de terceiros.
- Não altera kernel, headers, NVIDIA fixada 610.57.04, Steam Input, nem outros periféricos. Teste offline de integração adicionado; reconhecimento físico do G920/câmbio em KDE e uso no ETS2 ainda precisam de verificação na máquina.

## 3.21.6 — 2026-11-21

- **Correção de falha na instalação limpa NVIDIA:** a série **610.57.04 permanece fixada**, e os kernels oficiais `linux` e `linux-lts` continuam vindos do Arch, com os respectivos headers. Antes de executar `mkinitcpio -P`, o instalador verifica explicitamente o pacote NVIDIA, aplica uma compatibilidade de código-fonte para a mudança da API `dmem_cgroup_register_region` do Linux **7.3** apenas quando o fonte NVIDIA corresponde ao trecho reconhecido, executa DKMS para cada kernel e exige os quatro módulos `nvidia`, `nvidia_modeset`, `nvidia_uvm`, `nvidia_drm` com versão **610.57.04** e vermagic do kernel. Não troca driver nem kernel para mascarar a falha.
- O auxiliar é baixado do **mesmo commit imutável** dos demais arquivos da instalação e validado por SHA do blob Git **antes de apagar o disco principal**. Erro de módulo, headers, build DKMS, fonte desconhecido ou kernel acima de **7.3** impede gerar initramfs e avançar para GRUB; os últimos trechos de `make.log` são exibidos para diagnóstico. A checagem é exclusiva da instalação limpa, não altera a política de kernel do Callas OS Update.
- Publicado `programas-callas-os/instalador/callas-recuperar-nvidia.sh` para o caso específico de **instalação já interrompida no mkinitcpio**, enquanto a ISO oficial ainda está aberta e o sistema/ESP permanecem montados em `/mnt`. Ele não particiona, formata nem reexecuta pacstrap; verifica os arquivos e montagens, prepara DKMS, reexecuta `mkinitcpio -P` e retoma apenas a parte final da configuração interna pré-existente após a falha. Rejeita um destino fora do contexto previsto; falhas encerram a execução.
- Validações offline: sintaxe Bash do instalador e do resgate, compilação Python dos auxiliares e trechos embutidos, **5 testes novos** de regressão (patch exato/idempotente, fonte desconhecido, versões de kernel, ordem de DKMS vs initramfs, ausência de formatação no resgate). Não foi executada compilação DKMS real, boot do Arch, reparo físico, Steam ou teste de jogo. Uma nova falha real exige log da compilação.
- Backup original da **3.21.5** salvo em `Google Drive/CallasOS/CallasOS 3.21.5`, SHA-256 `7cc3547fb502f55630eb523b918c9e1a033eeef1b2d81c5ddac1c69d174ec310`, byte a byte verificado antes de alterar `instalar-arch.sh`. Nenhuma alteração nos favoritos KDE, montagem de armazenamento secundário, driver selecionado ou opção 5 do Update.

## 3.21.5 — 2026-11-20

- Corrigido o diálogo de formatação opcional dos discos secundários na instalação limpa para cumprir a escolha numérica **sem confirmação adicional**. Após o aviso explícito de que TODOS os dados e partições daquele disco serão apagados, **`1` é a autorização definitiva para formatar ext4**; **`2` preserva o disco**. Enter, texto e outras opções não autorizam formatação. A antiga pergunta para digitar a palavra `APAGAR` foi removida por solicitação expressa do usuário.
- A remoção é restrita à confirmação do armazenamento secundário. Mantidos: identificação individual do disco, filtragem de mídia da ISO/USB e do disco principal, revalidação do disco e ID antes de gravar, formatação ext4 somente das unidades selecionadas; o disco do sistema continua sujeito ao fluxo normal de seleção do instalador.
- Sem alterações no Callas OS Update, favoritos do KDE, dock, kernel, NVIDIA 610.57.04, Steam ou montagem automática.
- Sintaxe Bash verificada; nove testes locais simulados passaram para nenhuma unidade, uma e várias unidades, opção `1`, `2`, Enter, textos inválidos e proteções de escrita. Os testes de regressão no repositório foram atualizados para o novo diálogo. Não houve teste físico de formatação ou instalação completa em VM nesta entrega.
- Backup íntegro do instalador original da **3.21.4** salvo antes da alteração em `Google Drive/CallasOS/CallasOS 3.21.4` e verificado após leitura, SHA-256 `312586aa1d4cdce722599c8af98ed45f3cc56b3631fb7d1094699af83b8b14be`.

## 3.21.4 — 2026-11-20

- Corrigido o diálogo de formatação opcional de discos secundários na instalação limpa. O menu permanece **1 = SIM, formatar ext4** e **2 = NÃO, preservar arquivos**. Após a opção 1, o instalador agora exige **somente a palavra `APAGAR` em maiúsculas**, sem nome nem caminho do dispositivo. A unidade continua identificada por dispositivo, tamanho, modelo e sistema de arquivos no próprio diálogo.
- `2`, Enter e opções inválidas preservam os arquivos. `apagar`, `APAGAR /dev/sdb` ou qualquer texto que não seja exatamente `APAGAR` não autoriza formatação. A filtragem de unidades internas, o bloqueio do pendrive da ISO, a separação do disco principal e a revalidação antes de apagar permanecem intactos.
- **Nenhuma outra configuração foi modificada**: Callas OS Update, favoritos do KDE, dock, montagem de dados, Steam, kernel e NVIDIA 610.57.04 preservados.
- Sintaxe `bash -n` e sete testes de seleção simulada concluídos, sem disco físico. A regressão existente foi atualizada para a nova confirmação e inclui opções válidas/inválidas. Não foi realizado teste de instalação limpa em hardware.
- Backup da versão 3.21.3 realizado antes da alteração e verificado byte a byte no Google Drive (`CallasOS/CallasOS 3.21.3`, SHA-256 `079696d92ba5c523e6339da7320a9109c8be6bdc620f50345b47be719c13ca4c`).

## 3.21.3 — 2026-11-20

- **Favoritos padrão do menu KDE Plasma (Kickoff):** reduzidos a exatamente quatro lançadores, nesta ordem: **Central Callas OS**, **Steam**, **Discord** e **Configurações do Sistema**. Retirados dos favoritos padrão os extras antigos (Monitores, Konsole, Bazaar, ProtonPlus, Mission Center, qBittorrent, Spotify e Solaar), sem desinstalar nenhum aplicativo.
- O instalador limpo e a etapa `desktop` do Callas OS Update passaram a escrever a mesma lista em `/etc/xdg/kicker-extra-favoritesrc`, com `IgnoreDefaults=true`. A etapa é detectada por hash de conteúdo para reaplicação no Update. De acordo com o comportamento do KDE, essa configuração **define favoritos padrão para novas contas**; preferências personalizadas já salvas nas contas existentes não são apagadas ou reescritas automaticamente.
- **A dock/barra inferior não foi alterada**: permanece com os lançadores Dolphin e Brave já configurados. O pedido altera somente o menu Kickoff, não autostart de Steam/Discord nem os programas instalados.
- Proteções mantidas: nenhum ajuste em kernel, NVIDIA 610.57.04, rotinas de armazenamento, permissões de usuário ou outras configurações da Central.
- Testes: `bash -n` no instalador de conteúdo idêntico ao publicado e validação estática dos dois blocos Kickoff (quatro IDs na mesma ordem) concluídos. Adicionada regressão offline `tests/test_kde_menu_favorites.py`, ainda sem validação em uma sessão KDE real.
- Antes de editar o instalador, o original da versão **3.21.2** foi salvo e verificado byte a byte no Google Drive, em `CallasOS/CallasOS 3.21.2`, com SHA-256 `617830fc5c4e0c8625257e03636adea042e3c157bdf9f47c53935b81d5290591`. 

## 3.21.2 — 2026-11-20

- A instalação limpa preserva a seleção inicial do disco do sistema, que continuará sendo apagado conforme aviso existente. Cada armazenamento **secundário** elegível agora recebe um menu numérico: `1 — SIM, formatar em ext4` e `2 — NÃO, preservar arquivos`. Somente a opção literal `1` permite prosseguir à confirmação final obrigatória `APAGAR /dev/...`. Resposta inválida, vazia ou `2` preserva o disco; mídia USB, disco da ISO e disco principal continuam excluídos da escolha secundária.
- Sem discos secundários elegíveis, a pergunta é inteiramente omitida. Com vários discos, cada pergunta permanece individual e numerada; formatação destrutiva nunca é acionada apenas pela detecção de um disco ou por escolher o sistema no disco principal.
- Os discos de dados internos suportados continuam configurados automaticamente pelo **UUID** em `/etc/fstab`, sem pedir senha no Dolphin ou em cada boot. O componente **exclusivo da instalação limpa** reforça `x-systemd.before=local-fs.target` nos registros próprios `/mnt/callas-UUID` de ext4, NTFS3 e demais formatos admitidos, para aguardar a tentativa de montagem antes de abrir a sessão e reduzir a corrida com a Steam. `nofail` continua permitindo boot quando o disco está ausente/falha; os timeouts de descoberta/montagem existentes permanecem. No ext4 preserva `passno=2` e `errors=remount-ro` para checagens de consistência e proteção contra erros.
- O caminho de montagem permanece estável por UUID, inclusive depois de reiniciar. A biblioteca Steam ainda exige que a pessoa a escolha uma vez; o projeto já possui mecanismo separado de reconciliação de bibliotecas Steam. Nenhuma automação pode garantir recuperação após corrupção grave, falha física, perda de dados ou interrupção de energia durante gravação.
- **Callas OS Update, kernel e NVIDIA 610.57.04 preservados**. Os dois conjuntos existentes de testes atualizados passaram em simulação (15 testes), juntamente com 13 verificações complementares de menu e fstab. `bash -n` e compilação Python passaram; não houve teste físico de queda de energia, boot de VM, Steam com biblioteca montada ou instalação limpa completa.
- Backup íntegro do instalador **3.21.1** no Google Drive `CallasOS/CallasOS 3.21.1`, feito antes do commit e comparado byte a byte com o GitHub (SHA-256 `e6323d13eaee0cbd1b89c735368046a7f4c6acf9cd818343a57481a12c4abc7e`).

## 3.21.1 — 2026-11-20

- Instalação limpa: a etapa **Discos secundários** só aparece após filtrar discos internos elegíveis e somente quando existir ao menos um. Em instalação com um único disco (por exemplo, VM com 30 GB), o instalador segue diretamente para o usuário e senha sem exibir cabeçalho ou alerta sobre um secundário inexistente.
- Havendo vários discos, numera cada um na sequência com o disco do sistema incluído na contagem: **Armazenamento 2 de 3**, **Armazenamento 3 de 3** etc., mostrando dispositivo, modelo, tamanho, sistema de arquivos e o aviso de exclusão antes da decisão de cada unidade.
- A opção padrão segue sendo **não formatar**. A confirmação exata `APAGAR /dev/...`, a verificação de discos internos/USB e as proteções contra apagar volumes montados, o disco principal e a mídia ISO não foram alteradas. Nenhuma alteração funcional no Callas OS Update, kernels ou driver NVIDIA 610.57.04.
- Validação: `bash -n` do instalador e **9 testes offline de regressão** executados em cópia com conteúdo idêntico ao publicado (SHA do blob Git `984b6fa637e62c555a0d343da38bbae7ab898b83`). Cenários com zero, um e dois secundários, confirmação incorreta/correta e preservação por padrão. Não houve instalação completa ou teste físico de formatação.
- Backup anterior, da **3.21.0**, verificado por SHA-256 após leitura do Google Drive antes de alterar o instalador. Para respeitar o limite de 10 cópias utilizáveis, os arquivos dos dois backups mais antigos (3.3.2 e 3.3.3) foram enviados à lixeira de forma recuperável; as pastas vazias permanecem porque o conector não permite excluí-las.

## 3.21.0 — 2026-11-20

- A instalação limpa exibe no próprio terminal da ISO um banner grande **WELCOME / CALLAS OS**, em caracteres `#`, colorido em terminais compatíveis e monocromático nos demais, antes da seleção dos discos. Não exige figlet e não altera o boot ou os wallpapers.
- Depois de escolher o disco principal, mas antes do nome do usuário e da senha repetida, o instalador percorre os **discos internos secundários** elegíveis (SATA/ATA/NVMe), independentemente da quantidade. Para cada um, a pergunta oferece **[s/N]**; o padrão preserva integralmente o disco, independentemente de NTFS, exFAT ou ext4. Um pedido de formatação precisa ser seguido pela confirmação exata `APAGAR /dev/...`; caso contrário, nada é agendado.
- A formatação autorizada apaga **o disco físico secundário inteiro**, recria uma partição de dados GPT Linux e formata em **ext4**. Antes da primeira operação destrutiva e antes de cada disco, a seleção é revalidada com dispositivo e identificador maior:menor. Pendrive USB, mídia removível, disco principal, disco da ISO, discos montados, RAID/LVM/criptografia e pools Btrfs não são candidatos. Não há conversão de NTFS preservando arquivos: ext4 é criação de um novo sistema de arquivos.
- As novas partições ext4 são entregues ao mecanismo de montagem por UUID e de permissões da instalação limpa; permanece manual apenas a adição da biblioteca na Steam. **Nenhum código do Callas OS Update**, kernel ou NVIDIA foi modificado. Mantém a preferência por NVIDIA 610.57.04 e kernels atuais do Arch, com validação de boot já existente.

Verificações: sintaxe Bash do instalador e compilação do trecho Python do banner verificadas em cópia de texto; seis testes offline de seleção simulada passaram (padrão Não, confirmação exata, cancelamento e ordem das perguntas). Inclui regressões em `tests/test_installer_secondary_format.py`. Não foram testadas formatações em hardware real, instalação limpa completa, queda de energia ou compatibilidade do driver com kernels futuros. O backup anterior no Google Drive foi dispensado somente nesta entrega após concordância do usuário nesta conversa.

## 3.20.0 — 2026-11-20

- Instalação limpa: complementa a descoberta e a montagem por UUID que o instalador já executava via `callas-security.sh`. O novo componente finaliza a preparação de volumes internos ext4 e o acesso do usuário; a descoberta existente continua excluindo USB/removíveis e discos do sistema, sem formatar ou alterar UUID dos discos secundários. Os volumes elegíveis são acessíveis pelo Dolphin no boot sem solicitação de senha para montar.
- Nos volumes ext4 internos reconhecidos, configura a checagem segura de sistema de arquivos pelo systemd (`passno=2`) e `errors=remount-ro`. Após a instalação, ajusta **somente** a propriedade da raiz do volume quando ela pertence ao root e não parece ser outra instalação Linux; arquivos existentes e proprietários diferentes são preservados. A seleção da biblioteca na Steam continua manual.
- O complemento exclusivo do instalador fica em `programas-callas-os/instalador/callas-storage-setup.py`, baixado e verificado contra o SHA Git do mesmo commit antes de qualquer operação destrutiva no disco de instalação. A opção 5 — Callas OS Update não foi modificada.
- Preserva o kernel mais recente oferecido pelo Arch na instalação limpa, junto dos headers e do LTS de recuperação. Continua fixada a NVIDIA 610.57.04; a validação de DKMS/boot já existente deve bloquear a conclusão se o kernel não for compatível. Não existe garantia de compatibilidade com todos os kernels futuros nem recuperação automática de corrupção grave.

Validação: verificações offline de sintaxe Python e cenários simulados de fstab, persistência/idempotência, proteção do disco de sistema e permissões realizadas. Não foi feita instalação limpa em máquina física/VM, simulação de queda de energia ou compilação NVIDIA 610 contra kernel futuro. Por autorização explícita do usuário nesta conversa, a exigência de novo backup do instalador no Google Drive foi dispensada **somente nesta entrega**.

## 3.19.0 — 2026-11-20

- Adiciona **Discos (GNOME Disks)**, pacote oficial `gnome-disk-utility`, ao catálogo de aplicativos nativos do Callas OS (`present`, fase `apps`). É instalado na instalação limpa e também pela opção 5 — **Callas OS Update**, respeitando a proteção de kernel, headers, driver NVIDIA e a escolha de desinstalação do usuário.
- Disponibiliza **Discos (GNOME Disks)** na lista de **Aplicativos padrão Callas OS** para restauração seletiva, usando o ícone `org.gnome.DiskUtility` do pacote. O aplicativo aparece no menu KDE por seu próprio arquivo desktop; não instala o desktop GNOME nem substitui Dolphin ou as configurações de montagem.
- Nenhuma alteração automática de disco, partição, formato ou `/etc/fstab` foi introduzida. O HD500G permanece sob controle do usuário.

Validação: teste de regressão do catálogo e dos caminhos compartilhados adicionada em `tests/test_app_catalog.py`; não houve execução de instalação, Update completo nem testes de hardware físico nesta entrega.

## 3.18.5 — 2026-11-20

- Corrige o escopo da entrega 3.18.4: o resgate NTFS somente leitura **não corrige** uma partição marcada como `dirty` após queda de energia. Retira a tentativa automática de resgate do Callas OS Update e da inicialização, para não mascarar o erro nem confundir acesso temporário com reparação.
- Desativa, em instalações que receberam a 3.18.4, somente o serviço `callas-ntfs-rescue.service` criado pelo Callas OS. Não desmonta volumes em uso, não modifica os dados, o UUID ou o `/etc/fstab`. Restabelece os mesmos auxiliares de montagem da 3.18.3.
- O reparo completo do sistema de arquivos NTFS deve ser feito com `chkdsk <letra>: /f` no Windows após assegurar que não há outro sistema utilizando o volume. O `ntfsfix` do Linux é limitado e não equivale ao `chkdsk`; nenhuma promessa de reparo automático pós-queda de energia.

Validação: conferência das alterações de código e do manifesto do projeto; sem execução de `chkdsk`, atualização completa, montagem real ou testes de boot na máquina física.

## 3.18.4 — 2026-11-20

- Ao encontrar no log do kernel um volume NTFS marcado como `dirty`, permite tentar montá-lo automaticamente **somente para leitura** com `ntfs-3g`, respeitando o ponto de montagem já definido no `/etc/fstab` (inclusive `/mnt/hd-500`). Não altera UUID, tabela de partições, dados, `fstab` ou o estado `dirty`. Se não houver `ntfs-3g`, o destino não for seguro, ou o driver recusar, registra o motivo e mantém o volume sem montar.
- Integra o resgate à opção 5, **Callas OS Update**, e instala/habilita um serviço de inicialização também no fluxo de instalação limpa. Inclui `ntfs-3g` no catálogo compartilhado de aplicativos de sistema e repete a tentativa após preparar a dependência. O serviço preserva o namespace de montagem compartilhado com o Dolphin e mantém o processo FUSE durante a sessão.
- A recuperação somente leitura não substitui `chkdsk` no Windows nem garante acesso a volumes fisicamente danificados. Não usa `force`, `ntfsfix -d` ou reparos automáticos destrutivos. Preserva a política de kernel/NVIDIA e as montagens existentes.

Validação: testes offline de regressão adicionados em `tests/test_ntfs_rescue.py`, ainda sem execução em hardware/boot real nesta entrega; o HD afetado precisa de teste após a atualização.

## 3.18.3 — 2026-11-19

- Reorganiza a tela inicial da Central com mais espaço entre os botões e a ação Sair no rodapé.
- Reúne os controles de detalhes e logs no painel de progresso. Os detalhes têm altura limitada e a tela pode rolar para manter o campo de resposta acessível em janelas menores.

## 3.18.2 — 2026-11-19

- Corrige a montagem automática de partições GPT Microsoft Basic Data com NTFS ou exFAT e o atributo `0x8000000000000000`, que suprime a letra padrão no Windows. Os demais atributos continuam sujeitos à proteção existente, incluindo partições ocultas, somente leitura, de recuperação e reservadas.
- Permite configurar a montagem por UUID no Callas OS Update e na instalação limpa. Quando o Dolphin já montou o volume, preserva o caminho em uso. A Steam nativa pode recuperar a biblioteca existente na montagem persistente. O auxiliar passa a mostrar o tipo e os atributos de partições excluídas no log.

Validação: 433 testes offline executados, 432 aprovados e um opcional ignorado. Sintaxe de 98 Python e nove Bash conferida. Em QEMU/KVM com kernel e udev reais, o cenário SATA de sistema e NVMe com EFI, partição reservada e dados NTFS reproduziu a exclusão na 3.18.1. Com a correção, apenas os dados receberam a montagem persistente por UUID, e o volume montou como ntfs3 no boot seguinte com o atributo GPT intacto. O outro PC físico ainda não foi verificado.

## 3.18.1 — 2026-11-19

- Corrige a detecção de discos internos secundários com o sistema em SATA ou NVMe. Aceita disco interno marcado como hot-plug, sistema de arquivos diretamente no disco e partições de dados ao lado de partições reservadas. Inclui XFS e Btrfs de dispositivo único. Protege a origem do sistema, os volumes removíveis, os UUIDs ambíguos e as montagens configuradas pelo usuário.
- Aplica a montagem de armazenamento pelo Update antes das etapas de aplicativos, com backup de `/etc/fstab`. Em uma sessão ativa, tenta montar os novos destinos livres e reaplicar os destinos UUID criados pela 3.18.0. Mantém o caminho de uma montagem do Dolphin já em uso e registra no log por que cada volume foi preservado ou descartado.
- Recupera bibliotecas já existentes da Steam nativa pelos arquivos que identificam os jogos instalados. Restaura referências que ficaram com o caminho antigo e registra bibliotecas ausentes no catálogo quando pode identificá-las, como usuário e antes da abertura da Steam. Mantém os arquivos dos jogos, a biblioteca principal e a política do primeiro boot. Instalação limpa e Callas OS Update usam os mesmos auxiliares verificados.

Validação: 430 testes offline executados, 429 aprovados e um opcional ignorado. Sintaxe de 98 Python e nove Bash conferida. Em dois boots QEMU/KVM com kernel Arch 7.2.15 e udev reais, o auxiliar protegeu o SATA de sistema e montou o NVMe GPT de jogos por UUID no boot seguinte, com unidade produzida pelo gerador real do systemd. A Steam foi exercitada com catálogos e jogos de teste, sem abrir o cliente na VM. O outro PC físico e sua sessão KDE ainda não foram verificados.

## 3.18.0 — 2026-11-18

- Configura a montagem de partições NTFS, exFAT e ext4 elegíveis em discos internos SATA e NVMe, usando o UUID e as permissões da máquina. Preserva os discos do sistema, os volumes removíveis e as entradas de montagem existentes.
- Mantém o caminho de volumes montados pelo Dolphin na sessão atual, inclusive para bibliotecas Steam que já usam esse caminho. Partições ainda desmontadas recebem um caminho em `/mnt/callas-<uuid>`. A montagem entra em vigor na próxima inicialização. A Steam continua gerenciando o cadastro de novas bibliotecas.
- Distribui o mesmo auxiliar verificado pela opção 5 do Callas OS Update e pela instalação limpa. A atualização inclui `/etc/fstab` no backup de configurações, valida a tabela candidata antes da substituição e mantém a inicialização possível se o disco secundário faltar.

Validação: 406 testes offline executados, 405 aprovados e um opcional ignorado, com regressões de seleção de discos, preservação de montagens, reaplicação e falha de validação. Sintaxe de 96 arquivos Python e nove Bash conferida. Inventário real apenas de leitura e tabela candidata separada validada pelo findmnt. Boot e instalação em outro PC ainda não verificados.

## 3.17.0 — 2026-11-18

- Adiciona à Central a opção Driver NVIDIA, com versões da pilha Open DKMS publicadas no arquivo oficial do Arch. A troca manual valida pacotes assinados, a GPU e a compilação nos kernels padrão e LTS antes da transação. O seletor verifica o boot antes de confirmar a fixação e tenta restaurar a versão anterior se a aplicação falhar depois de alterar pacotes.
- Mantém a NVIDIA 610.57.04 como padrão da instalação limpa. A Atualização geral preserva a versão fixada e testa o DKMS antes de substituir kernels. A validação pós-transação verifica a versão e o kernel de cada módulo NVIDIA.
- Mostra a versão do Codex na lista de desinstalação e identifica instalações parciais pelo atalho ou pelos arquivos do aplicativo, preservando os dados do usuário.

## 3.16.2 — 2026-11-17

- Corrige a memória de janelas no formato do KWin 6.8: preserva General/Order, prioridade, identificadores e regras pessoais. O auxiliar antigo podia introduzir uma lista General/rules incompleta; a migração nativa então descartava grupos não listados. Mantém compatibilidade com o formato legado e inclui todos os grupos existentes antes de uma migração, com proteção contra gravação concorrente do KWin.
- Completa as políticas de lembrar monitor, maximização e tela cheia da janela principal do Discord, inclusive quando estava fechado durante a configuração. Não força monitor principal nem substitui valores já aprendidos por coordenadas de abertura.
- Adiciona memória persistente exclusiva do Discord, privada no perfil do usuário e independente do cache em memória do KWin. Restaura posição, tamanho e formato por conector físico; acompanha alterações e fechamento, mantém geometria normal quando maximizado/tela cheia e preserva a preferência quando o monitor ainda não está disponível, retomando ao conectar. Ignora splash, diálogos e popouts e deixa o usuário mover livremente.
- Integra o observador de usuário à ativação de janelas, com confirmação do próprio script antes de anunciar prontidão e retomada após reinício do KWin. O estágio verificado e os checkpoints distribuem auxiliar e serviço tanto na instalação limpa quanto no Update, sem alterar instalar-arch.sh. Preserva Spotify, demais janelas, perfis/contas, autostart do primeiro boot, atualizador interno do Discord e a política de kernel/NVIDIA.
- Registra em AGENTS.md a obrigação de cuidado com o Discord e de corrigir efeitos indiretos em entregas de monitores, sessão, Central e Update.

Validação: 391 testes offline executados, 390 aprovados e um opcional ignorado; sintaxe de 94 Python e nove Bash. Motor JavaScript exercita restauração, alterações do usuário, fechamento imediato, monitor tardio, persistência privada e compatibilidade histórica. Probe opt-in em KWin 6.8.2 real, com D-Bus, dois monitores virtuais e HOME/XDG isolados, confirmou posição/tamanho normal, maximização, tela cheia, reabertura e reinício de compositor/observador usando somente janela Qt sintética, incluindo reinício apenas do observador enquanto a janela permanece maximizada, preservando o retângulo normal. Revisão independente e regressão correspondente conferidas. A regra real do Discord desta máquina foi reparada para HDMI-A-1, posição 961,0 e tamanho 959×1080, sem mover ou encerrar a janela. Não encerrou Discord/chamadas, não reiniciou o PC, não instalou pacotes/kernel/NVIDIA nem executou Update completo; o teste virtual não equivale a um boot real do Discord.

## 3.16.1 — 2026-11-17

- Corrige a distribuição da página Monitores: título, lista de telas e mensagem permanecem juntos no alto; Atualizar lista, Configurações de telas do KDE e Voltar ficam no rodapé. O espaço expansível separa esses dois grupos, sem empurrar a lista para baixo.
- Remove o fundo retangular indevido do Relógio Moderno. O getter do Plasma pode informar StandardBackground mesmo sem preferência explícita; a movimentação passa a consultar a chave realmente salva antes de preservar um fundo. Novas instâncias usam NoBackground, inclusive quando a recuperação vem de um registro da versão anterior sem preferência explícita. Escolhas explícitas futuras continuam preservadas ao mover.
- O Update corrige uma única vez a aparência de relógios já instalados, na sessão do usuário e sem recriar/mover o widget ou instalar o relógio em quem não o tem. Guarda o estado anterior em registro privado e, sem sessão Plasma, deixa tentativa para o próximo login. Mantém fontes, tamanho, posição, atalhos e outros widgets. Instalação limpa recebe a mesma correção pelo auxiliar compartilhado, sem editar instalar-arch.sh.

Validação: 373 testes offline executados, 372 aprovados e um opcional ignorado; sintaxe Python/Bash conferida. Regressões de layout, fundo implícito/explícito, instalação inicial, recuperação histórica e migração opcional/repetição/falta de sessão. Correção aplicada ao relógio existente desta máquina via API Plasma: mesma instância 31 no desktop 2/tela 1, fonte 50 e sem recriação; ausência do retângulo conferida em captura real. Prévia Qt dos botões no rodapé conferida. Sem executar Update completo, instalar pacotes, mudar kernel/NVIDIA ou realizar instalação Arch limpa.

## 3.16.0 — 2026-11-17

- Corrige a página Monitores: lista de telas logo abaixo de “Definir monitor principal”, texto de orientação abaixo da lista e controles agrupados no topo, preservando a seleção do monitor principal e as configurações de telas do KDE.
- Adiciona Relógio Moderno aos Aplicativos padrão Callas OS, com Instalar e Configurar lado a lado. A configuração permanece dentro da mesma Central e mostra cada monitor detectado com quatro cantos clicáveis, além de abrir a edição livre da área de trabalho. Detecta novamente o conector antes de mover; preserva aparência, tamanho, atalho e bloqueio existentes e não reposiciona após arraste manual. Salva recuperação privada antes de recriar o relógio, aguarda a liberação efetiva do layout entre chamadas e confere a posição; falhas tentam restaurar a origem e mantêm a retomada se a sessão impedir a recuperação. Não remove outros widgets para liberar um canto ocupado.
- Instala o relógio por padrão apenas na instalação limpa, com adição única no primeiro login. O padrão inicial é o canto superior esquerdo da segunda tela, ou da principal quando houver uma. No Update de máquinas existentes, distribui apenas o auxiliar e o pacote verificado para instalação opcional pela Central; preserva instâncias existentes e não adiciona o relógio automaticamente. Instalar somente o relógio dispensa sudo; seleções mistas mantêm a operação do widget na sessão gráfica do usuário.
- Inclui auxiliar e pacote no estágio completo e checkpoints, preservando a preparação por lançadores históricos e a retomada após falha. O anexo permanece integral e é extraído com validação de caminhos e identidade. A instalação limpa usa o auxiliar compartilhado já chamado pelo instalador; não altera instalar-arch.sh, suas cópias embutidas, pacotes, kernel ou NVIDIA.

Validação: 367 testes offline executados, 366 aprovados e um opcional ignorado; sintaxe de 91 arquivos Python e nove Bash conferida. Scripts de posicionamento exercitados em motor JavaScript real com API Plasma simulada, perfis temporários para instalação/repetição/primeiro login e falhas, navegação e cliques Qt para três monitores. Revisão independente encontrou colisão na recriação e perda de atalho/bloqueio; regressões reproduziram as falhas antes da correção. Inclui exclusão adiada, canto ocupado por outro widget, recuperação e retomada em motor JS com API Plasma simulada. Prévia visual das telas de monitores e configuração conferida. Detecção real de dois monitores somente de leitura. Sem instalar o anexo, mover widgets nesta máquina, executar Update completo, instalação Arch real ou validar posicionamento/arraste no Plasma real.

## 3.15.1 — 2026-11-17

- Corrige o migrador visual do GRUB que recusava entradas válidas por exigir quatro espaços e um único arquivo na linha initrd. Reconhece microcódigo + initramfs, espaçamento/aspas/comentários, caminhos com /boot, comandos EFI, continuações e imagens fallback, preservando comandos originais, UUIDs, argumentos e ordem das imagens. Continua recusando entradas ausentes, ambíguas ou pares kernel/initramfs incompatíveis.
- Valida a compatibilidade antes de alterar os assets de boot. Mantém marcador de retomada desde a primeira alteração e preserva grub.cfg até o novo arquivo passar na validação. Ajusta as verificações posteriores para caminhos citados e inclui 09_callas no backup de configurações. O auxiliar compartilhado atende instalação limpa e Update sem alteração do instalador principal.
- Adiciona regressões de preparação direta pelos lançadores históricos 3.2.2, 3.7.0, 3.9.0 e 3.10.0, sem exigir releases intermediárias. Registra a obrigação de compatibilidade dos formatos e interfaces existentes para futuras mudanças. Essas simulações não certificam todas as possíveis instalações antigas ou customizações locais.
- Confirma por teste que o Brave Origin continua opcional na Central e fora do catálogo automático do Update. Somente a instalação limpa o define como navegador padrão; o Update não troca o navegador das máquinas existentes.

Validação: 338 testes offline executados, 337 aprovados e um opcional ignorado; sintaxe de 86 arquivos Python e nove Bash conferida. Migração e fase real do script GRUB exercitadas em arquivos temporários com ferramentas de geração simuladas, incluindo falha de validação seguida de retomada e preservação do arquivo anterior; revisão independente sem impedimentos após ajustes. Sem executar Update no sistema real, trocar pacotes/kernel/NVIDIA ou validar boot na máquina que enviou o log. O log não inclui 09_callas; o formato exato daquela máquina ainda não foi confirmado.

## 3.15.0 — 2026-11-17

- Troca o navegador das novas instalações para Brave Origin (`brave-origin-bin`), com associação HTTP/HTTPS/HTML, preferência do KDE e atalho do painel. Mantém o Brave tradicional disponível na Central e adiciona o Origin à mesma lista com ícone persistente. Não declara nenhum navegador como instalação automática do Update, não remove o tradicional nem altera o navegador padrão de máquinas existentes.
- Centraliza a configuração dos dois navegadores em `callas-browser`: políticas compartilhadas de Bonjourr/SteamDB e preferências recomendadas, pt-BR, KWallet, barra de título, botão inicial/favoritos e busca de abas. Perfis e flags permanecem separados. Instalação limpa e Update usam o mesmo auxiliar verificado; o hook de instalação/atualização dos dois pacotes reaplica somente os padrões de sistema.
- Preserva contas, extensões pessoais, preferências desconhecidas e perfis em uso. Não substitui JSON inválido, recusa caminhos simbólicos e confere alterações concorrentes antes da gravação. Configura perfis Default e adicionais; o backup do Update agora inclui as preferências de ambos, flags, políticas e preferências iniciais. Inclui Origin nas regras de memória de janelas e na limpeza de autostarts sem iniciá-lo automaticamente.
- Backup anterior 3.14.0 do instalador confirmado no Google Drive por leitura integral e SHA-256 antes da edição; retenção conferida com dez backups. Mantém cópias embutidas sincronizadas e preserva o escopo de aplicativos, kernel, NVIDIA e modo manual.

Validação: 328 testes offline executados, 327 aprovados e um opcional ignorado; sintaxe de 85 arquivos Python e nove Bash conferida. Configuração completa do instalador executada em namespace isolado com comandos de pacotes/hardware simulados, incluindo Origin como padrão; perfis temporários testados com preservação de contas/extensões, navegador aberto, JSON inválido e seleção das fontes de backup. Revisão independente sem impedimentos. Nenhum navegador ou perfil real desta máquina foi alterado; sem instalação real de pacotes, download das extensões num perfil novo, Update completo ou boot real.

## 3.14.0 — 2026-11-17

- Integra manutenção, monitores, aplicativos padrão e desinstalação como páginas internas da janela principal da Central, com retorno à tela inicial. Mantém os controles de progresso e detalhes existentes para atualizações/manutenção. Não abre janelas de navegação adicionais.
- Adiciona os ícones na coluna Aplicativo do desinstalador, com linhas maiores para reconhecimento visual. Usa as referências dos atalhos nativos/AppImages, IDs dos Flatpaks, ícone do Codex, assets persistentes do catálogo e exportações de ícones do sistema/usuário. Aplicativos sem ícone identificável recebem ícone genérico; pacote, origem e proteção permanecem independentes da imagem.
- Mostra as confirmações de instalação, remoção, monitor principal, atualização geral, modo manual, Codex e reinício dentro da mesma Central. Cancelar preserva o estado e não inicia a operação. Bloqueia navegação e fechamento enquanto um auxiliar está ativo. Mantém a senha no diálogo de autorização separado, fora dos logs, e a abertura de aplicativos externos como Codex/KDE nos seus próprios programas.
- Instalação limpa e Callas OS Update recebem a mesma interface e auxiliar de inventário pelos arquivos já incluídos no estágio verificado/checkpoints. Não altera o instalador principal, pacotes, kernel, NVIDIA nem as escolhas locais de desinstalação/restauração.

Validação: 321 testes offline executados, 320 aprovados e um opcional ignorado; navegação e confirmações Qt, cancelamento, bloqueios de operação, roteamento para progresso e referência de ícones AppImage cobertos. Inventário real somente de leitura e prévias Qt com uma única janela visível conferidos; revisão independente sem impedimentos. Sem instalar/remover aplicativos reais, trocar monitores, executar Update completo, instalação Arch limpa ou boot real.

## 3.13.0 — 2026-11-16

- Transforma Aplicativos nativos em submenu com “Aplicativos padrão Callas OS” e “Atualizar aplicativos”. A lista dos padrões expande a mesma janela, com cartões, ícones, descrição, versão, tamanho informado pela fonte, busca e estado instalado. Permite instalar individualmente ou marcar/desmarcar os desejados e instalar só os selecionados, com botões verdes.
- Oferece os aplicativos comuns da instalação limpa, incluindo nativos/AUR e Flatpaks de sistema. A oferta `defaults` usa o catálogo verificado, sem ampliar a lista de instalação automática do Update. Mantém separada a atualização dos aplicativos já instalados. Metadados indisponíveis aparecem explicitamente; tamanhos não incluem todas as dependências e o AUR não fornece tamanho antecipado.
- A restauração valida todos os IDs, mantém os locks e usa as instalações protegidas existentes, sem sincronização/atualização geral, kernel ou NVIDIA. Confirma cada instalação antes de desfazer a preferência de desinstalação daquele aplicativo. Falhas parciais preservam as escolhas dos demais e os sucessos confirmados. Desmarcar não desinstala; logs continuam em Documentos.
- Distribui auxiliar e ícones persistentes pelo mesmo estágio verificado da instalação limpa e do Update, com checkpoints de integridade. Não altera o instalador principal, as cópias embutidas nem adiciona convite/contato Discord.

Validação: 314 testes offline executados, 313 aprovados e um opcional ignorado; sintaxe de 82 arquivos Python e nove Bash conferida; testes Qt de navegação na mesma janela/seleção/cancelamento/falha parcial, restauração e opt-outs com pacotes simulados; inventário e metadados reais somente de leitura; prévia visual e revisão independente. Nenhum pacote real foi instalado/restaurado, nem executado Update completo, instalação Arch limpa ou boot real.

## 3.12.0 — 2026-11-16

- Adiciona “Desinstalar aplicativos” à Central, com janela do mesmo tamanho, busca, origem/versão e confirmação. Identifica aplicativos nativos/AUR pelo proprietário dos atalhos do sistema, Flatpaks de sistema/usuário, o Codex opcional da Central e AppImages no perfil do usuário. Componentes essenciais ficam ocultos por padrão e bloqueados mesmo quando exibidos para consulta.
- Revalida o alvo antes de remover. Nativos usam `pacman -R` protegido, sem cascata, limpeza de dependências ou atualização geral; dependências necessárias a outros pacotes impedem a remoção. Flatpaks usam a referência completa, sem apagar dados nem runtimes. Detecta aplicativos em uso e serializa remoções administrativas com as atualizações da Central.
- Preserva arquivos pessoais, login, conversas, anexos e modelos do Codex. Não executa desinstaladores baixados nem apaga diretórios genéricos; AppImages precisam ser arquivos identificáveis, pertencentes ao usuário, sem caminhos simbólicos. Operações pessoais dispensam sudo; pacotes nativos e Flatpaks de sistema usam a autorização gráfica existente, reaproveitando a validade da senha.
- Registra escolhas locais para o catálogo e as preparações complementares não reinstalarem aplicativos removidos pela Central. Salva logs em Documentos. Instalação limpa e Update distribuem o mesmo auxiliar e interface verificados; instalador e cópias embutidas não precisaram de alteração.

Validação: 303 testes offline executados, 302 aprovados e um opcional ignorado; sintaxe Python/Bash, diff e prévias Qt conferidos. Inventário real somente de leitura; remoção CLI real de um AppImage artificial em pasta temporária e testes de preservação do Codex em perfil simulado. Demais transações nativas/Flatpak e autorizações simuladas, sem remover aplicativos instalados, executar Update completo, instalação Arch limpa ou boot real.

## 3.11.1 — 2026-11-15

- Mostra “Reiniciar agora” e “Mais tarde”, lado a lado no canto inferior direito da Central, após conclusão bem-sucedida de Atualizar geral ou Callas OS Update. A oferta independe de mudança na versão dos pacotes, cobrindo atualizações de GRUB/Plymouth e configurações. Não apresenta reinício como obrigatório.
- Mantém os botões ocultos durante a execução, em erros e atualizações incompletas. “Mais tarde” apenas fecha a oferta; “Reiniciar agora” mantém a confirmação existente. Sem reinício automático.
- A instalação limpa e o Update distribuem a mesma interface verificada pelo auxiliar compartilhado; não foi necessário alterar o instalador.

Validação: 290 testes offline executados, 289 aprovados e um opcional ignorado. Interface Qt exercitada com sucesso, falha e conclusão incompleta nos dois fluxos, inclusive sem mudança de pacotes; botão “Mais tarde” e ausência de reinício automático conferidos. Prévia visual Qt inspecionada; integração compartilhada de instalação limpa e Update coberta pela suíte. Nenhuma atualização administrativa ou reinicialização real foi executada.

## 3.11.0 — 2026-11-15

- Adiciona transição do menu GRUB para o wallpaper em tela cheia durante a leitura de kernel/initramfs, sem mensagens em janela preta nem espera artificial. Mantém os três segundos e as entradas de recuperação/diagnóstico.
- Anima os três pontos do Plymouth independentemente do progresso. Instalação limpa e Update usam o mesmo migrador e os mesmos assets; preserva argumentos do kernel e NVIDIA.
- A leitura bloqueante no GRUB continua com imagem estática; a animação começa quando o Plymouth inicia. Não elimina o tempo de leitura nem promete boot em três segundos no total.

Validação: 289 testes offline executados, 288 aprovados e um opcional ignorado; sintaxe Bash/GRUB e parser nativo do Plymouth conferidos. Transição do menu para wallpaper em tela cheia validada em GRUB UEFI isolado no QEMU, usando o loading.cfg da entrega. Simuladas falhas de GRUB/initramfs seguidas de retomada. Sem execução do Update no computador principal, boot completo da distribuição ou instalação Arch real; animação e integração completa aguardam teste na VM.

## 3.10.0 — 2026-11-15

- Centraliza os aplicativos distribuídos pelo Update em catálogo verificado no mesmo commit do GitHub. Compara pacotes nativos, Flatpaks e registros locais antes de aplicar adições, remoções e substituições; preserva aplicativos pessoais. A retirada de uma entrada previamente gerenciada gera remoção; entradas `absent` também alcançam máquinas anteriores ao catálogo.
- Registra CPU AMD/Intel e GPUs NVIDIA/AMD/Intel pelo inventário local, sem trocar drivers. Instala substitutos antes de remover aplicativos antigos e adia remoções de programas em uso. Confirma resultados e preserva a propriedade de instalações parciais para retomada.
- Inclui aplicativos e auxiliares instalados nos checkpoints: app removido localmente ou auxiliar alterado impede a saída antecipada, mesmo sem novo commit. A instalação limpa usa o catálogo e o executor do mesmo estágio, sem alteração no instalador ou nas cópias embutidas. Mantém o modo manual, a migração GTK e as proteções de kernel/NVIDIA.

Validação: 284 testes offline executados, 283 aprovados e um opcional ignorado; sintaxe Python/Bash e diff conferidos. Varredura real somente de leitura nesta máquina (AMD/NVIDIA), sem pendências no catálogo; demais combinações de fabricantes simuladas. Sem transações de pacotes, execução de Update completo, instalação limpa ou validação de boot nesta entrega.


## 3.9.1 — 2026-11-15

- Corrige os dois atalhos GPU Screen Recorder deixados pela migração da interface GTK para o overlay nativo. O Update remove somente `gpu-screen-recorder-gtk` quando a interface nova está instalada e a antiga está fechada; mantém motor de captura, replay, serviços e configurações. Falhas ou interface antiga em uso interrompem a etapa para nova tentativa.
- A instalação limpa continua usando somente a interface nova e o mesmo auxiliar compartilhado. A manutenção preserva explicitamente o overlay e seu pacote de notificações.

Validação: 271 testes offline executados, 270 aprovados e um opcional ignorado; sintaxe Bash/Python conferida. Remoção real apenas do pacote GTK nesta máquina, com overlay e captura/replay mantendo os mesmos PIDs; cache do menu KDE atualizado. Sem execução de Update completo, instalação limpa ou alteração de kernel/NVIDIA.


## 3.9.0 — 2026-11-15

- Torna as atualizações exclusivamente manuais pela Central. Instalação limpa, Callas OS Update e reaplicação do modo manual desativam os timers atuais e antigos, sem criar nova agenda nem reativar atualizações ao reiniciar.
- Chamadas automáticas antigas e pendentes passam a encerrar sem atualizar pacotes. Atualizações manuais não recalculam datas; históricos existentes são preservados. Mantém limpeza periódica, kernel/NVIDIA e validações dos fluxos manuais.
- Substitui Reparar agendamento por Reaplicar modo manual na manutenção. Sincroniza a cópia embutida e registra a nova política nas instruções. Backup 3.8.0 do instalador confirmado no Google Drive por SHA-256 antes da edição.


Validação: 270 testes offline executados, 269 aprovados e um opcional ignorado. Inclui chamadas automáticas antigas inertes, migração no sistema e em chroot sem reativar timers, preservação das datas históricas e notificações manuais após sucesso. Sintaxe Python/Bash e cópia embutida conferidas. Timer real desativado nesta máquina; não foi executada atualização de pacotes, instalação Arch limpa ou validação de boot.

## 3.8.0 — 2026-11-15

- Ajusta o glifo Codex da Central ao mesmo azul dos demais botões, sem fundo próprio, e corrige seu tamanho de renderização para manter proporção visual equivalente. Preserva texto, botão e ícone do aplicativo no KDE.

- Adiciona o botão Codex à Central Callas OS: baixa e instala somente após escolha do usuário; abre o aplicativo quando já instalado. O pacote é separado, fixado por commit e verificado por SHA-256 antes da execução no perfil normal. Instalação limpa e Update distribuem apenas a opção, sem baixar ou instalar o chat.
- Publica o cliente gráfico Codex 1.3.0 em `programas-callas-os/codex`, com nome e ícone Codex, login individual ChatGPT/OpenAI pelo navegador e entrada no menu KDE. Preserva IDs, preferências, fotos e histórico anteriores; não publica dados de usuários.
- Mantém acesso completo do usuário e autorização administrativa por janela sudo separada dos logs. Dependências do aplicativo usam somente a instalação pontual protegida; falhas interrompem a instalação, sem atualização geral de kernel, headers, NVIDIA ou agenda.
- Mantém o instalador principal e suas cópias embutidas intactos. A Central modificada já integra o estágio compartilhado dos dois fluxos; o pacote opcional não entra na lista de arquivos desse estágio.

Validação: testes offline da Central, instalação opcional e cliente, incluindo cancelamento, abertura sem reinstalação, SHA inválido, extração insegura, senha separada e preservação dos dados/menu. Totais e limites registrados em `codex/INTEGRACAO.md`. Sem instalação Arch limpa, login de outra conta, senha real ou boot validado.

## 3.7.0 — 2026-11-15

- Renomeia a interface para Central Callas OS, preservando o ID e os favoritos existentes. Substitui Atualizar Discord por Monitores, com submenu gráfico para detectar as telas ativas, indicar a principal atual e selecionar outra pelo mouse.
- Reaproveita o ajuste de prioridade, painel, notificações e login existente. Confirma a escolha, verifica mudanças na lista de telas e usa autorização gráfica para o login. Não altera resolução, frequência, escala ou disposição física. Mantém o atalho antigo de monitores como acesso compatível ao submenu, oculto do menu; migra seu favorito para a Central uma vez.
- Retira a execução dedicada do atualizador interno do Discord dos fluxos manuais e automáticos. A manutenção normal do pacote permanece no pacman/AUR. Não adiciona envio de arquivos ao GitHub.
- Compartilha os arquivos entre instalação limpa e Update, com cópias embutidas sincronizadas. Backup original do instalador 3.6.2 verificado no Drive por conteúdo e SHA-256 antes da edição; preserva kernel, NVIDIA e agenda.

Validação: 262 testes offline executados sem falhas, com um opcional ignorado; sintaxe de 56 arquivos Python e 9 Bash conferida. Inclui três telas simuladas, principal atual, cancelamento, seleção pelo botão, desconexão e autorização gráfica simulada. Detecção somente leitura na sessão real encontrou DP-3 e HDMI-A-1. Nenhuma troca real de monitor principal, novo login, instalação Arch limpa ou boot foi validado.

## 3.6.2 — 2026-11-15

- Corrige a transição da 3.6.0 para a 3.6.1: uma alteração apenas no próprio instalador do Callas Baterias agora atualiza somente esse auxiliar. O pacote do aplicativo não mudou entre essas versões; reinstalar e reiniciar o serviço nesse caso era desnecessário.
- Separa mudanças nos arquivos de execução, regras udev, atalhos e arquivos do perfil. Reinicia o serviço somente quando seus arquivos de execução ou unidade mudam; regras e perfil são reaplicados somente quando necessário. O log identifica os arquivos diferentes.
- Cópias e gravações preservam arquivos cujo conteúdo e permissões já correspondem à entrega. Reparar um atalho não regrava o aplicativo nem reinicia o serviço; preferências e autostart desativado continuam preservados.
- Compartilha a correção entre instalação limpa e Update, sem alterar o instalador principal, pacote do Baterias, kernel, NVIDIA ou agendamento.

Validação: 257 testes offline executados, 256 aprovados e um opcional ignorado; sintaxe de 56 arquivos Python e 8 Bash conferida. Inclui testes da alteração isolada do instalador, reparo de atalho, preservação dos tempos dos arquivos e atualização real de código simulado com reinício somente nesse caso. Comparação somente leitura na máquina confirmou que apenas o auxiliar do instalador difere da nova entrega. Nenhuma implantação administrativa, reinício real do serviço ou instalação Arch limpa foi executada.

## 3.6.1 — 2026-11-15

- Compara os arquivos globais e do perfil do Callas Baterias com a entrega verificada antes de implantar. Arquivos iguais são preservados sem reinstalação, recarga udev ou reinício do serviço, inclusive quando outro auxiliar da etapa de segurança mudou. Respeita o autostart desativado e preserva preferências.
- Registra hashes e permissões dos arquivos gerenciados de referência por etapa, além das árvores de código do Baterias e do painel. Arquivos alterados ou ausentes invalidam a etapa correspondente. Recibos antigos são renovados uma vez para registrar essa comparação.
- Reutiliza downloads em cache limitado a uma cópia por arquivo. Cada conteúdo é comparado com o blob do commit atual no GitHub antes do uso; arquivos novos, alterados ou corrompidos são baixados novamente.
- A saída antecipada por commit idêntico passa a exigir a integridade local registrada, sem ignorar reparos pendentes. Migrações explícitas de aplicativos continuam separadas de remoções arbitrárias; nenhuma troca do Discord foi feita.
- O auxiliar compartilhado atende instalação limpa e Update sem alterar instalar-arch.sh, kernel, NVIDIA ou agendamento.

Validação: 253 testes offline executados, 252 aprovados e um opcional ignorado. Inclui comparação, arquivo alterado/ausente, autostart desativado, ausência de reinstalação/reinício, reparo no mesmo commit e cache reutilizado/corrompido. Sintaxe de 56 arquivos Python e 8 Bash conferida. Sem atualização real do sistema, instalação Arch limpa ou validação de boot/hardware.

## 3.6.0 — 2026-11-15

- Adiciona interface gráfica Qt/PySide6 para o atualizador, com tema escuro, botões centralizados, ícones próprios em cada função e manutenção acessível pelo mouse.
- Mostra saída em tempo real, progresso animado por etapa e percentuais somente quando fornecidos pelo backend. Confirmações interativas usam um campo de resposta; autorização sudo ocorre em diálogo de senha separado dos logs.
- Distingue sucesso, falha e adiamento de aplicativos. Após sucesso, compara componentes críticos e o marcador de reinício para oferecer “Reiniciar agora” e “Mais tarde” no canto inferior direito. Reinício exige clique e confirmação, respeitando inibidores do systemd.
- Preserva o ID do aplicativo e substitui os acessos em Documentos, sem segunda entrada de menu. Impede instâncias concorrentes da GUI e fechamento durante uma operação.
- Distribui a mesma interface pelo estágio verificado da instalação limpa e da opção 5. A dependência PySide6, quando ausente, usa a instalação pontual protegida. Preserva o backend, cópias embutidas, instalador principal, README, limites de kernel/NVIDIA e agendamento.

Validação: 244 testes executados (243 aprovados e um opcional ignorado); sintaxe de 55 arquivos Python e 8 Bash, entrada desktop e identidade do backend embutido conferidas. Inclui testes offline de parser, comparação de componentes, resultados, pseudoterminal com resposta real sem privilégios, atalhos idempotentes e permissões com umask 077. Interface aberta na sessão KDE; nenhuma atualização real, senha real, reinício, instalação Arch limpa ou validação de hardware foi executada nesta entrega. A notificação de reinício já existente no backend geral permanece disponível.

Validação complementar da integração: 248 testes executados, 247 aprovados e um opcional ignorado. Exercita o estágio real do instalador até a implantação da GUI em árvore temporária, ambos os modos do auxiliar compartilhado, preservação do agendamento no Update, falha da implantação, checkpoint e lançadores antigos sem os novos arquivos. Mesma entrega 3.6.0, sem novo incremento. Detalhes em `INTEGRACAO-GUI.md`; instalador principal e README preservados.

## 3.5.0 — 2026-11-15

- Adiciona Callas Baterias à instalação limpa e à opção 5, pelo estágio compartilhado verificado do mesmo commit. Inclui o monitor FreeWolf F75/Attack Shark e preserva o Solaar separado para o headset.
- Corrige a escala da variante X6 `0x10`: o relatório bruto `0A` representa 100%, sem alterar firmware ou presumir a mesma escala para outras variantes.
- Agrupa Callas Baterias e Solaar imediatamente à esquerda da rede com um ajuste local do painel, sem substituir componentes do Plasma nem adicionar arraste.
- Implanta menu, serviço de usuário, início automático e permissões restritas às interfaces HID suportadas. Perfis existentes apontam ao aplicativo global; preferências e histórico são preservados. Desativar autostart cria override local e permanece respeitado nas atualizações.
- Instala PySide6 somente quando ausente, pela transação pontual protegida. Falha ou dependência incompatível interrompe a entrega; kernel, NVIDIA e agenda permanecem no escopo existente. Protege PySide6 da remoção por revisão de órfãos.
- Mantém instalar-arch.sh, cópias embutidas do atualizador/NekoFetch e README intactos. O auxiliar compartilhado já atende os dois fluxos, sem nova alteração ou backup duplicado do instalador.

Validação: 237 testes offline executados, 236 aprovados e um ignorado por transação real libalpm opcional não habilitada; sintaxe de 52 arquivos Python e 9 Bash conferida. Inclui implantação em diretórios temporários com umask 077, correspondência integral pacote/fontes, preservação do autostart desativado, falha de dependência protegida e chamada compartilhada dos dois modos. Revisão independente sem bloqueios restantes. Aplicativo e ordem da bandeja foram usados na sessão KDE do usuário; a integração administrativa não foi executada em instalação Arch limpa, VM ou outro PC. Não comprova boot, jogos ou carga elétrica real da bateria. Detalhes em baterias/INTEGRACAO.md.

## 3.4.3 — 2026-11-14

- Evita o caminho de queda identificado em `WeakSet.has()` do Qt ao abrir janelas: os scripts Callas de diagnóstico de jogos e de posicionamento dos diálogos Steam usam tabelas indexadas pelo UUID da janela, sem WeakSet/WeakMap de objetos nativos do KWin.
- Limpa os registros quando a janela é removida, preservando observação única, diagnóstico único por janela e limite de reposicionamento dos diálogos. Mantém as demais janelas e jogos sem intervenção do monitor de diagnóstico.
- Distribui os mesmos auxiliares pelo estágio verificado compartilhado da instalação limpa e da opção 5. O arquivo principal do instalador permanece intacto; a atualização recarrega os auxiliares na sessão existente sem reiniciar o KDE. Não altera pacotes, kernel, NVIDIA ou agendamento.
- Corrige somente a simulação do teste de instalação completa: imagens de kernel artificiais passam a coincidir e a leitura de initramfs artificial é simulada, sem depender da ferramenta real do host. As verificações de boot de produção permanecem intactas.

Validação: 225 testes offline aprovados e um ignorado por namespace indisponível; sintaxe de 37 arquivos Python e 9 Bash conferida. Regressões dos dois scripts executadas antes e depois da correção, incluindo UUID repetido, remoção de janela, diagnóstico único e limite de movimentos. O estágio real do instalador foi exercitado com transporte HTTP simulado e integridade dos arquivos conferida; revisão independente sem achados bloqueantes. A corrupção original do Qt não foi reproduzida; estes testes não garantem ausência futura de falhas do compositor, boot real ou funcionamento de todos os jogos/monitores. Detalhes em `diagnosticos/2026-11-14-kwin-weakset.md`.

## 3.4.2 — 2026-11-14

- Corrige a inicialização automática de Steam e Discord na instalação limpa: o bloqueio dura todo o primeiro boot, inclusive chamadas repetidas e saída/entrada na sessão KDE sem reiniciar. Ambos continuam disponíveis para abertura manual pelo menu.
- Libera o autostart somente ao detectar outro boot do sistema; o mesmo estado é compartilhado pelos dois aplicativos e protegido contra chamadas simultâneas. Depois dessa reinicialização, o autostart segue normal nos próximos boots.
- O Callas OS Update distribui o auxiliar corrigido sem armar bloqueio em perfis existentes; reparos de configuração não rearmam o bloqueio. Sincroniza a mensagem e a cópia da preparação de sessão embutida no instalador.


Validação: 223 testes aprovados e um ignorado por namespace indisponível. Inclui chamadas reais simultâneas ao auxiliar com perfil temporário e mudança simulada de boot ID; chamadas de aplicativos são substituídas por criação de arquivos temporários. Sintaxe Bash/Python e cópia embutida conferidas. Primeira sessão de uma instalação KDE real não foi executada neste ambiente.

## 3.4.1 — 2026-11-14

- Corrige o caminho indireto da opção 5 para a atualização geral: a implantação das configurações preserva as datas, os arquivos e o estado do timer existente, sem reiniciá-lo, iniciá-lo ou recalcular o vencimento mensal. Timers legados continuam sendo desativados. Instalação limpa e reparo explícito mantêm a preparação normal da agenda.
- Remove `pacman -Syu` da atualização de aplicativos nativos. Usa somente alvos explícitos, sem sincronizar o banco do sistema; adia a etapa quando há mudanças de base ou divergência entre os bancos local e isolado.
- Aplica a mesma proteção PreTransaction às instalações nativas e às transações AUR `-S`/`-U`, incluindo dependências, remoções e substituições de pacotes protegidos. Se o aplicativo exigir kernel, NVIDIA ou base protegida, a transação inteira é recusada, sem atualização geral como alternativa.
- Implanta os hooks permanentes antes de qualquer pacote ou saída `--helpers-only`. Limpa autorizações de kernel herdadas fora do comando geral e exige hooks íntegros antes da atualização geral. Não muda a NVIDIA nem executa recuperação/downgrade de kernel.
- Mantém instalador e cópia embutida do atualizador alinhados; disponibiliza a política compartilhada antes do AUR na instalação limpa. Acrescenta Haruna às verificações de presença das etapas concluídas.


Validação: 219 testes aprovados e um ignorado por user namespace indisponível. Inclui pacman 7.0.0/libalpm 15 reais em banco privado com pacotes artificiais: dependência de kernel, arquivo de kernel e substituição/remoção são bloqueados antes de qualquer instalação, enquanto o aplicativo isolado instala. O harness sem privilégios simula UID/chroot e suprime ldconfig; os pacotes só contêm arquivos temporários. Sintaxe Bash/Python e cópia embutida conferidas. Não valida um sistema Arch completo, boot, VM ou compilação NVIDIA real.

## 3.4.0 — 2026-11-14

- Adiciona o reprodutor de vídeo Haruna nativo (`extra/haruna`) à instalação limpa e ao Callas OS Update.
- Em máquinas existentes, usa a instalação pontual protegida, sem sincronização de repositórios ou atualização geral; confirma a presença do pacote e interrompe a entrega em caso de falha. Instalações existentes do Haruna são preservadas.
- Mantém as políticas existentes de kernel e NVIDIA.

Validação: 206 testes offline aprovados e um ignorado por namespace indisponível; sintaxe Bash/Python conferida. Operações de pacotes são simuladas; instalação Arch real não executada.

## 3.3.5 — 2026-11-13

- Restringe mudanças de kernel/headers em máquinas instaladas à opção 4 — Atualizar geral, incluindo o agendamento mensal existente, sem antecipá-lo. O caminho opcional Discord `--pacman` passa a usar instalação pontual protegida, sem atualização geral.
- Instala hooks PreTransaction com AbortOnFail antes dos hooks que removem módulos. Fora da opção 4, mudanças de kernel são bloqueadas; a NVIDIA fixada não pode ser substituída/removida pela transação. Remoção de kernel tem bloqueio separado.
- Com NVIDIA fixada, exige pares oficiais completos e candidatos da mesma versão, em cache após validação do pacman. Testa a compilação com a fonte instalada do driver em namespace de montagem privado e árvore DKMS temporária, sem instalar módulos. Confere versão e vermagic dos quatro módulos NVIDIA produzidos.
- Falha de build, isolamento indisponível, cache/fonte ausente, par incompleto ou alteração simultânea das ferramentas de compilação/assinatura abortam a transação inteira antes de mudar pacotes. Não troca a NVIDIA, não força build e não faz atualização parcial como alternativa. A validação final de boot continua necessária após um teste prévio aprovado.
- Sincroniza o atualizador embutido no instalador e inclui o novo auxiliar no estágio verificado, implantação e checkpoints compartilhados. Registra a política em AGENTS.md e `instrucoes/atualizacao-kernel.md`; revisa o README, mantendo a tabela de aplicativos.
- Corrige mensagem de falha do Boxes para não afirmar que um Flatpak já removido em tentativa anterior foi preservado/reinstalado.

Validação: 204 testes offline aprovados e um ignorado por user namespace indisponível; sintaxe Bash/Python, cópias embutidas e preparação verificada da instalação conferidas. Testes cobrem contextos proibidos, driver fixado, pares incompletos, locale português, mudanças de toolchain, arquivos candidatos extraídos, falha de isolamento e versão/vermagic dos módulos; comandos pacman/DKMS/namespace são simulados. Build NVIDIA contra um kernel candidato real, instalação Arch e boot não foram executados neste ambiente. O usuário confirmou a recuperação anterior no kernel 7.2.15 com NVIDIA 610.57.04; isso não equivale a validar o novo preflight em hardware real. Transações com kernel e toolchain podem permanecer bloqueadas por esta política conservadora.

## 3.3.4 — 2026-11-13

- Corrige a instalação do Boxes na opção 5: instala apenas os alvos e suas dependências usando o banco existente, sem sincronização de repositórios ou atualização geral. Um hook PreTransaction com AbortOnFail bloqueia a transação inteira se ela tentar alterar kernel, NVIDIA, boot ou componentes protegidos da base. Falha ou dependência incompatível interrompe a etapa, sem executar uma atualização geral como alternativa.
- Aplica a mesma proteção à preparação de pacotes ausentes do suporte G920/segurança na opção 5. O instalador limpo continua recebendo esses pacotes pelo pacstrap e os mesmos auxiliares pelo estágio verificado.
- Antes de remover o Boxes Flatpak e antes de concluir a entrega, verifica módulos, imagens e boot em modo somente de verificação. Uma falha em hook PostTransaction do pacman não pode mais resultar em anúncio de sucesso do Callas OS Update.
- Preserva a captura temporária e mostra seu caminho se gravar/exportar o log falhar. Não atualiza drivers, não faz downgrade automático de kernel e não tenta reparar a máquina do usuário sem diagnóstico.
- Revisão dos 14 logs e limites da recuperação documentados em `programas-callas-os/diagnosticos/2026-11-13-boxes-kernel.md`. README preservado conforme instrução do projeto.

Validação: 192 testes offline aprovados e um ignorado por user namespace indisponível; sintaxe Bash/Python e cópias embutidas conferidas. Regressões exercitam bloqueio de dependências da base antes da transação, falha de boot impedindo conclusão, imagens antigas rejeitadas e preservação da captura quando o exportador falha. Instalação Arch real, boot e recuperação do computador afetado não foram executados neste ambiente.

## 3.3.3 — 2026-11-13

- Inclui GNOME Boxes nativo na instalação limpa, com suporte a redirecionamento USB.
- A opção 5 instala e verifica o pacote nativo antes de remover o Boxes Flatpak do sistema e do usuário da atualização. Falhas de consulta, instalação ou remoção impedem a conclusão da etapa; a execução seguinte retoma a migração pendente.
- Preserva dados, configurações e discos das VMs do Flatpak, sem `--delete-data`. A importação das VMs na versão nativa permanece manual; desligue as VMs e feche o Boxes antes de atualizar.
- Identifica cada aplicativo no README como nativo ou Flatpak, indicando AUR quando aplicável. Preserva a tabela e inclui o Boxes.

Validação: 185 testes offline aprovados e um ignorado por user namespace indisponível; sintaxe Bash/Python conferida. Testes executam o bloco real da migração com gerenciadores de pacotes simulados, incluindo falhas de consulta/instalação/remoção, repetição e preservação dos dados das VMs. Instalação Arch, sessão KDE e redirecionamento USB reais permanecem pendentes de teste no computador.

## 3.3.2 — 2026-11-12

- Restaura a sequência inicial do instalador: detecção do hardware, escolha do disco e credenciais, antes da preparação de arquivos. Essa preparação integra a fase automática, com mensagem de instalação e sem banner/lista de arquivos do Callas OS Update.
- O preparador compartilhado admite progresso desativado apenas para a instalação; a opção 5 mantém o progresso detalhado e os downloads simultâneos. Hashes e sintaxe continuam validados antes de apagar o disco. As configurações atuais continuam sendo aplicadas automaticamente na instalação limpa.
- Preserva perguntas de usuário/senha (a mesma senha para usuário e root), link do instalador, organização e versão NVIDIA. Registra o contrato do fluxo inicial em AGENTS.md.

Validação: 179 testes offline aprovados e um ignorado por user namespace indisponível; sintaxe de todos os arquivos Bash/Python e cópias embutidas conferidas. Regressões reproduzem o download antes da pergunta do disco e o banner do Update na instalação; o fluxo corrigido também foi executado com entradas de disco/usuário/senha e falha simulada de preparação, sem particionar. Transporte HTTP e hardware simulados; instalação Arch e sessão KDE reais não executadas.

## 3.3.1 — 2026-11-12

- Corrige a seleção da assinatura D-Bus de `loadScript` no KWin, que interrompia a opção 5 na memória de janelas ao enviar dois argumentos para a assinatura de um. Aplica a mesma correção à captura de janelas e ao monitor de jogos.
- Prepara a atualização com até quatro downloads simultâneos, mantendo commit imutável, conferência de cada blob e validação Bash/Python antes de executar a migração. Mostra consulta, contagem de arquivos verificados e início das configurações; reduz o timeout de cada requisição de 120 para 30 segundos.
- Informa quando aguarda outra atualização e quando verifica as etapas pendentes. Preserva checkpoints, preferências do Brave aberto e a trava da NVIDIA.
- O lançador antigo ainda prepara esta primeira migração com seu código instalado; os downloads simultâneos ficam disponíveis após instalar o novo lançador.
- Instalação nova recebe os mesmos auxiliares corrigidos pela preparação compartilhada. Remove downloads redundantes de monitores/janelas no instalador e testa a cópia dos arquivos atuais, incluindo a rejeição de conteúdo adulterado antes da instalação. Complemento da mesma entrega 3.3.1, sem novo incremento.

Validação adicional do instalador: 176 testes offline aprovados e um ignorado por user namespace indisponível. A preparação/cópia dos auxiliares foi executada em diretório temporário com transporte HTTP simulado; hashes e validação de sintaxe reais. Nenhum particionamento, instalação Arch ou teste de hardware foi executado.

Validação: 174 testes offline aprovados e um teste de configuração completa ignorado por indisponibilidade de user namespace neste ambiente; sintaxe Bash/Python e identidade do atualizador embutido conferidas. Regressão reproduz a exceção D-Bus do log antes da correção. Em uma medição de preparação do mesmo commit no ambiente de desenvolvimento, o fluxo sequencial levou 6,41 s e o paralelo 1,54 s; o tempo no computador do usuário depende da conexão. Sessão KDE real, atualização Arch e hardware não foram executados aqui.

## 3.3.0 — 2026-11-12

- Prepara o Logitech G920 (Xbox) na instalação e na opção 5 do Update com `usb_modeswitch`, incluindo a regra/perfil oficial de troca automática de Xbox (`046d:c261`) para HID (`046d:c262`).
- Usa o driver nativo `hid_logitech_hidpp` para botões, pedais e force feedback, sem substituir drivers ou instalar `new-lg4ff`. Permissões de entrada ficam restritas à sessão local ativa e ao G920.
- Preserva o pacote na revisão de órfãos e reaplica a configuração quando faltar sua regra. Volante já conectado deve ser reconectado após o Update.
- Mantém fluxo automático, prompts, estrutura do instalador, NVIDIA e suporte existente ao headset/Solaar. Revisão e roteiro físico em `programas-callas-os/REVISAO-G920.md`.

Validação: 172 testes offline aprovados, incluindo dependência ausente/presente, erros de consulta/transação, configuração repetida, preservação do headset e comportamento no chroot; sintaxe Bash/Python e regra pelo `udevadm verify` aprovadas. A configuração completa do instalador foi executada em filesystem isolado com comandos Arch/hardware simulados. Funcionamento de eixos, botões, câmbio opcional e force feedback depende de teste no G920 físico e nos jogos usados.

## 3.2.2 — 2026-11-11

Correção funcional após falha de instalação limpa relatada na VM.

- Corrige o endereço dos assets ausente dentro do arch-chroot. A linha 2156 reportava o bloco externo; o ponto interno interrompia a execução após as políticas do Brave, antes das preferências, do tema e dos auxiliares finais.
- Grava o bloco de configuração em arquivo e informa a linha interna de falha. Preserva/exporta logs também na interrupção e registra instalação incompleta.
- Remove a revisão/confirmacões extras do AUR na instalação inicial. Compila sem root/sudo, com no-new-privileges; o administrador resolve dependências e instala pacotes. Não desativa checksums/PGP nem concede pacman sem senha.
- Persiste o tema Brisa Escuro sem depender de sessão gráfica. O Update distribui os auxiliares e repara as preferências visuais conhecidas do Brave fechado, preservando contas e recusando reinicializar um perfil inválido.
- Mantém a NVIDIA travada, os links e a organização do repositório.

Validação: 109 testes offline, incluindo reprodução da falha antiga e execução do bloco completo em filesystem isolado com comandos Arch/hardware simulados; sintaxe Bash/Python conferida. Não foi executada instalação Arch real, driver, boot ou sessão KDE gráfica neste ambiente.

## 3.2.1 — 2026-11-11

- Instalação limpa pula somente o primeiro início automático de Steam e Discord; abertura manual continua disponível e os próximos logins mantêm o autostart habitual.
- Atualizações e reparos em instalações existentes não reiniciam essa supressão e não removem dados de contas.
- Migração preserva o arquivo Preferences de perfis Brave existentes; não inicia o navegador para processar políticas de extensões.
- Solaar e demais autostarts continuam como antes. Configurador de monitores permanece manual, nos favoritos.

Validação: 99 testes offline e sintaxe Bash/Python aprovados. Primeiro login em sessão KDE real permanece pendente.

### Organização interna — sem alteração da versão pública

- Move VERSION e este histórico para `programas-callas-os/atualizador/`; orientações ficam em `programas-callas-os/AGENTS.md`.
- Atualiza o estágio verificado e os links da documentação para os novos caminhos. O nome VERSION dentro do estágio temporário continua igual, preservando os pontos de integração do instalador e da migração.
- Mantém a ponte histórica de atualização na raiz, necessária para clientes que ainda consultam esse endereço.
- Lançadores das versões 3.2.0/3.2.1 que já tenham sido instalados podem exigir reiniciar a migração pela ponte: eles buscavam VERSION na raiz antes de baixar o lançador novo. O bootstrap de instalações anteriores permanece disponível.

Validação: 100 testes offline e sintaxe Bash/Python aprovados; instalação e atualização em VM continuam pendentes.

## 3.2.0 — 2026-11-11

Primeira versão identificada pelo novo esquema público. Consolida segurança, manutenção, atualização geral mensal, aplicativos semanais, SteamDB no Brave e as melhorias recentes do KDE.

- Versão central em `VERSION`; instalador e Callas OS Update registram a versão concluída, referência do código e estado da migração.
- NekoFetch mostra `Callas OS v3.2.0 (Arch Linux)` na linha OS, mantendo arte, cores e demais informações. O número acompanha a versão instalada.
- Documentos contém uma única pasta `Callas OS`, com `Callas OS Logs` e `Callas OS Backups`. Migra os caminhos anteriores sem sobrescrever cópias conflitantes.
- Logs novos incluem contexto da versão; arquivos novos de backup incluem `callas-release.json`. Backups permanecem administrativos, com limite combinado padrão de 1 GB.
- Instalações com arquitetura antiga de boot recebem as etapas compatíveis, mas não são identificadas como uma migração completa para 3.2.0.

Validação: testes offline e sintaxe. Instalação limpa, atualização em VM, reinício e funcionamento no hardware ainda exigem teste real.

## Marcos anteriores — classificação retrospectiva

Os números abaixo organizam a história relatada pelo mantenedor. Não representam tags ou releases publicadas na época; datas e a posição exata da introdução do atualizador não foram reconstruídas.

| Marco proposto | Etapa |
| --- | --- |
| 1.0 | Primeiro instalador funcional, anterior ao trabalho nesta conversa |
| 1.5 | Primeiras instalações em máquina real, com systemd-boot e sem identidade visual completa |
| 2.0 | Identidade visual, wallpapers, temas e GRUB personalizado |
| 2.1 | Integração do Callas OS Update; posição cronológica aproximada |
| 3.0 | Reconstrução do GRUB para corrigir o bloco preto em instalações novas; mudança de compatibilidade |
| 3.1 | Melhorias de monitores, memória de janelas e integração ao KDE |

## Numeração futura

- `3.2.1`: correção sem nova funcionalidade.
- `3.3.0`: novas funções compatíveis.
- `4.0.0`: mudança estrutural incompatível.

Kernel, KDE, aplicativos e pacotes do Arch mantêm suas próprias versões. Uma atualização desses pacotes não muda, por si só, o número do projeto.
