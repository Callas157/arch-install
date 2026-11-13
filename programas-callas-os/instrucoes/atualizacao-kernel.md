# Atualizações de kernel com NVIDIA fixada

Leia junto com [AGENTS.md](../AGENTS.md) e [versionamento.md](versionamento.md).

## Autorização

A opção **4 — Atualizar geral** é o único fluxo do projeto que autoriza atualizar kernels/headers em um sistema instalado. O agendamento mensal usa esse caminho e não pode ser antecipado por atualizações de aplicativos ou pela opção 5. Opção 2, Discord, AUR e instalação pontual não autorizam alterações de kernel.

A NVIDIA permanece na versão escolhida pelo usuário, atualmente **610.57.04**. Não a atualize para contornar incompatibilidade de kernel. O instalador limpo provisiona o sistema inicial com os auxiliares compartilhados do mesmo commit; não executa a interface da opção 5 e não pode anunciar conclusão se a NVIDIA fixada ou o boot falharem.

## Antes da transação

O hook `00-callas-kernel-policy.hook` recebe todos os alvos, usa PreTransaction, NeedsTargets e AbortOnFail, e roda antes dos hooks que removem módulos. Só o comando oficial da opção 4 recebe `CALLAS_KERNEL_UPDATE_CONTEXT=general`; não exporte essa autorização globalmente nem para o AUR.

Com NVIDIA fixada, exige pares oficiais completos (`linux` e `linux-headers`, ou `linux-lts` e `linux-lts-headers`) na mesma transação. As versões do kernel e dos headers devem coincidir. Pacotes precisam estar disponíveis no cache após validação de assinatura/integridade pelo pacman; metadados são consultados em locale C, independentemente do idioma do sistema.

O teste extrai dados dos pacotes em diretório temporário, sem executar scripts de instalação. Um namespace de montagem privado usa a árvore candidata apenas naquela visão de `/usr/lib/modules`, mantém `/usr/src` somente leitura e direciona a árvore DKMS para a área temporária. Executa `dkms add` e `dkms build`, não `dkms install`. Os quatro módulos produzidos devem informar a versão NVIDIA fixada e o vermagic candidato.

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
