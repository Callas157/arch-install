#!/usr/bin/python3
"""Export selected diagnostics as the desktop user, never root-write into HOME."""
import datetime
import os
from pathlib import Path
import pwd
import subprocess
import sys

CATEGORIES = ("Callas OS Update", "Sistema e Pacman", "Kernel Linux", "Driver NVIDIA",
              "Aplicativos", "AUR", "Seguranca e Firewall", "Instalacao")

def documents():
    result = subprocess.run(["/usr/bin/xdg-user-dir", "DOCUMENTS"], capture_output=True, text=True)
    name = result.stdout.strip()
    if result.returncode or not name.startswith("/") or Path(name) == Path.home():
        return Path.home() / "Documentos"
    return Path(name)

def write_log(category, data):
    if os.geteuid() == 0 or category not in CATEGORIES:
        raise ValueError("Categoria ou usuário inválido")
    base = documents() / "Logs do Callas OS"
    for name in CATEGORIES:
        (base / name).mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
    target = base / category / (stamp + ".log")
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
    return target

def root_log(category, data):
    if category not in CATEGORIES:
        raise ValueError("Categoria inválida")
    if os.geteuid() != 0:
        return write_log(category, data)
    base = Path("/var/log/callas-os") / category
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
    fd = os.open(base / (stamp + ".log"), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
    # Retain the 60 newest diagnostics of each category; desktop copies are preserved.
    for old in sorted(base.glob("*.log"))[:-60]:
        old.unlink()

def export(user):
    account = pwd.getpwnam(user)
    if account.pw_uid == 0:
        raise ValueError("Informe usuário normal")
    env = {"PATH": "/usr/bin:/bin", "HOME": account.pw_dir, "USER": user,
           "LOGNAME": user, "LANG": "C.UTF-8"}
    def send(category, data):
        subprocess.run(["/usr/bin/runuser", "-u", user, "--", "/usr/bin/env", "-i",
                        *[key + "=" + value for key, value in env.items()],
                        "/usr/local/libexec/callas-logs", "--write", category], input=data, check=True)
    for category in CATEGORIES:
        base = Path("/var/log/callas-os") / category
        if base.exists():
            logs = sorted(base.glob("*.log"))[-5:]
            # Only the newest five per category; export never follows symbolic links.
            for path in logs:
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
                with os.fdopen(fd, "rb") as stream:
                    data = stream.read(4 * 1024 * 1024)
                send(category, ("Origem: " + path.name + "\n").encode() + data)
    for path, category in ((Path("/var/log/pacman.log"), "Sistema e Pacman"),
                           (Path("/var/log/callas-instalacao-avisos.log"), "Instalacao")):
        if path.is_file() and not path.is_symlink():
            with path.open("rb") as stream:
                stream.seek(0, 2)
                stream.seek(max(0, stream.tell() - 1024 * 1024))
                send(category, stream.read())

def main():
    os.umask(0o077)
    if len(sys.argv) == 3 and sys.argv[1] == "--write":
        write_log(sys.argv[2], sys.stdin.buffer.read())
    elif len(sys.argv) == 3 and sys.argv[1] == "--record":
        root_log(sys.argv[2], sys.stdin.buffer.read())
    elif len(sys.argv) == 3 and sys.argv[1] == "--export" and os.geteuid() == 0:
        export(sys.argv[2])
    else:
        raise SystemExit("Uso interno do Callas OS")

if __name__ == "__main__":
    main()
