"""
Sons de alerta.

Nada é embutido nem baixado: o catálogo é montado varrendo os temas de som já
instalados na máquina, e o usuário pode apontar um arquivo próprio.

Um valor de configuração de som é uma destas três coisas:
    ""                caminho vazio  -> silêncio
    "@default:full"   apelido        -> melhor escolha disponível pro evento
    "/caminho.oga"    arquivo        -> tocado como está
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

# temas varridos, na ordem de preferência
THEME_DIRS = [
    Path("/usr/share/sounds/ocean/stereo"),
    Path("/usr/share/sounds/freedesktop/stereo"),
    Path.home() / ".local/share/sounds",
]
EXTS = (".oga", ".ogg", ".wav", ".flac", ".opus", ".mp3")

# nome do arquivo -> rótulo bonito. A ordem daqui é a ordem do menu.
_NICE = [
    ("battery-caution", "Bateria em alerta"),
    ("battery-low", "Bateria baixa"),
    ("battery-full", "Bateria cheia"),
    ("power-plug", "Carregador conectado"),
    ("power-unplug", "Carregador desconectado"),
    ("complete", "Concluído"),
    ("completion-success", "Conclusão com sucesso"),
    ("completion-fail", "Falha na conclusão"),
    ("dialog-warning", "Aviso"),
    ("dialog-error", "Erro"),
    ("dialog-error-serious", "Erro (grave)"),
    ("dialog-information", "Informação"),
    ("dialog-question", "Pergunta"),
    ("bell", "Sino"),
    ("bell-window-system", "Sino (janela)"),
    ("alarm-clock-elapsed", "Despertador"),
    ("message", "Mensagem"),
    ("message-new-instant", "Mensagem (instantânea)"),
    ("message-attention", "Mensagem de atenção"),
    ("message-highlight", "Mensagem em destaque"),
    ("window-attention", "Atenção da janela"),
    ("device-added", "Dispositivo adicionado"),
    ("device-removed", "Dispositivo removido"),
    ("desktop-login", "Entrada na sessão"),
    ("desktop-logout", "Saída da sessão"),
    ("service-login", "Serviço conectado"),
    ("service-logout", "Serviço desconectado"),
    ("network-connectivity-established", "Rede conectada"),
    ("network-connectivity-lost", "Rede desconectada"),
    ("audio-volume-change", "Mudança de volume"),
    ("trash-empty", "Lixeira esvaziada"),
    ("camera-shutter", "Obturador de câmera"),
    ("screen-capture", "Captura de tela"),
    ("suspend-error", "Erro ao suspender"),
    ("game-over-winner", "Fim de jogo — vitória"),
    ("game-over-loser", "Fim de jogo — derrota"),
    ("outcome-success", "Resultado: sucesso"),
    ("outcome-failure", "Resultado: falha"),
]

# evento -> ordem de preferência do som padrão
_DEFAULTS = {
    "critical": ["battery-caution", "dialog-warning-auth", "dialog-warning",
                 "dialog-error", "bell"],
    "low": ["battery-low", "dialog-warning", "message-attention", "bell"],
    "full": ["battery-full", "complete", "completion-success",
             "dialog-information"],
    "connected": ["device-added", "service-login", "desktop-login"],
    "disconnected": ["device-removed", "service-logout", "desktop-logout"],
    "charging": ["power-plug", "device-added", "audio-volume-change"],
}

_cache: dict[str, str] | None = None


def _index() -> dict[str, str]:
    """{nome sem extensão: caminho} varrendo os temas instalados."""
    global _cache
    if _cache is not None:
        return _cache
    found: dict[str, str] = {}
    for base in THEME_DIRS:
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.suffix.lower() in EXTS and path.is_file():
                found.setdefault(path.stem, str(path))
    _cache = found
    return found


def catalog() -> list[tuple[str, str]]:
    """[(rótulo, caminho)] com os sons realmente presentes, começando por 'Silent'."""
    index = _index()
    out = [("Silêncio", "")]
    for name, label in _NICE:
        if name in index:
            out.append((label, index[name]))
    return out


def default_for(event: str) -> str:
    index = _index()
    for name in _DEFAULTS.get(event, []):
        if name in index:
            return index[name]
    return ""


def default_label(event: str) -> str:
    """Nome curto do som padrão do evento, pro rótulo do menu."""
    path = default_for(event)
    if not path:
        return "nenhum encontrado"
    stem = Path(path).stem
    for name, label in _NICE:
        if name == stem:
            return label
    return stem


def resolve(value: str) -> str:
    """Converte o valor guardado no QSettings num caminho tocável."""
    if not value:
        return ""
    if value.startswith("@default:"):
        return default_for(value.split(":", 1)[1])
    return value


def label_for(value: str) -> str:
    """Como o som aparece na interface."""
    if not value:
        return "Silêncio"
    if value.startswith("@default:"):
        return f"Padrão — {default_label(value.split(':', 1)[1])}"
    for label, path in catalog():
        if path == value:
            return label
    return Path(value).name


class Player:
    """Mantém o QMediaPlayer vivo — sem isso o coletor corta o áudio no meio."""

    def __init__(self, volume: int = 85) -> None:
        self._player = None
        self._output = None
        self._volume = max(0.0, min(1.0, volume / 100.0))
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
            self._output = QAudioOutput()
            self._output.setVolume(self._volume)
            self._player = QMediaPlayer()
            self._player.setAudioOutput(self._output)
        except Exception:
            self._player = None

    def set_volume(self, volume: int) -> None:
        self._volume = max(0.0, min(1.0, volume / 100.0))
        if self._output is not None:
            self._output.setVolume(self._volume)

    def play(self, value: str) -> bool:
        """Toca um valor de configuração. Devolve False se não deu pra tocar."""
        path = resolve(value)
        if not path or not Path(path).is_file():
            return False
        if self._player is not None:
            try:
                from PySide6.QtCore import QUrl
                self._player.stop()
                self._player.setSource(QUrl.fromLocalFile(path))
                self._player.play()
                return True
            except Exception:
                pass
        return self._play_external(path)

    def _play_external(self, path: str) -> bool:
        vol = str(int(self._volume * 65536))
        for cmd in (["canberra-gtk-play", "-f", path],
                    ["paplay", "--volume", vol, path],
                    ["pw-play", path]):
            if shutil.which(cmd[0]):
                try:
                    subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
                    return True
                except OSError:
                    continue
        return False
