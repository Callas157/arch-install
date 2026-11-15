"""Prepare the pinned multilingual Whisper Medium model for local dictation."""
from pathlib import Path
import sys
from callas_chat.model_files import whisper_ready

MODEL = 'whisper-medium'
REPOSITORY = 'Systran/faster-whisper-medium'
REVISION = '08e178d48790749d25932bbc082711ddcfdfbc4f'
FILES = ['config.json', 'model.bin', 'tokenizer.json', 'vocabulary.txt']


def prepare(base):
    destination = Path(base)/'models'/MODEL
    if whisper_ready(destination):
        print('Whisper Medium local já disponível.')
        return
    from huggingface_hub import snapshot_download
    print('Baixando Whisper Medium multilíngue (~1,5 GB). O ditado funcionará offline após a instalação…', flush=True)
    snapshot_download(REPOSITORY, revision=REVISION,
                      local_dir=str(destination), allow_patterns=FILES)
    if not whisper_ready(destination):
        raise ValueError('O modelo Whisper está incompleto. Execute o instalador novamente para retomar o download.')
    print('Whisper Medium preparado para ditado local em português.')


if __name__ == '__main__':
    prepare(sys.argv[1])
