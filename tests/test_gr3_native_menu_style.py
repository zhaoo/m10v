"""Native menu draw contracts: execute our ARM with only widget leaves replaced."""
import struct, tempfile, subprocess, unittest
from pathlib import Path
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm_const as A
from scripts.build_gr3_m10v_library import FLAGS, link_object

class NativeMenuStyleTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
  obj=Path(cls.tmp.name)/'view.o'
  subprocess.run(['/opt/homebrew/opt/llvm/bin/clang',*FLAGS,'-c','native/gr3/m10v_settings_view.c','-o',str(obj)],check=True,capture_output=True)
  names=['m10v_library_name','m10v_sd_camera_catalog_name','m10v_sd_camera_custom_name','m10v_zoom_title','m10v_zoom_bits','m10v_zoom_caption','m10v_film_card_custom','m10v_film_card_render']
  cls.externals={n:0x55001000+4*i for i,n in enumerate(names)}
  cls.code,cls.symbols=link_object(obj.read_bytes(),0x54100000,cls.externals,'m10v_settings_view_',additional_exports=('m10v_settings_view_zoom',))
 def setUp(self):
  self.u=u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0x53000000,0x2000000);u.mem_map(0x55000000,0x100000)
  u.mem_write(0x54100000,self.code);self.heap=0x55040000;self.widgets=[];self.rects={};self.colors={};self.glyphs={};self.visible={};self.live=set()
  u.mem_write(0x55002000+0x28,struct.pack('<I',0x55003000));u.mem_write(0x55002000+0x34,struct.pack('<I',0x55003000))
  def service(uc,a,n,d):
   r=[uc.reg_read(getattr(A,'UC_ARM_REG_R'+str(i))) for i in range(4)];result=r[0]
   if a==0x536af2a8:
    result=self.heap;self.heap+=(r[0]+15)&~15;self.live.add(result)
   elif a in (0x5339199c,0x5339a908,0x53393d84,0x53396944,0x53390ca0):
    height=struct.unpack('<I',uc.mem_read(uc.reg_read(A.UC_ARM_REG_SP),4))[0]
    self.widgets.append(r[0]);self.rects[r[0]]=(r[1],r[2],r[3],height);uc.mem_write(r[0],struct.pack('<I',0x55002000))
   elif a==0x53393e00:self.colors[r[0]]=r[1]
   elif a==0x5339658c:self.glyphs[r[0]]=r[1]
   elif a==0x533ad3c0:self.visible[r[0]]=r[1]
   elif a==0x5316cde8:
    for p in struct.unpack('<'+'I'*r[2],uc.mem_read(r[1],4*r[2])):self.live.discard(p)
   elif a==0x536af2e4:self.live.discard(r[0])
   elif a in (0x533aba64,0x53396f80,0x5339aa30,0x5339aa44,0x533ad308,0x55003000):pass
   elif a in self.externals.values():result=0
   else:return
   uc.reg_write(A.UC_ARM_REG_R0,result);uc.reg_write(A.UC_ARM_REG_PC,uc.reg_read(A.UC_ARM_REG_LR))
  u.hook_add(UC_HOOK_CODE,service);self.call('create',0x55004000)
 def call(self,n,*args):
  u=self.u
  for i,v in enumerate(args):u.reg_write(getattr(A,'UC_ARM_REG_R'+str(i)),v)
  u.reg_write(A.UC_ARM_REG_SP,0x550ff000);u.reg_write(A.UC_ARM_REG_LR,0x550ff800)
  u.emu_start(self.symbols['m10v_settings_view_'+n],0x550ff800,count=100000)
  self.assertEqual(u.reg_read(A.UC_ARM_REG_PC),0x550ff800)
 def draw(self,screen=3,focus=1):
  # Current settings state is184 bytes, followed by8 controller words.
  state=bytearray(216);struct.pack_into('<8I',state,184,screen,focus,0,0,0,0,0,0)
  self.u.mem_write(0x55005000,bytes(state));self.call('draw',0x55004000,0x55005000,0)
 def test_stamp_selection_is_full_width_fill_with_dark_text_and_separators(self):
  self.draw();w=self.widgets
  self.assertEqual(self.rects[w[37]],(0,156,720,64))
  self.assertEqual(self.colors[w[37]],6)
  self.assertEqual(self.glyphs[w[45]],28);self.assertEqual(self.glyphs[w[49]],28)
  self.assertEqual(self.glyphs[w[44]],31)
  self.assertEqual([self.visible[w[36+i]] for i in range(4)],[0,1,0,0])
  for i in range(4):
   self.assertEqual(self.rects[w[40+i]],(0,147+72*i,720,1))
   self.assertEqual(self.visible[w[40+i]],1)
   self.assertEqual(self.colors[w[40+i]],2)
  self.call('destroy',0x55004000);self.assertEqual(self.live,set())
 def test_film_page_hides_setting_fills_and_separators(self):
  self.draw(1)
  self.assertEqual([self.visible[self.widgets[36+i]] for i in range(8)],[0]*8)

if __name__=='__main__':unittest.main()
