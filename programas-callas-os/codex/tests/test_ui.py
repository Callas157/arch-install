import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from PySide6.QtCore import QObject, Signal, QMimeData, QTimer, QSettings, QUrl, QPoint, QPointF, Qt
from PySide6.QtGui import QImage, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication
from callas_chat.ui import Window
from callas_chat.backend import Backend, codex_path

APP = QApplication.instance() or QApplication([])


class FakeBackend(QObject):
    ready = Signal()
    event = Signal(str, dict)
    error = Signal(str)
    disconnected = Signal()
    server_request = Signal(object)
    connected = True
    def __init__(self):
        super().__init__()
        self.requests = []
    def start(self): pass
    def close(self): pass
    def request(self, method, params, callback=None, failed=None):
        self.requests.append((method, params, callback, failed))
    def reply(self, *args, **kwargs): pass


class UiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = os.environ.get('XDG_DATA_HOME')
        os.environ['XDG_DATA_HOME'] = self.temp.name
        self.preferences = patch('callas_chat.ui.QSettings', lambda *args: QSettings(str(Path(self.temp.name)/'settings.ini'), QSettings.IniFormat))
        self.preferences.start()
        self.backend = FakeBackend()
        self.window = Window(self.backend, auto_start=False)

    def tearDown(self):
        self.window.busy = False
        self.window.close()
        APP.processEvents()
        self.preferences.stop()
        if self.old is None: os.environ.pop('XDG_DATA_HOME', None)
        else: os.environ['XDG_DATA_HOME'] = self.old
        self.temp.cleanup()

    def test_images_are_visible_before_send_and_in_conversation(self):
        from callas_chat.ui import ImagePreview
        image = QImage(1200, 600, QImage.Format_RGB32)
        image.fill(Qt.green)
        self.window.attach_image(image)
        self.window.show()
        APP.processEvents()
        preview = self.window.attachment_area.findChild(ImagePreview)
        self.assertGreater(preview.width(), 250)
        self.assertGreater(preview.height(), 100)
        self.window.thread_id = 'test-thread'
        self.window.send()
        APP.processEvents()
        card = self.window.message_layout.itemAt(0).widget()
        photo = card.findChild(ImagePreview)
        self.assertIsNotNone(photo)
        self.assertFalse(photo.source.isNull())
        self.assertNotIn('imagem(ns)', card.text)
        self.assertFalse(card.body.isVisible())
        self.assertFalse(self.window.attachment_area.isVisible())
        self.window.resize(850, 750)
        for _ in range(8): APP.processEvents()
        self.assertLessEqual(photo.width(), card.width())
        self.assertAlmostEqual(photo.pixmap().width() / photo.pixmap().height(), 2, places=1)

    def test_remove_image_hides_empty_attachment_area(self):
        from PySide6.QtWidgets import QPushButton
        image = QImage(100, 100, QImage.Format_RGB32)
        image.fill(Qt.green)
        self.window.attach_image(image)
        self.window.attachment_area.findChild(QPushButton).click()
        self.assertEqual(self.window.images, [])
        self.assertTrue(self.window.attachment_area.isHidden())

    def test_codex_brand_and_login_for_new_account(self):
        self.assertEqual(self.window.windowTitle(), 'Codex')
        self.assertFalse(self.window.windowIcon().isNull())
        self.window.account_loaded({'account': None})
        self.assertFalse(self.window.login_button.isHidden())
        self.window.login_button.click()
        method, params, callback, _ = self.backend.requests[-1]
        self.assertEqual((method, params), ('account/login/start', {'type': 'chatgpt'}))
        with patch('callas_chat.ui.QDesktopServices.openUrl') as opened:
            callback({'authUrl': 'https://auth.openai.com/example'})
            opened.assert_called_once()
        self.window.account_loaded({'account': {'type': 'chatgpt'}})
        self.assertTrue(self.window.login_button.isHidden())

    def test_long_command_fits_after_window_shrinks(self):
        self.window.clear_messages()
        card = self.window.add_card('assistant', '```bash\n' + 'verylongpath' * 150 + '\n```\n' + '\n```sh\necho ok\n```' * 12)
        card.body.show()
        self.window.show()
        for width in (1500, 850, 1100, 850):
            self.window.resize(width, 750)
            for _ in range(8): APP.processEvents()
            self.assertLessEqual(self.window.messages.width(), self.window.scroll.viewport().width())
            self.assertLessEqual(card.body.document().idealWidth(), card.body.viewport().width() + 1)
            self.assertLessEqual(card.body.document().size().height(), card.body.height())

    def test_expanded_activity_wraps_long_output(self):
        self.window.clear_messages()
        card = self.window.add_card('tool', 'resultado/' * 800)
        card.parentWidget().toggle.click()
        card.body.show()
        self.window.resize(850, 750)
        self.window.show()
        for _ in range(8): APP.processEvents()
        self.assertLessEqual(self.window.messages.width(), self.window.scroll.viewport().width())
        self.assertLessEqual(card.body.document().idealWidth(), card.body.viewport().width() + 1)
        self.assertLessEqual(card.body.document().size().height(), card.body.height())

    def test_collapsed_activity_is_one_compact_row(self):
        from PySide6.QtWidgets import QPushButton
        self.window.clear_messages()
        card = self.window.add_card('tool', '```sh\necho teste\n```')
        card.parentWidget().toggle.click()
        self.window.show()
        for _ in range(8): APP.processEvents()
        self.assertLessEqual(card.height(), 48)
        buttons = card.findChildren(QPushButton)
        self.assertEqual(len([b for b in buttons if b.isVisible()]), 1)
        buttons[0].click()
        APP.processEvents()
        self.assertTrue(card.body.isVisible())
        self.assertIn('echo teste', card.body.toPlainText())

    def test_consecutive_executions_share_collapsed_group(self):
        self.window.clear_messages()
        first = self.window.add_card('tool', 'primeiro', 'one')
        second = self.window.add_card('tool', 'segundo', 'two')
        self.window.show()
        APP.processEvents()
        group = self.window.message_layout.itemAt(0).widget()
        self.assertEqual(self.window.message_layout.count(), 1)
        self.assertIn('2 execuções', group.toggle.text())
        self.assertFalse(first.isVisible())
        group.toggle.click()
        APP.processEvents()
        self.assertTrue(first.isVisible())
        self.assertTrue(second.isVisible())
        second.set_text('saída atualizada')
        self.assertEqual(self.window.cards['two'].body.toPlainText(), 'saída atualizada')
        self.window.add_card('assistant', 'resposta')
        self.window.add_card('tool', 'terceiro')
        self.assertEqual(self.window.message_layout.count(), 3)
        self.window.clear_messages()
        self.window.add_card('tool', 'outra conversa')
        self.assertEqual(self.window.message_layout.count(), 1)

    def test_copy_appears_on_hover_without_changing_card_height(self):
        from PySide6.QtCore import QEvent
        self.window.clear_messages()
        card = self.window.add_card('assistant', 'texto para copiar')
        self.window.show()
        APP.processEvents()
        height = card.height()
        self.assertTrue(card.copy_button.isHidden())
        from PySide6.QtGui import QEnterEvent
        from PySide6.QtCore import QPointF
        APP.sendEvent(card, QEnterEvent(QPointF(), QPointF(), QPointF()))
        APP.processEvents()
        self.assertTrue(card.copy_button.isVisible())
        card.copy_button.click()
        self.assertEqual(APP.clipboard().text(), 'texto para copiar')
        APP.sendEvent(card, QEvent(QEvent.Leave))
        APP.processEvents()
        self.assertTrue(card.copy_button.isHidden())
        self.assertEqual(card.height(), height)

    def test_heading_keeps_full_title_in_tooltip(self):
        title = 'Uma conversa muito longa ' * 20
        self.window.heading.setText(title)
        self.window.show()
        self.window.resize(850, 750)
        APP.processEvents()
        self.assertEqual(self.window.heading.toolTip(), title)
        self.assertEqual(self.window.heading.text(), title)
        self.assertFalse(self.window.heading.wordWrap())

    def test_pasted_photo_waits_for_send_and_is_private(self):
        image = QImage(20, 20, QImage.Format_RGB32)
        image.fill(0xff336699)
        mime = QMimeData()
        mime.setImageData(image)
        self.window.editor.insertFromMimeData(mime)
        self.assertEqual(len(self.window.images), 1)
        path = Path(self.window.images[0])
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.backend.requests, [])
        self.window.editor.setPlainText('O que aparece aqui?')
        self.window.send()
        method, params, callback, _ = self.backend.requests[-1]
        self.assertEqual(method, 'thread/start')
        callback({'approvalPolicy': 'never', 'sandbox': {'type': 'dangerFullAccess'}, 'thread': {'id': 'thread'}})
        method, params, _, _ = self.backend.requests[-1]
        self.assertEqual(method, 'turn/start')
        self.assertEqual(params['input'][1], {'type': 'localImage', 'path': str(path)})

    def drop_files(self, target, urls):
        self.window.show()
        APP.processEvents()
        mime = QMimeData()
        mime.setUrls(urls)
        enter = QDragEnterEvent(QPoint(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
        APP.sendEvent(target, enter)
        drop = QDropEvent(QPointF(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
        APP.sendEvent(target, drop)
        return enter, drop

    def test_dropped_logs_on_editor_and_conversation_wait_for_send(self):
        for target in (self.window.editor.viewport(), self.window.scroll.viewport()):
            with self.subTest(target=target):
                path = Path(self.temp.name)/'sistema com espaços.log'
                path.write_text('falha no serviço')
                self.window.clear_images()
                self.window.editor.setPlainText('investigue')
                enter, drop = self.drop_files(target, [QUrl.fromLocalFile(str(path))])
                self.assertTrue(enter.isAccepted())
                self.assertTrue(drop.isAccepted())
                self.assertEqual(self.window.text_files[str(path)], 'falha no serviço')
                self.assertEqual(self.window.editor.toPlainText(), 'investigue')
                self.assertEqual(self.backend.requests, [])

    def test_drop_on_message_accepts_multiple_files_and_photo(self):
        card = self.window.add_card('assistant', 'Uma resposta')
        paths = [Path(self.temp.name)/'primeiro.log', Path(self.temp.name)/'segundo.txt']
        for path in paths: path.write_text(path.name)
        photo = Path(self.temp.name)/'foto.png'
        image = QImage(10, 10, QImage.Format_RGB32)
        image.fill(0xff336699)
        image.save(str(photo))
        _, drop = self.drop_files(card.body.viewport(), [QUrl.fromLocalFile(str(p)) for p in [*paths, photo]])
        self.assertTrue(drop.isAccepted())
        self.assertEqual(set(self.window.text_files), set(map(str, paths)))
        self.assertEqual(len(self.window.images), 1)
        self.assertEqual(self.backend.requests, [])

    def test_new_conversation_registers_native_drop_target_and_sends_first_log(self):
        self.window.thread_id = 'previous-thread'
        self.window.new_chat()
        self.window.show()
        APP.processEvents()
        # Qt routes native file-manager drags to the first accepting ancestor.
        # The welcome screen must have its own target, independent of the editor.
        target = self.window.welcome_card
        while target is not None and not target.acceptDrops():
            target = target.parentWidget()
        self.assertIsNotNone(target)
        self.assertTrue(target is self.window.drop_area or self.window.drop_area.isAncestorOf(target),
                        'The empty conversation must register a native drop target')
        path = Path(self.temp.name)/'primeira mensagem.log'
        path.write_text('falha antes da primeira mensagem')
        enter, drop = self.drop_files(target, [QUrl.fromLocalFile(str(path))])
        self.assertTrue(enter.isAccepted())
        self.assertTrue(drop.isAccepted())
        self.assertFalse(self.window.thread_id)
        self.assertEqual(self.window.text_files[str(path)], 'falha antes da primeira mensagem')
        self.assertEqual(self.backend.requests, [])
        self.window.send()
        self.assertEqual(self.backend.requests[-1][0], 'thread/start')
        self.backend.requests[-1][2]({'approvalPolicy': 'never', 'sandbox': {'type': 'dangerFullAccess'}, 'thread': {'id': 'new-thread'}})
        method, params, _, _ = self.backend.requests[-1]
        self.assertEqual(method, 'turn/start')
        self.assertEqual(params['threadId'], 'new-thread')
        self.assertIn('falha antes da primeira mensagem', params['input'][0]['text'])

    def test_drop_preserves_attachment_validation(self):
        directory = Path(self.temp.name)/'pasta'
        directory.mkdir()
        binary = Path(self.temp.name)/'binario.log'
        binary.write_bytes(b'abc\x00def')
        large = Path(self.temp.name)/'grande.log'
        large.write_bytes(b'x' * (1024 * 1024 + 1))
        for path in (directory, binary, large):
            with self.subTest(path=path):
                self.drop_files(self.window.scroll.viewport(), [QUrl.fromLocalFile(str(path))])
                self.assertEqual(self.window.text_files, {})
                self.assertTrue(self.window.error_box.text())
        self.assertEqual(self.backend.requests, [])

    def test_drop_outside_conversation_does_not_attach(self):
        path = Path(self.temp.name)/'erro.log'
        path.write_text('erro')
        self.drop_files(self.window.history.viewport(), [QUrl.fromLocalFile(str(path))])
        self.assertEqual(self.window.text_files, {})
        self.drop_files(self.window.editor.viewport(), [QUrl('https://example.org/erro.log')])
        self.assertEqual(self.window.text_files, {})
        self.assertEqual(self.backend.requests, [])

    def test_dropping_file_while_busy_does_not_change_draft(self):
        path = Path(self.temp.name)/'erro.log'
        path.write_text('erro')
        self.window.set_busy(True)
        self.drop_files(self.window.scroll.viewport(), [QUrl.fromLocalFile(str(path))])
        self.assertEqual(self.window.text_files, {})
        self.assertEqual(self.backend.requests, [])

    def test_document_tiles_remove_and_send_without_visible_paths(self):
        from callas_chat.ui import FileAttachment
        path = Path(self.temp.name)/'Arquivo de texto.txt'
        path.write_text('conteúdo do anexo')
        self.window.attach_files([str(path)])
        tile = self.window.attachment_area.findChild(FileAttachment)
        self.assertEqual(tile.filename.text(), path.name)
        tile.remove_button.click()
        self.assertEqual(self.window.text_files, {})
        APP.processEvents()
        self.window.attach_files([str(path)])
        self.window.editor.setPlainText('Veja este arquivo')
        self.window.thread_id = 'thread'
        self.window.send()
        card = self.window.message_layout.itemAt(0).widget()
        sent = card.findChild(FileAttachment)
        self.assertEqual(sent.filename.text(), path.name)
        self.assertIsNone(sent.remove_button)
        self.assertEqual(card.body.toPlainText(), 'Veja este arquivo')
        payload = self.backend.requests[-1][1]['input'][0]['text']
        self.assertIn('conteúdo do anexo', payload)
        self.assertEqual(self.window.text_files, {})

    def test_log_attachment_sends_snapshot_only_on_send(self):
        path = Path(self.temp.name)/'sistema.log'
        path.write_text('falha na inicialização\nserviço indisponível')
        self.window.attach_files([str(path)])
        self.assertEqual(self.backend.requests, [])
        path.write_text('alterado depois de anexar')
        self.window.send()
        self.backend.requests[-1][2]({'approvalPolicy': 'never', 'sandbox': {'type': 'dangerFullAccess'}, 'thread': {'id': 'thread'}})
        params = self.backend.requests[-1][1]
        self.assertIn('falha na inicialização', params['input'][0]['text'])
        self.assertIn('sistema.log', params['input'][0]['text'])
        self.assertNotIn('alterado depois', params['input'][0]['text'])
        self.assertEqual(len(params['input']), 1)

    def test_log_rejected_when_larger_than_limit(self):
        path = Path(self.temp.name)/'grande.log'
        path.write_bytes(b'x' * (1024 * 1024 + 1))
        self.window.attach_files([str(path)])
        self.assertEqual(self.window.text_files, {})
        self.assertIn('1 MB', self.window.error_box.text())

    def test_log_failure_restores_attachment_and_message(self):
        path = Path(self.temp.name)/'erro.log'
        path.write_text('erro importante')
        self.window.thread_id = 'thread'
        self.window.attach_files([str(path)])
        self.window.editor.setPlainText('investigue')
        self.window.send()
        self.assertEqual(self.window.text_files, {})
        self.backend.requests[-1][3]('falha de conexão')
        self.assertEqual(self.window.text_files[str(path)], 'erro importante')
        self.assertEqual(self.window.editor.toPlainText(), 'investigue')

    def test_binary_attachment_is_rejected(self):
        path = Path(self.temp.name)/'binario.txt'
        path.write_bytes(b'abc\x00def')
        self.window.attach_files([str(path)])
        self.assertTrue(self.window.error_box.text())
        self.assertEqual(self.backend.requests, [])

    def test_events_from_another_conversation_are_ignored(self):
        self.window.thread_id = 'current'
        self.window.on_event('item/agentMessage/delta', {'threadId': 'other', 'itemId': 'x', 'delta': 'wrong'})
        self.assertNotIn('x', self.window.cards)
        self.window.on_event('item/agentMessage/delta', {'threadId': 'current', 'itemId': 'y', 'delta': 'Olá'})
        self.window.flush_streams()
        self.assertEqual(self.window.cards['y'].text, 'Olá')

    def test_composer_grows_for_wrapped_dictation_and_shrinks_when_cleared(self):
        self.window.show()
        self.window.resize(850, 750)
        APP.processEvents()
        original = self.window.composer_stack.height()
        self.window.dictated('Uma frase longa para revisar o ditado. ' * 80)
        for _ in range(8): APP.processEvents()
        editor = self.window.editor
        self.assertGreater(self.window.composer_stack.height(), original)
        # Four full lines plus the document margins fit without clipping.
        self.assertGreaterEqual(editor.viewport().height(), 4 * editor.fontMetrics().lineSpacing() + 2 * editor.document().documentMargin())
        self.assertLess(self.window.composer_stack.height(), 160)
        self.assertGreater(editor.verticalScrollBar().maximum(), 0)
        self.window.voice.phase.emit('recording')
        self.assertEqual(self.window.composer_stack.height(), original)
        self.window.voice.phase.emit('idle')
        for _ in range(8): APP.processEvents()
        self.assertGreater(self.window.composer_stack.height(), original)
        editor.clear()
        for _ in range(8): APP.processEvents()
        self.assertEqual(self.window.composer_stack.height(), original)

    def test_composer_adapts_to_font_size_for_four_lines(self):
        from PySide6.QtGui import QFont
        self.window.show()
        self.window.editor.setFont(QFont('Noto Sans', 22))
        self.window.editor.setPlainText('linha\n' * 10)
        for _ in range(8): APP.processEvents()
        editor = self.window.editor
        self.assertGreaterEqual(editor.viewport().height(), 4 * editor.fontMetrics().lineSpacing() + 2 * editor.document().documentMargin())

    def test_recorder_replaces_editor_and_preserves_draft(self):
        self.window.editor.setPlainText('Texto que já estava aqui.')
        self.window.voice.active.emit(True)
        self.window.voice.phase.emit('preparing')
        self.assertIs(self.window.composer_stack.currentWidget(), self.window.recorder)
        self.assertIn('Preparando', self.window.recorder.caption.text())
        self.window.voice.phase.emit('recording')
        self.assertTrue(self.window.recorder.timer.isActive())
        self.window.voice.level.emit(.8)
        self.window.recorder.advance()
        self.assertGreater(max(self.window.recorder.waveform.values), 0)
        self.window.voice.phase.emit('transcribing')
        self.assertIn('Transcrevendo', self.window.recorder.caption.text())
        self.assertFalse(self.window.mic.isEnabled())
        self.window.voice.text.emit('Mais uma frase.')
        self.window.voice.active.emit(False)
        self.window.voice.phase.emit('idle')
        self.assertIs(self.window.composer_stack.currentWidget(), self.window.editor)
        self.assertEqual(self.window.editor.toPlainText(), 'Texto que já estava aqui. Mais uma frase.')
        self.assertFalse(self.window.recorder.timer.isActive())
        self.assertEqual(self.backend.requests, [])

    def test_silence_has_no_fake_waveform_and_elapsed_freezes_on_stop(self):
        self.window.voice.phase.emit('recording')
        self.window.recorder.advance()
        self.assertEqual(max(self.window.recorder.waveform.values), 0)
        self.window.recorder.clock.start()
        from PySide6.QtTest import QTest
        QTest.qWait(1050)
        self.window.recorder.advance()
        self.assertEqual(self.window.recorder.elapsed.text(), '00:01')
        self.window.voice.phase.emit('transcribing')
        before = self.window.recorder.elapsed.text()
        self.window.recorder.advance()
        self.assertEqual(self.window.recorder.elapsed.text(), before)
        self.window.voice.phase.emit('idle')

    def test_dictation_inserts_without_sending(self):
        self.window.dictated('olá mundo')
        self.assertEqual(self.window.editor.toPlainText(), 'olá mundo')
        self.assertEqual(self.backend.requests, [])

    def test_callback_exception_reaches_operation_failure(self):
        backend = Backend()
        failures = []
        timer = QTimer(backend)
        def callback(result): raise ValueError('policy denied')
        backend.pending[1] = (callback, failures.append, timer)
        backend.resolve(1, {})
        self.assertTrue(failures, 'Policy failure must unlock the UI')

    def test_disconnection_discards_loaded_backend_thread(self):
        self.window.thread_id = 'old-server-thread'
        self.window.turn_id = 'old-turn'
        self.window.disconnected()
        self.assertFalse(self.window.turn_id)
        self.assertFalse(self.window.thread_id)

    def test_private_codex_uses_custom_data_directory(self):
        binary = Path(self.temp.name)/'callas-chat/runtime/node_modules/.bin/codex'
        binary.parent.mkdir(parents=True)
        binary.write_text('#!/bin/sh\n')
        binary.chmod(0o755)
        self.assertEqual(codex_path(), str(binary))

    def test_close_waits_for_voice_worker_before_destroying_window(self):
        from PySide6.QtGui import QCloseEvent
        self.window.show()
        event = QCloseEvent()
        with patch.object(self.window.voice, 'close', return_value=False), patch.object(self.backend, 'close') as stop:
            self.window.closeEvent(event)
        self.assertFalse(event.isAccepted())
        stop.assert_not_called()


if __name__ == '__main__': unittest.main()
