# Varredura do Callas OS Update — 2026-11-15

Referência examinada: `main` em `2dde2f0276522a19d9ec5dbb812d9da53a8ea31d`, versão 3.9.1.

O lançador já resolvia um único commit do GitHub, verificava os blobs, reaproveitava o cache e comparava checkpoints de conteúdo antes de executar etapas. Também havia remoções específicas para GTK e Boxes. A lacuna era a ausência de um catálogo de aplicativos e de um inventário de pacotes nos checkpoints: a retirada de uma dependência da lista de instalação não significava remoção do aplicativo antigo. A verificação de integridade local também observava apenas parte dos auxiliares distribuídos.

A entrega 3.10.0 adiciona `callas-apps.json` e seu reconciliador, integra o inventário ao planejamento e à saída antecipada e amplia a observação dos auxiliares instalados. Retiradas de entradas anteriormente gerenciadas usam registros locais de propriedade; aplicativos pessoais não entram nesse conjunto. Entradas `absent` atendem instalações sem esses registros, como a migração GTK. As configurações específicas de Spotify/Boxes só são aplicadas se esses aplicativos continuarem presentes no catálogo.

A instalação limpa já prepara todos os arquivos declarados pelo `callas-release.py` remoto antes do particionamento e copia o estágio para o chroot. Ela executa `callas-security.sh --installation` desse mesmo estágio; o auxiliar agora aplica o catálogo nos três grupos. Não foi necessário alterar o instalador nem as cópias embutidas.

Validação real somente de leitura nesta máquina: CPU AMD, GPU NVIDIA, 1081 pacotes nativos e quatro aplicativos Flatpak de sistema; nenhuma ação pendente no catálogo inicial. O Flatpak pessoal extra de sistema permaneceu fora da lista gerenciada. Overlay/captura/replay mantiveram os PIDs 1341/66147/66171 durante o trabalho. Nenhuma transação de pacotes ou Update completo foi executado nesta entrega.

Validação offline: 284 testes executados, 283 aprovados e um opcional libalpm ignorado; sintaxe Python/Bash e diff conferidos. Inclui retirada do catálogo, substituição com falha, aplicativos pessoais, processos ativos, propriedade após sucesso parcial, transações protegidas, inventário com múltiplas GPUs AMD/NVIDIA/Intel, checkpoints sem novo commit e ambos os fluxos compartilhados. A detecção Intel/AMD/Arc foi simulada; não constitui teste de hardware, boot ou instalação Arch limpa.
