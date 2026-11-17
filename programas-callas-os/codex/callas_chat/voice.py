"""Explicit microphone capture and offline Portuguese dictation."""
import array
import math
import queue
from pathlib import Path
from functools import lru_cache
from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices
from .model_files import whisper_ready


def mono_pcm16(data, kind, channels):
    if kind == 'int16' and channels == 1:
        return data
    code = {'int16': 'h', 'int32': 'i', 'float': 'f', 'uint8': 'B'}[kind]
    samples = array.array(code)
    samples.frombytes(data)
    output = array.array('h')
    for i in range(0, len(samples), channels):
        value = sum(samples[i:i+channels])/channels
        if kind == 'float': value *= 32767
        elif kind == 'int32': value /= 65536
        elif kind == 'uint8': value = (value-128)*256
        output.append(max(-32768, min(32767, int(value))))
    return output.tobytes()


def amplify_pcm16(data, gain):
    """Boost quiet speech, limiting gain per buffer to preserve loud speech."""
    samples = array.array('h')
    samples.frombytes(data)
    peak = max((abs(value) for value in samples), default=0)
    factor = min(max(1.0, min(6.0, float(gain))), 30000 / peak) if peak else 1.0
    factor = max(1.0, factor)
    return array.array('h', (max(-32768, min(32767, round(value * factor)))
                            for value in samples)).tobytes()


def pcm_samples(pcm, rate):
    """Convert native mono PCM to Whisper's 16 kHz float32 input.

    Avoid PyAV's localized error decoding inside the Qt worker. Polyphase
    resampling also filters frequencies above the target Nyquist limit.
    """
    import numpy as np
    samples = np.frombuffer(pcm, dtype='<i2').astype(np.float32) / 32768.0
    if rate != 16000 and samples.size:
        from scipy.signal import resample_poly
        divisor = math.gcd(rate, 16000)
        samples = resample_poly(samples, 16000 // divisor, rate // divisor)
    return np.ascontiguousarray(samples, dtype=np.float32)


@lru_cache(maxsize=1)
def load_model(model_path):
    """Keep the local model resident across consecutive dictations."""
    from faster_whisper import WhisperModel
    return WhisperModel(str(model_path), device='cpu', compute_type='int8',
                        cpu_threads=8, local_files_only=True)


def transcribe_pcm(model, pcm, rate):
    """Pass the full utterance as samples, bypassing file decoding entirely."""
    if not pcm: return ''
    audio = pcm_samples(pcm, rate)
    segments, _ = model.transcribe(
        audio, language='pt', task='transcribe', beam_size=1,
        temperature=0, vad_filter=True,
        vad_parameters={'min_silence_duration_ms': 700, 'speech_pad_ms': 400},
        condition_on_previous_text=False,
    )
    return ' '.join(segment.text.strip() for segment in segments if segment.text.strip())


class Recognizer(QThread):
    loaded = Signal()
    text = Signal(str)
    progress = Signal(str)
    failure = Signal(str)

    def __init__(self, model_path, rate, parent=None):
        super().__init__(parent)
        self.model_path, self.rate = model_path, rate
        self.audio = queue.Queue()
        self.stopping = False

    def run(self):
        try:
            model = load_model(str(self.model_path))
            self.loaded.emit()
            recording = bytearray()
            while True:
                try:
                    data = self.audio.get(timeout=0.1)
                except queue.Empty:
                    if self.stopping: break
                    continue
                if data is None: break
                recording.extend(data)
            self.progress.emit('Transcrevendo em português… aguarde alguns segundos.')
            value = transcribe_pcm(model, bytes(recording), self.rate)
            if value: self.text.emit(value)
            elif recording:
                self.failure.emit('Não identifiquei fala nessa gravação. Confira o microfone selecionado no KDE e tente novamente.')
        except Exception as exc:
            self.failure.emit('Não consegui transcrever o ditado: '+str(exc))

    def stop(self):
        # The worker drains every queued frame before transcription. No audio
        # is evicted to make room for a sentinel when the queue is full.
        self.stopping = True



class Voice(QObject):
    text = Signal(str)
    status = Signal(str)
    error = Signal(str)
    active = Signal(bool)
    phase = Signal(str)
    level = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = self.source = self.device = None
        self.tail = b''
        self.recording = False
        self.gain = 2.0

    def start(self):
        if self.worker:
            self.stop()
            return
        audio = QMediaDevices.defaultAudioInput()
        if audio.isNull():
            self.error.emit('Nenhum microfone disponível. Conecte um microfone e confira as configurações de áudio do KDE.')
            return
        import os
        root = Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share')))
        model = root/'callas-chat/models/whisper-medium'
        if not whisper_ready(model):
            self.error.emit('O modelo de voz em português ainda não foi instalado. Execute instalar-callas-chat.sh novamente.')
            return
        fmt = QAudioFormat()
        fmt.setSampleRate(16000)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.Int16)
        if not audio.isFormatSupported(fmt): fmt = audio.preferredFormat()
        self.format = fmt
        self.recording = True
        self.active.emit(True)
        self.phase.emit('preparing')
        self.status.emit('Preparando microfone…')
        self.worker = Recognizer(model, fmt.sampleRate(), self)
        self.worker.text.connect(self.text)
        self.worker.progress.connect(self.status)
        self.worker.failure.connect(self.error)
        self.worker.finished.connect(self.finished)
        self.worker.start()
        self.capture(audio, fmt)

    def capture(self, audio, fmt):
        if not self.recording: return
        self.tail = b''
        self.source = QAudioSource(audio, fmt, self)
        self.source.setVolume(1.0)
        self.source.stateChanged.connect(self.audio_state)
        self.device = self.source.start()
        if not self.device:
            self.error.emit('Não foi possível acessar o microfone.')
            self.stop()
            return
        self.device.readyRead.connect(self.read)
        self.phase.emit('recording')
        self.status.emit('Gravando… fale em português e clique em Parar ditado para transcrever.')

    def audio_state(self, state):
        from PySide6.QtMultimedia import QtAudio
        if self.source and self.source.error() != QtAudio.NoError:
            self.error.emit('O microfone foi interrompido. Confira o dispositivo nas configurações do KDE.')
            self.stop()

    def read(self):
        if not self.device or not self.worker: return
        data = self.tail + bytes(self.device.readAll())
        frame = self.format.bytesPerFrame()
        size = len(data) - len(data) % frame
        self.tail = data[size:]
        kind = {QAudioFormat.Int16: 'int16', QAudioFormat.Int32: 'int32',
                QAudioFormat.Float: 'float', QAudioFormat.UInt8: 'uint8'}[self.format.sampleFormat()]
        pcm = mono_pcm16(data[:size], kind, self.format.channelCount())
        boosted = amplify_pcm16(pcm, self.gain)
        samples = array.array('h')
        samples.frombytes(boosted)
        rms = math.sqrt(sum(value * value for value in samples) / len(samples)) if samples else 0
        db = 20 * math.log10(max(rms, 1) / 32768)
        self.level.emit(max(0.0, min(1.0, (db + 60) / 52)))
        try: self.worker.audio.put_nowait(boosted)
        except queue.Full:
            self.recording = False
            self.error.emit('O reconhecimento não acompanhou o áudio. Pare o ditado e tente frases menores.')
            self.stop()

    def stop(self):
        self.recording = False
        if self.worker and not self.worker.stopping:
            self.phase.emit('transcribing')
            self.status.emit('Transcrevendo em português… aguarde alguns segundos.')
        if self.source:
            if self.device and self.worker and not self.worker.stopping and not getattr(self, "draining", False):
                self.draining = True
                self.read()
                self.draining = False
            if not self.source: return
            self.source.stop()
            self.source.deleteLater()
            self.source = self.device = None
        if self.worker: self.worker.stop()

    def finished(self):
        self.stop()
        if self.worker: self.worker.deleteLater()
        self.worker = None
        self.active.emit(False)
        self.phase.emit('idle')
        self.status.emit('Ditado finalizado. Revise o texto antes de enviar.')

    def close(self):
        self.stop()
        # Model loading cannot be interrupted inside native Whisper. The owner
        # must remain alive until finished, rather than destroying a QThread.
        return self.worker is None or self.worker.isFinished()
