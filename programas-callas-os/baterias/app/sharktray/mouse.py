"""
Leitura da bateria do mouse sem fio Attack Shark (dongle Xenta 1d57:fa60).

Nada disso vem de driver: o mouse NAO expoe bateria por HID padrao, entao
`/sys/class/power_supply` esta vazio e upower/waybar/wireless-hid nao veem
nada. O que existe e um canal proprietario na interface vendor do dongle
(bInterfaceNumber 02), que emite a cada ~2s:

    03 E5 40 ST NN
             |  +-- nivel da bateria, 0..100 (%)
             +----- estado: 01 = na bateria, 03 = carregando

Como isso foi estabelecido, para quem for mexer aqui depois:

  * o valor satura exatamente em 0x64 = 100, o que fixa a escala em porcento;
  * cai sozinho, ~1 ponto a cada 30 min de uso, sem religar o mouse;
  * sobe durante a carga, e a flag ST casou com tres janelas de cabo medidas;
  * nao muda com movimento intenso, entao nao e tensao instantanea nem RSSI.

Duas armadilhas que valem o codigo que gastam:

  1. O dongle intercala quadros `03 E5 01 00 00` (byte 2 = 0x01 em vez de 0x40)
     quando o enlace pisca. Ler um desses da 0% e dispara alarme falso. So
     quadro com `03 E5 40` conta.
  2. Com o cabo ligado no PC o mouse sai do radio: o dongle emudece e o mouse
     aparece como outro dispositivo USB (1d57:2155). Isso NAO e bateria
     acabando - e por isso que o silencio vira "asleep", nunca 0%.

O acesso sem root vem da regra udev em udev/70-attackshark-battery.rules, que
libera so a interface vendor. Liberar o dongle inteiro daria a qualquer app do
usuario as interfaces de teclado e mouse, ou seja, teclas por hidraw.
"""

from __future__ import annotations

import glob
import json
import os
import select
import time
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, QSocketNotifier, QTimer, Signal

# quadro valido: 03 xx 40 <estado> <nivel>
# O 2o byte identifica variantes de protocolo: E5 usa porcentagem direta;
# 10 (X6 observado) usa décimos de carga (0..10), convertidos em porcentagem.
# O que separa bateria do "falso zero" do enlace é o 3o byte:
# 0x40 = quadro de bateria; 0x01 = enlace piscando.
FRAME_HEAD = 0x03
FRAME_KIND = 0x40
FRAME_LEN = 5

# com o cabo/base ligado o mouse sai do radio e aparece como outro dispositivo USB
CHARGE_USB_IDS = {("1d57", "2155"), ("1d57", "fa61")}

ST_BATTERY = 0x01
ST_CHARGING = 0x03

# o mouse emite a cada ~2s; abaixo disso e so folga para um quadro perdido
ASLEEP_AFTER = 30.0
REOPEN_EVERY_MS = 1000

STATE_DIR = Path.home() / ".local/state/attackshark-tray"
LEVEL_FILE = STATE_DIR / "ultimo_nivel.json"


def find_device(cable: bool = False) -> str | None:
    """hidraw da interface vendor do dongle.

    O indice do hidraw muda a cada replug, entao nunca fixar o caminho. E o
    match e no `modalias` da usb_interface porque `idVendor` (usb_device) e
    `bInterfaceNumber` (usb_interface) moram em pais diferentes - a mesma
    armadilha que faz a regra udev ingenua nao casar com nada.
    """
    for node in sorted(glob.glob('/sys/class/hidraw/hidraw*')):
        try:
            with open(os.path.join(node, 'device/../modalias')) as f:
                ma = f.read().strip()
        except OSError:
            continue
        prefix = 'usb:v1D57pFA61' if cable else 'usb:v1D57pFA60'
        if ma.startswith(prefix) and ma.endswith('in02'):
            return '/dev/' + os.path.basename(node)
    return None


@dataclass(frozen=True)
class Reading:
    present: bool = False           # ha valor utilizavel para mostrar
    level: int = 0
    charging: bool = False
    status: str = "absent"          # charging | discharging | asleep | absent
    age: float = 0.0                # segundos desde o ultimo quadro bom
    raw: str = ""                   # ultimo quadro, em hex, para diagnostico
    error: str = ""                 # motivo de nao estar lendo
    cable: bool = False             # conexão USB: nível é o último conhecido
    level_known: bool = True
    usb_live: bool = False

    @property
    def live(self) -> bool:
        """True quando o numero e uma leitura de agora, nao um valor guardado."""
        return self.status in ("charging", "discharging") and (not self.cable or self.usb_live)

    @property
    def label(self) -> str:
        if not self.present:
            return "sem mouse"
        return f"{self.level}%" if self.level_known else "nível desconhecido"

    @property
    def status_en(self) -> str:
        if self.cable:
            if self.usb_live:
                return "conectado pelo cabo — bateria atualizada via USB"
            return "conectado pelo cabo — último nível conhecido (aguardando leitura USB)"
        return {
            "charging": "carregando",
            "discharging": "na bateria",
            "asleep": "mouse dormindo ou desligado",
            "absent": "receptor desconectado",
        }.get(self.status, self.status)


class MouseMonitor(QObject):
    """Escuta o dongle e publica a ultima leitura boa.

    Orientado a evento, nao a polling: o dongle so fala quando quer, entao um
    QSocketNotifier acorda no quadro em vez de acordar a CPU a cada N segundos
    para descobrir que nada mudou.
    """

    changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._fd: int | None = None
        self._path: str = ""
        self._source_cable = False
        self._notifier: QSocketNotifier | None = None
        self._error = ""
        self._last_frame: bytes | None = None
        self._last_ts = 0.0
        self._level = 0
        self._charging = False
        self._cable = False
        self._cable_ts = 0.0
        self._last_frame_count = 0
        self._saved_level = self._load_level()

        self._watch = QTimer(self)
        self._watch.timeout.connect(self._ensure_open)
        self._watch.start(REOPEN_EVERY_MS)
        self._ensure_open()

    # -- abertura ------------------------------------------------------
    def _ensure_open(self) -> None:
        """Abre o dispositivo, ou detecta que ele sumiu. Chamado por timer."""
        wired = find_device(cable=True)
        path = wired or find_device()
        if self._fd is not None:
            if path and path == self._path:
                self._emit_if_stale()
                return
            self._close()

        if path is None:
            self._set_error("")    # ausencia normal, nao e erro
            return
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        except PermissionError:
            self._set_error(f"sem permissão para ler {path} — a regra udev está "
                            "instalada? (udev/70-attackshark-battery.rules)")
            return
        except OSError as exc:
            self._set_error(f"não foi possível abrir {path}: {exc.strerror}")
            return

        self._fd = fd
        self._path = path
        self._source_cable = wired is not None
        self._error = ""
        self._notifier = QSocketNotifier(fd, QSocketNotifier.Read, self)
        self._notifier.activated.connect(self._on_ready)
        self.changed.emit()

    def _close(self) -> None:
        if self._notifier is not None:
            self._notifier.setEnabled(False)
            self._notifier.deleteLater()
            self._notifier = None
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
        self._fd = None
        self._path = ""
        self._source_cable = False
        self._last_frame = None
        self._last_ts = 0.0
        self.changed.emit()

    def _set_error(self, message: str) -> None:
        if message != self._error:
            self._error = message
            self.changed.emit()

    # -- leitura -------------------------------------------------------
    def _on_ready(self) -> None:
        if self._fd is None:
            return
        got = False
        # drena tudo que estiver na fila: interessa o quadro mais novo
        while True:
            try:
                r, _, _ = select.select([self._fd], [], [], 0)
            except OSError:
                self._close()
                return
            if not r:
                break
            try:
                data = os.read(self._fd, 64)
            except BlockingIOError:
                break
            except OSError:
                self._close()
                return
            if not data:
                self._close()
                return
            if self._accept(data):
                got = True
        if got:
            self.changed.emit()

    def _accept(self, data: bytes) -> bool:
        """Guarda o quadro se for um quadro de bateria de verdade."""
        if len(data) < FRAME_LEN or data[0] != FRAME_HEAD or data[2] != FRAME_KIND:
            return False            # inclui o `03 xx 01 00 00` do enlace piscando
        # X6 / variante 0x10: 0A = 10 décimos = 100%, não 10%.
        # Fontes: blak0p/attack-shark-linux docs/protocol-x6.md;
        # Abosmra/rust-shark src/protocol.rs. Não inferir escala pelo nível.
        level = data[4] * (10 if data[1] == 0x10 else 1)
        if level > 100:
            return False
        self._last_frame = bytes(data[:FRAME_LEN])
        self._last_ts = time.time()
        if level != self._level or self._last_frame_count == 0:
            self._save_level(level)
        self._last_frame_count += 1
        self._level = level
        self._charging = data[3] == ST_CHARGING
        return True

    def _emit_if_stale(self) -> None:
        """Avisa quando o mouse cala a boca, para a bandeja mudar de estado."""
        if self._last_ts and time.time() - self._last_ts > ASLEEP_AFTER:
            self.changed.emit()

    # -- resultado -----------------------------------------------------
    # -- carregando pelo cabo/base ---------------------------------------
    @staticmethod
    def _load_level() -> int | None:
        try:
            value = int(json.loads(LEVEL_FILE.read_text())["level"])
        except (OSError, ValueError, KeyError, TypeError):
            return None
        return value if 0 <= value <= 100 else None

    def _save_level(self, level: int) -> None:
        self._saved_level = level
        try:
            LEVEL_FILE.parent.mkdir(parents=True, exist_ok=True)
            LEVEL_FILE.write_text(json.dumps({"level": level, "ts": time.time()}))
        except OSError:
            pass

    def _cable_present(self, now: float) -> bool:
        """O mouse com cabo/base aparece como 1d57:2155. Consulta no maximo a cada 2 s."""
        if now - self._cable_ts < 2.0:
            return self._cable
        self._cable_ts = now
        found = False
        for dev in glob.glob("/sys/bus/usb/devices/*"):
            try:
                vid = Path(dev, "idVendor").read_text().strip().lower()
                pid = Path(dev, "idProduct").read_text().strip().lower()
            except OSError:
                continue
            if (vid, pid) in CHARGE_USB_IDS:
                found = True
                break
        self._cable = found
        return found

    def read(self) -> Reading:
        now = time.time()
        # A captura 1d57:fa61 confirmou 03 10 40 02 NN, com NN na mesma
        # escala de décimos do dongle X6 (normalizada em _accept). O significado exato de ST=02 não é
        # presumido: "charging" é mantido como estado de conexão pelo cabo.
        if (self._source_cable and self._fd is not None
                and self._last_frame is not None and now - self._last_ts <= ASLEEP_AFTER):
            age = now - self._last_ts
            raw = ' '.join(f'{b:02X}' for b in self._last_frame)
            return Reading(True, self._level, True, "charging", age, raw,
                           cable=True, usb_live=True)
        # Sem leitura USB recente, mantém apenas o último valor conhecido.
        if self._cable_present(now):
            level = self._level if self._last_frame is not None else self._saved_level
            age = now - self._last_ts if self._last_ts else 0.0
            return Reading(True, level if level is not None else 0, True,
                           "charging", age, cable=True, level_known=level is not None,
                           error=self._error)
        if self._fd is None:
            return Reading(status="absent", error=self._error or "receptor desconectado")
        if self._last_frame is None:
            return Reading(status="absent",
                           error=self._error or "receptor conectado, aguardando o "
                                 "mouse (dormindo ou fora do rádio)")

        age = now - self._last_ts
        raw = ' '.join(f'{b:02X}' for b in self._last_frame)
        if age > ASLEEP_AFTER:
            # o mouse parou de falar. O nivel que ele disse por ultimo continua
            # valendo - fingir 0% aqui seria alarme sobre um numero inventado.
            return Reading(True, self._level, self._charging, "asleep", age, raw)
        return Reading(True, self._level, self._charging,
                       "charging" if self._charging else "discharging", age, raw)

    def diagnostics(self) -> str:
        from . import __version__
        r = self.read()
        lines = [f"app             attackshark-tray {__version__}"]
        if self._path:
            lines.append(f"dispositivo     {self._path}")
        else:
            found = find_device(cable=True) or find_device()
            lines.append(f"dispositivo     fechado ({found or 'nenhum receptor encontrado'})")
        lines += [
            f"último quadro   {r.raw or '(nenhum)'}",
            f"idade do quadro {r.age:.1f}s",
            f"nível           {r.label}",
            f"estado          {r.status_en}",
            f"cabo/base USB   {'detectado' if r.cable else 'não detectado'}",
            f"leitura atual   {'USB' if r.usb_live else 'rádio' if r.live else 'último nível conhecido'}",
        ]
        if r.error:
            lines.append(f"erro            {r.error}")
        return "\n".join(lines)
