"""Original operating-time getter writes two output words and returns status.
Kernel lock/interrupt leaves are named boundaries; native stores execute ARM.
This reproduces the invalid output pointer behind the r8 last probe, without
claiming a camera exception PC or invoking a physical device.
"""
from pathlib import Path
import unittest
from scripts.analyze_gr3_border_iip import OriginalArm
class HalfClockNativeABI(unittest.TestCase):
 def fixture(self):
  p=OriginalArm(Path('builds/gr3-extension-validation/official-rtos.bin').read_bytes())
  p.words(0x557f14d4,0,0,0,0)
  p.words(0x557f25b8,0x89abcdef,0x12345678)
  p.boundaries={a:(lambda:0)for a in(0x5304fa88,0x53051360,0x530513e4,0x5304fa98)}
  return p
 def test_original_getter_writes_high_low_output_and_returns_zero_status(self):
  p=self.fixture();out=0x55200008;p.words(out-4,0xaaaa5555,0,0,0x5555aaaa)
  self.assertEqual(p.call(0x53067c24,out),0)
  self.assertEqual(p.read_words(out-4,4),[0xaaaa5555,0x12345678,0x89abcdef,0x5555aaaa])
 def test_old_scalar_call_would_write_through_invalid_r0(self):
  p=self.fixture()
  with self.assertRaisesRegex(AssertionError,'UC_ERR_WRITE_UNMAPPED.*PC=0x53067ca0'):p.call(0x53067c24,1)
