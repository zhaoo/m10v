"""GR III UI contracts; execute target ARM and check official hook preimages."""
import json, struct, tempfile, unittest
from pathlib import Path
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm_const as A
from scripts.build_gr3_m10v_library import build
from scripts.build_gr3_digital_hdf import official_rtos

class UiPolishTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
  cls.m=build(cls.tmp.name,sd_library=True,live_color=True,appended_slots=True,universal_halation=True,native_color=True,native_grain=True,recipe_snapshot=True,lifecycle_trace=True,hdf_enabled=True)
  cls.b=(Path(cls.tmp.name)/'m10v-library-arm.bin').read_bytes();cls.rom=official_rtos()
 def test_halo_caption_has_bounded_mode_labels(self):
  texts=self.m['resources']['texts']
  self.assertEqual(texts[1137-786],'光晕 0关 1溢出 2拉丝')
 def test_halo_rail_executes_numeric_values_in_the_native_box(self):
  for profile,value in ((6,'0'),(4,'1'),(5,'2')):
   u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0x53000000,0x2000000);u.mem_write(self.m['base'],self.b);u.mem_map(0x55000000,0x100000)
   ui=0x55004000;u.mem_write(ui+0x198,bytes([25,0,12,0,0,0,0,0]));u.mem_write(ui+0x194,struct.pack('<I',0x55005000))
   state=bytearray(184);struct.pack_into('<H',state,12,33);state[19]=profile
   calls=[]
   def service(m,a,n,d):
    if a==self.m['symbols']['m10v_camera_library_load']:m.mem_write(m.reg_read(A.UC_ARM_REG_R0),bytes(state));v=0
    elif a==self.m['symbols']['m10v_library_valid']:v=1
    elif a==0x53394758:v=0x55006000
    elif a==0x5339e2f8:
     calls.append((m.reg_read(A.UC_ARM_REG_R1),bytes(m.mem_read(m.reg_read(A.UC_ARM_REG_R2),4)).split(b'\0')[0].decode()));v=0
    else:return
    m.reg_write(A.UC_ARM_REG_R0,v);m.reg_write(A.UC_ARM_REG_PC,m.reg_read(A.UC_ARM_REG_LR))
   u.hook_add(UC_HOOK_CODE,service)
   for reg,v in ((A.UC_ARM_REG_R0,3),(A.UC_ARM_REG_R1,ui),(A.UC_ARM_REG_R2,4<<16),(A.UC_ARM_REG_SP,0x550f0000),(A.UC_ARM_REG_LR,0x550ff000)):u.reg_write(reg,v)
   u.emu_start(self.m['symbols']['m10v_detail_control'],0x550ff000,count=10000)
   self.assertEqual(calls,[(484,value)])
 def test_root_groups_preserve_stock_rows_and_have_no_name_sibling(self):
  p=self.m['hdf_menu']['patches']
  routes={r['address']:r['replacement'] for r in p}
  self.assertEqual(routes[0x53b36adc]>>24,33)
  self.assertEqual([routes[0x53b36c88+i*4] for i in range(3)],[0x0200f100,0x0200f101,0x0200f102])
 def test_effects_hdf_cancel_save_and_return_to_group(self):
  from tests.test_gr3_hdf_menu import HdfMenuTests
  h=HdfMenuTests();h.m=self.m;h.b=self.b;h.rom=self.rom;h.setUp()
  h.page=h.owner+self.m['hdf_menu']['owner_offset']
  self.assertEqual(h.call('m10v_hdf_menu_ready',h.page,0),1)
  h.call('m10v_hdf_menu_enter',h.page,0,0)
  self.assertIn(1140,[i for _,i in h.captions]);self.assertIn(1141,[i for _,i in h.captions])
  h.key(0xd8);h.key(0xcf);h.key(0xda)
  self.assertEqual(h.writes,[]);self.assertEqual(h.closed,[]);self.assertEqual(h.get(h.page+0x180),0)
  h.key(0xd8);h.key(0xcf);h.key(0xd8)
  self.assertEqual(len(h.writes),1);self.assertEqual(h.closed,[])
  h.key(0xda);self.assertEqual(h.closed,[h.page])
 def test_playback_only_recognizes_recorded_private_tones_and_keeps_stock(self):
  hooks=self.m['appended_slots']['playback']
  from scripts.build_gr3_menu_patches import branch
  for address,expected,name in [(0x53179b7c,0xeb04f4da,'icon'),(0x532b7cfc,0xebfff1ee,'detail')]:
   patch=next(p for p in self.m['appended_slots']['patches'] if p['address']==address)
   self.assertEqual(struct.unpack_from('<I',self.rom,address-0x53000000)[0],expected)
   self.assertEqual(patch['replacement'],branch(address,hooks[name],True))
  for native in (0,447):
   for tag in (*range(0x1000c,0x10016),0,1,12,0x1000b,0x10016,0x18000):
    u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0x53000000,0x2000000);u.mem_write(0x53000000,self.rom);u.mem_write(self.m['base'],self.b);u.mem_map(0x55000000,0x100000)
    u.mem_write(0x55001220,struct.pack('<I',tag));u.mem_write(0x55002000,b'\xa5');u.reg_write(A.UC_ARM_REG_R0,0x55001000);u.reg_write(A.UC_ARM_REG_R1,0x55002000)
    def services(m,a,n,d):
     if a==0x532b6eec:v=native
     elif a==0x532b44bc:v=int(bool(native))
     elif a==0x5320ad88:v=0x55003000
     elif a==0x5320b97c:v=0x55001000
     else:return
     m.reg_write(A.UC_ARM_REG_R0,v);m.reg_write(A.UC_ARM_REG_PC,m.reg_read(A.UC_ARM_REG_LR))
    u.hook_add(UC_HOOK_CODE,services)
    private=0x1000c<=tag<=0x10015
    for name in ('icon','detail'):
     u.mem_write(0x55002000,b'\xa5');u.reg_write(A.UC_ARM_REG_R0,0x55001000);u.reg_write(A.UC_ARM_REG_R1,0x55002000)
     u.reg_write(A.UC_ARM_REG_SP,0x550f0000);u.reg_write(A.UC_ARM_REG_LR,0x550ff000)
     u.emu_start(hooks[name],0x550ff000,count=10000)
     self.assertEqual(u.reg_read(A.UC_ARM_REG_PC),0x550ff000)
     self.assertEqual(u.reg_read(A.UC_ARM_REG_SP),0x550f0000)
     self.assertEqual(u.reg_read(A.UC_ARM_REG_R0), (native or (876 if private else 0)) if name=='icon' else int(bool(native) or private))
     self.assertEqual(bytes(u.mem_read(0x55002000,1)),b'\x0b' if name=='detail' and not native and private else b'\xa5')

 def test_real_stock_metadata_icon_getter_preserves_factory_and_decodes_private(self):
  for tag in (*range(1,13),*range(0x1000c,0x10016),0,0x18000):
   u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0x53000000,0x2000000);u.mem_write(0x53000000,self.rom);u.mem_write(self.m['base'],self.b);u.mem_map(0x55000000,0x100000)
   u.mem_write(0x55001220,struct.pack('<I',tag))
   def service(m,a,n,d):
    if a==0x5320ad88:v=0x55003000
    elif a==0x5320b97c:v=0x55001000
    elif a==0x535be018:self.assertEqual(m.reg_read(A.UC_ARM_REG_R1),0x25);v=tag
    else:return
    m.reg_write(A.UC_ARM_REG_R0,v);m.reg_write(A.UC_ARM_REG_PC,m.reg_read(A.UC_ARM_REG_LR))
   u.hook_add(UC_HOOK_CODE,service)
   results=[]
   for entry in (0x532b6eec,self.m['appended_slots']['playback']['icon']):
    u.reg_write(A.UC_ARM_REG_SP,0x550f0000);u.reg_write(A.UC_ARM_REG_LR,0x550ff000)
    u.emu_start(entry,0x550ff000,count=10000)
    self.assertEqual(u.reg_read(A.UC_ARM_REG_PC),0x550ff000)
    results.append(u.reg_read(A.UC_ARM_REG_R0))
   self.assertEqual(results[1],876 if 0x1000c<=tag<=0x10015 else results[0])
