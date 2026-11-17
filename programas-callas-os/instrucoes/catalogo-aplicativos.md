# Catálogo de aplicativos do Callas OS Update

`atualizador/callas-apps.json` declara o estado dos aplicativos distribuídos pelo Update. O arquivo e seu executor `callas-apps.py` são baixados do mesmo commit imutável que os demais arquivos da entrega, com verificação dos blobs do GitHub. A instalação limpa usa esse mesmo estágio e executor; não há uma segunda lista de migração dentro do instalador.

Ao clicar em Callas OS Update, o lançador consulta a main. Se houver uma entrega nova ou diferenças locais, prepara os arquivos verificados. O backend inventaria pacotes nativos e Flatpaks de sistema, informa CPU/GPU detectadas e compara o catálogo com a instalação e os registros de aplicativos gerenciados. Os checkpoints também verificam aplicativos e auxiliares instalados: um commit inalterado não esconde um app ausente, uma remoção pendente ou um auxiliar modificado.

## Publicar uma mudança de aplicativo

- Adicionar: incluir uma entrada `present`, com `source` igual a `repo`, `aur` ou `flatpak`, e a fase correspondente (`security`, `apps` ou `flatpaks`). As fontes nativas usam as transações protegidas existentes, sem sincronização/upgrade geral. AUR compila como usuário normal.
- Remover: usar `absent`. Para máquinas que já receberam este catálogo, retirar uma entrada anteriormente `present` também solicita a remoção, usando o registro local de propriedade. Para alcançar instalações anteriores ao catálogo, manter uma entrada `absent` explícita é necessário: a ausência de um arquivo de código no GitHub, sozinha, não identifica um pacote instalado.
- Substituir: declarar o substituto `present` e o anterior `absent`, com `replacement` apontando para o novo nome, na mesma fase. A instalação deve ter sucesso e ser confirmada antes da remoção. Manter a fase de um aplicativo ao editar sua entrada; ela identifica seu registro de migração.

Os aplicativos ausentes da lista e que nunca foram gerenciados pelo catálogo são preservados. O catálogo inicial cobre os aplicativos já provisionados pelas etapas de aplicativos/Flatpak do Update e a migração do GPU Screen Recorder; não assume controle de todos os pacotes do Arch nem do cliente Codex opcional.

## Execução e retomada

O executor confirma o resultado no banco local após cada ação. Instalações confirmadas recebem registro de propriedade imediatamente, mesmo se uma ação posterior falhar. O registro completo da fase só é consolidado após verificar que não há mais diferenças. Registros ficam em `/var/lib/callas-os/apps-managed-FASE.json`, com escrita atômica e acesso administrativo.

Remoções nativas usam apenas `pacman -R`, sem recursão, com hook que verifica todos os alvos resolvidos. Aplicativos em uso adiam a remoção com falha explícita para nova tentativa. Flatpaks são gerenciados no escopo de sistema, sem `--delete-data`; instalações pessoais no escopo de usuário permanecem fora do catálogo. A migração histórica do Boxes continua verificando os dois escopos e preservando discos de VMs.

O inventário de CPU AMD/Intel e GPU NVIDIA/AMD/Intel (inclusive Arc) usa `/proc/cpuinfo` e os dispositivos PCI em `/sys`, sem escolher, instalar ou trocar drivers. O catálogo de aplicativos é comum aos fabricantes; esta entrega não adiciona políticas de instalação de drivers por hardware. Kernel, headers, NVIDIA e base continuam protegidos. Atualizações de versões dos pacotes Arch/AUR permanecem nos fluxos próprios; este catálogo define presença/remoção de aplicativos e as correções do projeto continuam comparadas por conteúdo.

Logs e backups seguem as pastas existentes em Documentos. O Update permanece manual e preserva a política de timers desativados.

## Desinstalação pela Central

A opção **Desinstalar aplicativos** registra remoções administrativas confirmadas em `/var/lib/callas-os/apps-user-removed.json`. O catálogo e `--wants` respeitam essas escolhas: uma entrada `present` não reinstala o aplicativo removido. Isso também impede as preparações complementares de Spotify, Haruna e Boxes de desfazerem a escolha. A reinstalação explícita pelo gerenciador de pacotes é preservada; o registro não solicita remoção de aplicativos presentes. Entradas `absent` e migrações de aplicativos retirados continuam funcionando normalmente.

Remoções usam o lock global da Central e um lock compartilhado com a reconciliação do catálogo. O auxiliar é preparado pelo estágio verificado e instalado pelo mesmo `callas-security.sh` na instalação limpa e no Update. Nativos/AUR exigem autorização administrativa e passam novamente pela classificação de aplicativos e pela transação protegida sem cascata. Componentes de kernel, NVIDIA, boot, sessão e ferramentas essenciais ficam bloqueados. Uma dependência obrigatória impede a transação pelo próprio pacman; nunca use flags para ignorá-la.

Flatpaks são separados por escopo e referência completa; runtimes e dados não são apagados. Codex instalado pela Central e AppImages identificáveis no perfil são removidos como usuário normal. AppImages são descobertos em `~/Applications`, `~/Downloads` e pelos atalhos pessoais com caminho absoluto para o arquivo. Diretórios arbitrários e scripts de desinstalação de downloads não são executados/removidos automaticamente. Os logs pessoais usam a categoria Aplicativos em Documentos. Testes de pacotes são simulados; as prévias e o inventário de leitura não comprovam remoção real de pacotes em outra máquina.

## Restauração seletiva dos padrões

O campo `defaults` do mesmo catálogo descreve apenas os aplicativos comuns oferecidos em **Aplicativos nativos → Aplicativos padrão Callas OS**. Ele não adiciona aplicativos à reconciliação automática: `applications` continua sendo o contrato de presença/remoção do Update. Aplicativos já retirados (`absent`), base e drivers não podem entrar na oferta. A lista corresponde aos aplicativos da instalação limpa, sem seus drivers ou ferramentas essenciais.

O submenu mantém **Atualizar aplicativos** no fluxo anterior de atualização dos aplicativos instalados. A outra opção expande a própria janela e mostra cartões com seleção, instalação individual e instalação dos selecionados. A consulta de versões/tamanhos é somente leitura, sem sudo ou sincronização do banco pacman. Repositórios oficiais usam metadados locais; AUR consulta seu RPC e não informa tamanho antecipado; Flatpaks usam informações da instalação ou do remoto. Falhas de metadados não viram tamanho zero nem impedem ver a lista. Tamanhos são rotulados e não prometem incluir todas as dependências.

`callas-defaults --restore USUARIO ID...` exige autorização administrativa, usuário originador do sudo, IDs válidos no catálogo instalado e locks compartilhados com a Central/reconciliação. Valida a seleção inteira antes de começar e instala somente os escolhidos, com as proteções nativas/AUR existentes e Flatpaks de sistema. Não executa atualização geral. Confirma cada aplicativo no banco local e só então desfaz sua preferência de desinstalação. Uma falha preserva os sucessos anteriores e os opt-outs ainda não restaurados. Desmarcar não remove aplicativos. Os logs continuam na categoria Aplicativos.

Ícones em `assets/central-callas-os/default-app-icons.json` são distribuídos pelo mesmo estágio verificado e continuam visíveis mesmo sem o aplicativo instalado. Auxiliar, catálogo, interface, asset e checkpoints atendem instalação limpa e Update, sem alteração do instalador principal.

## Navegação da Central e ícones

Os submenus de manutenção, monitores, padrões e desinstalação são páginas internas da janela principal. “Voltar” retorna à Central; confirmação e cancelamento também usam uma página interna. A navegação e o fechamento são bloqueados durante auxiliares ativos. O diálogo de senha continua separado do fluxo de logs; atalhos para aplicativos externos continuam abrindo os próprios programas.

O inventário do desinstalador inclui uma referência de ícone sem usá-la como comando ou identidade de pacote. A interface resolve o ícone do atalho, assets verificados dos padrões, tema e exportações Flatpak do sistema/usuário, usando um ícone genérico quando não há imagem reconhecível. A coluna Aplicativo conserva o ID original nos dados da linha; filtros, origem, versão e proteções continuam independentes do ícone. Os mesmos arquivos já distribuídos pelo estágio compartilhado atendem instalação limpa e Update.

## Brave Origin como padrão da instalação limpa

A instalação limpa instala `brave-origin-bin` e o define como navegador padrão (MIME, KDE e atalho do painel). Os dois navegadores ficam no campo `defaults` para instalação voluntária pela Central; o Brave tradicional não é removido do repositório. Nenhum deles entra em `applications`: o Update não instala o Origin automaticamente, não remove o tradicional e não troca a associação de navegador de máquinas existentes.

Toda configuração comum fica em `callas-browser.py`, distribuído no estágio verificado e instalado como `/usr/local/libexec/callas-browser`. Ambos leem `/etc/brave/policies`; os IDs de Bonjourr e SteamDB continuam idênticos. As flags são separadas em `brave-flags.conf` e `brave-origin-flags.conf`; perfis ficam em `Brave-Browser` e `Brave-Origin`. O modo `--system` grava políticas e preferências iniciais dos pacotes presentes. O modo `--user` aplica flags e ajustes visuais sem recriar os perfis. `--default-origin` só é chamado pela instalação limpa.

A transação dos pacotes reaplica os padrões de sistema pelo hook `95-callas-browser-defaults.hook`; não escreve em perfis de usuário. O Update prepara o backup antes dos ajustes de usuário e preserva perfis abertos, retornando pendência para nova tentativa. Perfis inválidos ou alterados durante a gravação interrompem a etapa sem substituir os dados. O backup contempla ambos navegadores e perfis adicionais e continua privado e sujeito à quota existente. Não copie configurações paralelas no instalador ou no Update: altere o auxiliar comum para manter os dois navegadores equivalentes.
