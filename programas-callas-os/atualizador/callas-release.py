#!/usr/bin/python3
"""Root-owned download staging. GitHub remains the release trust authority.

One immutable commit per operation; verify Git blob IDs before execution.
This is transport/content verification, NOT an independent release signature.
"""
import hashlib
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
    "VERSION",
    "programas-callas-os/atualizador/callas-version.py",
    "programas-callas-os/atualizador/callas-nekofetch.sh",
    "programas-callas-os/atualizador/callas-storage.py",
    "programas-callas-os/atualizador/callas-maintenance.py",
    "programas-callas-os/atualizador/callas-native.py",
    "programas-callas-os/atualizador/callas-aur.py",
    "programas-callas-os/atualizador/callas-config-update.sh",
    "programas-callas-os/atualizador/callas-security.sh",
    "programas-callas-os/atualizador/callas-release.py",
    "programas-callas-os/atualizador/put-update.sh",
    "programas-callas-os/atualizador/callas-logs.py",
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
    with urllib.request.urlopen(req, timeout=120) as response:
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

def stage_files(destination, ref):
    if not re.fullmatch(r"[0-9a-f]{40}", ref):
        raise ValueError("Commit inválido")
    tree = json.loads(request(API + "/git/trees/" + ref + "?recursive=1"))
    if tree.get("truncated"):
        raise ValueError("Árvore incompleta")
    blobs = {item["path"]: item for item in tree["tree"] if item["type"] == "blob"}
    for name in FILES:
        item = blobs[name]
        if item["mode"] not in ("100644", "100755"):
            raise ValueError("Tipo de arquivo não permitido")
        data = request(RAW + "/" + ref + "/" + name)
        verify_blob(data, item["sha"])
        target = Path(destination) / Path(name).name
        target.write_bytes(data)
        target.chmod(0o600)
        if name.endswith(".sh"):
            subprocess.run(["/usr/bin/bash", "-n", str(target)], check=True)
        elif name.endswith(".py"):
            compile(data, name, "exec")

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
        ref = resolve_ref()
        with tempfile.TemporaryDirectory(prefix="callas-release-", dir="/var/tmp") as stage:
            stage_files(stage, ref)
            env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "SUDO_USER": user,
                   "CALLAS_RELEASE_REF": ref, "CALLAS_RELEASE_DIR": stage}
            if os.environ.get("SSH_CONNECTION"):
                env["SSH_CONNECTION"] = os.environ["SSH_CONNECTION"]
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
