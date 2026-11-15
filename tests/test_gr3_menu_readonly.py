"""Execute delivered view with all firmware ROM RX, actual bitmap resource lookup and heap lifecycle."""
import hashlib,json,os,struct,subprocess,tempfile,unittest
from pathlib import Path
from unicorn import UC_PROT_READ,UC_PROT_EXEC
from unicorn import arm_const as A
from tests.test_gr3_settings_view import SettingsViewTests
ROOT=Path(__file__).resolve().parents[1]
class MenuReadonlyTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  from scripts.build_gr3_m10v_library import build,capture_stock_rtos
  cls.tmp=tempfile.TemporaryDirectory(prefix='m10v-menu-readonly-');cls.addClassCleanup(cls.tmp.cleanup)
  tmp=Path(cls.tmp.name);original=tmp/'official-rtos.bin';original.write_bytes(capture_stock_rtos())
  previous=os.environ.get('M10V_GR3_ORIGINAL_RTOS')
  def restore_environment():
   if previous is None:os.environ.pop('M10V_GR3_ORIGINAL_RTOS',None)
   else:os.environ['M10V_GR3_ORIGINAL_RTOS']=previous
  cls.addClassCleanup(restore_environment);os.environ['M10V_GR3_ORIGINAL_RTOS']=str(original)
  SettingsViewTests.setUpClass();cls.addClassCleanup(SettingsViewTests.doClassCleanups)
  explicit=os.environ.get('M10V_MENU_CANDIDATE')
  cls.folder=Path(explicit) if explicit else tmp/'candidate'
  if not explicit:
   manifest=build(tmp/'runtime',sd_library=True)
   (cls.folder/'evidence').mkdir(parents=True)
   (cls.folder/'evidence/M10V-runtime-manifest.json').write_text(json.dumps(manifest))
   js="import{readFileSync,writeFileSync}from'node:fs';import{buildNativeLibrary}from'./node/gr3-m10v-native-build.mjs';const m=JSON.parse(readFileSync(process.argv[1]));const r=readFileSync(process.argv[2]);const {candidate}=buildNativeLibrary(readFileSync('bin/fwdc239b-gr3-official.bin'),r,m);writeFileSync(process.argv[3],candidate);"
   subprocess.run(['node','--input-type=module','-e',js,str(cls.folder/'evidence/M10V-runtime-manifest.json'),str(tmp/'runtime/m10v-library-arm.bin'),str(cls.folder/'fwdc239b.bin')],cwd=ROOT,check=True,capture_output=True)
  manifest_path=cls.folder/'M10V-runtime-manifest.json'
  if not manifest_path.is_file():manifest_path=cls.folder/'evidence/M10V-runtime-manifest.json'
  cls.manifest=json.loads(manifest_path.read_text())
  js="import{readFileSync}from'node:fs';import{decodeFrameMap}from'./node/gr3-frames.mjs';let b=readFileSync(process.argv[1]),d=decodeFrameMap(b,b.readUInt32LE(b.length-8)).decoded;process.stdout.write(d.subarray(0x10870,0x10870+d.readUInt32LE(0x1086c)));"
  cls.rom=subprocess.check_output(['node','--input-type=module','-e',js,str(cls.folder/'fwdc239b.bin')],cwd=ROOT)
 def fixture(self,fail=False):
  h=SettingsViewTests();u=h.machine(native_accessor=True,fail_cards=fail);u.mem_write(0x53000000,self.rom);u.mem_protect(0x53000000,0x2000000,UC_PROT_READ|UC_PROT_EXEC)
  h.heap=0x55800000;h.symbols=self.manifest['symbols'];owner=0x550a0000;p=owner+0x13bc;view=p+0x158
  u.mem_write(p,struct.pack('<I',self.manifest['settings_menu']['vtable']));u.mem_write(0x55063910,struct.pack('<I',1));u.mem_write(0x55063988,struct.pack('<I',owner))
  return h,u,view
 def call(self,u,address,*args):
  for i in range(4):u.reg_write(getattr(A,'UC_ARM_REG_R'+str(i)),args[i]if i<len(args)else 0)
  u.reg_write(A.UC_ARM_REG_SP,0x100f0000);u.reg_write(A.UC_ARM_REG_LR,0x10000000);u.emu_start(address,0x10000000,count=10000000)
  self.assertEqual(u.reg_read(A.UC_ARM_REG_PC),0x10000000);return u.reg_read(A.UC_ARM_REG_R0)
 def draw(self,h,u,view,screen=1):
  state=bytearray(216)
  for i in range(5):struct.pack_into('<H',state,12+i*8,33+i)
  struct.pack_into('<8I',state,184,screen,0,0,0,33,0,0,64)
  u.mem_write(0x10002000,bytes(state))
  h.call(u,'draw',view,0x10002000,0)
 def heap(self,u,view):
  return struct.unpack('<I',u.mem_read(view+55*4,4))[0]
 def test_repeated_film_view_entry_and_exit_never_write_rom_or_leak(self):
  h,u,view=self.fixture();before=hashlib.sha256(bytes(u.mem_read(0x53000000,len(self.rom)))).digest()
  cards=self.manifest['film_cards']
  for repeat in range(3):
   self.assertEqual(h.call(u,'create',view),0);self.draw(h,u,view)
   heap=self.heap(u,view)
   for i in range(5):
    w,ht,p=struct.unpack('<HHI',u.mem_read(heap+cards['descriptor_offset']+i*8,8))
    self.assertEqual((w,ht,p*4),(128,172,heap+i*128*172*4))
    self.assertEqual(self.call(u,0x53209fb8,0,749+i),128)
    self.assertEqual(self.call(u,0x53209fec,0,749+i),172)
   self.draw(h,u,view,2)
   self.assertEqual(self.call(u,0x53209fb8,0,857),448)
   self.assertEqual(self.call(u,0x53209fec,0,857),8)
   h.call(u,'destroy',view);self.assertFalse(h.live)
   self.assertEqual(self.call(u,0x53209fb8,0,749),40) # Safe immutable fallback after owner releases RAM.
  self.assertEqual(hashlib.sha256(bytes(u.mem_read(0x53000000,len(self.rom)))).digest(),before)
 def test_timestamp_view_never_allocates_card_metadata(self):
  h,u,view=self.fixture();h.call(u,'create',view);self.draw(h,u,view,3)
  self.assertEqual(self.heap(u,view),0);h.call(u,'destroy',view);self.assertFalse(h.live)

 def test_dynamic_directory_adapters_preserve_registers_stack_and_flags(self):
  h,u,view=self.fixture();h.call(u,'create',view);self.draw(h,u,view,2)
  heap=self.heap(u,view)
  registers=[getattr(A,'UC_ARM_REG_R'+str(i))for i in range(13)]+[A.UC_ARM_REG_LR,A.UC_ARM_REG_SP]
  for name,outreg,idreg,end in [('width',3,1,0x53209fd4),('height',3,1,0x5320a008),('draw',2,3,0x5320a80c)]:
   for icon in (671,749,753,857):
    for i,reg in enumerate(registers):u.reg_write(reg,0x12340000+i*256)
    u.reg_write(registers[idreg],icon);u.reg_write(A.UC_ARM_REG_SP,0x100f0000)
    flags=(u.reg_read(A.UC_ARM_REG_CPSR)&0x0fffffff)|0xa0000000;u.reg_write(A.UC_ARM_REG_CPSR,flags)
    expected=[u.reg_read(reg)for reg in registers];expected[outreg]=heap+self.manifest['film_cards']['directory_offset']-749*4 if icon>=749 else self.manifest['icons']['table']
    u.emu_start(self.manifest['film_cards']['directory_hooks'][name],end,count=100000)
    self.assertEqual(u.reg_read(A.UC_ARM_REG_PC),end)
    self.assertEqual([u.reg_read(reg)for reg in registers],expected)
    self.assertEqual(u.reg_read(A.UC_ARM_REG_CPSR)&0xf0000000,flags&0xf0000000)

 def test_large_card_oom_keeps_original_icons_and_tears_down_cleanly(self):
  h,u,view=self.fixture(fail=True);h.call(u,'create',view);self.draw(h,u,view,2)
  self.assertEqual(self.heap(u,view),0)
  self.assertEqual(self.call(u,0x53209fb8,0,749),40)
  h.call(u,'destroy',view);self.assertFalse(h.live)
