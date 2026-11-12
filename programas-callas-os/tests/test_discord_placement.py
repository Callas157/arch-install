"""Discord-only placement migration; preserve learned geometry and other apps."""
import configparser
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('discordplacement', ROOT / 'janelas/callas-janelas.py')
win = importlib.util.module_from_spec(spec)
spec.loader.exec_module(win)

class DiscordPlacementTests(unittest.TestCase):
    def sample(self, **extra):
        return dict(app='discord', role='', output='HDMI-A-1', x=2880, y=0,
                    width=960, height=1080, maxH=False, maxV=False, **extra)

    def test_migration_repairs_position_and_screen_once_without_changing_size(self):
        rule = dict(Description='Callas OS: lembrar discord', wmclass='discord',
                    position='810,335', positionrule='4', size='960,1080',
                    sizerule='4', screen='0', screenrule='4', maximizevert='false')
        self.assertGreater(win.repair_discord_rule(rule, self.sample(), ['DP-3', 'HDMI-A-1']), 0)
        self.assertEqual((rule['position'], rule['screen']), ('2880,0', '1'))
        self.assertEqual((rule['positionrule'], rule['sizerule'], rule['size']), ('4', '4', '960,1080'))
        self.assertEqual((rule['ignoregeometry'], rule['ignoregeometryrule']), ('true', '2'))
        before = dict(rule)
        wrong = self.sample(); wrong.update(x=0, y=335, output='DP-3')
        self.assertEqual(win.repair_discord_rule(rule, wrong, ['DP-3', 'HDMI-A-1']), 0)
        self.assertEqual(rule, before)

    def test_closed_discord_preserves_learned_values_without_guessing_a_monitor(self):
        rule = dict(Description='Callas OS: lembrar discord', wmclass='discord', position='-960,0', size='960,1080')
        win.repair_discord_rule(rule, None, [])
        self.assertEqual(rule['position'], '-960,0')
        self.assertNotIn('screen', rule)
        self.assertEqual(rule['size'], '960,1080')

    def test_maximized_sample_does_not_replace_restore_position(self):
        rule = dict(Description='Callas OS: lembrar discord', wmclass='discord', position='2880,0', screen='1')
        sample = self.sample(); sample['maxV'] = True; sample['x'] = 0
        win.repair_discord_rule(rule, sample, ['DP-3', 'HDMI-A-1'])
        self.assertEqual(rule['position'], '2880,0')
        self.assertEqual(rule['screen'], '1')

    def test_other_apps_and_user_authored_discord_rules_are_untouched(self):
        for app, desc in [('spotify', 'Callas OS: lembrar spotify'), ('steam', 'Steam'), ('discord', 'Minha regra Discord')]:
            rule = dict(Description=desc, wmclass=app, position='42,19', size='500,700')
            before = dict(rule)
            self.assertEqual(win.repair_discord_rule(rule, self.sample(), ['DP-3', 'HDMI-A-1']), 0)
            self.assertEqual(rule, before)

    def test_full_rules_migration_preserves_spotify_steam_brave_and_custom_sections(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); path = root / 'kwinrulesrc'
            cfg = configparser.ConfigParser(interpolation=None); cfg.optionxform = str
            cfg['General'] = {'rules': 'discord,spotify,steam,brave,brave-browser,custom', 'count': '6'}
            for app in ('discord', 'spotify', 'steam', 'brave', 'brave-browser'):
                cfg[app] = dict(Description='Callas OS: lembrar ' + app, wmclass=app,
                    position='810,335', positionrule='4', size='960,1080', sizerule='4',
                    screen='0', screenrule='4', maximizehorizrule='4', maximizevertrule='4')
            cfg['custom'] = {'Description': 'Meu editor', 'wmclass': 'kate', 'position': '99,44'}
            with path.open('w') as stream: cfg.write(stream)
            original = {section: dict(cfg[section]) for section in cfg.sections() if section != 'discord'}
            fake = types.SimpleNamespace(Interface=lambda *args: types.SimpleNamespace(reconfigure=lambda: None))
            session = types.SimpleNamespace(get_object=lambda *args: None)
            with patch.object(win, 'CONFIG', root), patch.object(win, 'STATE', root / 'state'), \
                 patch.object(win, 'bus', return_value=session), patch.dict(sys.modules, {'dbus': fake}), \
                 patch.object(win, 'outputs', return_value=[{'name': 'DP-3', 'priority': 1}, {'name': 'HDMI-A-1', 'priority': 2}]):
                win.remember_rules([self.sample()])
                migrated = configparser.ConfigParser(interpolation=None); migrated.optionxform = str; migrated.read(path)
                for section, values in original.items(): self.assertEqual(dict(migrated[section]), values)
                self.assertEqual(migrated['discord']['position'], '2880,0')
                before = path.read_bytes()
                win.remember_rules([self.sample()])
                self.assertEqual(path.read_bytes(), before)
                self.assertEqual(len(list((root / 'state/window-backups').glob('*/kwinrulesrc'))), 1)

if __name__ == '__main__': unittest.main()
