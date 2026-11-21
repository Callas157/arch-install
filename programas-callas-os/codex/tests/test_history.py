"""Regressões de fixação e limpeza de histórico, sem dados reais do usuário."""
import json
import tempfile
from pathlib import Path
import unittest
from callas_chat.history import load_pins, save_pins


class PinnedHistoryTests(unittest.TestCase):
    def test_pins_preserved_by_provider(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'pins.json'
            save_pins('codex', {'a': 'conversa importante'}, path)
            save_pins('gpt', {'b': 'diagnóstico'}, path)
            self.assertEqual(load_pins('codex', path), {'a': 'conversa importante'})
            self.assertEqual(load_pins('gpt', path), {'b': 'diagnóstico'})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertNotIn('apiKey', json.dumps(json.loads(path.read_text())))

    def test_invalid_file_is_safe_and_no_follow_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root/'pins.json'
            path.write_text('{invalid')
            self.assertEqual(load_pins('codex', path), {})
            real = root/'real.json'
            real.write_text('{}')
            path.unlink()
            path.symlink_to(real)
            with self.assertRaises(ValueError):
                save_pins('gpt', {'a': 'b'}, path)
            self.assertEqual(real.read_text(), '{}')


if __name__ == '__main__':
    unittest.main()
