# Roteiro de versionamento para agentes do Callas OS

Leia este roteiro no início de cada tarefa e retomada, junto com [AGENTS.md](../AGENTS.md). As regras normativas ficam em AGENTS.md; este arquivo organiza sua aplicação. As instruções ficam no repositório para serem consultadas em outros chats, sem depender da memória do agente.

## 1. Estabelecer a referência atual

- Consulte a `main` remota de `Callas157/arch-install` e registre seu commit.
- Examine a árvore do repositório, as instruções e os arquivos relacionados ao pedido.
- Leia [VERSION](../atualizador/VERSION) e o [CHANGELOG](../atualizador/CHANGELOG.md) na mesma referência remota.
- Não parta de uma versão lembrada de outro chat ou de um checkout desatualizado.

## 2. Identificar a entrega e decidir o incremento

Uma entrega pode conter vários commits. Verifique primeiro se ela já recebeu um incremento. Corrigir ou complementar a mesma entrega não cria automaticamente outro incremento.

| Maior impacto da entrega | Ação |
| --- | --- |
| Apenas documentação ou organização de pastas | Manter a versão |
| Correção de bug | Aumentar PATCH |
| Novo recurso compatível com instalações existentes | Aumentar MINOR e zerar PATCH |
| Mudança incompatível que exige migração especial ou reinstalação | Aumentar MAJOR e zerar MINOR e PATCH |

Exemplos: `3.2.2 → 3.2.3` para correção; `3.2.3 → 3.3.0` para recurso compatível; `3.3.0 → 4.0.0` para mudança incompatível.

Considere o conjunto da entrega, não o número de arquivos, commits ou pacotes. Atualizar pacotes comuns do Arch, kernel ou aplicativos não aumenta a versão do Callas OS. Classifique uma alteração do projeto pelo comportamento entregue; não use a troca de um aplicativo como regra automática para todas as entregas futuras.

Se a versão remota já for `3.4.1`, uma nova correção será `3.4.2`, mesmo que você lembre de `3.2.2`. Não reduza a versão nem compense incrementos anteriores. Uma instrução explícita para manter uma versão é uma exceção apenas para aquela entrega.

## 3. Preparar e validar

- Quando houver incremento, atualize VERSION e o CHANGELOG correspondente uma única vez.
- Não edite o README sem solicitação.
- Preserve instalador, Callas OS Update, NekoFetch, logs e backups. Verifique os fluxos afetados tanto na instalação limpa quanto na atualização.
- A identidade instalada só avança após as etapas obrigatórias concluírem com sucesso. Falhas não podem anunciar a versão de destino como instalada.
- Mantenha versão pública, revisão interna por data e commit como identificadores separados.
- Execute a validação apropriada à mudança e diferencie testes simulados de testes reais no sistema ou hardware. Documentação isolada exige revisão de coerência e links, sem criar testes que apenas repetem seu texto.

## 4. Conferir novamente e publicar

- Consulte novamente o commit e VERSION na `main` remota.
- Se outro agente publicou alterações, releia VERSION e o CHANGELOG e reconcilie a entrega antes de publicar.
- Verifique se o incremento já foi aplicado e não aumente a versão uma segunda vez.
- Publique diretamente na `main`, nos caminhos existentes, conforme a orientação do projeto. Não crie branches ou pull requests sem pedido explícito e não force a referência para contornar concorrência.
- Confira os arquivos publicados e a versão remota após a publicação.

## 5. Usar a versão correta em backups, inclusive no Google Drive

Quando um backup for solicitado, consulte as instruções e a estrutura de pastas já adotadas para esse destino antes de criar pastas. Este roteiro não autoriza criar ou enviar backups por conta própria.

- Para backup do código de uma entrega, identifique a versão pelo VERSION do commit efetivamente copiado e registre também esse commit.
- Para backup de um sistema instalado, use a identidade efetivamente registrada por `callas-version`, incluindo o estado de uma migração pendente ou incompleta. Não use a versão remota de destino como se já estivesse instalada.
- Use esses dados ao escolher a pasta de versão prevista na organização existente. Não invente uma versão para um backup antigo, renomeie arquivos históricos ou sobrescreva colisões.
- Versão, commit e data têm funções diferentes: vários backups podem pertencer à mesma versão. Preserve as regras existentes de nomes, retenção, permissões e localização.
