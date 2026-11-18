"""Discord-only persistence independent of KWin's in-memory Remember cache."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]


def load():
    spec=importlib.util.spec_from_file_location('discord_memory',ROOT/'janelas/callas-discord.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


SAVED=dict(schema=1,boot_id='old-boot',window_id='old-window',output='HDMI-A-1',
           rect=dict(x=1920,y=40,width=960,height=1000),output_rect=dict(x=1920,y=0,width=1920,height=1080),
           maxH=False,maxV=False,fullScreen=False)

HARNESS=r'''
var queue=[],writes=[],messages=[];
function signal(){return {callbacks:[],connect:function(f){this.callbacks.push(f);},emit:function(){var a=arguments;this.callbacks.forEach(f=>f.apply(null,a));}};}
function QTimer(){this.timeout=signal();this.active=false;this.start=function(){if(!this.active){this.active=true;queue.push(this);}};this.stop=function(){this.active=false;};}
function flush(){var n=0;while(queue.length && n++<200){var t=queue.shift();if(t.active){t.active=false;t.timeout.emit();}}if(n>=200)throw Error('timer loop');}
function callDBus(s,p,i,m,payload){if(m==='save')writes.push(JSON.parse(payload));else messages.push(m);}
function print(s){messages.push(s);}
var outputs=[{name:'DP-3',geometry:{x:0,y:0,width:1920,height:1080}},{name:'HDMI-A-1',geometry:{x:1920,y:0,width:1920,height:1080}}];
function makeWindow(app,id){return {normalWindow:true,transient:false,splash:false,resourceClass:app,windowRole:'',internalId:id,output:outputs[0],
 frameGeometry:{x:20,y:10,width:800,height:700},maximizeMode:0,fullScreen:false,
 frameGeometryChanged:signal(),outputChanged:signal(),fullScreenChanged:signal(),maximizedChanged:signal(),windowClassChanged:signal(),
 interactiveMoveResizeStarted:signal(),interactiveMoveResizeFinished:signal(),
 setMaximize:function(h,v){this.maximizeMode=(h?2:0)|(v?1:0);}};}
var discord=makeWindow('discord','new-window'),spotify=makeWindow('spotify','spotify-window');
var workspace={stackingOrder:[discord,spotify],screenOrder:outputs,windowAdded:signal(),windowRemoved:signal(),screensChanged:signal(),
 sendClientToScreen:function(w,o){w.output=o;}};
'''


class DiscordMemoryTests(unittest.TestCase):
    def engine(self, saved=None, setup=''):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        from PySide6.QtQml import QJSEngine
        self.app=QApplication.instance() or QApplication([])
        engine=QJSEngine();engine.evaluate(HARNESS+setup)
        result=engine.evaluate(load().memory_script(saved,'current-boot'))
        self.assertFalse(result.isError(),result.toString())
        result=engine.evaluate('flush()');self.assertFalse(result.isError(),result.toString())
        return engine

    def test_restore_only_discord_to_saved_connector_and_geometry(self):
        e=self.engine(SAVED)
        self.assertEqual(e.evaluate('discord.output.name').toString(),'HDMI-A-1')
        self.assertEqual(json.loads(e.evaluate('JSON.stringify(discord.frameGeometry)').toString()),SAVED['rect'])
        self.assertEqual(e.evaluate('spotify.output.name').toString(),'DP-3')
        self.assertEqual(e.evaluate('spotify.frameGeometry.x').toInt(),20)

    def test_maximized_and_fullscreen_restore_without_overwriting_normal_size(self):
        for state in (dict(SAVED,maxH=True,maxV=True),dict(SAVED,fullScreen=True)):
            e=self.engine(state)
            self.assertEqual(e.evaluate('discord.fullScreen').toBool(),state['fullScreen'])
            self.assertEqual(e.evaluate('discord.maximizeMode').toInt(),(2 if state['maxH'] else 0)|(1 if state['maxV'] else 0))
            self.assertEqual(json.loads(e.evaluate('JSON.stringify(writes[writes.length-1].rect)').toString()),SAVED['rect'])

    def test_partial_maximization_keeps_changes_on_the_unmaximized_axis(self):
        e=self.engine(SAVED)
        e.evaluate('discord.setMaximize(true,false);discord.frameGeometry={x:1920,y:80,width:1920,height:700};discord.frameGeometryChanged.emit();flush();')
        row=json.loads(e.evaluate('JSON.stringify(writes[writes.length-1])').toString())
        self.assertEqual(row['rect']['width'],960)
        self.assertEqual(row['rect']['height'],700)

    def test_restart_only_observer_preserves_normal_geometry_of_maximized_or_fullscreen_window(self):
        for flags,setup in ((dict(maxH=True,maxV=True), 'discord.maximizeMode=3;'),
                            (dict(fullScreen=True), 'discord.fullScreen=true;')):
            state=dict(SAVED,boot_id='current-boot',window_id='new-window',**flags)
            e=self.engine(state,setup+"discord.output=outputs[1];discord.frameGeometry={x:1920,y:0,width:1920,height:1080};")
            self.assertEqual(json.loads(e.evaluate('JSON.stringify(writes[writes.length-1].rect)').toString()),SAVED['rect'])

    def test_move_finished_persists_new_choice_and_removed_window_keeps_state(self):
        e=self.engine(SAVED)
        e.evaluate("discord.interactiveMoveResizeStarted.emit();discord.output=outputs[0];discord.frameGeometry={x:10,y:30,width:900,height:700};discord.interactiveMoveResizeFinished.emit();flush();workspace.windowRemoved.emit(discord);")
        row=json.loads(e.evaluate('JSON.stringify(writes[writes.length-1])').toString())
        self.assertEqual(row['output'],'DP-3');self.assertEqual(row['rect']['width'],900)

    def test_reopening_in_same_session_uses_latest_choice_not_service_start_snapshot(self):
        e=self.engine(SAVED)
        e.evaluate("discord.interactiveMoveResizeStarted.emit();discord.output=outputs[0];discord.frameGeometry={x:10,y:30,width:900,height:700};discord.interactiveMoveResizeFinished.emit();flush();workspace.stackingOrder=[spotify];workspace.windowRemoved.emit(discord);discord=makeWindow('discord','reopened-window');workspace.stackingOrder.push(discord);workspace.windowAdded.emit(discord);flush();")
        self.assertEqual(e.evaluate('discord.frameGeometry.x').toInt(),10)
        self.assertEqual(e.evaluate('discord.frameGeometry.width').toInt(),900)

    def test_close_captures_latest_state_without_waiting_for_debounce(self):
        e=self.engine(SAVED)
        e.evaluate('discord.fullScreen=true;discord.fullScreenChanged.emit();workspace.stackingOrder=[spotify];workspace.windowRemoved.emit(discord);')
        self.assertTrue(e.evaluate('writes[writes.length-1].fullScreen').toBool())

    def test_missing_connector_does_not_overwrite_preferred_state(self):
        e=self.engine(SAVED,"outputs.pop();")
        self.assertEqual(e.evaluate('writes.length').toInt(),0)
        self.assertEqual(e.evaluate('discord.output.name').toString(),'DP-3')

    def test_monitor_that_becomes_ready_after_login_restores_saved_placement(self):
        e=self.engine(SAVED,"outputs.pop();")
        e.evaluate("outputs.push({name:'HDMI-A-1',geometry:{x:1920,y:0,width:1920,height:1080}});workspace.screensChanged.emit();flush();")
        self.assertEqual(e.evaluate('discord.output.name').toString(),'HDMI-A-1')
        self.assertEqual(e.evaluate('discord.frameGeometry.width').toInt(),960)

    def test_monitor_disconnect_does_not_learn_automatic_fallback_as_user_choice(self):
        e=self.engine(SAVED)
        e.evaluate("outputs.pop();discord.output=outputs[0];discord.outputChanged.emit();workspace.screensChanged.emit();flush();")
        self.assertEqual(e.evaluate('writes[writes.length-1].output').toString(),'HDMI-A-1')

    def test_user_can_choose_available_monitor_while_saved_monitor_is_absent(self):
        e=self.engine(SAVED,"outputs.pop();")
        e.evaluate('discord.interactiveMoveResizeStarted.emit();discord.frameGeometry={x:10,y:20,width:900,height:700};discord.interactiveMoveResizeFinished.emit();flush();')
        self.assertEqual(e.evaluate('writes[writes.length-1].output').toString(),'DP-3')

    def test_splash_and_popouts_do_not_override_main_window_memory(self):
        for setup in ('discord.splash=true;','discord.transient=true;',"discord.windowRole='popout';"):
            e=self.engine(SAVED,setup);self.assertEqual(e.evaluate('writes.length').toInt(),0)

    def test_private_atomic_state_reloads_after_process_restart_and_rejects_invalid_payload(self):
        helper=load()
        with tempfile.TemporaryDirectory() as temp,patch.object(helper,'STATE',Path(temp)/'discord-window.json'):
            helper.save_state(SAVED);self.assertEqual(helper.read_state(),SAVED)
            self.assertEqual(helper.STATE.stat().st_mode&0o777,0o600)
            with self.assertRaises(ValueError):helper.save_state(dict(SAVED,rect=dict(x=0,y=0,width=-1,height=500)))
            self.assertEqual(helper.read_state(),SAVED)

    def test_initial_migration_uses_learned_kwin_rule_before_wrong_startup_geometry(self):
        helper=load()
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'kwinrulesrc'
            path.write_text('[General]\nOrder=managed\n[managed]\nDescription=Callas OS: lembrar discord\nwmclass=discord\nposition=1920,40\nsize=960,1000\nscreen=1\npositionrule=4\nsizerule=4\nscreenrule=4\nmaximizehoriz=true\nmaximizevert=true\n')
            legacy=helper.legacy_rule(path)
            self.assertEqual(legacy['screen'],1)
            self.assertEqual(legacy['rect'],SAVED['rect'])
            self.assertTrue(legacy['maxH'])


if __name__=='__main__':unittest.main()
