"""Regression checks without a running Plasma/SDDM session.
Run: python -m unittest discover -s programas-callas-os/tests -v
Hardware acceptance steps are documented in README; these are not GUI tests.
"""
import configparser
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
spec = importlib.util.spec_from_file_location('monitores', ROOT / 'monitores/callas-monitores.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
window_spec = importlib.util.spec_from_file_location('janelas', ROOT / 'janelas/callas-janelas.py')
win = importlib.util.module_from_spec(window_spec)
window_spec.loader.exec_module(win)


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.config = patch.object(m, 'CONFIG', self.base)
        self.config.start()
        self.addCleanup(self.config.stop)
        self.state = patch.object(m, 'STATE', self.base / 'callas-os')
        self.state.start()
        self.addCleanup(self.state.stop)
        for name, value in [('CONFIG', self.base), ('STATE', self.base / 'callas-os'),
                            ('bus', lambda: types.SimpleNamespace(get_object=lambda *args: None))]:
            patcher = patch.object(win, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_disconnected_disabled_and_implicit_enabled(self):
        data = {'outputs': [{'name': 'DP-3', 'connected': True},
                            {'name': 'HDMI-A-1', 'connected': True, 'enabled': False},
                            {'name': 'DP-1', 'connected': False, 'enabled': True}]}
        with patch.object(m, 'run', return_value=json.dumps(data)):
            self.assertEqual([x['name'] for x in m.outputs()], ['DP-3'])

    def test_choose_changes_only_priority(self):
        a = {'id': 1, 'name': 'HDMI-A-1', 'priority': 1}
        b = {'id': 2, 'name': 'DP-3', 'priority': 2}
        with patch.object(m, 'outputs', side_effect=[[a, b], [a, b], [a | {'priority': 2}, b | {'priority': 1}]]), \
             patch('builtins.input', return_value='2'), patch.object(m, 'run') as run, \
             patch.object(m, 'apply_desktop') as desktop, \
             patch.object(m.subprocess, 'run') as login:
            m.choose()
        calls = [c.args for c in run.call_args_list]
        self.assertIn(('kscreen-doctor', 'output.2.priority.1', 'output.1.priority.2'), calls)
        self.assertFalse(any('.mode.' in str(c) or '.position.' in str(c) or '.scale.' in str(c) for c in calls))
        self.assertEqual(json.loads((m.STATE / 'monitors.json').read_text())['primary'], 'DP-3')
        desktop.assert_called_once()
        self.assertEqual(login.call_args.args[0][-1], 'DP-3')

    def test_disconnect_between_list_and_choice_aborts(self):
        with patch.object(m, 'outputs', side_effect=[[{'id': 2, 'name': 'DP-3'}], []]), \
             patch('builtins.input', return_value='1'), patch.object(m, 'run') as run:
            with self.assertRaises(RuntimeError):
                m.choose()
            run.assert_not_called()

    def test_cancel_does_not_write_or_request_sudo(self):
        with patch.object(m, 'outputs', return_value=[{'name': 'DP-3'}]), \
             patch('builtins.input', return_value='0'), patch.object(m, 'run') as run:
            m.choose()
            run.assert_not_called()
        self.assertFalse(m.STATE.exists())

    def test_native_rules_preserve_existing_and_learn_half_screen(self):
        path = self.base / 'kwinrulesrc'
        path.write_text('[General]\nrules=custom\ncount=1\n[custom]\nDescription=Meu editor\nwmclass=kate\nposition=17,29\npositionrule=4\n')
        fake = types.SimpleNamespace(Interface=lambda *args: types.SimpleNamespace(reconfigure=lambda: None))
        with patch.dict(sys.modules, {'dbus': fake}), \
             patch.object(m, 'bus', return_value=types.SimpleNamespace(get_object=lambda *args: None)):
            win.remember_rules([{'app': 'discord', 'role': '', 'x': 1920, 'y': 0, 'width': 960, 'height': 1080, 'maxH': False, 'maxV': False}])
            cfg = configparser.ConfigParser()
            cfg.read(path)
            self.assertEqual(cfg['custom']['position'], '17,29')
            rule = next(cfg[s] for s in cfg.sections() if cfg[s].get('wmclass') == 'discord')
            self.assertEqual(rule['position'], '1920,0')
            self.assertEqual(rule['size'], '960,1080')
            self.assertEqual(rule['positionrule'], '4')
            self.assertNotIn('screenrule', rule)
            before = path.read_bytes()
            win.remember_rules([{'app': 'discord', 'role': '', 'x': 0, 'y': 0, 'width': 400, 'height': 400, 'maxH': False, 'maxV': False}])
            self.assertEqual(path.read_bytes(), before)

    def test_equivalent_browser_windows_not_collapsed(self):
        w = {'app': 'brave', 'role': '', 'x': 0, 'y': 0, 'width': 900, 'height': 1000, 'maxH': False, 'maxV': False}
        fake = types.SimpleNamespace(Interface=lambda *args: types.SimpleNamespace(reconfigure=lambda: None))
        with patch.dict(sys.modules, {'dbus': fake}), patch.object(m, 'bus', return_value=types.SimpleNamespace(get_object=lambda *args: None)):
            win.remember_rules([w, w])
        cfg = configparser.ConfigParser()
        cfg.read(self.base / 'kwinrulesrc')
        self.assertFalse(any(cfg[s].get('wmclass') == 'brave' for s in cfg.sections()))

    def test_favorites_are_imported_once(self):
        with patch.object(m, 'favorite') as fav:
            m.session_setup()
            m.session_setup()
            fav.assert_called_once()

    def test_plasma_script_moves_panel_not_windows_or_files(self):
        captured = []
        with patch.object(m, 'run', return_value=str(self.base / 'Desktop')), \
             patch.object(m, 'plasma', side_effect=captured.append), patch.object(m.Path, 'home', return_value=self.base):
            m.apply_desktop()
        js = captured[0]
        harness = '''
let logs=[];
function item(screen,url) {return {screen, url, readConfig:()=>url, writeConfig:function(k,v){this.url=v},reloadConfig:()=>{}}}
const ds=[item(0,'desktop:/'),item(1,'desktop:/'),item(2,'file:///custom')];
const ps=[{screen:1,widgets:()=>[{}]}];
function desktops(){return ds} function panels(){return ps} function print(x){logs.push(x)}
'''+js+'''
if(ds[0].url!=='desktop:/') throw Error('primary folder');
if(!ds[1].url.includes('secondary-desktop')) throw Error('secondary folder');
if(ds[2].url!=='file:///custom') throw Error('custom folder overwritten');
if(ps[0].screen!==0 || !logs.includes('CALLAS_OK')) throw Error('panel');
'''
        subprocess.run(['node', '-e', harness], check=True)
        self.assertNotIn('windowList', js)
        self.assertNotIn('remove()', js)

    def test_installer_helpers_match_update_sources(self):
        installer = (REPO / 'instalar-arch.sh').read_text()
        for name, delim in [('callas-inicio-kde', 'CALLAS_KDE_START'), ('callas-kde-desligamento-login', 'CALLAS_KDE_LOGIN')]:
            embedded = installer.split("<<'"+delim+"'\n", 1)[1].split('\n'+delim+'\n', 1)[0]+'\n'
            self.assertEqual(embedded, (ROOT / ('sessao' if name == 'callas-inicio-kde' else 'monitores') / (name+'.sh')).read_text())
        startup = (ROOT / 'sessao/callas-inicio-kde.sh').read_text()
        self.assertIn('"emptySession"', startup)
        self.assertNotIn('--start-minimized', startup)
        self.assertNotIn('or outro_app_do_usuario', startup)

    def test_mirrored_configuration_aborts_before_sudo(self):
        with patch.object(m, 'outputs', return_value=[{'id': 2, 'name': 'DP-3', 'replicationSource': 1}]), \
             patch('builtins.input', return_value='1'), patch.object(m, 'run') as run:
            with self.assertRaises(RuntimeError):
                m.choose()
            run.assert_not_called()

    def test_priority_failure_does_not_move_panel_or_record_choice(self):
        original = [{'id': 1, 'name': 'HDMI-A-1', 'priority': 1}, {'id': 2, 'name': 'DP-3', 'priority': 2}]
        with patch.object(m, 'outputs', side_effect=[original, original, original]), \
             patch('builtins.input', return_value='2'), patch.object(m, 'run'), patch.object(m, 'apply_desktop') as desktop:
            with self.assertRaises(RuntimeError):
                m.choose()
            desktop.assert_not_called()
        self.assertFalse((m.STATE / 'monitors.json').exists())

    def test_maximized_window_remembers_location_and_state(self):
        w = {'app': 'spotify', 'role': '', 'x': -1920, 'y': 0, 'width': 1920, 'height': 1080, 'maxH': True, 'maxV': True}
        fake = types.SimpleNamespace(Interface=lambda *args: types.SimpleNamespace(reconfigure=lambda: None))
        with patch.dict(sys.modules, {'dbus': fake}), patch.object(m, 'bus', return_value=types.SimpleNamespace(get_object=lambda *args: None)):
            win.remember_rules([w])
        cfg = configparser.ConfigParser()
        cfg.read(self.base / 'kwinrulesrc')
        rule = next(cfg[s] for s in cfg.sections() if cfg[s].get('wmclass') == 'spotify')
        self.assertEqual(rule['position'], '-1920,0')
        self.assertEqual(rule['maximizehoriz'], 'true')
        self.assertEqual(rule['maximizevertrule'], '4')

    def test_autostart_preserves_user_apps_and_discord_geometry(self):
        import os
        auto = self.base / 'autostart'
        auto.mkdir()
        unknown = auto / 'my-tool.desktop'
        unknown.write_text('[Desktop Entry]\nType=Application\nName=Meu app\nExec=/opt/my-tool\n')
        browser = auto / 'brave.desktop'
        browser.write_text('[Desktop Entry]\nType=Application\nName=Brave\nExec=brave\n')
        before = unknown.read_bytes()
        code = (ROOT / 'sessao/callas-inicio-kde.sh').read_text().split("python3 - <<'PY'\n", 1)[1].split('\nPY', 1)[0]
        settings = self.base / 'discord/settings.json'
        settings.parent.mkdir()
        settings.write_text('{"windowBounds":{"x":1920,"y":0,"width":960,"height":1080}}')
        def which(name):
            return '/usr/bin/discord' if name == 'discord' else None
        with patch.dict(os.environ, {'XDG_CONFIG_HOME': str(self.base), 'XDG_CONFIG_DIRS': str(self.base / 'global')}), \
             patch('pathlib.Path.home', return_value=self.base), patch('shutil.which', side_effect=which), \
             patch('subprocess.run', return_value=types.SimpleNamespace(returncode=1)), \
             patch('subprocess.check_output', return_value='emptySession'):
            exec(compile(code, 'callas-inicio-kde', 'exec'), {})
        self.assertEqual(unknown.read_bytes(), before)
        self.assertIn('Hidden=true', browser.read_text())
        self.assertNotIn('--start-minimized', (auto / 'callas-discord.desktop').read_text())
        self.assertEqual(json.loads(settings.read_text())['windowBounds']['x'], 1920)

    def test_login_theme_patch_is_idempotent_and_keeps_wallpaper(self):
        text = (ROOT / 'monitores/callas-kde-desligamento-login.sh').read_text()
        func = text.split('ajustar_tema_sddm() {', 1)[1].split('\ninstalar_tema_sddm()', 1)[0]
        qml = self.base / 'Main.qml'
        qml.write_text('import QtQuick\nItem {\n Item {\n id: wallpaper\n }\n MouseArea {\n id: loginScreenRoot\n }\n}\n')
        code = 'ajustar_tema_sddm() {' + func + '\najustar_tema_sddm aplicar "$1" DP-3\najustar_tema_sddm aplicar "$1" DP-3\n'
        subprocess.run(['bash', '-eu', '-c', code, 'bash', str(qml)], check=True)
        patched = qml.read_text()
        self.assertEqual(patched.count('inicio do login por tela'), 1)
        self.assertIn('const alvo = "DP-3"', patched)
        self.assertLess(patched.index('id: wallpaper'), patched.index('visible: {'))

    def test_screen_remap_preserves_physical_connector_and_user_rules(self):
        path = self.base / 'kwinrulesrc'
        path.write_text('[General]\nrules=managed,user\n[managed]\nDescription=Callas OS: lembrar discord\nscreenrule=4\nscreen=0\nposition=1920,0\n[user]\nDescription=Minha regra\nscreenrule=4\nscreen=0\n')
        fake = types.SimpleNamespace(Interface=lambda *args: types.SimpleNamespace(reconfigure=lambda: None))
        with patch.dict(sys.modules, {'dbus': fake}), patch.object(m, 'bus', return_value=types.SimpleNamespace(get_object=lambda *args: None)):
            m.remap_rule_screens([{'name': 'HDMI-A-1'}, {'name': 'DP-3'}], [{'name': 'DP-3'}, {'name': 'HDMI-A-1'}])
        cfg = configparser.ConfigParser()
        cfg.read(path)
        self.assertEqual(cfg['managed']['screen'], '1')
        self.assertEqual(cfg['managed']['position'], '1920,0')
        self.assertEqual(cfg['user']['screen'], '0')

    def test_open_window_gets_remember_screen_not_force(self):
        w = {'app': 'discord', 'role': '', 'output': 'HDMI-A-1', 'x': 1920, 'y': 0, 'width': 960, 'height': 1080, 'maxH': False, 'maxV': False}
        fake = types.SimpleNamespace(Interface=lambda *args: types.SimpleNamespace(reconfigure=lambda: None))
        with patch.dict(sys.modules, {'dbus': fake}), patch.object(m, 'bus', return_value=types.SimpleNamespace(get_object=lambda *args: None)), \
             patch.object(win, 'outputs', return_value=[{'name': 'DP-3', 'priority': 1}, {'name': 'HDMI-A-1', 'priority': 2}]):
            win.remember_rules([w])
        cfg = configparser.ConfigParser()
        cfg.read(self.base / 'kwinrulesrc')
        rule = next(cfg[s] for s in cfg.sections() if cfg[s].get('wmclass') == 'discord')
        self.assertEqual(rule['screen'], '1')
        self.assertEqual(rule['screenrule'], '4')

    def test_monitor_choice_does_not_activate_window_memory(self):
        import inspect
        self.assertNotIn('remember_windows', inspect.getsource(m.choose))
        self.assertNotIn('loginMode', inspect.getsource(m.choose))
        self.assertNotIn('Ativar memória', inspect.getsource(m.main))
        self.assertNotIn('kcm_kwinrules', inspect.getsource(m.main))

    def test_window_patch_installs_invisible_activation_and_user_service(self):
        written = {}
        with patch.object(win.os, 'geteuid', return_value=0), \
             patch.object(win, 'atomic', side_effect=lambda path, text, mode: written.update({str(path): text})):
            win.install_system()
        self.assertEqual(len(written), 2)
        self.assertIn('NoDisplay=true', written['/etc/xdg/autostart/callas-janelas.desktop'])
        self.assertIn('callas-janelas --activate', written['/etc/systemd/user/callas-janelas.service'])
        self.assertNotIn('callas-monitores', ''.join(written.values()))

    def test_update_activates_memory_and_install_does_not_open_monitor_tool(self):
        updater = (ROOT / 'atualizador/callas-config-update.sh').read_text()
        installer = (REPO / 'instalar-arch.sh').read_text()
        self.assertIn('start callas-janelas.service', updater)
        self.assertIn('DBUS_SESSION_BUS_ADDRESS="unix:path=$runtime_sessao/bus" systemctl --user', updater)
        self.assertIn('"$libexec/callas-janelas" --install-system', installer)
        self.assertNotIn('callas-monitores.service', updater)
        self.assertNotIn('callas-monitores --first', installer)

    def test_automatic_activation_is_serialized_and_never_calls_monitor_setup(self):
        with patch.object(win.os, 'geteuid', return_value=1000), patch.object(win, 'remember_windows') as remember, \
             patch.object(m, 'choose') as choose:
            win.activate()
            win.activate()
            self.assertEqual(remember.call_count, 2)
            choose.assert_not_called()
        self.assertTrue((win.STATE / 'window-memory.lock').exists())

    def test_closed_app_bootstraps_later_without_overwriting_learned_position(self):
        fake = types.SimpleNamespace(Interface=lambda *args: types.SimpleNamespace(reconfigure=lambda: None))
        with patch.dict(sys.modules, {'dbus': fake}):
            win.remember_rules([])
            cfg = configparser.ConfigParser()
            cfg.optionxform = str
            path = self.base / 'kwinrulesrc'
            cfg.read(path)
            rule = next(cfg[s] for s in cfg.sections() if cfg[s].get('wmclass') == 'spotify')
            rule['position'] = '1920,100'
            rule['size'] = '960,900'
            with path.open('w') as stream:
                cfg.write(stream)
            win.remember_rules([{'app': 'spotify', 'role': '', 'x': 0, 'y': 0, 'width': 1920, 'height': 1080, 'maxH': True, 'maxV': True}])
            cfg.read(path)
            rule = next(cfg[s] for s in cfg.sections() if cfg[s].get('wmclass') == 'spotify')
            self.assertEqual(rule['position'], '1920,100')
            self.assertEqual(rule['size'], '960,900')
            self.assertEqual(rule['maximizehorizrule'], '4')
            self.assertTrue(list((win.STATE / 'window-backups').glob('*/kwinrulesrc')))

    def test_update_migrates_installed_updater_to_new_url(self):
        # Migration replaces the complete root-owned updater, rather than
        # editing downloaded/user-controlled shell code with text substitutions.
        text = (ROOT / 'atualizador/callas-security.sh').read_text()
        self.assertIn('put-update.sh) target=put-update', text)
        self.assertIn('install -o root -g root -m 0755', text)
        installer = (REPO / 'instalar-arch.sh').read_text()
        program = installer.split("<<'CALLAS_UPDATER'\n", 1)[1].split('\nCALLAS_UPDATER\n', 1)[0]
        canonical = (ROOT / 'atualizador/put-update.sh').read_text().rstrip('\n')
        self.assertEqual(program, canonical)
        self.assertIn('sudo /usr/local/libexec/callas-release', program)
        subprocess.run(['bash', '-n'], input=program, text=True, check=True)

    def test_program_sources_use_canonical_updater_after_bridge_retirement(self):
        expected = ['monitores/callas-monitores.py', 'monitores/callas-kde-desligamento-login.sh',
                    'janelas/callas-janelas.py', 'sessao/callas-inicio-kde.sh',
                    'atualizador/callas-config-update.sh', 'tests/test_monitores.py']
        for relative in expected:
            self.assertTrue((ROOT / relative).is_file(), relative)
        for name in ['callas-monitores.py', 'callas-janelas.py', 'callas-inicio-kde.sh', 'callas-kde-desligamento-login.sh', 'tests']:
            self.assertFalse((REPO / name).exists(), name)
        self.assertFalse((REPO / 'callas-config-update.sh').exists())
        canonical = (ROOT / 'atualizador/callas-config-update.sh').read_text()
        self.assertRegex(canonical, r'(?m)^VERSAO="[^"]+"')
        launcher = (ROOT / 'atualizador/put-update.sh').read_text()
        self.assertIn('sudo /usr/local/libexec/callas-release', launcher)
        self.assertIn('main/programas-callas-os/atualizador/callas-config-update.sh', launcher)
        self.assertNotIn('main/callas-config-update.sh', launcher)
        installer = (REPO / 'instalar-arch.sh').read_text()
        self.assertIn('$CALLAS_PROGRAMAS_BASE/monitores/callas-monitores.py', installer)
        self.assertIn('$CALLAS_PROGRAMAS_BASE/janelas/callas-janelas.py', installer)
        self.assertIn('$CALLAS_RELEASE_DIR/$nome', canonical)


if __name__ == '__main__':
    unittest.main()

