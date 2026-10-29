"""Run the final installed ratio overlay through the real native RGBA blitter."""
import os,struct,unittest
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE,UC_PROT_READ,UC_PROT_EXEC,arm_const as A
BASE=0x53000000;RAM=0x55000000;STOP=RAM+0xf0000
class FinalAspectIndicator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=os.environ.get('M10V_ASPECT_RTOS')
        if not path:raise unittest.SkipTest('Set M10V_ASPECT_RTOS to the final decoded RTOS')
        cls.code=Path(path).read_bytes()
        from scripts.gr3_aspect_overlay import build_module
        _,cls.entries=build_module()
    def test_real_native_blitter_consumes_each_installed_aspect_tile(self):
        for ratio in (4,5,6):
            with self.subTest(ratio=ratio):
                u=Uc(UC_ARCH_ARM,UC_MODE_ARM);extent=(len(self.code)+4095)&~4095
                u.mem_map(BASE,extent);u.mem_write(BASE,self.code);u.mem_protect(BASE,extent,UC_PROT_READ|UC_PROT_EXEC)
                u.mem_map(RAM,0x400000);u.reg_write(A.UC_ARM_REG_SP,RAM+0xd0000);u.reg_write(A.UC_ARM_REG_LR,STOP)
                view,surface,manager,graphics,fb=RAM+0x2000,RAM+0x3000,RAM+0x4000,RAM+0x5000,RAM+0x100000
                u.mem_write(RAM+0x100,struct.pack('<I',RAM+0x200))
                u.mem_write(view+0x9e,b'\x01')
                for offset in (0x30,0x64):u.mem_write(view+offset,struct.pack('<4I',0,0,720,480))
                u.mem_write(surface+2,b'\x05');u.mem_write(surface+0x18,struct.pack('<H',720))
                u.mem_write(graphics,struct.pack('<I',0x57000000));u.mem_write(fb,b'\x33'*(720*480*4))
                returns={0x53525d5c:RAM+0x100,0x5354a778:ratio,0x53549958:0,0x53654150:manager,0x53654220:0,0x540b8000:0,0x540b88b4:0,0x5320804c:manager,0x532081ec:graphics,0x53208298:graphics,0x536c7520:fb}
                blits=[];allocs=[];asserts=[]
                def native(m,a,s,d):
                    if a==0x5320a020:blits.append(a);return
                    if a==0x536af2a8:allocs.append(m.reg_read(A.UC_ARM_REG_R0));v=0
                    elif a==0x536b93d0:asserts.append(tuple(hex(m.reg_read(reg)) for reg in (A.UC_ARM_REG_LR,A.UC_ARM_REG_R0,A.UC_ARM_REG_R1,A.UC_ARM_REG_R2,A.UC_ARM_REG_R3)));v=0
                    elif a in returns:v=returns[a]
                    else:return
                    m.reg_write(A.UC_ARM_REG_R0,v);m.reg_write(A.UC_ARM_REG_PC,m.reg_read(A.UC_ARM_REG_LR))
                u.hook_add(UC_HOOK_CODE,native);u.reg_write(A.UC_ARM_REG_R0,view);u.reg_write(A.UC_ARM_REG_R1,surface)
                u.emu_start(self.entries['m10v_aspect_draw'],STOP,count=1000000)
                self.assertEqual(u.reg_read(A.UC_ARM_REG_PC),STOP)
                self.assertEqual(u.reg_read(A.UC_ARM_REG_SP),RAM+0xd0000)
                self.assertEqual(allocs,[]);self.assertTrue(all(row[1]=='0x1' for row in asserts),asserts);self.assertTrue(blits)
                art=(Path(__file__).resolve().parents[1]/'native/gr3/m10v_half_frame_icon.rgba').read_bytes() if ratio==6 else (Path(__file__).resolve().parents[1]/'native/gr3/m10v_aspect_icons.rgba').read_bytes()[(ratio-4)*9600:(ratio-3)*9600]
                for y in range(40):
                    actual=bytes(u.mem_read(fb+((48+y)*720+652)*4,240))
                    # Native blend preserves framebuffer under transparent edge pixels.
                    for x in range(60):
                        pixel=art[(y*60+x)*4:(y*60+x+1)*4]
                        if pixel[3]==255:self.assertEqual(actual[x*4:x*4+3],pixel[:3],(x,y))
                self.assertEqual(bytes(u.mem_read(fb,4)),b'\x33'*4)
