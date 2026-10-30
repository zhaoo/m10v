"""Actual installed ScreenOrigin/ThumbnailOrigin across ratio changes.

Both callbacks take the stored ratio, unlike native viewport dimension helpers
which take a class. This checks complete coordinate writes and guards only;
it does not emulate LCD planes, DMA, composition or black-bar clearing.
"""
import os,struct,unittest
from pathlib import Path
from unicorn import UC_PROT_ALL
from scripts.analyze_gr3_border_iip import OriginalArm
ROOT=Path(__file__).resolve().parents[1]
OFFICIAL=ROOT/'builds/gr3-extension-validation/official-rtos.bin'
INSTALLED=Path(os.environ.get('M10V_DISPLAY_RTOS',ROOT/'builds/gr3-half-frame-r5-debug-final-20261030/final-rtos.bin'))
OUT=0x55200010

def fixture(installed):
 rom=OFFICIAL.read_bytes();p=OriginalArm(rom)
 if installed:
  code=INSTALLED.read_bytes();old=(len(rom)+4095)&~4095;new=(len(code)+4095)&~4095
  if new>old:p.u.mem_map(0x53000000+old,new-old)
  p.u.mem_protect(0x53000000,old,UC_PROT_ALL);p.u.mem_write(0x53000000,code)
 return p

class LiveDisplayOrigins(unittest.TestCase):
 def test_wide_native_origins_overwrite_both_coordinates_after_each_other_ratio(self):
  p=fixture(True);reference=fixture(False)
  for entry in(0x536a2f50,0x536a3008):
   for previous in(0,1,3,4,5,6,2):
    with self.subTest(entry=hex(entry),previous=previous):
     p.u.mem_write(OUT-8,b'\xa5'*20)
     p.call(entry,0,previous,OUT,OUT+2)
     p.call(entry,0,2,OUT,OUT+2)
     reference.u.mem_write(OUT-8,b'\xa5'*20);reference.call(entry,0,2,OUT,OUT+2)
     self.assertEqual(bytes(p.u.mem_read(OUT-8,20)),bytes(reference.u.mem_read(OUT-8,20)))
     self.assertEqual(struct.unpack('<2H',p.u.mem_read(OUT,4)),(0,38)if entry==0x536a2f50 else(0,16))
     self.assertFalse(p.assertions);self.assertFalse(reference.assertions)
 def test_stock_origin_callbacks_match_official_for_all_native_ratios(self):
  p=fixture(True);r=fixture(False)
  for entry in(0x536a2f50,0x536a3008):
   for ratio in(0,1,2,3):
    p.u.mem_write(OUT,b'\xa5'*4);r.u.mem_write(OUT,b'\xa5'*4)
    p.call(entry,0,ratio,OUT,OUT+2);r.call(entry,0,ratio,OUT,OUT+2)
    self.assertEqual(bytes(p.u.mem_read(OUT,4)),bytes(r.u.mem_read(OUT,4)),(hex(entry),ratio))
if __name__=='__main__':unittest.main()
