"""Production RTOS journal commit/readback; only the stock file API is doubled."""
import os,struct,subprocess,tempfile,unittest,zlib
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC
ROOT=Path(__file__).resolve().parents[1]
class NativeStore(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup);d=Path(cls.tmp.name);objects=[]
  for i,name in enumerate(['native/gr3/m10v_library_camera.c','native/gr3/m10v_library.c','native/gr3/m10v_sd_library.c','native/companion/runtime.c']):
   obj=d/f'{i}.o';r=subprocess.run(['clang','--target=armv7-none-eabi','-mcpu=cortex-a9','-marm','-mfloat-abi=soft','-Os','-ffreestanding','-fno-builtin','-ffunction-sections','-fdata-sections','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-DM10V_COMPANION_ENABLED=1','-DM10V_LIVE_COLOR=1','-DM10V_APPENDED_SLOTS=1','-DM10V_SD_LIBRARY=1','-c',str(ROOT/name),'-o',str(obj)],capture_output=True,text=True)
   if r.returncode:raise AssertionError(r.stderr)
   objects.append(obj)
  out=d/'store.elf';r=subprocess.run(['ld.lld','-m','armelf_linux_eabi','--gc-sections','--entry=m10v_camera_library_commit_snapshot','-Ttext=0x540c0000','--defsym=m10v_sd_camera_custom_record=0x54010000','--defsym=m10v_companion_ui_storage_enter=0x54010040','--defsym=m10v_companion_ui_storage_leave=0x54010080',*[str(p) for p in objects],'-o',str(out)],capture_output=True,text=True)
  if r.returncode:raise AssertionError(r.stderr)
  cls.elf=out.read_bytes();nm=subprocess.check_output(['/opt/homebrew/opt/llvm/bin/llvm-nm','--defined-only',str(out)],text=True);cls.symbols={line.split()[2]:int(line.split()[0],16) for line in nm.splitlines() if len(line.split())==3}
 def test_real_store_single_write_full_readback_and_failure_paths(self):
  self.assertIn('m10v_camera_library_commit_snapshot',self.symbols,'native single-commit API is missing')
  for fault in [None,'crc','sequence','readback','write','unlocked']:
   with self.subTest(fault=fault):self.run_case(fault)
 def run_case(self,fault):
  u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0x53000000,0x3000000);u.mem_map(0x56000000,0x20000)
  b=self.elf;off=struct.unpack_from('<I',b,28)[0];size,count=struct.unpack_from('<HH',b,42)
  for i in range(count):
   kind,at,va,_,n,_,_,_=struct.unpack_from('<8I',b,off+i*size)
   if kind==1:
    if va<0x53000000:u.mem_map(va&~4095,((va%4096+n+4095)//4096)*4096)
    u.mem_write(va,b[at:at+n])
  def put(at,*values):u.mem_write(at,struct.pack('<'+'I'*len(values),*values))
  owner=0x55860000;put(0x55063910,1);put(0x55063988,owner);put(owner+0x213c,0x3856504d,2 if fault=='unlocked' else 3)
  put(0x558e0008,0x558e0100);put(0x558e0100,0x558e0200);u.mem_write(0x558e0220,b'\x01')
  old=bytearray(184);struct.pack_into('<IHHI',old,0,0x5630314d,5,184,17)
  for i in range(10):struct.pack_into('<HBBBBBB',old,12+8*i,34+i,0,0,0,3,5,6)
  struct.pack_into('<I',old,180,zlib.crc32(old[:180]));new=bytearray(old);new[86]=2;struct.pack_into('<I',new,8,17 if fault=='sequence' else 18);struct.pack_into('<I',new,180,zlib.crc32(new[:180]))
  if fault=='crc':new[86]^=1
  address=0x558f0000;u.mem_write(address,bytes(new));files={'M10V6B.bin':bytes(old)};writes=[]
  def hook(cpu,pc,n,ctx):
   regs=[cpu.reg_read(r) for r in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]];result=None
   if pc==0x54010040:self.assertEqual(regs[0],1);result=1
   elif pc==0x54010080:self.assertEqual(regs[0],1);result=1
   elif pc==0x53828014:result=0x558e0000
   elif pc in [0x53825648,0x53825fa8]:
    name=bytes(cpu.mem_read(regs[1],12)).split(b'\0')[0].decode();self.assertIn(name,['M10V6A.bin','M10V6B.bin']);self.assertEqual(regs[2],184)
    if pc==0x53825fa8:
     writes.append(name);data=bytes(cpu.mem_read(regs[3],184))
     if fault!='write':files[name]=data if fault!='readback' else bytes(old)
     result=int(fault!='write')
    elif name in files:cpu.mem_write(regs[3],files[name]);result=1
    else:result=0
   if result is not None:cpu.reg_write(UC_ARM_REG_R0,result);cpu.reg_write(UC_ARM_REG_PC,cpu.reg_read(UC_ARM_REG_LR))
  u.hook_add(UC_HOOK_CODE,hook);u.reg_write(UC_ARM_REG_SP,0x5600f000);u.reg_write(UC_ARM_REG_LR,0x56010000);u.reg_write(UC_ARM_REG_R0,address);u.emu_start(self.symbols['m10v_camera_library_commit_snapshot'],0x56010000,count=1000000)
  self.assertEqual(u.reg_read(UC_ARM_REG_PC),0x56010000)
  if fault in ['crc','sequence','unlocked']:self.assertEqual(writes,[])
  else:self.assertEqual(writes,['M10V6A.bin'])
  self.assertEqual(u.reg_read(UC_ARM_REG_R0)==0,fault is None)
  self.assertEqual(files['M10V6B.bin'],bytes(old))
  if fault is None:self.assertEqual(files['M10V6A.bin'],bytes(new))
