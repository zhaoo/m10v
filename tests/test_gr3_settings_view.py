"""Unintegrated view: execute actual GR III 2.10 constructors/setters/destructors.
Allocator/free leaves are replaced; initialized firmware singleton state is seeded.
No framebuffer, controller routing or hardware validation is implied.
"""
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
from scripts.build_gr3_m10v_library import FLAGS, link_object
from scripts.analyze_gr3_settings import read_firmware
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import *
ROOT = Path(__file__).resolve().parents[1]
BASE=0x540c0000
class SettingsViewTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  path=Path(os.environ.get('M10V_GR3_ORIGINAL_RTOS','/tmp/m10v-sd-research/rtos.bin'))
  if not path.exists():raise unittest.SkipTest('official GR III 2.10 RTOS required')
  cls.firmware=read_firmware(path)
  cc=os.environ.get('M10V_LLVM_CLANG') or '/opt/homebrew/opt/llvm/bin/clang'
  if not Path(cc).exists():cc=shutil.which('clang')
  with tempfile.TemporaryDirectory() as d:
   obj=Path(d)/'view.o'
   subprocess.run([cc,*FLAGS,'-c',str(ROOT/'native/gr3/m10v_settings_view.c'),'-o',str(obj)],check=True,capture_output=True)
   card=Path(d)/'card.o'
   from scripts.generate_m10v_film_cards import caption_blob
   cls.captions=caption_blob()
   subprocess.run([cc,*FLAGS,'-DM10V_CARD_CAPTION_EXTERNAL=1','-c',str(ROOT/'native/gr3/m10v_film_card.c'),'-o',str(card)],check=True,capture_output=True)
   cls.card,entries=link_object(card.read_bytes(),BASE+0x4000,{'caption_offsets':BASE+0x20000,'caption_rle':BASE+0x20000+88*4},prefix='m10v_film_card_')
   cls.code,cls.symbols=link_object(obj.read_bytes(),BASE,{'m10v_library_name':0x540b0000,'m10v_sd_camera_catalog_name':0x540b0020,'m10v_sd_camera_custom_name':0x540b0030,'m10v_zoom_title':0x540b0040,'m10v_zoom_bits':0x540b0044,'m10v_zoom_caption':0x540b0048,**entries},prefix='m10v_settings_view_',additional_exports=('m10v_settings_view_zoom',))
 def machine(self,fail_object=0,fail_cards=False,native_accessor=False,custom_names=None,catalog_ids=None):
  u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
  for addr,size in [(0x53000000,0x2000000),(0x55000000,0x1000000),(0x10000000,0x200000)]:u.mem_map(addr,size)
  u.mem_write(0x53000000,self.firmware);u.mem_write(BASE,self.code);u.mem_write(BASE+0x4000,self.card)
  u.mem_write(BASE+0x20000,self.captions)
  u.mem_write(0x55000000,self.firmware[0x107b540:0x107b540+0x3a080])
  u.reg_write(UC_ARM_REG_C1_C0_2,0xf00000);u.reg_write(UC_ARM_REG_FPEXC,0x40000000)
  for address in (0x5536d074,0x55063d80,0x55063ed0):u.mem_write(address,struct.pack('<I',1))
  u.mem_write(0x5536d078,self.firmware[0x6b7058:0x6b705c])
  u.mem_write(0x55063f34,struct.pack('<I',0x55100000));u.mem_write(0x551009ba,b'\x14')
  self.heap=0x10100000;self.live={};self.object_count=0;self.executed=set()
  # Catalog-name provider stub only; stock view APIs execute unchanged.
  u.mem_write(0x10000800,b'PORTRA\0')
  def hook(uc,a,n,_):
   self.executed.add(a)
   if a in (0x536af2a8,0x536af31c):
    size=uc.reg_read(UC_ARM_REG_R0)
    if size in (0xf0,0xf8,0x110):self.object_count+=1
    if (fail_object and self.object_count==fail_object and size in (0xf0,0xf8,0x110)) or (fail_cards and size==710580):p=0
    else:
     p=self.heap;self.heap+=(size+15)&~15;self.live[p]=size
    uc.reg_write(UC_ARM_REG_R0,p)
   elif a in (0x536af2e4,0x536af358):
    p=uc.reg_read(UC_ARM_REG_R0)
    if p:self.assertIn(p,self.live);del self.live[p]
   elif a==0x540b60e0 and not native_accessor:uc.reg_write(UC_ARM_REG_R0,0x10004000)
   elif a==0x540b0040:uc.reg_write(UC_ARM_REG_R0,1024)
   elif a==0x540b0044:pass # Numeric mm boundary mock for this view test.
   elif a==0x540b0048:uc.reg_write(UC_ARM_REG_R0,1031+uc.reg_read(UC_ARM_REG_R0)-28)
   elif a==0x540b0000:uc.reg_write(UC_ARM_REG_R0,0x10000800)
   elif a==0x540b0010:
    index=uc.reg_read(UC_ARM_REG_R1);uc.reg_write(UC_ARM_REG_R0,catalog_ids.get(index,0) if catalog_ids is not None else 33+index if index<7 else 0)
   elif a in (0x540b0020,0x540b0030):
    index=uc.reg_read(UC_ARM_REG_R0 if a==0x540b0020 else UC_ARM_REG_R1)
    name=(custom_names or {}).get(index)
    if name:uc.mem_write(uc.reg_read(UC_ARM_REG_R2),name.encode()+b'\0')
    uc.reg_write(UC_ARM_REG_R0,int(name is not None))
   elif a in (0x536b93d0,0x53820074):self.fail('original assertion '+hex(a))
   else:return
   uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
  u.hook_add(UC_HOOK_CODE,hook);return u
 def call(self,u,name,*args):
  for reg,value in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3),args):u.reg_write(reg,value)
  u.reg_write(UC_ARM_REG_SP,0x100f0000);u.reg_write(UC_ARM_REG_LR,0x10000000)
  u.emu_start(self.symbols['m10v_settings_view_'+name],0x10000000,count=10000000)
  self.assertEqual(u.reg_read(UC_ARM_REG_PC),0x10000000);self.assertEqual(u.reg_read(UC_ARM_REG_SP),0x100f0000)
  return u.reg_read(UC_ARM_REG_R0)
 def state(self,u,screen=1,focus=2):
  s=bytearray(136)
  for i in range(5):struct.pack_into('<H',s,12+8*i,33+i)
  s[52:56]=bytes([1,2,3,0]);struct.pack_into('<8I',s,104,screen,focus,0,0,0,1,0,0)
  u.mem_write(0x10002000,bytes(s))
 def widgets(self,u):return struct.unpack('<40I',u.mem_read(0x10001000,160))
 def test_film_cards_fill_their_frames_and_restore_descriptors_on_destroy(self):
  u=self.machine();self.call(u,'create',0x10001000);w=self.widgets(u)
  self.state(u);self.call(u,'draw',0x10001000,0x10002000,0)
  ids=[struct.unpack('<H',u.mem_read(w[16+i]+0xea,2))[0] for i in range(5)]
  self.assertEqual(ids,[749,750,751,752,753])
  for i in range(5):
   width,height,pixels=struct.unpack('<HHI',u.mem_read(struct.unpack('<I',u.mem_read(0x10001000+39*4,4))[0]+470400+i*8,8))
   self.assertEqual((width,height),(120,196))
   self.assertIn(pixels*4,range(0x10100000,self.heap))
   self.assertTrue(any(u.mem_read(pixels*4,120*196*4)))
  allocated=len(self.live)
  self.state(u,2,1);self.call(u,'draw',0x10001000,0x10002000,0)
  self.assertEqual(len(self.live),allocated) # Paging reuses the owned buffers.
  self.call(u,'destroy',0x10001000)
  self.assertFalse(self.live)
  self.assertEqual(bytes(u.mem_read(0x10001000,164)),bytes(164))
 def test_card_allocation_failure_keeps_small_icons_and_can_be_destroyed(self):
  u=self.machine(fail_cards=True);self.call(u,'create',0x10001000);w=self.widgets(u)
  self.state(u);self.call(u,'draw',0x10001000,0x10002000,0)
  self.assertEqual([struct.unpack('<H',u.mem_read(w[16+i]+0xea,2))[0] for i in range(5)],[703,704,705,706,707])
  self.call(u,'destroy',0x10001000);self.assertFalse(self.live)
 def test_charmera_is_visible_in_slot_catalog_and_small_icon_fallback(self):
  for screen in (1,2):
   for fail_cards in (False,True):
    u=self.machine(fail_cards=fail_cards,catalog_ids={0:289});self.call(u,'create',0x10001000);w=self.widgets(u)
    self.state(u,screen,0);u.mem_write(0x10002000+12,struct.pack('<H',289))
    ops=0x10003000;u.mem_write(ops,struct.pack('<7I',0,0,0x540b0010,0,0,0,0))
    self.call(u,'draw',0x10001000,0x10002000,ops)
    self.assertEqual(struct.unpack('<H',u.mem_read(w[16]+0xea,2))[0],755 if fail_cards else 749)
    text=struct.unpack('<I',u.mem_read(w[3]+0xf0,4))[0]
    self.assertIn('PORTRA',bytes(u.mem_read(text,40)).decode('utf-16le').split('\0')[0])
    self.call(u,'destroy',0x10001000);self.assertFalse(self.live)
 def test_linked_runtime_owns_and_clears_the_actual_live_descriptors(self):
  from scripts.build_gr3_m10v_library import build
  with tempfile.TemporaryDirectory() as folder:
   m=build(Path(folder),sd_library=True)
   u=self.machine(native_accessor=True)
   u.mem_write(m['base'],(Path(folder)/'m10v-library-arm.bin').read_bytes())
   self.symbols=m['symbols']
   self.call(u,'create',0x10001000);self.state(u)
   self.call(u,'draw',0x10001000,0x10002000,0)
   heap=struct.unpack('<I',u.mem_read(0x10001000+39*4,4))[0]
   d=heap+m['film_cards']['descriptor_offset']
   self.assertEqual(struct.unpack('<HH',u.mem_read(d,4)),(120,196))
   p=struct.unpack('<I',u.mem_read(d+4,4))[0]*4
   self.assertIn(p,range(0x10100000,self.heap))
   self.call(u,'destroy',0x10001000)
   self.assertEqual(bytes(u.mem_read(0x10001000,164)),bytes(164));self.assertFalse(self.live)
 def test_ab_live_paths_never_allocate_attach_or_destroy_native_views(self):
  from tests import test_gr3_settings_controller as adapter
  adapter.ControllerLifetimeTests.setUpClass()
  a=adapter.ControllerLifetimeTests
  u=self.machine();self.heap=0x55110000
  self.call(u,'create',0x10001000);root=self.widgets(u)[0];baseline=dict(self.live)
  for at,blob in a.blobs:
   u.mem_write(at,blob);u.ctl_remove_cache(at,at+len(blob))
  owner=0x55040000;page=owner+0x13bc;ab=page+0x284;live=0x55050000
  u.mem_write(page,struct.pack('<I',adapter.STUB+0x800))
  u.mem_write(ab,struct.pack('<11I',1,5,1,0,1,34,0,0,0,0,0))
  u.mem_write(0x55063910,struct.pack('<I',1));u.mem_write(0x55063988,struct.pack('<I',owner))
  u.mem_write(live+0x15c,struct.pack('<I',root));clock=[1000];tone=[12]
  reverse={addr:name for name,addr in a.externals.items() if adapter.STUB<=addr<adapter.STUB+0x100}
  def hook(m,at,n,_):
   name=reverse.get(at)
   if name=='m10v_settings_controller_vtable':m.reg_write(UC_ARM_REG_R0,adapter.STUB+0x800)
   elif name=='m10v_library_name':m.reg_write(UC_ARM_REG_R0,0x10000800)
   elif name=='m10v_camera_library_load':
    fresh=bytearray(104);struct.pack_into('<H',fresh,12,34);m.mem_write(m.reg_read(UC_ARM_REG_R0),bytes(fresh));m.reg_write(UC_ARM_REG_R0,0)
   elif name and name.startswith('m10v_ab_'):m.reg_write(UC_ARM_REG_R0,0)
   elif at==0x532bd6b4:m.reg_write(UC_ARM_REG_R0,tone[0])
   elif at==0x53050b7c:
    m.mem_write(m.reg_read(UC_ARM_REG_R0),struct.pack('<II',clock[0]//1000,(clock[0]%1000)*1000));m.reg_write(UC_ARM_REG_R0,0)
   else:return
   m.reg_write(UC_ARM_REG_PC,m.reg_read(UC_ARM_REG_LR))
  u.hook_add(UC_HOOK_CODE,hook)
  def call(name,*args):
   for reg,val in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2),args):u.reg_write(reg,val)
   u.reg_write(UC_ARM_REG_SP,0x100f0000);u.reg_write(UC_ARM_REG_LR,0x10000000)
   try:u.emu_start(a.externals['m10v_settings_controller_ab_'+name],0x10000000,count=1000000)
   except Exception as e:raise AssertionError((hex(u.reg_read(UC_ARM_REG_PC)),hex(u.reg_read(UC_ARM_REG_LR)),hex(u.reg_read(UC_ARM_REG_R0)))) from e
   self.assertEqual(u.reg_read(UC_ARM_REG_PC),0x10000000)
  canvas=bytes(u.mem_read(root,0xf8));heap=self.heap
  for key in (5,26):
   call('live_enter',live,0x08000000,0)
   self.assertEqual(self.live,baseline);self.assertEqual(self.heap,heap)
   self.assertEqual(bytes(u.mem_read(root,0xf8)),canvas)
   for phase,repeats in ((1,1),(2,0)):
    u.mem_write(0x10000100,struct.pack('<HHI',key,0,0x55000120))
    u.mem_write(0x55000120,struct.pack('<II',phase,repeats))
    call('live_event',live,0x10000100)
   # Even if legacy words contain a real native canvas address, they are
   # retired state, never owned pointers to detach/hide/delete.
   u.mem_write(ab+28,struct.pack('<4I',root,root,0,0));call('live_leave',live)
   self.assertEqual(bytes(u.mem_read(ab+28,16)),bytes(16))
   self.assertEqual(self.live,baseline);self.assertEqual(self.heap,heap)
   self.assertEqual(bytes(u.mem_read(root,0xf8)),canvas)
  tone[0]=16;call('live_enter',live,0x08000000,0)
  self.assertEqual(struct.unpack('<I',u.mem_read(ab+8,4))[0],0)
  u.mem_write(ab+8,struct.pack('<I',1));u.mem_write(ab+16,struct.pack('<I',5))
  call('live_enter',live,0x08000000,0);call('live_destroy',live)
  self.assertEqual(self.live,baseline);self.assertEqual(self.heap,heap)
  self.assertEqual(bytes(u.mem_read(root,0xf8)),canvas)
 def test_ab_choices_include_actual_stock_high_contrast_black_and_white(self):
  u=self.machine();self.call(u,'create',0x10001000);w=self.widgets(u)
  self.state(u,6,1)
  u.mem_write(0x10002000+112,struct.pack('<II',1,5))
  self.call(u,'draw',0x10001000,0x10002000,0)
  self.assertEqual(struct.unpack('<H',u.mem_read(w[33]+0xea,2))[0],860) # installed 800T
  self.assertEqual(struct.unpack('<H',u.mem_read(w[34]+0xea,2))[0],272) # native Hi-Contrast BW
  p=struct.unpack('<I',u.mem_read(w[3]+0xf0,4))[0]
  self.assertEqual(bytes(u.mem_read(p,32)),'Hi-Contrast B&W\0'.encode('utf-16le'))
  self.call(u,'destroy',0x10001000);self.assertFalse(self.live)
 def test_original_tree_film_selection_and_teardown(self):
  u=self.machine();self.assertEqual(self.call(u,'create',0x10001000),0)
  w=self.widgets(u);self.assertEqual(struct.unpack('<I',u.mem_read(0x100010a0,4))[0],37)
  for p in w[1:37]:self.assertEqual(struct.unpack('<I',u.mem_read(p+4,4))[0],w[0])
  self.state(u);self.call(u,'draw',0x10001000,0x10002000,0)
  self.assertEqual([u.mem_read(w[6+i]+0xea,1)[0] for i in range(5)],[1,1,6,1,1])
  self.assertEqual([struct.unpack('<H',u.mem_read(w[16+i]+0xea,2))[0] for i in range(5)],[749,750,751,752,753])
  p=struct.unpack('<I',u.mem_read(w[3]+0xf0,4))[0];self.assertEqual(bytes(u.mem_read(p,28)),'3 / 5  PORTRA\0'.encode('utf-16le'))
  self.assertEqual(struct.unpack('<H',u.mem_read(w[2]+0xea,2))[0],937)
  self.call(u,'destroy',0x10001000);self.assertFalse(self.live)
  for a in (0x5339199c,0x53393d84,0x5339a908,0x53396944,0x53390ca0,0x53390ef8,0x5339a9a0,0x53396f80,0x5316cde8):self.assertIn(a,self.executed)
 def test_original_stamp_rows_and_value_preview(self):
  u=self.machine();self.call(u,'create',0x10001000);w=self.widgets(u)
  self.state(u,3,2);self.call(u,'draw',0x10001000,0x10002000,0)
  self.assertEqual([u.mem_read(w[29+i]+0xee,1)[0] for i in range(4)],[31,31,10,31])
  self.assertEqual([u.mem_read(w[16+i]+0x9e,1)[0] for i in range(5)],[0]*5)
  self.assertEqual([struct.unpack('<H',u.mem_read(w[33+i]+0xea,2))[0] for i in range(4)],[951,955,960,961])
  self.assertEqual([u.mem_read(w[21+i]+0x9e,1)[0] for i in range(4)],[0,0,1,0])
  self.assertEqual([u.mem_read(w[25+i]+0x9e,1)[0] for i in range(4)],[0,0,1,0])
  self.state(u,4,2);self.call(u,'draw',0x10001000,0x10002000,0)
  self.assertEqual(struct.unpack('<H',u.mem_read(w[35]+0xea,2))[0],958)
  self.assertEqual(struct.unpack('<H',u.mem_read(w[2]+0xea,2))[0],967)
  self.assertEqual([u.mem_read(w[29+i]+0xee,1)[0] for i in range(4)],[31]*4)
  self.assertEqual([u.mem_read(w[33+i]+0xee,1)[0] for i in range(4)],[31,31,10,31])
  self.call(u,'destroy',0x10001000);self.assertFalse(self.live)
 def test_each_top_level_allocation_failure_cleans_partial_tree(self):
  for failure in range(1,38):
   with self.subTest(failure=failure):
    u=self.machine(failure);self.assertEqual(self.call(u,'create',0x10001000),0xffffffff)
    self.assertFalse(self.live);self.assertEqual(bytes(u.mem_read(0x10001000,164)),bytes(164))
 def test_actual_glyph_palette_branch_distinguishes_yellow_from_white(self):
  u=self.machine();descriptor=0x10003000
  for style,table,pixel in [(6,0x53b4dbec,0xffffffff),(31,0x53b4dbec,0xffffffff),(10,0x53b4dc6c,0xff00e1ff)]:
   u.mem_write(descriptor+0x25,bytes([style]));u.reg_write(UC_ARM_REG_R7,descriptor)
   u.emu_start(0x53208fec,0x53209018,count=32)
   self.assertEqual(u.reg_read(UC_ARM_REG_PC),0x53209018)
   self.assertEqual(u.reg_read(UC_ARM_REG_R10),table)
   self.assertEqual(struct.unpack('<I',u.mem_read(table+60,4))[0],pixel)
 def test_every_stamp_row_has_one_visible_frame_and_films_clear_all_rows(self):
  u=self.machine();self.call(u,'create',0x10001000);w=self.widgets(u)
  for focus in range(4):
   self.state(u,3,focus);self.call(u,'draw',0x10001000,0x10002000,0)
   self.assertEqual([u.mem_read(w[21+i]+0x9e,1)[0] for i in range(4)],[int(i==focus) for i in range(4)])
   self.assertEqual([u.mem_read(w[21+i]+0xea,1)[0] for i in range(4)],[6]*4)
   self.assertEqual([u.mem_read(w[6+i]+0x9e,1)[0] for i in range(5)],[0]*5)
  self.state(u,5,0);self.call(u,'draw',0x10001000,0x10002000,0)
  self.assertEqual(struct.unpack('<H',u.mem_read(w[2]+0xea,2))[0],990)
  self.assertEqual(struct.unpack('<H',u.mem_read(w[29]+0xea,2))[0],989)
  self.assertEqual([u.mem_read(w[29+i]+0x9e,1)[0] for i in range(4)],[1,0,0,0])
  self.state(u,1,4);self.call(u,'draw',0x10001000,0x10002000,0)
  self.assertEqual([u.mem_read(w[21+i]+0x9e,1)[0] for i in range(4)],[0]*4)
  self.assertEqual([u.mem_read(w[6+i]+0xea,1)[0] for i in range(5)],[1,1,1,1,6])
  outer=struct.unpack('<4I',u.mem_read(w[6]+0x20,16));inner=struct.unpack('<4I',u.mem_read(w[11]+0x20,16))
  self.assertEqual(outer,(24,102,128,204));self.assertEqual(inner,(26,104,124,200))
  self.assertEqual(struct.unpack('<4I',u.mem_read(w[16]+0x20,16)),(28,106,120,196))
 def test_zoom_three_rows_direct_draft_error_and_no_film_allocation(self):
  u=self.machine();self.call(u,'create',0x10001000);w=self.widgets(u);heap=self.heap
  # saved state, editor, focus/editing/closed/error/selected
  u.mem_write(0x10002000,struct.pack('<IHH8I',9,35,50,9,1,49,2,1,0,1,0))
  self.call(u,'zoom',0x10001000,0x10002000)
  self.assertEqual(self.heap,heap)
  self.assertEqual([u.mem_read(w[29+i]+0x9e,1)[0] for i in range(4)],[1,1,1,0])
  self.assertEqual([u.mem_read(w[33+i]+0x9e,1)[0] for i in range(4)],[0,1,1,0])
  self.assertEqual([u.mem_read(w[16+i]+0x9e,1)[0] for i in range(5)],[0]*5)
  self.assertEqual([u.mem_read(w[21+i]+0x9e,1)[0] for i in range(4)],[0,0,1,0])
  cap=lambda index:struct.unpack('<H',u.mem_read(w[index]+0xea,2))[0]
  self.assertEqual([cap(i) for i in (2,4,5,29,30,31,34,35)],[1024,1028,1029,2,1025,1026,1038,1052])
  self.assertEqual(u.mem_read(w[5]+0x9e,1)[0],1)
  self.call(u,'destroy',0x10001000);self.assertFalse(self.live)

 def test_catalog_highlights_actual_index_and_hides_empty_last_page_entries(self):
  u=self.machine();self.call(u,'create',0x10001000);w=self.widgets(u);self.state(u,2,4)
  u.mem_write(0x10002000+116,struct.pack('<I',6))
  u.mem_write(0x10003000,struct.pack('<5I',0,0,0x540b0010,0,0))
  self.call(u,'draw',0x10001000,0x10002000,0x10003000)
  self.assertEqual([u.mem_read(w[6+i]+0xea,1)[0] for i in range(5)],[1,6,1,1,1])
  self.assertEqual([u.mem_read(w[16+i]+0x9e,1)[0] for i in range(5)],[1,1,0,0,0])
  self.assertEqual(struct.unpack('<H',u.mem_read(w[2]+0xea,2))[0],969)
  p=struct.unpack('<I',u.mem_read(w[3]+0xf0,4))[0]
  self.assertEqual(bytes(u.mem_read(p,20)),'7  PORTRA\0'.encode('utf-16le'))



 def test_film_names_do_not_alias_watermark_captions(self):
  from scripts.build_gr3_m10v_library import build
  with tempfile.TemporaryDirectory() as folder:
   m=build(Path(folder),sd_library=True)
   texts=m['resources']['texts']
   self.assertEqual(texts[978-786:988-786],['Portra 160','富士业务用 100','乐凯 C200','CCD Classic','富士 C200','ProImage 100','T-Max 100','Aerochrome','2460','5203'])

 def test_custom_slot_cards_use_each_saved_name_and_safe_fallback_icon(self):
  names={0:'LOMO',1:'Portra 400',2:'Night LUT',3:'My Film',4:'CUSTOM'}
  u=self.machine(custom_names=names);self.call(u,'create',0x10001000);self.state(u,1,0)
  for i in range(5):u.mem_write(0x10002000+12+8*i,struct.pack('<H',79+i))
  self.call(u,'draw',0x10001000,0x10002000,0)
  w=self.widgets(u);heap=w[39];images=[]
  for i in range(5):images.append(bytes(u.mem_read(heap+i*120*196*4,120*196*4)))
  self.assertEqual(len(set(images)),5)
  text=struct.unpack('<I',u.mem_read(w[3]+0xf0,4))[0]
  self.assertEqual(bytes(u.mem_read(text,24)),'1 / 5  LOMO\0'.encode('utf-16le'))
  self.call(u,'destroy',0x10001000);self.assertFalse(self.live)
  u=self.machine(fail_cards=True);self.call(u,'create',0x10001000);self.state(u,1,0)
  u.mem_write(0x10002000+12,struct.pack('<H',79));self.call(u,'draw',0x10001000,0x10002000,0)
  w=self.widgets(u);self.assertEqual(struct.unpack('<H',u.mem_read(w[16]+0xea,2))[0],754)
  self.call(u,'destroy',0x10001000);self.assertFalse(self.live)

 def test_custom_directory_tail_draws_cards_and_two_digit_page_numbers(self):
  u=self.machine(custom_names={250:'User LUT',251:'Night LUT'},catalog_ids={250:285,251:286})
  self.call(u,'create',0x10001000)
  state=bytearray(216);struct.pack_into('<8I',state,184,2,0,0,251,286,0,0,254)
  u.mem_write(0x10002000,bytes(state))
  ops=0x10003000;u.mem_write(ops,struct.pack('<7I',0,0,0x540b0010,0,0,0,0))
  self.call(u,'draw',0x10001000,0x10002000,ops)
  w=struct.unpack('<56I',u.mem_read(0x10001000,224))
  self.assertEqual([u.mem_read(w[26+i]+0x9e,1)[0] for i in range(10)],[1,1,0,0,0,0,0,0,0,0])
  self.assertEqual([u.mem_read(w[6+i]+0xea,1)[0] for i in range(2)],[1,6])
  heap=w[55]
  self.assertNotEqual(bytes(u.mem_read(heap,120*148*4)),bytes(u.mem_read(heap+120*148*4,120*148*4)))
  text=struct.unpack('<I',u.mem_read(w[52]+0xf0,4))[0]
  self.assertEqual(bytes(u.mem_read(text,12)),'26/26\0'.encode('utf-16le'))
  self.call(u,'destroy',0x10001000);self.assertFalse(self.live)

 def test_custom_catalog_page_uses_each_absolute_index_and_complete_focus_name(self):
  u=self.machine(custom_names={5:'LOMO',6:'Night LUT'},catalog_ids={5:79,6:80})
  self.call(u,'create',0x10001000);self.state(u,2,0)
  u.mem_write(0x10002000+116,struct.pack('<I',6))
  u.mem_write(0x10003000,struct.pack('<5I',0,0,0x540b0010,0,0))
  self.call(u,'draw',0x10001000,0x10002000,0x10003000)
  w=self.widgets(u);heap=w[39]
  self.assertNotEqual(bytes(u.mem_read(heap,120*196*4)),bytes(u.mem_read(heap+120*196*4,120*196*4)))
  self.assertEqual([u.mem_read(w[16+i]+0x9e,1)[0] for i in range(5)],[1,1,0,0,0])
  text=struct.unpack('<I',u.mem_read(w[3]+0xf0,4))[0]
  self.assertEqual(bytes(u.mem_read(text,26)),'7  Night LUT\0'.encode('utf-16le'))
  self.call(u,'destroy',0x10001000);self.assertFalse(self.live)

if __name__=='__main__':unittest.main()
