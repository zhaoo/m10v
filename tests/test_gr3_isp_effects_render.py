"""ARM renderer orchestration; real pixel/noise/asset planes remain unmapped."""
from pathlib import Path
import struct,unittest,sys
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn import arm_const as A
from scripts import build_gr3_isp_effect_render as build
BASE=0x54e00000
EXT=dict(zip(build.EXTERNALS,(0x54d00000,0x54d00100,0x54d00200,0x54d00300)))
def bindings():
 at=0x540c0000
 def t(w,h):
  nonlocal at
  s=(w+63)&~63;n=s*h*3//2;d=dict(base=at,bytes=n,width=w,height=h,stride=s);at+=n;return d
 return dict(grain=t(3072,2048),leaks=[[t(256,128),t(256,128)] for _ in range(9)],leaks_vertical=[[t(128,256),t(128,256)] for _ in range(9)])
class RenderTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.code,cls.manifest=build.build(BASE,bindings(),EXT,enabled=True);cls.symbols=cls.manifest['symbols']
 def put(self,p,*v):self.u.mem_write(p,struct.pack('<'+'I'*len(v),*v))
 def words(self,p,n):return struct.unpack('<'+'I'*n,self.u.mem_read(p,n*4))
 def reg(self,n):return self.u.reg_read(getattr(A,'UC_ARM_REG_R'+str(n)))
 def setUp(self):
  self.u=Uc(UC_ARCH_ARM,UC_MODE_ARM);self.u.mem_map(BASE,0x10000);self.u.mem_write(BASE,self.code);self.u.mem_map(0x54d00000,0x10000);self.u.mem_map(0x55000000,0x100000)
  self.photo,self.shot,self.ctx,self.stop=0x55001000,0x55002000,0x55003000,0x550f0000
  self.work,self.y,self.uv=0x63000000,0x60000000,0x61000000;self.w,self.h,self.stride=400,300,416;self.token=0x55012345
  self.calls=[];self.native_count=0;self.fail_at=0;self.fail_result=0;self.mutate=False;self.plan_result=1
  self.configure();self.u.hook_add(UC_HOOK_CODE,self.hook)
 def configure(self,fmt=1,grain=2,leak=2,size=1,pos=1,spread=2,orientation=1):
  self.format=fmt;self.capacity=400*300*(2 if fmt==1 and leak else 3/2);self.capacity=int(self.capacity)
  self.put(self.photo,0xabcd0000|fmt,self.y,self.uv,0,self.w|(self.h<<16),self.stride|(self.h<<16),0,2)
  # magic owner ready sequence; settings; plan metadata; state; reserved.
  self.put(self.shot,0x31584653,0x55004000,1,7,leak,pos,spread,0,size,0,0,0,self.w,self.h,self.capacity,grain,1,0,0,self.token,0,0,orientation,0)
 def hook(self,u,pc,size,data):
  if pc not in EXT.values():return
  args=[self.reg(i) for i in range(4)];sp=u.reg_read(A.UC_ARM_REG_SP)
  if pc==EXT[build.EXTERNALS[0]]:
   h,sw,sh,phase,fmt,out=self.words(sp,6);t=self.words(args[0],5);self.calls.append(('plan',t,args[1],args[2],args[3],h,sw,sh,phase,fmt))
   w=args[3];pitch=(w+15)&~15;ny=pitch*h;sy=t[4]*t[3];n=ny*(2 if fmt==1 else 3)//(1 if fmt==1 else 2)
   source=(2,t[0],t[0]+sy,0,sw|(sh<<16),t[4]|(t[3]<<16),0,2)
   dest=(fmt,args[1],args[1]+ny,0,w|(h<<16),pitch|(h<<16),0,2)
   self.put(out,*source,*dest,n);result=self.plan_result
  elif pc==EXT[build.EXTERNALS[1]]:
   self.calls.append(('execute',self.words(args[0],17),args[1]));self.native_count+=1;result=self.fail_result if self.fail_at==self.native_count else 1
   if self.mutate:self.put(self.photo,*([0]*8));self.put(self.shot,*([0]*24))
  elif pc==EXT[build.EXTERNALS[3]]:
   self.calls.append(('luma',args[0],self.words(args[1],8),self.words(args[2],8),args[3]));self.native_count+=1;result=self.fail_result if self.fail_at==self.native_count else 1
  else:
   plane,n,curves=self.words(sp,3);self.calls.append(('granulation',args[0],self.words(args[1],8),self.words(args[2],8),args[3],plane,n,curves));self.native_count+=1;result=self.fail_result if self.fail_at==self.native_count else 1
  u.reg_write(A.UC_ARM_REG_R0,result&0xffffffff);u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
 def invoke(self,capacity=None,work=None):
  self.u.reg_write(A.UC_ARM_REG_SP,0x550e0000);self.put(0x550e0000,self.shot)
  for n,v in enumerate((self.ctx,self.photo,self.work if work is None else work,self.capacity if capacity is None else capacity)):self.u.reg_write(getattr(A,'UC_ARM_REG_R'+str(n)),v)
  self.u.reg_write(A.UC_ARM_REG_LR,self.stop);self.u.emu_start(self.symbols['m10v_isp_effects_render'],self.stop,count=100000)
  r=self.reg(0);return r if r<0x80000000 else r-0x100000000
 def test_saved_orientation_selects_display_edge_with_no_native_pixel_rotation(self):
  for orientation,vertical,swap in ((1,False,False),(3,False,True),(8,True,False),(6,True,True)):
   for position in (0,1,2):
    self.configure(grain=0,leak=1,pos=position,spread=0,orientation=orientation);self.calls=[]
    self.assertEqual(self.invoke(),1);plans=[c for c in self.calls if c[0]=='plan'];self.assertEqual(len(plans),2)
    sensor_position=position^1 if swap and position<2 else position
    expected=bindings()['leaks_vertical' if vertical else 'leaks'][sensor_position*3]
    self.assertEqual([c[1][0] for c in plans],[p['base'] for p in expected])
  for invalid in (0,2,4,5,7,9):
   self.configure(orientation=invalid);self.calls=[];self.assertEqual(self.invoke(),-1);self.assertFalse(self.calls)
 def test_roi_normalizes_only_owned_metadata_and_preserves_full_allocation(self):
  for fmt in (1,2):
   self.configure(fmt=fmt,grain=1,leak=1);self.calls=[]
   rows=self.h+4;left,top=4,2
   self.put(self.photo+20,self.stride|(rows<<16));self.put(self.photo+24,left|(top<<16))
   before=bytes(self.u.mem_read(self.photo,32));self.assertEqual(self.invoke(),1)
   calls=[c for c in self.calls if c[0]=='granulation'];yoffset=top*self.stride+left;uvoffset=(top if fmt==1 else top//2)*self.stride+left
   self.assertEqual(calls[2][2][1],self.y+yoffset);self.assertEqual(calls[2][2][2],self.uv+uvoffset)
   self.assertEqual(calls[2][2][6],0);self.assertEqual(calls[2][2][5]>>16,self.h)
   self.assertEqual(calls[0][2][1],self.uv+uvoffset)
   self.assertEqual(bytes(self.u.mem_read(self.photo,32)),before)
 def test_original_granulation_constructors_bind_normalized_roi_planes_and_byte_strides(self):
  sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
  from scripts.analyze_gr3_border_iip import OriginalArm
  root=Path(__file__).resolve().parents[1]
  for model in ('gr3','gr3x'):
   for fmt in (1,2):
    self.configure(fmt=fmt,grain=1,leak=1);self.calls=[]
    self.put(self.photo+20,self.stride|(304<<16));self.put(self.photo+24,4|(2<<16));self.assertEqual(self.invoke(),1)
    gr=[c[2] for c in self.calls if c[0]=='granulation'];views=[gr[2],gr[0]]
    rom=(root/f'builds/gr3-pure-isp-feasibility-20261031/{model}-official-rtos.bin').read_bytes()
    for view in views:
     p=OriginalArm(rom);frame,abstract=0x55090000,0x55080000;allocated=[]
     p.words(abstract,*view);p.words(frame-0x644,view[4]>>16);p.words(frame-0x64c,view[4]&65535)
     p.words(frame-0x658,abstract);p.words(frame-0x654,abstract);p.words(frame-0x648,0x63000000);p.words(frame-0x650,400)
     def allocate():
      address=0x55100000+len(allocated)*0x1000;allocated.append(address);return address
     p.boundaries={0x536af2a8:allocate}
     p.u.reg_write(A.UC_ARM_REG_FP,frame);p.u.reg_write(A.UC_ARM_REG_SP,frame-0x800)
     p.u.emu_start(0x5367af34,0x5367afdc,count=1000)
     self.assertEqual(len(allocated),2)
     # Original source/destination byte descriptors use normalized photo
     # plane0; source extra plane+48 binds prepared noise with its own pitch.
     self.assertEqual(p.read_words(allocated[0]+0x3c,1)[0],view[1])
     self.assertEqual(p.read_words(allocated[0]+0x2c,1)[0],view[5]&65535)
     self.assertEqual(tuple(struct.unpack('<HH',p.u.mem_read(allocated[0]+0x28,4))),(view[4]&65535,view[4]>>16))
     self.assertEqual(p.read_words(allocated[1]+0x3c,1)[0],view[1])
     self.assertEqual(p.read_words(allocated[1]+0x2c,1)[0],view[5]&65535)
     self.assertEqual(p.read_words(allocated[0]+0x48,1)[0],0x63000000)
     self.assertEqual(p.read_words(allocated[0]+0x38,1)[0],400)
     cache=[]
     p.boundaries={0x536bbc30:lambda:0,0x536bbcac:lambda:cache.append((p.u.reg_read(A.UC_ARM_REG_R1),p.u.reg_read(A.UC_ARM_REG_R2)))}
     p.call(0x5376bd18,allocated[0]);p.call(0x5376bd18,allocated[1])
     expected_height=view[4]>>16
     self.assertIn((view[1],self.stride*expected_height),cache)
     self.assertIn((0x63000000,400*expected_height),cache)
     self.assertEqual(p.assertions,[])
 def test_invalid_roi_or_granulation_cache_tail_rejects_before_any_native_call(self):
  for fmt,left,top,rows in ((1,17,0,304),(1,4,5,304),(2,4,1,304),(1,2,0,304),(1,4,0,300),(2,4,0,300)):
   self.configure(fmt=fmt,grain=1,leak=1);self.calls=[]
   self.put(self.photo+20,self.stride|(rows<<16));self.put(self.photo+24,left|(top<<16))
   before=bytes(self.u.mem_read(self.photo,32));self.assertEqual(self.invoke(),-1);self.assertFalse(self.calls)
   self.assertEqual(bytes(self.u.mem_read(self.photo,32)),before)
 def test_native_order_real_422_uv_extent_and_exact_grain_crop_phase(self):
  self.assertEqual(self.invoke(),1);self.assertEqual([c[0] for c in self.calls],['plan','execute','luma','granulation','plan','execute','luma','granulation','granulation','plan','execute','granulation'])
  plans=[c for c in self.calls if c[0]=='plan'];self.assertEqual([c[-1] for c in plans],[1,1,2]);self.assertEqual(plans[-1][6:9],(1500,1000,self.token&63))
  grains=[c for c in self.calls if c[0]=='granulation'];self.assertEqual([c[4] for c in grains],[1,1,1,2]);self.assertEqual([c[5] for c in grains],[self.work+120000,self.work+120000,self.work,self.work]);self.assertEqual([c[6] for c in grains],[120000]*4)
  self.assertEqual(grains[1][2][1:3],(self.uv,0));self.assertEqual(grains[1][2][4]>>16,self.h);self.assertEqual(grains[1][2][5]&65535,self.stride);self.assertEqual(grains[-1][7],0)
 def test_upper_data_bank_workspace_and_photo_planes_reach_native_services(self):
  self.work,self.y,self.uv=0xA4000000,0xB0000000,0xB1000000
  self.configure()
  self.assertEqual(self.invoke(),1)
  self.assertEqual([c[5] for c in self.calls if c[0]=='granulation'],[self.work+120000,self.work+120000,self.work,self.work])
 def test_effective_grain_strength_maps_to_reversed_original_argument(self):
  for effective,native in ((1,3),(2,2),(3,1)):
   self.configure(grain=effective,leak=0);self.calls=[];self.assertEqual(self.invoke(),1)
   grain=[c for c in self.calls if c[0]=='granulation'];self.assertEqual(len(grain),1);self.assertEqual(grain[0][4],native)
 def test_nv12_uv_has_half_height_and_all_profiles_are_build_time(self):
  self.configure(fmt=2);self.assertEqual(self.invoke(),1)
  gran=[c for c in self.calls if c[0]=='granulation'];self.assertEqual(gran[1][2][4]>>16,150);self.assertEqual(gran[1][6],60000)
  curves=self.symbols['m10v_render_curves'];all_c=struct.unpack('<7680h',self.u.mem_read(curves,15360));self.assertTrue(all(0<=v<=255 for v in all_c))
  self.assertEqual(all_c,tuple(v for profile in build.leak_curves() for row in profile for v in row))
  self.assertEqual(all_c[255+256],255) # white luma remains white
  self.assertEqual(all_c[9*768:9*768+256],(0,)*256)
  for profile in range(9):self.assertEqual(all_c[profile*768+256:profile*768+512],tuple(range(256)))
  gates=[c for c in self.calls if c[0]=='luma'];self.assertEqual(len(gates),2)
  for c in gates:self.assertEqual(c[2][1],self.work+120000);self.assertEqual(c[3][1],self.y)
 def test_freezes_original_inputs_across_native_calls(self):
  self.mutate=True;self.assertEqual(self.invoke(),1)
  self.assertEqual([c[2] for c in self.calls if c[0]=='execute'],[self.token]*3)
  gran=[c for c in self.calls if c[0]=='granulation'];self.assertEqual(gran[-1][2][1],self.y);self.assertEqual(gran[-1][2][4]&65535,self.w)
 def test_every_native_non_success_stops_and_invalidates_output(self):
  for failure in (0,-1,-3,-4,2):
   for at in range(1,10):
    self.calls=[];self.native_count=0;self.fail_result=failure;self.fail_at=at
    self.assertEqual(self.invoke(),-4);self.assertEqual(self.native_count,at)
 def test_planning_non_success_never_submits_and_invalid_metadata_never_calls(self):
  for result in (0,-1,2):
   self.calls=[];self.plan_result=result;self.assertEqual(self.invoke(),-4);self.assertEqual([c[0] for c in self.calls],['plan'])
  self.plan_result=1
  for address,value in ((self.shot,0),(self.shot+16,4),(self.shot+32,3),(self.shot+64,2),(self.photo+8,self.y),(self.photo+24,2)):
   self.configure();self.calls=[];self.put(address,value);self.assertEqual(self.invoke(),-1);self.assertFalse(self.calls)
 def test_bounds_reject_short_or_overlapping_work_without_native_calls(self):
  for cap,work in ((self.capacity-1,self.work),(self.capacity,self.y),(self.capacity,self.uv),(self.capacity,self.photo),(self.capacity,self.shot),(self.capacity,0x550d0000),(self.capacity,self.ctx)):
   self.calls=[];self.assertEqual(self.invoke(cap,work),-1);self.assertFalse(self.calls)
 def test_disabled_and_grain_sizes(self):
  self.configure(grain=0,leak=0);self.assertEqual(self.invoke(0,0),1);self.assertFalse(self.calls)
  for size,crop in enumerate(((3000,2000),(1500,1000),(1008,672))):
   self.configure(grain=1,leak=0,size=size);self.calls=[];self.assertEqual(self.invoke(),1);self.assertEqual(self.calls[0][6:8],crop);self.assertEqual(len(self.calls),3)
 def test_builder_disabled_and_rejects_unbounded_overlapping_bindings(self):
  self.assertEqual(build.build()[0],b'');self.assertFalse(self.manifest['pixel_math_proven'])
  for change in ('length','overlap','code','external'):
   b=bindings();e=dict(EXT)
   if change=='length':b['grain']['bytes']-=1
   elif change=='overlap':b['leaks'][0][0]['base']=b['grain']['base']
   elif change=='code':b['leaks'][0][0]['base']=BASE
   else:e[build.EXTERNALS[0]]=BASE
   with self.assertRaises(ValueError):build.build(BASE,b,e,enabled=True)
if __name__=='__main__':unittest.main()
