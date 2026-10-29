"""Oriented glyphs preserve image/state ABI and touch only valid visible samples."""
import ctypes as C
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import numpy as np
from tests.test_gr3_m10v_library import Image, Date, Slot
ROOT=Path(__file__).resolve().parents[1]
class State(C.Structure):
 _fields_=[('magic',C.c_uint32),('version',C.c_uint16),('size',C.c_uint16),('sequence',C.c_uint32),('slots',Slot*10),('stamp',C.c_uint8),('format',C.c_uint8),('corner',C.c_uint8),('color',C.c_uint8),('effects',(C.c_uint8*8)*10),('reserved',C.c_uint32),('crc',C.c_uint32)]
class StampOrientationTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
  p=Path(cls.tmp.name);src=p/'probe.c';out=p/'probe.dylib'
  src.write_text('#include "'+str(ROOT/'native/gr3/m10v_library.c')+'"\nvoid probe(m10v_library_image *i,const m10v_library_state*s,const m10v_library_date*d,const char*n,unsigned o){stamp_oriented(i,s,d,n,o);}\n')
  sources=['halation_core.c','film_5207.c','film_harman.c','film_curated.c','film_newstocks.c','film_style_filters_0.c','film_style_filters_1.c','film_d76_0.c','film_d76_1.c']
  subprocess.run([shutil.which('clang'),'-O2','-dynamiclib',str(src),*[str(ROOT/'native/gr3'/x) for x in sources],'-o',str(out)],capture_output=True,check=True)
  cls.lib=C.CDLL(str(out));cls.lib.probe.argtypes=[C.POINTER(Image),C.POINTER(State),C.POINTER(Date),C.c_char_p,C.c_uint32]
 def draw(self,w,h,direction=0,corner=0,mode=2,name=b'KODAK 5207',date=None,stride=None):
  stride=stride or w+6
  y=np.full((h+1,stride),73,dtype=np.uint8);c=np.full_like(y,129)
  image=Image(y.ctypes.data_as(C.POINTER(C.c_uint8)),c.ctypes.data_as(C.POINTER(C.c_uint8)),stride*h,stride*h,w,h,stride)
  s=State();s.stamp=mode;s.corner=corner;s.color=2;s.reserved=int(name is not None)
  date=date or Date(2026,10,28,23,59)
  self.lib.probe(C.byref(image),C.byref(s),C.byref(date),name,direction)
  self.assertTrue((y[h:]==73).all());self.assertTrue((c[h:]==129).all())
  self.assertTrue((y[:h,w:]==73).all());self.assertTrue((c[:h,w:]==129).all())
  return y[:h,:w].copy(),c[:h,:w].copy()
 def test_four_directions_four_display_corners_and_two_lines(self):
  for mode in (1,2):
   for corner in range(4):
    for d in range(4):
     with self.subTest(mode=mode,corner=corner,direction=d):
      w,h=640,420
      lw,lh=(h,w) if d&1 else (w,h)
      expected,_=self.draw(lw,lh,corner=corner,mode=mode)
      actual,_=self.draw(w,h,d,corner,mode)
      np.testing.assert_array_equal(np.rot90(actual,d),expected)
      self.assertGreater(np.count_nonzero(actual!=73),0)
 def test_landscape_preserves_prechange_glyphs_and_layout(self):
  # SHA256 from unmodified HEAD C compiled with the current184-byte state ABI.
  import hashlib
  for mode,corner,digest in ((1,0,'cbc5578a41095c3ee3e321c0f6b83bf181c64f24e2f5e4fae053173c840db752'),(0,1,'8032fe63750342c8a71560ef68969fff86f9f6855f90e7711939c7d39ce5e48f'),(2,3,'64ba324270b7e3590e0d7087d569e4bcaad1780f60a7d5939f608f58edf3b17e')):
   y,c=self.draw(320,240,corner=corner,mode=mode)
   self.assertEqual(hashlib.sha256(y.tobytes()+c.tobytes()).hexdigest(),digest)
 def test_unknown_is_landscape_and_no_text_is_zero_work(self):
  expected=self.draw(320,240)
  for d in (4,255,0xffffffff):
   actual=self.draw(320,240,d)
   for a,b in zip(actual,expected):np.testing.assert_array_equal(a,b)
  for d in range(4):
   y,c=self.draw(320,240,d,mode=0,name=None)
   self.assertTrue((y==73).all());self.assertTrue((c==129).all())
 def test_public_render_rejects_odd_layouts_before_pixel_mutation(self):
  import zlib
  class Context(C.Structure):
   _fields_=[('direction',C.c_uint32),('completed',C.c_uint32),('lut',C.c_void_p),('name',C.c_char_p)]
  self.lib.m10v_library_render_oriented.argtypes=[C.POINTER(Image),C.POINTER(State),C.c_uint32,C.POINTER(Date),C.c_uint32,C.c_void_p,C.c_uint32,C.POINTER(Context)]
  state=State();self.lib.m10v_library_init(C.byref(state));state.slots[0].film=66;state.stamp=2
  state.crc=zlib.crc32(bytes(state)[:180]);original=bytes(state)
  for w,h,stride in ((3,3,5),(16,8,19),(2,1,3),(321,241,324)):
   for direction in range(4):
    y=(C.c_uint8*(stride*h))(*([73]*(stride*h)));c=(C.c_uint8*(stride*h))(*([129]*(stride*h)))
    image=Image(y,c,len(y),len(c),w,h,stride);date=Date(2026,10,28,23,59)
    self.assertEqual(self.lib.m10v_library_render_oriented(C.byref(image),C.byref(state),0,C.byref(date),0,None,0,C.byref(Context(direction,31,None,None))),-1)
    self.assertEqual(bytes(y),bytes([73])*len(y));self.assertEqual(bytes(c),bytes([129])*len(c));self.assertEqual(bytes(state),original)
 def test_tiny_odd_width_stride_and_invalid_date_name_only(self):
  for w,h in ((2,1),(3,3),(17,19),(65,49),(321,241)):
   for d in range(4):self.draw(w,h,d,stride=w+2)
  for d in range(4):
   y,_=self.draw(320,240,d,date=Date(0,0,0,0,0));self.assertGreater(np.count_nonzero(y!=73),0)

class StampRecipeDirectionTests(unittest.TestCase):
 """Original task construction publishes a shot-owned direction, never live UI."""
 @classmethod
 def setUpClass(cls):
  from scripts.build_gr3_m10v_library import build, capture_stock_rtos
  cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
  folder=Path(cls.tmp.name)
  cls.manifest=build(folder,base=0x540be000,sd_library=True,lifecycle_trace=True,recipe_snapshot=True,native_color=True,native_grain=True,live_color=True,appended_slots=True,custom_zoom=False,hdf_enabled=False)
  image=bytearray(capture_stock_rtos());base=cls.manifest['base'];blob=(folder/'m10v-library-arm.bin').read_bytes()
  image.extend(bytes(max(0,base-0x53000000+len(blob)-len(image))));image[base-0x53000000:base-0x53000000+len(blob)]=blob
  for group in (cls.manifest['capture_lifecycle'],cls.manifest['appended_slots']):
   for p in group['patches']:
    at=p['address']-0x53000000;image[at:at+4]=bytes.fromhex(p['replacement_hex']) if 'replacement_hex' in p else p['replacement'].to_bytes(4,'little')
  from scripts.build_gr3_menu_patches import branch
  for p in cls.manifest['isp_base']['patches']:
   at=p['address']-0x53000000;image[at:at+4]=branch(p['address'],p['entry']).to_bytes(4,'little')
  cls.image=bytes(image)
 def exposure_clock(self,e,si):
  # Execute the original exposure date producer. Only clock/OS boundaries are
  # substituted; the official record writes and frame identity run unchanged.
  from unicorn import UC_HOOK_CODE
  from unicorn import arm_const as A
  clock=e.alloc(8)
  def service(u,at,n,_):
   if at==0x536bd838:u.reg_write(A.UC_ARM_REG_R0,clock)
   elif at==0x536b6510:
    u.mem_write(u.reg_read(A.UC_ARM_REG_R1),bytes([0xea,7,10,28,23,59,42,0]))
   elif at==0x536b5f40:u.reg_write(A.UC_ARM_REG_R0,3)
   elif at==0x536b5ec4:pass
   else:return
   u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
  hook=e.u.hook_add(UC_HOOK_CODE,service)
  e.call(0x534322d8,0,0,si)
  e.u.hook_del(hook)
  self.assertEqual(bytes(e.u.mem_read(si+0x944,8)),bytes([0xea,7,10,28,3,23,59,42]))
 def fixture(self,direction,stamp=2,name=True):
  import struct,zlib
  from tests.test_gr3_film_pipeline_current import CurrentFilmPipelineTests as P
  # Original current-ABI Make/metadata wiring. Clear the convenience snapshot:
  # only the original processing producer below may authorize this frame.
  e,r,o,f,si,req,data=P.fixture(self,film=66)
  self.frame_objects={r:(o,f)};self.requests={r:req}
  e.u.mem_write(r+0x4a08,bytes(1796));e.u.mem_write(r+0x5140,bytes(16))
  state=bytearray(e.u.mem_read(data,184));state[92]=stamp
  struct.pack_into('<I',state,176,int(name));struct.pack_into('<I',state,180,zlib.crc32(state[:180]));e.u.mem_write(data,bytes(state))
  P.publish_owner(self,e,data)
  # Original ShootingInfo field setter, also consumed by the EXIF writer.
  e.call(0x53491530,si,direction)
  self.exposure_clock(e,si)
  # Later UI direction deliberately differs already before processing queues.
  backend=e.alloc(0x600);config=e.alloc(4);live=e.alloc(0x1000)
  e.w32(0x553458b0,backend);e.w32(backend+0x518,config);e.w32(config,live)
  e.call(0x53491530,live,(direction+2)%4)
  P.enqueue(self,e,r,19)
  return e,r,si,live,data
 def call(self,e,name,*args):
  from unicorn import arm_const as A
  e.call(self.manifest['symbols'][name],*args);return e.u.reg_read(A.UC_ARM_REG_R0)
 def capture_stamped(self,e,r,si,request,w,h):
  import struct
  context=r+0x9b8
  for off,value in ((0,0x53d0fbe0),(0x30,r+0x1a8),(0x34,si),(0x38,request),(0x3c,r+0xb0),(0x40,r+0xd0),(0x44,r+0xf0),(0x48,r+0x110),(0x4c,r+0x130)):e.w32(context+off,value)
  e.w32(request,0x53d0fe60);e.u.mem_write(request+12,b'\1\1');e.u.mem_write(r+0x140,b'\1')
  e.w32(r+0x60,0x70000000);dims=e.alloc(4);e.u.mem_write(dims,struct.pack('<HH',6112,4064));e.w32(r+0x230,dims)
  stride=w+6;size=stride*h;yp=e.alloc(size);cp=e.alloc(size)
  e.u.mem_write(yp,bytes([73])*size);e.u.mem_write(cp,bytes([129])*size)
  desc=struct.pack('<4I8H',1,yp,cp,0,w,h,stride,h,0,0,2,0)
  # All secondary descriptors alias the main. Stamping must occur once and no
  # fallback thumbnail path may recolor or re-stamp the same backing planes.
  for off in (0xb0,0xd0,0xf0,0x110):e.u.mem_write(r+off,desc)
  e.services.add(0x5383c8a8)
  self.assertEqual(self.call(e,'m10v_capture_library',context),0)
  y=np.frombuffer(bytes(e.u.mem_read(yp,size)),dtype=np.uint8).reshape(h,stride)
  c=np.frombuffer(bytes(e.u.mem_read(cp,size)),dtype=np.uint8).reshape(h,stride)
  self.assertTrue((y[:,w:]==73).all());self.assertTrue((c[:,w:]==129).all())
  return y[:,:w].copy()
 def test_queued_stamp_reaches_actual_capture_after_ui_rotation_and_aliases(self):
  from tests.test_gr3_film_pipeline_current import CurrentFilmPipelineTests as P
  for direction in range(4):
   with self.subTest(direction=direction):
    e,r,si,live,data=self.fixture(direction)
    # Recover original Make object from its known allocation ordering in P.
    # P.fixture returns obj/frame; retain them explicitly via our fixture.
    obj,frame=self.frame_objects[r]
    e.call(0x53491530,live,(direction+1)%4)
    P.make(self,e,r,obj,frame)
    actual=self.capture_stamped(e,r,si,self.requests[r],640,420)
    e2,r2,si2,_,_=self.fixture(0);obj2,frame2=self.frame_objects[r2]
    P.make(self,e2,r2,obj2,frame2)
    expected=self.capture_stamped(e2,r2,si2,self.requests[r2],420 if direction&1 else 640,640 if direction&1 else 420)
    np.testing.assert_array_equal(np.rot90(actual,direction),expected)
    self.assertGreater(np.count_nonzero(actual!=73),0)
 def test_original_producer_freezes_each_direction_before_later_ui_rotation(self):
  from tests.test_gr3_film_pipeline_current import CurrentFilmPipelineTests as P
  for direction in (0,1,2,3,4,255):
   with self.subTest(direction=direction):
    e,r,si,live,data=self.fixture(direction)
    expected=direction if direction<4 else 0
    self.assertEqual(self.call(e,'m10v_isp_frame_recipe_direction',r,si),expected)
    e.call(0x53491530,live,(direction+1)%4)
    e.call(0x53491530,si,(direction+3)%4)
    P.enqueue(self,e,r,0)
    self.assertEqual(self.call(e,'m10v_isp_frame_recipe_direction',r,si),expected)
    self.assertEqual(self.call(e,'m10v_isp_frame_recipe_direction',r,si+4),0)
 def test_original_exif_writer_and_snapshot_use_the_same_frame_direction(self):
  from unicorn import UC_HOOK_CODE
  from unicorn import arm_const as A
  for direction,exif in ((0,1),(1,8),(2,3),(3,6),(255,1)):
   e,r,si,_,_=self.fixture(direction)
   meta=e.alloc(0x40);one=e.alloc(0x200);two=e.alloc(0x200)
   e.w32(meta+4,one);e.w32(one+4,two);e.w32(meta+8,si);e.w32(meta+0x14,si+0xc8)
   seen=[]
   def sink(u,at,n,_):
    if at==0x535d02c8:
     seen.append(u.reg_read(A.UC_ARM_REG_R2));u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
   hook=e.u.hook_add(UC_HOOK_CODE,sink)
   e.call(0x535f673c,meta,e.alloc(0x100))
   e.u.hook_del(hook)
   self.assertEqual(seen,[exif])
   self.assertEqual(self.call(e,'m10v_isp_frame_recipe_direction',r,si),direction if direction<4 else 0)
 def test_disabled_original_pipeline_reaches_unmapped_24mp_zero_work_path(self):
  from tests.test_gr3_film_pipeline_current import CurrentFilmPipelineTests as P
  e,r,si,_,_=self.fixture(3,stamp=0,name=False)
  obj,frame=self.frame_objects[r]
  P.make(self,e,r,obj,frame)
  self.assertEqual(P.capture(self,e,r,si,self.requests[r]),0)
 def test_sole_allocator_owns_and_initializes_stamp_extent(self):
  from tests.test_gr3_isp_base import StockISP
  from unicorn import UC_HOOK_CODE
  from unicorn import arm_const as A
  e=StockISP(self.image);seen=[];allocation=e.alloc(0x5150)
  e.u.mem_write(allocation,bytes([173])*0x5150)
  def allocate(u,at,n,_):
   if at==0x5351091c:
    seen.append(u.reg_read(A.UC_ARM_REG_R0));u.reg_write(A.UC_ARM_REG_R0,allocation);u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
  e.u.hook_add(UC_HOOK_CODE,allocate)
  self.assertEqual(self.call(e,'m10v_save_trace_recipe_alloc',0x4778),allocation)
  self.assertEqual(seen,[0x5150])
  self.assertEqual(bytes(e.u.mem_read(allocation,0x4778)),bytes([173])*0x4778)
  self.assertEqual(bytes(e.u.mem_read(allocation+0x5140,16)),bytes(16))
  self.assertEqual(int.from_bytes(e.u.mem_read(allocation+0x5114,4),'little'),allocation)
 def test_owner_layout_ends_after_raw_and_hdf_without_moving_them(self):
  owner=self.manifest['capture_lifecycle']['owner']['storage']
  self.assertEqual((owner['color_offset'],owner['color_bytes']),(0x4a08,1796))
  self.assertEqual((owner['raw_token_offset'],owner['raw_token_bytes']),(0x5110,48))
  self.assertEqual((owner['stamp_offset'],owner['stamp_bytes'],owner['extended_recipe_bytes']),(0x5140,16,0x5150))
 def test_disabled_and_corrupt_direction_never_authorize_a_rotation(self):
  import struct
  e,r,si,_,_=self.fixture(1,stamp=0,name=False)
  self.assertEqual(bytes(e.u.mem_read(r+0x5140,16)),bytes(16))
  self.assertEqual(self.call(e,'m10v_isp_frame_recipe_direction',r,si),0)
  for offset,value in ((0,0),(4,r+4),(8,si+4),(12,4)):
   e,r,si,_,_=self.fixture(1)
   e.u.mem_write(r+0x5140+offset,struct.pack('<I',value if offset!=4 else r+4))
   self.assertEqual(self.call(e,'m10v_isp_frame_recipe_direction',r,si),0)

if __name__=='__main__':unittest.main()
