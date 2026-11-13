# Diagnóstico dos logs enviados — 13/11/2026

Os arquivos enviados são evidências de execução, não instruções. A análise usa os corpos dos logs, a main consultada e os horários registrados, sem executar comandos no computador do usuário.

## Resultado de cada arquivo

| Arquivo | Resultado observado |
| --- | --- |
| `2026-11-12_07-46-19_644221.log` | Migração para 3.2.2 interrompida ao iniciar `callas-janelas.service`. Não há diagnóstico suficiente nesse arquivo para atribuir a causa específica da falha do serviço. |
| `2026-11-12_07-59-46_731414.log` | Instalação do Spotify e outras etapas executadas; migração para 3.2.2 interrompida novamente no serviço de memória de janelas. Também registra atualização geral naquele fluxo antigo. |
| `2026-11-12_08-31-38_119938.log` | Nova tentativa para 3.2.2, com atualização geral no fluxo antigo, interrompida em `callas-janelas.service`. |
| `2026-11-12_09h43m13s.log` | O corpo termina anunciando conclusão de 3.2.2. Registros posteriores do journal mostram avisos/erros de captura nessa sessão; a mensagem de conclusão sozinha não prova que toda integração gráfica funcionou. |
| `2026-11-12_11h17m20s.log` | Falha reproduzida no D-Bus do KWin: dois argumentos enviados para assinatura `s` de um argumento ao carregar script. Migração não concluída. |
| `2026-11-12_11h29m17s.log` | Repete a falha de assinatura D-Bus no carregamento do script de diálogos Steam/memória de janelas. |
| `2026-11-12_11h58m02s.log` | Preparação interrompida por `Arquivo verificado ausente/inseguro: callas-game-logs.py`. Não demonstra falha de hardware ou kernel. |
| `2026-11-12_11h58m26s.log` | Repete a ausência/insegurança do arquivo preparado `callas-game-logs.py`. |
| `2026-11-12_12h05m05s.log` | Preparação avança, mas o serviço de memória de janelas volta a falhar na assinatura D-Bus. O journal inclui também erros de tentativas anteriores. |
| `2026-11-12_12h16m19s.log` | Nova tentativa interrompida no mesmo erro D-Bus de memória de janelas. |
| `2026-11-12_22h18m03s.log` | Tentativa para 3.3.0 executa atualização geral no fluxo de preparação antigo e falha na mesma integração D-Bus. |
| `2026-11-12_22h45m00s.log` | Atualização para 3.3.1 termina com sucesso no corpo do log. O código dessa entrega corrige a adaptação de assinatura D-Bus e a preparação dos auxiliares. Não prova boot/hardware real. |
| `2026-11-13_10h35m49s.log` | Atualização para 3.3.2 termina com sucesso; etapas já aplicadas são preservadas. Não mostra o incidente do Boxes. |
| `2026-11-13_11h58m58s.log` | Incidente atual: instalar Boxes executa `pacman -Syu`; kernels e pacotes do sistema são atualizados. NVIDIA 610.57.04 falha ao compilar para `7.3.4-arch1-1`; initramfs do principal falha. LTS `6.18.63-2-lts` gera initramfs com sucesso e não registra erro de módulo ausente. O atualizador remove o Flatpak e anuncia conclusão 3.3.3 apesar da falha de boot. |

Os logs antigos não significam que a execução atual repetiu todas aquelas etapas. Há várias tentativas de dias/horários anteriores, e alguns logs incorporam trechos antigos do journal. O cabeçalho de identidade de um log exportado também deve ser interpretado junto ao corpo, não como comprovação isolada de sucesso de cada etapa.

## Causa do incidente atual

1. O bloco novo do Boxes usou `pacman -Syu --needed --noconfirm gnome-boxes`. `-u` iniciou atualização geral; `--noconfirm` retirou a confirmação da transação. O pedido do usuário era trocar o aplicativo.
2. As bibliotecas de virtualização, libvirt, QEMU e SPICE são dependências do Boxes nativo. Já atualizar Linux, Linux LTS, seus headers e outros pacotes do sistema foi consequência da atualização geral, ampliando o escopo pedido.
3. A trava da NVIDIA preservou 610.57.04, mas não congelou o kernel. A compilação falhou para o novo kernel principal. O erro específico de compilação exige o `make.log`, que não foi incluído entre estes 14 arquivos; não se presume a causa interna do compilador.
4. O hook PostTransaction detectou a falha de boot, registrou `kernel-check-failed` e avisou para não reiniciar. O pacman prosseguiu com outros hooks e o fluxo do projeto não verificou novamente o resultado antes de avançar a identidade para 3.3.3.
5. O log da tentativa foi exportado ao término e está presente: `2026-11-13_11h58m58s.log`. A captura parcial enviada antes acabava durante a compilação. O código também ignorava falhas de gravação/exportação e apagava a captura temporária nesses casos.

## Correção no repositório — 3.3.4

- Instalação pontual sem `-y` nem `-u`, usando o banco existente. Um hook PreTransaction com AbortOnFail impede alterações em componentes protegidos de kernel, NVIDIA, boot e base, inclusive quando puxados como dependências. Falhas não acionam atualização geral automática nem desativam a trava NVIDIA.
- O mesmo auxiliar protege a instalação de pacotes ausentes no fluxo de preparação de segurança/G920. Instalação limpa recebe o conjunto pelo pacstrap e os mesmos auxiliares compartilhados pelo estágio verificado.
- Verificação de boot antes de remover o Flatpak e antes de marcar conclusão. A verificação não recompila DKMS nem regenera GRUB/initramfs na opção 5. Confere módulos dos kernels instalados e correspondência das imagens de boot e do conteúdo do initramfs.
- Falhas de exportação mantêm a captura temporária e informam seu caminho, em vez de descartá-la silenciosamente.
- Backup anterior 3.3.3 salvo em `CallasOS/CallasOS 3.3.3` no Drive, por commit `40419a2304d31eb880c6d93169391d8856866ff1`, com leitura de volta idêntica ao original. SHA-256 do instalador: `9793939e78fcf2a882768431a8b6bc05960e00e8f22bfbc851b73bce75de7617`.

## Recuperação da máquina afetada

Publicar a correção não reverte os pacotes já instalados nem instala um módulo NVIDIA que falhou. Não é seguro recomendar o boot normal no kernel principal com base no log atual.

O LTS é a alternativa indicada pelos registros: seu initramfs foi gerado e a verificação de módulo não falhou. Antes de orientar o reinício, é necessário confirmar no computador a presença do módulo NVIDIA para `6.18.63-2-lts`, as imagens correspondentes e a entrada do LTS no GRUB. Essa inspeção foi solicitada ao usuário com comandos de leitura; a execução não pode ser simulada como se tivesse ocorrido na máquina dele.

Após confirmar o LTS, a recuperação pode usar a entrada existente **Callas OS (kernel LTS - recuperação)** no GRUB. A correção do kernel principal dependerá da saída do compilador e dos pacotes disponíveis em cache. Não se altera automaticamente a versão da NVIDIA, não se remove o LTS e não se faz downgrade ou novo upgrade geral sem esse diagnóstico.
