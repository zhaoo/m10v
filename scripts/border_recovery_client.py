#!/usr/bin/env python3
"""Offline owned native-client + public caller-frame retention original ARM probes."""
from pathlib import Path
import shutil,struct,subprocess,tempfile,unittest
from border_recovery_contract import RecoveryContract as _Harness,ROOT,A
from build_gr3_iip_graph import FLAGS
BASE=0x54160000
def build():
 folder=tempfile.TemporaryDirectory(prefix='border_recovery_client_');p=Path(folder.name)
 subprocess.run([shutil.which('clang'),*FLAGS,'-c',str(ROOT/'scripts/border_recovery_client.c'),'-o',str(p/'probe.o')],check=True,capture_output=True)
 (p/'link.ld').write_text(f'SECTIONS {{ . = {BASE}; .text : {{ *(.text*) }} .rodata : {{ *(.rodata*) }} /DISCARD/ : {{ *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }} }}')
 subprocess.run([shutil.which('ld.lld'),'-T',str(p/'link.ld'),'--entry=border_recovery_construct',str(p/'probe.o'),'-o',str(p/'probe.elf')],check=True,capture_output=True)
 b=(p/'probe.elf').read_bytes();sh=struct.unpack_from('<I',b,32)[0];n=struct.unpack_from('<H',b,48)[0]
 rows=[struct.unpack_from('<10I',b,sh+i*40) for i in range(n)];image=bytearray();symbols={}
 for row in rows:
  if row[2]&2 and row[5]:
   assert row[1]==1 and not row[2]&1
   off=row[3]-BASE;assert 0<=off<65536
   if len(image)<off+row[5]:image.extend(bytes(off+row[5]-len(image)))
   image[off:off+row[5]]=b[row[4]:row[4]+row[5]]
  if row[1]==2:
   sr=rows[row[6]];strings=b[sr[4]:sr[4]+sr[5]]
   for at in range(row[4],row[4]+row[5],16):
    name,value,_,info,_,section=struct.unpack_from('<IIIBBH',b,at);name=strings[name:].split(b'\0',1)[0].decode()
    assert section or not name
    if name.startswith('border_recovery_') and info&15==2:symbols[name]=value
 return folder,bytes(image),symbols
class ClientRecovery(unittest.TestCase):
 reg=_Harness.reg;put=_Harness.put;word=_Harness.word;call=_Harness.call
 @classmethod
 def setUpClass(cls):cls.folder,cls.code,cls.symbols=build()
 @classmethod
 def tearDownClass(cls):cls.folder.cleanup()
 def setUp(self):
  _Harness.setUp(self);self.u.mem_map(BASE,0x10000);self.u.mem_write(BASE,self.code)
  self.client,self.worker,self.job=0x55001000,0x55002000,0x55003000
  self.stubs.update({0x536a9bf8:0,0x536aa3a4:1,0x536aa34c:0,0x536a9d1c:0})
  self.call(self.symbols['border_recovery_construct'],self.client)
  self.put(self.job,0,self.client,0x55004000,0x010e8006,0)
  self.assertEqual(self.call(self.symbols['border_recovery_prepare'],self.client,self.worker,self.job),1)
  self.calls.clear();self.visited.clear();self.pause_outer=False
 def hook(self,u,pc,size,data):
  if pc==0x534aae2c and self.pause_outer and self.reg(4)==self.client+4 and self.word(self.client+32)==0x42524331 and (self.word(self.client+36) or self.word(self.client+40)):u.emu_stop();return
  if pc==0x536abd28:
   # Queue backend: copy caller's two result words as zeros, keep stack job
   # pointer recorded; no worker or DMA is started by this endpoint.
   sp=u.reg_read(A.UC_ARM_REG_SP);result=self.word(sp+8);self.put(result,0,0)
   self.enqueued_job=self.reg(1)
  if pc==0x536a9d1c and getattr(self,'observe_notify',False):
   self.inside_signal=(self.word(self.client+36),self.word(self.client+40))
  return _Harness.hook(self,u,pc,size,data)
 def callback_call(self,fn,*args):
  for n,v in enumerate(args):self.u.reg_write(getattr(A,'UC_ARM_REG_R'+str(n)),v)
  self.u.reg_write(A.UC_ARM_REG_SP,0x550ed000);self.u.reg_write(A.UC_ARM_REG_LR,0x550ff000)
  self.u.emu_start(fn,0x550ff000,count=10000)
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x550ff000)
  return self.reg(0)
 def test_pending_prevents_destruction_before_any_callback(self):
  self.assertEqual(self.word(self.client+40),0)
  self.assertEqual(self.call(self.symbols['border_recovery_can_release'],self.client),0)
  self.assertEqual(self.call(self.symbols['border_recovery_destroy_if_done'],self.client),0)
  self.assertNotIn(0x534ac164,self.visited)
 def test_real_completion_callback_keeps_pending_and_inflight_through_native_signal(self):
  self.observe_notify=True
  notify=self.word(self.word(self.client)+8)
  self.call(notify,self.client,0x03050006,0)
  self.assertEqual(self.inside_signal,(1,1))
  self.assertIn(0x534aab0c,self.visited)
  self.assertEqual([(a[0],a[1]) for pc,a in self.calls if pc==0x536a9d1c],[(self.client+4,0x400)])
  self.assertEqual((self.word(self.client+36),self.word(self.client+40),self.word(self.client+44)),(0,0,1))
  self.assertEqual(self.call(self.symbols['border_recovery_destroy_if_done'],self.client),1)
  self.assertIn(0x534ac164,self.visited)
 def test_unrelated_callback_does_not_complete_job_and_match_requires_exact_client_worker_job(self):
  self.call(self.word(self.word(self.client)+8),self.client,0x03050001,0)
  self.assertEqual(self.word(self.client+36),1)
  match=self.symbols['border_recovery_match']
  self.assertEqual(self.call(match,self.client,self.worker,self.job),1)
  self.assertEqual(self.call(match,self.client,self.worker+4,self.job),0)
  self.put(self.job+4,self.client+4)
  self.assertEqual(self.call(match,self.client,self.worker,self.job),0)
  self.put(self.client+32,0)
  self.assertEqual(self.call(match,self.client,self.worker,self.job),0)
 def test_original_public_wait_failure_unwinds_without_owned_gate(self):
  self.stubs.update({0x536abd28:0,0x536a9e8c:0,0x536a9dd4:0})
  self.call(0x534aad6c,self.client,0x400,self.worker+8,self.job)
  self.assertIn(0x534aae48,self.visited)
  self.assertEqual(self.word(self.client+36),1,'pending work exists even after stock wait caller returned')
 def test_owned_gate_retains_original_public_frame_until_full_completion_callback(self):
  self.stubs.update({0x536abd28:0,0x536a9e8c:0,0x536a9dd4:0});self.pause_outer=True
  for n,v in enumerate((self.client,0x400,self.worker+8,self.job)):self.u.reg_write(getattr(A,'UC_ARM_REG_R'+str(n)),v)
  self.u.reg_write(A.UC_ARM_REG_SP,0x550fd000);self.u.reg_write(A.UC_ARM_REG_LR,0x550ff000)
  self.u.emu_start(0x534aad6c,0x550ff000,count=10000)
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x534aae2c)
  self.assertLess(self.u.reg_read(A.UC_ARM_REG_SP),0x550fd000)
  self.assertNotIn(0x536a9dd4,self.visited)
  paused=self.u.context_save();held_sp=self.u.reg_read(A.UC_ARM_REG_SP)
  held_stack=bytes(self.u.mem_read(held_sp,0x550fd000-held_sp))
  # Execute full custom wrapper + real original notification with independent
  # callback stack, preserving paused public caller CPU context and memory.
  self.callback_call(self.word(self.word(self.client)+8),self.client,0x03050006,0)
  self.assertEqual(self.callback_call(self.symbols['border_recovery_can_release'],self.client),1)
  self.assertEqual(bytes(self.u.mem_read(held_sp,len(held_stack))),held_stack,'callback uses a separate stack and preserves held caller frame')
  self.u.context_restore(paused);self.pause_outer=False
  self.u.emu_start(0x534aae2c,0x550ff000,count=10000)
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x550ff000)
  self.assertIn(0x536a9dd4,self.visited)
if __name__=='__main__':unittest.main(defaultTest='ClientRecovery',verbosity=2)
