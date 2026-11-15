# Callas Baterias

Bandeja única para FreeWolf F75 e Attack Shark, com o Solaar do headset preservado separadamente. No X6 observado (`1d57:fa61`, variante `0x10`), o nível bruto é convertido de décimos em porcentagem: `0A` corresponde a 100%. Outras variantes mantêm sua escala anterior. O número depende do relatório do dispositivo; conexão USB sozinha não prova corrente real de carga.

O aplicativo deriva do trabalho MIT de Gabriel Marques Ferrarezi; a licença original acompanha `app/LICENSE-AttackShark`. A interface PT-BR e as adaptações foram fornecidas pelo usuário. Referências da escala X6: [protocolo](https://github.com/blak0p/attack-shark-linux/blob/main/docs/protocol-x6.md) e [parser](https://github.com/Abosmra/rust-shark/blob/main/src/protocol.rs).

## Distribuição no Callas OS

- Instalação limpa: o instalador já prepara os arquivos do commit imutável com `callas-release.py`, copia o estágio para o chroot e chama `callas-security.sh --installation`. Esse auxiliar agora instala também o Callas Baterias antes de concluir a identidade da instalação.
- PCs existentes: opção **5 — Callas OS Update**, que baixa o mesmo pacote verificado e chama o auxiliar compartilhado com `--config-update`. A publicação no GitHub não executa remotamente a atualização nos PCs; o aplicativo chega quando essa opção é executada.
- O lançador antigo expande o estágio pelo `callas-release.py` atual antes de implantar arquivos novos. Checkpoint de segurança inclui instalador do aplicativo, pacote e presença dos arquivos obrigatórios.
- `pyside6` só é instalado se ausente, via `callas-native --install pyside6`, usando banco existente e proteção de todos os alvos da transação. Recusa ou falha interrompe a entrega; não há atualização geral de fallback.
- Arquivos globais ficam em `/usr/local/share/callas-os/baterias`, com serviço de usuário, entrada de menu, autostart e regra udev restrita às interfaces dos dispositivos suportados. Não depende de arquivos pessoais deste PC.
- Perfis existentes são migrados pelo próprio usuário, com serviço apontando ao aplicativo global; preferências QSettings e histórico ficam intactos. Os indicadores antigos são desativados para evitar duplicação.
- Outros perfis recebem o início automático global. Em instalação limpa/chroot, nenhuma sessão gráfica é iniciada. A bandeja é organizada no login, após a existência do painel.
- O ajuste local `br.com.callas.ordem-baterias` mantém **Callas Baterias → Solaar → rede**, sem substituir o Plasma nem adicionar arraste. Depende das interfaces QML do Plasma 6; mudanças futuras do KDE podem exigir adaptação. Ausência do painel não impede monitorar a bateria.
- O Solaar é um aplicativo separado já integrante do Callas OS; seus arquivos não são alterados. Hardware não suportado aparece sem leitura, sem tentativa de reprogramação de firmware.

## Manutenção e verificação

Edite os fontes em `app/` ou `painel/` e execute `python3 programas-callas-os/baterias/empacotar.py` na raiz do repositório. O pacote é determinístico, sem preferências, histórico, caches ou arquivos privados. Os testes conferem cada arquivo do pacote contra os fontes.

Execute `python3 -m unittest discover -s programas-callas-os/tests -v`. A suíte offline simula pacotes, perfis e implantação; não valida boot real nem uma instalação Arch inteira. O aplicativo corrigido e a ordem de ícones foram usados na sessão KDE do usuário antes desta integração; a implantação administrativa é validada em diretórios temporários.

`instalar-arch.sh`, seu atualizador embutido e o README permanecem intactos nesta entrega. Não houve necessidade de editar o instalador; por isso, conforme AGENTS.md, não foi criada cópia duplicada dele no Drive. A versão pública avança uma vez, de 3.4.3 para 3.5.0.
