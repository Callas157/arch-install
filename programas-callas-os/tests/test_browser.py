"""Browser configuration in disposable roots; never touches actual profiles."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

UP=Path(__file__).resolve().parents[1]/'atualizador'
def load():
    spec=importlib.util.spec_from_file_location('browser_test',UP/'callas-browser.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

class BrowserTests(unittest.TestCase):
    def test_both_variants_receive_same_policies_and_initial_preferences(self):
        browser=load()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in ('brave-bin','brave-origin-bin'):(root/'opt'/name).mkdir(parents=True)
            browser.configure_system(root)
            policies=json.loads((root/'etc/brave/policies/managed/callas-bonjourr.json').read_text())
            self.assertEqual(set(policies['ExtensionSettings']),{'dlnejlppicbjfcfcedcflplfjajinajd','kdbmhfkmnlmbkgbabkdealhhbfhlmmon'})
            a=json.loads((root/'opt/brave-bin/initial_preferences').read_text())
            b=json.loads((root/'opt/brave-origin-bin/initial_preferences').read_text())
            self.assertEqual(a,b);self.assertFalse(a['browser']['custom_chrome_frame'])

    def test_profiles_keep_accounts_extensions_flags_and_default_choice_on_update(self):
        browser=load()
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp)
            for profile,flags in browser.VARIANTS.values():
                pref=home/'.config/BraveSoftware'/profile/'Default/Preferences';pref.parent.mkdir(parents=True)
                pref.write_text('{"account":"keep","extensions":{"custom":1}}')
                (home/'.config'/flags).write_text('--custom-flag\n--lang=en-US\n')
            mime=home/'.config/mimeapps.list';mime.write_text('[Default Applications]\nx-scheme-handler/https=personal.desktop\n')
            with patch.object(browser,'running',return_value=False):self.assertFalse(browser.configure_user(home))
            for profile,flags in browser.VARIANTS.values():
                data=json.loads((home/'.config/BraveSoftware'/profile/'Default/Preferences').read_text())
                self.assertEqual(data['account'],'keep');self.assertEqual(data['extensions'],{'custom':1})
                self.assertIn('kActionTabSearch',data['toolbar']['pinned_actions'])
                self.assertIn('--custom-flag',(home/'.config'/flags).read_text())
                self.assertIn('--lang=pt-BR',(home/'.config'/flags).read_text())
            self.assertIn('personal.desktop',mime.read_text())

    def test_active_or_malformed_profile_is_preserved(self):
        browser=load()
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp);pref=home/'.config/BraveSoftware/Brave-Origin/Default/Preferences';pref.parent.mkdir(parents=True)
            pref.write_text('{invalid')
            with patch.object(browser,'running',return_value=True):self.assertTrue(browser.configure_user(home))
            self.assertEqual(pref.read_text(),'{invalid')
            with patch.object(browser,'running',return_value=False):
                with self.assertRaises(ValueError):browser.configure_user(home)
            self.assertEqual(pref.read_text(),'{invalid')

    def test_clean_install_default_preserves_other_mime_associations(self):
        browser=load()
        with tempfile.TemporaryDirectory() as temp:
            config=Path(temp)
            (config/'mimeapps.list').write_text('[Default Applications]\nimage/png=viewer.desktop\nx-scheme-handler/https=other.desktop\n')
            (config/'kdeglobals').write_text('[General]\nColorScheme=BreezeDark\n')
            browser.default_origin(config)
            self.assertIn('image/png = viewer.desktop',(config/'mimeapps.list').read_text())
            self.assertIn('x-scheme-handler/https = brave-origin.desktop',(config/'mimeapps.list').read_text())
            self.assertIn('ColorScheme = BreezeDark',(config/'kdeglobals').read_text())

    def test_running_origin_uses_executable_path_even_if_argv_name_is_brave(self):
        browser=load()
        with tempfile.TemporaryDirectory() as temp:
            proc=Path(temp);p=proc/'100';p.mkdir()
            (p/'cmdline').write_bytes(b'brave\0--type=renderer\0')
            (p/'exe').symlink_to('/opt/brave-origin-bin/brave')
            self.assertTrue(browser.running('brave-origin-bin',proc))
            self.assertFalse(browser.running('brave-bin',proc))

    def test_default_catalog_offers_both_without_automatic_browser_install(self):
        data=json.loads((UP/'callas-apps.json').read_text())
        offered={entry['name'] for entry in data['defaults']}
        self.assertTrue({'brave-bin','brave-origin-bin'} <= offered)
        self.assertFalse(any(entry['name'] in ('brave-bin','brave-origin-bin') for entry in data['applications']))

    def test_update_backup_includes_both_browsers_and_additional_profiles(self):
        spec=importlib.util.spec_from_file_location('browser_storage',UP/'callas-storage.py')
        storage=importlib.util.module_from_spec(spec);spec.loader.exec_module(storage)
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp)
            expected=[]
            for profile in ('Brave-Browser','Brave-Origin'):
                for name in ('Default','Profile 1'):
                    path=home/'.config/BraveSoftware'/profile/name/'Preferences'
                    path.parent.mkdir(parents=True);path.write_text('{}');expected.append(path)
            backups=SimpleNamespace(create=lambda category,sources:list(sources))
            with patch.object(storage.pwd,'getpwnam',return_value=SimpleNamespace(pw_dir=str(home))):
                sources=storage.snapshot(backups,'--config','fixture')
            self.assertTrue(set(expected)<=set(sources))
            self.assertIn(home/'.config/brave-origin-flags.conf',sources)

if __name__=='__main__':unittest.main()
