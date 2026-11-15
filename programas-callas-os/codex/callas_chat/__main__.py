import os
import sys
from pathlib import Path
from PySide6.QtCore import QLocale, QTranslator, QLibraryInfo, QLockFile, QStandardPaths
from PySide6.QtWidgets import QApplication, QMessageBox, QInputDialog, QLineEdit
from .ui import Window


def main():
    QLocale.setDefault(QLocale(QLocale.Portuguese, QLocale.Brazil))
    app = QApplication(sys.argv)
    app.setApplicationName('Codex')
    app.setDesktopFileName('io.github.callasos.CallasChat')
    app.setOrganizationName('CallasOS')
    app.setStyle('Fusion')
    translator = QTranslator(app)
    translator.load('qtbase_pt_BR', QLibraryInfo.path(QLibraryInfo.TranslationsPath))
    app.installTranslator(translator)
    if '--askpass' in sys.argv[1:]:
        value, accepted = QInputDialog.getText(None, 'Codex — autorização administrativa',
            'O sistema precisa da sua senha para continuar:', QLineEdit.Password)
        if accepted:
            sys.stdout.write(value + '\n')
            return 0
        return 1
    lock_dir = QStandardPaths.writableLocation(QStandardPaths.RuntimeLocation) or str(Path.home()/'.cache')
    lock = QLockFile(str(Path(lock_dir)/'callas-chat.lock'))
    if not lock.tryLock(100):
        QMessageBox.information(None, 'Codex', 'O Codex já está aberto. Procure a janela na barra de tarefas do KDE.')
        return 0
    if os.geteuid() == 0:
        QMessageBox.warning(None, 'Codex', 'Abra o aplicativo como seu usuário normal, sem sudo.')
        return 1
    window = Window()
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
