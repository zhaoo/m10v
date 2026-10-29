#!/usr/bin/env python3
"""Owned Transfer-worker CAS gate and original singleton lifetime evidence."""
import unittest
from border_recovery_wait_guard import build,WaitGuard as _WaitGuard
from border_recovery_contract import A
class StageGate(unittest.TestCase):
 reg=_WaitGuard.reg;put=_WaitGuard.put;word=_WaitGuard.word;call=_WaitGuard.call;invoke=_WaitGuard.invoke
 @classmethod
 def setUpClass(cls):cls.folder,cls.code,cls.symbols=build()
 @classmethod
 def tearDownClass(cls):cls.folder.cleanup()
 def setUp(self):
  _WaitGuard.setUp(self);self.u.mem_map(0x5536c000,0x1000)
  self.factory=0x5536c00c;self.guard=0x5536c018;self.put(self.guard,1);self.put(self.factory+4,self.worker)
  self.call(self.symbols['m10v_border_transfer_construct'],self.worker)
  self.registered=[];self.deletion_attempts=[];self.stop_at_yield=False
 def hook(self,u,pc,size,data):
  def ret(v):u.reg_write(A.UC_ARM_REG_R0,v);u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
  if pc==0x5313fbb8:self.registered.append(tuple(self.reg(i) for i in range(3)));ret(0);return
  if pc==0x5369ad5c:self.deletion_attempts.append((self.reg(0),self.word(self.worker+0x54)));ret(0);return
  return _WaitGuard.hook(self,u,pc,size,data)
 def enter(self,token):return self.call(self.symbols['m10v_border_stage_enter'],token)
 def leave(self,token):return self.call(self.symbols['m10v_border_stage_leave'],self.worker,token)
 def test_zero_token_does_not_touch_factory_and_owned_gate_uses_exact_singleton(self):
  self.visited.clear();self.assertEqual(self.enter(0),0);self.assertNotIn(0x5369a0e8,self.visited)
  self.assertEqual(self.enter(71),self.worker);self.assertIn(0x5369a0e8,self.visited)
  self.assertEqual(self.word(self.worker+0x54),71)
  self.assertEqual(self.leave(72),0);self.assertEqual(self.word(self.worker+0x54),71)
  self.assertEqual(self.leave(71),1);self.assertEqual(self.word(self.worker+0x54),0)
 def test_second_owner_waits_until_actual_matching_cas_release(self):
  self.assertEqual(self.enter(71),self.worker);self.stop_at_yield=True
  self.invoke(self.symbols['m10v_border_stage_enter'],(72,))
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x536b0a74)
  self.assertEqual(self.word(self.worker+0x54),71);waiting=self.u.context_save()
  self.stop_at_yield=False
  self.invoke(self.symbols['m10v_border_stage_leave'],(self.worker,71),0x550dd000)
  self.assertEqual(self.reg(0),1)
  self.u.context_restore(waiting);self.u.reg_write(A.UC_ARM_REG_R0,0)
  self.u.reg_write(A.UC_ARM_REG_PC,self.u.reg_read(A.UC_ARM_REG_LR))
  self.u.emu_start(self.u.reg_read(A.UC_ARM_REG_PC),0x550ff000,count=10000)
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x550ff000)
  self.assertEqual(self.reg(0),self.worker);self.assertEqual(self.word(self.worker+0x54),72)
  self.assertEqual(self.leave(71),0);self.assertEqual(self.word(self.worker+0x54),72)
 def test_wrong_tail_tag_is_rejected_before_gate_acquisition(self):
  self.put(self.worker+0x44,0);self.assertEqual(self.enter(71),0)
  self.assertEqual(self.word(self.worker+0x54),0)
 def test_native_factory_guard_initializes_static_object_and_registers_destructor(self):
  self.put(self.guard,0);self.stubs.update({0x538c8444:1,0x538c84ac:0})
  self.assertEqual(self.enter(71),0,'native getter alone does not create its worker')
  self.assertEqual(self.registered[0][0],0x53699ed0)
  self.assertEqual(self.word(self.factory+4),0)
  self.assertNotIn(0x536af2a8,self.visited)
 def test_original_factory_destroy_does_not_consult_stage_gate_lifetime_lease(self):
  self.assertEqual(self.enter(71),self.worker)
  self.invoke(0x53699f1c,(self.factory,))
  self.assertEqual(self.deletion_attempts,[(self.worker,71)])
  self.assertEqual(self.word(self.factory+4),0)
  self.assertEqual(self.word(self.worker+0x54),71,'heap-free endpoint was replaced; real native teardown would invalidate this storage')
if __name__=='__main__':unittest.main(defaultTest='StageGate',verbosity=2)
