# Relógio Moderno na Central Callas OS

Aprovado com esclarecimentos do usuário em 2026-11-17. Referência consultada: main remota, Callas OS 3.15.1.

## Comportamento solicitado

- Manter a seção Monitores. Organizar seu conteúdo como título “Definir monitor principal”, opções das telas e mensagem explicativa abaixo das opções. Conferir alinhamento, espaçamento e textos da lista.
- Adicionar Relógio Moderno em Aplicativos nativos → Aplicativos padrão Callas OS, com Instalar e Configurar lado a lado. Ajustar o cartão para acomodar ambos sem cortar textos ou prejudicar os demais cartões.
- Configurar abre uma página interna da mesma Central, com retorno à lista. Exibir a representação do monitor com quatro quadrados clicáveis, um por canto. Mostrar cada monitor detectado (Monitor 1, Monitor 2, Monitor 3…), cada um com seus quatro cantos, dentro da mesma página.
- Permitir abrir o modo de edição do Plasma para arrastar e redimensionar livremente. Não reaplicar um canto automaticamente após movimentação manual.
- Adicionar o relógio por padrão somente na instalação limpa. Em máquinas existentes, o Update disponibiliza os arquivos e a opção na Central, sem instalar ou adicionar o relógio sem escolha explícita. Reexecuções não duplicam o widget nem apagam sua configuração existente.

## Decisões propostas

- Nome do cartão: Relógio Moderno. Reutilizar o plasmoid anexado e a infraestrutura Python/Qt da Central.
- Posição inicial: canto superior esquerdo da segunda tela ativa quando houver duas; na ausência dela, usar a tela principal. Essa regra é apenas o padrão inicial, não uma posição forçada a cada login ou Update.
- Manter o identificador interno do pacote, `com.github.prayag2.modernclock`, e reconhecer instâncias existentes. A pasta do anexo usa outro nome; normalizar o empacotamento sem criar uma segunda identidade do relógio.
- Configurar fica disponível após a instalação. Se o pacote já estiver instalado sem instância na área de trabalho, a configuração permite adicionar uma única instância no destino escolhido.
- Preservar a aparência do anexo e o dia da semana em português; não substituir configurações pessoais existentes.

## Abordagens

Recomendada: manter o relógio como widget nativo do Plasma e controlá-lo por um auxiliar compartilhado, integrado à oferta opcional do catálogo e ao estágio verificado da instalação/Update. Preserva o editor de área de trabalho e centraliza instalação, identificação e configuração.

Alternativa: uma janela de relógio independente. Exigiria recriar o widget e controlar posicionamento no Wayland, sem aproveitar a edição nativa solicitada.

Editar diretamente o arquivo de configuração do Plasma durante a sessão não é a abordagem escolhida: pode disputar gravações com o Plasma. Preferir sua interface de sessão para adicionar/mover instâncias, confirmando o resultado e comunicando falhas.

## Entrega e validação

Estender o catálogo para representar o componente local distribuído com a entrega; não tratá-lo como pacote Arch/AUR inexistente. Incluir arquivos no mesmo commit verificado e nos checkpoints, respeitar escolhas de remoção e preservar compatibilidade com catálogos históricos.

Verificar primeiro se os auxiliares compartilhados atendem a instalação limpa sem editar `instalar-arch.sh`. Se a edição for necessária, cumprir antes o backup verificado no Drive exigido por AGENTS.md. A entrega de recurso prevê um incremento MINOR único, a partir da versão remota vigente no momento da publicação.

Validar catálogo, instalação em perfil temporário, preservação de instância/configuração, repetição do Update, escolha das telas/cantos e navegação Qt. Conferir o layout visualmente. Separar testes simulados de validação real no Plasma com dois monitores; não executar o anexo nem alterar a área de trabalho desta máquina durante a preparação sem autorização correspondente.

## Limites

A revisão confirmou que a recriação precisa de registro persistente, remoção em chamada separada, confirmação de liberação do layout e conferência da posição. Preservar também atalho e bloqueio; recuperar na origem em falha, mantendo retomada se a sessão impedir a recuperação.

Sem mudanças de kernel/NVIDIA, atualização geral ou alteração do navegador. Sem apagar ou reorganizar outros widgets. Sem criar branches/PRs nem editar README.
