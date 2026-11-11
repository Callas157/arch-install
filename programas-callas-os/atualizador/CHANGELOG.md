# Histórico do Callas OS

## 3.2.2 — 2026-11-11

- Move VERSION e este histórico para `programas-callas-os/atualizador/`; orientações ficam em `programas-callas-os/AGENTS.md`.
- Atualiza o estágio verificado e os links da documentação para os novos caminhos. O nome VERSION dentro do estágio temporário continua igual, preservando os pontos de integração do instalador e da migração.
- Mantém a ponte histórica de atualização na raiz, necessária para clientes que ainda consultam esse endereço.
- Lançadores das versões 3.2.0/3.2.1 que já tenham sido instalados podem exigir reiniciar a migração pela ponte: eles buscavam VERSION na raiz antes de baixar o lançador novo. O bootstrap de instalações anteriores permanece disponível.

Validação: 100 testes offline e sintaxe Bash/Python aprovados; instalação e atualização em VM continuam pendentes.

## 3.2.1 — 2026-11-11

- Instalação limpa pula somente o primeiro início automático de Steam e Discord; abertura manual continua disponível e os próximos logins mantêm o autostart habitual.
- Atualizações e reparos em instalações existentes não reiniciam essa supressão e não removem dados de contas.
- Migração preserva o arquivo Preferences de perfis Brave existentes; não inicia o navegador para processar políticas de extensões.
- Solaar e demais autostarts continuam como antes. Configurador de monitores permanece manual, nos favoritos.

Validação: 99 testes offline e sintaxe Bash/Python aprovados. Primeiro login em sessão KDE real permanece pendente.

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
