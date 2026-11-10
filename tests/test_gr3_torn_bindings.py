"""Eligibility uses frozen SI and state, with no live getter at enqueue."""
import shutil,struct,subprocess,tempfile,unittest
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn import arm_const as A
from scripts.build_gr3_m10v_library import FLAGS,link_object
ROOT=Path(__file__).resolve().parents[1]
class Bindings(unittest.TestCase):
 def test_bindings_exist(self):self.assertTrue((ROOT/'native/gr3/m10v_torn_bindings.c').exists())
 def setUp(self):
  if not (ROOT/'native/gr3/m10v_torn_bindings.c').exists():
   if self._testMethodName=='test_bindings_exist':return
   self.skipTest('bindings not implemented')
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);p=Path(self.tmp.name);obj=p/'b.o'
  subprocess.run([shutil.which('clang'),*FLAGS,'-DM10V_APPENDED_SLOTS=1','-c',str(ROOT/'native/gr3/m10v_torn_bindings.c'),'-o',str(obj)],check=True,capture_output=True)
  self.ext={'m10v_camera_library_read_current':0x54f00000,'m10v_isp_frame_recipe_state':0x54f00004,'m10v_isp_effects_shot_read':0x54f00008}
  code,self.sym=link_object(obj.read_bytes(),0x54d00000,self.ext,'m10v_torn_binding_',additional_exports=('m10v_torn_eligible','m10v_torn_camera_busy'))
  self.u=Uc(UC_ARCH_ARM,UC_MODE_ARM);self.u.mem_map(0x53000000,0x2000000);self.u.mem_write(0x54d00000,code);self.u.mem_map(0x55000000,0x1000000)
  self.r=0x55100000;self.si=0x55200000;self.put(self.r,0x53d0fc90);self.put(self.r+0x44c8,self.si);self.u.mem_write(self.si+0x77c,b'\x19');self.film=34;self.calls=[]
  self.effects_ready=True;self.u.hook_add(UC_HOOK_CODE,self.hook)
 def put(self,a,*v):self.u.mem_write(a,struct.pack('<'+'I'*len(v),*v))
 def hook(self,u,pc,size,data):
  if pc not in self.ext.values():return
  if pc==self.ext['m10v_isp_effects_shot_read']:
   self.calls.append(pc);u.reg_write(A.UC_ARM_REG_R0,int(self.effects_ready));u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR));return
  self.calls.append(pc);out=u.reg_read(A.UC_ARM_REG_R1) if pc==self.ext['m10v_isp_frame_recipe_state'] else u.reg_read(A.UC_ARM_REG_R0)
  u.mem_write(out,bytes(184));u.mem_write(out+12,struct.pack('<H',self.film));u.reg_write(A.UC_ARM_REG_R0,1 if pc==self.ext['m10v_isp_frame_recipe_state'] else 0);u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
 def call(self):
  self.u.reg_write(A.UC_ARM_REG_SP,0x55fe0000);self.u.reg_write(A.UC_ARM_REG_R0,self.r);self.u.reg_write(A.UC_ARM_REG_R1,self.si);self.u.reg_write(A.UC_ARM_REG_LR,0x55ff0000);self.u.emu_start(self.sym['m10v_torn_eligible'],0x55ff0000,count=100000);return self.u.reg_read(A.UC_ARM_REG_R0)
 def test_saved_single_only_and_no_live_getter(self):
  self.assertEqual(self.call(),1);self.assertEqual(self.calls,[self.ext['m10v_isp_effects_shot_read'],self.ext['m10v_isp_frame_recipe_state']])
  for offset,value in ((0xfb9,3),(0x799,5),(0x7b6,6),(0x77c,14)):
   before=bytes(self.u.mem_read(self.si+offset,1));self.u.mem_write(self.si+offset,bytes([value]));self.assertEqual(self.call(),0);self.u.mem_write(self.si+offset,before)
 def test_special_and_custom_films_are_not_admitted(self):
  for film in (0,100,289,290):self.film=film;self.assertEqual(self.call(),0)
 def test_unavailable_effect_cache_cannot_claim_a_capture(self):
  self.effects_ready=False;self.assertEqual(self.call(),0)
