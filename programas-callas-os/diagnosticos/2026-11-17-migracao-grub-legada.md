# Migração GRUB de uma instalação com identidade 3.9.0

O log enviado relata destino 3.15.0 e falha em `callas-boot-theme.py`: `ValueError: Entrada incompleta: Callas OS Linux`. As fases anteriores já estavam aplicadas; a falha ocorreu na migração visual do boot, antes de regenerar grub.cfg. O log não contém `/etc/grub.d/09_callas`, portanto não demonstra qual linha difere do formato esperado. Não atribuir o problema à GPU Intel/NVIDIA, ao Brave Origin ou à diferença de versão, por si só.

A implementação anterior exigia exatamente quatro espaços, linux /vmlinuz-linux[...] e um único initrd /initramfs-linux[...]. Reproduções com entradas válidas contendo `initrd /intel-ucode.img /initramfs-linux.img`, assim como espaços/tabs, aspas ou caminhos diferentes, geravam a mesma exceção. O arquivo da outra máquina foi solicitado como diagnóstico opcional para confirmar a variante exata.

A correção lê comandos sem executá-los e valida o par principal/LTS preservando o texto original. Faz preflight antes dos assets, mantém marcador de retomada, inclui as entradas no backup e conserva grub.cfg em caso de falha da geração/validação. Não cria UUIDs, não retira microcódigo e não troca kernel/NVIDIA. O instalador existente consome o mesmo auxiliar do estágio verificado, sem necessidade de editar seu código.

Também foram verificadas listas de lançadores históricos (3.2.2, 3.7.0, 3.9.0 e 3.10.0) e a regra de navegador opcional. O teste de preparação direta não equivale a atualizar um sistema Arch real com todos os possíveis pacotes/configurações. Validação final: 338 testes offline, 337 aprovados e um opcional ignorado; sem boot ou execução de Update na máquina do relato.
