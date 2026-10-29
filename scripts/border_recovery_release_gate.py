#!/usr/bin/env python3
"""Private pre-release gate: actual stock lock wrappers/getters, no DMA model."""
import unittest
from border_recovery_wait_guard import build,WaitGuard as _WaitGuard
from border_recovery_contract import A
class ReleaseGate(unittest.TestCase):
 reg=_WaitGuard.reg;put=_WaitGuard.put;word=_WaitGuard.word;call=_WaitGuard.call
 invoke=_WaitGuard.invoke;patch_bl=_WaitGuard.patch_bl;configure_other_owner=_WaitGuard.configure_other_owner
 @classmethod
 def setUpClass(cls):cls.folder,cls.code,cls.symbols=build()
 @classmethod
 def tearDownClass(cls):cls.folder.cleanup()
 def setUp(self):
  _WaitGuard.setUp(self)
  self.u.mem_map(0x5536c000,0x1000);self.put(0x5536c880,1);self.put(0x5536c7a4,1)
  self.stubs.pop(0x536ae71c,None);self.stubs.pop(0x536ae870,None)
  self.stubs[0x536b9f1c]=0
  self.kernel=[];self.held=set();self.cleanup=[];self.observations=[];self.stop_at_yield=False
  self.kernel_results={};self.update_on_yield=None;self.second_busy=False
 def hook(self,u,pc,size,data):
  def ret(v):u.reg_write(A.UC_ARM_REG_R0,v);u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
  if pc in (0x53050c9c,0x53051188,0x53051284,0x530511f4):
   lock=self.reg(0);self.kernel.append((pc,lock,self.reg(1)))
   sequence=self.kernel_results.get(pc,[]);result=sequence.pop(0) if sequence else 0
   if result==0:
    if pc in (0x53050c9c,0x53051188):self.held.add(lock)
    else:self.held.discard(lock)
   ret(result);return
  if pc in (0x53778490,0x53778458,0x53778474):
   self.assertEqual(self.held,{0x9090,0x1414},'driver conditions observed only while both native locks held')
   if pc==0x53778474 and self.second_busy:self.put(self.registers+4,7)
   self.observations.append((pc,self.word(self.registers+4)))
  if pc==0x5376ed74:
   self.assertEqual(self.held,set(),'release re-enters native locks only after verified unlock')
   self.cleanup.append((self.reg(0),self.reg(1),self.reg(2)))
   ret(77);return
  if pc==0x536b0a74:
   self.yields+=1
   if self.update_on_yield:self.update_on_yield(self)
   if self.stop_at_yield:u.emu_stop();return
   ret(0);return
  return _WaitGuard.hook(self,u,pc,size,data)
 def fixture(self,kind='fill',count=1,status=4):
  self.configure_other_owner(kind)
  self.service,self.context,self.driver,self.registers=0x55007000,0x55008000,0x55009000,0x5500a000
  self.frame=0x5500d000
  self.put(self.service+0x24,self.driver);self.put(self.driver+0x14,self.registers);self.put(self.registers+4,status)
  self.put(self.service+0x94,0x9090);self.put(self.service+0x18,0x1414)
  self.u.mem_write(self.service+0xfc,bytes([count]))
  if kind=='fill':
   self.put(self.worker+0x44,self.context);self.put(self.context+0xc,self.service)
   self.put(self.frame-4,0x53659258);self.put(self.frame-36,self.worker)
   self.info=self.frame-0xb0;self.callback=self.context+4
  else:
   self.put(self.worker+0x34,self.context);self.put(self.context+0x38,self.service)
   self.put(self.frame-4,0x536733e4);self.put(self.frame-28,self.worker)
   self.put(self.frame-0x2d0,self.context);self.put(self.frame-0x2e4,self.context+4)
   self.info=self.frame-0x194;self.callback=self.context+4
  self.u.mem_write(self.info+3,b'\0');self.u.mem_write(self.info+0x74,b'\x01')
  self.put(self.info+0x78,0x200);self.put(self.service+0x100,0x200);self.put(self.service+0x40,self.callback)
  self.kind=kind
 def start_gate(self):
  args=(self.service,self.callback,self.info,self.frame)
  if self.kind=='fill':args+=(self.context,)
  self.invoke(self.symbols['m10v_border_'+self.kind+'_release'],args)
 def test_real_native_lock_wrappers_success_order_and_normal_driver_contract(self):
  self.fixture();self.start_gate()
  self.assertEqual(self.reg(0),77);self.assertEqual(len(self.cleanup),1)
  self.assertEqual([(pc,lock) for pc,lock,tmo in self.kernel],[(0x53050c9c,0x9090),(0x53051188,0x1414),(0x530511f4,0x1414),(0x53051284,0x9090)])
  self.assertEqual(self.kernel[0][2],0xffffffff);self.assertEqual(self.kernel[1][2],5000)
  self.assertEqual([pc for pc,s in self.observations],[0x53778490,0x53778458,0x53778474])
  self.assertEqual(self.word(self.service+0x40),self.callback);self.assertEqual(self.word(self.service+0x100),0x200)
 def test_contradictory_completion_and_busy_never_enters_cleanup_or_aborts(self):
  self.fixture(status=0);self.stop_at_yield=True;self.start_gate()
  self.assertEqual(self.cleanup,[]);self.assertEqual(self.held,set())
  self.assertEqual(self.word(self.service+0x40),self.callback);self.assertEqual(self.word(self.client+36),1)
  self.assertNotIn(0x5376daf0,self.visited);self.assertNotIn(0x5377876c,self.visited)
  self.assertEqual(self.observations,[(0x53778490,0)])
 def test_others_active_then_first_busy_then_second_busy_retry_full_native_gate(self):
  self.fixture(count=2,status=0)
  def progress(s):
   if s.yields==1:s.u.mem_write(s.service+0xfc,b'\x01')
   elif s.yields==2:s.put(s.registers+4,4);s.second_busy=True
   elif s.yields==3:s.second_busy=False;s.put(s.registers+4,4)
  self.update_on_yield=progress;self.start_gate()
  self.assertEqual(self.yields,3);self.assertEqual(len(self.cleanup),1)
  self.assertEqual(self.held,set())
  self.assertEqual(sum(pc==0x53778458 for pc,v in self.observations),2,'second-busy retry rechecks sole-active and first predicate before another command')
 def test_failed_global_lock_never_treated_as_held(self):
  self.fixture();self.kernel_results[0x53050c9c]=[0xffffffff,0];self.start_gate()
  self.assertEqual(self.yields,1);self.assertEqual(len(self.cleanup),1)
  self.assertEqual([pc for pc,lock,tmo in self.kernel[:3]],[0x53050c9c,0x53050c9c,0x53051188])
 def test_failed_mutex_releases_only_acquired_global_lock_then_retries(self):
  self.fixture();self.kernel_results[0x53051188]=[0xffffffff,0];self.start_gate()
  self.assertEqual(self.yields,1);self.assertEqual(len(self.cleanup),1)
  self.assertEqual([pc for pc,lock,tmo in self.kernel[:3]],[0x53050c9c,0x53051188,0x53051284])
 def test_missing_reservation_fatally_retains_owners_without_native_cleanup(self):
  self.fixture();self.put(self.service+0x100,0);self.stop_at_yield=True;self.start_gate()
  self.assertEqual(self.cleanup,[]);self.assertEqual(self.held,{0x9090,0x1414})
  self.assertEqual(self.word(self.client+36),1)
 def test_actual_fill_successful_event_then_busy_release_holds_until_native_conditions(self):
  self.fixture(status=0);self.put(self.frame-0x2d0,self.callback)
  self.patch_bl(0x5376a370,self.symbols['border_recovery_fill_wait_hook'],0xebfcfec5)
  self.patch_bl(0x5376a38c,self.symbols['border_recovery_fill_release_hook'],0xeb001278)
  self.u.reg_write(A.UC_ARM_REG_FP,self.frame);self.u.reg_write(A.UC_ARM_REG_R6,self.context)
  self.u.reg_write(A.UC_ARM_REG_R9,self.context+0x20);self.u.reg_write(A.UC_ARM_REG_R8,1)
  self.u.reg_write(A.UC_ARM_REG_R10,0);self.u.reg_write(A.UC_ARM_REG_SP,0x5500c000)
  self.wait_results=[(1,1)];self.stop_at_yield=True
  self.u.emu_start(0x5376a358,0x5376a390,count=100000)
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x536b0a74)
  self.assertEqual(len(self.waits),1);self.assertEqual(self.cleanup,[]);self.assertEqual(self.held,set())
  self.assertEqual(self.observations,[(0x53778490,0)])
  self.assertEqual(self.word(self.service+0x40),self.callback)
  self.put(self.registers+4,4);self.stop_at_yield=False
  self.u.reg_write(A.UC_ARM_REG_R0,0);self.u.reg_write(A.UC_ARM_REG_PC,self.u.reg_read(A.UC_ARM_REG_LR))
  self.u.emu_start(self.u.reg_read(A.UC_ARM_REG_PC),0x5376a390,count=100000)
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x5376a390)
  self.assertEqual(len(self.cleanup),1);self.assertEqual(self.reg(0),77)
 def test_failed_unlock_fatally_retains_instead_of_entering_stock_release(self):
  self.fixture();self.kernel_results[0x530511f4]=[0xffffffff];self.stop_at_yield=True;self.start_gate()
  self.assertEqual(self.cleanup,[]);self.assertEqual(self.held,{0x9090,0x1414})
 def test_actual_resize_prerelease_callsite_uses_verified_saved_context(self):
  self.fixture('resize');self.patch_bl(0x53771968,self.symbols['border_recovery_resize_release_hook'],0xebfff501)
  self.u.reg_write(A.UC_ARM_REG_FP,self.frame);self.u.reg_write(A.UC_ARM_REG_SP,0x5500c000)
  self.u.emu_start(0x53771958,0x5377196c,count=100000)
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x5377196c)
  self.assertEqual(self.cleanup,[(self.service,self.callback,self.info)])
 def test_original_irq_callback_progress_does_not_require_service_gate_locks(self):
  self.fixture();vt=0x5500e000
  self.put(self.context+4,vt);self.put(vt+8,0x53768744)
  self.held={0x9090,0x1414}
  self.invoke(0x5376d0e8,(self.service,0x5b,0x100))
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x550ff000)
  self.assertEqual(self.signal_state[-1][2:],(self.context+0x20,1))
  self.assertEqual(self.kernel,[],'original IRQ dispatcher and synchronous Fill callback take neither service lock')
  self.assertEqual(self.held,{0x9090,0x1414})
 def test_two_unserialized_private_jobs_can_both_hold_count2_and_require_outer_gate(self):
  import json
  from border_recovery_contract import ROOT
  contract=json.loads((ROOT/'scripts/border_recovery_wait_guard_contract.json').read_text())
  self.assertTrue(contract['serialized_private_chain_required']);self.assertFalse(contract['stage_gate_installed'])
  self.fixture(count=2,status=4);client1=self.client;self.stop_at_yield=True;self.start_gate()
  self.assertEqual(self.cleanup,[]);self.assertEqual(self.held,set())
  sp1=self.u.reg_read(A.UC_ARM_REG_SP);stack1=bytes(self.u.mem_read(sp1,0x550fd000-sp1))
  self.client,self.worker,self.job=0x55010000,0x55011000,0x55012000
  self.invoke(self.symbols['m10v_border_client_construct'],(self.client,),0x5502d000)
  self.put(self.job,0,self.client,0x55015000,0x00708002,0)
  self.invoke(self.symbols['m10v_border_client_prepare'],(self.client,0x03020002,0x40),0x5502d000)
  self.invoke(self.symbols['m10v_border_resize_construct'],(self.worker,),0x5502d000)
  self.put(self.worker+0x48,0x42525731,self.client,self.job,1);self.put(self.client+60,self.worker,self.job)
  frame,context=0x55014000,0x55013000;info=frame-0x194;callback=context+4
  self.put(self.worker+0x34,context);self.put(context+0x38,self.service)
  self.put(frame-4,0x536733e4);self.put(frame-28,self.worker);self.put(frame-0x2d0,context);self.put(frame-0x2e4,callback)
  self.u.mem_write(info+3,b'\x01');self.u.mem_write(info+0x74,b'\x01');self.put(info+0x78,0x400)
  self.put(self.service+0x104,0x400);self.put(self.service+0x5c,callback)
  self.invoke(self.symbols['m10v_border_resize_release'],(self.service,callback,info,frame),0x5502d000)
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x536b0a74)
  self.assertEqual(self.cleanup,[]);self.assertEqual(self.held,set())
  self.assertEqual(bytes(self.u.mem_read(self.service+0xfc,1)),b'\x02')
  self.assertEqual((self.word(client1+36),self.word(self.client+36)),(1,1))
  self.assertEqual(bytes(self.u.mem_read(sp1,len(stack1))),stack1)
 def test_resize_exact_parent_frame_uses_same_gate(self):
  self.fixture('resize');self.start_gate();self.assertEqual(self.reg(0),77);self.assertEqual(len(self.cleanup),1)
if __name__=='__main__':unittest.main(defaultTest='ReleaseGate',verbosity=2)
