"""Asynchronous local stdio transport; no shell command interpolation."""
import json
import os
from pathlib import Path
import shutil
from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal
from .protocol import JsonLines


def codex_path():
    data = Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share')))
    for path in (data/'callas-chat/runtime/node_modules/.bin/codex',
                 Path.home()/'.local/bin/codex'):
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return shutil.which('codex') or ''


class Backend(QObject):
    ready = Signal()
    event = Signal(str, dict)
    error = Signal(str)
    disconnected = Signal()
    server_request = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.read)
        self.process.readyReadStandardError.connect(self.read_errors)
        self.process.started.connect(self.initialize)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.process_error)
        self.parser = JsonLines()
        self.pending = {}
        self.serial = 0
        self.connected = False
        self.closing = False
        self.stderr = ''

    def start(self):
        if self.process.state() != QProcess.NotRunning:
            return
        path = codex_path()
        if not path:
            self.error.emit('Codex não encontrado. Execute novamente o instalador do Codex.')
            return
        self.closing = False
        self.parser = JsonLines()
        env = QProcessEnvironment.systemEnvironment()
        askpass = Path.home()/'.local/bin/codex-askpass'
        if askpass.is_file(): env.insert('SUDO_ASKPASS', str(askpass))
        env.remove('CALLAS_KERNEL_UPDATE_CONTEXT')
        self.process.setProcessEnvironment(env)
        self.process.setProgram(path)
        self.process.setArguments(['-c', 'approval_policy="never"', '-c',
                                   'sandbox_mode="danger-full-access"', 'app-server', '--stdio'])
        self.process.start()

    def initialize(self):
        self.request('initialize', {'clientInfo': {'name': 'callas_chat', 'title': 'Codex',
                     'version': '1.3.0'}, 'capabilities': {'experimentalApi': False}}, self.initialized)

    def initialized(self, result):
        self.write({'method': 'initialized', 'params': {}})
        self.connected = True
        self.ready.emit()

    def write(self, message):
        if self.process.state() != QProcess.Running:
            return False
        self.process.write((json.dumps(message, ensure_ascii=False)+'\n').encode())
        return True

    def request(self, method, params, callback=None, failed=None):
        self.serial += 1
        request_id = self.serial
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self.timeout(request_id))
        self.pending[request_id] = (callback, failed, timer)
        if not self.write({'id': request_id, 'method': method, 'params': params}):
            self.resolve(request_id, error='O Codex está desconectado. Use Reconectar.')
        else:
            timer.start(60000)
        return request_id

    def timeout(self, request_id):
        self.resolve(request_id, error='O Codex demorou para responder. Confira a conexão e tente novamente.')

    def resolve(self, request_id, result=None, error=None):
        record = self.pending.pop(request_id, None)
        if not record:
            return
        callback, failed, timer = record
        timer.stop()
        timer.deleteLater()
        if error:
            if failed: failed(error)
            else: self.error.emit(error)
        elif callback:
            try:
                callback(result or {})
            except Exception as exc:
                message = 'Não foi possível processar a resposta: '+str(exc)
                if failed: failed(message)
                else: self.error.emit(message)

    def read(self):
        try:
            messages = self.parser.feed(bytes(self.process.readAllStandardOutput()))
        except (ValueError, UnicodeError) as exc:
            self.error.emit('Protocolo incompatível com esta versão do Codex: '+str(exc))
            self.process.kill()
            return
        for message in messages:
            if 'method' in message:
                if 'id' in message:
                    self.server_request.emit(message)
                else:
                    self.event.emit(message['method'], message.get('params') or {})
            elif 'id' in message:
                err = message.get('error')
                self.resolve(message['id'], message.get('result'),
                             ('O Codex retornou um erro: '+str(err.get('message', err))) if isinstance(err, dict) else None)

    def reply(self, request_id, result=None, error=None):
        message = {'id': request_id}
        message['error' if error else 'result'] = error if error else result
        self.write(message)

    def read_errors(self):
        self.stderr = (self.stderr + bytes(self.process.readAllStandardError()).decode(errors='replace'))[-12000:]

    def process_error(self, error):
        if error == QProcess.FailedToStart:
            self.error.emit('Não consegui iniciar o Codex. Verifique sua instalação.')

    def finished(self, *args):
        self.connected = False
        for request_id in list(self.pending):
            self.resolve(request_id, error='A conexão local com o Codex foi encerrada.')
        self.disconnected.emit()
        if not self.closing:
            self.error.emit('Conexão com o Codex encerrada. Clique em Reconectar.')

    def close(self):
        self.closing = True
        self.process.closeWriteChannel()
        if not self.process.waitForFinished(1500):
            self.process.terminate()
            if not self.process.waitForFinished(1000):
                self.process.kill()
                self.process.waitForFinished(1000)
