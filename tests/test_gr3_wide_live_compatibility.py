"""GR III normal-still wide preview uses full native backing plus an LCD mask.

The capture ratio remains raw2. Native movie/forced-wide consumers retainclass1.
No camera pixels, display DMA, cache coherency or hardware timing is emulated.
"""
import struct,unittest
from unicorn import UC_HOOK_CODE,arm_const as A
from tests import test_gr3_aspect as support
RAM,STOP=support.RAM,support.STOP
class WideLiveCompatibility(unittest.TestCase):
 setUpClass=classmethod(support.AspectTests.setUpClass.__func__)
 machine=support.AspectTests.machine
 call=support.AspectTests.call
 live_machine=support.AspectTests.live_machine
 def fixture(self,kind=0,override=0,ratio=2):
  u=self.machine();u.mem_write(RAM+0x100,struct.pack('<I',RAM+0x200));u.mem_write(RAM+0x500+0x6c2,b'\1')
  results={0x53525d5c:RAM+0x100,0x5354a778:ratio,0x53549958:kind,0x53654150:RAM+0x500,0x53654220:override}
  def services(m,a,n,d):
   if a in results:m.reg_write(A.UC_ARM_REG_R0,results[a]);m.reg_write(A.UC_ARM_REG_PC,m.reg_read(A.UC_ARM_REG_LR))
  u.hook_add(UC_HOOK_CODE,services);return u
 def test_actual_daily_mapper_changes_only_normal_still_wide(self):
  for kind in(0,1):
   for override in(0,1):
    for raw,stockclass in((0,0),(1,2),(2,1),(3,3),(4,4),(5,0),(6,0),(255,0)):
     with self.subTest(kind=kind,override=override,raw=raw):
      u=self.fixture(kind,override,raw);profile=RAM+0x6000;u.mem_write(profile+4,b'\xa5')
      u.reg_write(A.UC_ARM_REG_R0,profile);u.reg_write(A.UC_ARM_REG_R1,1);u.emu_start(0x53669424,STOP,count=50000)
      expected=1 if override else 0 if raw==2 and kind!=1 else stockclass
      self.assertEqual(u.reg_read(A.UC_ARM_REG_R0),expected);self.assertEqual(bytes(u.mem_read(profile+4,1)),bytes([expected]))
 def test_wide_mask_is_opaque_and_matches_even_projection_of_saved_photo(self):
  for width,height,margin in((720,480,38),(360,240,19)):
   u=self.live_machine(2,0x3f800000);view=RAM+0x2000;surface=RAM+0x3000;u.mem_write(view+0x9e,b'\1')
   for at in(0x30,0x64):u.mem_write(view+at,struct.pack('<4I',0,0,width,height))
   rectangles=[];results={0x5320804c:RAM+0x400,0x532081ec:RAM+0x500,0x540b88b4:0}
   def drawing(m,a,n,d):
    if a not in results:return
    if a==0x540b88b4:rectangles.append(struct.unpack('<5I',m.mem_read(m.reg_read(A.UC_ARM_REG_SP),20)))
    m.reg_write(A.UC_ARM_REG_R0,results[a]);m.reg_write(A.UC_ARM_REG_PC,m.reg_read(A.UC_ARM_REG_LR))
   u.hook_add(UC_HOOK_CODE,drawing);u.reg_write(A.UC_ARM_REG_R0,view);u.reg_write(A.UC_ARM_REG_R1,surface);u.emu_start(self.entries['m10v_aspect_draw'],STOP,count=10000)
   self.assertEqual(rectangles,[(0,0,width,margin,1),(0,height-margin,width,margin,1)])
   self.assertEqual(height-2*margin,(height*3376//4000//2)*2)
 def test_movie_and_forced_override_do_not_enter_wide_mask(self):
  for kind,override in((1,0),(0,1)):
   u=self.fixture(kind,override);u.emu_start(self.entries['m10v_aspect_mask_active'],STOP,count=10000);self.assertEqual(u.reg_read(A.UC_ARM_REG_R0),0)
 def test_production_overlay_installs_checked_class_bridges_only_for_gr3(self):
  import json
  from scripts import gr3_aspect_overlay as overlay
  template=json.loads((support.ROOT/'.runtime/grlife-current/reconstruction/firmware_store/templates/urban160-native.json').read_text())
  source=bytearray((support.ROOT/'builds/gr3-extension-validation/official-rtos.bin').read_bytes())
  blob=bytes.fromhex(template['program_hex']);at=template['base_va']-support.BASE
  source.extend(bytes(max(0,at+len(blob)-len(source))));source[at:at+len(blob)]=blob
  # Retained component installs this native callback table entry separately
  # from its code blob; the overlay strictly verifies that real preimage.
  struct.pack_into('<I',source,0x53b2fa48-support.BASE,0x540b7bf4)
  for half in(False,True):
   result,symbols=overlay.apply_overlay(source,half)
   for site,(name,expected)in overlay.NATIVE_CLASS_HOOKS.items():
    actual=struct.unpack_from('<I',result,site-support.BASE)[0]
    self.assertEqual(actual,overlay.branch(site,symbols['m10v_aspect_'+name])if half else expected)
   if not half:self.assertNotIn('m10v_aspect_mapper_class',symbols)
  for site in overlay.NATIVE_CLASS_HOOKS:
   damaged=bytearray(source);struct.pack_into('<I',damaged,site-support.BASE,0xe1a00000)
   with self.assertRaisesRegex(ValueError,'crop preimage differs'):overlay.apply_overlay(damaged,True)
 def test_saved_wide_jpeg_dimensions_remain_native_at_every_quality(self):
  for quality,expected in enumerate(((6000,3376),(4800,2704),(3360,1888),(1920,1080))):
   u=self.machine();u.reg_write(A.UC_ARM_REG_C1_C0_2,0xf00000);u.reg_write(A.UC_ARM_REG_FPEXC,0x40000000);u.mem_write(RAM,b'\xa5'*4);u.mem_write(RAM+0xf0000,struct.pack('<I',RAM+2))
   for reg,val in((A.UC_ARM_REG_S0,0x3f800000),(A.UC_ARM_REG_R1,quality),(A.UC_ARM_REG_R2,2),(A.UC_ARM_REG_R3,RAM)):u.reg_write(reg,val)
   u.emu_start(0x536a2a30,STOP,count=30000);self.assertEqual(struct.unpack('<2H',u.mem_read(RAM,4)),expected)
if __name__=='__main__':unittest.main()
