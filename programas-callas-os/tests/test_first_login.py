"""First-login autostart regressions using temporary profiles and mocked apps."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('autostart', ROOT / 'sessao/callas-autostart.py')
autostart = importlib.util.module_from_spec(spec); spec.loader.exec_module(autostart)

class FirstLoginTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.home = Path(self.temp.name)
        self.config = self.home / '.config'; self.config.mkdir()
        self.state = self.home / '.local/state'
        self.environment = patch.dict(os.environ, {'XDG_CONFIG_HOME':str(self.config),
            'XDG_CONFIG_DIRS':str(self.home / 'global'), 'XDG_STATE_HOME':str(self.state)})
        self.environment.start()
    def tearDown(self): self.environment.stop(); self.temp.cleanup()
    def configure(self, first=False):
        code = (ROOT / 'sessao/callas-inicio-kde.sh').read_text().split("python3 - <<'PY'\n",1)[1].split('\nPY',1)[0]
        def which(name):
            return '/usr/bin/' + name if name in ('steam','discord','solaar') else None
        with patch.dict(os.environ, {'CALLAS_PREPARE_FIRST_LOGIN':'1' if first else '0'}), \
             patch('pathlib.Path.home',return_value=self.home), patch('shutil.which',side_effect=which), \
             patch('subprocess.run',return_value=types.SimpleNamespace(returncode=1)), \
             patch('subprocess.check_output',return_value='emptySession'):
            exec(compile(code,'session-fixture','exec'),{})
    def launch(self, app):
        command = ['/usr/bin/' + app] + (['-silent'] if app == 'steam' else [])
        with patch.object(autostart.os,'geteuid',return_value=1000), \
             patch.object(sys,'argv',['callas-autostart',app,*command]), patch.object(autostart.os,'execvp') as execute:
            autostart.main()
        return execute
    def test_clean_install_skips_each_app_once_then_starts_normally(self):
        self.configure(first=True)
        for app in ('steam','discord'):
            self.assertEqual(self.launch(app).call_count,0)
        self.assertEqual(list((self.state/'callas-os').glob('*.pending')),[])
        self.launch('steam').assert_called_once_with('/usr/bin/steam',['/usr/bin/steam','-silent'])
        self.launch('discord').assert_called_once_with('/usr/bin/discord',['/usr/bin/discord'])
    def test_migration_never_arms_first_login_and_keeps_existing_settings(self):
        settings = self.config/'discord/settings.json'; settings.parent.mkdir()
        settings.write_text(json.dumps({'accountPreference':'keep','windowBounds':{'x':1920,'y':20}}))
        self.configure()
        self.assertFalse((self.state/'callas-os').exists())
        self.assertEqual(json.loads(settings.read_text())['accountPreference'],'keep')
        self.assertEqual(json.loads(settings.read_text())['windowBounds'],{'x':1920,'y':20})
        self.assertEqual(self.launch('steam').call_count,1)
        self.assertEqual(self.launch('discord').call_count,1)
    def test_repair_does_not_rearm_consumed_markers(self):
        self.configure(first=True); self.launch('steam'); self.launch('discord')
        self.configure()
        self.assertEqual(self.launch('steam').call_count,1)
        self.assertEqual(self.launch('discord').call_count,1)
    def test_repair_before_first_login_preserves_pending_markers(self):
        self.configure(first=True); self.configure()
        self.assertEqual(self.launch('steam').call_count,0)
        self.assertEqual(self.launch('discord').call_count,0)
    def test_only_steam_and_discord_use_guard_other_autostarts_are_unchanged(self):
        self.configure(first=True)
        auto = self.config/'autostart'
        self.assertIn('callas-autostart steam /usr/bin/steam -silent',(auto/'steam.desktop').read_text())
        self.assertIn('callas-autostart discord /usr/bin/discord',(auto/'callas-discord.desktop').read_text())
        solaar=(auto/'solaar.desktop').read_text()
        self.assertIn('--window=hide',solaar); self.assertNotIn('callas-autostart',solaar)
        self.assertFalse(any('brave' in p.read_text().lower() and 'Exec=' in p.read_text() for p in auto.glob('*.desktop')))
    def test_invalid_app_is_rejected_without_consuming_steam_marker(self):
        self.configure(first=True)
        with self.assertRaises(ValueError): autostart.skip_first_start('brave')
        self.assertTrue((self.state/'callas-os/first-login-steam.pending').exists())
    def test_installer_is_the_only_caller_that_arms_clean_login(self):
        installer=(ROOT.parent/'instalar-arch.sh').read_text()
        updater=(ROOT/'atualizador/callas-config-update.sh').read_text()
        self.assertIn('como_usuario "$libexec/callas-inicio-kde" --preparar-primeiro-login',installer)
        self.assertNotIn('--preparar-primeiro-login',updater)
        self.assertNotIn('first-login-',updater)
    def test_existing_brave_preferences_are_not_rewritten_even_if_malformed(self):
        updater=(ROOT/'atualizador/callas-config-update.sh').read_text()
        section=updater[updater.index('brave_pref='):updater.index('# Coleção atual de wallpapers')]
        pref=self.home/'.config/BraveSoftware/Brave-Browser/Default/Preferences'; pref.parent.mkdir(parents=True)
        for content in (b'{"account":"keep","extensions":{"settings":{"id":"keep"}}}',b'{invalid-profile'):
            for running in (True,False):
                pref.write_bytes(content)
                code='home="$PROFILE_HOME"\nusuario=fixture\npgrep() { return '+('0' if running else '1')+'; }\ncomo_usuario() { echo "unexpected profile writer" >&2; return 99; }\n'+section
                subprocess.run(['bash','-eu','-c',code],env=dict(os.environ,PROFILE_HOME=str(self.home)),check=True,capture_output=True)
                self.assertEqual(pref.read_bytes(),content)

if __name__=='__main__': unittest.main()
