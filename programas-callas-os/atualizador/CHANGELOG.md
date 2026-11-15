# Histórico do Callas OS

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
