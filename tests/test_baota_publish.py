"""Exercise deployment guards and rollback with fake host commands, no network."""
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
SCRIPT=Path(__file__).resolve().parents[1]/'skills/m10v-baota-publish/scripts/update-server.sh'
BEFORE='1'*40
AFTER='2'*40
FAKE='''#!/usr/bin/env python3
import os,sys
from pathlib import Path
name=Path(sys.argv[0]).name;a=sys.argv[1:];root=Path(os.environ['M10V_DEPLOY_ROOT'])
with (root/'trace').open('a') as f:f.write(name+' '+repr(a)+'\\n')
if name=='git':
 if a[:2]==['remote','get-url']:print(os.getenv('FAKE_ORIGIN','https://github.com/zhaoo/m10v.git'))
 elif a[0]=='status':
  if os.getenv('FAKE_STATUS_FAIL'):sys.exit(128)
  print(' M server-edit' if os.getenv('FAKE_DIRTY') else '',end='')
 elif a[0]=='branch':print('main')
 elif a[0]=='rev-parse':print(os.environ['FAKE_EXPECTED'] if (a[1]=='origin/main' or a[1].startswith('refs/m10v/releases/')) else (root/'head').read_text())
 elif a[0]=='merge':
  (root/'head').write_text(a[-1]);(root/'release-source').write_text('source')
 elif a[0]=='reset':(root/'head').write_text(a[-1])
 elif 'fetch' in a and os.getenv('FAKE_FETCH_FAILURES'):
  count=root/'fetch-count';n=int(count.read_text()) if count.exists() else 0;count.write_text(str(n+1))
  if n<int(os.environ['FAKE_FETCH_FAILURES']):sys.exit(128)
elif name=='systemctl':
 if a[0]=='show':print('www' if a[3]=='User' else str(root))
elif name=='systemd-run':
 import subprocess
 sys.exit(subprocess.run(a[a.index('--')+1:]).returncode)
elif name=='runuser':
 if os.getenv('FAKE_BUILD_SLEEP'):__import__('time').sleep(30)
 if os.getenv('FAKE_REQUIRE_READABLE') and not ((root/'release-source').stat().st_mode & 4):sys.exit(13)
 sys.exit(int(os.getenv('FAKE_BUILD_FAIL','0')))
elif name=='flock':sys.exit(int(os.getenv('FAKE_LOCK_FAIL','0')))
elif name=='curl':Path(a[a.index('-o')+1]).write_text('<input id="debug-mode">')
'''
class BaotaPublishTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name);self.bin=self.root/'commands';self.bin.mkdir()
  for name in ('git','systemctl','systemd-run','journalctl','runuser','flock','chown','curl','sleep'):
   p=self.bin/name;p.write_text(FAKE);p.chmod(0o755)
  (self.root/'head').write_text(BEFORE)
  (self.root/'.venv/bin').mkdir(parents=True)
  (self.root/'.venv/bin/python').symlink_to(Path(__import__('sys').executable))
  (self.root/'bin').mkdir()
  for name in ('fwdc239b-gr3-official.bin','fwdc243b-gr3x-official.bin'):(self.root/'bin'/name).write_bytes(b'protected')
  self.env={**os.environ,'PATH':str(self.bin)+':'+os.environ['PATH'],'M10V_DEPLOY_ROOT':str(self.root),'M10V_DEPLOY_NODE':__import__('sys').executable,'M10V_DEPLOY_LOCK':str(self.root/'lock'),'FAKE_EXPECTED':AFTER}
 def run_script(self,*args,**env):
  return subprocess.run(['bash',str(SCRIPT),*args],env={**self.env,**env},capture_output=True,text=True)
 def trace(self):return (self.root/'trace').read_text() if (self.root/'trace').exists() else ''
 def test_gr4_actual_build_is_checked_before_service_restart(self):
  r=self.run_script('--deploy',AFTER);self.assertEqual(r.returncode,0,r.stderr)
  trace=self.trace();self.assertIn('scripts/check_gr4_release.mjs',trace)
  self.assertLess(trace.index('scripts/check_gr4_release.mjs'),trace.index("'restart'"))
  self.assertIn('FIRMWARE_BUILD_OK model=gr4',r.stdout)
 def test_build_process_tree_is_bounded_and_reports_stages(self):
  r=self.run_script('--deploy',AFTER);self.assertEqual(r.returncode,0,r.stderr)
  trace=self.trace()
  self.assertEqual(trace.count('systemd-run '),3)
  for control in ('MemoryHigh=600M','MemoryMax=700M','MemorySwapMax=384M','CPUQuota=100%','TasksMax=64','RuntimeMaxSec=600','OOMPolicy=kill','KillMode=control-group'):
   self.assertIn(control,trace)
  self.assertIn('FIRMWARE_BUILD_START model=gr3x',r.stdout)
  self.assertIn('FIRMWARE_BUILD_START model=gr4',r.stdout)
  self.assertRegex(r.stdout,r'FIRMWARE_BUILD_START model=gr4 .*timeout=900s')
  self.assertIn('RuntimeMaxSec=900',trace)
 def test_term_interrupts_wait_and_stops_build_before_rollback(self):
  proc=subprocess.Popen(['bash',str(SCRIPT),'--deploy',AFTER],env={**self.env,'FAKE_BUILD_SLEEP':'1'},stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
  try:
   deadline=time.monotonic()+5
   while 'runuser ' not in self.trace() and time.monotonic()<deadline:time.sleep(.02)
   self.assertIn('runuser ',self.trace())
   proc.terminate()
   proc.wait(timeout=3)
   trace=self.trace();self.assertLess(trace.index("'stop'"),trace.index("'reset'"))
   self.assertEqual((self.root/'head').read_text(),BEFORE)
  finally:
   if proc.poll() is None:proc.kill();proc.wait()
   proc.stdout.close();proc.stderr.close()
 def test_invalid_sha_never_touches_server(self):
  r=self.run_script('--deploy','main');self.assertEqual(r.returncode,2);self.assertEqual(self.trace(),'')
 def test_git_status_failure_stops_before_mutation(self):
  r=self.run_script('--deploy',AFTER,FAKE_STATUS_FAIL='1');self.assertNotEqual(r.returncode,0)
  self.assertNotIn("'fetch'",self.trace());self.assertNotIn("'restart'",self.trace())
 def test_github_origin_without_dot_git_is_accepted(self):
  r=self.run_script('--check',FAKE_ORIGIN='https://github.com/zhaoo/m10v');self.assertEqual(r.returncode,0,r.stderr)
 def test_check_is_read_only(self):
  r=self.run_script('--check');self.assertEqual(r.returncode,0,r.stderr)
  self.assertNotIn("'fetch'",self.trace());self.assertNotIn("'restart'",self.trace())
 def test_dirty_checkout_and_lock_conflict_stop_before_fetch(self):
  r=self.run_script('--deploy',AFTER,FAKE_DIRTY='1');self.assertNotEqual(r.returncode,0);self.assertNotIn("'fetch'",self.trace())
  r=self.run_script('--deploy',AFTER,FAKE_LOCK_FAIL='1');self.assertNotEqual(r.returncode,0);self.assertNotIn("'fetch'",self.trace())
 def test_changed_remote_stops_before_merge(self):
  r=self.run_script('--deploy',AFTER,FAKE_EXPECTED='3'*40);self.assertNotEqual(r.returncode,0)
  self.assertNotIn("'merge',",self.trace());self.assertNotIn("'restart'",self.trace())
 def test_build_failure_restores_previous_commit(self):
  r=self.run_script('--deploy',AFTER,FAKE_BUILD_FAIL='1');self.assertNotEqual(r.returncode,0)
  self.assertEqual((self.root/'head').read_text(),BEFORE);self.assertIn("'reset', '--keep'",self.trace());self.assertNotIn('DEPLOY_OK',r.stdout)
  self.assertIn("'stop'",self.trace())
 def test_bundle_path_verifies_and_avoids_github_fetch(self):
  bundle=self.root/'release.bundle';bundle.write_bytes(b'fixture')
  r=self.run_script('--deploy',AFTER,str(bundle));self.assertEqual(r.returncode,0,r.stderr)
  self.assertIn("'bundle', 'verify'",self.trace());self.assertIn('refs/m10v/releases/'+AFTER,self.trace())
  self.assertNotIn("'fetch', 'origin'",self.trace())
 def test_transient_fetch_is_retried_before_deploy(self):
  r=self.run_script('--deploy',AFTER,FAKE_FETCH_FAILURES='1');self.assertEqual(r.returncode,0,r.stderr)
  self.assertIn('DEPLOY_OK',r.stdout);self.assertEqual((self.root/'fetch-count').read_text(),'2')
 def test_exhausted_fetch_retries_preserve_running_commit(self):
  r=self.run_script('--deploy',AFTER,FAKE_FETCH_FAILURES='5');self.assertNotEqual(r.returncode,0)
  self.assertEqual((self.root/'head').read_text(),BEFORE);self.assertNotIn("'merge',",self.trace())
  self.assertEqual((self.root/'fetch-count').read_text(),'3')
 def test_restrictive_ssh_umask_does_not_hide_deployed_sources(self):
  r=subprocess.run(['bash','-c','umask 077; exec bash "$1" --deploy "$2"','ssh-fixture',str(SCRIPT),AFTER],env={**self.env,'FAKE_REQUIRE_READABLE':'1'},capture_output=True,text=True)
  self.assertEqual(r.returncode,0,r.stderr)
  self.assertTrue((self.root/'release-source').stat().st_mode & 4)
 def test_success_checks_builds_restart_and_exact_commit(self):
  r=self.run_script('--deploy',AFTER);self.assertEqual(r.returncode,0,r.stderr)
  self.assertEqual((self.root/'head').read_text(),AFTER);self.assertIn('DEPLOY_OK commit='+AFTER,r.stdout)
  self.assertIn('scripts/build_gr3_device_candidate.mjs',self.trace());self.assertIn('scripts/check_gr3x_release.mjs',self.trace());self.assertNotIn('scripts/export_gr3_m10v_native.mjs',self.trace());self.assertIn('MODEL_GUARD_OK model=gr3x native_export=blocked',r.stdout);self.assertIn('M10V_PYTHON=',self.trace());self.assertEqual(self.trace().count('runuser '),3);self.assertIn("'restart'",self.trace())
  self.assertEqual((self.root/'bin/fwdc239b-gr3-official.bin').read_bytes(),b'protected')
if __name__=='__main__':unittest.main()
