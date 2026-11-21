"""Regressões offline: escolha de discos secundários na instalação limpa."""
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = Path(os.environ.get('CALLAS_TEST_INSTALLER', ROOT / 'instalar-arch.sh'))


def source():
    return INSTALLER.read_text(encoding='utf-8')


def selection_body():
    src = source()
    part = src.split('# ---------------- Discos secundários — opção destrutiva explícita ----------------', 1)[1].split('read -rp "Nome do usuário', 1)[0]
    return part[part.index("printf '\\n>>> Discos secundários"):]


def format_body():
    src = source()
    return src.split('# Somente unidades explicitamente selecionadas e confirmadas são formatadas.', 1)[1].split('# ---------------- Instalação base ----------------', 1)[0]


class InstallerSecondaryFormatTests(unittest.TestCase):
    def run_selection(self, answers):
        fake = """set -Eeuo pipefail
DISCO=/dev/sda
BOOTDISK=/dev/sdc
callas_disco_secundario_seguro() { [[ $1 == /dev/sdb ]]; }
lsblk() {
  if [[ $1 == -dnpo ]]; then
    printf '/dev/sda disk 0 0\\n/dev/sdb disk 0 0\\n/dev/sdc disk 1 0\\n'
  elif [[ $1 == -dnro && $2 == MAJ:MIN ]]; then
    printf '8:16\\n'
  fi
}
"""
        code = fake + selection_body() + "printf 'SELECTED=%s\\n' \"${FORMATAR_SECUNDARIOS[*]}\"\n".replace('\\$', '$')
        return subprocess.run(['bash', '-c', code], input=answers, capture_output=True, text=True)

    def test_question_order(self):
        src = source()
        self.assertLess(src.index('CALLAS_WELCOME'), src.index('# ---------------- Escolha do disco'))
        self.assertLess(src.index('>>> Discos secundários'), src.index('Nome do usuário'))
        self.assertLess(src.index('Nome do usuário'), src.index('Senha do usuário'))
        self.assertLess(src.index('Senha do usuário'), src.index('Repita a senha'))
        self.assertLess(src.index('CALLAS_STORAGE_STAGE'), src.index('# Revalida TODOS os dispositivos'))

    def test_no_is_default(self):
        for answer in ('\n', 'n\n', 'não\n'):
            with self.subTest(answer=answer):
                process = self.run_selection(answer)
                self.assertEqual(process.returncode, 0, process.stderr)
                self.assertIn('SELECTED=\n', process.stdout)

    def test_mistyped_confirmation_preserves_files(self):
        process = self.run_selection('s\nAPAGAR /dev/sda\n')
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn('SELECTED=\n', process.stdout)
        self.assertIn('será preservado', process.stdout)

    def test_exact_double_confirmation(self):
        process = self.run_selection('sim\nAPAGAR /dev/sdb\n')
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn('SELECTED=/dev/sdb\n', process.stdout)

    def test_destructive_loop_only_for_authorized_disks(self):
        src = source()
        formatting = format_body()
        self.assertIn('[[ $alvo != "$DISCO" && $alvo != "$BOOTDISK" ]]', src)
        self.assertIn('^' + '(ata|sata|nvme)' + '$', src)
        self.assertIn('FORMATAR_SECUNDARIOS=()', src)
        self.assertIn('FORMATAR_SECUNDARIOS_IDS=()', src)
        self.assertIn('callas_disco_secundario_seguro "$CALLAS_OUTRO_DISCO"', formatting)
        self.assertIn('wipefs -af "$CALLAS_OUTRO_DISCO"', formatting)
        self.assertIn('mkfs.ext4 -F -L CALLAS_DADOS "$CALLAS_PARTICAO_DADOS"', formatting)
        self.assertNotIn('wipefs -af "$DISCO"', formatting)

    def test_banner_compiles(self):
        banner = source().split("python - <<'CALLAS_WELCOME'", 1)[1].split('CALLAS_WELCOME', 1)[0]
        compile(banner, '<banner>', 'exec')
        self.assertIn("('WELCOME', 'CALLAS OS')", banner)


if __name__ == '__main__':
    unittest.main()
