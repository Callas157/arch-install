# Callas OS

## Leitura obrigatória no início do trabalho

Antes de planejar ou implementar alterações, consulte a `main` remota atualizada de `Callas157/arch-install`, examine a árvore do repositório e leia estas instruções, [o roteiro de versionamento](instrucoes/versionamento.md), `atualizador/VERSION` e o histórico relevante em `atualizador/CHANGELOG.md`. Leia também os arquivos e as instruções relacionados à tarefa. Repita essa consulta em cada novo chat ou retomada; não dependa da memória de conversas anteriores. A regra vale também para tarefas no instalador da raiz ou em `assets/`.

## Regras existentes do projeto

- Keep the repository root limited to the existing `assets/`, `programas-callas-os/`, `instalar-arch.sh`, and `README.md`. New programs, metadata, docs and tests belong inside `programas-callas-os/`; visual resources belong inside `assets/`. Do not create extra top-level files.

- Preserve `instalar-arch.sh`, canonical program paths and existing installation short links. The root updater bridge was retired after the user confirmed migration; do not recreate it.
- Apply authorized updates directly to `main`, preserving canonical paths and installer/update URLs. Do not create branches or pull requests unless the user explicitly requests them.
- Keep embedded `put-update` and `callas-nekofetch` in the installer identical to their canonical files under `programas-callas-os/atualizador/`.
- Every delivery must cover both clean installation and Callas OS Update. Check the current installer together with the migration before publishing. Shared helpers must come from the same verified release; update embedded copies when applicable and test the files actually staged/installed. A shared-helper change may already serve both flows without changing the installer itself; verify this instead of relying on file timestamps. Never publish an updater-only fix when clean installation needs the same correction.
- Preserve the installer's initial hardware detection, disk selection and account/password prompts. Prepare shared installation files only after these prompts, within the automatic installation sequence and before destructive disk operations. Sharing verified helper code must never display the Callas OS Update interface/banner/file list during installation; detailed updater progress belongs to option 5 on the installed system. Clean installation applies current configurations automatically in its own setup flow.
- The user's NVIDIA version hold is intentional. Do not remove it or change drivers without explicit authorization.
- User-visible logs and backups belong under the user's XDG Documents folder: `Callas OS/Callas OS Logs` and `Callas OS/Callas OS Backups`. Backup archives stay root-only and bounded by the configured combined quota. Migrate existing files without overwriting collisions or following symlinks.
- Validate relevant changes with the offline test suite and shell/Python syntax checks. Clearly distinguish mocked checks from real Arch, boot, VM and hardware validation.

## Versionamento público do Callas OS

A versão pública segue **MAJOR.MINOR.PATCH**:

| Parte | Quando aumentar | Exemplo |
| --- | --- | --- |
| PATCH | Correções de bugs | `3.2.2 → 3.2.3` |
| MINOR | Novos recursos compatíveis com as instalações existentes | `3.2.3 → 3.3.0` |
| MAJOR | Mudanças incompatíveis que exigem migração especial ou reinstalação | `3.3.0 → 4.0.0` |

- Ao aumentar MINOR, zere PATCH. Ao aumentar MAJOR, zere MINOR e PATCH.
- **Não aumente a versão a cada commit.** Uma entrega pode reunir vários commits, correções e recursos. Faça um único incremento por entrega, considerando a mudança de maior impacto.
- Mudanças apenas em documentação ou organização de pastas não exigem aumento da versão pública.
- Uma exceção explícita do usuário para manter uma versão vale apenas naquela entrega; não a transforme em regra permanente. Estas regras substituem a classificação específica anteriormente registrada para a troca do Boxes.

### Antes de alterar

1. Consulte a branch `main` atualizada do repositório `Callas157/arch-install`.
2. Leia `programas-callas-os/atualizador/VERSION` nessa referência remota.
3. Use essa versão como referência, mesmo que outro agente tenha publicado alterações desde sua última participação.
4. Não use a versão lembrada de uma conversa antiga.

Se a memória indicar `3.2.2`, mas o repositório já estiver em `3.4.1`, uma nova correção será `3.4.2`. Não volte para `3.2.3` nem tente compensar incrementos anteriores.

### Antes de publicar

- Confira se a entrega já recebeu seu incremento, evitando aumentá-la duas vezes.
- Confira novamente a versão e o commit remotos. Se houver mudanças concorrentes, reconcilie-as antes de publicar; não sobrescreva trabalho de outro agente nem force a referência.
- Em entregas que alteram a versão pública, atualize `atualizador/VERSION` e a entrada correspondente de `atualizador/CHANGELOG.md`. Documentação ou organização isoladas mantêm a versão.
- **Não edite o README sem solicitação do usuário.** Não atualize suas referências de versão automaticamente.
- Valide as alterações antes de publicar. Use o roteiro em `instrucoes/versionamento.md`.

### Integração com o sistema

- `atualizador/VERSION` é a fonte única da versão pública.
- Preserve a integração existente com instalador, Callas OS Update, NekoFetch, logs e backups. A identidade instalada é mantida por `callas-version`; não altere o `os-release` do Arch para exibir a versão do projeto.
- A identidade instalada só deve avançar após as etapas obrigatórias terminarem com sucesso. Preserve o estado incompleto ou de boot legado sem anunciar uma entrega concluída.
- Atualizações comuns do Arch, kernel ou aplicativos não aumentam a versão do projeto Callas OS.
- A revisão interna por data (`VERSAO`) e o identificador do commit são separados da versão pública; preserve suas funções existentes.
