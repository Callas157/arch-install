Transição gráfica de boot — implementação autorizada em 2026-11-15
1. Backup remoto imutável do instalador: Drive, leitura e SHA-256.
2. Compartilhar script GRUB de transição nos assets: reinicializar gfxterm em tela cheia, carregar wallpaper, sem clear/echo em janela temática; preservar fallback.
3. Instalar script em ambos os fluxos; Update modifica apenas entradas Callas reconhecidas, valida configuração antes de substituir; sem pacotes/kernel/NVIDIA.
4. Animação Plymouth: três pontos com opacidade cíclica, logo e barra; atende ambos os fluxos pelos assets atuais.
5. Testes offline de migração/idempotência/falhas e GRUB UEFI isolado em QEMU. Publicar main com versão 3.11.0 após validação.
Limite: imagem estática durante leituras bloqueantes do GRUB; animação real somente no Plymouth. Sem atrasos artificiais.

Entrega 3.11.0
- Backup verificado: CallasOS 3.10.0 no Drive, instalador do commit e45fc9fb37b8866ec1ff0b9396a95774edb56867.
- SHA-256 anterior: e3e3151d149aa72c73f7e84e8def80fe0a71ec88a799fe569bcb1d1aa220ea6f.
- Reutilizados os assets existentes em assets/grub e assets/plymouth; sem imagens novas.
- Migrador compartilhado preserva argumentos Linux/initrd, rejeita layout desconhecido e não altera entradas pessoais.
- Marcadores pendentes permitem retomar gerações que falharam após fontes já atualizadas.
- 289 testes offline: 288 aprovados, um ignorado. Parser nativo Plymouth, Bash e GRUB válidos.
- QEMU UEFI: transição gráfica isolada confirmada com o loading.cfg da entrega. Não é teste do boot completo da distribuição.
- Revisão independente confirmou integração e correção da retomada de falhas explícitas.
- Limite conhecido: uma interrupção abrupta entre a escrita de fontes e a criação do marcador pode exigir reaplicação; não foi simulado corte de energia.
- Validação final do visual animado e boot completo: usuário na máquina virtual, pela opção 5 da Central; instalação limpa deve ser testada separadamente.
- Máquina principal não recebeu alterações administrativas nesta entrega.
