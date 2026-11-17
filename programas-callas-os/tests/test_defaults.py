"""Selective default restoration, without real package-manager mutations."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

UP = Path(__file__).resolve().parents[1] / 'atualizador'

def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), UP / (name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


class DefaultsTests(unittest.TestCase):
    def setUp(self):
        self.helper = load('callas-defaults')
        self.apps = load('callas-apps')
        self.spotify = dict(name='spotify', source='aur', title='Spotify', icon='spotify', description='Música')
        self.haruna = dict(name='haruna', source='repo', title='Haruna', icon='haruna', description='Vídeos')

    def test_widget_offer_uses_personal_package_status_and_no_package_queries(self):
        entry = dict(name='com.github.prayag2.modernclock', source='plasmoid', title='Relógio Moderno',
                     icon='clock', description='Relógio')
        widget = type('Widget', (), {'package_installed': lambda self: True,
                                    'PAYLOAD': Path(__file__)})()
        with patch.object(self.helper, 'widget_module', return_value=widget), patch.object(self.helper, 'query') as query:
            row = self.helper.metadata(entry, {'native':{}, 'flatpak':{}})
        self.assertTrue(row['installed'])
        self.assertEqual(row['id'], 'plasmoid:com.github.prayag2.modernclock')
        self.assertEqual(row['download'], 'Incluído no Callas OS')
        query.assert_not_called()

    def test_personal_widget_restore_never_uses_native_package_installation(self):
        entry = dict(name='com.github.prayag2.modernclock', source='plasmoid', title='Relógio Moderno',
                     icon='clock', description='Relógio')
        with patch.object(self.helper, 'defaults', return_value=[entry]), \
                patch.object(self.helper.os, 'geteuid', return_value=1000), \
                patch.object(self.helper, 'widget_module') as widget, \
                patch.object(self.helper, 'apps_module') as apps:
            self.helper.restore('fixture', ['plasmoid:com.github.prayag2.modernclock'])
            widget.return_value.install.assert_called_once_with()
            apps.assert_not_called()

    def test_restore_only_selected_and_clear_only_confirmed_choice(self):
        installed = {'native': {}, 'flatpak': {}}
        def install(entry, user): installed['native'][entry['name']] = '1'
        with tempfile.TemporaryDirectory() as temp, patch.object(self.apps, 'STATE', Path(temp)), \
                patch.object(self.helper, 'apps_module', return_value=self.apps), \
                patch.object(self.helper, 'defaults', return_value=[self.spotify, self.haruna]), \
                patch.object(self.apps, 'inventory', side_effect=lambda: installed), \
                patch.object(self.apps, 'install', side_effect=install) as install_mock:
            self.apps.remember_removal('native', 'spotify'); self.apps.remember_removal('native', 'haruna')
            self.helper.restore('fixture', ['native:spotify'])
            self.assertEqual([c.args[0]['name'] for c in install_mock.call_args_list], ['spotify'])
            self.assertEqual(self.apps.removed_choices(), {'native:haruna'})

    def test_validate_all_ids_before_any_install_and_keep_choice_on_failure(self):
        with patch.object(self.helper, 'defaults', return_value=[self.spotify]), \
                patch.object(self.helper, 'apps_module') as apps:
            with self.assertRaises(ValueError): self.helper.restore('fixture', ['native:spotify', 'native:linux'])
            apps.assert_not_called()
            apps.return_value.inventory.return_value = {'native': {}, 'flatpak': {}}
            apps.return_value.install.side_effect = RuntimeError('blocked')
            with self.assertRaises(RuntimeError): self.helper.restore('fixture', ['native:spotify'])
            apps.return_value.forget_removal.assert_not_called()

    def test_partial_success_is_remembered_and_no_other_app_is_restored(self):
        installed = {'native': {}, 'flatpak': {}}
        def install(entry, user):
            if entry['name'] == 'haruna': raise RuntimeError('dependency')
            installed['native'][entry['name']] = '1'
        with patch.object(self.helper, 'defaults', return_value=[self.spotify, self.haruna]), \
                patch.object(self.helper, 'apps_module') as apps:
            apps.return_value.inventory.side_effect = lambda: installed
            apps.return_value.install.side_effect = install
            with self.assertRaises(RuntimeError): self.helper.restore('fixture', ['native:spotify', 'native:haruna'])
            apps.return_value.forget_removal.assert_called_once_with('native', 'spotify')

    def test_metadata_errors_keep_installed_version_and_size_honest(self):
        with patch.object(self.helper, 'query', side_effect=RuntimeError('offline')):
            row = self.helper.metadata(self.haruna, {'native': {'haruna': '1.0'}, 'flatpak': {}})
        self.assertTrue(row['installed']); self.assertEqual(row['version'], '1.0')
        self.assertEqual(row['size'], 'Não informado'); self.assertIn('indisponíveis', row['notice'])

    def test_repository_metadata_uses_read_only_queries_and_local_installed_size(self):
        answers = ['Installed Size : 10 MiB\n',
                   'Version : 2.0\nDownload Size : 5 MiB\nInstalled Size : 20 MiB\n']
        with patch.object(self.helper, 'query', side_effect=answers) as query:
            row = self.helper.metadata(self.haruna, {'native': {'haruna': '1.0'}, 'flatpak': {}})
        self.assertEqual((row['version'], row['available'], row['size'], row['download']),
                         ('1.0', '2.0', '10 MiB', '5 MiB'))
        self.assertEqual([c.args[0][1] for c in query.call_args_list], ['-Qi', '-Si'])

    def test_installed_size_survives_missing_sync_metadata(self):
        with patch.object(self.helper, 'query', side_effect=['Installed Size : 10 MiB\n', RuntimeError('offline')]):
            row = self.helper.metadata(self.haruna, {'native': {'haruna': '1.0'}, 'flatpak': {}})
        self.assertEqual(row['size'], '10 MiB'); self.assertEqual(row['version'], '1.0')

    def test_catalog_excludes_drivers_and_retired_apps(self):
        entries = self.helper.defaults()
        self.assertIn('spotify', [entry['name'] for entry in entries])
        self.assertIn('qbittorrent', [entry['name'] for entry in entries])
        self.assertNotIn('gpu-screen-recorder-gtk', [entry['name'] for entry in entries])
        for entry in entries:
            if entry['source'] != 'flatpak': self.assertFalse(self.apps.native().frozen(entry['name']))

if __name__ == '__main__': unittest.main()
