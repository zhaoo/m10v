"""Native IIP pairing requests/callback ownership; photo pixels stay UNMAPPED.
Actual original public clients/queue/dispatcher/notify and installed wait guards
execute. Only DMA bodies, kernel/cache leaves and scalar heap are doubles.
Set M10V_HALF_IIP_FINAL to a deliverable directory or final-rtos.bin path to
replay its exact code, manifest exports and existing18patches without rebuilding
or repairing any guard. Both fixture and delivered modes keep pixels unmapped.
"""
import hashlib,json,os,shutil,struct,subprocess,tempfile,unittest
from pathlib import Path
from unicorn import UC_HOOK_CODE,UC_PROT_READ,UC_PROT_WRITE,UC_PROT_EXEC
from unicorn import arm_const as A
import tests.test_gr3_border_runtime as harness
from tests.test_gr3_border_runtime import build_runtime,WORKERS,HEAP,HOOKS
from scripts.build_gr3_border_wait_guard import FLAGS
ROOT=Path(__file__).resolve().parents[1];PAIR_BASE=0x54200000
class HalfPairIipTests(unittest.TestCase):
 model='gr3'
 reg=harness.BorderRuntimeArmTests.reg;put=harness.BorderRuntimeArmTests.put;word=harness.BorderRuntimeArmTests.word;patch=harness.BorderRuntimeArmTests.patch;ret=harness.BorderRuntimeArmTests.ret;invoke=harness.BorderRuntimeArmTests.invoke;call=harness.BorderRuntimeArmTests.call
 @classmethod
 def setUpClass(cls):
  cls.final_image=None;cls.final_manifest=None
  selected=os.environ.get('M10V_HALF_IIP_FINAL')
  if selected:
   path=Path(selected).resolve();path=path/'final-rtos.bin' if path.is_dir() else path
   cls.final_image=path.read_bytes();cls.final_manifest=json.loads((path.parent/'manifest.json').read_text());cls.final_path=path
   m=cls.final_manifest;p=m['half_pair']
   assert m['camera_model']=='gr3' and p['enabled'] and p['backend']=='native-IIP'
   cls.syms=m['symbols'];assert 'm10v_half_pair_compose' not in cls.syms
   for component in (p['iip_guard'],p['iip_component']):
    at=component['base']-0x53000000;n=component['code_bytes']
    assert 0<=at and n>0 and at+n<=len(cls.final_image)
    assert hashlib.sha256(cls.final_image[at:at+n]).hexdigest()==component['code_sha256']
    for name,address in component['symbols'].items():assert cls.syms[name]==address
   cls.final_sha256=hashlib.sha256(cls.final_image).hexdigest()
   return
  cls.folder,cls.code,cls.syms=build_runtime();cls.addClassCleanup(cls.folder.cleanup)
  cls.pair_folder=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.pair_folder.cleanup);p=Path(cls.pair_folder.name)
  obj=p/'iip.o';subprocess.run([shutil.which('clang'),*FLAGS,'-fno-jump-tables','-c',str(ROOT/'native/gr3/m10v_half_pair_iip.c'),'-o',str(obj)],check=True,capture_output=True)
  script=p/'link.ld';script.write_text('\n'.join(f'{name} = {address};' for name,address in cls.syms.items())+f'\nSECTIONS {{ . = {PAIR_BASE}; .text : {{ *(.text*) }} .rodata : {{ *(.rodata*) }} /DISCARD/ : {{ *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }} }}')
  elf=p/'iip.elf';subprocess.run([shutil.which('ld.lld'),'-T',str(script),'--entry=m10v_half_pair_iip_ready',str(obj),'-o',str(elf)],check=True,capture_output=True)
  b=elf.read_bytes();sh=struct.unpack_from('<I',b,32)[0];n=struct.unpack_from('<H',b,48)[0];rows=[struct.unpack_from('<10I',b,sh+40*i) for i in range(n)];code=bytearray();symbols={}
  for row in rows:
   if row[2]&2 and row[5]:
    assert row[1]==1 and not row[2]&1,'no globals/BSS';off=row[3]-PAIR_BASE;assert 0<=off<65536;code.extend(bytes(max(0,off+row[5]-len(code))));code[off:off+row[5]]=b[row[4]:row[4]+row[5]]
   if row[1]==2:
    sr=rows[row[6]];strings=b[sr[4]:sr[4]+sr[5]]
    for at in range(row[4],row[4]+row[5],16):
     name,value,_,info,_,section=struct.unpack_from('<IIIBBH',b,at);name=strings[name:].split(b'\0',1)[0].decode();assert section or not name,'unresolved '+name
     if name.startswith('m10v_half_pair_iip_') and info&15==2:symbols[name]=value
  cls.pair_code=bytes(code);cls.syms={**cls.syms,**symbols}
 def setUp(self):
  self.copy_calls=[];self.cache_calls=[];self.fail_heap=False;self.probes=[];self.complete_wait=False;self.fill_images=[]
  if self.final_image is None:
   harness.BorderRuntimeArmTests.setUp(self);self.u.mem_map(PAIR_BASE,65536);self.u.mem_write(PAIR_BASE,self.pair_code)
  else:
   self.stock=(ROOT/'builds/gr3-extension-validation/official-rtos.bin').read_bytes();self.assertEqual(hashlib.sha256(self.stock).hexdigest(),harness.MODELS['gr3']['rtos_sha256'])
   self.p=self.new_arm();self.u=self.p.u
   self.events=[];self.prepare_traces=[];self.queue=[];self.allocations=[];self.frees=[];self.signals=[];self.body_calls=[];self.bundles=[]
   self.resize_calls=[];self.callbacks=0;self.visited=[];self.stop_on_yield=True;self.library_result=0;self.active_client=0
   self.stubs={0x536a9bf8:0,0x536aa3a4:1,0x536aa34c:0,0x536abc78:0,0x536a9dd4:0,0x536a2954:0,0x536a29b4:0}
   self.u.hook_add(UC_HOOK_CODE,self.hook)
   # Read the delivered patch words. Never install a separately linked guard
   # or repair candidate hooks in the final-artifact replay.
   for at,old,target,_ in HOOKS:
    replacement=harness.arm_bl(at,self.syms[target]) if isinstance(target,str) else target
    self.assertEqual(self.word(at),replacement,hex(at))
   for fn,worker in zip(('transfer','fill','resize'),WORKERS):self.call('m10v_border_'+fn+'_construct',worker)
   for getter,guard,factory,offset,vtable,worker in (
    (0x5369a0e8,0x5536c018,0x5536c00c,4,0x53d59700,WORKERS[0]),
    (0x53658a68,0x55363278,0x5536327c,4,0x53d51958,WORKERS[1]),
    (0x53672c48,0x5536bf6c,0x5536bf5c,12,0x53d56bd8,WORKERS[2])):
    self.put(guard,1);self.put(factory,vtable);self.put(factory+offset,worker)
   for address,length in ((harness.RECIPE,0x5200),(harness.MODULE,0xa000),(0x55400000,0x500)):self.u.mem_write(address,bytes(length))
   harness.fixture(self.u.mem_write);self.put(0x55300000,0x53d0fe60,0,0,1)

  self.first=0x55401000;self.second=0x55401020;self.output=0x55401040;self.previews=0x55401060
  self.descriptor(self.first,2992,4000,3008,4000,0x60000000,0x61000000)
  self.descriptor(self.second,2992,4000,3008,4000,0x62000000,0x63000000)
  self.descriptor(self.output,5984,4000,6016,4000,0x64000000,0x66000000)
  self.descriptor(self.previews,720,480,720,480,0x68000000,0x68100000)
  self.descriptor(self.previews+32,160,120,160,120,0x68200000,0x68300000)
  self.events.clear();self.visited.clear()
 def new_arm(self):
  from scripts.analyze_gr3_border_iip import OriginalArm
  p=OriginalArm(self.stock)
  if self.final_image is not None:
   original_end=(0x53000000+len(self.stock)+4095)&~4095
   delivered_end=(0x53000000+len(self.final_image)+4095)&~4095
   self.assertLessEqual(delivered_end,0x55000000,'delivered RO image overlaps the native RAM fixture')
   if delivered_end>original_end:p.u.mem_map(original_end,delivered_end-original_end)
   # OriginalArm protects original text RX. Temporarily permit the one exact
   # delivered image write, then restore RX across original and appended pages.
   p.u.mem_protect(0x53000000,delivered_end-0x53000000,UC_PROT_READ|UC_PROT_WRITE|UC_PROT_EXEC)
   p.u.mem_write(0x53000000,self.final_image)
   p.u.mem_protect(0x53000000,delivered_end-0x53000000,UC_PROT_READ|UC_PROT_EXEC)
  return p
 def test_delivered_or_fixture_guard_bindings_are_complete_before_first_enqueue(self):
  self.assertEqual(self.call('m10v_half_pair_iip_ready'),1)
  for at,old,target,_ in HOOKS:self.assertEqual(self.word(at),harness.arm_bl(at,self.syms[target]) if isinstance(target,str) else target)
  self.assertEqual(self.queue,[]);self.assertEqual(self.copy_calls,[])
  if self.final_image is not None:
   self.assertEqual(hashlib.sha256(self.final_path.read_bytes()).hexdigest(),self.final_sha256)
   self.assertEqual(self.word(self.syms['m10v_half_pair_iip_copy']),struct.unpack_from('<I',self.final_image,self.syms['m10v_half_pair_iip_copy']-0x53000000)[0])
 def descriptor(self,at,w,h,s,rows,y,c,fmt=1):self.put(at,fmt,y,c,0,w|(h<<16),s|(rows<<16),0,2)
 def hook(self,u,pc,size,data):
  if pc==0x536a9e8c and self.complete_wait:
   if self.reg(2):self.put(self.reg(2),self.reg(1))
   self.ret(1);return
  if pc==self.syms.get('m10v_debug_log'):
   self.probes.append((self.reg(0),self.reg(1)));self.ret(1);return
  if pc in (0x534ab1a4,0x534ab60c):self.cache_calls.append((pc,bytes(u.mem_read(self.reg(1),32))));self.ret(0);return
  if pc==0x536aa34c:self.events.append('client-destroy');self.ret(1);return
  if pc==0x5365900c:self.fill_images.append(bytes(u.mem_read(self.word(self.reg(1)),32)))
  if pc==0x5369a948:
   pair=self.reg(1);src,dst=self.word(pair),self.word(pair+4);self.copy_calls.append((bytes(u.mem_read(src,32)),bytes(u.mem_read(dst,32))));self.ret(0);return
  if pc==0x536af2a8 and self.fail_heap:self.allocations.append(self.reg(0));self.ret(0);return
  harness.BorderRuntimeArmTests.hook(self,u,pc,size,data)
 def dispatch_one(self):
  self.assertTrue(self.queue);job=self.queue.pop(0);client=self.word(job+4);self.assertEqual(self.word(client+36),1)
  paused=self.u.context_save();opcode=self.word(job+12)
  if opcode==0x010e0004:worker,entry=WORKERS[1],0x5365935c
  elif opcode==0x010e8006:worker,entry=WORKERS[0],0x5369abc8
  else:worker,entry=WORKERS[2],0x53673f48
  self.invoke(entry,worker,job,stack=0x55dfe000);self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x55fff000);self.assertEqual(self.word(client+36),0);self.assertEqual(self.word(client+40),0)
  self.callbacks+=1;self.u.context_restore(paused);self.u.reg_write(A.UC_ARM_REG_R0,0);self.u.reg_write(A.UC_ARM_REG_PC,self.u.reg_read(A.UC_ARM_REG_LR));self.u.emu_start(self.u.reg_read(A.UC_ARM_REG_PC),0x55fff000,count=3000000)
 def finish(self,count):
  for _ in range(count):self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x536b0a74);self.assertEqual(self.frees,[]);self.dispatch_one()
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x55fff000);self.assertEqual(self.reg(0),1);self.assertEqual(self.word(WORKERS[0]+0x54),0);self.assertEqual(self.p.assertions,[])
 def test_copy_uses_native_transfer_and_waits_for_exact_callback(self):
  dst=0x55402000;self.descriptor(dst,2992,4000,3008,4000,0x64000000,0x65000000)
  self.invoke('m10v_half_pair_iip_copy',0x5c000028,self.first,dst)
  self.assertEqual(self.word(self.queue[0]+12),0x010e8006);self.assertEqual(self.word(WORKERS[0]+0x54),0x5c000028);self.assertEqual(self.allocations,[])
  self.finish(1);self.assertEqual([mask for _,mask in self.signals],[0x400]);self.assertEqual(len(self.copy_calls),1);self.assertEqual(len(self.cache_calls),3)
  if self.final_manifest and self.final_manifest['half_pair']['iip_guard'].get('trace_log'):
   for phase in (30,33,34,35,36,37,38,39,40,41,42,44,45):self.assertIn((223,phase),self.probes)
   for phase in (50,51,60,61,70,71,80):self.assertIn((224,phase),self.probes)
 def test_compose_native_fill_two_transfers_two_resizes_and_no_pixel_mapping(self):
  self.invoke('m10v_half_pair_iip_compose',0x5c000028,self.first,self.second,self.output,self.previews,1);self.finish(6)
  self.assertEqual([mask for _,mask in self.signals],[0x10,0x400,0x400,0x10,0x40,0x40]);self.assertEqual(self.frees,[HEAP]);self.assertEqual(len(self.copy_calls),2);self.assertEqual(len(self.resize_calls),2)
  first=struct.unpack('<8I',self.copy_calls[0][1]);second=struct.unpack('<8I',self.copy_calls[1][1]);self.assertEqual(first[6],0);self.assertEqual(second[6],2992)
  self.assertTrue(self.allocations[0]<8192);self.assertEqual(len(self.cache_calls),8)
  fills=[raw for pc,raw in self.body_calls if pc==0x5365900c];self.assertGreater(len(fills),30)
  for raw in fills:
   d=self.word(struct.unpack_from('<I',raw)[0]+16);self.assertLess((d&65535)*(d>>16),0x100000);self.assertEqual(struct.unpack_from('<3H',raw,4),(16,128,128))
 def test_center_black_separator_is_native_fill_before_both_thumbnail_resizes(self):
  self.invoke('m10v_half_pair_iip_compose',0x5c000028,self.first,self.second,self.output,self.previews,1)
  self.finish(6)
  self.assertEqual([mask for _,mask in self.signals],[0x10,0x400,0x400,0x10,0x40,0x40])
  fills=[raw for pc,raw in self.body_calls if pc==0x5365900c]
  descriptor=struct.unpack('<8I',self.fill_images[-1])
  self.assertEqual(descriptor[4],240|(4000<<16));self.assertEqual(descriptor[6],2872)
  self.assertEqual(struct.unpack_from('<3H',fills[-1],4),(16,128,128))
  for source,_ in self.resize_calls:self.assertEqual(struct.unpack('<8I',source)[4],5984|(4000<<16))
  self.assertLess(self.allocations[0],8192)
 def test_separator_all_photo_sizes_and_orientations_stays_centered_and_bounded(self):
  for w,h,gx,gy in ((2992,4000,240,320),(2400,3200,192,256),(1680,2240,136,184),(960,1280,80,104)):
   for orientation in (1,3,6,8):
    with self.subTest(size=(w,h),orientation=orientation):
     self.setUp();pitch=(w+63)&~63;rows=(h+15)&~15
     self.descriptor(self.first,w,h,pitch,rows,0x60000000,0x61000000)
     self.descriptor(self.second,w,h,pitch,rows,0x62000000,0x63000000)
     ow,oh=(2*w,h)if orientation in(1,3)else(w,2*h)
     self.descriptor(self.output,ow,oh,(ow+63)&~63,(oh+15)&~15,0x64000000,0x66000000)
     self.invoke('m10v_half_pair_iip_compose',0x5c000028,self.first,self.second,self.output,self.previews,orientation);self.finish(6)
     d=struct.unpack('<8I',self.fill_images[-1]);sw,sh=d[4]&65535,d[4]>>16;x,y=d[6]&65535,d[6]>>16
     if orientation in(1,3):self.assertEqual((sw,sh,x,y),(gx,h,(ow-gx)//2,0))
     else:self.assertEqual((sw,sh,x,y),(w,gy,0,(oh-gy)//2))
     self.assertLess(sw*sh,0x100000);self.assertEqual((x*2+sw,y*2+sh),(ow,oh));self.assertEqual((x|y|sw|sh)&1,0)
     for src,_ in self.resize_calls:self.assertEqual(struct.unpack('<8I',src)[4],ow|(oh<<16))
     self.assertEqual(len(self.copy_calls),2);self.assertEqual(self.frees,[HEAP])
 def test_orientation_bindings_are_native_rectangles(self):
  for orientation,expected in ((1,(0,16)),(3,(16,0)),(6,(16<<16,0)),(8,(0,16<<16))):
   with self.subTest(orientation=orientation):
    self.setUp();self.descriptor(self.first,16,16,64,16,0x60000000,0x61000000);self.descriptor(self.second,16,16,64,16,0x62000000,0x63000000)
    self.descriptor(self.output,32 if orientation<6 else 16,16 if orientation<6 else 32,64,16 if orientation<6 else 32,0x64000000,0x66000000)
    self.invoke('m10v_half_pair_iip_compose',0x5c000028,self.first,self.second,self.output,self.previews,orientation);self.finish(6)
    self.assertEqual(tuple(struct.unpack('<8I',call[1])[6] for call in self.copy_calls),expected)
 def test_original_transfer_body_programs_both_planes_with_rectangle_offsets(self):
  for x,y,pitch,rows in ((2992,0,6016,4000),(0,4000,3008,8000)):
   with self.subTest(x=x,y=y):
    p=self.new_arm();worker,service,packet,args,src,dst=[0x55080000+i*0x1000 for i in range(6)];p.words(worker+0x34,service);p.words(service+0x54,packet);p.words(args,src,dst)
    p.words(src,1,0x60000000,0x61000000,0,2992|(4000<<16),3008|(4000<<16),0,2)
    p.words(dst,1,0x64000000,0x66000000,0,2992|(4000<<16),pitch|(rows<<16),x|(y<<16),2)
    requests=[]
    def dma():
     raw=bytes(p.u.mem_read(p.u.reg_read(p.A.UC_ARM_REG_R2),0x2d));requests.append((raw[0],struct.unpack_from('<II',raw,4),struct.unpack_from('<8H',raw,12)))
    p.boundaries={0x5356284c:lambda:0,0x537e25fc:dma,0x536a9dd4:lambda:0,0x536a9e8c:lambda:1,0x537e29e4:lambda:0}
    p.call(0x5369a948,worker,args)
    self.assertEqual(requests,[(6,(0x60000000,0x64000000),(2992,4000,3008,pitch,0,0,x,y)),(6,(0x61000000,0x66000000),(2992,4000,3008,pitch,0,0,x,y))]);self.assertEqual(p.assertions,[])
 def test_native_dma_wait_probe_brackets_exact_wait_without_changing_bits(self):
  client,job,bits=0x55403000,0x55404000,0x55405000;worker=WORKERS[0]
  self.call('m10v_border_client_construct',client)
  self.assertEqual(self.call('m10v_border_client_prepare',client,0x03050006,0x400),1)
  self.put(worker+0x48,client,job,1);self.put(client+60,worker,job);self.put(job+4,client)
  self.complete_wait=True
  self.assertEqual(self.call('m10v_border_transfer_wait',worker+0x38,0x03050001,bits,1,worker),1)
  self.assertEqual(self.word(bits),0x03050001);self.assertEqual(self.word(client+36),1)
  if self.final_manifest and self.final_manifest['half_pair']['iip_guard'].get('trace_log'):
   self.assertEqual([p for p in self.probes if p[0]==224],[(224,62),(224,63)])
 def test_each_missing_guard_rejects_before_enqueue(self):
  for at,old,_,_ in HOOKS:
   installed=self.word(at);self.patch(at,old);self.assertEqual(self.call('m10v_half_pair_iip_ready'),0,hex(at));self.assertEqual(self.queue,[]);self.patch(at,installed)
 def test_overlap_odd_geometry_and_oom_reject_without_enqueue(self):
  self.put(self.second+4,0x60000000,0x61000000);self.assertEqual(self.call('m10v_half_pair_iip_compose',1,self.first,self.second,self.output,self.previews,1),0);self.assertEqual(self.queue,[]);self.assertEqual(self.frees,[HEAP])
  self.setUp();self.put(self.first+16,2991|(4000<<16));self.assertEqual(self.call('m10v_half_pair_iip_copy',1,self.first,self.second),0);self.assertEqual(self.allocations,[])
  self.setUp();self.fail_heap=True;self.assertEqual(self.call('m10v_half_pair_iip_compose',1,self.first,self.second,self.output,self.previews,1),0);self.assertEqual(self.queue,[]);self.assertEqual(self.frees,[])
 def test_wrong_event_cannot_release_live_client_or_metadata(self):
  self.invoke('m10v_half_pair_iip_compose',0x5c000028,self.first,self.second,self.output,self.previews,1);client=self.active_client;paused=self.u.context_save()
  self.invoke('m10v_border_client_notify',client,0x03050006,0,stack=0x55dfe000);self.assertEqual(self.word(client+36),1);self.assertEqual(self.word(client+44),0);self.assertEqual(self.frees,[]);self.assertEqual(self.word(WORKERS[0]+0x54),0x5c000028);self.u.context_restore(paused)
 def test_every_missing_completion_retains_all_owners(self):
  for completed in range(6):
   with self.subTest(completed=completed):
    self.setUp();self.invoke('m10v_half_pair_iip_compose',0x5c000028,self.first,self.second,self.output,self.previews,1)
    for _ in range(completed):self.dispatch_one()
    self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x536b0a74);self.assertEqual(self.frees,[]);self.assertEqual(len(self.queue),1);self.assertEqual(self.word(WORKERS[0]+0x54),0x5c000028)
if __name__=='__main__':unittest.main()
