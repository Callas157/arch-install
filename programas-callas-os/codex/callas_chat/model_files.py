"""Check the local multilingual Whisper model layout."""
from pathlib import Path


def whisper_ready(path):
    path = Path(path)
    return all((path/name).is_file() and (path/name).stat().st_size > 0
               for name in ('config.json', 'model.bin', 'tokenizer.json', 'vocabulary.txt'))
