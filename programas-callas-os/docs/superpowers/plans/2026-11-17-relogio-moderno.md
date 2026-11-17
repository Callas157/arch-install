# Relógio Moderno Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans para execução nesta sessão. As instruções do repositório autorizam trabalho direto na main.

**Goal:** Corrigir a ordem da lista de monitores e oferecer o relógio com instalação e posicionamento pela Central.

**Architecture:** Auxiliar pessoal administra um pacote Plasma local verificado e posiciona instâncias via D-Bus. A Central reaproveita a lista de padrões e uma página interna para todos os monitores. A instalação limpa prepara o relógio no primeiro login; o Update apenas distribui a oferta.

**Tech Stack:** Python, PySide6, Plasma 6, Bash, QML.

**Spec:** ../specs/2026-11-17-relogio-moderno-design.md

## Global Constraints

- Preservar configuração/posição existente e arraste livre.
- Sem alteração automática da área de trabalho desta máquina durante o desenvolvimento.
- Widget opcional em máquinas existentes; padrão somente na instalação limpa.
- Preservar kernel, NVIDIA, instalador e README. Auxiliares compartilhados já atendem o instalador.

## Review Focus

- Múltiplas telas e mudança de conectores: validar novamente o destino antes de mover.
- Instância existente: preservar aparência, não duplicar no login ou Update.
- Pacote local: recusar ZIP com traversal, links ou identidade inesperada.
- Sessão Plasma indisponível: preservar pendência e informar falha sem anunciar posição aplicada.
- Atualizador histórico: incluir auxiliar e payload no estágio completo e checkpoints.

### Task 1: Layout de monitores

**Files:** atualizador/callas-update-gui.py; tests/test_update_gui.py.
**Interfaces:** MonitorDialog.choices permanece uma lista; título, lista, mensagem, ações agrupados no topo.

- [x] Adicionar teste Qt que verifica a ordem e distância entre título, lista e mensagem na janela alta; executar e observar falha.
- [x] Corrigir ordem e inserir expansão somente após os controles; executar testes Qt.

### Task 2: Auxiliar e catálogo

**Files:** atualizador/callas-widget.py; atualizador/callas-defaults.py; atualizador/callas-apps.json; relogio/relogio-moderno.plasmoid; tests/test_widget.py; tests/test_defaults.py.
**Interfaces:** callas-widget --install, --screens, --move CONNECTOR CORNER, --edit, --first-login; defaults usa identidade plasmoid:com.github.prayag2.modernclock.

- [x] Adicionar testes de extração segura, preservação, scripts executados em motor JS e oferta opcional; observar falhas.
- [x] Implementar instalação pessoal, detecção Qt, criação/movimento via API Plasma e marca de primeiro login só na instalação limpa.
- [x] Integrar metadados/instalação de plasmoid na oferta de padrões sem entrar em applications; executar testes.

### Task 3: Central e distribuição

**Files:** atualizador/callas-update-gui.py; atualizador/callas-security.sh; atualizador/callas-release.py; atualizador/callas-update-state.py; tests/test_widget_gui.py; tests/test_stage_compatibility.py; instrucoes/catalogo-aplicativos.md.
**Interfaces:** cartão com botões lado a lado; página interna com quatro cantos por tela, chamada pessoal a callas-widget; preparação compartilhada --prepare-clean USUARIO só em --installation.

- [x] Adicionar testes de navegação, cliques por conector/canto, instalação sem sudo e separação clean/Update; observar falhas.
- [x] Implementar interface e entrega dos arquivos pelo estágio verificado; conferir instalação limpa sem editar instalar-arch.sh.
- [x] Executar suíte offline, sintaxe e prévias Qt; revisar diff e preservar limitações de hardware.
- [x] Incrementar MINOR uma vez, escrever changelog e revisar main remota.

Publicação: executar após a validação acima, diretamente na main, e conferir VERSION e blobs públicos.
