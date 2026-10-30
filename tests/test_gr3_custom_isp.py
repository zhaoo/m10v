"""Versioned SD custom ISP profile validation; old records remain readable."""
import ctypes, json, struct, subprocess, tempfile, unittest, zlib
from pathlib import Path

class CustomIspRecordTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
  lib=Path(cls.tmp.name)/'sd.dylib'
  subprocess.run(['clang','-shared','-fPIC','-O2','native/gr3/m10v_sd_library.c','-o',str(lib)],check=True,capture_output=True)
  cls.lib=ctypes.CDLL(str(lib));cls.lib.m10v_sd_record.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32]
  js="import{customFilmRecord}from'./node/gr3-sd-film-pack.mjs';process.stdout.write(customFilmRecord({name:'Warm',rgb:Buffer.alloc(6591,90)},79));"
  cls.legacy=subprocess.check_output(['node','--input-type=module','-e',js])
 def record(self):
  b=bytearray(self.legacy);payload=struct.pack('<18h',8192,0,0,0,8192,0,0,0,8192,512,0,0,0,512,0,0,0,512)
  payload+=struct.pack('<768H',*([round(i*16383/255) for i in range(256)]*3))
  b[6688:6704]=struct.pack('<4I',0x5053494d,1,1572,zlib.crc32(payload));b[6704:8276]=payload
  return self.reseal(b)
 def reseal(self,b):struct.pack_into('<I',b,12284,zlib.crc32(b[:12284]));return b
 def valid(self,b):return self.lib.m10v_sd_record(ctypes.create_string_buffer(bytes(b)),len(b),79)
 def test_legacy_record_stays_readable(self):self.assertEqual(self.valid(self.legacy),79)
 def test_main_baseline_custom_renderer_stays_readable_after_upgrade(self):
  b=bytearray(self.legacy);contract=json.loads(Path('node/gr3-sd-pre-instax-contract.json').read_text())
  b[8448:8480]=bytes.fromhex(contract['renderer'])
  self.assertEqual(self.valid(self.reseal(b)),79)
  b[8448:8480]=bytes(32);self.assertEqual(self.valid(self.reseal(b)),0)
 def test_versioned_monotonic_profile_is_readable(self):self.assertEqual(self.valid(self.record()),79)
 def test_bad_payload_crc_and_unknown_version_rejected(self):
  for offset,value in ((6704,1),(6692,2),(8276,1)):
   b=self.record();b[offset]=value;self.assertEqual(self.valid(self.reseal(b)),0)
 def test_repaired_crc_does_not_allow_curve_overflow_or_descent(self):
  for value in (65535,16383):
   b=self.record();struct.pack_into('<H',b,6740+12,value)
   struct.pack_into('<I',b,6700,zlib.crc32(b[6704:8276]));self.assertEqual(self.valid(self.reseal(b)),0)
 def test_repaired_crc_does_not_allow_non_neutral_matrix_rows(self):
  b=self.record();struct.pack_into('<h',b,6704,8191)
  struct.pack_into('<I',b,6700,zlib.crc32(b[6704:8276]));self.assertEqual(self.valid(self.reseal(b)),0)

if __name__=='__main__':unittest.main()

class CustomIspCacheTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  from scripts.build_gr3_m10v_library import FLAGS,link_object
  cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup);obj=Path(cls.tmp.name)/'camera.o'
  subprocess.run(['/opt/homebrew/opt/llvm/bin/clang',*FLAGS,'-DM10V_LIVE_COLOR=1','-DM10V_SD_LIBRARY=1','-c','native/gr3/m10v_library_camera.c','-o',str(obj)],check=True,capture_output=True)
  names=sorted(line.split()[-1] for line in subprocess.check_output(['/opt/homebrew/opt/llvm/bin/llvm-nm','-u',str(obj)],text=True).splitlines() if line.strip())
  cls.externals={n:0x55001000+4*i for i,n in enumerate(names)}
  cls.code,cls.symbols=link_object(obj.read_bytes(),0x54100000,cls.externals,'m10v_camera_library_')
 def setUp(self):
  from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
  from unicorn import arm_const as A
  self.A=A;self.u=u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0x53000000,0x2000000);u.mem_map(0x55000000,0x200000)
  u.mem_write(0x54100000,self.code);u.mem_write(0x55063910,struct.pack('<I',1));u.mem_write(0x55063988,struct.pack('<I',0x55010000))
  self.reads=0;self.allocs=0;self.freed=[];self.reenter=False;self.record=bytearray(12288)
  struct.pack_into('<4I',self.record,6688,0x5053494d,1,1572,0)
  struct.pack_into('<18h',self.record,6704,8192,0,0,0,8192,0,0,0,8192,512,0,0,0,512,0,0,0,512)
  struct.pack_into('<768H',self.record,6740,*([i*32 for i in range(256)]*3))
  reverse={v:k for k,v in self.externals.items()}
  def leaf(uc,a,n,d):
   r=[uc.reg_read(getattr(A,'UC_ARM_REG_R'+str(i))) for i in range(4)];name=reverse.get(a)
   if name=='m10v_library_valid':v=1
   elif name=='m10v_sd_camera_custom_record':
    self.reads+=1;uc.mem_write(r[2],bytes(self.record));v=1
    if self.reenter:uc.mem_write(0x55012140,bytes(4)) # reentered constructor, same address, version0
   elif name=='m10v_sd_u32':v=struct.unpack('<I',uc.mem_read(r[0],4))[0]
   elif a==0x536af2a8:self.allocs+=1;v=0x55080000 if self.allocs==1 else 0x55100000
   elif a==0x536af2e4:self.freed.append(r[0]);v=0
   elif name:v=0
   else:return
   uc.reg_write(A.UC_ARM_REG_R0,v);uc.reg_write(A.UC_ARM_REG_PC,uc.reg_read(A.UC_ARM_REG_LR))
  u.hook_add(UC_HOOK_CODE,leaf);self.call('preview_init',0x55010000)
  self.state=bytearray(184);struct.pack_into('<H',self.state,12,79);self.state[102]=21
  u.mem_write(0x55005000,bytes(self.state))
 def call(self,name,*args):
  u=self.u;A=self.A
  for i,v in enumerate(args):u.reg_write(getattr(A,'UC_ARM_REG_R'+str(i)),v)
  u.reg_write(A.UC_ARM_REG_SP,0x551ff000);u.reg_write(A.UC_ARM_REG_LR,0x551ff800)
  u.emu_start(self.symbols['m10v_camera_library_'+name],0x551ff800,count=300000)
  self.assertEqual(u.reg_read(A.UC_ARM_REG_PC),0x551ff800);return u.reg_read(A.UC_ARM_REG_R0)
 def test_ui_publication_caches_profile_and_frame_reads_never_touch_storage(self):
  self.assertEqual(self.call('mutation_begin'),1);self.call('mutation_end',0x55005000)
  self.assertEqual(self.reads,1);allocs=self.allocs
  for _ in range(3):
   self.assertEqual(self.call('custom_profile',0x55005000,0,0x55007000),1)
   self.assertEqual(struct.unpack('<H',self.u.mem_read(0x55007000+36+510,2))[0],8160)
  self.assertEqual(self.reads,1);self.assertEqual(self.allocs,allocs)
  self.assertEqual(self.call('mutation_begin'),1)
  self.assertEqual(self.call('custom_profile',0x55005000,0,0x55007000),0)
  self.call('mutation_end',0x55005000);self.assertEqual(self.reads,1)
  self.call('preview_clear',0x55010000)
  self.assertEqual(self.call('custom_profile',0x55005000,0,0x55007000),0)
  # Profile storage belongs to the TopMenu allocation, never a separately
  # freed object that an in-flight LiveView copy could still dereference.
  self.assertEqual(len(self.freed),1)
 def test_reentrant_storage_reinitialization_never_publishes_stale_owner(self):
  self.reenter=True;self.call('mutation_begin');self.call('mutation_end',0x55005000)
  self.assertEqual(struct.unpack('<I',self.u.mem_read(0x55012140,4))[0],0)
  self.assertEqual(self.call('custom_profile',0x55005000,0,0x55007000),0)
  self.assertEqual(len(self.freed),1)

class CustomIspResidualTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup);out=Path(cls.tmp.name)/'render.dylib'
  files=['m10v_library.c','halation_core.c','film_5207.c','film_harman.c','film_curated.c','film_newstocks.c','film_style_filters_0.c','film_style_filters_1.c','film_d76_0.c','film_d76_1.c']
  subprocess.run(['clang','-shared','-fPIC','-O2',*['native/gr3/'+f for f in files],'-o',str(out)],check=True,capture_output=True)
  cls.lib=ctypes.CDLL(str(out))
 def test_completed_custom_color_is_not_applied_again_in_stamp_residual(self):
  from tests.test_gr3_m10v_library import Image
  state=ctypes.create_string_buffer(184);self.lib.m10v_library_init(state)
  b=bytearray(state.raw);struct.pack_into('<H',b,12,79);b[102]=21;struct.pack_into('<I',b,176,1)
  struct.pack_into('<I',b,180,zlib.crc32(b[:180]));state=ctypes.create_string_buffer(bytes(b))
  self.assertEqual(self.lib.m10v_library_valid(state),1)
  y=(ctypes.c_uint8*64)(*([125]*64));c=(ctypes.c_uint8*64)(*([128]*64));image=Image(y,c,64,64,8,8,8)
  lut=ctypes.create_string_buffer(bytes(6591))
  # A tiny stamp is skipped, leaving ISP color unchanged; old code applied
  # the raw all-black LUT despite authentic native completion.
  result=self.lib.m10v_library_render_custom(ctypes.byref(image),state,0,None,0,None,0,1,lut,b'Warm')
  self.assertEqual(result,0);self.assertEqual(bytes(y),bytes([125]*64));self.assertEqual(bytes(c),bytes([128]*64))
