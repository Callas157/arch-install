# Atualizador gráfico: instalação limpa e Callas OS Update

Entrega pública: **3.6.0**. Integração de produção publicada no commit
`e462c4b97d0657a0f5ac17c367da25406f3e88f9`.

## Instalação limpa

1. Depois das perguntas de disco/conta/senha e antes de particionar, `instalar-arch.sh` obtém `callas-release.py` pelo commit escolhido e chama `stage_files(..., progress=False)`.
2. A lista `FILES` inclui `callas-update-gui.py` e `callas-update-gui-install.py`. A preparação confere os blobs e a sintaxe antes de copiar os arquivos ao estágio do sistema novo.
3. O instalador copia todos os arquivos preparados para `/usr/local/share/callas-os/security-stage` e, dentro do chroot, executa `callas-security.sh --installation` a partir daquele mesmo estágio.
4. O auxiliar compartilhado provisiona o backend e depois executa o instalador gráfico. PySide6 ausente só pode ser instalado pela transação pontual protegida.
5. A GUI, seu auxiliar de senha e o ícone ficam em caminhos globais. O menu e os acessos do usuário em Documentos apontam à GUI; nenhuma janela é aberta durante a instalação.

O instalador principal já executa esse fluxo compartilhado. Não foi necessário editar `instalar-arch.sh` nesta integração. Suas cópias embutidas de `put-update` e NekoFetch continuam idênticas às fontes canônicas. Não houve alteração do instalador que exigisse novo backup no Drive.

## Callas OS Update (opção 5)

O lançador prepara a mesma lista por um único commit. Lançadores antigos podem completar o estágio usando a lista da versão verificada. O conteúdo dos dois arquivos gráficos participa do checkpoint de segurança; alterações invalidam essa etapa, e arquivos globais obrigatórios ausentes também exigem sua execução.

`callas-security.sh --config-update` provisiona o backend com `--preserve-schedule` e depois instala a mesma GUI global. A etapa de ferramentas refaz os acessos gráficos após organizar os atalhos tradicionais. Os dois fluxos mantêm o ID `io.github.Callas157.AtualizadorDoSistema.desktop`, substituindo a entrada anterior sem adicionar outro aplicativo ao menu.

A opção 5 mantém seu escopo: aplicativos e configurações. Não atualiza kernel, headers ou NVIDIA nem inicia/reinicia/antecipa o agendamento geral. Uma falha na instalação da GUI interrompe a etapa e não registra conclusão.

## Validação em 2026-11-15

- 248 testes offline executados: 247 aprovados e um opcional ignorado.
- O teste do estágio real do instalador usa transporte HTTP simulado, mas executa Bash/Python, conferência de blobs, validação de sintaxe e cópias reais em diretórios temporários. Implanta exatamente a GUI copiada para o estágio e confere os atalhos finais.
- Os dois ramos do auxiliar compartilhado são executados, substituindo somente operações administrativas por comandos de teste; as gravações da GUI, ícone, auxiliar de senha e entradas desktop são reais em uma árvore temporária. O teste confirma o mesmo arquivo gráfico nos dois modos e `--preserve-schedule` somente no Update.
- Regressões verificam falha da implantação, invalidação de checkpoint e expansão do estágio de um lançador antigo sem os novos arquivos gráficos.
- Sintaxe Bash/Python, `git diff --check` e identidade das duas cópias embutidas conferidos.

Esses testes não executam uma instalação Arch completa, particionamento, atualização real, reinício nem validação de boot/NVIDIA em hardware ou VM. A interface foi aberta na sessão KDE na entrega original.
