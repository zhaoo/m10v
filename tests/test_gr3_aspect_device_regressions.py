"""Regressions derived from r3 device assertions, not mocked success paths."""
import unittest
from unicorn import UC_HOOK_CODE,arm_const as A
from tests.test_gr3_aspect import AspectTests,STOP,RAM
class DeviceAspectRegressions(unittest.TestCase):
 setUpClass=classmethod(AspectTests.setUpClass.__func__)
 machine=AspectTests.machine
 call=AspectTests.call
 live_machine=AspectTests.live_machine
 def test_restored_sixteen_by_nine_has_a_real_caption(self):
  self.assertNotEqual(self.call(0x540b9428,0,2).reg_read(A.UC_ARM_REG_R0),0)
 def test_original_binary_converter_accepts_restored_wide_identity(self):
  u=self.machine();bad=[]
  def fail(m,a,s,d):
   if a==0x536b93d0:bad.append(a);m.emu_stop()
  u.hook_add(UC_HOOK_CODE,fail);u.reg_write(A.UC_ARM_REG_R0,2)
  u.emu_start(0x540b9788,STOP,count=10000)
  self.assertEqual(bad,[])
  self.assertEqual(u.reg_read(A.UC_ARM_REG_R0),0)
 def test_restored_wide_af_bounds_are_centered_and_inside_crop(self):
  u=self.live_machine(2,0x3f800000)
  for r,v in [(A.UC_ARM_REG_R0,2),(A.UC_ARM_REG_R1,0),(A.UC_ARM_REG_R2,RAM+0x9000)]:u.reg_write(r,v)
  u.emu_start(self.entries['m10v_aspect_af_bounds'],STOP,count=10000)
  self.assertEqual(u.reg_read(A.UC_ARM_REG_R0),1)
