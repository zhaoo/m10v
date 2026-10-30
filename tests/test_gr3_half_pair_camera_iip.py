"""Owned-RAM pairing adapter ARM tests with every image address UNMAPPED.

Only scalar recipe/session/packet/stack RAM exists. Native IIP completion is a
named boundary here; tests/test_gr3_half_pair_iip.py tests its native queue ABI.
No image values, DMA, SD, camera throughput or physical completion are emulated.
Set M10V_HALF_IIP_FINAL to an audited candidate folder to run its unmodified
camera adapter/plan code rather than source-built objects on the r6 foundation.
"""
import hashlib,json,os,struct,subprocess,tempfile,unittest
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE,UcError
from unicorn import arm_const as A
from scripts.build_gr3_m10v_library import FLAGS,link_object
ROOT=Path(__file__).resolve().parents[1]

class HalfPairCameraIIP(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup);directory=Path(cls.tmp.name)
  # Obtain offsets from the real private C structs; no test-only production API.
  helper=directory/'layout.c'
  helper.write_text('''#include <stdio.h>
#include "m10v_half_pair_camera.c"
int m10v_half_pair_plan(uint32_t a,uint32_t b,uint32_t c,uint32_t d,m10v_half_pair_plan_info *out){return 0;}
int m10v_half_pair_iip_ready(void){return 0;}
int m10v_half_pair_iip_copy(uint32_t t,const uint32_t a[8],const uint32_t b[8]){return 0;}
int m10v_half_pair_iip_compose(uint32_t t,const uint32_t a[8],const uint32_t b[8],const uint32_t c[8],const uint32_t d[2][8],uint32_t o){return 0;}
uint32_t m10v_save_trace_recipe_raw_status(uint32_t a,uint32_t b,uint32_t c,uint32_t d){return 2;}
int main(void){printf("%u %u %u %u %u %u",(unsigned)(M10V_SETTINGS_OWNER_BYTES+offsetof(m10v_settings_controller,half_pair)),(unsigned)sizeof(session),(unsigned)offsetof(session,first),(unsigned)offsetof(session,orientation),(unsigned)offsetof(session,cookie),(unsigned)sizeof(((m10v_settings_controller*)0)->half_pair));}
''')
  subprocess.run(['clang','-I',str(ROOT/'native/gr3'),str(helper),'-o',str(directory/'layout')],check=True,capture_output=True)
  cls.offset,cls.state_bytes,cls.first_offset,cls.orientation_offset,cls.cookie_offset,cls.storage_bytes=map(int,subprocess.check_output([str(directory/'layout')]).split())
  final=os.environ.get('M10V_HALF_IIP_FINAL');folder=Path(final or ROOT/'builds/gr3-half-frame-r6-debug-final-20261030')
  cls.manifest=json.loads((folder/'manifest.json').read_text());cls.image=bytearray((folder/'final-rtos.bin').read_bytes());cls.symbols=dict(cls.manifest['symbols'])
  if final:
   base=cls.manifest['base']-0x53000000;size=cls.manifest['code_bytes']
   assert hashlib.sha256(cls.image[base:base+size]).hexdigest()==cls.manifest['code_sha256']
   cls.boundary={name:cls.symbols[name] for name in('m10v_half_pair_iip_ready','m10v_half_pair_iip_copy','m10v_half_pair_iip_compose','m10v_debug_log','m10v_save_trace_recipe_raw_status')}
  else:
   cls.boundary={name:0x53000100+4*i for i,name in enumerate(('m10v_half_pair_iip_ready','m10v_half_pair_iip_copy','m10v_half_pair_iip_compose','m10v_debug_log','m10v_save_trace_recipe_raw_status'))}
   at=0x54800000;image=bytearray()
   for name,prefix,extra,omitted in [('m10v_half_pair.c','m10v_half_pair_',(),('m10v_half_pair_compose',)),('m10v_half_pair_camera.c','m10v_half_pair_camera',('m10v_half_pair_init','m10v_half_pair_destroy','m10v_half_pair_reset','m10v_half_pair_select'),())]:
    obj=directory/(name+'.o');flags=[f for f in FLAGS if f!='-Os']+['-O2','-DM10V_DEBUG_MODE=1','-DM10V_HALF_PAIR_PLANS_ONLY=1','-fno-jump-tables']
    subprocess.run(['clang',*flags,'-c',str(ROOT/'native/gr3'/name),'-o',str(obj)],check=True,capture_output=True)
    while len(image)%16:image.append(0)
    code,exports=link_object(obj.read_bytes(),at+len(image),{**cls.symbols,**cls.boundary},prefix,additional_exports=extra,omitted_exports=omitted)
    image.extend(code);cls.symbols.update(exports)
   cls.image.extend(bytes(max(0,at-0x53000000+len(image)-len(cls.image))));cls.image[at-0x53000000:at-0x53000000+len(image)]=image
  cls.boundary['foundation_debug']=cls.manifest['symbols']['m10v_debug_log']
  cls.leave_original=cls.manifest['settings_menu']['exports']['m10v_ab_live_leave_original']
 def setUp(self):
  self.u=u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0x53000000,(len(self.image)+4095)&~4095);u.mem_write(0x53000000,bytes(self.image));u.mem_map(0x55000000,0x1000000)
  self.owner=0x550d0000;self.state=self.owner+self.offset;self.manager=0x55004000;self.clock=100;self.fail_clock=False;self.clock_calls=[]
  self.allocations=[];self.frees=[];self.copies=[];self.compositions=[];self.events=[];self.timeline=[];self.next_token=0x70000004;self.token_step=0x1000000
  self.fail_alloc=False;self.fail_copy=False;self.fail_compose=False;self.ready=True;self.queue_cancel=False;self.sleep_action=None
  self.put(0x55063910,1);self.put(0x55063988,self.owner);self.put(self.owner+0x13bc,self.manifest['settings_menu']['vtable'])
  self.u.hook_add(UC_HOOK_CODE,self.service);self.call('m10v_half_pair_init',self.owner)
 def put(self,at,value):self.u.mem_write(at,struct.pack('<I',value))
 def words(self,at,*values):self.u.mem_write(at,struct.pack('<'+'I'*len(values),*values))
 def get(self,at):return struct.unpack('<I',self.u.mem_read(at,4))[0]
 def desc(self,at):return struct.unpack('<8I',self.u.mem_read(at,32))
 def token(self):return self.get(self.state+self.first_offset)
 def expose(self,index=0,w=32,h=16,direction=0,half=True):
  recipe=0x55010000+index*0x10000;si=0x55100000+index*0x80000;req=recipe+0x8000;context=recipe+0x9b8;bank=0x60000004+index*0x1000000
  self.words(recipe,0x53d0fc90);self.put(recipe+0x4778,0x31545653);self.put(recipe+0x44c8,si);self.put(recipe+0x5c,req)
  self.words(req,0x53d0fe60);self.u.mem_write(req+12,b'\1\0');self.u.mem_write(si+0x7b6,bytes([6 if half else 0]));self.u.mem_write(si+0xc8,bytes([direction]));self.u.mem_write(recipe+0x140,b'\1')
  for off,value in((0,0x53d0fbe0),(0x30,recipe+0x1a8),(0x34,si),(0x38,req),(0x3c,recipe+0xb0),(0x40,recipe+0xd0),(0x44,recipe+0xf0),(0x48,recipe+0x110),(0x4c,recipe+0x130)):self.put(context+off,value)
  self.put(recipe+0x304,bank);self.put(recipe+0x364,65536);self.put(recipe+0x230,0xdead0000) # retired RAW metadata intentionally unmapped
  d=(1,(bank+0x23f)&~63,(bank+0x423f)&~63,0,w|(h<<16),64|(((h+15)&~15)<<16),0,2)
  for off in(0x70,0xb0,0x110):self.words(recipe+off,*d)
  for off in(0xd0,0xf0):self.words(recipe+off,1,bank+0x6000,bank+0x6100,0,2|(2<<16),2|(2<<16),0,2)
  return recipe,context,d
 def call(self,name,*args):
  for i in range(13):self.u.reg_write(getattr(A,'UC_ARM_REG_R'+str(i)),args[i] if i<len(args) else 0)
  self.u.reg_write(A.UC_ARM_REG_SP,0x55ffe000);self.u.reg_write(A.UC_ARM_REG_LR,0x55fff000)
  self.u.emu_start(self.symbols[name],0x55fff000,count=3000000)
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x55fff000);self.assertEqual(self.u.reg_read(A.UC_ARM_REG_SP),0x55ffe000)
  value=self.u.reg_read(A.UC_ARM_REG_R0);return value if value<0x80000000 else value-0x100000000
 def service(self,u,pc,size,data):
  r=[u.reg_read(getattr(A,'UC_ARM_REG_R'+str(i)))for i in range(4)];ret=0;sp=u.reg_read(A.UC_ARM_REG_SP)
  if pc==self.boundary['m10v_half_pair_iip_ready']:ret=int(self.ready)
  elif pc==self.boundary['m10v_half_pair_iip_copy']:
   source,destination=self.desc(r[1]),self.desc(r[2]);self.copies.append((r[0],source,destination));self.timeline.append(('copy.done',destination[1]))
   self.assertEqual(self.desc(r[0]+0xb0),source,'recipe changed before IIP completion')
   if self.queue_cancel:self.put(self.state+8,self.get(self.state+8)|1);self.queue_cancel=False
   ret=int(not self.fail_copy)
  elif pc==self.boundary['m10v_half_pair_iip_compose']:
   previews=self.get(sp);orientation=self.get(sp+4);record=(r[0],self.desc(r[1]),self.desc(r[2]),self.desc(r[3]),(self.desc(previews),self.desc(previews+32)),orientation)
   self.assertNotEqual(self.desc(r[0]+0xb0)[4],record[3][4],'published pair before IIP completion')
   self.compositions.append(record);self.timeline.append(('compose.done',r[0]));ret=int(not self.fail_compose)
  elif pc in(self.boundary['m10v_debug_log'],self.boundary['foundation_debug']):self.events.append((*r,self.get(sp)))
  elif pc==self.boundary['m10v_save_trace_recipe_raw_status']:ret=2
  elif pc==0x536a2424:ret=self.manager
  elif pc==0x536a27e8:
   self.assertEqual(r[0],self.manager);self.assertEqual(r[2],2);self.allocations.append((r[0],r[1],r[2]));ret=0 if self.fail_alloc else self.next_token
   if ret:self.next_token+=self.token_step;self.timeline.append(('allocate',ret))
  elif pc==0x536a248c:self.assertEqual(r[0],self.manager);self.frees.append(r[1]);self.timeline.append(('free',r[1]))
  elif pc==0x53050b7c:
   self.assertTrue(sp<=r[0]<=0x55ffe000-8,f'operating-time getter requires an owned writable8-byte stack output, got r0={r[0]:#x}')
   self.assertEqual(bytes(u.mem_read(r[0],8)),bytes(8),'clock output must be initialized')
   self.clock_calls.append(r[0]);self.clock+=1
   if self.fail_clock:ret=0xfffffffc
   else:self.words(r[0],0x1234,self.clock);ret=0 # native order: signed high, low; status0

  elif pc==0x532525a4:ret=37
  elif pc==0x536b0a74:
   self.timeline.append(('sleep',r[0]));self.assertTrue(self.get(self.state+4)&1)
   if self.sleep_action:self.sleep_action()
   else:raise AssertionError('unexpected destructor wait')
  elif pc==self.leave_original:ret=41
  elif pc in(0x535847d8,0x53828014):raise AssertionError('frame filesystem path executed')
  else:return
  u.reg_write(A.UC_ARM_REG_R0,ret);u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
 def capture(self,exposure):return self.call('m10v_half_pair_camera',exposure[1])
 def test_clock_native_output_abi_and_low_word_used_without_retaining_stack(self):
  a=self.expose();self.assertEqual(self.capture(a),1)
  self.assertEqual(len(self.clock_calls),2)
  timings=[e for e in self.events if e[0]==222]
  self.assertEqual(timings[-1][1:4],(a[0],1,1))
 def test_clock_failure_does_not_abort_first_or_second_jpeg(self):
  self.fail_clock=True
  self.assertEqual(self.capture(self.expose(0)),1)
  self.assertEqual(self.capture(self.expose(1)),2)
  self.assertEqual(len(self.compositions),1)
 def test_two_distinct_recipes_pair_without_any_mapped_image_memory(self):
  a=self.expose(0);self.assertEqual(self.capture(a),1);first=self.token();self.assertEqual(first,0x70000004);self.assertEqual(self.desc(a[0]+0xb0),a[2]);self.assertEqual(len(self.copies),1)
  b=self.expose(1);self.assertEqual(self.capture(b),2);self.assertEqual(len(self.copies),2);self.assertEqual(len(self.compositions),1)
  output=self.compositions[0][3];self.assertEqual(output[4],64|(16<<16));self.assertEqual(self.desc(b[0]+0xb0),output)
  for off in(0x70,0x110):self.assertEqual(self.desc(b[0]+off),output)
  self.assertEqual(self.frees,[0x71000004,first]);self.assertEqual(self.token(),0);self.assertEqual(self.get(self.state+4),0)
 def test_full24mp_private_frame_and_pair_still_never_map_image_addresses(self):
  self.token_step=0x4000000
  frames=[]
  for index in(0,1):
   item=self.expose(index,w=2992,h=4000);recipe=item[0];bank=self.get(recipe+0x304);self.put(recipe+0x364,3*6144*4064)
   d=(1,bank+884736,bank+26345536,0,2992|(4000<<16),6144|(4000<<16),0,2)
   for off in(0x70,0xb0,0x110):self.words(recipe+off,*d)
   frames.append((recipe,item[1],d))
  self.assertEqual(self.capture(frames[0]),1);self.assertEqual(self.allocations[0][1],2*3008*4000+63)
  self.assertEqual(self.capture(frames[1]),2);self.assertEqual(self.desc(frames[1][0]+0xb0)[4],5984|(4000<<16))
  self.assertEqual(self.frees,[0x74000004,0x70000004])
 def test_oom_preserves_pending_first_and_current_original_jpeg(self):
  a=self.expose(0);self.assertEqual(self.capture(a),1);token=self.token();self.fail_alloc=True;b=self.expose(1);before=bytes(self.u.mem_read(b[0]+0x70,192))
  self.assertEqual(self.capture(b),-8);self.assertEqual(self.token(),token);self.assertFalse(self.frees);self.assertEqual(bytes(self.u.mem_read(b[0]+0x70,192)),before)
 def test_first_oom_does_not_publish_a_pending_frame(self):
  self.fail_alloc=True;a=self.expose(0);self.assertEqual(self.capture(a),-8);self.assertEqual(self.token(),0);self.assertEqual(self.desc(a[0]+0xb0),a[2]);self.assertFalse(self.copies);self.assertFalse(self.frees)
 def test_compose_rejection_keeps_first_and_publishes_no_pair_descriptors(self):
  a=self.expose(0);self.assertEqual(self.capture(a),1);token=self.token();self.fail_compose=True;b=self.expose(1);before=bytes(self.u.mem_read(b[0]+0x70,192))
  self.assertEqual(self.capture(b),-16);self.assertEqual(self.token(),token);self.assertEqual(self.frees,[0x71000004]);self.assertEqual(bytes(self.u.mem_read(b[0]+0x70,192)),before)
 def test_iip_unavailable_or_rejected_copy_preserves_original_and_releases_only_private_token(self):
  a=self.expose(0);self.ready=False;self.assertEqual(self.capture(a),-15);self.assertFalse(self.allocations)
  self.ready=True;self.fail_copy=True;self.assertEqual(self.capture(a),-16);self.assertEqual(self.token(),0);self.assertEqual(self.frees,[0x70000004]);self.assertEqual(self.desc(a[0]+0xb0),a[2])
 def test_changed_orientation_or_size_starts_a_new_group(self):
  for direction,width in((1,32),(0,48)):
   with self.subTest(direction=direction,width=width):
    self.setUp();a=self.expose(0);self.assertEqual(self.capture(a),1);old=self.token();b=self.expose(1,w=width,direction=direction);self.assertEqual(self.capture(b),1);self.assertNotEqual(self.token(),old);self.assertEqual(self.frees,[old]);self.assertFalse(self.compositions)
 def test_explicit_mode_leave_frees_pending_without_filesystem_work(self):
  a=self.expose(0);self.assertEqual(self.capture(a),1);token=self.token();self.assertEqual(self.call('m10v_half_pair_select',0x55005000,0),37);self.assertEqual(self.token(),0);self.assertEqual(self.frees,[token])
 def test_mode_cancel_queued_during_iip_is_not_lost(self):
  self.queue_cancel=True;a=self.expose(0);self.assertEqual(self.capture(a),1);old=self.token();self.assertEqual(self.get(self.state+8)&1,1)
  b=self.expose(1);self.assertEqual(self.capture(b),1);self.assertIn(old,self.frees);self.assertFalse(self.compositions);self.assertNotEqual(self.token(),old)
 def test_actual_automatic_review_leave_keeps_owned_pending_frame(self):
  a=self.expose(0);self.assertEqual(self.capture(a),1);token=self.token();before=bytes(self.u.mem_read(self.state,self.state_bytes))
  self.assertEqual(self.call('m10v_settings_controller_ab_live_leave',0x550a0000),41);self.assertEqual(bytes(self.u.mem_read(self.state,self.state_bytes)),before);self.assertFalse(self.frees)
  b=self.expose(1);self.assertEqual(self.capture(b),2);self.assertIn(token,self.frees)
 def test_destructor_waits_for_busy_consumer_before_free_and_prevents_reentry(self):
  a=self.expose(0);self.assertEqual(self.capture(a),1);token=self.token();self.put(self.state+4,1)
  def release():self.assertNotIn(token,self.frees);self.assertEqual(self.get(self.state),0);self.put(self.state+4,self.get(self.state+4)&~1)
  self.sleep_action=release;self.call('m10v_half_pair_destroy',self.owner);self.assertEqual(self.frees,[token]);self.assertLess(self.timeline.index(('sleep',1)),self.timeline.index(('free',token)));self.assertEqual(self.capture(self.expose(1)),-10)
 def test_ordinary_mode_has_zero_iip_allocation_and_pixel_work(self):
  self.assertEqual(self.capture(self.expose(0,half=False)),0);self.assertFalse(self.allocations);self.assertFalse(self.copies);self.assertFalse(self.compositions)
if __name__=='__main__':unittest.main()
