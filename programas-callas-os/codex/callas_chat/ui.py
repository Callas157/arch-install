import os
import math
import re
import uuid
from pathlib import Path
from PySide6.QtCore import Qt, QSettings, QTimer, QUrl, Signal, QSize, QEvent
from PySide6.QtGui import QDesktopServices, QFont, QIcon, QImage, QPixmap, QTextDocument, QTextOption, QTextCursor, QTextBlockFormat, QPainter
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QLineEdit, QListWidget, QListWidgetItem, QScrollArea, QFrame,
    QTextBrowser, QPlainTextEdit, QFileDialog, QDialog, QFormLayout, QDialogButtonBox,
    QSpinBox, QMessageBox, QInputDialog, QSizePolicy, QStackedWidget)
from .attachments import prepare_document
from .backend import Backend
from .protocol import thread_params, turn_params, check_full_access, messages_from_thread, safe_markdown
from .voice import Voice
from .recorder import RecorderPanel


class Editor(QPlainTextEdit):
    submitted = Signal()
    image_pasted = Signal(QImage)
    files_pasted = Signal(list)
    size_hint_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.textChanged.connect(self.size_hint_changed)
        self.document().documentLayout().documentSizeChanged.connect(lambda *_: self.size_hint_changed.emit())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.size_hint_changed.emit()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.FontChange, QEvent.StyleChange):
            self.size_hint_changed.emit()

    def composer_height(self):
        # QPlainTextDocumentLayout reports height in wrapped text lines.
        lines = max(1, min(4, math.ceil(self.document().size().height())))
        chrome = self.height() - self.viewport().height()
        return max(64, math.ceil(lines * self.fontMetrics().lineSpacing()
                                + 2 * self.document().documentMargin() + chrome + 2))

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not event.modifiers() & Qt.ShiftModifier:
            self.submitted.emit()
            return
        super().keyPressEvent(event)

    def insertFromMimeData(self, source):
        if source.hasImage():
            self.image_pasted.emit(QImage(source.imageData()))
        elif source.hasUrls() and any(url.isLocalFile() for url in source.urls()):
            self.files_pasted.emit([url.toLocalFile() for url in source.urls() if url.isLocalFile()])
        else:
            super().insertFromMimeData(source)


class ImagePreview(QLabel):
    """Fit an attachment to available space without cropping its contents."""
    def __init__(self, path, max_width=560, max_height=360):
        super().__init__()
        self.path = str(path)
        self.source = QPixmap(self.path)
        self.bounds = QSize(max_width, max_height)
        self.setObjectName('imagePreview')
        self.setMinimumWidth(0)
        self.setMaximumWidth(max_width)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip('Clique para abrir a imagem em tamanho original')
        self.setAccessibleName('Imagem anexada: ' + Path(path).name)
        self.update_image(max_width)

    def update_image(self, width):
        if self.source.isNull():
            self.setText('Imagem indisponível')
            self.setFixedHeight(32)
            return
        pixmap = self.source.scaled(max(1, min(width, self.bounds.width())),
                                    self.bounds.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(pixmap)
        self.setFixedHeight(pixmap.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_image(event.size().width())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.path))
        super().mouseReleaseEvent(event)


class FileAttachment(QFrame):
    """Compact document preview shared by the draft and sent messages."""
    def __init__(self, path, removable=False):
        super().__init__()
        self.setObjectName('fileAttachment')
        self.setMaximumWidth(340)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setStyleSheet('QFrame#fileAttachment { background: #202630; border: 1px solid #424b59; border-radius: 10px; } QFrame#fileAttachment QLabel { background: transparent; border: none; }')
        self.setToolTip(str(path))
        self.setAccessibleName('Arquivo anexado: ' + Path(path).name)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 12, 10)
        icon = QLabel('📄')
        row.addWidget(icon)
        details = QVBoxLayout()
        details.setSpacing(2)
        self.filename = ConversationTitle(Path(path).name)
        self.filename.setMinimumWidth(0)
        self.filename.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        details.addWidget(self.filename)
        kind = QLabel((Path(path).suffix.lstrip('.').upper() or 'ARQUIVO') + ' · Documento')
        kind.setTextFormat(Qt.PlainText)
        details.addWidget(kind)
        row.addLayout(details, 1)
        self.remove_button = None
        if removable:
            self.remove_button = QPushButton('×')
            self.remove_button.setObjectName('quietButton')
            self.remove_button.setFixedWidth(28)
            self.remove_button.setToolTip('Remover anexo')
            self.remove_button.setAccessibleName('Remover ' + Path(path).name)
            row.addWidget(self.remove_button)


class ConversationTitle(QLabel):
    def __init__(self, text):
        super().__init__(text)
        self.setToolTip(text)
        self.setWordWrap(False)
        self.setTextFormat(Qt.PlainText)

    def setText(self, text):
        super().setText(text)
        self.setToolTip(text)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setFont(self.font())
        painter.setPen(self.palette().windowText().color())
        text = self.fontMetrics().elidedText(self.text(), Qt.ElideRight, self.contentsRect().width())
        painter.drawText(self.contentsRect(), Qt.AlignLeft | Qt.AlignVCenter, text)


class ExecutionGroup(QFrame):
    def __init__(self):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Maximum)
        self.cards = []
        self.expanded = False
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(4, 0, 4, 0)
        self.layout.setSpacing(2)
        self.toggle = QPushButton()
        self.toggle.setObjectName('quietButton')
        self.toggle.setAccessibleName('Mostrar ou ocultar execuções')
        self.toggle.clicked.connect(self.toggle_details)
        self.layout.addWidget(self.toggle, alignment=Qt.AlignLeft)

    def add_card(self, card):
        self.cards.append(card)
        self.layout.addWidget(card)
        card.setVisible(self.expanded)
        self.update_summary()

    def update_summary(self):
        count = len(self.cards)
        self.toggle.setText(('▾ ' if self.expanded else '▸ ') +
                            (f'{count} execuções' if count != 1 else '1 execução'))

    def toggle_details(self):
        self.expanded = not self.expanded
        for card in self.cards:
            card.setVisible(self.expanded)
        self.update_summary()


class MessageCard(QFrame):
    def __init__(self, role, text='', parent=None):
        super().__init__(parent)
        self.role, self.text = role, text
        self.setObjectName('userCard' if role == 'user' else 'messageCard')
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(4, 4, 4, 8)
        self.layout.setSpacing(4)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Maximum)
        bar = QHBoxLayout()
        label = QLabel({'user': 'VOCÊ', 'assistant': 'CODEX', 'tool': 'ATIVIDADE'}[role])
        label.setObjectName('roleLabel')
        if role != 'tool': bar.addWidget(label)
        bar.addStretch()
        copy = QPushButton('Copiar')
        self.copy_button = copy
        copy.setObjectName('quietButton')
        copy.setToolTip('Copiar mensagem')
        policy = copy.sizePolicy()
        policy.setRetainSizeWhenHidden(True)
        copy.setSizePolicy(policy)
        copy.hide()
        copy.clicked.connect(lambda: QApplication.clipboard().setText(self.text))
        if role != 'tool': bar.addWidget(copy)
        self.layout.addLayout(bar)
        self.body = QTextBrowser()
        self.body.setOpenLinks(False)
        self.body.anchorClicked.connect(self.open_link)
        self.body.setFrameShape(QFrame.NoFrame)
        self.body.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.body.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.body.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.body.setMinimumWidth(0)
        self.body.setLineWrapMode(QTextBrowser.WidgetWidth)
        self.body.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.body.document().documentLayout().documentSizeChanged.connect(self.resize_body)
        self.layout.addWidget(self.body)
        if role == 'tool':
            self.layout.setContentsMargins(4, 0, 4, 0)
            toggle = QPushButton('▸ Ver execução')
            toggle.setObjectName('quietButton')
            bar.insertWidget(0, toggle)
            self.body.hide()
            toggle.clicked.connect(lambda: (self.body.setVisible(not self.body.isVisible()),
                toggle.setText('▾ Ocultar execução' if self.body.isVisible() else '▸ Ver execução'), self.resize_body()))
        self.code_row = QVBoxLayout()
        if role != 'tool': self.layout.addLayout(self.code_row)
        self.set_text(text)

    def enterEvent(self, event):
        if self.role != 'tool': self.copy_button.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.copy_button.hide()
        super().leaveEvent(event)

    def open_link(self, url):
        if url.scheme() in ('http', 'https'):
            QDesktopServices.openUrl(url)

    def set_text(self, text):
        self.text = text
        if self.role == 'tool': self.body.setPlainText(text[-40000:])
        else: self.body.setMarkdown(safe_markdown(text))
        # Markdown code blocks default to non-wrapping paragraphs in Qt.
        block = self.body.document().begin()
        while block.isValid():
            cursor = QTextCursor(block)
            fmt = block.blockFormat()
            fmt.setNonBreakableLines(False)
            if self.role != 'tool':
                fmt.setLineHeight(125, QTextBlockFormat.ProportionalHeight.value)
            cursor.setBlockFormat(fmt)
            block = block.next()
        while self.code_row.count():
            item = self.code_row.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        for number, code in enumerate(re.findall(r'```[^\n]*\n(.*?)```', text, re.S) if self.role != 'tool' else [], 1):
            button = QPushButton('Copiar código' + (f' {number}' if number > 1 else ''))
            button.setObjectName('quietButton')
            button.clicked.connect(lambda checked=False, value=code: QApplication.clipboard().setText(value))
            self.code_row.addWidget(button, alignment=Qt.AlignLeft)

        self.resize_body()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resize_body()

    def resize_body(self, *_):
        doc = self.body.document()
        doc.setTextWidth(max(1, self.body.viewport().width()))
        self.body.setFixedHeight(max(24, min(30000, int(doc.size().height())+4)))


class Window(QMainWindow):
    def __init__(self, backend=None, auto_start=True):
        super().__init__()
        self.settings = QSettings('CallasOS', 'CallasChat')
        self.cwd = self.settings.value('cwd', str(Path.home()))
        if not Path(self.cwd).is_dir(): self.cwd = str(Path.home())
        self.model = self.settings.value('model', '')
        self.font_size = int(self.settings.value('font_size', 12))
        self.backend = backend or Backend(self)
        self.voice = Voice(self)
        self.thread_id = self.turn_id = ''
        self.busy = False
        self.epoch = 0
        self.cursor = None
        self.cards = {}
        self.streams = {}
        self.images = []
        self.text_files = {}
        self.voice.gain = float(self.settings.value("mic_gain", 2.0))
        self.account_text = 'Verificando conta…'
        self.setWindowTitle('Codex')
        self.setMinimumSize(850, 650)
        self.resize(1250, 880)
        icon = Path(__file__).resolve().parents[1]/'assets/codex.svg'
        self.setWindowIcon(QIcon(str(icon)))
        self.build_ui(icon)
        self.apply_theme()
        geometry = self.settings.value('geometry')
        if geometry: self.restoreGeometry(geometry)
        self.backend.ready.connect(self.connected)
        self.backend.error.connect(self.show_error)
        self.backend.disconnected.connect(self.disconnected)
        self.backend.event.connect(self.on_event)
        self.backend.server_request.connect(self.server_request)
        self.voice.text.connect(self.dictated)
        self.voice.status.connect(self.activity.setText)
        self.voice.error.connect(self.show_error)
        self.voice.active.connect(self.voice_active)
        self.voice.phase.connect(self.voice_phase)
        self.voice.level.connect(self.recorder.set_level)
        self.stream_timer = QTimer(self)
        self.stream_timer.timeout.connect(self.flush_streams)
        self.stream_timer.start(90)
        if auto_start: QTimer.singleShot(0, self.backend.start)

    def build_ui(self, icon):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(265)
        left = QVBoxLayout(sidebar)
        left.setContentsMargins(18, 24, 18, 18)
        brand = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(QIcon(str(icon)).pixmap(38, 38))
        logo.setFixedSize(38, 38)
        brand.addWidget(logo)
        title = QLabel('Codex<br><span style="font-size:9pt;color:#9aabc2">Seu assistente no Linux</span>')
        title.setTextFormat(Qt.RichText)
        brand.addWidget(title)
        left.addLayout(brand)
        left.addSpacing(22)
        self.new_button = QPushButton('Nova conversa')
        self.new_button.setIcon(QIcon.fromTheme('document-new'))
        self.new_button.setObjectName('primaryButton')
        self.new_button.clicked.connect(self.new_chat)
        left.addWidget(self.new_button)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Buscar nas conversas…')
        self.search.textChanged.connect(self.filter_history)
        left.addWidget(self.search)
        caption = QLabel('CONVERSAS RECENTES')
        caption.setObjectName('roleLabel')
        left.addSpacing(12)
        left.addWidget(caption)
        self.history = QListWidget()
        self.history.setWordWrap(True)
        self.history.itemClicked.connect(self.select_thread)
        left.addWidget(self.history, 1)
        self.more_button = QPushButton('Carregar mais conversas')
        self.more_button.clicked.connect(lambda: self.load_history(False))
        self.more_button.setObjectName('quietButton')
        self.more_button.hide()
        left.addWidget(self.more_button)
        self.account = QLabel('Conectando ao Codex…')
        self.account.setObjectName('muted')
        self.account.setWordWrap(True)
        left.addWidget(self.account)
        self.login_button = QPushButton('Entrar com ChatGPT')
        self.login_button.clicked.connect(self.start_login)
        self.login_button.hide()
        left.addWidget(self.login_button)
        self.settings_button = QPushButton('⚙  Conta e configurações')
        self.settings_button.clicked.connect(self.open_settings)
        left.addWidget(self.settings_button)
        outer.addWidget(sidebar)
        self.drop_area = QWidget()
        main = QVBoxLayout(self.drop_area)
        main.setContentsMargins(20, 12, 20, 12)
        main.setSpacing(12)
        header = QHBoxLayout()
        heading = QVBoxLayout()
        self.heading = ConversationTitle('Uma conversa, muitas possibilidades')
        self.heading.setObjectName('heading')
        self.heading.setWordWrap(False)
        self.heading.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        heading.addWidget(self.heading)
        self.connection = QLabel('● Conectando…')
        self.connection.setObjectName('muted')
        self.connection.hide()
        heading.addWidget(self.connection)
        header.addLayout(heading, 1)
        access = QLabel('●  Acesso completo')
        access.setObjectName('accessBadge')
        access.setToolTip('Arquivos e rede sem sandbox, sem confirmação de comandos. Sudo continua exigindo autenticação do Linux.')
        header.addWidget(access)
        self.reconnect = QPushButton('Reconectar')
        self.reconnect.clicked.connect(self.backend.start)
        self.reconnect.hide()
        header.addWidget(self.reconnect)
        main.addLayout(header)
        self.folder = QPushButton()
        self.folder.setObjectName('folderButton')
        self.folder.clicked.connect(self.choose_folder)
        self.update_folder()
        main.addWidget(self.folder, alignment=Qt.AlignLeft)
        self.error_box = QLabel()
        self.error_box.setObjectName('errorBox')
        self.error_box.setWordWrap(True)
        self.error_box.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.error_box.hide()
        main.addWidget(self.error_box)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.messages = QWidget()
        self.messages.setMaximumWidth(960)
        self.messages.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.message_layout = QVBoxLayout(self.messages)
        self.message_layout.setContentsMargins(0, 12, 10, 20)
        self.message_layout.setSpacing(8)
        self.message_layout.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.messages)
        main.addWidget(self.scroll, 1)
        self.welcome()
        self.activity = QLabel('Preparando sua conta e suas conversas…')
        self.activity.setObjectName('muted')
        self.activity.setWordWrap(True)
        main.addWidget(self.activity)
        self.attachment_area = QScrollArea()
        self.attachment_area.setFrameShape(QFrame.NoFrame)
        self.attachment_area.setWidgetResizable(True)
        self.attachment_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.attachment_area.setMaximumHeight(198)
        attachment_content = QWidget()
        self.attachments = QHBoxLayout(attachment_content)
        self.attachments.setContentsMargins(0, 0, 0, 0)
        self.attachments.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.attachment_area.setWidget(attachment_content)
        self.attachment_area.hide()
        compose = QFrame()
        compose.setObjectName('composer')
        box = QVBoxLayout(compose)
        box.addWidget(self.attachment_area)
        self.editor = Editor()
        self.editor.setPlaceholderText('Converse, arraste arquivos ou cole uma foto…')
        self.editor.setMinimumHeight(64)
        self.editor.submitted.connect(self.send)
        self.editor.image_pasted.connect(self.attach_image)
        self.editor.files_pasted.connect(self.attach_files)
        self.recorder = RecorderPanel()
        self.composer_stack = QStackedWidget()
        self.composer_stack.setObjectName('composerStack')
        self.composer_stack.setFixedHeight(64)
        self.composer_stack.addWidget(self.editor)
        self.composer_stack.addWidget(self.recorder)
        box.addWidget(self.composer_stack)
        self.editor.size_hint_changed.connect(self.resize_composer)
        controls = QHBoxLayout()
        self.attach_button = QPushButton('Anexar')
        self.attach_button.setIcon(QIcon.fromTheme('image-x-generic'))
        self.attach_button.clicked.connect(self.choose_images)
        controls.addWidget(self.attach_button)
        self.mic = QPushButton('Microfone')
        self.mic.setIcon(QIcon.fromTheme('audio-input-microphone'))
        self.mic.setToolTip('Whisper Medium local em português. Fale e clique em Parar ditado para transcrever (até 2 minutos).')
        self.mic.clicked.connect(self.voice.start)
        controls.addWidget(self.mic)
        hint = QLabel('Enter envia · Shift+Enter quebra a linha')
        hint.setObjectName('muted')
        hint.hide()
        self.editor.setToolTip('Enter envia · Shift+Enter quebra a linha')
        hint.setWordWrap(True)
        controls.addStretch(1)
        self.stop_button = QPushButton('■  Interromper')
        self.stop_button.clicked.connect(self.interrupt)
        self.stop_button.hide()
        controls.addWidget(self.stop_button)
        self.send_button = QPushButton('Enviar  ↑')
        self.send_button.setObjectName('primaryButton')
        self.send_button.clicked.connect(self.send)
        controls.addWidget(self.send_button)
        box.addLayout(controls)
        compose.setMaximumWidth(960)
        composer_row = QHBoxLayout()
        composer_row.addStretch(1)
        composer_row.addWidget(compose, 100)
        composer_row.addStretch(1)
        main.addLayout(composer_row)
        foot = QLabel('Codex conectado à sua conta · Ditado local em português · Revise comandos e respostas importantes')
        foot.setObjectName('footer')
        foot.hide()
        foot.setWordWrap(True)
        foot.setAlignment(Qt.AlignCenter)
        main.addWidget(foot, alignment=Qt.AlignHCenter)
        outer.addWidget(self.drop_area, 1)
        self.drop_area.setAcceptDrops(True)
        QApplication.instance().installEventFilter(self)
        self.set_busy(False)
        self.send_button.setEnabled(False)

    def eventFilter(self, watched, event):
        # Child editors and scroll viewports can consume drops before the window.
        # Handle local files consistently throughout this conversation only.
        if (event.type() in (QEvent.DragEnter, QEvent.DragMove, QEvent.Drop)
                and isinstance(watched, QWidget) and watched.window() is self):
            point = self.drop_area.mapFrom(watched, event.position().toPoint())
            if self.drop_area.rect().contains(point):
                paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
                if paths:
                    if self.busy:
                        event.ignore()
                    else:
                        # Always copy: dropping a file must never move the original.
                        event.setDropAction(Qt.CopyAction)
                        event.accept()
                        if event.type() == QEvent.Drop:
                            self.attach_files(paths)
                    return True
        return super().eventFilter(watched, event)

    def apply_theme(self):
        css = (Path(__file__).with_name('theme.qss')).read_text()
        self.setStyleSheet(css)
        QApplication.instance().setFont(QFont('Noto Sans', self.font_size))
        for card in self.messages.findChildren(MessageCard):
            card.body.setFont(QFont('Noto Sans', self.font_size + 1))
            card.resize_body()

    def welcome(self):
        card = QFrame()
        card.setObjectName('welcomeCard')
        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 34, 28, 34)
        title = QLabel('O que vamos fazer hoje?')
        title.setObjectName('welcomeTitle')
        layout.addWidget(title)
        subtitle = QLabel('Converse em português, cuide dos seus projetos\nou peça ajuda com o seu Linux.')
        subtitle.setObjectName('muted')
        layout.addWidget(subtitle)
        layout.addSpacing(20)
        for label, text in [('Entender um problema', 'Me ajude a investigar um problema no meu Linux.'),
                            ('Trabalhar num projeto', 'Quero trabalhar em um projeto. Me ajude a começar.'),
                            ('Conversar com uma imagem', '')]:
            button = QPushButton(label+'  ↗')
            button.clicked.connect(lambda checked=False, value=text: self.editor.setPlainText(value) if value else self.choose_images())
            layout.addWidget(button)
        self.message_layout.addWidget(card)
        self.welcome_card = card

    def clear_messages(self):
        self.cards.clear()
        self.streams.clear()
        self.welcome_card = None
        while self.message_layout.count():
            item = self.message_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

    def add_card(self, role, text, item_id='', images=(), documents=()):
        if self.welcome_card:
            self.welcome_card.deleteLater()
            self.message_layout.removeWidget(self.welcome_card)
            self.welcome_card = None
        card = MessageCard(role, text)
        for path in images:
            card.layout.addWidget(ImagePreview(path))
        for path in documents:
            card.layout.addWidget(FileAttachment(path))
        if (images or documents) and not text.strip(): card.body.hide()
        card.body.setFont(QFont('Noto Sans', self.font_size + 1))
        if role == 'tool':
            last = self.message_layout.itemAt(self.message_layout.count() - 1)
            group = last.widget() if last else None
            if not isinstance(group, ExecutionGroup):
                group = ExecutionGroup()
                self.message_layout.addWidget(group)
            group.add_card(card)
        else:
            self.message_layout.addWidget(card)
        if item_id: self.cards[item_id] = card
        self.scroll_bottom()
        return card

    def scroll_bottom(self):
        QTimer.singleShot(30, lambda: self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum()))

    def connected(self):
        self.connection.setText('● Conectado ao Codex')
        self.reconnect.hide()
        self.error_box.hide()
        self.activity.setText('Pronto. Digite, cole uma foto ou use o microfone.')
        self.set_busy(False)
        self.backend.request('account/read', {'refreshToken': False}, self.account_loaded)
        self.load_history()
        if getattr(self, 'reconnect_thread', ''):
            item = QListWidgetItem(self.heading.text())
            item.setData(Qt.UserRole, self.reconnect_thread)
            self.reconnect_thread = ''
            self.select_thread(item)

    def disconnected(self):
        self.reconnect_thread = self.thread_id
        self.thread_id = self.turn_id = ''
        self.cancel_pending = False
        self.connection.setText('● Desconectado')
        self.reconnect.show()
        self.set_busy(False)

    def account_loaded(self, result):
        account = result.get('account') or {}
        kind = account.get('type')
        self.account_text = ('Conectado com sua conta ChatGPT' if kind == 'chatgpt' else
                             'Conectado com chave de API' if kind == 'apiKey' else 'Entre na sua conta para conversar')
        self.account.setText(self.account_text)
        self.login_button.setVisible(not bool(account))

    def load_history(self, replace=True):
        params = {'limit': 50, 'sortKey': 'updated_at', 'sourceKinds': []}
        if not replace and self.cursor: params['cursor'] = self.cursor
        def loaded(result):
            if replace: self.history.clear()
            for thread in result.get('data', []):
                name = thread.get('name') or thread.get('preview') or 'Conversa sem título'
                name = name.replace('\n', ' ')[:85]
                item = QListWidgetItem(name)
                item.setData(Qt.UserRole, thread['id'])
                item.setToolTip(name+'\n'+(thread.get('cwd') or ''))
                item.setSizeHint(QSize(215, 60))
                self.history.addItem(item)
            self.cursor = result.get('nextCursor')
            self.more_button.setVisible(bool(self.cursor))
            self.filter_history()
        self.backend.request('thread/list', params, loaded)

    def filter_history(self, *args):
        query = self.search.text().casefold()
        for i in range(self.history.count()):
            item = self.history.item(i)
            item.setHidden(query not in item.text().casefold())

    def new_chat(self):
        if self.busy or self.voice.worker: return
        self.voice.stop()
        self.epoch += 1
        self.thread_id = self.turn_id = ''
        self.clear_messages()
        self.welcome()
        self.clear_images()
        self.editor.clear()
        self.heading.setText('Uma conversa, muitas possibilidades')
        self.error_box.hide()
        self.editor.setFocus()

    def select_thread(self, item):
        if self.busy: return
        self.voice.stop()
        self.epoch += 1
        epoch = self.epoch
        thread_id = item.data(Qt.UserRole)
        title = item.text()
        self.set_busy(True)
        self.activity.setText('Abrindo conversa…')
        params = thread_params(self.cwd)
        params['threadId'] = thread_id
        def loaded(result):
            if epoch != self.epoch: return
            check_full_access(result)
            thread = result['thread']
            self.thread_id, self.turn_id = thread['id'], ''
            self.clear_messages()
            for message in messages_from_thread(thread):
                self.add_card(message['role'], message['text'], message['id'], message.get('images', ()), message.get('documents', ()))
            if not self.cards: self.welcome()
            self.clear_images()
            self.heading.setText(title)
            self.set_busy(False)
            self.activity.setText('Conversa retomada com acesso completo.')
        self.backend.request('thread/resume', params, loaded, self.operation_failed)

    def send(self):
        if self.busy or self.voice.worker or not self.backend.connected: return
        text = self.editor.toPlainText().strip()
        if not text and not self.images and not self.text_files: return
        documents = dict(self.text_files)
        prompt = text or ("Analise os arquivos anexados e responda em português." if documents else "Analise a imagem anexada e responda em português.")
        for name, content in documents.items():
            prompt += "\n\nArquivo anexado: " + name + "\n<conteudo_do_arquivo>\n" + content + "\n</conteudo_do_arquivo>"
        images = list(self.images)
        self.error_box.hide()
        self.set_busy(True)
        self.cancel_pending = False
        self.turn_id = ''
        self.activity.setText('Preparando conversa…')
        def start_turn():
            self.editor.clear()
            self.clear_images()
            self.add_card('user', text, images=images, documents=documents)
            self.activity.setText('O Codex está trabalhando…')
            params = turn_params(self.thread_id, prompt, self.cwd, images)
            if self.model: params['model'] = self.model
            def started(result):
                self.turn_id = result.get('turn', {}).get('id', self.turn_id)
            def failed(error):
                self.operation_failed(error)
                if not self.editor.toPlainText(): self.editor.setPlainText(text)
                for path in images:
                    self.add_attachment(path)
                for name, content in documents.items():
                    self.add_text_attachment(name, content)
            self.backend.request('turn/start', params, started, failed)
        if self.thread_id:
            start_turn()
        else:
            params = thread_params(self.cwd)
            params['developerInstructions'] = 'Responda ao usuário em português do Brasil, com linguagem clara. Preserve o idioma de código, comandos e citações quando necessário.'
            if self.model: params['model'] = self.model
            def created(result):
                check_full_access(result)
                self.thread_id = result['thread']['id']
                self.heading.setText(text or 'Conversa com imagem')
                start_turn()
            self.backend.request('thread/start', params, created, self.operation_failed)

    def set_busy(self, busy):
        self.busy = busy
        self.send_button.setEnabled(not busy and self.backend.connected and not self.voice.worker)
        self.stop_button.setVisible(busy)
        for control in (self.new_button, self.history, self.folder, self.attach_button, self.mic, self.settings_button):
            control.setEnabled(not busy)

    def operation_failed(self, error):
        self.set_busy(False)
        self.show_error(error)

    def show_error(self, text):
        self.error_box.setText(text)
        self.error_box.show()
        if not self.backend.connected: self.reconnect.show()

    def interrupt(self):
        if self.thread_id and self.turn_id:
            self.activity.setText('Interrompendo…')
            self.backend.request('turn/interrupt', {'threadId': self.thread_id, 'turnId': self.turn_id},
                lambda result: self.activity.setText('Interrupção solicitada…'), self.operation_failed)
        else:
            self.activity.setText('Aguardando o início do turno para interromper…')
            self.cancel_pending = True

    def on_event(self, method, params):
        if method in ('account/updated', 'account/login/completed'):
            if method == 'account/login/completed' and not params.get('success', True):
                self.show_error('O login não foi concluído. Tente novamente em Conta e configurações.')
            else: self.backend.request('account/read', {'refreshToken': False}, self.account_loaded)
            return
        if params.get('threadId') != self.thread_id: return
        if method == 'turn/started':
            self.turn_id = params.get('turn', {}).get('id', '')
            if getattr(self, 'cancel_pending', False):
                self.cancel_pending = False
                self.interrupt()
        elif method == 'item/agentMessage/delta':
            item_id = params['itemId']
            if item_id not in self.cards: self.add_card('assistant', '', item_id)
            self.streams[item_id] = self.streams.get(item_id, self.cards[item_id].text) + params.get('delta', '')
        elif method in ('item/started', 'item/completed'):
            item = params.get('item', {})
            kind, item_id = item.get('type'), item.get('id', '')
            if kind == 'agentMessage' and method == 'item/completed':
                self.streams.pop(item_id, None)
                card = self.cards.get(item_id) or self.add_card('assistant', '', item_id)
                card.set_text(item.get('text', ''))
            elif kind in ('commandExecution', 'fileChange', 'mcpToolCall', 'webSearch'):
                labels = {'commandExecution': 'Executando comando…', 'fileChange': 'Editando arquivos…',
                          'mcpToolCall': 'Consultando ferramenta…', 'webSearch': 'Pesquisando na internet…'}
                self.activity.setText(labels[kind])
                if method == 'item/completed':
                    messages = messages_from_thread({'turns': [{'items': [item]}]})
                    for message in messages:
                        card = self.cards.get(item_id) or self.add_card('tool', '', item_id)
                        card.set_text(message['text'])
        elif method == 'turn/completed':
            self.flush_streams()
            self.turn_id = ''
            self.cancel_pending = False
            self.set_busy(False)
            turn = params.get('turn', {})
            status = turn.get('status')
            self.activity.setText('Resposta interrompida.' if status == 'interrupted' else 'Pronto. Pode continuar a conversa.')
            if turn.get('error'): self.show_error('Não foi possível concluir: '+str(turn['error'].get('message', turn['error'])))
            self.load_history()
        elif method == 'error':
            self.show_error('O Codex informou: '+str(params.get('error', {}).get('message', 'Falha durante a resposta.')))

    def flush_streams(self):
        if not self.streams: return
        bar = self.scroll.verticalScrollBar()
        at_bottom = bar.maximum()-bar.value() < 130
        for item_id, text in list(self.streams.items()):
            if item_id in self.cards: self.cards[item_id].set_text(text)
        self.streams.clear()
        if at_bottom: self.scroll_bottom()

    def server_request(self, message):
        method, params = message['method'], message.get('params') or {}
        request_id = message['id']
        if method in ('item/commandExecution/requestApproval', 'item/fileChange/requestApproval'):
            self.backend.reply(request_id, {'decision': 'accept'})
        elif method == 'item/tool/requestUserInput':
            answers = {}
            for question in params.get('questions', []):
                choices = [o.get('label', '') for o in (question.get('options') or [])]
                if choices:
                    answer, ok = QInputDialog.getItem(self, 'O Codex precisa de uma resposta', question.get('question', ''), choices, 0, True)
                else:
                    answer, ok = QInputDialog.getText(self, 'O Codex precisa de uma resposta', question.get('question', ''))
                answers[question['id']] = {'answers': [answer] if ok else []}
            self.backend.reply(request_id, {'answers': answers})
        else:
            self.backend.reply(request_id, error={'code': -32601, 'message': 'Este pedido de ferramenta ainda não é suportado pelo Codex.'})

    def update_folder(self):
        self.folder.setText('▱  '+self.cwd)
        self.folder.setToolTip('Escolher a pasta em que o Codex vai trabalhar')

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Escolher pasta de trabalho', self.cwd)
        if folder:
            self.cwd = folder
            self.settings.setValue('cwd', folder)
            self.update_folder()

    def choose_images(self):
        paths, _ = QFileDialog.getOpenFileNames(self, 'Anexar arquivos', str(Path.home()), 'Arquivos (*.plasmoid *.zip *.tar *.gz *.7z *.png *.jpg *.jpeg *.webp *.bmp *.txt *.log *.md *.csv *.json *.jsonl *.yaml *.yml *.xml *.ini *.conf *.out);;Todos os arquivos (*)')
        self.attach_files(paths)

    def attach_files(self, paths):
        if self.busy: return
        for value in paths:
            path = Path(value)
            if path.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp', '.bmp'):
                image = QImage(str(path))
                if image.isNull(): self.show_error('Não consegui abrir a imagem: '+path.name)
                else: self.attach_image(image)
                continue
            try:
                content = prepare_document(path)
                if sum(len(t.encode('utf-8')) for n, t in self.text_files.items() if n != str(path)) + len(content.encode('utf-8')) > 2 * 1024 * 1024:
                    raise ValueError('O limite de textos por mensagem é 2 MB.')
                self.add_text_attachment(str(path), content)
            except (OSError, ValueError) as exc:
                self.show_error('Não consegui anexar '+path.name+': '+str(exc))

    def add_text_attachment(self, name, content):
        if name in self.text_files: return
        self.text_files[name] = content
        tile = FileAttachment(name, removable=True)
        tile.setFixedWidth(320)
        def remove():
            self.text_files.pop(name, None)
            self.attachments.removeWidget(tile)
            tile.deleteLater()
            self.attachment_area.setVisible(bool(self.attachments.count()))
        tile.remove_button.clicked.connect(remove)
        self.attachments.addWidget(tile)
        self.attachment_area.show()

    def attach_image(self, image):
        if self.busy: return
        if len(self.images) >= 6:
            self.show_error('Anexe até seis imagens por mensagem.')
            return
        if image.isNull(): return
        root = Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share')))/'callas-chat/attachments'
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = root/(uuid.uuid4().hex+'.png')
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
            if not image.save(str(path), 'PNG'): raise OSError('Não consegui salvar a foto colada.')
            self.add_attachment(str(path))
        except OSError as exc: self.show_error('Falha ao preparar a foto: '+str(exc))

    def add_attachment(self, path):
        if path in self.images: return
        self.images.append(path)
        tile = QFrame()
        tile.setObjectName('attachmentTile')
        tile.setFixedWidth(320)
        layout = QVBoxLayout(tile)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        layout.addWidget(ImagePreview(path, 312, 150))
        button = QPushButton('Remover ×')
        button.setObjectName('quietButton')
        button.setToolTip('A imagem só será enviada ao clicar em Enviar.')
        def remove():
            if path in self.images: self.images.remove(path)
            self.attachments.removeWidget(tile)
            tile.deleteLater()
            self.attachment_area.setVisible(bool(self.attachments.count()))
        button.clicked.connect(remove)
        layout.addWidget(button, alignment=Qt.AlignRight)
        self.attachments.addWidget(tile)
        self.attachment_area.show()

    def clear_images(self):
        self.attachment_area.hide()
        self.images.clear()
        self.text_files.clear()
        while self.attachments.count():
            item = self.attachments.takeAt(0)
            if item.widget(): item.widget().deleteLater()

    def dictated(self, text):
        cursor = self.editor.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText((' ' if self.editor.toPlainText() else '')+text)
        self.editor.setTextCursor(cursor)

    def resize_composer(self):
        height = self.editor.composer_height() if self.composer_stack.currentWidget() is self.editor else 64
        if self.composer_stack.height() != height:
            self.composer_stack.setFixedHeight(height)

    def voice_phase(self, phase):
        self.recorder.set_phase(phase)
        self.composer_stack.setCurrentWidget(self.editor if phase == 'idle' else self.recorder)
        self.resize_composer()
        self.mic.setEnabled(phase != 'transcribing' and not self.busy)
        if phase == 'transcribing': self.mic.setText('Transcrevendo…')
        elif phase == 'idle':
            self.mic.setText('Microfone')
            self.editor.setFocus()

    def voice_active(self, active):
        self.mic.setText('Parar ditado' if active else 'Microfone')
        self.mic.setProperty('recording', active)
        self.mic.style().unpolish(self.mic)
        self.mic.style().polish(self.mic)
        self.send_button.setEnabled(not active and not self.busy and self.backend.connected)
        for control in (self.new_button, self.history, self.folder):
            control.setEnabled(not active and not self.busy)
        if not active and getattr(self, 'closing_requested', False):
            QTimer.singleShot(0, self.close)

    def start_login(self):
        def result(data):
            url = QUrl(data.get('authUrl', ''))
            if url.scheme() == 'https': QDesktopServices.openUrl(url)
            else: self.show_error('O login não forneceu uma página segura de autenticação. Tente novamente.')
        self.backend.request('account/login/start', {'type': 'chatgpt'}, result)

    def open_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('Conta e configurações')
        dialog.setMinimumWidth(470)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(self.account_text))
        login = QPushButton('Entrar com minha conta ChatGPT')
        login.clicked.connect(lambda: (self.start_login(), dialog.accept()))
        layout.addWidget(login)
        form = QFormLayout()
        model = QLineEdit(self.model)
        model.setPlaceholderText('Automático — configuração atual do Codex')
        form.addRow('Modelo:', model)
        size = QSpinBox()
        size.setRange(10, 22)
        size.setValue(self.font_size)
        form.addRow('Tamanho do texto:', size)
        gain = QSpinBox()
        gain.setRange(100, 600)
        gain.setSuffix('%')
        gain.setValue(round(self.voice.gain * 100))
        gain.setToolTip('Aumenta a voz baixa com proteção contra saturação. Padrão: 200%.')
        form.addRow('Sensibilidade do microfone:', gain)
        layout.addLayout(form)
        note = QLabel('Acesso completo está ativado: arquivos e rede sem sandbox e sem confirmações.\nO aplicativo não guarda senhas nem substitui a autenticação do sudo.\n\nO microfone usa Whisper Medium local em português. Clique em Parar ditado para transcrever e revise antes de Enviar.')
        note.setWordWrap(True)
        note.setObjectName('muted')
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText('Salvar')
        buttons.button(QDialogButtonBox.Cancel).setText('Cancelar')
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.Accepted:
            self.model, self.font_size = model.text().strip(), size.value()
            self.voice.gain = gain.value() / 100
            self.settings.setValue('mic_gain', self.voice.gain)
            self.settings.setValue('model', self.model)
            self.settings.setValue('font_size', self.font_size)
            self.apply_theme()

    def closeEvent(self, event):
        if self.busy and not getattr(self, 'closing_requested', False):
            answer = QMessageBox.question(self, 'Resposta em andamento',
                'Há uma tarefa em andamento. Interromper e fechar?', QMessageBox.Yes | QMessageBox.No)
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self.interrupt()
        self.closing_requested = True
        self.settings.setValue('geometry', self.saveGeometry())
        if not self.voice.close():
            self.activity.setText('Finalizando o ditado antes de fechar…')
            event.ignore()
            return
        self.backend.close()
        event.accept()
