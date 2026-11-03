import struct,subprocess,tempfile,unittest
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_LR,UC_ARM_REG_PC,UC_ARM_REG_SP
ROOT=Path(__file__).resolve().parents[1]
class Ctor(unittest.TestCase):
 def test_owner_init_is_wired_only_for_explicit_companion_build(self):
  for enabled in [0,1]:
   with self.subTest(enabled=enabled):self.run_case(enabled)
 def run_case(self,enabled):
  with tempfile.TemporaryDirectory()as tmp:
   d=Path(tmp);obj=d/'controller.o';r=subprocess.run(['clang','--target=armv7-none-eabi','-mcpu=cortex-a9','-marm','-mfloat-abi=soft','-Os','-ffreestanding','-fno-builtin','-ffunction-sections','-fdata-sections','-fno-unwind-tables','-fno-asynchronous-unwind-tables',f'-DM10V_COMPANION_ENABLED={enabled}','-DM10V_LIVE_COLOR=1','-DM10V_APPENDED_SLOTS=1','-c',str(ROOT/'native/gr3/m10v_settings_controller.c'),'-o',str(obj)],capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stderr)
   names=subprocess.check_output(['/opt/homebrew/opt/llvm/bin/llvm-nm','--undefined-only',str(obj)],text=True);ports={name:0x54010000+i*64 for i,name in enumerate(sorted({line.split()[-1] for line in names.splitlines()}|{'m10v_companion_ui_init'}))}
   elf=d/'ctor.elf';subprocess.run(['ld.lld','-m','armelf_linux_eabi','--gc-sections','--entry=m10v_settings_controller_top_ctor','-Ttext=0x540c0000',*[f'--defsym={name}={address}' for name,address in ports.items()],str(obj),'-o',str(elf)],check=True,capture_output=True)
   b=elf.read_bytes();u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0x53000000,0x3000000);u.mem_map(0x56000000,0x20000);off=struct.unpack_from('<I',b,28)[0];size,count=struct.unpack_from('<HH',b,42)
   for i in range(count):
    kind,at,va,_,n,_,_,_=struct.unpack_from('<8I',b,off+i*size)
    if kind==1:
     if va<0x53000000:u.mem_map(va&~4095,((va%4096+n+4095)//4096)*4096)
     u.mem_write(va,b[at:at+n])
   seen=[]
   def hook(cpu,pc,n,ctx):
    if pc in ports.values():
     name=next(k for k,v in ports.items() if v==pc);self.assertIn(name,['m10v_settings_controller_vtable','m10v_camera_library_preview_init','m10v_companion_ui_init']);seen.append((name,cpu.reg_read(UC_ARM_REG_R0)));cpu.reg_write(UC_ARM_REG_R0,0x54020000 if name=='m10v_settings_controller_vtable' else 0);cpu.reg_write(UC_ARM_REG_PC,cpu.reg_read(UC_ARM_REG_LR))
    elif pc in [0x5319aa68,0x5316c8d4]:cpu.reg_write(UC_ARM_REG_PC,cpu.reg_read(UC_ARM_REG_LR))
   u.hook_add(UC_HOOK_CODE,hook);u.reg_write(UC_ARM_REG_R0,0x55860000);u.reg_write(UC_ARM_REG_SP,0x5600f000);u.reg_write(UC_ARM_REG_LR,0x56010000);u.emu_start(struct.unpack_from('<I',b,24)[0],0x56010000,count=100000)
   self.assertEqual([argument for name,argument in seen if name=='m10v_companion_ui_init'],[0x55860000]if enabled else [])
