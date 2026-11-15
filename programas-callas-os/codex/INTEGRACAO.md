# Codex opcional — Callas OS 3.8.0 / cliente 1.3.0

O botão **Codex** da Central oferece instalação no perfil do usuário. Quando o
aplicativo já existe, o mesmo botão apenas o abre. O aplicativo é publicado em
`programas-callas-os/codex/`, separado de `instalar-arch.sh`. Nenhum pacote do
chat é incluído em `callas-release.FILES`: o estágio da instalação limpa e do
Callas OS Update distribui a Central e seu botão, sem instalar o aplicativo.

O download usa a URL de um commit imutável e o SHA-256 gravado na Central.
Antes da extração, rejeita pacotes grandes, caminhos externos, links e arquivos
especiais. O instalador roda como usuário normal. Cria venv, runtime Codex,
modelo Whisper e aplicativo sob o perfil. Dependências nativas ausentes usam
`sudo -A -- /usr/local/libexec/callas-native --install ...`, com a proteção de
toda a transação já existente. Não sincroniza bancos, não executa atualização
geral, não altera kernel/headers/NVIDIA nem agenda. Falha interrompe o processo.

O cliente passa a se chamar **Codex** e usa o glifo Codex da OpenAI também na
Central. Preserva o ID desktop, lançador e diretórios internos anteriores, para
manter favoritos, preferências, fotos e histórico. Não substitui o executável
`codex` da CLI. A entrada KDE aponta ao cliente gráfico.

Cada pessoa usa sua própria conta **ChatGPT/OpenAI**, autenticada no navegador
pelo OAuth do Codex. GitHub é a hospedagem do código/download, não o provedor de
login do chat. A conta/autenticação existente da pessoa é reutilizada quando
presente. O pacote não contém contas, tokens, conversas nem imagens de usuários.
O botão de login aparece quando a leitura de conta retorna sem autenticação.

O processo do backend continua com `approval_policy=never` e
`sandbox_mode=danger-full-access`. Acesso completo é do usuário normal; não é
root automático. O backend fornece `SUDO_ASKPASS` aos comandos filhos. O helper
abre uma janela de senha separada e devolve a resposta somente ao sudo, sem
salvar a senha ou inseri-la no chat. Cancelamento devolve erro e saída vazia.
Nenhuma regra de sudo sem senha foi adicionada.

## Verificação desta entrega

- 269 testes do Callas OS executados: 268 aprovados e um teste opcional de
  transação libalpm não habilitado. Inclui estágio compartilhado da instalação
  limpa e Update, cancelamento/confirmacão, abertura sem reinstalar, processo
  sem sudo global, remoção do contexto de atualização geral, SHA inválido,
  extração insegura e execução do pacote somente após validação.
- 52 testes do cliente aprovados. Inclui nome/ícone, login pelo navegador,
  reinstalação idempotente, preservação de fotos, entrada KDE única e helper de
  senha com confirmação/cancelamento simulados e saída isolada.
- Sintaxe de 72 arquivos Python e nove Bash conferida.
- Pacote baixado do commit público e comparado por SHA-256 e por cada arquivo
  com as fontes revisadas. Instalação real **sem dependências** em perfil
  temporário e entrada KDE validada com `desktop-file-validate`; sem copiar conta.
- `instalar-arch.sh`, `put-update.sh`, NekoFetch e README preservados. O helper
  da Central já integra o checkpoint da etapa security e os dois fluxos; não
  há nova alteração do instalador principal nem novo backup idêntico necessário.

Os testes de dependências, senha, rede defeituosa e transações são simulados.
Não foi validada instalação Arch limpa completa, download inicial de todas as
dependências/modelo em outra máquina, autenticação de outra conta, senha real,
boot ou hardware. A instalação opcional não implementa atualização automática
do chat; esse recurso fica para uma entrega posterior.
