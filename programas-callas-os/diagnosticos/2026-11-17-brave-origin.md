# Entrega Brave Origin 3.15.0

Origem remota antes da edição: `acd86c43d9bb23c741bbbc7f9b9feae1bcdd13e2`, versão `3.14.0`.

Backup obrigatório confirmado por download integral do arquivo retornado pelo conector do Drive: 107394 bytes; SHA-256 `6854253f9aaec1a1c2868fb425c84262283e373a4a797c8d0fb1587a4b7388db`.

Pasta: [CallasOS 3.14.0](https://drive.google.com/drive/folders/1H9a16JkAePW5xhkLxiAPck6pJaiKrI_g). Arquivo: [instalar-arch.sh](https://drive.google.com/file/d/1BQ0DqY9R5MzBZqMnY2OPnpSRskzUn47J/view). Registro: [backup.json](https://drive.google.com/file/d/1lVtZsGV2QEk9BArjUaVUJPppoTjwwp2m/view). A raiz CallasOS contém dez pastas de backup após esta cópia; não foi necessário remover históricos.

O pacote `brave-origin-bin` é documentado pela [página oficial do Brave Origin para Linux](https://brave.com/origin/linux/). O PKGBUILD mantido por Brave e os arquivos instalados foram consultados somente para leitura: launcher `/usr/bin/brave-origin`, flags `brave-origin-flags.conf`, diretório `/opt/brave-origin-bin` e desktop `brave-origin.desktop`. O binário instalado contém os caminhos `/etc/brave/policies` e `BraveSoftware/Brave-Origin`, confirmando a política comum e o perfil separado. Não foi aberto o navegador nem alterada sua configuração real.

Validação final: 328 testes offline (327 aprovados e um opcional ignorado). O teste completo de configuração limpa usa namespace isolado, arquivos temporários e comandos simulados para pacotes/hardware. Confirma associação Origin, preparação de ambos initial_preferences e ausência de instalação do Brave tradicional nesse fluxo. Testes adicionais cobrem políticas iguais, dados pessoais preservados, perfis abertos/inválidos e backup dos dois navegadores e perfis adicionais. Isso não comprova download efetivo das extensões em perfil novo, instalação Arch real ou boot.
