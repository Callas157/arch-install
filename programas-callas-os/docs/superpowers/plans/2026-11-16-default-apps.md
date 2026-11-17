# Aplicativos padrão na Central — plano

Objetivo: transformar Aplicativos nativos em um submenu com atualização dos instalados e restauração seletiva dos aplicativos comuns distribuídos na instalação limpa. A lista abre dentro do próprio submenu, com cartões, ícones, versão, tamanho e seleção sem terceira janela de navegação. Confirmações e autorização administrativa permanecem modais.

Arquitetura: catálogo verificado existente mantém applications (reconciliação automática) e recebe defaults (somente oferta explícita de restauração). Executor callas-defaults usa o catálogo instalado, valida todos os IDs antes de atuar, mantém os locks da Central/catálogo e reaproveita transações protegidas nativas/AUR/Flatpak. Só instala selecionados; confirma cada resultado e então limpa a preferência local de remoção desse aplicativo. Não atualiza bases pacman nem kernel/NVIDIA. Falhas parciais preservam os resultados já confirmados e as demais escolhas. UI Qt permanece responsiva por QProcess e consulta metadados sem privilégios. Ícones preparados nos assets e distribuídos pelo estágio compartilhado.

- [x] Testes de restauração seletiva, validação integral, falha parcial, proteção e preferências.
- [x] Catálogo defaults e executor com metadados locais/remotos limitados e erros explícitos por cartão.
- [x] Submenu Qt na mesma janela, cartões com ícones e seleção, botões verdes e progresso/logs.
- [x] Distribuição compartilhada para instalação limpa/Update e checkpoints de helpers/assets.
- [x] Testes Qt, suíte offline, sintaxe, prévia visual e revisão independente.
- [x] Preparar versão 3.13.0, changelog e entrega validada para publicação atômica na main; conferir a referência remota ao publicar.

Escolhas de implementação: atualizar mantém o fluxo nativos existente; restaurar não é atualização geral. Tamanho do pacote e tamanho instalado são rotulados separadamente, sem prometer incluir dependências. Sem Discord/convite. Nenhuma alteração do instalador principal é necessária se a integração compartilhada for confirmada.
