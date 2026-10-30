"""Execute official ImageTone decoding and album icon dispatch, without metadata stubs."""
import struct
import unittest
import tempfile
import zlib
from pathlib import Path
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm_const as A
from scripts.build_gr3_digital_hdf import official_rtos
from scripts.build_gr3_film_slot_extension import build_appended_slots
from scripts.build_gr3_m10v_library import build


class PlaybackMetadataTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.rom=official_rtos()
  cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
  cls.manifest=build(cls.tmp.name,sd_library=True,appended_slots=True,debug_mode=True,lifecycle_trace=True,recipe_snapshot=True)
  cls.code=(Path(cls.tmp.name)/'m10v-library-arm.bin').read_bytes()
  cls.report=cls.manifest['appended_slots']

 def fixture(self,patched):
  u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0x53000000,0x2000000)
  u.reg_write(A.UC_ARM_REG_C1_C0_2,0xf00000);u.reg_write(A.UC_ARM_REG_FPEXC,0x40000000)
  u.mem_write(0x53000000,self.rom);u.mem_write(self.manifest['base'],self.code)
  u.mem_map(0x55000000,0x100000);u.mem_map(0x55300000,0x100000)
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
  u.emu_start(entry,end,count=1000000)
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
   if private:self.assertEqual(icon,876)
   else:
    stock=self.fixture(False);self.parse(stock,tone)
    self.assertEqual(icon,self.call(stock,0x532b6eec))
   u.mem_write(0x55002000,b'\xa5')
   result=self.call(u,self.report['playback']['detail'],0x55001000,0x55002000)
   self.assertEqual(bool(result),private or 0x100<=tone<=0x10b)
   if private:self.assertEqual(bytes(u.mem_read(0x55002000,1)),b'\x0b')

 def test_stock_metadata_mapping_is_unchanged_and_private_survives_cold_owner(self):
  for tone in (*range(0x100,0x10c),0,0xff,0x116,0xf000,0xffff):
   stock=self.fixture(False);patched=self.fixture(True)
   self.assertEqual(self.parse(patched,tone),self.parse(stock,tone))
  for tone in range(0x10c,0x116):
   u=self.fixture(True)  # no state or slot history survives this fresh owner
   # The official reader also supports out-of-line EXIF SHORT values.
   u.mem_write(0x55003010,struct.pack('<I',0x55005000))
   u.mem_write(0x55005000,struct.pack('<H',tone))
   self.call(u,0x535c24ec,0,0x5500118c,0x55003000)
   self.call(u,0x53179b7c,end=0x53179b88)
   self.assertEqual(u.reg_read(A.UC_ARM_REG_R1),876)

 def test_exact_builtin_and_custom_identity_is_from_the_recorded_short(self):
  u=self.fixture(True)
  for code,icon in ((0x1000+33,703),(0x1000+289,755),(0x1000+314,871),(0x2000,754),(0xe0c5,754),(0x10c,876),(0,0)):
   with self.subTest(code=code):
    self.parse(u,code)
    self.call(u,0x53179b7c,end=0x53179b88)
    self.assertEqual(u.reg_read(A.UC_ARM_REG_R1),icon)

 def test_pool_membership_lease_and_clear_reject_stale_or_foreign_identity(self):
  u=self.fixture(True);si=0x55010000;manager=0x550a0000;tail=si+0x74270
  u.mem_write(0x55345328,struct.pack('<I',manager))
  u.mem_write(manager+0x20,struct.pack('<I',0x74280));u.mem_write(manager+0x88,struct.pack('<I',si))
  code=0x1000+33
  u.mem_write(tail,struct.pack('<4I',0x31444946,3,code,(~code^3)&0xffffffff))
  entry=self.manifest['symbols']['m10v_isp_frame_identity_code']
  self.assertEqual(self.call(u,entry,si),code)
  self.assertEqual(self.call(u,entry,0x55009000),0)
  self.assertEqual(self.call(u,entry,0x55100000),0) # Foreign SI/tail is unmapped.
  u.mem_write(manager+0x24,b'\1');self.assertEqual(self.call(u,entry,si),0)
  u.mem_write(manager+0x24,b'\0')
  self.call(u,self.manifest['symbols']['m10v_isp_frame_identity_clear'],si)
  self.assertEqual(self.call(u,entry,si),0)
  self.assertEqual(struct.unpack('<I',u.mem_read(tail+4,4))[0],4)
  for name,end in (('checkout',0x53523e04),('return',0x53523a6c)):
   u.mem_write(manager+0x24,b'\0')
   u.mem_write(tail,struct.pack('<4I',0x31444946,4,code,(~code^4)&0xffffffff))
   u.reg_write(A.UC_ARM_REG_R6,si);u.reg_write(A.UC_ARM_REG_R3,manager)
   flags=(u.reg_read(A.UC_ARM_REG_CPSR)&0x0fffffff)|0xa0000000;u.reg_write(A.UC_ARM_REG_CPSR,flags)
   self.call(u,self.report['playback']['identity_hooks'][name],manager,manager if name=='checkout' else si,0 if name=='checkout' else 1,end=end)
   self.assertEqual(u.reg_read(A.UC_ARM_REG_CPSR)&0xf0000000,0xa0000000)
   self.assertEqual(struct.unpack('<I',u.mem_read(tail,4))[0],0)
  u.mem_write(manager+0x24,b'\0')
  # Original full-SI copy only moves0x74270 stock bytes. Its adapter must
  # invalidate destination identity even though the appended tail is untouched.
  u.mem_write(tail,struct.pack('<4I',0x31444946,4,code,(~code^4)&0xffffffff))
  self.call(u,0x53510830,si,0x55010000,0x74270,end=0x53510834)
  self.assertEqual(self.call(u,entry,si),0)

 def test_producer_freezes_film_before_writer_and_selection_changes(self):
  u=self.fixture(True);si=0x55010000;manager=0x550a0000;recipe=0x550b0000;owner=0x550c0000;state=0x55009000
  u.mem_write(0x55345328,struct.pack('<I',manager))
  u.mem_write(manager+0x20,struct.pack('<I',0x74280));u.mem_write(manager+0x88,struct.pack('<I',si))
  self.call(u,self.manifest['symbols']['m10v_library_init'],state)
  data=bytearray(u.mem_read(state,184));struct.pack_into('<H',data,12,33);struct.pack_into('<H',data,44,38);struct.pack_into('<I',data,180,zlib.crc32(data[:180]))
  u.mem_write(0x55063910,struct.pack('<I',1));u.mem_write(0x55063988,struct.pack('<I',owner))
  u.mem_write(owner+0x213c,struct.pack('<II',0x3856504d,2));u.mem_write(owner+0x2144,bytes(data))
  u.mem_write(recipe,struct.pack('<I',0x53d0fc90));u.mem_write(recipe+0x4778,struct.pack('<I',0x31545653))
  u.mem_write(recipe+0x44c8,struct.pack('<I',si));u.mem_write(si+0x77c,b'\x19')
  producer=self.manifest['symbols']['m10v_isp_frame_recipe_producer']
  self.assertEqual(self.call(u,producer,recipe),1)
  struct.pack_into('<H',data,12,34);struct.pack_into('<I',data,180,zlib.crc32(data[:180]));u.mem_write(owner+0x2144,bytes(data))
  self.assertEqual(self.call(u,producer,recipe),1)
  recorded=[]
  def sink(m,a,n,d):
   if a==0x535d02c8:
    recorded.append(m.reg_read(A.UC_ARM_REG_R2));m.reg_write(A.UC_ARM_REG_PC,m.reg_read(A.UC_ARM_REG_LR))
  u.hook_add(UC_HOOK_CODE,sink)
  for caller in (0x53608080,0x5361c0cc):
   self.call(u,caller,0,0x55003000,si,end=caller+4)
  self.assertEqual(recorded,[0x1000+33]*2)
  self.parse(u,recorded[0]);self.call(u,0x53179b7c,end=0x53179b88)
  self.assertEqual(u.reg_read(A.UC_ARM_REG_R1),703)
  self.assertEqual(self.call(u,self.report['playback']['detail'],0x55001000,0x55002000),1)
  self.assertEqual(bytes(u.mem_read(0x55002000,1)),b'\x0b')
  # The full valid immutable-bank boundary survives in the photograph's code.
  struct.pack_into('<H',data,12,288);data[102]=255;struct.pack_into('<I',data,180,zlib.crc32(data[:180]))
  u.mem_write(owner+0x2144,bytes(data));u.mem_write(recipe+0x4a08,bytes(1796))
  self.assertEqual(self.call(u,producer,recipe),1)
  self.call(u,0x53608080,0,0x55003000,si,end=0x53608084)
  self.assertEqual(recorded[-1],0xe0c5)


if __name__=='__main__':unittest.main()
