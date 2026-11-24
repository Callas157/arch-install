"""Run the actual shell bootstrap with an older installed launcher's file list."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from collections import Counter

ROOT=Path(__file__).resolve().parents[1];UP=ROOT/'atualizador'
spec=importlib.util.spec_from_file_location('stagingcompat',UP/'callas-release.py')
release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)


def installer_prepartition_flow():
    installer = (ROOT.parent / 'instalar-arch.sh').read_text()
    start = installer.index('# ---------------- Escolha do disco ----------------\n')
    end = installer.index('# ---------------- Particionamento ----------------\n', start)
    return installer[start:end]


class StageCompatibilityTests(unittest.TestCase):
    def test_preparation_waits_for_credentials_and_failure_stops_before_partitioning(self):
        flow=installer_prepartition_flow()
        # Only replace the hardware type probe: the disposable disk fixture is
        # a regular file. All prompt and credential handling remains real Bash.
        flow=flow.replace('[[ ! -b "$DISCO"','[[ ! -e "$DISCO"')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);disk=root/'disk';disk.write_bytes(b'untouched')
            fake='''set -Eeuo pipefail
NVIDIA=0
DISCO=
findmnt() { return 0; }
lsblk() {
    case "$*" in
        '-dpno NAME,TYPE,RO') printf '%s disk 0\\n' "$FIXTURE_DISK" ;;
        '-dno SIZE,MODEL '*) echo '30G fixture' ;;
        '-dnro TYPE,RO '*) echo 'disk 0' ;;
        '-nr -o MOUNTPOINTS '*) return 0 ;;
        *) printf '%s\\n' "$FIXTURE_DISK" ;;
    esac
}
timedatectl() { return 0; }
sed() { return 0; }
pacman() { return 0; }
mountpoint() { return 1; }
mktemp() {
    if [[ ${1:-} == /var/tmp/* ]]; then
        command mktemp "$TMPDIR/install.XXXXXXXX.log"
    else
        command mktemp "$@"
    fi
}
curl() {
    [[ ${USUARIO:-} == fixture && ${SENHA:-} == sample && ${SENHA2:-} == sample ]] || return 98
    echo 'Preparação após credenciais: OK'
    return 99
}
'''
            env=dict(os.environ,TMPDIR=str(root),FIXTURE_DISK=str(disk),CALLAS_ASSET_REF='a'*40)
            result=subprocess.run(['bash','-c',fake+flow],input='1\nfixture\nsample\nsample\n',text=True,capture_output=True,env=env)
            self.assertEqual(result.returncode,99,result.stdout+result.stderr)
            self.assertIn('Preparação após credenciais: OK',result.stdout)
            self.assertNotIn('Callas OS Update',result.stdout)
            self.assertEqual(disk.read_bytes(),b'untouched')

    def test_disk_question_is_reached_before_release_downloads(self):
        # Run the real pre-install flow up to partitioning. An invalid disk
        # answer must exit before any download, log setup or disk operation.
        flow=installer_prepartition_flow()
        with tempfile.TemporaryDirectory() as temp:
            requests=Path(temp)/'requests'
            fake='''set -Eeuo pipefail
NVIDIA=0
DISCO=
findmnt() { return 0; }
lsblk() { printf '/dev/fixture disk 0\\n'; }
curl() { echo unexpected-download >> "$FIXTURE_REQUESTS"; return 1; }
'''
            result=subprocess.run(['bash','-c',fake+flow],input='0\n',text=True,capture_output=True,
                env=dict(os.environ,FIXTURE_REQUESTS=str(requests)))
            self.assertIn('Discos encontrados:',result.stdout)
            self.assertIn('Opção inválida.',result.stdout)
            self.assertEqual(result.returncode,1,result.stderr)
            self.assertFalse(requests.exists(),'release was downloaded before disk selection')
            self.assertNotIn('Callas OS Update',result.stdout)

    def run_installer_preparation(self, tamper=False):
        """Real installer staging/copy blocks; only HTTP is served locally."""
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source';source.mkdir()
            counter=root/'requests';target=root/'target'
            bodies={path:(ROOT.parent/path).read_bytes() for path in release.FILES}
            module=bodies['programas-callas-os/atualizador/callas-release.py'].decode()
            module+='''
# Test transport only: execute real staging, hashes, syntax checks and copies.
def request(url):
    from pathlib import Path
    import os
    if '/git/trees/' in url:return Path(os.environ['FIXTURE_TREE']).read_bytes()
    name=url.rsplit('/',1)[-1]
    with open(os.environ['FIXTURE_REQUESTS'],'a') as stream:stream.write(name+'\\n')
    data=(Path(os.environ['FIXTURE_SOURCE'])/name).read_bytes()
    if os.environ.get('FIXTURE_TAMPER')=='1' and name=='callas-janelas.py':data+=b'\\n# tampered'
    return data
'''
            bodies['programas-callas-os/atualizador/callas-release.py']=module.encode()
            tree={'tree':[]}
            for path,data in bodies.items():
                (source/Path(path).name).write_bytes(data)
                sha=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
                tree['tree'].append({'path':path,'type':'blob','mode':'100644','sha':sha})
            (root/'tree.json').write_text(json.dumps(tree))
            installer=(ROOT.parent/'instalar-arch.sh').read_text()
            prepare=installer.split('# Valida a ferramenta adicional antes de apagar o disco.\n',1)[1].split('\nCALLAS_STAGE\n',1)[0]+'\nCALLAS_STAGE\n'
            copy=installer.split('# ---------------- Arquivos integrados ----------------\n',1)[1].split('install -d /mnt/usr/share/icons',1)[0]
            transport='''set -Eeuo pipefail
curl() {
    local url= destination= argument
    while (( $# )); do
        argument=$1; shift
        case $argument in
            -o) destination=$1; shift ;;
            https://*) url=$argument ;;
        esac
    done
    printf '%s\\n' "${url##*/}" >> "$FIXTURE_REQUESTS"
    cp "$FIXTURE_SOURCE/${url##*/}" "$destination"
}
'''
            extra='''
NVIDIA=0
cp "$FIXTURE_STORAGE" "$CALLAS_SECURITY_TMP/callas-storage-setup.py"
'''
            code=transport+prepare+extra+copy.replace('/mnt/',str(target)+'/')
            env=dict(os.environ,TMPDIR=str(root),CALLAS_ASSET_REF='a'*40,
                CALLAS_PROGRAMAS_BASE='https://fixture/'+'a'*40+'/programas-callas-os',
                FIXTURE_TREE=str(root/'tree.json'),FIXTURE_SOURCE=str(source),
                FIXTURE_STORAGE=str(ROOT/'instalador/callas-storage-setup.py'),
                FIXTURE_REQUESTS=str(counter),FIXTURE_TAMPER='1' if tamper else '0')
            result=subprocess.run(['bash','-c',code],env=env,capture_output=True,text=True)
            if tamper:
                self.assertNotEqual(result.returncode,0)
                self.assertIn('blob',result.stderr)
                self.assertFalse((target/'usr/local/libexec/callas-janelas').exists())
                return
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertNotIn('Callas OS Update',result.stdout)
            self.assertNotIn('Verificado:',result.stdout)
            installed=target/'usr/local/libexec'
            self.assertEqual((installed/'callas-janelas').read_bytes(),(ROOT/'janelas/callas-janelas.py').read_bytes())
            self.assertEqual((installed/'callas-monitores').read_bytes(),(ROOT/'monitores/callas-monitores.py').read_bytes())
            stage=target/'usr/local/share/callas-os/security-stage'
            for name in ('callas-release.py','callas-game-logs.py','put-update.sh','VERSION',
                         'callas-update-gui.py','callas-update-gui-install.py','callas-uninstall.py',
                         'callas-defaults.py','default-app-icons.json','callas-browser.py',
                         'callas-automount.py','callas-steam-libraries.py',
                         'callas-steam-libraries.desktop'):
                self.assertEqual((stage/name).read_bytes(),(source/name).read_bytes())
            # Install the exact staged GUI into a disposable new-system prefix.
            spec=importlib.util.spec_from_file_location('staged_gui_installer',stage/'callas-update-gui-install.py')
            gui_installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(gui_installer)
            prefix=target/'usr/local'
            entry,gui=gui_installer.deploy(stage/'callas-update-gui.py',prefix)
            home=target/'home/fixture'
            gui_installer.configure_user(home,entry,gui)
            self.assertEqual(gui.read_bytes(),(UP/'callas-update-gui.py').read_bytes())
            self.assertIn(b'Terminal=false',entry)
            self.assertIn(str(gui).encode(),entry)
            self.assertEqual((home/'Documentos/Callas OS/Atualizador do sistema.desktop').read_bytes(),entry)
            self.assertEqual((prefix/'share/applications'/gui_installer.ID).read_bytes(),entry)
            counts=Counter(counter.read_text().splitlines())
            self.assertEqual(counts['callas-janelas.py'],1,'window helper downloaded twice')
            self.assertEqual(counts['callas-monitores.py'],1,'monitor helper downloaded twice')
            self.assertEqual(counts['callas-update-gui.py'],1,'GUI downloaded twice')
            self.assertEqual(counts['callas-update-gui-install.py'],1,'GUI installer downloaded twice')

    def test_installer_prepares_current_shared_helpers_without_duplicate_downloads(self):
        self.run_installer_preparation()

    def test_installer_rejects_tampered_shared_helper_before_installing(self):
        self.run_installer_preparation(tamper=True)

    def test_complete_checks_every_current_file_and_rejects_insecure_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in ['update-assets.json',*(Path(p).name for p in release.FILES)]:
                p=root/name;p.write_text('fixture');p.chmod(0o600)
            self.assertTrue(release.stage_complete(root,os.getuid()))
            helper=root/'callas-game-logs.py';helper.unlink()
            self.assertFalse(release.stage_complete(root,os.getuid()))
            helper.symlink_to(root/'VERSION')
            with self.assertRaisesRegex(ValueError,'simbólico'):release.stage_complete(root,os.getuid())
            helper.unlink();helper.write_text('fixture');helper.chmod(0o666)
            with self.assertRaisesRegex(ValueError,'inseguro'):release.stage_complete(root,os.getuid())
            helper.chmod(0o600)
            with self.assertRaisesRegex(ValueError,'inseguro'):release.stage_complete(root,os.getuid()+1)

    def run_legacy_bootstrap(self, future=False, unsafe=False, missing_gui=False, legacy_files=None):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source';stage=root/'stage';source.mkdir();stage.mkdir()
            counter=root/'requests';ref='a'*40
            names=list(release.FILES)
            module=(UP/'callas-release.py').read_text()
            # Fixture files are owned by the test runner, not by production root.
            module=module.replace('def stage_complete(destination, expected_owner=0):',f'def stage_complete(destination, expected_owner={os.getuid()}):')
            if future:
                names.append('programas-callas-os/atualizador/future-helper.py')
                module+='\nFILES += ("programas-callas-os/atualizador/future-helper.py",)\n'
            module+='''
# Fixture-only immutable network transport; real verification and staging run.
def request(url):
    from pathlib import Path
    with Path(COUNTER).open('a') as stream:stream.write(url+'\\n')
    if '/git/trees/' in url:return Path(TREE).read_bytes()
    return (Path(SOURCE)/url.rsplit('/',1)[-1]).read_bytes()
'''.replace('COUNTER',repr(str(counter))).replace('TREE',repr(str(root/'tree.json'))).replace('SOURCE',repr(str(source)))
            bodies={name:(module.encode() if name.endswith('/callas-release.py') else b'# fixture\n') for name in names}
            tree={'tree':[]}
            for name,body in bodies.items():
                target=source/Path(name).name;target.write_bytes(body)
                tree['tree'].append({'path':name,'type':'blob','mode':'100644','sha':hashlib.sha1(b'blob '+str(len(body)).encode()+b'\0'+body).hexdigest()})
                excluded=('/callas-game-logs.py','/future-helper.py')
                if missing_gui: excluded+=('/callas-update-gui.py','/callas-update-gui-install.py')
                if ((legacy_files is not None and name in legacy_files)
                        or (legacy_files is None and not name.endswith(excluded))):
                    dest=stage/Path(name).name;dest.write_bytes(body);dest.chmod(0o600)
            (root/'tree.json').write_text(json.dumps(tree))
            (stage/'update-assets.json').write_text('{}');(stage/'update-assets.json').chmod(0o600)
            if unsafe:(stage/'callas-game-logs.py').symlink_to(stage/'VERSION')
            updater=(UP/'callas-config-update.sh').read_text()
            block=updater[updater.index('if python - "$CALLAS_RELEASE_DIR" <<\'CHECK_STAGE\''):updater.index('\nexec 8>/run/put-update.lock')]
            code='set -Eeuo pipefail\nerro(){ echo "$*" >&2; exit 2; }\n'+block
            env=dict(os.environ,CALLAS_RELEASE_DIR=str(stage),CALLAS_RELEASE_REF=ref)
            result=subprocess.run(['bash','-c',code],env=env,capture_output=True,text=True)
            if unsafe:
                self.assertNotEqual(result.returncode,0)
                self.assertIn('insegura',result.stderr)
                self.assertFalse(counter.exists())
                self.assertTrue((stage/'callas-game-logs.py').is_symlink())
                return
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertTrue((stage/'callas-game-logs.py').is_file())
            if future:self.assertTrue((stage/'future-helper.py').is_file())
            if missing_gui:
                self.assertTrue((stage/'callas-update-gui.py').is_file())
                self.assertTrue((stage/'callas-update-gui-install.py').is_file())
            self.assertTrue(counter.exists())
            before=counter.read_bytes()
            self.assertTrue(all('/'+ref in line for line in before.decode().splitlines()))
            result=subprocess.run(['bash','-c',code],env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(counter.read_bytes(),before,'complete stage downloaded again')

    def test_direct_upgrade_from_historical_launchers_without_intermediate_releases(self):
        fixtures=json.loads((Path(__file__).parent/'fixtures/historical-release-files.json').read_text())
        for fixture in fixtures:
            with self.subTest(version=fixture['version']):
                self.run_legacy_bootstrap(legacy_files=fixture['files'])

    def test_old_launcher_missing_graphical_updater_downloads_both_helpers(self):
        self.run_legacy_bootstrap(missing_gui=True)

    def test_old_launcher_missing_game_helper_expands_once(self):self.run_legacy_bootstrap()
    def test_future_helpers_do_not_require_another_shell_allowlist(self):self.run_legacy_bootstrap(future=True)
    def test_unsafe_stage_fails_before_any_download(self):self.run_legacy_bootstrap(unsafe=True)

if __name__=='__main__':unittest.main()
