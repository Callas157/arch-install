"""Recovery of the unsuccessful Discord override and placement diagnostics."""
import configparser
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('discordplacement', ROOT / 'janelas/callas-janelas.py')
win = importlib.util.module_from_spec(spec); spec.loader.exec_module(win)

class DiscordPlacementTests(unittest.TestCase):
    def fixture_rules(self, root, modern=True):
        cfg=configparser.ConfigParser(interpolation=None);cfg.optionxform=str
        cfg['General']={('Order' if modern else 'rules'):'custom,discord,spotify'}
        cfg['custom']=dict(Description='Minha regra',wmclass='kate',position='41,29',positionrule='4')
        for app in ('discord','spotify'):
            cfg[app]=dict(Description='Callas OS: lembrar '+app,wmclass=app,position='961,0',size='959,1080',
                positionrule='4',sizerule='4',screenrule='4',screen='1',maximizehorizrule='4',maximizehoriz='false',
                maximizevertrule='4',maximizevert='false',fullscreenrule='4',fullscreen='false')
        path=root/'kwinrulesrc'
        with path.open('w') as stream:cfg.write(stream)
        return cfg,path

    def run_rules(self, root, windows):
        fake=types.SimpleNamespace(Interface=lambda *args:types.SimpleNamespace(reconfigure=lambda:None))
        with patch.object(win,'CONFIG',root),patch.object(win,'STATE',root/'state'),patch.object(win,'bus'), \
                patch.dict(sys.modules,{'dbus':fake}),patch.object(win,'outputs',return_value=[{'name':'DP-3','priority':1},{'name':'HDMI-A-1','priority':2}]):
            win.remember_rules(windows)
        cfg=configparser.ConfigParser(interpolation=None);cfg.optionxform=str;cfg.read(root/'kwinrulesrc');return cfg

    def test_modern_order_keeps_original_ids_and_prevents_kwin_purging_other_rules(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);before,path=self.fixture_rules(root)
            cfg=self.run_rules(root,[self.sample()])
            # KWin 6.8 migrates a nonempty legacy list by deleting groups absent
            # from it. An updater must not introduce that incomplete list.
            legacy=cfg['General'].get('rules','')
            surviving=set(legacy.split(',')) if legacy else set(cfg.sections())
            self.assertTrue({'custom','discord','spotify'}<=surviving)
            self.assertNotIn('rules',cfg['General'])
            self.assertEqual(cfg['General']['Order'].split(',')[:3],['custom','discord','spotify'])
            for section in ('custom','discord','spotify'):self.assertEqual(dict(cfg[section]),dict(before[section]))
            original=path.read_bytes();self.run_rules(root,[dict(self.sample(),x=2000,output='DP-3')])
            self.assertEqual(path.read_bytes(),original)

    def test_legacy_order_includes_stray_groups_before_native_migration(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);cfg,path=self.fixture_rules(root,modern=False)
            cfg['unlisted']=dict(Description='Outra regra pessoal',wmclass='konsole',size='800,600')
            with path.open('w') as stream:cfg.write(stream)
            after=self.run_rules(root,[])
            self.assertIn('unlisted',after['General']['rules'].split(','))
            self.assertEqual(dict(after['unlisted']),dict(cfg['unlisted']))

    def test_closed_discord_remembers_monitor_maximize_and_fullscreen_without_forcing_primary(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg=self.run_rules(Path(temp),[])
            rule=next(cfg[s] for s in cfg.sections() if cfg[s].get('wmclass')=='discord')
            for key in ('positionrule','sizerule','screenrule','maximizehorizrule','maximizevertrule','fullscreenrule'):
                self.assertEqual(rule.get(key),'4',key)
            self.assertNotIn('screen',rule)

    def test_fullscreen_sample_is_saved_and_modern_order_is_used_in_diagnostics(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'kwinrulesrc').write_text('[General]\nOrder=personal\n[personal]\nwmclass=kate\n')
            cfg=self.run_rules(root,[dict(self.sample(),fullScreen=True)])
            ident=next(s for s in cfg.sections() if cfg[s].get('wmclass')=='discord')
            self.assertEqual(cfg[ident].get('fullscreen'),'true')
            with patch.object(win,'CONFIG',root),patch.object(win,'outputs',return_value=[]):
                report=win.discord_state([])
            self.assertEqual(report['rules'][0]['order'],cfg['General']['Order'].split(',').index(ident))

    def sample(self):
        return dict(app='discord', rawClass='Discord', role='', output='HDMI-A-1', x=2880, y=0,
                    width=960, height=1080, maxH=False, maxV=False)

    def test_remove_only_unsuccessful_override_without_promoting_a_startup_position(self):
        rule = dict(Description='Callas OS: lembrar discord', wmclass='discord',
                    position='810,335', positionrule='4', size='960,1080', sizerule='4',
                    screen='0', screenrule='4', maximizevert='false',
                    ignoregeometry='true', ignoregeometryrule='2')
        before = dict(rule)
        self.assertEqual(win.repair_discord_rule(rule, self.sample(), ['DP-3','HDMI-A-1']), 2)
        expected = {k:v for k,v in before.items() if k not in ('ignoregeometry','ignoregeometryrule')}
        self.assertEqual(rule, expected)
        self.assertEqual(win.repair_discord_rule(rule, self.sample(), ['DP-3','HDMI-A-1']), 0)
        self.assertEqual(rule, expected)

    def test_closed_or_maximized_discord_does_not_lose_geometry(self):
        for sample in (None, dict(self.sample(), maxV=True)):
            rule = dict(Description='Callas OS: lembrar discord', wmclass='discord', position='-960,0',
                        size='960,1080', ignoregeometry='true', ignoregeometryrule='2')
            win.repair_discord_rule(rule, sample, [])
            self.assertEqual(rule['position'],'-960,0');self.assertEqual(rule['size'],'960,1080')
            self.assertNotIn('screen',rule)

    def test_other_apps_user_authored_rules_and_other_geometry_policies_untouched(self):
        for app, desc, ignore, policy in [('spotify','Callas OS: lembrar spotify','true','2'),
             ('steam','Steam','true','2'),('discord','Minha regra Discord','true','2'),
             ('discord','Callas OS: lembrar discord','false','3')]:
            rule = dict(Description=desc,wmclass=app,position='42,19',size='500,700',ignoregeometry=ignore,ignoregeometryrule=policy)
            before=dict(rule)
            self.assertEqual(win.repair_discord_rule(rule,self.sample(),['DP-3','HDMI-A-1']),0)
            self.assertEqual(rule,before)

    def test_full_rules_recovery_preserves_spotify_steam_brave_and_custom_sections(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path=root/'kwinrulesrc';cfg=configparser.ConfigParser(interpolation=None);cfg.optionxform=str
            cfg['General']={'rules':'discord,spotify,steam,brave,brave-browser,brave-origin,brave-origin-browser,custom','count':'8'}
            for app in ('discord','spotify','steam','brave','brave-browser','brave-origin','brave-origin-browser'):
                cfg[app]=dict(Description='Callas OS: lembrar '+app,wmclass=app,position='810,335',positionrule='4',
                    size='960,1080',sizerule='4',screen='0',screenrule='4',maximizehorizrule='4',maximizevertrule='4')
            cfg['discord'].update(ignoregeometry='true',ignoregeometryrule='2')
            cfg['custom']={'Description':'Meu editor','wmclass':'kate','position':'99,44'}
            with path.open('w') as stream:cfg.write(stream)
            original={section:dict(cfg[section]) for section in cfg.sections() if section!='discord'}
            fake=types.SimpleNamespace(Interface=lambda *args:types.SimpleNamespace(reconfigure=lambda:None))
            session=types.SimpleNamespace(get_object=lambda *args:None)
            with patch.object(win,'CONFIG',root),patch.object(win,'STATE',root/'state'),patch.object(win,'bus',return_value=session), \
                 patch.dict(sys.modules,{'dbus':fake}),patch.object(win,'outputs',return_value=[{'name':'DP-3','priority':1},{'name':'HDMI-A-1','priority':2}]):
                win.remember_rules([self.sample()])
                migrated=configparser.ConfigParser(interpolation=None);migrated.optionxform=str;migrated.read(path)
                for section,values in original.items():self.assertEqual(dict(migrated[section]),values)
                self.assertEqual(migrated['discord']['position'],'810,335')
                self.assertNotIn('ignoregeometryrule',migrated['discord'])
                before=path.read_bytes();win.remember_rules([self.sample()]);self.assertEqual(path.read_bytes(),before)
                self.assertEqual(len(list((root/'state/window-backups').glob('*/kwinrulesrc'))),1)

    def test_diagnostic_records_actual_class_screen_and_conflicting_rules_without_personal_data(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'discord').mkdir()
            (root/'discord/settings.json').write_text(json.dumps({'WINDOW_BOUNDS':{'x':2880,'y':0,'width':960,'height':1080},'TOKEN':'SECRET','EMAIL':'PRIVATE'}))
            (root/'kwinrulesrc').write_text('[General]\nrules=custom,managed\n[managed]\nDescription=Callas OS: lembrar discord\nwmclass=discord\nposition=810,335\n[custom]\nDescription=private description\nwmclass=Discord\ntitle=private channel\nposition=0,0\n')
            with patch.object(win,'CONFIG',root),patch.object(win,'outputs',return_value=[{'name':'HDMI-A-1','priority':2,'pos':{'x':1920,'y':0},'modes':['huge']} ]):
                report=win.discord_state([self.sample(),{'app':'spotify','title':'private song'}])
            text=json.dumps(report)
            for private in ('SECRET','PRIVATE','private description','private channel','private song','huge'):self.assertNotIn(private,text)
            self.assertEqual(report['windows'][0]['rawClass'],'Discord')
            self.assertEqual(report['discord_bounds']['WINDOW_BOUNDS']['x'],2880)
            self.assertEqual([r['order'] for r in report['rules']],[1,0])
            self.assertEqual(report['outputs'][0]['pos'],{'x':1920,'y':0})

    def test_diagnostic_is_attempted_even_when_saving_rules_fails(self):
        with patch.object(win,'capture_windows',return_value=[self.sample()]),patch.object(win,'discord_state',return_value={'before':True}), \
             patch.object(win,'remember_rules',side_effect=RuntimeError('cannot save')),patch.object(win,'log_discord_state') as log:
            with self.assertRaisesRegex(RuntimeError,'cannot save'):win.remember_windows()
            log.assert_called_once_with({'before':True},[self.sample()])

    def test_diagnostic_errors_do_not_replace_a_successful_rule_operation(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(win,'CONFIG',Path(temp)),patch.object(win,'outputs',side_effect=RuntimeError('no kscreen')):
            (Path(temp)/'discord').mkdir();(Path(temp)/'discord/settings.json').write_text('bad json')
            result=win.discord_state([])
            self.assertIn('outputs_error',result);self.assertEqual(result['bounds_error'],'JSONDecodeError')
        with patch.object(win.Path,'is_file',return_value=True),patch.object(win,'discord_state',return_value={}), \
             patch.object(win.subprocess,'run',side_effect=OSError('no logger')):
            win.log_discord_state({},[])

if __name__=='__main__':unittest.main()
