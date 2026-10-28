"""Inactive runtime ARM control/lifetime checks; no pixel or performance proof.
Real metadata/runtime/guard functions, all18 original hook patches and original
public queue/dispatcher/native-callback paths execute. Hardware body, allocator,
Setup6/library and kernel queue/event endpoints are explicit doubles. This does
not replace original ingress/StillMake/early-Setup6 integration tests.
"""
import hashlib,shutil,struct,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from analyze_gr3_border_iip import OriginalArm
from build_gr3_border_wait_guard import FLAGS,HOOKS,arm_bl,MODELS
from tests.test_gr3_border_prepare import fixture,RECIPE,MODULE,CONFIG
from unicorn import UC_HOOK_CODE,UC_PROT_READ,UC_PROT_WRITE,UC_PROT_EXEC
from unicorn import arm_const as A
BASE=0x54160000
POST=RECIPE+0x904
HEAP=0x55580000
WORKERS=(0x55500000,0x55501000,0x55502000)

def build_runtime():
 folder=tempfile.TemporaryDirectory(prefix='border_recovery_runtime_');p=Path(folder.name)
 names=('m10v_border','m10v_border_bank','m10v_border_shot','m10v_border_prepare',
        'm10v_border_canvas','m10v_border_fill_plan','m10v_border_wait_guard','m10v_border_runtime')
 sources=[ROOT/'native/gr3'/f'{name}.c' for name in names]+[ROOT/'scripts/border_recovery_wait_guard.S']
 objs=[]
 for i,source in enumerate(sources):
  obj=p/f'{i}.o';subprocess.run([shutil.which('clang'),*FLAGS,'-c',str(source),'-o',str(obj)],check=True,capture_output=True);objs.append(str(obj))
 script=p/'link.ld';script.write_text(f'''m10v_capture_library = 0x53000100;
m10v_border_camera_snapshot = 0x53000104;
m10v_save_trace_recipe_mark = 0x53000108;
SECTIONS {{ . = {BASE}; .text : {{ *(.text*) }} .rodata : {{ *(.rodata*) }}
/DISCARD/ : {{ *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }} }}''')
 elf=p/'runtime.elf';subprocess.run([shutil.which('ld.lld'),'-T',str(script),
 '--entry=m10v_border_runtime_after_resize',*objs,'-o',str(elf)],check=True,capture_output=True)
 b=elf.read_bytes();sh=struct.unpack_from('<I',b,32)[0];n=struct.unpack_from('<H',b,48)[0]
 rows=[struct.unpack_from('<10I',b,sh+40*i) for i in range(n)];code=bytearray();syms={}
 for row in rows:
  if row[2]&2 and row[5]:
   assert row[1]==1 and not row[2]&1,'no writable globals/TLS/BSS admitted'
   off=row[3]-BASE;assert 0<=off<0x10000
   code.extend(bytes(max(0,off+row[5]-len(code))));code[off:off+row[5]]=b[row[4]:row[4]+row[5]]
  if row[1]==2:
   sr=rows[row[6]];strings=b[sr[4]:sr[4]+sr[5]]
   for at in range(row[4],row[4]+row[5],16):
    name,value,_,info,_,section=struct.unpack_from('<IIIBBH',b,at)
    name=strings[name:].split(b'\0',1)[0].decode()
    assert section or not name,'unresolved '+name
    if name and info&15==2:syms[name]=value
 return folder,bytes(code),syms

class BorderRuntimeArmTests(unittest.TestCase):
 model='gr3'
 @classmethod
 def setUpClass(cls):
  cls.folder,cls.code,cls.syms=build_runtime();cls.addClassCleanup(cls.folder.cleanup)
 def setUp(self):
  path='builds/gr3-extension-validation/official-rtos.bin' if self.model=='gr3' else 'builds/gr3-border-iip-20261027/gr3x-official-rtos.bin'
  self.stock=(ROOT/path).read_bytes();self.assertEqual(hashlib.sha256(self.stock).hexdigest(),MODELS[self.model]['rtos_sha256'])
  self.p=OriginalArm(self.stock);self.u=self.p.u;self.u.mem_map(BASE,0x10000);self.u.mem_write(BASE,self.code)
  self.events=[];self.prepare_traces=[];self.queue=[];self.allocations=[];self.frees=[];self.signals=[];self.body_calls=[];self.bundles=[]
  self.resize_calls=[];self.callbacks=0;self.visited=[];self.stop_on_yield=True;self.library_result=0;self.active_client=0
  self.stubs={0x536a9bf8:0,0x536aa3a4:1,0x536aa34c:0,0x536abc78:0,0x536a9dd4:0,0x536a2954:0,0x536a29b4:0}
  self.u.hook_add(UC_HOOK_CODE,self.hook)
  for at,old,target,_ in HOOKS:
   self.patch(at,arm_bl(at,self.syms[target]) if isinstance(target,str) else target,old)
  # Exact original constructors initialize genuinely appended owned tails.
  for fn,worker in zip(('transfer','fill','resize'),WORKERS):self.call('m10v_border_'+fn+'_construct',worker)
  for getter,guard,factory,offset,vtable,worker in (
   (0x5369a0e8,0x5536c018,0x5536c00c,4,0x53d59700,WORKERS[0]),
   (0x53658a68,0x55363278,0x5536327c,4,0x53d51958,WORKERS[1]),
   (0x53672c48,0x5536bf6c,0x5536bf5c,12,0x53d56bd8,WORKERS[2])):
   self.put(guard,1);self.put(factory,vtable);self.put(factory+offset,worker)
  for address,length in ((RECIPE,0x5200),(MODULE,0xa000),(0x55400000,0x500)):
   self.u.mem_write(address,bytes(length))
  fixture(self.u.mem_write)
  self.put(0x55300000,0x53d0fe60,0,0,1) # native Request JPEG byte12=1 byte13=0
  self.events.clear();self.visited.clear()
 def reg(self,n):return self.u.reg_read(getattr(A,'UC_ARM_REG_R'+str(n)))
 def put(self,p,*v):self.u.mem_write(p,struct.pack('<'+'I'*len(v),*v))
 def word(self,p):return struct.unpack('<I',self.u.mem_read(p,4))[0]
 def patch(self,pc,value,expected=None):
  if expected is not None:self.assertEqual(self.word(pc),expected)
  page=pc&~4095;self.u.mem_protect(page,4096,UC_PROT_READ|UC_PROT_WRITE|UC_PROT_EXEC)
  self.put(pc,value);self.u.mem_protect(page,4096,UC_PROT_READ|UC_PROT_EXEC)
 def ret(self,value):
  self.u.reg_write(A.UC_ARM_REG_R0,value&0xffffffff);self.u.reg_write(A.UC_ARM_REG_PC,self.u.reg_read(A.UC_ARM_REG_LR))
 def hook(self,u,pc,size,data):
  self.visited.append(pc)
  if pc==0x536aa34c:
   self.assertEqual(self.callbacks,4);self.events.append('client-destroy')
  if pc in self.stubs:self.ret(self.stubs[pc]);return
  if pc==0x53000104:self.fail('runtime must use already-frozen shot, never fresh camera snapshot')
  if pc==0x536af2a8:
   self.allocations.append(self.reg(0));self.events.append('alloc');self.ret(HEAP);return
  if pc==0x536af2e4:self.frees.append(self.reg(0));self.events.append('free');self.ret(0);return
  if pc==0x5350e624:
   self.assertEqual((self.reg(0),self.reg(1)),(RECIPE,6));self.events.append('setup6');self.ret(0);return
  if pc==0x53000100:self.events.append('library');self.ret(self.library_result);return
  if pc==0x53000108:
   self.prepare_traces.append(tuple(self.reg(i) for i in range(4))+(self.word(self.reg(13)),))
   self.events.append('prepare-trace');self.ret(1);return
  if pc==0x5383c8a8:self.events.append('library-cache');self.ret(0);return
  if pc==self.syms['m10v_border_fill_bundle_submit']:
   b=self.reg(1);self.bundles.append((b,self.word(b+4),bytes(u.mem_read(b,36))))
   self.events.append('bundle'+str(len(self.bundles)))
  if pc==self.syms['m10v_border_stage_leave']:self.events.append('gateleave')
  if pc==0x534ab6b8:
   self.resize_calls.append((bytes(u.mem_read(self.reg(1),32)),bytes(u.mem_read(self.reg(2),32))))
   self.events.append('resize'+str(len(self.resize_calls)))
  if pc==0x536abd28:
   job=self.reg(1);self.queue.append(job);self.active_client=self.word(job+4)
   self.events.append('queue');out=self.word(u.reg_read(A.UC_ARM_REG_SP)+8);self.put(out,0,0);self.ret(1);return
  if pc==0x536a9e8c:
   if self.reg(2):self.put(self.reg(2),0)
   self.ret(0);return
  if pc==0x536b0a74:
   if self.stop_on_yield:u.emu_stop();return
   self.ret(0);return
  if pc in (0x5365900c,0x53673098):
   self.body_calls.append((pc,bytes(u.mem_read(self.reg(1),12))));self.events.append('fill-hw' if pc==0x5365900c else 'resize-hw')
   self.ret(0);return # hardware body only is the explicit double
  if pc==0x536a9d1c:
   self.signals.append((self.reg(0),self.reg(1)))
   self.events.append('native-signal');self.ret(1);return
 def invoke(self,name,*args,stack=0x55ffe000):
  for i,v in enumerate(args):
   if i<4:self.u.reg_write(getattr(A,'UC_ARM_REG_R'+str(i)),v)
   else:self.put(stack+4*(i-4),v)
  self.u.reg_write(A.UC_ARM_REG_SP,stack);self.u.reg_write(A.UC_ARM_REG_LR,0x55fff000)
  self.u.emu_start(self.syms.get(name,name),0x55fff000,count=3000000)
 def call(self,name,*args):
  self.invoke(name,*args);self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x55fff000)
  return self.reg(0)
 def phase(self):return (self.word(RECIPE+0x510c)>>5)&7
 def prepare(self):
  self.call('m10v_border_runtime_before_submit',MODULE,CONFIG);self.assertEqual(self.phase(),6)
 def post_fixture(self):
  self.prepare()
  # Post-BackResize metadata fixture; actual original ingress/BackResize lives
  # in the separate integration tests and is not replaced by this unit test.
  self.u.mem_write(RECIPE+0xb0,bytes(self.u.mem_read(RECIPE+0x70,32)))
  self.put(POST+0x30,RECIPE+0x1a8,self.word(RECIPE+0x44c8),self.word(RECIPE+0x5c),
   RECIPE+0x70,RECIPE+0xb0,RECIPE+0x90,RECIPE+0xd0,RECIPE+0xf0)
  self.events.clear()
 def dispatch_one(self):
  self.assertTrue(self.queue);job=self.queue.pop(0);client=self.word(job+4)
  self.assertEqual(self.word(client+36),1)
  paused=self.u.context_save();sp=self.u.reg_read(A.UC_ARM_REG_SP)
  held=bytes(self.u.mem_read(sp,0x55ffe000-sp))
  opcode=self.word(job+12)
  worker,entry=(WORKERS[1],0x5365935c) if opcode==0x010e0004 else (WORKERS[2],0x53673f48)
  self.invoke(entry,worker,job,stack=0x55dfe000)
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x55fff000)
  self.assertEqual(self.word(client+36),0);self.assertEqual(self.word(client+40),0)
  after=bytearray(self.u.mem_read(sp,len(held)));unchanged=bytearray(held)
  # The owned76-byte client is a runtime stack local: real notify updates its
  # pending/completed/worker/job fields. All other retained stack bytes stay.
  self.assertGreaterEqual(client,sp);self.assertLessEqual(client+76,0x55ffe000)
  after[client-sp:client-sp+76]=bytes(76);unchanged[client-sp:client-sp+76]=bytes(76)
  self.assertEqual(after,unchanged)
  self.callbacks+=1;self.u.context_restore(paused)
  self.u.reg_write(A.UC_ARM_REG_R0,0);self.u.reg_write(A.UC_ARM_REG_PC,self.u.reg_read(A.UC_ARM_REG_LR))
  self.u.emu_start(self.u.reg_read(A.UC_ARM_REG_PC),0x55fff000,count=3000000)
 def test_off_has_zero_allocation_queue_setup6_and_no_stagegate_factory(self):
  self.put(RECIPE+0x510c,0x42524400)
  self.call('m10v_border_runtime_before_submit',MODULE,CONFIG)
  self.assertEqual(self.call('m10v_border_runtime_after_resize',MODULE,POST),0)
  self.assertEqual(self.allocations,[]);self.assertEqual(self.queue,[]);self.assertEqual(self.events,[])
  self.assertNotIn(0x5369a0e8,self.visited)
 def test_missing_each_guard_patch_rejects_before_allocation_or_hardware(self):
  self.post_fixture()
  for at,stock,target,_ in HOOKS:
   installed=self.word(at);self.patch(at,stock)
   self.put(RECIPE+0x510c,0x425244c1)
   result=self.call('m10v_border_runtime_after_resize',MODULE,POST)
   self.assertEqual(result,(-7)&0xffffffff,hex(at))
   self.assertEqual(self.allocations,[]);self.assertEqual(self.queue,[])
   self.assertNotIn('setup6',self.events);self.patch(at,installed)
 def test_post_resize_admission_failure_retains_reason_for_camera_log(self):
  self.post_fixture();self.put(POST+0x30,0)
  self.assertEqual(self.call('m10v_border_runtime_after_resize',MODULE,POST),(-3)&0xffffffff)
  self.assertEqual(self.phase(),5)
  self.assertEqual(self.prepare_traces[-1][1:5],(197,0x424f5244,3,3))
  self.assertEqual(self.queue,[]);self.assertEqual(self.allocations,[])
 def test_missing_each_owned_worker_tag_rejects_before_hardware(self):
  self.post_fixture()
  for worker,offset in zip(WORKERS,(0x44,0x58,0x48)):
   tag=self.word(worker+offset);self.put(worker+offset,0);self.put(RECIPE+0x510c,0x425244c1)
   self.assertEqual(self.call('m10v_border_runtime_after_resize',MODULE,POST),(-7)&0xffffffff)
   self.assertEqual(self.allocations,[]);self.assertEqual(self.queue,[]);self.put(worker+offset,tag)
 def test_three_pre_submit_stripes_retain_expanded_pitch_without_queue_or_allocation(self):
  original_status=bytes(self.u.mem_read(RECIPE+0x1a8,0x180))
  for column in (0,2000,4000):
   self.u.mem_write(MODULE+0x9960,struct.pack('<H',6016))
   self.put(MODULE+0x9950,self.word(CONFIG+0x18)+column)
   self.put(MODULE+0x9954,self.word(CONFIG+0x1c)+column)
   self.call('m10v_border_runtime_before_submit',MODULE,CONFIG)
   self.assertEqual(self.phase(),6)
   self.assertEqual(struct.unpack('<H',self.u.mem_read(MODULE+0x9960,2))[0],6336)
   self.assertEqual(self.word(MODULE+0x9950),self.word(CONFIG+0x18)+column)
  self.assertEqual(bytes(self.u.mem_read(RECIPE+0x1a8,0x180)),original_status)
  self.assertEqual(self.allocations,[]);self.assertEqual(self.queue,[]);self.assertEqual(self.events,[])
 def test_prepared_later_stripe_failure_retains_native_frame_without_old_pitch_enqueue(self):
  self.prepare()
  self.u.mem_write(MODULE+0x9960,struct.pack('<H',6016))
  self.put(MODULE+0x9950,self.word(CONFIG+0x18)+2000);self.put(MODULE+0x9954,self.word(CONFIG+0x1c)+2000)
  self.put(CONFIG+0x14,50000000) # admission fails on the next stripe
  self.invoke('m10v_border_runtime_before_submit',MODULE,CONFIG)
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x536b0a74)
  self.assertEqual(self.phase(),6);self.assertEqual(self.queue,[]);self.assertEqual(self.allocations,[])
  self.assertLess(self.u.reg_read(A.UC_ARM_REG_SP),0x55ffe000)
 def test_normal_post_runs_native_public_callbacks_then_publishes_and_frees(self):
  self.post_fixture();before=bytes(self.u.mem_read(RECIPE+0x70,32))
  self.invoke('m10v_border_runtime_after_resize',MODULE,POST)
  for i in range(4):
   self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x536b0a74)
   self.assertEqual(self.frees,[]);self.assertNotEqual(self.phase(),3)
   self.dispatch_one()
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x55fff000);self.assertEqual(self.reg(0),1)
  self.assertEqual(self.callbacks,4);self.assertEqual([mask for _,mask in self.signals],[0x10,0x10,0x40,0x40])
  self.assertEqual(self.allocations,[5820]);self.assertEqual(self.frees,[HEAP]);self.assertEqual(self.phase(),3)
  self.assertEqual(self.word(WORKERS[0]+0x54),0)
  self.assertEqual(self.bundles[0][0],self.bundles[1][0]);self.assertGreater(self.bundles[0][1],2);self.assertEqual(self.bundles[1][1],2)
  published=bytes(self.u.mem_read(RECIPE+0x70,32));self.assertNotEqual(published,before)
  self.assertEqual(bytes(self.u.mem_read(RECIPE+0xb0,32)),published)
  self.assertEqual(bytes(self.u.mem_read(RECIPE+0x110,32)),published)
  self.assertEqual(self.events[:4],['alloc','setup6','library','bundle1'])
  self.assertEqual(self.events[-2:],['free','gateleave'])
  self.assertEqual([e for e in self.events if e in ('setup6','library','bundle1','bundle2','resize1','resize2','free','gateleave')],
   ['setup6','library','bundle1','bundle2','resize1','resize2','free','gateleave'])
  self.assertEqual(len(self.resize_calls),2)
  for i,(src,dst) in enumerate(self.resize_calls):
   self.assertEqual(src,published)
   self.assertEqual(bytes(self.u.mem_read(RECIPE+0xd0+32*i,32)),dst)
  # Second bundle initializes FULL allocated preview dimensions before fit Resize.
  preview_fills=[raw for pc,raw in self.body_calls if pc==0x5365900c][-2:]
  for raw,(_,dst) in zip(preview_fills,self.resize_calls):
   descriptor=struct.unpack_from('<I',raw)[0]
   fill=bytes(self.u.mem_read(descriptor,32))
   self.assertEqual(struct.unpack_from('<I',fill,16)[0],struct.unpack_from('<I',dst,20)[0])
   self.assertEqual(struct.unpack_from('<I',fill,24)[0],0)
 def finish_post(self):
  self.invoke('m10v_border_runtime_after_resize',MODULE,POST)
  for _ in range(4):
   self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x536b0a74);self.dispatch_one()
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x55fff000);self.assertEqual(self.reg(0),1)
 def test_jpeg_handoff_restores_completed_full_canvas_after_owner_reset(self):
  self.put(RECIPE+0x510c,0x42524402);self.post_fixture()
  inner=bytes(self.u.mem_read(RECIPE+0xb0,32))
  self.finish_post();outer=bytes(self.u.mem_read(RECIPE+0xb0,32))
  self.u.mem_write(RECIPE+0x70,inner);self.u.mem_write(RECIPE+0xb0,inner)
  self.u.mem_write(RECIPE+0x110,inner)
  self.events.clear();self.assertEqual(self.call('m10v_border_runtime_jpeg',RECIPE+0x9b8),0)
  self.assertEqual(bytes(self.u.mem_read(RECIPE+0xb0,32)),outer)
  self.assertEqual(bytes(self.u.mem_read(RECIPE+0x110,32)),outer)
  self.assertEqual(self.events[0],'library');self.assertNotIn('alloc',self.events)
 def test_jpeg_handoff_late_xpan_crop_uses_same_bank_and_hardware(self):
  self.put(RECIPE+0x510c,0x42524402);self.post_fixture()
  original=self.word(RECIPE+0xb0+4);chroma=self.word(RECIPE+0xb0+8)
  stride=self.word(RECIPE+0xb0+20)&65535
  self.put(RECIPE+0x510c,0x425244a2)
  self.put(RECIPE+0x70+4,original+896*stride,chroma+896*stride)
  self.put(RECIPE+0xb0+4,original+896*stride,chroma+896*stride)
  for at in (RECIPE+0x70,RECIPE+0xb0):self.put(at+16,6000|(2208<<16))
  self.library_result=(-4)&0xffffffff
  self.invoke('m10v_border_runtime_jpeg',RECIPE+0x9b8)
  for _ in range(4):
   self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x536b0a74);self.dispatch_one()
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x55fff000)
  self.assertEqual(self.phase(),3);self.assertEqual(self.callbacks,4)
  self.assertEqual(self.word(RECIPE+0xb0+16),6272|(2480<<16))
  self.assertEqual(self.word(RECIPE+0x110+16),6272|(2480<<16))
  self.assertEqual(self.events[0],'library')
 def test_jpeg_handoff_late_6x7_crop_preserves_full_native_height(self):
  self.put(RECIPE+0x510c,0x42524402);self.post_fixture()
  y=self.word(RECIPE+0xb0+4);c=self.word(RECIPE+0xb0+8)
  self.put(RECIPE+0x510c,0x425244a2)
  for at in (RECIPE+0x70,RECIPE+0xb0):
   self.put(at+4,y+666,c+666);self.put(at+16,4668|(4000<<16))
  self.invoke('m10v_border_runtime_jpeg',RECIPE+0x9b8)
  for _ in range(4):
   self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x536b0a74);self.dispatch_one()
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x55fff000)
  self.assertEqual(self.phase(),3);self.assertEqual(self.word(RECIPE+0xb0+16),5148|(4480<<16))
  self.assertEqual(self.word(RECIPE+0x110+16),5148|(4480<<16))
 def test_valid_original_preview_roi_is_normalized_before_fill_resize_and_publication(self):
  self.post_fixture();self.put(RECIPE+0xd0+16,718|(478<<16));self.put(RECIPE+0xd0+24,2|(2<<16))
  self.finish_post()
  self.assertEqual(self.word(RECIPE+0xd0+24),0)
  self.assertEqual(struct.unpack_from('<I',self.resize_calls[0][1],24)[0],0)
 def test_preview_whole_allocation_at_native_split_threshold_rejects_before_hardware(self):
  self.post_fixture();self.put(RECIPE+0xd0+20,1024|(1024<<16))
  self.assertEqual(self.call('m10v_border_runtime_after_resize',MODULE,POST),(-7)&0xffffffff)
  self.assertEqual(self.allocations,[]);self.assertEqual(self.queue,[]);self.assertNotIn('setup6',self.events)
 def test_format2_thumbnail_keeps_native_format_and_two_planes_through_complete_chain(self):
  self.post_fixture();self.put(RECIPE+0xf0,2)
  self.finish_post();thumb=self.resize_calls[1][1]
  self.assertEqual(thumb[0],2);self.assertEqual(struct.unpack_from('<I',thumb,12)[0],0)
  self.assertEqual(bytes(self.u.mem_read(RECIPE+0xf0,32)),thumb)
  raw=[raw for pc,raw in self.body_calls if pc==0x5365900c][-1]
  d=struct.unpack_from('<I',raw)[0]
  self.assertEqual(self.u.mem_read(d,1)[0],2);self.assertEqual(self.word(d+12),0)
 def test_film_holes_use_bounded_one_bundle_then_same_metadata_preview_bundle(self):
  self.put(RECIPE+0x510c,0x42524402);self.post_fixture();self.finish_post()
  self.assertGreater(self.bundles[0][1],4);self.assertLessEqual(self.bundles[0][1],132)
  self.assertEqual(self.bundles[1][1],2);self.assertEqual(self.allocations,[5820])
  self.assertEqual(self.callbacks,4);self.assertEqual(self.frees,[HEAP])
  fills=[raw for pc,raw in self.body_calls if pc==0x5365900c]
  self.assertEqual({struct.unpack_from('<H',raw,4)[0] for raw in fills},{0,224})
  self.assertTrue(all(struct.unpack_from('<2H',raw,6)==(128,128) for raw in fills))
  self.assertTrue(all(struct.unpack_from('<H',raw,4)[0]==0 for raw in fills[-2:]))
 def test_request_format_and_recipe_mode_gates_fail_before_work_or_hold_if_prepared(self):
  for address,value in ((RECIPE+0x18,2),(0x55300000,0),(0x5530000c,0),(0x5530000c,0x0201)):
   self.put(address,value)
   self.call('m10v_border_runtime_before_submit',MODULE,CONFIG)
   self.assertEqual(self.phase(),5);self.assertEqual(self.allocations,[]);self.assertEqual(self.queue,[])
   self.assertTrue(self.prepare_traces);self.assertEqual(self.prepare_traces[-1][1:4],(197,0x424f5244,1))
   self.setUp()
  self.prepare();self.put(0x5530000c,0)
  self.invoke('m10v_border_runtime_before_submit',MODULE,CONFIG)
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x536b0a74)
  self.assertEqual(self.phase(),6);self.assertEqual(self.queue,[])
 def test_only_explicit_native_library_sentinel_continues_and_other_errors_do_not_draw(self):
  self.library_result=-14;self.post_fixture();self.finish_post()
  self.assertEqual(self.phase(),3);self.assertEqual(self.callbacks,4)
  for result in (-4,-6,-1):
   self.setUp();self.library_result=result;self.post_fixture()
   self.assertEqual(self.call('m10v_border_runtime_after_resize',MODULE,POST),(-11)&0xffffffff)
   self.assertEqual(self.phase(),4);self.assertEqual(self.callbacks,0);self.assertEqual(self.queue,[])
   self.assertEqual(self.bundles,[]);self.assertEqual(self.frees,[HEAP])
   self.assertEqual(self.word(WORKERS[0]+0x54),0)
   self.assertEqual(self.events.count('library-cache'),2)
 def test_complete_reentry_is_once_only_without_repeat_setup_library_queue_or_free(self):
  self.post_fixture();self.finish_post()
  observed=(list(self.events),list(self.allocations),list(self.frees),self.callbacks)
  self.assertEqual(self.call('m10v_border_runtime_after_resize',MODULE,POST),1)
  self.assertEqual((self.events,self.allocations,self.frees,self.callbacks),observed)
 def test_wrong_native_callback_event_cannot_complete_pending_first_bundle(self):
  self.post_fixture();self.invoke('m10v_border_runtime_after_resize',MODULE,POST)
  client=self.active_client;waiting=self.u.context_save()
  self.invoke('m10v_border_client_notify',client,0x03020002,0,stack=0x55dfe000)
  self.assertEqual(self.word(client+36),1);self.assertEqual(self.word(client+44),0)
  self.assertEqual(self.frees,[]);self.assertEqual(self.phase(),2)
  self.assertEqual(self.word(WORKERS[0]+0x54),RECIPE)
  self.u.context_restore(waiting)
 def test_without_each_required_callback_caller_metadata_and_gate_never_release(self):
  for completed in range(4):
   if completed:self.setUp()
   self.post_fixture();before=bytes(self.u.mem_read(RECIPE+0x70,32))
   previews=bytes(self.u.mem_read(RECIPE+0xd0,64))
   self.invoke('m10v_border_runtime_after_resize',MODULE,POST)
   for _ in range(completed):self.dispatch_one()
   self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x536b0a74)
   self.assertEqual(self.callbacks,completed);self.assertEqual(len(self.queue),1)
   client=self.active_client;self.assertEqual(self.word(client+36),1)
   self.assertEqual(self.frees,[]);self.assertEqual(self.phase(),2)
   self.assertEqual(self.word(WORKERS[0]+0x54),RECIPE)
   self.assertEqual(bytes(self.u.mem_read(RECIPE+0x70,32)),before)
   self.assertEqual(bytes(self.u.mem_read(RECIPE+0xd0,64)),previews)
   self.assertEqual(self.word(HEAP),0x42464231)
   self.assertLess(self.u.reg_read(A.UC_ARM_REG_SP),0x55ffe000)
class BorderRuntimeGr3xArmTests(BorderRuntimeArmTests):model='gr3x'
if __name__=='__main__':unittest.main()
