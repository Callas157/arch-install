import struct
import unittest
from callas_chat.voice import mono_pcm16


class VoiceTests(unittest.TestCase):
    def test_stereo_float_is_mixed_and_clamped(self):
        raw = struct.pack('<ffff', 1.0, -1.0, 2.0, 2.0)
        pcm = mono_pcm16(raw, 'float', 2)
        self.assertEqual(struct.unpack('<hh', pcm), (0, 32767))

    def test_int16_mono_preserved(self):
        raw = struct.pack('<hh', 1200, -300)
        self.assertEqual(mono_pcm16(raw, 'int16', 1), raw)

    def test_stereo_integer_mixed(self):
        self.assertEqual(struct.unpack('<h', mono_pcm16(struct.pack('<hh', 100, 300), 'int16', 2)), (200,))

    def test_gain_amplifies_quiet_speech_without_clipping(self):
        from callas_chat.voice import amplify_pcm16
        quiet = struct.pack('<hh', 1000, -2000)
        self.assertEqual(struct.unpack('<hh', amplify_pcm16(quiet, 3)), (3000, -6000))
        loud = struct.pack('<hh', 30000, -30000)
        self.assertEqual(struct.unpack('<hh', amplify_pcm16(loud, 3)), (30000, -30000))

    def test_stop_drains_remaining_audio_before_final_result(self):
        from unittest.mock import Mock
        from callas_chat.voice import Voice
        voice = Voice()
        voice.worker = Mock(stopping=False)
        voice.source = Mock()
        voice.device = Mock()
        order = []
        voice.read = lambda: order.append('drain')
        voice.source.stop.side_effect = lambda: order.append('source-stop')
        voice.worker.stop.side_effect = lambda: order.append('recognizer-stop')
        voice.stop()
        self.assertEqual(order, ['drain', 'source-stop', 'recognizer-stop'])

    def test_whisper_receives_numeric_audio_and_fixed_portuguese(self):
        import numpy as np
        from types import SimpleNamespace
        from unittest.mock import Mock
        from callas_chat.voice import transcribe_pcm
        model = Mock()
        model.transcribe.return_value = (iter([SimpleNamespace(text=' Tá muito ruinzinho ainda, cara.')]), None)
        raw = struct.pack('<h', 1000) * 16000
        text = transcribe_pcm(model, raw, 16000)
        self.assertEqual(text, 'Tá muito ruinzinho ainda, cara.')
        args, kwargs = model.transcribe.call_args
        self.assertEqual(kwargs['language'], 'pt')
        self.assertTrue(kwargs['vad_filter'])
        self.assertIsInstance(args[0], np.ndarray)
        self.assertEqual(args[0].dtype, np.float32)
        self.assertEqual(len(args[0]), 16000)
        np.testing.assert_allclose(args[0], 1000 / 32768)

    def test_resampling_preserves_speech_and_filters_aliasing(self):
        import numpy as np
        from callas_chat.voice import pcm_samples
        rate = 48000
        t = np.arange(rate) / rate
        speech = (np.sin(2*np.pi*1000*t) * 16000).astype('<i2').tobytes()
        ultrasonic = (np.sin(2*np.pi*12000*t) * 16000).astype('<i2').tobytes()
        output = pcm_samples(speech, rate)
        rejected = pcm_samples(ultrasonic, rate)
        self.assertEqual(len(output), 16000)
        self.assertGreater(float(np.std(output)), .3)
        self.assertLess(float(np.std(rejected[100:-100])), .005)


    def test_whisper_worker_keeps_audio_until_stop(self):
        import sys
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        from callas_chat.voice import Recognizer
        model = Mock()
        model.transcribe.return_value = (iter([SimpleNamespace(text=' uma frase inteira')]), None)
        worker = Recognizer('/modelo', 48000)
        worker.audio.put(struct.pack('<h', 2000) * 48000)
        worker.audio.put(None)
        texts, failures = [], []
        worker.text.connect(texts.append)
        worker.failure.connect(failures.append)
        with patch.dict(sys.modules, {'faster_whisper': SimpleNamespace(WhisperModel=Mock(return_value=model))}):
            worker.run()
        self.assertEqual(failures, [])
        self.assertEqual(texts, ['uma frase inteira'])
        self.assertEqual(model.transcribe.call_count, 1)

    def test_stop_preserves_audio_even_when_queue_is_full(self):
        from callas_chat.voice import Recognizer
        worker = Recognizer('/modelo', 16000)
        for i in range(100): worker.audio.put_nowait(bytes([i]))
        worker.stop()
        self.assertTrue(worker.stopping)
        self.assertEqual([worker.audio.get_nowait() for _ in range(100)], [bytes([i]) for i in range(100)])

    def test_meter_uses_actual_captured_pcm(self):
        import queue
        from unittest.mock import Mock
        from PySide6.QtMultimedia import QAudioFormat
        from callas_chat.voice import Voice
        voice = Voice()
        voice.format = QAudioFormat()
        voice.format.setSampleRate(16000)
        voice.format.setChannelCount(1)
        voice.format.setSampleFormat(QAudioFormat.Int16)
        voice.worker = Mock(audio=queue.Queue())
        voice.device = Mock()
        levels = []
        voice.level.connect(levels.append)
        voice.device.readAll.return_value = b'\0\0' * 160
        voice.read()
        voice.device.readAll.return_value = struct.pack('<h', 5000) * 160
        voice.read()
        self.assertEqual(levels[0], 0)
        self.assertGreater(levels[1], .4)
        self.assertLessEqual(levels[1], 1)
