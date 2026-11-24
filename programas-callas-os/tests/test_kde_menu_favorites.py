"""Exercise the staged KDE defaults without accessing a live user profile."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
UPDATER = ROOT / 'programas-callas-os/atualizador'
AVATAR = ROOT / 'assets/profile-pictures/callas-profile.png'
HELPER = UPDATER / 'callas-kde-defaults.py'
EXPECTED = [
    'io.github.Callas157.AtualizadorDoSistema.desktop',
    'steam.desktop',
    'discord.desktop',
    'systemsettings.desktop',
    'org.kde.konsole.desktop',
]


class KdeDefaultsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.gallery = self.root / 'usr/share/plasma/avatars/callas-profile.png'
        self.accounts = self.root / 'var/lib/AccountsService'

    def provision(self, *, initial_user=None):
        self.assertTrue(HELPER.is_file(), 'Falta o provisionamento compartilhado do KDE')
        spec = importlib.util.spec_from_file_location('kde_defaults', HELPER)
        defaults = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(defaults)
        defaults.provision(AVATAR, root=self.root, initial_user=initial_user)

    def test_defaults_include_system_settings_and_konsole(self):
        self.provision()
        lines = (self.root / 'etc/xdg/kicker-extra-favoritesrc').read_text().splitlines()
        self.assertEqual(lines, ['[General]', 'IgnoreDefaults=true', 'Prepend=' + ';'.join(EXPECTED) + ';'])

    def test_clean_install_sets_initial_avatar_and_installs_gallery_copy(self):
        self.provision(initial_user='fixture')
        icon = self.accounts / 'icons/fixture'
        record = self.accounts / 'users/fixture'
        self.assertEqual(self.gallery.read_bytes(), AVATAR.read_bytes())
        self.assertEqual(icon.read_bytes(), self.gallery.read_bytes())
        self.assertEqual(record.read_text(), '[User]\nIcon=/var/lib/AccountsService/icons/fixture\n')
        self.assertEqual(icon.stat().st_mode & 0o777, 0o644)
        self.assertEqual(record.stat().st_mode & 0o777, 0o600)

    def test_upgrade_preserves_custom_avatar_and_personal_favorites(self):
        icon = self.accounts / 'icons/fixture'
        record = self.accounts / 'users/fixture'
        local = self.root / 'home/fixture/.face.icon'
        favorites = self.root / 'home/fixture/.config/kactivitymanagerd-statsrc'
        personal_files = {icon: b'personal image', record: b'[User]\nIcon=personal\n',
                          local: b'legacy image', favorites: b'personal favorites'}
        for path, content in personal_files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        self.provision()
        for path, content in personal_files.items():
            self.assertEqual(path.read_bytes(), content)
        self.assertEqual(self.gallery.read_bytes(), AVATAR.read_bytes())
        self.assertEqual(list((self.accounts / 'icons').iterdir()), [icon])

    def test_interrupted_install_can_finish_initial_avatar_registration(self):
        icon = self.accounts / 'icons/fixture'
        icon.parent.mkdir(parents=True)
        icon.write_bytes(AVATAR.read_bytes())
        self.provision(initial_user='fixture')
        self.assertTrue((self.accounts / 'users/fixture').is_file())

    def test_staging_feeds_both_clean_install_and_updates(self):
        release = (UPDATER / 'callas-release.py').read_text()
        security = (UPDATER / 'callas-security.sh').read_text()
        updater = (UPDATER / 'callas-config-update.sh').read_text()
        installer = (ROOT / 'instalar-arch.sh').read_text()
        self.assertIn('"assets/profile-pictures/callas-profile.png"', release)
        self.assertIn('"programas-callas-os/atualizador/callas-kde-defaults.py"', release)
        self.assertIn('callas-security.sh" "$usuario" --installation', installer)
        self.assertIn('callas-kde-defaults.py" "$stage/callas-profile.png" --initial-user "$usuario"', security)
        preboot = updater.split('# CALLAS_PHASE_END apps', 1)[1].split('grub_compativel=0', 1)[0]
        self.assertIn('if phase_needed desktop;', preboot)
        self.assertIn('callas-kde-defaults.py" "$CALLAS_RELEASE_DIR/callas-profile.png"', preboot)
        self.assertNotIn('--initial-user', updater)

    def test_dock_is_separate_from_menu_favorites(self):
        source = (ROOT / 'instalar-arch.sh').read_text()
        self.assertIn('const callasLaunchers = ["applications:org.kde.dolphin.desktop"]', source)
        self.assertIn('callasLaunchers.push("applications:brave-origin.desktop")', source)
        self.assertIn('callasLaunchers.push("applications:brave-browser.desktop")', source)


if __name__ == '__main__':
    unittest.main()
