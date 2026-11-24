"""Clock package and Plasma scripts in temporary homes / a real JS engine."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'atualizador/callas-widget.py'
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QJSEngine
APP = QApplication.instance() or QApplication([])


def load():
    spec = importlib.util.spec_from_file_location('clock_widget', SOURCE)
    helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
    return helper


HARNESS = r'''
var logs=[], removed=[], created=[], pending=[], live=[], failCreate=false, failCopy=false, alwaysFailCreate=false;
function print(s) { logs.push(s); }
function currentActivity() { return 'current'; }
function screenForConnector(name) { return {'DP-1':0,'HDMI-1':1,'DP-3':2}[name] ?? -1; }
function widget(id) {
 return {id:id,type:'com.github.prayag2.modernclock',currentConfigGroup:[],
  globalShortcut:'Meta+Alt+C',locked:true,userBackgroundHints:'NoBackground',
  data:{'Appearance':{day_font_size:'50',date_font_color:'#abcdef'},'':{custom:'keep'}},
  get configKeys(){ return Object.keys(this.data[this.currentConfigGroup.join('/')] || {}); },
  get configGroups(){ return this.currentConfigGroup.length ? [] : ['Appearance']; },
  readConfig:function(k){ return this.data[this.currentConfigGroup.join('/')][k]; },
  writeConfig:function(k,v){ if(failCopy){failCopy=false;throw new Error('copy failed');} var p=this.currentConfigGroup.join('/');if(!this.data[p])this.data[p]={};this.data[p][k]=v; },
  geometry:{x:48,y:16,width:656,height:176},
  remove:function(){removed.push(this.id);pending.push(this.id);}
 };
}
var old=widget(27); live.push({screen:1,widget:old});
function flushRemoved(){ live=live.filter(function(a){return pending.indexOf(a.widget.id)<0;});pending=[]; }
var ds=[0,1,2].map(function(i){ return {id:10+i,screen:i,activity:'current',
 widgets:function(type){return live.filter(function(a){return a.screen===i && (!type || a.widget.type===type);}).map(function(a){return a.widget;});},
 widgetById:function(id){return this.widgets().find(function(w){return w.id===id;});},
 addWidget:function(type,x,y,w,h){
  if(failCreate || alwaysFailCreate){failCreate=false;throw new Error('creation failed');}
  // Real layout reserves the old rectangle until deleteLater runs between calls.
  if(this.widgets().some(function(a){var g=a.geometry;return x<g.x+g.width && x+w>g.x && y<g.y+g.height && y+h>g.y;})) x+=w+32;
  var a=widget(100+created.length);a.data={};a.globalShortcut='';a.locked=false;a.userBackgroundHints='StandardBackground';a.geometry={x:x,y:y,width:w,height:h};
  var item={screen:i,widget:a};created.push(item);live.push(item);return a;
 }};});
function desktopsForActivity(a){return ds;}
function desktops(){return ds;}
function desktopForScreen(s){return ds[s];}
function desktopById(id){return ds.find(function(d){return d.id===id;});}
'''


class WidgetTests(unittest.TestCase):
    def test_clean_install_prepares_package_once_and_first_login_preserves_retries(self):
        helper = load()
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {
                'XDG_DATA_HOME':temp+'/data', 'XDG_CONFIG_HOME':temp+'/config', 'XDG_STATE_HOME':temp+'/state'}), \
                patch.object(helper, 'install_package') as package:
            helper.prepare_first_login(); helper.prepare_first_login()
            pending=Path(temp)/'state/callas-os/clock-first-login.pending'
            autostart=Path(temp)/'config/autostart/callas-clock.desktop'
            self.assertTrue(pending.is_file()); self.assertIn('--first-login',autostart.read_text())
            with patch.object(helper, 'install', side_effect=RuntimeError('Plasma unavailable')):
                with self.assertRaises(RuntimeError): helper.first_login()
            self.assertTrue(pending.is_file()); self.assertTrue(autostart.is_file())
            with patch.object(helper, 'install') as install:
                helper.first_login(); helper.first_login(); install.assert_called_once_with()
            self.assertFalse(pending.exists()); self.assertFalse(autostart.exists())
            helper.prepare_first_login(); self.assertFalse(pending.exists())

    def test_verified_stage_contains_payload_and_helper_and_installer_uses_shared_flow(self):
        spec=importlib.util.spec_from_file_location('clock_release',ROOT/'atualizador/callas-release.py')
        release=importlib.util.module_from_spec(spec); spec.loader.exec_module(release)
        self.assertIn('programas-callas-os/relogio/relogio-moderno.plasmoid',release.FILES)
        self.assertIn('programas-callas-os/atualizador/callas-widget.py',release.FILES)

    def test_only_clean_install_arms_clock_when_running_real_provisioning_block(self):
        import subprocess
        source=(ROOT/'atualizador/callas-security.sh').read_text()
        block=source.split('# CALLAS_CLOCK_CLEAN_BEGIN\n')[1].split('# CALLAS_CLOCK_CLEAN_END')[0]
        for mode in ('--installation','--config-update','--helpers-only'):
            code='set -eu\nusuario=fixture\nstage=/verified\npython() { printf "%s\\n" "$*"; }\n'+block
            result=subprocess.run(['bash','-c',code,'fixture','fixture',mode],text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual('--prepare-clean fixture' in result.stdout,mode=='--installation')

    def test_update_repairs_only_existing_clock_as_user_without_installing_it(self):
        import subprocess
        source=(ROOT/'atualizador/callas-security.sh').read_text()
        block=source.split('# CALLAS_CLOCK_APPEARANCE_BEGIN\n')[1].split('# CALLAS_CLOCK_APPEARANCE_END')[0]
        for mode in ('--installation','--config-update','--helpers-only'):
            code='set -eu\nusuario=fixture\nid(){ echo 1000; }\ngetent(){ echo fixture:x:1000:1000::/home/fixture:/bin/bash; }\nrunuser(){ printf "%s\\n" "$@"; }\n'+block
            result=subprocess.run(['bash','-c',code,'fixture','fixture',mode],text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual('--migrate-appearance' in result.stdout,mode=='--config-update')
            self.assertNotIn('--install\n',result.stdout)

    def test_package_installs_under_internal_id_and_preserves_existing_files(self):
        helper = load()
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'XDG_DATA_HOME': temp}):
            target = helper.install_package(ROOT / 'relogio/relogio-moderno.plasmoid')
            self.assertEqual(target.name, 'com.github.prayag2.modernclock')
            self.assertEqual(json.loads((target / 'metadata.json').read_text())['KPlugin']['Id'], target.name)
            metadata = (target / 'metadata.json').read_bytes()
            (target / 'personal').write_text('preserve')
            helper.install_package(ROOT / 'relogio/relogio-moderno.plasmoid')
            self.assertEqual((target / 'personal').read_text(), 'preserve')
            self.assertEqual((target / 'metadata.json').read_bytes(), metadata)
            self.assertTrue(helper.package_installed())

    def test_invalid_archive_is_rejected_before_writing_any_files(self):
        helper = load()
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'XDG_DATA_HOME': temp + '/data'}):
            archive = Path(temp) / 'bad.zip'
            with zipfile.ZipFile(archive, 'w') as stream:
                stream.writestr('clock/../../escape', 'bad')
            with self.assertRaises(ValueError): helper.install_package(archive)
            self.assertFalse((Path(temp) / 'data').exists())

    def run_script(self, initial=False, corner='bottom-right', setup='', connector='DP-3', retry=False):
        engine=QJSEngine(); result=engine.evaluate(HARNESS+setup)
        self.assertFalse(result.isError(),result.toString())
        helper=load()
        def evaluate(script):
            result=engine.evaluate(script)
            engine.evaluate('flushRemoved()')
            if result.isError(): raise RuntimeError(result.toString())
            return engine.evaluate('logs[logs.length-1]').toString()
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ,{'XDG_STATE_HOME':temp}), \
                patch.object(helper,'screens',return_value=[dict(name=connector,area=dict(x=0,y=0,width=1920,height=1080))]), \
                patch.object(helper,'package_installed',return_value=True), patch.object(helper,'evaluate',side_effect=evaluate), \
                patch.object(helper,'leave_edit_mode'), patch.object(helper.time,'sleep'):
            error=None
            try: helper.move(connector,corner,initial=initial)
            except Exception as exc: error=exc
            if error and retry:
                engine.evaluate('alwaysFailCreate=false;failCreate=false;failCopy=false;')
                error=None
                try: helper.move(connector,corner,initial=initial)
                except Exception as exc: error=exc
            engine.globalObject().setProperty('recoveryPresent',(Path(temp)/'callas-os/widget-recovery.json').exists())
        return engine,error

    def test_leaving_edit_mode_before_geometry_snapshot_avoids_scaled_scene_coordinates(self):
        helper = load()
        interface = Mock()
        interface.return_value.Get.return_value = True
        dbus = SimpleNamespace(Interface=interface, Boolean=bool)
        with patch.dict(sys.modules, {'dbus': dbus}), patch.object(helper, 'plasma_object') as plasma, \
                patch.object(helper.time, 'sleep'):
            helper.leave_edit_mode()
        interface.assert_called_once_with(plasma.return_value, 'org.freedesktop.DBus.Properties')
        interface.return_value.Set.assert_called_once_with('org.kde.PlasmaShell', 'editMode', False)

    def test_snapshot_accepts_literal_error_word_inside_user_configuration(self):
        helper = load()
        interface = Mock()
        interface.return_value.evaluateScript.return_value = 'CALLAS_WIDGET_OK:{"format":"Error"}'
        dbus = SimpleNamespace(Interface=interface)
        with patch.dict(sys.modules, {'dbus': dbus}), patch.object(helper, 'plasma_object'):
            self.assertEqual(helper.result('read-only fixture'), {'format': 'Error'})

    def test_initial_placement_preserves_existing_widget_without_creating_or_moving(self):
        engine, result = self.run_script(initial=True)
        self.assertIsNone(result, str(result))
        self.assertEqual(engine.evaluate('created.length').toInt(), 0)
        self.assertEqual(engine.evaluate('removed.length').toInt(), 0)

    def test_initial_placement_adds_only_one_widget_and_keeps_free_geometry(self):
        engine, result = self.run_script(initial=True, corner='top-left',
            setup='live=[];')
        self.assertIsNone(result, str(result))
        self.assertEqual(engine.evaluate('created.length').toInt(), 1)
        self.assertEqual(engine.evaluate('created[0].widget.data.Appearance.day_font_size').toInt(), 50)
        # No anchoring configuration/binding is written: native dragging stays free.
        self.assertEqual(engine.evaluate('created[0].widget.geometry.x').toInt(), 24)
        self.assertEqual(engine.evaluate('created[0].widget.userBackgroundHints').toString(), 'NoBackground')

    def test_implicit_plasma_background_is_not_persisted_as_user_choice_when_moving(self):
        engine,error=self.run_script(setup="old.userBackgroundHints='StandardBackground';")
        self.assertIsNone(error,str(error))
        self.assertEqual(engine.evaluate('created[0].widget.userBackgroundHints').toString(),'NoBackground')

    def test_explicit_user_background_choice_is_preserved_when_moving(self):
        engine,error=self.run_script(setup="old.userBackgroundHints='StandardBackground';old.data[''].UserBackgroundHints='StandardBackground';")
        self.assertIsNone(error,str(error))
        self.assertEqual(engine.evaluate('created[0].widget.userBackgroundHints').toString(),'StandardBackground')

    def test_legacy_recovery_record_does_not_turn_an_implicit_background_into_a_preference(self):
        engine=QJSEngine();engine.evaluate(HARNESS+'live=[];')
        geometry=dict(x=24,y=24,width=656,height=176)
        plan=dict(activity='current',target=12,connector='DP-3',geometry=geometry,
            previous=dict(id=27,desktop=11,geometry=geometry,hints='StandardBackground',shortcut='',locked=False,
                          config=dict(path=[],values={},children=[])))
        out=engine.evaluate(load().transaction_script(plan,'create'))
        self.assertFalse(out.isError(),out.toString())
        self.assertEqual(engine.evaluate('created[0].widget.userBackgroundHints').toString(),'NoBackground')

    def test_background_repair_keeps_existing_instance_position_and_other_widgets(self):
        engine=QJSEngine()
        engine.evaluate(HARNESS+"old.userBackgroundHints='StandardBackground';var other=widget(50);other.type='org.kde.plasma.notes';other.userBackgroundHints='StandardBackground';live.push({screen:1,widget:other});")
        helper=load()
        out=engine.evaluate(helper.appearance_script(apply=True))
        self.assertFalse(out.isError(),out.toString())
        self.assertEqual(engine.evaluate('old.userBackgroundHints').toString(),'NoBackground')
        self.assertEqual(engine.evaluate('old.id').toInt(),27)
        self.assertEqual(engine.evaluate('JSON.stringify(old.geometry)').toString(),'{"x":48,"y":16,"width":656,"height":176}')
        self.assertEqual(engine.evaluate('old.data.Appearance.day_font_size').toString(),'50')
        self.assertEqual(engine.evaluate('other.userBackgroundHints').toString(),'StandardBackground')
        self.assertEqual(engine.evaluate('created.length+removed.length').toInt(),0)

    def test_background_migration_is_optional_once_and_retries_after_missing_session(self):
        helper=load()
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ,{'XDG_STATE_HOME':temp+'/state','XDG_CONFIG_HOME':temp+'/config'}), \
                patch.object(helper,'package_installed',return_value=False), patch.object(helper,'result') as result:
            helper.repair_appearance(migrate=True);result.assert_not_called()
            self.assertFalse((Path(temp)/'state').exists())
            with patch.object(helper,'package_installed',return_value=True):
                result.side_effect=RuntimeError('no session')
                helper.repair_appearance(migrate=True)
                autostart=Path(temp)/'config/autostart/callas-clock-appearance.desktop'
                self.assertTrue(autostart.exists())
                result.side_effect=None;result.return_value=[dict(id=27,hints='NoBackground')]
                helper.repair_appearance(migrate=True)
                self.assertFalse(autostart.exists())
                result.reset_mock();helper.repair_appearance(migrate=True);result.assert_not_called()

    def test_multiple_existing_clocks_are_preserved_instead_of_destroying_arbitrary_instance(self):
        engine, result = self.run_script(setup='ds[1].widgets=function(){ return [old,widget(28)]; };')
        self.assertIsNotNone(result); self.assertIn('vários relógios', str(result))
        self.assertEqual(engine.evaluate('created.length').toInt(), 0)
        self.assertEqual(engine.evaluate('removed.length').toInt(), 0)

    def test_invalid_corner_and_unsafe_package_destination_are_rejected(self):
        helper = load()
        with self.assertRaises(ValueError):
            helper.position_script('DP-1','invalid',dict(x=0,y=0,width=1920,height=1080))
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'XDG_DATA_HOME':temp+'/link'}):
            root=Path(temp); (root/'real').mkdir(); (root/'link').symlink_to(root/'real',target_is_directory=True)
            with self.assertRaises(ValueError): helper.install_package(ROOT/'relogio/relogio-moderno.plasmoid')
            self.assertEqual(list((root/'real').iterdir()),[])

    def test_move_third_screen_preserves_appearance_and_removes_old_only_after_creation(self):
        engine, result = self.run_script()
        self.assertIsNone(result, str(result))
        self.assertEqual(engine.evaluate('created[0].screen').toInt(), 2)
        self.assertEqual(engine.evaluate('JSON.stringify(created[0].widget.geometry)').toString(),
                         '{"x":1240,"y":880,"width":656,"height":176}')
        self.assertEqual(engine.evaluate('created[0].widget.data.Appearance.day_font_size').toString(), '50')
        self.assertEqual(engine.evaluate('created[0].widget.data[""].custom').toString(), 'keep')
        self.assertEqual(engine.evaluate('JSON.stringify(removed)').toString(), '[27]')

    def test_each_corner_uses_local_logical_coordinates(self):
        for corner, point in [('top-left',(24,24)),('top-right',(1240,24)),
                              ('bottom-left',(24,880)),('bottom-right',(1240,880))]:
            engine, result = self.run_script(corner=corner)
            self.assertIsNone(result, str(result))
            self.assertEqual((engine.evaluate('created[0].widget.geometry.x').toInt(),
                              engine.evaluate('created[0].widget.geometry.y').toInt()), point)

    def test_repeating_same_corner_waits_for_old_layout_slot_to_be_released(self):
        engine,error=self.run_script(connector='HDMI-1',corner='top-left')
        self.assertIsNone(error,str(error))
        self.assertEqual(engine.evaluate('created[0].widget.geometry.x').toInt(),24)
        self.assertEqual(engine.evaluate('created[0].widget.geometry.y').toInt(),24)

    def test_global_shortcut_and_lock_are_preserved_when_moving(self):
        engine,error=self.run_script()
        self.assertIsNone(error,str(error))
        self.assertEqual(engine.evaluate('created[0].widget.globalShortcut').toString(),'Meta+Alt+C')
        self.assertTrue(engine.evaluate('created[0].widget.locked').toBool())

    def test_unrecoverable_session_failure_keeps_persistent_snapshot(self):
        engine,error=self.run_script(setup='alwaysFailCreate=true;')
        self.assertIsNotNone(error)
        self.assertTrue(engine.evaluate('recoveryPresent').toBool())

    def test_retry_recovers_persisted_configuration_before_new_move(self):
        engine,error=self.run_script(setup='alwaysFailCreate=true;',retry=True)
        self.assertIsNone(error,str(error))
        self.assertFalse(engine.evaluate('recoveryPresent').toBool())
        self.assertEqual(engine.evaluate('live.length').toInt(),1)
        self.assertEqual(engine.evaluate('live[0].screen').toInt(),2)
        self.assertEqual(engine.evaluate('live[0].widget.globalShortcut').toString(),'Meta+Alt+C')

    def test_occupied_destination_rolls_back_without_moving_other_widgets(self):
        setup="var blocker=widget(99);blocker.type='org.kde.plasma.notes';blocker.geometry={x:1240,y:880,width:656,height:176};live.push({screen:2,widget:blocker});"
        engine,error=self.run_script(setup=setup)
        self.assertIsNotNone(error); self.assertIn('restaurado',str(error))
        self.assertFalse(engine.evaluate('recoveryPresent').toBool())
        self.assertEqual(engine.evaluate("live.filter(function(a){return a.widget.type==='com.github.prayag2.modernclock';})[0].screen").toInt(),1)
        self.assertEqual(engine.evaluate('blocker.geometry.x').toInt(),1240)
        self.assertNotIn(99,json.loads(engine.evaluate('JSON.stringify(removed)').toString()))

    def test_failure_creating_or_copying_keeps_original(self):
        for setup in ('failCreate=true;', 'failCopy=true;'):
            engine, result = self.run_script(setup=setup)
            self.assertIsNotNone(result)
            self.assertEqual(engine.evaluate('live.length').toInt(),1)
            self.assertEqual(engine.evaluate('live[0].widget.data.Appearance.day_font_size').toString(),'50')

    def test_disconnected_connector_is_rejected_without_changes(self):
        helper = load()
        with patch.object(helper, 'screens', return_value=[{'name':'DP-1'}]), patch.object(helper, 'evaluate') as evaluate:
            with self.assertRaises(ValueError): helper.move('disconnected', 'top-left')
            evaluate.assert_not_called()

    def test_catalog_is_optional_and_never_in_automatic_update_applications(self):
        data = json.loads((ROOT / 'atualizador/callas-apps.json').read_text())
        rows = [row for row in data['defaults'] if row['source'] == 'plasmoid']
        self.assertEqual([row['name'] for row in rows], ['com.github.prayag2.modernclock'])
        self.assertFalse(any(row['name'] == rows[0]['name'] for row in data['applications']))


if __name__ == '__main__': unittest.main()
