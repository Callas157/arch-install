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

## 3. Fazer o backup obrigatório antes de alterar o instalador

Antes de editar `instalar-arch.sh`, execute o procedimento da seção 6. O backup deve conter o instalador anterior da main, obtido por commit imutável. Só comece a implementação após verificar a cópia no Drive. Não adie esse passo para depois da edição ou da publicação. Se o backup falhar, interrompa a alteração do instalador.

## 4. Preparar e validar

- Quando houver incremento, atualize VERSION e o CHANGELOG correspondente uma única vez.
- Não edite o README sem solicitação.
- Preserve instalador, Callas OS Update, NekoFetch, logs e backups. Verifique os fluxos afetados tanto na instalação limpa quanto na atualização.
- A identidade instalada só avança após as etapas obrigatórias concluírem com sucesso. Falhas não podem anunciar a versão de destino como instalada.
- Mantenha versão pública, revisão interna por data e commit como identificadores separados.
- Execute a validação apropriada à mudança e diferencie testes simulados de testes reais no sistema ou hardware. Documentação isolada exige revisão de coerência e links, sem criar testes que apenas repetem seu texto.

## 5. Conferir novamente e publicar

- Consulte novamente o commit e VERSION na `main` remota.
- Se outro agente publicou alterações, releia VERSION e o CHANGELOG e reconcilie a entrega antes de publicar.
- Verifique se o incremento já foi aplicado e não aumente a versão uma segunda vez.
- Publique diretamente na `main`, nos caminhos existentes, conforme a orientação do projeto. Não crie branches ou pull requests sem pedido explícito e não force a referência para contornar concorrência.
- Confira os arquivos publicados e a versão remota após a publicação.

## 6. Backup do instalador no Google Drive

O usuário autorizou permanentemente este procedimento para cada atualização do instalador, incluindo criação das cópias e retenção de até **10 backups**. Não é necessário solicitar autorização novamente.

### Destino e identificação

- Use a pasta existente [CallasOS](https://drive.google.com/drive/folders/1gGvO2rTC4Y0iH1R5BosbWsJH8fwxaMgm), ID `1gGvO2rTC4Y0iH1R5BosbWsJH8fwxaMgm`; confirme acesso e identidade do destino antes de escrever.
- A pasta de cada backup deve ter o nome `CallasOS X.Y.Z`, com a versão anterior lida em VERSION na main remota, não a versão planejada para a atualização.
- Há uma pasta existente chamada `CallasOS 3.3.2`. Sua existência não prova que o arquivo do instalador esteja salvo ou íntegro; verifique o conteúdo antes de reutilizar qualquer backup.
- Não invente versões, renomeie históricos ou sobrescreva cópias anteriores. Se a mesma versão corresponder a outro conteúdo, acrescente data/hora ao nome: `CallasOS X.Y.Z — AAAA-MM-DD HH-mm-ss`, horário de São Paulo. Cada cópia conta para o limite de 10.

### Sequência obrigatória

1. Consulte a main atualizada e fixe o commit de origem.
2. Leia VERSION e obtenha `instalar-arch.sh` daquele mesmo commit. Use os bytes originais do GitHub, não um arquivo local já modificado.
3. Confira os backups existentes. Uma cópia íntegra do mesmo instalador/commit pode ser reutilizada após verificação; não crie duplicatas desnecessárias.
4. Se não houver cópia verificada, crie a pasta de versão dentro de CallasOS e salve `instalar-arch.sh`. Inclua um registro de versão, commit de origem, data/hora e SHA-256.
5. Leia o arquivo salvo pelo conector do Drive e confira seu SHA-256 contra o original. Confirme também seu nome e a pasta de destino. Não considere apenas a criação da pasta ou o retorno inicial do envio como sucesso.
6. Após confirmar o novo backup, aplique a retenção abaixo.
7. **Somente agora edite e implemente a atualização no instalador.** Mantenha o backup da versão anterior intacto.
8. Valide a entrega. Antes de publicar, releia a main remota; se o instalador remoto mudou por ação concorrente, faça e verifique o backup dessa nova origem antes de reconciliar e publicar.
9. Confira os arquivos publicados na main. Não crie branches ou pull requests sem solicitação.

Se faltar acesso ao Drive, ocorrer falha de envio ou não for possível verificar a integridade, pare a alteração do instalador e informe o bloqueio. Não publique primeiro para tentar fazer o backup depois.

### Retenção: no máximo 10 backups

- Conte apenas pastas de backup do instalador devidamente identificadas dentro de CallasOS; preserve outros conteúdos.
- O novo backup conta no limite de 10. Ordene os backups pela data real de captura registrada; não ordene versões como texto.
- Envie à lixeira somente os backups mais antigos necessários para voltar ao limite de 10, após confirmar o novo backup. Não use exclusão definitiva.
- Nunca remova a cópia anterior antes de concluir e verificar o envio da próxima.
- Se não for possível identificar com segurança os backups antigos ou cumprir a retenção, informe o bloqueio e resolva-o antes de prosseguir com a atualização.

### Relação com versão e backups locais

Documentação isolada, sem mudança do instalador, não exige duplicar um backup idêntico nem aumentar a versão pública. A criação de um backup também não incrementa VERSION.

Para backups de um sistema instalado, use a identidade efetivamente registrada por `callas-version`, incluindo estado pendente ou incompleto, e não a versão remota de destino. Preserve as regras locais existentes de nomes, permissões, localização e retenção; o limite de 10 desta seção aplica-se aos backups do instalador no Drive.
