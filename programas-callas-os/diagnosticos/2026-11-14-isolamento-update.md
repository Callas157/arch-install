# Revisão do isolamento do Callas OS Update — 2026-11-14

Origem revisada: `0160e83936fd86ae3d33b4e79b4846efa4770455` (3.4.0).
O usuário relatou que a VM passou de 7.2.15 para 7.3.4 após usar o Update.
Sem o log dessa transação, esta revisão identifica caminhos do código; não
atribui o evento da VM a um comando específico nem tenta recuperação automática.

## Caminhos encontrados e corrigidos

1. Opção 5 → `callas-security --config-update` → `put-update --instalar-para`
   reinstalava/reiniciava `put-update-check.timer`. `OnBootSec=2min` já vencido
   pode provocar verificação imediata. O worker aguarda o lock do Update e
   executa a atualização geral se a agenda mensal estiver vencida. A implantação
   de configurações agora usa `--preserve-schedule`: preserva datas, unidades
   e estado do timer, sem iniciar/reiniciar ou recalcular datas.
2. A opção de aplicativos nativos usava `-Syu` sob um hook temporário. Agora
   somente solicita alvos explícitos e não sincroniza o banco real. Se houver
   alteração de base ou diferença entre banco local e consulta isolada, adia.
3. O AUR inicial (também usado pelo Spotify na opção 5) usava `-S`/`-U` sem
   o bloqueio temporário compartilhado. O AUR de manutenção tinha uma lista
   protegida menor e confiava no hook permanente. Ambos agora usam a mesma
   política sobre a transação efetivamente resolvida, incluindo Remove.
4. Os hooks permanentes só eram instalados depois das dependências de
   segurança, e `--helpers-only` não os instalava. Foram antecipados.
5. Atualização geral supunha hooks existentes. Agora exige `--check-hooks`
   antes de chamar pacman e fornece o diretório verificado explicitamente.
6. O bootstrap direto podia herdar contexto `general`. Os pontos de entrada
   não gerais descartam/substituem essa autorização.
7. O checkpoint de aplicativos não verificava a presença do Haruna. Incluído.

O bloco Haruna original já usava instalação pontual protegida; não continha
`-Syu`. A revisão anterior desse bloco e os testes simulados não cobriam o
efeito indireto do reinício do timer nem todos os caminhos AUR.

## Cobertura da revisão

Foram percorridos menu, opções manuais, Discord, agendamento semanal/mensal,
bootstrap e estágio por commit, checkpoints, implantação de auxiliares,
provisionamento de dependências, instalações AUR iniciais e manutenção AUR,
hooks Pre/PostTransaction e validação de boot. Storage/logs/versionamento
foram conferidos quanto às chamadas externas: não iniciam upgrades. A
manutenção automática limpa cache/logs; a remoção manual de órfãos exige sua
própria confirmação e não é chamada pela opção 5. O instalador conserva seu
provisionamento inicial e recebe a mesma política antes dos aplicativos AUR.

Kernel, headers e NVIDIA de máquinas existentes não são instalados como
requisito da etapa de segurança. A atualização geral mensal/opção 4 mantém
seu fluxo separado e não é chamada como fallback de aplicativos.

## Verificação e limites

219 testes aprovados, um ignorado por namespace indisponível. A suíte inclui
execução real do pacman 7.0.0/libalpm 15 com banco privado e pacotes artificiais
que escrevem só no diretório temporário. Um harness sem privilégios simula
UID/chroot e suprime ldconfig; resolução, hooks e commit do libalpm são reais.

As transações de dependência de kernel, arquivo de kernel e aplicativo comum
que remove/substitui o kernel são recusadas integralmente. O pacote anterior
continua 7.2.15 e o novo aplicativo não é instalado; um aplicativo sem alteração
protegida instala. A preservação de agenda vencida/unidades é exercitada por
Bash real com systemctl simulado. Sintaxe e cópia embutida conferidas.

Isso não valida um Arch completo, a VM do usuário, boot físico ou compilação
NVIDIA real. Nenhum downgrade ou reparo da máquina do usuário foi executado.
