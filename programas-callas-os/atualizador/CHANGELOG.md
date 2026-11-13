# Histórico do Callas OS

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
