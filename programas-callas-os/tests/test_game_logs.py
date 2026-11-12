"""Offline diagnostics regression tests: events, isolation, quotas and KDE JS."""
import configparser
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch, MagicMock

UP = Path(__file__).resolve().parents[1]/'atualizador'
spec = importlib.util.spec_from_file_location('game_logs', UP/'callas-game-logs.py')
games = importlib.util.module_from_spec(spec); spec.loader.exec_module(games)

class GameLogTests(unittest.TestCase):
    def core(self, uid=1000):
        return {'MESSAGE_ID':games.CORE_ID, 'COREDUMP_UID':str(uid), 'COREDUMP_PID':'5162',
                'COREDUMP_CGROUP':'/user.slice/user-1000.slice/app-steam-app2183900-5162.scope',
                'COREDUMP_ENVIRON':'TOKEN=do-not-export\nSteamAppId=2183900',
                'COREDUMP_COMM':'Retail.exe', 'COREDUMP_SIGNAL':'11', '__CURSOR':'cursor1'}

    def hang(self, uid=1000):
        return {'_UID':str(uid), 'SYSLOG_IDENTIFIER':'callas-game-event', '__CURSOR':'cursor2',
                'MESSAGE':json.dumps({'pid':5162, 'reason':'KDE: jogo não respondendo',
                'class':'steam_app_2183900', 'title':'Space Marine 2',
                'game':{'appid':'2183900','name':'Steam-2183900'}})}

    def test_environment_extracts_identity_without_secrets_and_rejects_shell_fragments(self):
        env = games.selected_env(b'SteamAppId=2183900\0TOKEN=secret\0PASSWORD=secret\0HOME=/bad\0')
        self.assertEqual(env, {'SteamAppId':'2183900'})
        self.assertEqual(games.identity(env)['appid'], '2183900')
        self.assertIsNone(games.identity({'SteamAppId':'$(touch /bad)'}))
        self.assertIsNone(games.identity({'SteamAppId':'0'}))
        self.assertEqual(games.identity({'HEROIC_APP_NAME':'My game'})['name'], 'My game')

    def test_only_current_account_game_events_are_selected(self):
        self.assertEqual(games.event_game(self.core(),1000)['appid'],'2183900')
        self.assertIsNone(games.event_game(self.core(1001),1000))
        event=self.core();event.pop('COREDUMP_CGROUP');event['COREDUMP_ENVIRON']='APP=ordinary-editor'
        self.assertIsNone(games.event_game(event,1000))
        self.assertIsNone(games.event_game(self.hang(1001),1000))
        self.assertIsNone(games.event_game({'_UID':'1000','SYSLOG_IDENTIFIER':'other','MESSAGE':'{}'},1000))
        self.assertIsNone(games.event_game({'_UID':'1000','SYSLOG_IDENTIFIER':'callas-game-event','MESSAGE':'bad-json'},1000))

    def test_kde_event_survives_immediate_force_close_and_deduplicates_related_crashes(self):
        account=types.SimpleNamespace(pw_uid=1000)
        with patch.object(games,'process_game',return_value=None),patch.object(games,'snapshot') as snapshot:
            seen={}
            self.assertTrue(games.handle_event(self.hang(),account,seen))
            self.assertFalse(games.handle_event(self.hang(),account,seen))
            self.assertFalse(games.handle_event(self.core(),account,seen))
            snapshot.assert_called_once()
            self.assertEqual(snapshot.call_args.args[1]['appid'],'2183900')

    def test_coredump_collection_excludes_environment_and_retries_failed_delivery(self):
        event=self.core(); account=types.SimpleNamespace(pw_uid=1000)
        seen={}
        with patch.object(games,'snapshot',side_effect=RuntimeError('failed')):
            with self.assertRaises(RuntimeError):games.handle_event(event,account,seen)
        self.assertEqual(seen,{})
        with patch.object(games,'snapshot') as snapshot:
            self.assertTrue(games.handle_event(event,account,seen))
        self.assertNotIn('TOKEN',snapshot.call_args.args[4])
        self.assertNotIn('do-not-export',snapshot.call_args.args[4])

    def test_proc_ownership_checked_before_environment_or_thread_read(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(games,'PROC',Path(temp)):
            root=Path(temp)/'5162'; root.mkdir(); (root/'environ').write_bytes(b'SteamAppId=2183900\0TOKEN=secret')
            self.assertIsNone(games.process_game(5162,os.getuid()+1,'steam_app_2183900'))
            self.assertEqual(games.process_game(5162,os.getuid())['appid'],'2183900')
            self.assertFalse(games.owned_process('../etc',os.getuid()))

    def test_snapshot_drops_privilege_before_documents_write_and_never_executes_user_paths(self):
        account=types.SimpleNamespace(pw_uid=1000,pw_name='callas',pw_dir='/home/callas')
        with patch.object(games.os,'geteuid',return_value=0),patch.object(games,'owned_process',return_value=False), \
             patch.object(games,'bounded_command',return_value='kernel USB event'),patch.object(games.subprocess,'run') as run:
            games.snapshot(account,{'appid':'2183900','name':'Game'},5162,'manual')
        argv=run.call_args.args[0]
        self.assertEqual(argv[:4],['runuser','-u','callas','--'])
        self.assertEqual(argv[-2:],[games.HELPER,'--receive'])
        self.assertNotIn('shell',run.call_args.kwargs)
        payload=json.loads(run.call_args.kwargs['input'])
        self.assertEqual(payload['kernel'],'kernel USB event')
        self.assertNotIn('environ',payload)

    def test_friendly_names_private_files_collision_safety_and_existing_proton_tail(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp);base=home/'Documentos/Callas OS/Callas OS Logs';base.mkdir(parents=True)
            logs=games.logs_module()
            proton=home/'steam-2183900.log';proton.write_text('Proton diagnostic only')
            payload={'game':{'appid':'2183900','name':'fallback'},'pid':5162,'reason':'KDE: jogo não respondendo','kernel':'USB inserted'}
            with patch.object(games.os,'geteuid',return_value=1000),patch.object(games,'logs_module',return_value=logs), \
                 patch.object(games,'steam_name',return_value='Warhammer: Space Marine 2'),patch.object(games.Path,'home',return_value=home), \
                 patch.object(logs,'prepare',return_value=base),patch.object(logs,'identified',side_effect=lambda x:x), \
                 patch.object(games,'bounded_command',return_value='session event'):
                first=games.receive(payload);second=games.receive(payload)
            self.assertEqual(first.parent,base/'Jogos/Warhammer- Space Marine 2 (2183900)')
            self.assertNotEqual(first,second)
            self.assertRegex(first.name,r'^\d{4}-\d{2}-\d{2}_\d{2}h\d{2}m\d{2}s(?:__parte-\d+)?\.log$')
            self.assertEqual(first.stat().st_mode&0o777,0o600)
            self.assertIn('USB inserted',first.read_text())
            self.assertIn('Proton diagnostic only',first.read_text())
            self.assertIn('Encerrado em:',first.read_text())

    def test_symlink_destination_rejected_and_root_never_writes_documents(self):
        with patch.object(games.os,'geteuid',return_value=0),self.assertRaises(ValueError):games.receive({})
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);outside=root/'outside';outside.mkdir();base=root/'logs';base.mkdir();(base/'Jogos').symlink_to(outside)
            logs=types.SimpleNamespace(prepare=lambda:base)
            with patch.object(games.os,'geteuid',return_value=1000),patch.object(games,'logs_module',return_value=logs),self.assertRaises(ValueError):
                games.receive({'game':{'name':'Game','appid':''}})
            self.assertFalse(list(outside.iterdir()))

    def test_pruning_respects_age_count_total_and_never_follows_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);base=root/'Jogos';base.mkdir();folder=base/'Game';folder.mkdir();outside=root/'outside.log';outside.write_text('keep')
            (base/'linked').symlink_to(root);(folder/'linked.log').symlink_to(outside)
            for i in range(5):
                p=folder/f'{i}.log';p.write_bytes(b'x'*64);os.utime(p,(time_value:=100000+i,time_value))
            with patch.object(games,'policy',return_value=(130,30,3)),patch.object(games.time,'time',return_value=100010):games.prune_games(base)
            self.assertEqual(sorted(p.name for p in folder.glob('*.log') if not p.is_symlink()),['3.log','4.log'])
            self.assertEqual(outside.read_text(),'keep')
            with patch.object(games,'policy',return_value=(130,1,3)),patch.object(games.time,'time',return_value=300000):games.prune_games(base)
            self.assertFalse([p for p in folder.glob('*.log') if not p.is_symlink()])

    def test_policy_is_configurable_and_clamped(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'policy';p.write_text('[Jogos]\nlimit_mib=9999\nretention_days=-1\nfiles_per_game=invalid\n')
            with patch.object(games,'POLICY',p):self.assertEqual(games.policy(),(128*1024**2,1,20))

    def test_kwin_script_observes_hangs_without_moving_or_interacting_with_games(self):
        if not shutil.which('node'):self.skipTest('node unavailable')
        script='''const events=[];
function signal(){return {f:[],connect(cb){this.f.push(cb)},emit(){this.f.forEach(cb=>cb())}}}
function win(){return {pid:5162,resourceClass:'steam_app_2183900',caption:'Space Marine 2',normalWindow:true,transient:false,unresponsive:false,unresponsiveChanged:signal()}}
const a=win(),b=win();b.normalWindow=false;
const workspace={windowAdded:signal(),stackingOrder:[a,b]};
function callDBus(...args){events.push(JSON.parse(args.at(-1)))}
'''+games.kwin_script()+'''
if(events.length)throw Error('normal game reported');
a.unresponsive=true;a.unresponsiveChanged.emit();a.unresponsiveChanged.emit();
b.unresponsive=true;b.unresponsiveChanged.emit();
if(events.length!==1||events[0].pid!==5162)throw Error('wrong hang detection');
const c=win();workspace.windowAdded.f.forEach(cb=>cb(c));c.unresponsive=true;c.unresponsiveChanged.emit();
if(events.length!==2)throw Error('new window ignored');
'''
        result=subprocess.run(['node','-e',script],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        for forbidden in ('sendClientToScreen','frameGeometry','activeWindow','kill','mouse'):
            self.assertNotIn(forbidden,games.kwin_script())

    def test_service_installation_enables_only_target_service_and_preserves_policy(self):
        for chroot in (True,False):
            with self.subTest(chroot=chroot),tempfile.TemporaryDirectory() as temp:
                policy=Path(temp)/'policy';policy.write_text('custom policy')
                written={}
                def write(path,text,mode=0o644):written[str(path)]=text
                def run(argv,**kw):return types.SimpleNamespace(returncode=0 if chroot else 1)
                with patch.object(games.os,'geteuid',return_value=0),patch.object(games,'POLICY',policy), \
                     patch.object(games,'atomic',side_effect=write),patch.object(games.subprocess,'run',side_effect=run) as command:
                    games.install_system()
                self.assertEqual(policy.read_text(),'custom policy')
                self.assertEqual(len(written),3)
                commands=[call.args[0] for call in command.call_args_list]
                expected=['systemctl','--root=/','enable','callas-game-events.service'] if chroot else ['systemctl','restart','callas-game-events.service']
                self.assertIn(expected,commands)
                self.assertIn('NoNewPrivileges=yes',written['/etc/systemd/system/callas-game-events.service'])
                self.assertIn('OnlyShowIn=KDE;',written['/etc/xdg/autostart/callas-game-logs.desktop'])

    def test_system_journal_stream_filters_events_and_persists_only_deduplication_keys(self):
        account=types.SimpleNamespace(pw_uid=1000,pw_name='callas')
        child=MagicMock();child.stdout=io.BytesIO((json.dumps(self.core())+'\n'+json.dumps(self.core(1001))+'\n').encode())
        original_read=Path.read_text
        def read(path,*args,**kwargs):
            if str(path)=='/etc/callas-os/log-user':return 'callas\n'
            return original_read(path,*args,**kwargs)
        with tempfile.TemporaryDirectory() as temp,patch.object(games,'SEEN',Path(temp)/'events'), \
             patch.object(games.os,'geteuid',return_value=0),patch.object(games.pwd,'getpwnam',return_value=account), \
             patch.object(Path,'read_text',read),patch.object(games.subprocess,'Popen',return_value=child) as spawn, \
             patch.object(games,'snapshot') as snapshot:
            with self.assertRaisesRegex(RuntimeError,'journal foi interrompido'):games.watch_system()
            snapshot.assert_called_once()
            ledger=games.SEEN.read_text()
            self.assertNotIn('TOKEN',ledger);self.assertNotIn('do-not-export',ledger)
            self.assertTrue(json.loads(ledger))
            argv=spawn.call_args.args[0]
            self.assertIn('MESSAGE_ID='+games.CORE_ID,argv)
            self.assertIn('_UID=1000',argv);self.assertIn('+',argv)
            child.terminate.assert_called_once()

    def test_published_stage_clean_installer_and_menu_include_helper(self):
        release=(UP/'callas-release.py').read_text();security=(UP/'callas-security.sh').read_text();updater=(UP/'callas-config-update.sh').read_text()
        menu=(UP/'put-update.sh').read_text();installer=(UP.parent.parent/'instalar-arch.sh').read_text()
        self.assertIn('programas-callas-os/atualizador/callas-game-logs.py',release)
        self.assertIn('callas-game-logs.py) target=callas-game-logs',security)
        self.assertIn('/usr/local/libexec/callas-game-logs --install-system',security)
        self.assertIn('restart callas-game-logs.service',updater)
        self.assertIn('Coletar diagnóstico de jogo',menu)
        self.assertIn('Coletar diagnóstico de jogo',installer)
        self.assertIn('callas-security.sh" "$usuario" --installation',installer)

if __name__=='__main__':unittest.main()
