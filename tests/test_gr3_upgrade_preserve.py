"""Real linked ARM upgrade path; never touches camera or user files."""
import inspect,struct,tempfile,unittest,zlib
from pathlib import Path
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_PC,UC_ARM_REG_LR
from scripts.build_gr3_m10v_library import build
from tests import test_gr3_sd_camera as _sd

class UpgradePreserve(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.ready='preserve_existing' in inspect.signature(build).parameters
  if not cls.ready:return
  cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
  cls.manifest=build(Path(cls.tmp.name),sd_library=True,appended_slots=True,preserve_existing=True)
  cls.code=(Path(cls.tmp.name)/'m10v-library-arm.bin').read_bytes();cls.pack=b''
 def setUp(self):
  self.assertTrue(self.ready,'missing explicit preserve_existing build policy')
  _sd.SdCameraTests.setUp(self)
  self.tone=26;self.tone_sets=[]
  def model(u,pc,size,data):
   if pc==0x532bd6d4:value=0
   elif pc==0x532bd6b4:value=self.tone
   elif pc==0x532c26c0:self.tone=u.reg_read(UC_ARM_REG_R1);self.tone_sets.append(self.tone);value=0
   else:return
   u.reg_write(UC_ARM_REG_R0,value);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
  self.u.hook_add(UC_HOOK_CODE,model)
 w=_sd.SdCameraTests.w
 n=_sd.SdCameraTests.n
 string=_sd.SdCameraTests.string
 hook=_sd.SdCameraTests.hook
 call=_sd.SdCameraTests.call
 def state(self):
  s=bytearray(184);struct.pack_into('<IHHI',s,0,0x5630314d,5,184,77)
  for i,film in enumerate([33,34,35,36,37,38,39,40,41,42]):struct.pack_into('<H6B',s,12+8*i,film,0,0,0,3,5,2)
  s[92:96]=bytes([1,2,3,1]);struct.pack_into('<I',s,176,1)
  struct.pack_into('<I',s,180,zlib.crc32(s[:180]));return bytes(s)
 def test_valid_app_journal_survives_missing_changed_or_unreadable_seed_receipt(self):
  original=self.state()
  for receipt in [None,bytes(16),b'broken',struct.pack('<4I',0x31474643,123,~123&0xffffffff,0x31474643^123)]:
   with self.subTest(receipt=receipt):
    self.files={'M10V6A.bin':original};self.calls=[];self.tone_sets=[]
    if receipt is not None:self.files['M10VCFG.bin']=receipt
    before=dict(self.files)
    self.assertEqual(self.call('m10v_camera_library_reconcile_legacy_selection',0x5500e000),0)
    self.assertEqual(self.files,before);self.assertEqual(self.calls,[]);self.assertEqual(self.tone_sets,[])
    self.assertEqual(self.call('m10v_camera_library_load',0x5500a000),0)
    self.assertEqual(bytes(self.u.mem_read(0x5500a000,184)),original)
 def test_first_use_still_initializes_valid_current_journal(self):
  self.assertEqual(self.call('m10v_camera_library_reconcile_legacy_selection',0x5500e000),0)
  self.assertTrue(any(n.startswith('M10V6') for n in self.files))
  self.assertEqual(self.call('m10v_camera_library_load',0x5500a000),0)
  data=bytes(self.u.mem_read(0x5500a000,184));self.assertEqual(struct.unpack_from('<IHH',data),(0x5630314d,5,184))
  self.assertEqual(zlib.crc32(data[:180]),struct.unpack_from('<I',data,180)[0])
 def test_native_manifest_records_preserve_policy(self):
  self.assertEqual(self.manifest.get('preserve_existing'),True)
