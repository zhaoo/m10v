"""Execute real menu transitions with native UI/service boundaries only."""
import shutil,struct,subprocess,tempfile,unittest
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn import arm_const as A
from scripts.build_gr3_m10v_library import FLAGS,link_object
ROOT=Path(__file__).resolve().parents[1]
class ImprintMenuTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
  obj=Path(cls.tmp.name)/'menu.o';src=obj.with_suffix('.c')
  src.write_text('\n'.join('#include "'+str(ROOT/'native/gr3'/f)+'"' for f in ('m10v_isp_effects_state.c','m10v_hdf_menu.c')))
  subprocess.run(['clang',*FLAGS,'-DM10V_BORDER_ENABLED=1','-DM10V_BORDER_CACHE_OWNER_OFFSET=0x62e4','-DM10V_PURE_ISP_EFFECTS=1','-DM10V_HDF_GROUPED=1','-DM10V_HDF_OWNER_OFFSET=0x613c','-c',str(src),'-o',str(obj)],check=True,capture_output=True)
  names=['m10v_hdf_menu_parent_'+n for n in ('ctor','dtor','factory','key_route')]+['m10v_hdf_menu_vtable','m10v_hdf_load','m10v_hdf_save','m10v_border_camera_refresh','m10v_border_camera_save','m10v_isp_effects_camera_init','m10v_isp_effects_camera_refresh','m10v_isp_effects_camera_snapshot','m10v_isp_effects_camera_save']
  cls.ext={name:0x53000100+i*4 for i,name in enumerate(names)}
  cls.code,cls.symbols=link_object(obj.read_bytes(),0x541d0000,cls.ext,'m10v_hdf_menu_')
 def setUp(self):
  self.u=u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0x53000000,0x1500000);u.mem_write(0x541d0000,self.code);u.mem_map(0x55000000,0x100000)
  self.owner=0x55010000;self.page=self.owner+0x613c;self.cursor=0x55040000;self.style=0;self.saves=[];self.caption=[];self.fail=False;self.init=0
  self.put(0x55009028,0x53010000);self.put(0x55009034,0x53010004)
  u.hook_add(UC_HOOK_CODE,self.hook);self.call('top_ctor',self.owner);self.assertEqual(self.call('ready',self.page,0),1)
 def put(self,p,*v):self.u.mem_write(p,struct.pack('<'+'I'*len(v),*v))
 def word(self,p):return struct.unpack('<I',self.u.mem_read(p,4))[0]
 def hook(self,u,pc,size,data):
  r=[u.reg_read(getattr(A,'UC_ARM_REG_R'+str(i))) for i in range(4)];result=r[0]
  name=next((n for n,a in self.ext.items() if a==pc),None)
  if name:
   result=0
   if name=='m10v_hdf_menu_vtable':result=0x55009000
   elif name=='m10v_hdf_load':self.put(r[0],0)
   elif name=='m10v_isp_effects_camera_init':self.init+=1
   elif name=='m10v_isp_effects_camera_snapshot':self.put(r[0],0,0,0,0,0,0,0,0x46580000|(self.style<<7));self.put(r[1],7);result=1
   elif name=='m10v_isp_effects_camera_save':
    self.saves.append((r[0],self.word(r[1]+28)));result=-4 if self.fail else 0
    if not self.fail:self.style=(self.word(r[1]+28)>>7)&7
  elif pc==0x536af2a8:result=self.cursor;self.cursor+=0x200
  elif pc in (0x5339199c,0x53393d84,0x53396944):self.put(r[0],0x55009000)
  elif pc==0x53396f80:self.caption.append(r[1])
  elif pc not in (0x5316c8d4,0x5316ce8c,0x5316c774,0x533aba64,0x53393e00,0x5339658c,0x533ad3c0,0x533ad308,0x5316d354,0x53010000,0x53010004):return
  u.reg_write(A.UC_ARM_REG_R0,result&0xffffffff);u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
 def call(self,name,*args):
  for i in range(4):self.u.reg_write(getattr(A,'UC_ARM_REG_R'+str(i)),args[i] if i<len(args) else 0)
  self.u.reg_write(A.UC_ARM_REG_SP,0x550fd000);self.u.reg_write(A.UC_ARM_REG_LR,0x550ff000)
  self.u.emu_start(self.symbols['m10v_hdf_menu_'+name],0x550ff000,count=200000)
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x550ff000)
  return self.u.reg_read(A.UC_ARM_REG_R0)
 def key(self,k):self.u.mem_write(0x55006000,struct.pack('<H',k));return self.call('key',self.page,0x55006000)
 def open_imprint(self):self.key(0xd1);self.key(0xd1);self.key(0xd8)
 def test_root_has_third_entry_and_initializes_global_cache(self):
  self.call('enter',self.page,0,0)
  self.assertEqual(self.init,1);self.assertIn(1203,self.caption)
 def test_all_five_styles_paginate_and_save_to_independent_journal(self):
  self.open_imprint()
  for i in range(7):self.key(0xd1)
  self.assertEqual(self.word(self.page+0x180),7)
  self.assertIn(1210,self.caption)
  self.key(0xd8)
  self.assertEqual(self.style,7);self.assertEqual(self.word(self.page+0x18c),1)
  self.assertEqual(self.saves[0][0],self.owner)
 def test_cancel_never_saves_and_reentry_uses_committed_style(self):
  self.style=2;self.open_imprint();self.key(0xd1);self.key(0xda)
  self.assertEqual(self.saves,[]);self.key(0xd8)
  self.assertEqual(self.word(self.page+0x180),2)
 def test_failed_save_keeps_menu_open_and_reconciles_committed_value(self):
  self.open_imprint();self.key(0xd1);self.fail=True;self.key(0xd8)
  self.assertEqual(self.word(self.page+0x188),1);self.assertEqual(self.word(self.page+0x18c),0)
  self.assertEqual(self.word(self.page+0x180),0)
