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
    return 'mapfile -t CALLAS_DISCOS_DISPONIVEIS' + src.split('mapfile -t CALLAS_DISCOS_DISPONIVEIS', 1)[1].split('read -rp "Nome do usuário', 1)[0]


def format_body():
    src = source()
    return src.split('# Somente unidades explicitamente selecionadas e confirmadas são formatadas.', 1)[1].split('# ---------------- Instalação base ----------------', 1)[0]


class InstallerSecondaryFormatTests(unittest.TestCase):
    def run_selection(self, answers, eligible='/dev/sdb'):
        fake = """set -Eeuo pipefail
DISCO=/dev/sda
BOOTDISK=/dev/sdd
FORMATAR_SECUNDARIOS=()
FORMATAR_SECUNDARIOS_IDS=()
callas_disco_secundario_seguro() {
  case " $ELIGIBLE " in *" $1 "*) return 0;; *) return 1;; esac
}
lsblk() {
  if [[ $1 == -dnpo ]]; then
    printf '/dev/sda disk 0 0\\n/dev/sdb disk 0 0\\n/dev/sdc disk 0 0\\n/dev/sdd disk 1 0\\n'
  elif [[ $1 == -dnro && $2 == MAJ:MIN ]]; then
    printf '8:16\\n'
  fi
}
"""
        code = fake + selection_body() + "printf 'SELECTED=%s\\n' \"${FORMATAR_SECUNDARIOS[*]}\"\n".replace('\\$', '$')
        return subprocess.run(['bash', '-c', code], input=answers, capture_output=True, text=True,
                              env={**os.environ, 'ELIGIBLE': eligible})

    def test_question_order(self):
        src = source()
        self.assertLess(src.index('CALLAS_WELCOME'), src.index('# ---------------- Escolha do disco'))
        self.assertLess(src.index('>>> Discos secundários'), src.index('Nome do usuário'))
        self.assertLess(src.index('Nome do usuário'), src.index('Senha do usuário'))
        self.assertLess(src.index('Senha do usuário'), src.index('Repita a senha'))
        self.assertLess(src.index('CALLAS_STORAGE_STAGE'), src.index('# Revalida TODOS os dispositivos'))

    def test_no_secondary_skips_entire_step(self):
        process = self.run_selection('', eligible='')
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertNotIn('Discos secundários', process.stdout)
        self.assertNotIn('Armazenamento', process.stdout)
        self.assertEqual(process.stdout, 'SELECTED=\n')

    def test_one_secondary_labeled_second_of_two(self):
        process = self.run_selection('\n')
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn('Armazenamento 2 de 2', process.stdout)
        self.assertNotIn('Armazenamento 3', process.stdout)

    def test_multiple_secondary_disks_numbered(self):
        process = self.run_selection('2\n1\n', eligible='/dev/sdb /dev/sdc')
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn('Armazenamento 2 de 3', process.stdout)
        self.assertIn('Armazenamento 3 de 3', process.stdout)
        self.assertEqual(process.stdout.count('Discos secundários'), 1)
        self.assertIn('Dados preservados em /dev/sdb', process.stdout)
        self.assertIn('SELECTED=/dev/sdc\n', process.stdout)

    def test_no_is_default(self):
        for answer in ('\n', '2\n', 'não\n', 'sim\n', '3\n'):
            with self.subTest(answer=answer):
                process = self.run_selection(answer)
                self.assertEqual(process.returncode, 0, process.stderr)
                self.assertIn('SELECTED=\n', process.stdout)

    def test_choice_one_is_final_authorization_without_another_prompt(self):
        process = self.run_selection('1\n')
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn('SELECTED=/dev/sdb\n', process.stdout)
        self.assertNotIn('CONFIRMAÇÃO FINAL', process.stdout)
        self.assertNotIn('digite APAGAR', process.stdout)

    def test_choice_two_preserves_without_another_prompt(self):
        process = self.run_selection('2\n')
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn('SELECTED=\n', process.stdout)
        self.assertNotIn('CONFIRMAÇÃO FINAL', process.stdout)

    def test_apagar_word_is_not_valid_numeric_choice(self):
        process = self.run_selection('APAGAR\n')
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn('SELECTED=\n', process.stdout)

    def test_destructive_loop_only_for_authorized_disks(self):
        src = source()
        formatting = format_body()
        self.assertIn('[[ $alvo != "$DISCO" && $alvo != "$BOOTDISK" ]]', src)
        self.assertIn('^' + '(ata|sata|nvme)' + '$', src)
        self.assertIn('FORMATAR_SECUNDARIOS=()', src)
        self.assertIn('FORMATAR_SECUNDARIOS_IDS=()', src)
        self.assertIn('Digite 1 ou 2:', src)
        self.assertIn('case $CALLAS_FORMATAR_RESPOSTA in', src)
        self.assertNotIn('CALLAS_FORMATAR_CONFIRMA', selection_body())
        self.assertNotIn('CONFIRMAÇÃO FINAL', selection_body())
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
