"""Steam launch-dialog routing with the real JS and mocked KWin objects."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch,MagicMock

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('steamwindows',ROOT/'janelas/callas-janelas.py')
win=importlib.util.module_from_spec(spec);spec.loader.exec_module(win)

class SteamDialogTests(unittest.TestCase):
    def test_loader_selects_two_string_signature_when_introspection_picks_one(self):
        # Qt exports both loadScript(s) and loadScript(ss). dbus-python's
        # introspection cache can select s; an explicit signature bypasses it.
        with tempfile.TemporaryDirectory() as temp:
            scripting = MagicMock()
            scripting.isScriptLoaded.return_value = False
            def load(path, name, **kwargs):
                if kwargs.get('signature', 's') != 'ss':
                    raise TypeError('Fewer items found in D-Bus signature than in Python arguments')
                self.assertTrue(Path(path).is_file())
                self.assertEqual(name, 'callas-steam-launch-dialogs')
                return 7
            scripting.loadScript.side_effect = load
            script = MagicMock()
            fake = types.SimpleNamespace(Interface=lambda obj, interface:
                scripting if interface == 'org.kde.kwin.Scripting' else script)
            with patch.object(win, 'STATE', Path(temp)), patch.object(win, 'bus', return_value=MagicMock()), patch.dict(sys.modules, {'dbus': fake}), patch.object(win.subprocess, 'run', return_value=types.SimpleNamespace(returncode=1, stdout='')):
                win.start_steam_dialogs()
            script.run.assert_called_once()

    def run_js(self,scenario,preferred='DP-3'):
        if not shutil.which('node'):self.skipTest('node unavailable')
        harness='''const moves=[],diagnostics=[];
function signal(){return {listeners:[],connect(cb){this.listeners.push(cb)},emit(...args){this.listeners.forEach(cb=>cb(...args))}}}
const primary={name:'DP-3'},secondary={name:'HDMI-A-1'};
function window(extra={}){return Object.assign({resourceClass:'steam',windowRole:'',caption:'Steam',fullScreen:false,output:secondary,windowClassChanged:signal(),windowRoleChanged:signal(),captionChanged:signal(),outputChanged:signal()},extra)}
const workspace={screenOrder:[primary,secondary],windowAdded:signal(),stackingOrder:[],sendClientToScreen(w,o){moves.push(w);w.output=o;w.outputChanged.emit()}};
const print=(message)=>diagnostics.push(message);
'''+scenario.split('// LOAD')[0]+'\n'+win.steam_dialog_script(preferred)+'\n'+scenario.split('// LOAD')[1]
        result=subprocess.run(['node','-e',harness],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
    def test_existing_portuguese_launch_popup_is_routed_and_main_windows_are_preserved(self):
        self.run_js('''const popup=window({caption:'Iniciando o jogo'}),library=window(),game=window({resourceClass:'steam_app_2183900',caption:'Launching game'}),discord=window({resourceClass:'discord',caption:'Iniciando o jogo'});
workspace.stackingOrder=[popup,library,game,discord];
// LOAD
if(moves.length!==1||moves[0]!==popup||popup.output!==primary)throw Error('wrong window routed');
if(library.output!==secondary||game.output!==secondary||discord.output!==secondary)throw Error('other windows changed');
''')
    def test_late_identity_caption_and_steam_reposition_are_handled_without_stealing_focus(self):
        self.run_js('''// LOAD
const popup=window({resourceClass:'',caption:''});workspace.windowAdded.emit(popup);
if(moves.length)throw Error('unidentified window moves');
popup.resourceClass='steamwebhelper';popup.windowClassChanged.emit();
popup.caption='Launching Warhammer';popup.captionChanged.emit();
if(moves.length!==1||popup.output!==primary)throw Error('late caption ignored');
popup.output=secondary;popup.outputChanged.emit();
if(moves.length!==2||popup.output!==primary)throw Error('late Steam placement ignored');
workspace.windowAdded.emit(popup);popup.captionChanged.emit();
if(moves.length!==2)throw Error('duplicate handler or unnecessary movement');
''')
    def test_launch_role_with_game_id_and_primary_changes(self):
        self.run_js('''// LOAD
const popup=window({windowRole:'GameLaunchDialog_2183900',caption:'Steam',output:primary});workspace.windowAdded.emit(popup);
if(moves.length!==1||popup.output!==secondary)throw Error('selected primary ignored');
''',preferred='HDMI-A-1')
    def test_unplugged_primary_falls_back_and_unknown_windows_are_not_guessed(self):
        self.run_js('''// LOAD
const popup=window({caption:'Preparing to launch'});workspace.windowAdded.emit(popup);
if(popup.output!==primary)throw Error('active-output fallback');
const unknown=window({caption:'Steam',windowRole:'browser-window'}),login=window({caption:'Iniciando sessão'}),fullscreen=window({caption:'Launching game',fullScreen:true});workspace.windowAdded.emit(unknown);workspace.windowAdded.emit(login);workspace.windowAdded.emit(fullscreen);
if(moves.length!==1)throw Error('unrelated Steam window moves');
if(!diagnostics.some(line=>line.includes('browser-window')))throw Error('missing identity diagnostic');
''',preferred='unplugged-output')
    def test_older_kwin_window_list_and_screens_api_still_work(self):
        self.run_js('''const popup=window({caption:'Steam - Iniciando o jogo'});workspace.screens=workspace.screenOrder;delete workspace.screenOrder;workspace.windowList=()=>[popup];
// LOAD
if(moves.length!==1||popup.output!==primary)throw Error('legacy API not supported');
''')
    def test_connector_name_is_data_and_cannot_inject_code(self):
        self.run_js('''// LOAD
const popup=window({caption:'Launching game'});workspace.windowAdded.emit(popup);
if(popup.output!==primary)throw Error('escaped connector invalidated script');
''',preferred='DP-3"; throw Error("injected"); //')
    def test_loader_reuses_live_script_but_reloads_after_choice_or_kwin_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            scripting=MagicMock();scripting.isScriptLoaded.return_value=False;scripting.loadScript.return_value=7;scripting.unloadScript.return_value=True
            script=MagicMock();session=MagicMock()
            fake=types.SimpleNamespace(Interface=lambda obj,interface:scripting if interface=='org.kde.kwin.Scripting' else script)
            with patch.object(win,'STATE',root),patch.object(win,'bus',return_value=session),patch.dict(sys.modules,{'dbus':fake}),patch.object(win.subprocess,'run',return_value=types.SimpleNamespace(returncode=1,stdout='')):
                win.start_steam_dialogs();script.run.assert_called_once()
                scripting.isScriptLoaded.return_value=True
                win.start_steam_dialogs();self.assertEqual(script.run.call_count,1)
                (root/'monitors.json').write_text(json.dumps({'primary':'HDMI-A-1'}))
                win.start_steam_dialogs();self.assertEqual(script.run.call_count,2)
                scripting.unloadScript.assert_called_once_with('callas-steam-launch-dialogs')
                scripting.isScriptLoaded.return_value=False
                win.start_steam_dialogs();self.assertEqual(script.run.call_count,3)
    def test_load_failure_is_reported_and_shared_paths_cover_clean_and_existing_systems(self):
        with tempfile.TemporaryDirectory() as temp:
            scripting=MagicMock();scripting.isScriptLoaded.return_value=False;scripting.loadScript.return_value=-1
            fake=types.SimpleNamespace(Interface=lambda *args:scripting)
            with patch.object(win,'STATE',Path(temp)),patch.object(win,'bus',return_value=MagicMock()),patch.dict(sys.modules,{'dbus':fake}):
                with self.assertRaises(RuntimeError):win.start_steam_dialogs()
        installer=(ROOT.parent/'instalar-arch.sh').read_text()
        updater=(ROOT/'atualizador/callas-config-update.sh').read_text()
        release=(ROOT/'atualizador/callas-release.py').read_text()
        monitor=(ROOT/'monitores/callas-monitores.py').read_text()
        self.assertIn('"$libexec/callas-janelas" --install-system',installer)
        self.assertIn('callas-janelas.py',updater)
        self.assertIn('programas-callas-os/janelas/callas-janelas.py',release)
        self.assertIn("'--steam-dialogs'",monitor)
        source=(ROOT/'janelas/callas-janelas.py').read_text()
        self.assertLess(source.index('        start_steam_dialogs()\n'),source.index('        remember_windows()\n'))

if __name__=='__main__':unittest.main()
