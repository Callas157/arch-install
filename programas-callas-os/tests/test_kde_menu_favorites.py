"""Verifica os favoritos padrão do menu KDE, separadamente da dock.

Não modifica sessão ou banco de favoritos pessoal do usuário.
"""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "instalar-arch.sh"
UPDATE = ROOT / "programas-callas-os/atualizador/callas-config-update.sh"
EXPECTED = [
    "io.github.Callas157.AtualizadorDoSistema.desktop",
    "steam.desktop",
    "discord.desktop",
    "systemsettings.desktop",
]


def favorites(source: str, destination: str, end_token: str):
    pattern = (
        r"cat > " + re.escape(destination)
        + r" <<'" + re.escape(end_token) + r"'\\n(.*?)\\n"
        + re.escape(end_token) + r"(?:\\n|$)"
    )
    match = re.search(pattern, source, re.DOTALL)
    if match is None:
        raise AssertionError("Configuração KDE não encontrada: " + destination)
    lines = match.group(1).splitlines()
    if lines[:2] != ["[General]", "IgnoreDefaults=true"]:
        raise AssertionError("Padrão do KDE não foi isolado.")
    entries = [line for line in lines if line.startswith("Prepend=")]
    if len(entries) != 1:
        raise AssertionError("É obrigatório um único Prepend.")
    value = entries[0].removeprefix("Prepend=")
    return [entry for entry in value.split(";") if entry]


class FavoritesTests(unittest.TestCase):
    def test_installer_has_only_four(self):
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertEqual(
            favorites(source, "/mnt/etc/xdg/kicker-extra-favoritesrc", "KICKER_FAVORITES"),
            EXPECTED,
        )

    def test_update_uses_identical_defaults(self):
        source = UPDATE.read_text(encoding="utf-8")
        self.assertEqual(
            favorites(source, "/etc/xdg/kicker-extra-favoritesrc", "EOF"),
            EXPECTED,
        )
        self.assertIn("# CALLAS_PHASE_BEGIN desktop", source)
        self.assertIn("# CALLAS_PHASE_END desktop", source)

    def test_dock_is_separate_from_menu_favorites(self):
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertIn('const callasLaunchers = ["applications:org.kde.dolphin.desktop"]', source)
        self.assertIn('callasLaunchers.push("applications:brave-origin.desktop")', source)
        self.assertIn('callasLaunchers.push("applications:brave-browser.desktop")', source)
        # No mutation of user ActivityManager databases or personal favorites.
        updater = UPDATE.read_text(encoding="utf-8")
        self.assertNotIn("kactivitymanagerd-statsrc", updater)
        self.assertNotIn("favoriteApps", updater)


if __name__ == "__main__":
    unittest.main()
