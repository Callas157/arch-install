import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from callas_chat.attachments import prepare_document


class AttachmentTests(unittest.TestCase):
    def test_plasmoid_copy_survives_original_removal(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'XDG_DATA_HOME': folder}):
            path = Path(folder)/'relógio.plasmoid'
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('contents/ui/main.qml', 'import QtQuick\n')
            original = path.read_bytes()
            result = prepare_document(path)
            metadata = json.loads(result.split('\n', 1)[1])
            path.unlink()
            saved = Path(metadata['caminho_local'])
            self.assertEqual(saved.read_bytes(), original)
            self.assertEqual(metadata['sha256'], hashlib.sha256(original).hexdigest())
            self.assertEqual(saved.stat().st_mode & 0o777, 0o600)
            self.assertEqual(saved.suffix, '.plasmoid')
            self.assertFalse((Path(folder)/'contents').exists())

    def test_text_encodings_are_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'text.txt'
            for encoding in ('utf-8-sig', 'utf-16', 'cp1252'):
                path.write_bytes('Olá\n'.encode(encoding))
                self.assertEqual(prepare_document(path), 'Olá\n')

    def test_large_binary_is_rejected_without_copy(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'XDG_DATA_HOME': folder}):
            path = Path(folder)/'file.bin'
            path.write_bytes(b'\x00' * 20)
            with patch('callas_chat.attachments.BINARY_LIMIT', 10):
                with self.assertRaisesRegex(ValueError, '100 MB'):
                    prepare_document(path)
            self.assertFalse((Path(folder)/'callas-chat').exists())
