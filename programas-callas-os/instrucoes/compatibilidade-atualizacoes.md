# Compatibilidade do Callas OS Update

O botão Callas OS Update deve buscar a entrega atual diretamente, mesmo quando a versão instalada ficou várias releases atrás. Não introduza dependência de execução das releases intermediárias nem listas fixas de arquivos que obriguem o cliente antigo a conhecer todos os auxiliares futuros.

## Contratos obrigatórios

- Resolver uma referência imutável e verificar todos os arquivos pelo mesmo commit. O lançador histórico pode preparar uma lista antiga; o estágio atual deve completá-la antes de aplicar alterações. Preserve URLs e pontos de entrada compatíveis existentes.
- Tratar dados instalados como entradas de migração, incluindo variações válidas de sintaxe. Não presumir que sejam idênticos ao template do instalador atual. Não executar arquivos de configuração para descobrir parâmetros: leia-os e preserve argumentos, UUIDs, caminhos e dados pessoais.
- Verificar antes de alterar. A atualização visual do boot não pode reescrever argumentos ou descartar microcódigo. Só substituir grub.cfg após validar o candidato; manter backup das entradas e marcador de retomada em falhas parciais.
- Manter checkpoints por conteúdo, opções removidas/restauradas, estado pendente e identidade incompleta em falhas. Não remover essas proteções para anunciar sucesso.
- Preservar o escopo de aplicativos/configurações: nunca atualizar kernel, headers ou NVIDIA como forma de resolver uma migração. Uma dependência protegida ou corrupção real deve continuar interrompendo a operação com diagnóstico, em vez de forçar alterações.
- Brave Origin continua padrão apenas na instalação limpa. Em máquinas existentes, os navegadores são escolhas da pessoa e a oferta da Central não equivale a instalação automática.

## Casos históricos e validação

`tests/fixtures/historical-release-files.json` preserva listas reais de arquivos dos lançadores 3.2.2, 3.7.0, 3.9.0 e 3.10.0 com seus commits de origem. `test_stage_compatibility.py` prepara o estágio atual a partir delas e confere download pelo mesmo commit e reaplicação sem downloads repetidos. Preserve esses casos quando adicionar auxiliares.

`test_boot_theme.py` cobre formatos válidos de entradas, incluindo microcódigo Intel/AMD, tabulação, caminhos, comandos EFI, comentários, aspas e CRLF. `test_boot_migration_integration.py` executa o bloco real do Update com boot temporário, incluindo falha e retomada sem sobrescrever a configuração anterior. `test_kernel_check.py` verifica a aceitação coerente dos caminhos citados na etapa final. Esses testes não executam boot ou atualização de pacotes reais.

Uma máquina sem atualizar por muito tempo deve continuar encontrando o protocolo de entrega e as migrações mantidas. Não prometa compatibilidade irrestrita com configurações desconhecidas ou corrompidas, indisponibilidade externa ou qualquer combinação de pacotes: diagnostique a condição real, adicione uma regressão e preserve o sistema enquanto corrige a incompatibilidade.
