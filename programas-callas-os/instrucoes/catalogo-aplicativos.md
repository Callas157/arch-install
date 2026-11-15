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
