# Callas OS

- Keep the repository root limited to the existing `assets/`, `programas-callas-os/`, `instalar-arch.sh`, `README.md` and legacy updater bridge. New programs, metadata, docs and tests belong inside `programas-callas-os/`; visual resources belong inside `assets/`. Do not create extra top-level files.

- Preserve `instalar-arch.sh`, repository paths, existing short links and the root updater compatibility bridge.
- The public project version has one source: `/programas-callas-os/atualizador/VERSION`. The installed identity is maintained by `callas-version`; do not change Arch's `os-release` to display the project version.
- Bump the public version only for changes to delivered functionality: patch for behavioral fixes, minor for new features, major for incompatible structural changes. Repository organization, file moves and documentation-only changes retain the current public version. For a functional release, update `atualizador/VERSION`, `atualizador/CHANGELOG.md` and current-version references in README together. The initial adoption of this scheme is `3.2.0`.
- Keep the date-based `VERSAO` revision used by legacy updater clients in sync between the root bridge and the full updater. It is an internal migration revision, separate from the public project version.
- Project identity advances only after the required migration or installation steps succeed. Preserve incomplete/legacy boot state without claiming a completed new release. Ordinary Arch/application updates do not advance the project version.
- Keep embedded `put-update` and `callas-nekofetch` in the installer identical to their canonical files under `programas-callas-os/atualizador/`.
- The user's NVIDIA version hold is intentional. Do not remove it or change drivers without explicit authorization.
- User-visible logs and backups belong under the user's XDG Documents folder: `Callas OS/Callas OS Logs` and `Callas OS/Callas OS Backups`. Backup archives stay root-only and bounded by the configured combined quota. Migrate existing files without overwriting collisions or following symlinks.
- Validate relevant changes with the offline test suite and shell/Python syntax checks. Clearly distinguish mocked checks from real Arch, boot, VM and hardware validation.
