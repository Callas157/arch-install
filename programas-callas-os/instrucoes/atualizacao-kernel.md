# Seleção e atualizações de kernel e NVIDIA

Leia junto com [AGENTS.md](../AGENTS.md) e [versionamento.md](versionamento.md).

## Escopo que não pode ser ultrapassado

Leia a seção “Regra obrigatória: cada opção respeita seu escopo” em [AGENTS.md](../AGENTS.md) antes de alterar qualquer fluxo. **A opção 5 — Callas OS Update só atende aplicativos (adição/remoção autorizada) e configurações do Linux/Callas OS. Não altera pacotes de kernel, headers ou driver NVIDIA**, inclusive reinstalação, remoção, substituição e downgrade. Uma dependência incompatível interrompe a transação; não autoriza atualização geral, troca do driver ou ativação/antecipação do agendamento.

A instalação limpa usa Linux **7.2.15.arch1-1** com os headers correspondentes do Arquivo do Arch e Linux LTS com headers dos repositórios atuais. O kernel principal é a primeira opção do GRUB e inicia após três segundos. O LTS fica em segundo. Em GPUs compatíveis, a versão inicial é NVIDIA Open DKMS **610.57.04**. Os pacotes arquivados e suas assinaturas são verificados antes de formatar. A série 7.2 encerrou o suporte upstream.

## Troca manual na Central

- **Kernel Linux** mostra o kernel em uso e as versões instaladas. A seleção troca `linux` e `linux-headers` juntos. Escolha uma versão anterior para reverter e selecione **Callas OS Linux** no GRUB para iniciá-la.
- **Driver NVIDIA** verifica a GPU pelo barramento PCI, confere a pilha assinada e testa os módulos nos dois kernels. A ação **Reparar versão instalada** recompila os módulos da versão atual.
- Se a listagem do Arquivo do Arch estiver indisponível, digite a versão do kernel no formato do pacote, como `7.2.15.arch1-1`, ou a versão do driver, como `610.57.04`. A instalação depende dos pacotes e assinaturas correspondentes.
- Os seletores preparam os pacotes anteriores antes de aplicar a troca e tentam restaurá-los se houver falha depois que os pacotes mudarem. O Callas OS Update migra os blocos `IgnorePkg` antigos do projeto.

A opção **4 — Atualizar geral** também pode atualizar os pares de kernel/headers. Ela preserva a escolha da NVIDIA nessa transação. As ações da Central são manuais. Os agendamentos antigos permanecem desativados.

## Antes da transação

O hook `00-callas-kernel-policy.hook` recebe todos os alvos, usa PreTransaction, NeedsTargets e AbortOnFail, e roda antes dos hooks que removem módulos. O comando geral e os seletores exigem antes `callas-kernel-policy --check-hooks`: auxiliar e hooks precisam existir, pertencer a root, ter permissões seguras e corresponder às definições esperadas. A transação usa explicitamente o diretório desses hooks. Só o comando oficial da opção 4 recebe `CALLAS_KERNEL_UPDATE_CONTEXT=general`; não exporte essa autorização globalmente nem para o AUR.

O teste com NVIDIA exige pares oficiais completos (`linux` e `linux-headers`, ou `linux-lts` e `linux-lts-headers`) na mesma transação. As versões do kernel e dos headers devem coincidir. Na atualização geral, os pacotes candidatos vêm do cache do pacman. A seleção manual usa pacotes locais assinados como alvos da transação; metadados são consultados em locale C, independentemente do idioma do sistema.

O teste extrai dados dos pacotes em diretório temporário, sem executar scripts de instalação. Um namespace de montagem privado usa a árvore candidata apenas naquela visão de `/usr/lib/modules`, mantém `/usr/src` somente leitura e direciona a árvore DKMS para a área temporária. Executa `dkms add` e `dkms build`, não `dkms install`. Os quatro módulos produzidos devem informar a versão NVIDIA instalada e o vermagic candidato.

Falha no build, pacote/fonte/ferramenta ausente, par incompleto, kernel não suportado ou impossibilidade de criar isolamento bloqueiam a transação inteira. Se DKMS, compiladores ou bibliotecas/ferramentas de build/assinatura também forem mudar, a transação é bloqueada: não é seguro aprová-la com o ambiente anterior. Não contorne isso com atualização parcial da base ou troca do driver.

Esse bloqueio pode manter a atualização geral pendente nas tentativas seguintes, pois os mesmos pacotes continuam na fila. Uma solução futura precisaria validar também o ambiente de compilação candidato ou adotar outra estratégia completa revisada. Não anuncie que o modo geral sempre conseguirá atualizar nem remova a proteção para destravá-lo.

O hook separado `00-callas-kernel-deny-remove.hook` impede interpretar remoção como atualização. Os hooks são proteções operacionais; não impedem um administrador root de editar a política deliberadamente.

## Depois da transação

A compilação prévia prova compatibilidade naquele ambiente, não garante sucesso contra falta de disco, interrupções ou outras falhas posteriores. Os artefatos de teste são temporários; o DKMS normal prepara os módulos instalados. Preserve a validação final de módulos, initramfs e GRUB e o bloqueio de conclusão/reinício quando houver erro.

O diagnóstico prévio fica em `/var/lib/callas-os/kernel-preflight-last.log`, com registro na categoria Kernel Linux quando o exportador estiver disponível. Logs e backups seguem os caminhos e limites existentes.

## Revisão e publicação

- Faça o backup anterior no Drive antes de editar o instalador.
- Procure comandos pacman/Paru/AUR em todos os modos, inclusive Discord `--pacman`, hooks e agendamento.
- Mantenha `put-update.sh` e sua cópia embutida idênticos; distribua helper e hooks pela instalação limpa e pelo Update com estágio verificado e checkpoints.
- Teste contextos proibidos, driver fixado, pares incompletos, falha de namespace/build, locale português, módulos incorretos e bloqueio antes da transação. Diferencie simulação de compilação/boot real.

## Aplicativos e configurações: isolamento obrigatório

- Por pedido explícito do usuário em 2026-11-15, instalação limpa, opção 5 e reaplicação do modo manual desativam os timers atuais e antigos. Não criam novos timers nem recalculam datas históricas. `--preserve-schedule` permanece aceito por compatibilidade, sem preservar timers ativos. Chamadas automáticas antigas encerram sem atualizar pacotes.
- A opção de aplicativos nunca usa `pacman -Syu`, `-Sy` ou `--sysupgrade`. Compara a consulta isolada com o banco local; divergência ou mudança de base adia a fase. Não sincroniza o banco real para tentar uma atualização parcial.
- Todos os caminhos nativos e AUR `-S`/`-U` usam `callas-native.guarded_transaction`, com hook temporário próprio cobrindo Install, Upgrade e Remove, `Target = *`, NeedsTargets e AbortOnFail. Conferir só os nomes pedidos não cobre dependências e substituições. Os hooks permanentes são implantados antes de pacotes e antes da saída `--helpers-only`.
- Autorizações herdadas de atualização geral são descartadas nos pontos de entrada. Uma dependência protegida deve interromper a transação inteira. Não execute atualização geral como fallback para instalar Haruna, Boxes, Spotify, Discord ou qualquer outro aplicativo.
- O teste opcional `test_pacman_transaction.py`, habilitado por `CALLAS_TEST_PACMAN`, valida transações reais do libalpm com banco privado e pacotes artificiais que só escrevem no diretório temporário. Cobre dependência de kernel, arquivo de kernel e aplicativo que remove/substitui um kernel. Não instala kernels reais nem valida boot/NVIDIA.
