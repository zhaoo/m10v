"""Execute official ImageTone decoding and album icon dispatch, without metadata stubs."""
import struct
import unittest
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm_const as A
from scripts.build_gr3_digital_hdf import official_rtos
from scripts.build_gr3_film_slot_extension import build_appended_slots


class PlaybackMetadataTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.rom=official_rtos()
  symbols={'m10v_camera_library_shooting_count':0x54180000}
  symbols.update({'m10v_tone_menu_'+n:0x54180000 for n in
   ('menu_name','menu_icon','index','adj_name','adj_icon','menu_matches','adj_matches','adj_select')})
  cls.code,cls.report=build_appended_slots(0x54100000,0x54000000,cls.rom,symbols)

 def fixture(self,patched):
  u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0x53000000,0x2000000)
  u.mem_write(0x53000000,self.rom);u.mem_write(0x54100000,self.code)
  u.mem_map(0x55000000,0x100000)
  if patched:
   for p in self.report['patches']:u.mem_write(p['address'],struct.pack('<I',p['replacement']))
  def services(m,a,n,d):
   if a==0x536b93d0:v=0  # original assertion logger only
   elif a==0x5320ad88:v=0x55004000
   elif a==0x5320b97c:v=0x55001000
   else:return
   m.reg_write(A.UC_ARM_REG_R0,v);m.reg_write(A.UC_ARM_REG_PC,m.reg_read(A.UC_ARM_REG_LR))
  u.hook_add(UC_HOOK_CODE,services)
  return u

 def call(self,u,entry,*args,end=0x550ff000):
  for r,v in zip((A.UC_ARM_REG_R0,A.UC_ARM_REG_R1,A.UC_ARM_REG_R2),args):u.reg_write(r,v)
  u.reg_write(A.UC_ARM_REG_SP,0x550f0000);u.reg_write(A.UC_ARM_REG_LR,0x550ff000)
  u.emu_start(entry,end,count=10000)
  self.assertEqual(u.reg_read(A.UC_ARM_REG_PC),end)
  return u.reg_read(A.UC_ARM_REG_R0)

 def parse(self,u,tone):
  u.mem_write(0x5500300c,struct.pack('<H',tone))
  self.call(u,0x535c24ec,0,0x5500118c,0x55003000)
  return struct.unpack('<I',u.mem_read(0x55001220,4))[0]

 def test_official_reader_clamps_private_tone_to_unknown(self):
  u=self.fixture(False)
  self.assertEqual(self.parse(u,0x10c),0)

 def test_real_reader_and_album_caller_handle_private_switches_and_stock(self):
  u=self.fixture(True)
  # Reuse the actual metadata owner across photo switches, including unsupported
  # and stock photos. No journal/current shooting slot is mapped or consulted.
  for tone in (*range(0x10c,0x116),0x100,0x115,0x10b,0x116,0,0xffff):
   tag=self.parse(u,tone)
   private=0x10c<=tone<=0x115
   self.assertEqual(tag,0x10000+tone-0x100 if private else tone-0xff if 0x100<=tone<=0x10b else 0)
   self.call(u,0x53179b7c,end=0x53179b88)
   icon=u.reg_read(A.UC_ARM_REG_R1)
   if private:self.assertEqual(icon,754)
   else:
    stock=self.fixture(False);self.parse(stock,tone)
    self.assertEqual(icon,self.call(stock,0x532b6eec))
   u.mem_write(0x55002000,b'\xa5')
   result=self.call(u,self.report['playback']['detail'],0x55001000,0x55002000)
   self.assertEqual(bool(result),private or 0x100<=tone<=0x10b)
   if private:self.assertEqual(bytes(u.mem_read(0x55002000,1)),b'\x0b')

 def test_stock_metadata_mapping_is_unchanged_and_private_survives_cold_owner(self):
  for tone in (*range(0x100,0x10c),0,0xff,0x116,0x8000,0xffff):
   stock=self.fixture(False);patched=self.fixture(True)
   self.assertEqual(self.parse(patched,tone),self.parse(stock,tone))
  for tone in range(0x10c,0x116):
   u=self.fixture(True)  # no state or slot history survives this fresh owner
   # The official reader also supports out-of-line EXIF SHORT values.
   u.mem_write(0x55003010,struct.pack('<I',0x55005000))
   u.mem_write(0x55005000,struct.pack('<H',tone))
   self.call(u,0x535c24ec,0,0x5500118c,0x55003000)
   self.call(u,0x53179b7c,end=0x53179b88)
   self.assertEqual(u.reg_read(A.UC_ARM_REG_R1),754)


if __name__=='__main__':unittest.main()
