# Queda do KWin ao observar janelas

Origem: `main` em `af2d708151543b588533a889575f5af4dd5c7cbc`, Callas OS 3.4.2.

Em 14/11/2026 às 22:53:41, o KWin 6.8.2/Qt 6.12.0 terminou com SIGSEGV
em `QV4::Value::sameValueZero`. O endereço de retorno seguinte,
`libQt6Qml.so.6 + 0x22def9`, foi identificado no binário instalado como
`QV4::WeakSetPrototype::method_has`. A pilha chega ao sinal `windowAdded`.
Os scripts Callas de diagnóstico de jogos e de diálogos Steam usam WeakSet
nesse sinal. A pilha não permite atribuir a falha a um deles individualmente.
Não foi reproduzida a corrupção original do Qt; trata-se de evitar o caminho
identificado, sem afirmar que outros crashes do compositor sejam impossíveis.

## Plano e validação

- [x] Acrescentar regressões de observação única por UUID e limpeza após remoção;
  executar os scripts gerados com coleções fracas indisponíveis e observar falha.
- [x] Substituir WeakSet/WeakMap por tabelas sem protótipo indexadas por
  `String(window.internalId)`, removidas em `workspace.windowRemoved`.
- [x] Validar os dois scripts e a distribuição dos mesmos arquivos verificados
  pelo instalador limpo e pelo Update; manter `instalar-arch.sh` intacto.
- [x] Preparar PATCH 3.4.3 e obter revisão independente sem achados bloqueantes.
- A publicação verifica novamente a referência remota e não força a main.

As fontes canônicas já pertencem ao estágio compartilhado `callas-release.py`.
O instalador instala `callas-janelas.py` desse estágio e entrega os diagnósticos
por `callas-security.sh`; a opção 5 usa os mesmos arquivos e reativa os scripts
na sessão existente. A alteração dos auxiliares não requer editar o instalador,
nem criar outra cópia idêntica de backup no Drive (AGENTS.md).

Escopo: nenhuma mudança de kernel, headers, NVIDIA, pacotes, agenda ou sessão.
Os testes com janelas simuladas não comprovam ausência futura de falhas no Qt,
boot real ou comportamento de todos os jogos/monitores.

## Falha preexistente da simulação de instalação

A suíte completa encontrou uma falha também reproduzida na main original,
extraída por `git archive`: o teste de configuração completa colocava conteúdo
`data` no kernel de boot e `kernel` no arquivo de módulos, além de chamar
`lsinitcpio` real contra um initramfs artificial. Em um host com namespaces e
ferramentas Arch disponíveis, essas verificações corretamente falhavam.
O fixture agora usa bytes coincidentes e simula apenas a listagem do initramfs.
O checker real e os testes dedicados de imagens antigas não foram alterados.

Resultado final: 226 testes executados, 225 aprovados e um ignorado por
namespace indisponível. Sintaxe de 37 arquivos Python e 9 Bash validada.
Revisão independente sem achados bloqueantes. Instalador e README preservados
byte a byte em relação à origem.
