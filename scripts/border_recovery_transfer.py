#!/usr/bin/env python3
"""Original TransRect DMA stop/wait CPU evidence, with no image-plane mappings."""
import unittest
from border_recovery_contract import RecoveryContract as _Harness,A
from unicorn import UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
class TransferRecovery(unittest.TestCase):
 setUp=_Harness.setUp
 reg=_Harness.reg
 put=_Harness.put
 word=_Harness.word
 call=_Harness.call
 def hook(self,u,pc,size,data):
  if pc==0x5500d000 and hasattr(self,'irq_order'):self.irq_order.append(('dispatch',self.reg(2)))
  if getattr(self,'pause_at_callback_semaphore',False) and pc==0x536b00c8:u.emu_stop();return
  if getattr(self,'pause_before_cleanup',False) and pc==0x5369a47c:u.emu_stop();return
  return _Harness.hook(self,u,pc,size,data)
 def setup_stop(self):
  svc,driver,channel0,channel1=0x55002000,0x55003000,0x55004000,0x55005000
  self.put(svc+0x14,driver,0x55006000);self.put(driver+0x14,channel0,channel1)
  self.u.mem_write(svc+0x60,b'\x01\x01')
  self.put(channel0,0xa5a50003,0xdeadbeef);self.put(channel1,0x5a5a0003,0xcafebabe)
  self.put(svc+0x20,0x55007000);self.put(svc+0x3c,0x55008000)
  self.stubs.update({0x53784de0:0,0x5377c648:0,0x536b0014:0})
  return svc,driver,channel0,channel1
 def test_stop_masks_irq_clears_control_detaches_without_status_ack(self):
  for channel in (0,1):
   svc,driver,c0,c1=self.setup_stop();self.calls.clear();self.visited.clear();reads=[]
   h=self.u.hook_add(UC_HOOK_MEM_READ,lambda u,t,p,n,v,d:reads.append((p,n)),begin=c0,end=c1+0x100)
   try:self.call(0x537e29e4,svc,channel)
   finally:self.u.hook_del(h)
   chosen=c1 if channel else c0
   self.assertEqual(self.word(chosen)&3,0)
   self.assertEqual(self.word(c0+4),0xdeadbeef);self.assertEqual(self.word(c1+4),0xcafebabe)
   self.assertEqual(reads,[(chosen,4)],'real stop reads only channel control, no status acknowledgment')
   self.assertEqual([(p,a[:3]) for p,a in self.calls if p==0x53784de0],[(0x53784de0,(0x55006000,0x6f,0x10 if channel else 1))])
   self.assertEqual([a[0] for p,a in self.calls if p==0x536b0014],[svc+(0x40 if channel else 0x24)])
   self.assertEqual(self.word(svc+(0x3c if channel else 0x20)),0,'real detach clears callback owner then posts its semaphore')
   self.assertEqual(bytes(self.u.mem_read(svc+0x60,2)),b'\0\0')
 def test_perplane_wait_failure_still_clears_stops_and_returns(self):
  worker=0x55001000
  for result in (0,1,0xffffffff):
   svc,*_=self.setup_stop();self.put(worker+0x34,svc)
   self.stubs.update({0x537e2814:0,0x536a9e8c:result,0x536a9dd4:0})
   self.calls.clear();self.visited.clear();self.call(0x5369a40c,worker,0x55007000)
   order=[p for p,a in self.calls]
   self.assertEqual(order.count(0x536a9dd4),2)
   self.assertLess(order.index(0x536a9e8c),order.index(0x536b0014))
   self.assertIn(0x537e29e4,self.visited)
   wait=[a for p,a in self.calls if p==0x536a9e8c][0]
   self.assertEqual((wait[0],wait[1],wait[3]),(worker+0x38,0x03050001,0xffffffff))
 def test_irq_dispatch_recognizes_completion_bits_without_stop_or_ack(self):
  svc=0x55002000;self.stubs[0x535628dc]=0
  for bits,expected in ((0,[]),(1,[(svc+0x1c,0x020a0001,0)]),(0x10,[(svc+0x38,0x020a0002,0)]),
       (0x11,[(svc+0x1c,0x020a0001,0),(svc+0x38,0x020a0002,0)])):
   self.calls.clear();self.visited.clear();self.assertEqual(self.call(0x537e22a0,svc,0x6f,bits),0)
   self.assertEqual([a[:3] for p,a in self.calls if p==0x535628dc],expected)
   self.assertNotIn(0x537e29e4,self.visited)
 def test_channel0_irq_calls_original_worker_event_callback_synchronously(self):
  svc,worker,vt=0x55002000,0x55001000,0x55009000
  self.put(svc+0x20,worker+4);self.put(worker+4,vt);self.put(vt+8,0x5369a2b8)
  self.stubs[0x536a9d1c]=0
  self.assertEqual(self.call(0x537e22a0,svc,0x6f,1),0)
  self.assertIn(0x535628dc,self.visited);self.assertIn(0x5369a244,self.visited)
  self.assertEqual([(p,a[:2]) for p,a in self.calls],[(0x536a9d1c,(worker+0x38,0x03050001))])
 def test_new_channel0_request_blocks_at_retained_callback_reservation_before_start(self):
  svc,*_=self.setup_stop();owner_before=self.word(svc+0x20)
  self.pause_at_callback_semaphore=True
  for n,v in enumerate((svc,0,0x55009000,0x5500a000)):self.u.reg_write(getattr(A,'UC_ARM_REG_R'+str(n)),v)
  self.u.reg_write(A.UC_ARM_REG_SP,0x550fd000);self.u.reg_write(A.UC_ARM_REG_LR,0x550ff000)
  self.u.emu_start(0x537e2814,0x550ff000,count=1000)
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x536b00c8)
  self.assertEqual((self.reg(0),self.reg(1)),(svc+0x24,0xffffffff))
  self.assertEqual(self.word(svc+0x20),owner_before)
  self.assertNotIn(0x537e25fc,self.visited)
 def test_irq_manager_writes_pending_ack_before_dispatch(self):
  manager,vt,driver=0x5500b000,0x5500c000,0x55006000
  self.put(manager,vt);self.put(manager+0x70,driver);self.put(vt+0x18,0x5500d000)
  self.u.mem_map(0x288c0000,0x1000);self.stubs[0x5500d000]=0
  for bits,enabled in ((0,0x11),(1,0x11),(0x10,0x11),(0x11,0x11),(1,0),(0x11,1),(0x11,0x10)):
   self.put(0x288c0004,enabled,bits);self.irq_order=[]
   h=self.u.hook_add(UC_HOOK_MEM_WRITE,lambda u,t,p,n,v,d:self.irq_order.append(('ack',v)),begin=0x288c0008,end=0x288c0008)
   try:self.call(0x53787b44,manager)
   finally:self.u.hook_del(h)
   dispatched=bits&enabled
   self.assertEqual(self.irq_order,[('ack',bits)]+([('dispatch',dispatched)] if dispatched else []))
 def test_precleanup_hook_can_retain_original_frame_after_wait_failure(self):
  worker=0x55001000;svc,*_=self.setup_stop();self.put(worker+0x34,svc)
  self.stubs.update({0x537e2814:0,0x536a9e8c:0,0x536a9dd4:0})
  self.pause_before_cleanup=True
  self.u.reg_write(A.UC_ARM_REG_R0,worker);self.u.reg_write(A.UC_ARM_REG_R1,0x55007000)
  self.u.reg_write(A.UC_ARM_REG_SP,0x550fd000);self.u.reg_write(A.UC_ARM_REG_LR,0x550ff000)
  self.u.emu_start(0x5369a40c,0x550ff000,count=10000)
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x5369a47c)
  self.assertEqual(self.reg(0),0);self.assertLess(self.u.reg_read(A.UC_ARM_REG_SP),0x550fd000)
  self.assertEqual([p for p,a in self.calls].count(0x536a9dd4),1)
  self.assertNotIn(0x537e29e4,self.visited)
def disassemble():
 from border_recovery_contract import ROOT,SHA,BASE
 from capstone import Cs,CS_ARCH_ARM,CS_MODE_ARM
 import hashlib
 b=(ROOT/'builds/gr3-extension-validation/official-rtos.bin').read_bytes()
 assert hashlib.sha256(b).hexdigest()==SHA
 print('Original GR III 2.10 RTOS SHA256',SHA)
 m=Cs(CS_ARCH_ARM,CS_MODE_ARM)
 for title,start,end in [
  ('irq_manager_ack_then_dispatch',0x53787b44,0x53787b9c),
  ('irq_driver_enable_pending_ack',0x5378fcf4,0x5378fd5c),
  ('perplane_wait_and_cleanup',0x5369a40c,0x5369a4b4),
  ('service_stop',0x537e29e4,0x537e2a84),
  ('driver_channel_control',0x537e2ea4,0x537e2ec0),
  ('service_irq_dispatch',0x537e22a0,0x537e2344),
  ('worker_completion_callback',0x5369a244,0x5369a2c0),
  ('callback_bind_invoke_detach',0x5356284c,0x53562934),
  ('native_packet_bind',0x537e2814,0x537e2840),
  ('channel_start_tail',0x537e2728,0x537e2764),
  ('driver_factory_roots',0x537e3668,0x537e3684),
  ('clock_ref_apb',0x537e23f0,0x537e249c),
  ('clock_ref_axi',0x537e2550,0x537e25fc),
 ]:
  print('\n'+title,hex(start),hex(end),'range_sha256',hashlib.sha256(b[start-BASE:end-BASE]).hexdigest())
  for i in m.disasm(b[start-BASE:end-BASE],start):print(f'{i.address:08x} {i.bytes.hex():8s} {i.mnemonic:8s} {i.op_str}')
if __name__=='__main__':
 import sys
 if sys.argv[1:]==['--disassemble']:disassemble()
 else:unittest.main(defaultTest='TransferRecovery',verbosity=2)
