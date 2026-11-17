# Codex opcional — cliente 1.3.2

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

## Validação histórica da integração inicial (cliente 1.3.0)

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

## Cliente 1.3.1 — 2026-11-17

- Remove os dois cortes de duração do ditado. A captação inicia sem esperar
  carregar Whisper Medium; o modelo é reutilizado entre ditados. Usa busca de
  decodificação com `beam_size=1`, mantendo português e processamento local.
- Os 55 testes do cliente passam, incluindo áudio simulado de 130 segundos,
  captação independente do carregamento e reutilização do modelo. O usuário
  confirmou início mais rápido e boa transcrição na máquina dele.
- O gerador sem argumentos agora cria somente `codex.tar.gz` nesta pasta.
  Um instalador avulso só é gerado com destino explícito, quando solicitado.
  Não gera novas cópias em Documentos no fluxo de publicação.
- Fontes e pacote são publicados no GitHub; a Central fixa o commit do pacote
  e seu SHA-256. O cliente segue versão própria; o sistema permanece 3.15.0.
  Instalação continua opcional e não atualiza automaticamente clientes existentes.

Publicação: executar `python build_installer.py` nesta pasta, validar os testes
com o Python que contém as dependências de voz, conferir cada arquivo do pacote
contra as fontes e publicar na main. Em seguida fixar o commit e SHA-256 na
Central, validar seus testes e conferir o download pelo commit público. O pacote
contém somente os arquivos de distribuição definidos pelo gerador, sem dados,
contas, conversas, anexos ou modelos locais.

## Cliente 1.3.2 — 2026-11-17

- Exibe documentos anexados em cartões com ícone, nome e extensão no rascunho
  e na mensagem enviada, sem mostrar o caminho completo no corpo da mensagem.
- Mantém remoção antes do envio, conteúdo enviado e restauração após falha.
  Reconstrói os cartões ao carregar o histórico dos anexos desse cliente.
- Validação: 57 testes do cliente aprovados, incluindo remoção, envio do
  conteúdo e leitura de múltiplos anexos no histórico. Visual e envio de um
  arquivo de log confirmados pelo usuário no aplicativo local.
- Mantém a versão do Callas OS e os fluxos opcionais de instalação existentes.
