"""Live recording feedback inside the message composer."""
import math
from PySide6.QtCore import Qt, QTimer, QElapsedTimer, QRectF
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QSizePolicy


class Waveform(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('recordingWaveform')
        self.values = [0.0] * 64
        self.phase = 'idle'
        self.frame = 0
        self.setMinimumHeight(24)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAccessibleName('Nível do áudio do microfone')

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        spacing = self.width() / len(self.values)
        width = max(1.0, min(4.0, spacing * .55))
        for i, value in enumerate(self.values):
            if self.phase != 'recording':
                value = .06 + .16 * (1 + math.sin(i * .3 - self.frame * .2)) / 2
            height = 3 + value * max(0, self.height() - 6)
            color = QColor('#9aa9ff' if self.phase != 'recording' else '#ed8d9f')
            color.setAlphaF(.45 + .55 * min(1.0, value + .2))
            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(i * spacing, (self.height() - height) / 2,
                                          width, height), width / 2, width / 2)


class RecorderPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('recorderPanel')
        self.phase = 'idle'
        self.target = self.smoothed = 0.0
        self.clock = QElapsedTimer()
        self.last_level = QElapsedTimer()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(2)
        top = QHBoxLayout()
        self.caption = QLabel()
        self.caption.setObjectName('recordingCaption')
        self.elapsed = QLabel('00:00')
        self.elapsed.setObjectName('recordingTime')
        self.elapsed.setAccessibleName('Duração da gravação')
        top.addWidget(self.caption)
        top.addStretch()
        top.addWidget(self.elapsed)
        layout.addLayout(top)
        self.waveform = Waveform()
        layout.addWidget(self.waveform, 1)
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.advance)

    def set_phase(self, phase):
        if phase == self.phase: return
        self.phase = self.waveform.phase = phase
        if phase == 'idle':
            self.timer.stop()
            self.target = self.smoothed = 0.0
            self.clock.invalidate()
            self.last_level.invalidate()
            return
        if phase in ('preparing', 'recording'):
            self.waveform.values = [0.0] * 64
            self.target = self.smoothed = 0.0
            self.elapsed.setText('00:00')
            self.last_level.invalidate()
        if phase == 'recording': self.clock.start()
        self.caption.setText({'preparing': '◌  Preparando microfone…',
                              'recording': '●  Gravando áudio',
                              'transcribing': '◌  Transcrevendo áudio…'}[phase])
        self.setAccessibleName(self.caption.text())
        self.timer.start()
        self.waveform.update()

    def set_level(self, value):
        if self.phase != 'recording': return
        self.target = max(0.0, min(1.0, value))
        self.last_level.start()

    def advance(self):
        if self.phase == 'recording':
            if not self.last_level.isValid() or self.last_level.elapsed() > 250:
                self.target = 0.0
            self.smoothed += (self.target - self.smoothed) * .5
            self.waveform.values = self.waveform.values[1:] + [self.smoothed]
            seconds = self.clock.elapsed() // 1000 if self.clock.isValid() else 0
            self.elapsed.setText(f'{seconds // 60:02d}:{seconds % 60:02d}')
        self.waveform.frame += 1
        self.waveform.update()
