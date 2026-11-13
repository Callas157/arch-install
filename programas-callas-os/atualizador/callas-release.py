#!/usr/bin/python3
"""Root-owned download staging. GitHub remains the release trust authority.

One immutable commit per operation; verify Git blob IDs before execution.
This is transport/content verification, NOT an independent release signature.
"""
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import pwd
import re
import subprocess
import sys
import tempfile
import urllib.request

API = "https://api.github.com/repos/Callas157/arch-install"
RAW = "https://raw.githubusercontent.com/Callas157/arch-install"
FILES = (
    "programas-callas-os/atualizador/VERSION",
    "programas-callas-os/atualizador/callas-version.py",
    "programas-callas-os/atualizador/callas-nekofetch.sh",
    "programas-callas-os/atualizador/callas-storage.py",
    "programas-callas-os/atualizador/callas-maintenance.py",
    "programas-callas-os/atualizador/callas-native.py",
    "programas-callas-os/atualizador/callas-aur.py",
    "programas-callas-os/atualizador/callas-aur-install.py",
    "programas-callas-os/atualizador/callas-config-update.sh",
    "programas-callas-os/atualizador/callas-security.sh",
    "programas-callas-os/atualizador/callas-update-state.py",
    "programas-callas-os/atualizador/callas-spotify-permissions.sh",
    "programas-callas-os/atualizador/callas-release.py",
    "programas-callas-os/atualizador/put-update.sh",
    "programas-callas-os/atualizador/callas-logs.py",
    "programas-callas-os/atualizador/callas-game-logs.py",
    "programas-callas-os/atualizador/callas-kernel-check.sh",
    "programas-callas-os/monitores/callas-monitores.py",
    "programas-callas-os/janelas/callas-janelas.py",
    "programas-callas-os/sessao/callas-inicio-kde.sh",
    "programas-callas-os/sessao/callas-autostart.py",
    "programas-callas-os/monitores/callas-kde-desligamento-login.sh",
    "assets/plymouth/callas/callas.script",
    "assets/plymouth/callas/callas.plymouth",
)

def request(url):
    req = urllib.request.Request(url, headers={"User-Agent": "CallasOS-Updater", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as response:
        if not response.url.startswith("https://"):
            raise ValueError("Redirecionamento sem HTTPS")
        data = response.read(4 * 1024 * 1024 + 1)
        if len(data) > 4 * 1024 * 1024:
            raise ValueError("Resposta excedeu o limite")
        return data

def resolve_ref():
    ref = json.loads(request(API + "/git/ref/heads/main"))["object"]["sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", ref):
        raise ValueError("Commit inválido")
    return ref

def verify_blob(data, expected):
    actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    if actual != expected:
        raise ValueError("Conteúdo diferente do blob publicado")

def stage_complete(destination, expected_owner=0):
    """Check the current release's entire file list, including future helpers.

    Old installed launchers can download this verified module but still stage
    only their old FILES tuple. Never infer completeness from a fixed subset.
    """
    destination = Path(destination)
    complete = True
    for name in ('update-assets.json', *(Path(p).name for p in FILES)):
        target = destination / name
        if target.is_symlink():
            raise ValueError('Arquivo simbólico na preparação: ' + name)
        if not target.exists():
            complete = False
            continue
        info = target.stat()
        if not target.is_file() or info.st_uid != expected_owner or info.st_mode & 0o022:
            raise ValueError('Arquivo inseguro na preparação: ' + name)
    return complete


def stage_files(destination, ref):
    if not re.fullmatch(r"[0-9a-f]{40}", ref):
        raise ValueError("Commit inválido")
    print('Preparando Callas OS Update: consultando arquivos da versão verificada...', flush=True)
    tree = json.loads(request(API + "/git/trees/" + ref + "?recursive=1"))
    if tree.get("truncated"):
        raise ValueError("Árvore incompleta")
    blobs = {item["path"]: item for item in tree["tree"] if item["type"] == "blob"}
    manifest={'commit':ref,'assets':{name.removeprefix('assets/'):item['sha'] for name,item in blobs.items() if name.startswith('assets/')}}
    (Path(destination)/'update-assets.json').write_text(json.dumps(manifest,sort_keys=True)+'\n')
    # Reject unsafe entries before starting any file download.
    for name in FILES:
        item = blobs[name]
        if item["mode"] not in ("100644", "100755"):
            raise ValueError("Tipo de arquivo não permitido")
    print(f'Baixando e verificando {len(FILES)} arquivos (até 4 por vez)...', flush=True)
    with ThreadPoolExecutor(max_workers=4) as downloads:
        pending = {downloads.submit(request, RAW + "/" + ref + "/" + name): name for name in FILES}
        try:
            for count, future in enumerate(as_completed(pending), 1):
                name = pending[future]
                data = future.result()
                verify_blob(data, blobs[name]["sha"])
                target = Path(destination) / Path(name).name
                target.write_bytes(data)
                target.chmod(0o600)
                if name.endswith(".sh"):
                    subprocess.run(["/usr/bin/bash", "-n", str(target)], check=True)
                elif name.endswith(".py"):
                    compile(data, name, "exec")
                print(f'  [{count}/{len(FILES)}] Verificado: {Path(name).name}', flush=True)
        except Exception:
            for future in pending:
                future.cancel()
            raise

def main():
    if os.geteuid() != 0:
        raise SystemExit("Abra a opção 5 do Atualizador do sistema.")
    user = os.environ.get("SUDO_USER", "")
    if not user or pwd.getpwnam(user).pw_uid == 0:
        raise SystemExit("Não consegui identificar o usuário normal.")
    if len(sys.argv) > 2 or (len(sys.argv) == 2 and sys.argv[1] != "--force"):
        raise SystemExit("Argumento inválido")
    os.umask(0o077)
    try:
        print('Callas OS Update: verificando atualizações no GitHub...', flush=True)
        ref = resolve_ref()
        if not sys.argv[1:]:
            try:
                installed=json.loads(Path('/etc/callas-os/release.json').read_text())
            except FileNotFoundError:installed={}
            pending=Path('/var/lib/callas-os')/('update-pending-'+str(pwd.getpwnam(user).pw_uid))
            if installed.get('release')==ref and installed.get('status')=='complete' and not pending.exists():
                print('Callas OS Update: nenhuma nova atualização do projeto no GitHub.')
                return 0
        with tempfile.TemporaryDirectory(prefix="callas-release-", dir="/var/tmp") as stage:
            stage_files(stage, ref)
            env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "SUDO_USER": user,
                   "CALLAS_RELEASE_REF": ref, "CALLAS_RELEASE_DIR": stage}
            if os.environ.get("SSH_CONNECTION"):
                env["SSH_CONNECTION"] = os.environ["SSH_CONNECTION"]
            print('Preparação concluída. Iniciando atualização das configurações...', flush=True)
            result = subprocess.run(["/usr/bin/bash", stage + "/callas-config-update.sh", *sys.argv[1:]], env=env)
            return result.returncode
    except Exception as error:
        logger = "/usr/local/libexec/callas-logs"
        if Path(logger).is_file():
            subprocess.run([logger, "--record", "Callas OS Update"],
                           input=("Falha ao preparar atualização: " + str(error) + "\n").encode())
            subprocess.run([logger, "--export", user])
        raise

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print("Callas OS Update interrompido: " + str(error), file=sys.stderr)
        sys.exit(1)
