# Atualizador gráfico do Callas OS

Pedido: interface Qt nativa do KDE, escura, botões centralizados com ícones e progresso animado por etapa. Reutilizar funções existentes, substituir o mesmo ID de menu e os acessos em Documentos. Reiniciar agora/Mais tarde no rodapé direito após sucesso que exija reinício. Usuário autorizou continuar com essa abordagem.

Implementação nesta sessão: GUI PySide6 executa os comandos existentes em pseudoterminal, autorização sudo por diálogo separado sem registrar senha, confirmações interativas na GUI, trava contra fechar no meio de transação. Erros e adiamentos distintos de sucesso. Progresso indeterminado quando o backend não fornece percentual; percentual somente quando informado. Detecção de reinício compara versões de componentes críticos, boot ID e marcador do sistema; falha nunca oferece reinício.

Arquivos: atualizador/callas-update-gui.py (janela e processo); atualizador/callas-update-gui-install.py (implantação local/global e atalhos); assets/icons/callas-update.svg (ícone). Integração pelo estágio compartilhado callas-release.py/callas-security.sh e checkpoints de callas-update-state.py; put-update.sh e instalador permanecem idênticos. Ambos os fluxos instalam a mesma GUI após o backend. Preservar agendas, kernel/NVIDIA e limites de cada função.

- [x] Testar parser de progresso, resultados, reinício e atalhos sem executar atualizações.
- [x] Implementar GUI, autenticação isolada, execução PTY e diálogos de resposta.
- [x] Integrar implantação compartilhada e manter ID desktop existente; provisionar dependência somente via transação protegida.
- [x] Rodar testes offline e smoke Qt offscreen; instalar no perfil atual, abrir janela real sem executar transações.
- [x] Revisar entrega e registrar limites de validação; atualizar versão minor uma vez.

Validação final: 244 testes executados, 243 aprovados e um opcional ignorado; sintaxe de 55 Python e 8 Bash; desktop-file-validate e git diff --check aprovados. Instalador principal e backend embutido preservados e idênticos ao canônico. Instalação local realizada sem privilégios, GUI aberta na sessão KDE, sem executar atualizações reais.
