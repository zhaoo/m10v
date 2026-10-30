"""Run actual HDF/effects ARM controller with recorded native widget services."""
import struct, subprocess, tempfile, unittest
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn import arm_const as A
from scripts.build_gr3_m10v_library import FLAGS,link_object

class HdfStyleTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup);cls.variants={}
  for border,hdf in ((0,1),(1,1),(1,0)):
   obj=Path(cls.tmp.name)/f'hdf-{border}-{hdf}.o'
   externals={name:0x55001000+4*i for i,name in enumerate(['m10v_hdf_load','m10v_hdf_save','m10v_hdf_menu_parent_ctor','m10v_hdf_menu_parent_dtor','m10v_hdf_menu_parent_factory','m10v_hdf_menu_parent_key_route','m10v_hdf_menu_vtable','m10v_border_camera_refresh','m10v_border_camera_save'])}
   subprocess.run(['clang',*FLAGS,'-DM10V_BORDER_CACHE_OWNER_OFFSET=0x1ae4',f'-DM10V_BORDER_ENABLED={border}',f'-DM10V_HDF_ENABLED={hdf}',f'-DM10V_HDF_GROUPED={border}','-c','native/gr3/m10v_hdf_menu.c','-o',str(obj)],check=True,capture_output=True)
   cls.variants[border,hdf]=(*link_object(obj.read_bytes(),0x54100000,externals,'m10v_hdf_menu_'),externals)
 def fixture(self,border=1,fail=0,hdf=1):
  code,self.symbols,ext=self.variants[border,hdf];u=self.u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
  u.mem_map(0x53000000,0x2000000);u.mem_map(0x55000000,0x100000);u.mem_write(0x54100000,code)
  self.page=0x55008000+0x193c;self.owner=0x55008000;self.live=set();self.rects={};self.colors={};self.glyphs={};self.visible={};self.created=[];self.closed=[];self.saved=[];self.allocs=0;self.heap=0x55040000
  self.put(0x55002028,0x55003000);self.put(0x55002034,0x55003000)
  def service(uc,a,n,d):
   r=[uc.reg_read(getattr(A,'UC_ARM_REG_R'+str(i))) for i in range(4)];result=r[0]
   if a==0x536af2a8:
    self.allocs+=1;result=0
    if self.allocs!=fail:result=self.heap;self.heap+=(r[0]+15)&~15;self.live.add(result)
   elif a in (0x5339199c,0x53393d84,0x53396944):
    self.assertTrue(r[0]);h=self.get(uc.reg_read(A.UC_ARM_REG_SP));self.rects[r[0]]=(r[1],r[2],r[3],h);self.created.append(r[0]);self.put(r[0],0x55002000)
   elif a==0x53393e00:self.colors[r[0]]=r[1]
   elif a==0x5339658c:self.glyphs[r[0]]=r[1]
   elif a==0x533ad3c0:self.visible[r[0]]=r[1]
   elif a==0x5316cde8:
    for p in struct.unpack('<'+'I'*r[2],uc.mem_read(r[1],r[2]*4)):
     self.assertIn(p,self.live);self.live.remove(p)
   elif a==0x536af2e4:self.assertIn(r[0],self.live);self.live.remove(r[0])
   elif a==0x5316ca28:self.closed.append(r[0])
   elif a==ext['m10v_hdf_load']:self.put(r[0],0);result=0
   elif a==ext['m10v_hdf_save']:self.saved.append(r[0]);result=0
   elif a in ext.values():result=0
   elif a in (0x533aba64,0x53396f80,0x533ad308,0x5316d354,0x5316c8d4,0x5316ce8c,0x5316c774,0x55003000):pass
   else:return
   uc.reg_write(A.UC_ARM_REG_R0,result);uc.reg_write(A.UC_ARM_REG_PC,uc.reg_read(A.UC_ARM_REG_LR))
  u.hook_add(UC_HOOK_CODE,service);self.call('top_ctor',self.owner)
 def put(self,a,v):self.u.mem_write(a,struct.pack('<I',v))
 def get(self,a):return struct.unpack('<I',self.u.mem_read(a,4))[0]
 def call(self,name,*args):
  for i in range(13):self.u.reg_write(getattr(A,'UC_ARM_REG_R'+str(i)),args[i] if i<len(args) else 0)
  self.u.reg_write(A.UC_ARM_REG_SP,0x550ff000);self.u.reg_write(A.UC_ARM_REG_LR,0x550ff800)
  self.u.emu_start(self.symbols['m10v_hdf_menu_'+name],0x550ff800,count=200000)
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x550ff800)
  return self.u.reg_read(A.UC_ARM_REG_R0)
 def key(self,k):self.u.mem_write(0x55007000,struct.pack('<H',k));return self.call('key',self.page,0x55007000)
 def assert_rows(self,selected,count):
  heap=self.get(self.page+0x1bc);self.assertNotEqual(heap,0)
  rows=[self.get(heap+i*4) for i in range(8)]
  for i in range(4):
   label=self.get(self.page+0x158+(4+i)*4)
   self.assertEqual(self.rects[rows[i]],(0,84+i*72,720,64))
   self.assertEqual(self.rects[rows[4+i]],(0,147+i*72,720,1))
   self.assertEqual(self.colors[rows[i]],6);self.assertEqual(self.colors[rows[4+i]],2)
   self.assertEqual(self.visible[rows[i]],int(i<count and i==selected))
   self.assertEqual(self.visible[rows[4+i]],int(i<count))
   self.assertEqual(self.rects[label],(36,90+i*72,644,52))
   self.assertEqual(self.glyphs[label],28 if i==selected and i<count else 31)
   self.assertLess(self.created.index(rows[i]),self.created.index(label))
 def test_effects_hdf_and_border_vertical_rows_keep_offsets_and_cancel_semantics(self):
  self.fixture();self.assertEqual(self.call('ready',self.page,0),1);self.call('enter',self.page,0,0)
  self.assertEqual(self.get(self.page+0x190+4),0x43464448);self.assertEqual(self.get(self.page+0x17c),9)
  self.assert_rows(0,2);self.key(0xd5);self.assert_rows(1,2);self.key(0xd8);self.assert_rows(0,3)
  self.key(0xd5);self.assert_rows(1,3);self.key(0xda);self.assert_rows(1,2);self.assertEqual(self.saved,[])
  self.key(0xd4);self.key(0xd8);self.assert_rows(0,4);self.key(0xd5);self.assert_rows(1,4)
  allocated=self.allocs;style=self.get(self.page+0x1bc)
  self.assertEqual(self.call('ready',self.page,0),1);self.assertEqual(self.allocs,allocated);self.assertEqual(self.get(self.page+0x1bc),style)
  self.call('destroy',self.page);self.assertEqual(self.live,set());self.assertEqual(self.get(self.page+0x1bc),0)
  self.call('destroy',self.page);self.assertEqual(self.live,set())
 def test_standalone_hdf_has_the_same_native_rows_and_back_behavior(self):
  self.fixture(0);self.assertEqual(self.call('ready',self.page,0),1);self.call('enter',self.page,0,0);self.assert_rows(0,4)
  self.key(0xcf);self.assert_rows(1,4);self.key(0xda);self.assertEqual(self.closed,[self.page]);self.assertEqual(self.saved,[])
  self.call('destroy',self.page);self.assertEqual(self.live,set())
 def test_hdf_description_is_hidden_but_save_error_remains_visible(self):
  self.fixture(0);self.assertEqual(self.call('ready',self.page,0),1)
  self.call('enter',self.page,0,0);message=self.get(self.page+0x158+8*4)
  self.assertEqual(self.visible[message],0)
  self.put(self.page+0x188,1);self.call('enter',self.page,0,0)
  self.assertEqual(self.visible[message],1)
  self.call('destroy',self.page);self.assertEqual(self.live,set())
 def test_every_partial_allocation_failure_releases_widgets_and_style_heap(self):
  for border,hdf in ((0,1),(1,1),(1,0)):
   for fail in range(1,19):
    with self.subTest(border=border,fail=fail):
     self.fixture(border,fail,hdf);self.assertEqual(self.call('ready',self.page,0),0)
     self.assertEqual(self.get(self.page+0x17c),0);self.assertEqual(self.get(self.page+0x1bc),0);self.assertEqual(self.live,set())
     self.assertEqual(self.call('ready',self.page,0),1);self.call('destroy',self.page);self.assertEqual(self.live,set())
 def test_border_only_effects_hides_unused_rows(self):
  self.fixture(1,hdf=0);self.assertEqual(self.call('ready',self.page,0),1);self.call('enter',self.page,0,0)
  self.assert_rows(0,1);self.key(0xd8);self.assert_rows(0,3);self.key(0xda);self.assert_rows(0,1)
  self.call('destroy',self.page);self.assertEqual(self.live,set())
