# Callas Baterias no Callas OS — plano de implementação

Objetivo: distribuir o aplicativo já validado no PC do usuário, incluindo a escala do X6 e a ordem fixa da bandeja, pela instalação limpa e opção 5.

Arquitetura: pacote autocontido em baterias/, auxiliar administrativo não interativo e integração em callas-security.sh, já executado pelos dois fluxos com arquivos do mesmo commit verificado. Não alterar instalar-arch.sh, README, kernels, NVIDIA ou agenda. Incrementar uma única vez de 3.4.3 para 3.5.0.

- [x] Escrever regressões para pacote corrigido, dependência protegida, instalação em perfil novo/existente, permissões e preparação pelos dois fluxos.
- [x] Empacotar aplicativo/licença/ajuste QML sem preferências nem cache pessoal; implantar arquivos globais e configurar o perfil com os privilégios do usuário.
- [x] Integrar estágio verificado, checkpoint de segurança, dependência pyside6 protegida e preservação contra limpeza de órfãos.
- [x] Rodar suíte offline completa, sintaxe e verificar instalador/updater embutido intactos; registrar limites da validação.
- [ ] Reconsultar main/VERSION, publicar diretamente na main sem force e conferir o conteúdo remoto.

Falhas a cobrir: pacote inseguro ou ausente; dependência recusada; perfil existente com versão local; ausência de sessão gráfica durante chroot; máquina sem dispositivos suportados. A ordem dos ícones é um ajuste local, sem alterar o Plasma do sistema; Solaar é preservado.

Revisão: corrigidos diretórios sob umask077 e override de autostart global; 11 regressões específicas aprovadas. Suíte final: 236 aprovados/1 ignorado, sintaxe Python/Bash válida. Publicação é a etapa restante.
