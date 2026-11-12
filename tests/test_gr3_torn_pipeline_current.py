"""Final-candidate producer/Granulation control proof; no ISP pixels emulated.

The original producer, owned hooks, graph constructors, reservation, submit
header, event wait, release and encoder admission execute. Hardware drivers,
unit-reset services, OS locks/events, allocation and cache are explicit leaves.
No test writes a torn snapshot or recipe native-completion field.
"""
import hashlib,json,os,struct,subprocess,unittest
from pathlib import Path
from unicorn import UC_HOOK_CODE
from unicorn import arm_const as A
from tests import test_gr3_film_pipeline_current as existing
from tests.test_gr3_debug import DebugLogArmTests
from tests.test_gr3_isp_base import StockISP,ROOT

class TornPipelineCurrentTests(unittest.TestCase):
 call=existing.CurrentFilmPipelineTests.call
 fixture=existing.CurrentFilmPipelineTests.fixture
 publish_owner=existing.CurrentFilmPipelineTests.publish_owner
 enqueue=existing.CurrentFilmPipelineTests.enqueue
 make=existing.CurrentFilmPipelineTests.make
 @classmethod
 def setUpClass(cls):
  folder=os.environ.get('M10V_CURRENT_PIPELINE_CANDIDATE')
  if not folder:raise unittest.SkipTest('set M10V_CURRENT_PIPELINE_CANDIDATE to the final torn delivery folder')
  folder=Path(folder);cls.manifest=json.loads((folder/'M10V-runtime-manifest.json').read_text())
  if not cls.manifest.get('torn_overlay',{}).get('enabled'):raise AssertionError('candidate lacks torn core')
  receipt=json.loads((folder/'M10V-build-receipt.json').read_text());binary=folder/receipt['filename']
  assert hashlib.sha256(binary.read_bytes()).hexdigest()==receipt['candidate_sha256']
  js="import{readFileSync}from'node:fs';import{decodeFrameMap}from'./node/gr3-frames.mjs';const b=readFileSync(process.argv[1]),d=decodeFrameMap(b,b.readUInt32LE(b.length-8)).decoded;process.stdout.write(d.subarray(0x10870,0x10870+d.readUInt32LE(0x1086c)));"
  cls.image=subprocess.check_output(['node','--input-type=module','-e',js,str(binary)],cwd=ROOT)
  off=cls.manifest['base']-0x53000000
  assert hashlib.sha256(cls.image[off:off+cls.manifest['code_bytes']]).hexdigest()==cls.manifest['code_sha256']
 def word(self,e,p):return struct.unpack('<I',e.u.mem_read(p,4))[0]
 def spatial_hook(self,e,site,ctx,params,arg,recipe):
  carrier=recipe+0x4320
  e.w32(carrier+0x30,recipe+0x1a8)
  for n,v in enumerate((ctx,params,arg,0,carrier)):
   e.u.reg_write(getattr(A,'UC_ARM_REG_R'+str(n)),v)
  e.u.reg_write(A.UC_ARM_REG_SP,0x5effff00)
  e.u.reg_write(A.UC_ARM_REG_CPSR,0x13)
  e.u.emu_start(site,site+4,count=5000000)
  self.assertEqual(e.u.reg_read(A.UC_ARM_REG_PC),site+4)
  return e.u.reg_read(A.UC_ARM_REG_R0)
 def session_start(self,e,owner,debug_batches=None,resize_requests=None):
  self.call(e,'m10v_torn_init',owner)
  e.w32(0x55064398,1);e.w32(0x55063ecc,1);e.u.mem_write(0x55067958+0x880,b'\3');e.u.mem_write(0x55063e03,b'\0');e.w32(0x55063dcc,1)
  e.w32(0x55067958+0x2c,0)
  def camera(u,pc,size,data):
   if pc==0x536a2424:result=0x55060000
   elif pc==0x536a27e8:result=0x76000000
   elif pc==0x536a248c:result=1
   elif pc==0x5320ad88:result=0x55061000
   elif pc in (0x5320b31c,0x5320ba9c):result=0x55062000
   elif pc in (0x53245190,0x53245260,0x532bd6d4):result=0
   elif pc==0x532bd6b4:result=11
   elif pc==0x53050b7c:result=0
   elif pc==self.manifest['symbols'].get('m10v_isp_effect_transfer_execute'):
    ptr=u.reg_read(A.UC_ARM_REG_R0)
    if resize_requests is not None:resize_requests.append(struct.unpack('<17I',u.mem_read(ptr,68)))
    result=1
   elif pc==self.manifest['symbols'].get('m10v_debug_batch'):
    if debug_batches is not None:
     ptr=u.reg_read(A.UC_ARM_REG_R0);count=u.reg_read(A.UC_ARM_REG_R1)
     debug_batches.extend(struct.iter_unpack('<5I',u.mem_read(ptr,count*20)))
    result=0
   else:return
   u.reg_write(A.UC_ARM_REG_R0,result);u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
  e.u.hook_add(UC_HOOK_CODE,camera)
  self.assertEqual(self.call(e,'m10v_torn_set',owner,1),0)
 def graph_leaves(self,e,context):
  """Execute native graph and owner registration; substitute physical leaves."""
  wrapper,service,driver,table=[e.alloc(n) for n in (0x40,0x200,0x40,0x400)]
  e.w32(context+8,wrapper);e.w32(wrapper+4,service);e.w32(wrapper+12,table)
  e.w32(service+0x24,driver);e.w32(service+0x2c,table);e.w32(service+0x30,table);e.w32(service+0x34,table);e.w32(service+0x38,table)
  e.u.mem_map(0x28880000,0x10000);e.w32(0x28880004,2)
  record={'bindings':[],'weights':[],'curves':[],'submit':[],'wait_events':[],'releases':0,'rng':0,'leaf_calls':[]}
  next_handle=[0]
  # Original scheduler calls these unit reset services after reservation. Their
  # device state is external; the graph creation/linking itself is not replaced.
  resets={0x537640d0,0x53766910,0x53770750,0x537744c4,0x5376b8e8,0x5376702c,0x53773998,0x5376852c,0x5376a668}
  def reg(n):return e.u.reg_read(getattr(A,'UC_ARM_REG_R'+str(n)))
  def leaf(u,pc,size,data):
   result=1
   if pc in (0x5376c434,0x5376c45c):
    # Unicorn's macOS build SIGILLs on these metadata u64 shifts. Execute
    # their ARM bitset semantics only; no pixel arithmetic is substituted.
    shift=u.reg_read(A.UC_ARM_REG_D17)&255
    if shift&128:shift-=256
    value=u.reg_read(A.UC_ARM_REG_D8)
    result=((value<<shift) if shift>=0 else (value>>-shift))&0xffffffffffffffff if abs(shift)<64 else 0
    u.reg_write(A.UC_ARM_REG_D16,result);u.reg_write(A.UC_ARM_REG_PC,pc+4)
    record.setdefault('resource_bitset_instruction_substitutions',[]).append(pc);return
   if pc==0x5368a92c:record['rng']+=1;raise AssertionError('CPU RNG entered')
   if pc==0x5376bc08:record['bindings'].append((reg(1),reg(2)));return
   if pc==0x5376bc38:record['weights'].append((reg(1),reg(2)));return
   if pc==0x5376cd10:
    graph=reg(1);record['curves'].append(tuple(struct.unpack('<256h',u.mem_read(self.word(e,graph+off),512)) for off in (0x5c,0x6c,0x60)));return
   if pc==0x5376e55c:
    info=reg(1);record['submit'].append((reg(0),self.word(e,info+0x78),bytes(u.mem_read(info,0x7c))))
    return # native submit header publishes the real reservation mask
   if pc==0x5376c044:record['releases']+=1;return
   if pc==0x536a9e8c:
    # Hardware completion is represented only as an OS event; the original
    # wait routine and owned completion helper consume it themselves.
    e.w32(reg(2),0x400);record['wait_events'].append((reg(0),reg(1)))
   elif pc==0x53779dd4:result=next_handle[0];next_handle[0]+=1
   elif pc in (0x53870cc8,0x53870d38,0x53778490,0x53778474,0x537794bc,0x537794d0,0x537794e4,0x537794f8,0x5377950c,0x53779520):result=0
   elif pc in (0x536bbc30,):result=0
   elif pc in (0x536bbcac,0x536bbc3c,0x5383c8a8,0x5387110c,0x5377c4d4,0x53775018,0x5377c1c8,0x5377c214,0x53779e74,0x53783820,0x53784de0,0x536b00c8,0x536b0014,0x536ae71c,0x536ae870,0x536a848c,0x536a8544):pass
   elif pc in resets:pass
   elif 0x53778000<=pc<0x53779744:
    # Native hardware register services. Ready/status reads return idle0;
    # start handshake reads use1 so native submit can progress.
    result=0 if pc in (0x537780a8,0x537780d4,0x53778100,0x537785f8) else 1
   elif pc==0x537700a0:result=wrapper
   elif pc==0x536b0a74:raise AssertionError('native hold/wait did not drain')
   else:return
   record['leaf_calls'].append(pc);u.reg_write(A.UC_ARM_REG_R0,result);u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
  e.u.hook_add(UC_HOOK_CODE,leaf);return record
 def test_rejected_shot_keeps_its_exact_reason_after_the_shared_trace_fills(self):
  if not self.manifest.get('debug_mode'):self.skipTest('requires a debug delivery')
  e,recipe,obj,frame,si,request,data=self.fixture(66,stage=0)
  batches=[]
  self.session_start(e,self.publish_owner(e,data),batches)
  self.enqueue(e,recipe,19)
  self.make(e,recipe,obj,frame)
  photo=e.alloc(32)
  # An incompatible layout should leave the original unmodified and must
  # still explain its rejection when no more shared records fit.
  e.u.mem_write(photo,struct.pack('<8I',2,0x70000000,0x74000000,0,
                                640|(480<<16),640|(480<<16),0,1))
  for _ in range(32):
   self.call(e,'m10v_save_trace_recipe_mark',recipe,198,0,0,0)
  self.assertEqual(self.call(e,'m10v_torn_execute',recipe,e.alloc(0x40),photo),0xffffffff)
  self.assertEqual(self.call(e,'m10v_torn_encoder_admit',recipe,si),1)
  self.call(e,'m10v_lifecycle_phase',recipe+0x9b8,190,0)
  self.assertEqual([r for r in batches if r[0]==225],
                   [(225,recipe,2,1<<8,(-(6|((1|32)<<8)))&0xffffffff)])
  self.assertTrue(any(r[0]==199 for r in batches))
 def test_real_producer_freezes_exact_recipe_then_original_graph_and_encoder(self):
  e,recipe,obj,frame,si,request,data=self.fixture(66,stage=0)
  resizes=[]
  owner=self.publish_owner(e,data);self.session_start(e,owner,resize_requests=resizes)
  self.call(e,'m10v_torn_reserve',recipe)
  e.u.mem_write(recipe+0x4a08,bytes(1796))
  self.enqueue(e,recipe,19)
  p=recipe+0x57d8;frozen=bytes(e.u.mem_read(p,32))
  self.assertEqual(struct.unpack('<8I',frozen)[:3],(0x31524f54,recipe,si))
  self.assertEqual(struct.unpack('<8I',frozen)[4],1)
  # Later UI selection is different; subsequent original producer messages
  # must not rebuild this recipe's identity or its phase.
  e.u.mem_write(owner+0x2144,bytes(184));e.w32(owner+0x2140,8)
  self.enqueue(e,recipe,0);self.assertEqual(bytes(e.u.mem_read(p,32)),frozen)
  self.make(e,recipe,obj,frame)
  ctx=e.alloc(0x40);photo=e.alloc(32)
  e.u.mem_write(photo,struct.pack('<8I',1,0x70000000,0x74000000,0,640|(480<<16),640|(480<<16),0,2))
  # Native RAW still belongs to a separate allocation. No borrowed pixel is
  # mapped and no photo copy/threshold/blend can execute on the CPU.
  e.w32(recipe+0x60,0x7c000000);dims=e.alloc(4);e.w32(dims,640|(480<<16));e.w32(recipe+0x230,dims)
  record=self.graph_leaves(e,ctx)
  params,other,values,query=[e.alloc(n) for n in (0x34,32,12,4)]
  e.u.mem_write(other,struct.pack('<8I',1,0x71000000,0x75000000,0,640|(480<<16),640|(480<<16),0,2))
  e.u.mem_write(params,struct.pack('<13I',0,photo,other,0,values,0,0,0,0,0,0,0,0))
  self.call(e,'m10v_isp_effects_pipeline_settings',recipe,si,params,0)
  self.assertEqual(self.word(e,params+0x20),recipe)
  self.assertEqual(self.spatial_hook(e,0x535033e8,ctx,params,query,recipe),1)
  self.assertEqual(self.call(e,'m10v_torn_encoder_admit',recipe,si),0)
  # Model an original worker rewriting normalized drive after the owning
  # producer has already admitted this single exposure.
  e.u.mem_write(si+0x799,b'\x02')
  self.assertEqual(self.spatial_hook(e,0x53503ab4,ctx,params,0,recipe),1)
  self.assertEqual(self.call(e,'m10v_torn_encoder_admit',recipe,si),1)
  self.assertEqual(self.call(e,'m10v_isp_effects_pipeline_encoder_admit',recipe,si),1)
  self.assertEqual(self.word(e,p+28),1);self.assertEqual(record['rng'],0)
  bindings=[(0x76000000,640),(0x76000000,640),
            (0x70000000,640),(0x70000000,640),(0x74000000,640),(0x74000000,640),
            (0x76000000,640),(0x76000000,640),(0x70000000,640),(0x70000000,640)]
  self.assertEqual(record['bindings'],bindings)
  self.assertEqual(len(record['submit']),5);self.assertEqual(record['releases'],5);self.assertEqual(len(record['wait_events']),5)
  e.u.mem_write(si+0x799,b'\x00')
  # The second exposure is independently allocated and enters through the
  # SAME original producer. Reserve initializes an empty tail; it does not
  # create a frozen snapshot or report completion.
  e.u.mem_write(owner+0x2144,bytes(e.u.mem_read(data,184)));e.w32(owner+0x2140,2)
  second=e.alloc(self.manifest['torn_overlay']['recipe_bytes']);second_si=e.alloc(0x74280);second_request=e.alloc(0x40)
  e.u.mem_write(second_si,bytes(e.u.mem_read(si,0x74270)))
  e.w32(second,0x53d0fc90);e.w32(second+0x4778,0x31545653);e.w32(second+0x44c8,second_si);e.w32(second+0x5c,second_request)
  e.w32(frame+0x82d0,second_si)
  e.u.reg_write(A.UC_ARM_REG_R0,second);e.u.reg_write(A.UC_ARM_REG_R4,second);e.u.emu_start(0x5350eb10,0x5350eb38,count=100)
  self.call(e,'m10v_isp_effects_shot_reserve',second);self.enqueue(e,second,19)
  second_frozen=struct.unpack('<8I',e.u.mem_read(second+0x57d8,32))
  self.assertEqual(second_frozen[:3],(0x31524f54,second,second_si));self.assertEqual(second_frozen[4],1)
  self.make(e,second,obj,frame)
  e.w32(second+0x60,0x7c000000);e.w32(second+0x230,dims)
  self.call(e,'m10v_isp_effects_pipeline_settings',second,second_si,params,0)
  self.assertEqual(self.spatial_hook(e,0x535033e8,ctx,params,query,second),1)
  self.assertEqual(self.call(e,'m10v_torn_encoder_admit',second,second_si),0)
  self.assertEqual(self.spatial_hook(e,0x53503ab4,ctx,params,0,second),1)
  self.assertEqual(self.call(e,'m10v_isp_effects_pipeline_encoder_admit',second,second_si),1)
  self.assertEqual(self.word(e,second+0x57d8+28),1)
  self.assertEqual(record['bindings'],bindings*2)
  self.assertEqual(len(record['submit']),10);self.assertEqual(record['releases'],10);self.assertEqual(len(record['wait_events']),10)
  self.assertEqual(record['weights'],[(0x70000000,640),(0x76000000,640),
      (0x76000000,640),(0x70000000,640),(0x76000000,640)]*2)
  self.assertEqual(len(resizes),4)
  self.assertEqual(resizes[0],resizes[1]);self.assertEqual(resizes[2],resizes[3])
  self.assertNotEqual(resizes[0][1],resizes[2][1])
  masks=self.manifest['torn_overlay']['core']['masks']
  from scripts.build_gr3_torn_overlay import _mask_blob
  self.assertEqual(self.manifest['torn_overlay']['core']['layout'],'center-tear')
  offset=masks['base']-0x53000000
  self.assertEqual(self.image[offset:offset+masks['bytes']],_mask_blob())
  stride=masks['bytes']//masks['count']
  self.assertTrue(all(r[1] in [masks['base']+n*stride for n in range(masks['count'])] for r in resizes))
  for r in resizes:
   luma=bytes(e.u.mem_read(r[1],masks['width']*masks['height']))
   self.assertEqual(min(luma),0)
   self.assertGreaterEqual(max(luma),214) # backing shade above the opaque lip
   self.assertGreater(len(set(luma)),16)
  self.assertTrue(all(r[8:13]==(2,0x76000000,0x76000000+640*480,0,640|(480<<16)) for r in resizes))
  identity=tuple(range(256))
  edge_a,edge_b,edge_out=record['curves'][0]
  self.assertEqual(edge_a,edge_b);self.assertEqual(edge_out,identity)
  self.assertEqual(edge_a[:117],(0,)*117)
  self.assertEqual(edge_a[124:],(255,)*132)
  self.assertEqual(edge_a[120],128)
  shadow_a,shadow_b,shadow_out=record['curves'][3]
  self.assertEqual(shadow_a,shadow_b);self.assertEqual(shadow_out,identity)
  self.assertFalse(any(shadow_a[:132]))
  self.assertGreater(max(shadow_a),shadow_a[255])
  self.assertGreater(shadow_a[255],shadow_a[214])
  self.assertEqual(record['curves'],[(edge_a,edge_b,identity),
      ((255,)*256,identity,identity),((128,)*256,identity,identity),
      (shadow_a,shadow_b,identity),((205,)*256,identity,identity)]*2)
  self.assertEqual(self.call(e,'m10v_torn_state',query,query+4),1);self.assertEqual(self.word(e,query),1)
  self.assertEqual(e.assertions,[])

class TornDedicatedLogTests(unittest.TestCase):
 setUp=DebugLogArmTests.setUp
 services=DebugLogArmTests.services
 log=DebugLogArmTests.log
 decoded=DebugLogArmTests.decoded
 @classmethod
 def setUpClass(cls):
  folder=os.environ.get('M10V_CURRENT_PIPELINE_CANDIDATE')
  if not folder:raise unittest.SkipTest('set M10V_CURRENT_PIPELINE_CANDIDATE')
  folder=Path(folder)
  cls.manifest=json.loads((folder/'M10V-runtime-manifest.json').read_text())
  if 'M10VTO0.BIN' not in (cls.manifest.get('debug_log') or {}).get('files',[]):
   raise unittest.SkipTest('requires dedicated torn logging')
  cls.code=(folder/'M10V-runtime-arm.bin').read_bytes()
 def test_outcome_writes_independent_pages_and_decodes_after_restart(self):
  self.assertEqual(self.log(225,0x55005000,2,0x100,(-0x2106)&0xffffffff),1)
  self.assertEqual(self.log(198,0x55005000,0,0,0),1)
  self.assertEqual(self.log(225,0x55005000,3,0x201,1),1)
  self.assertTrue(all('C:\\'+name in self.files for name in ('M10VTO0.BIN','M10VTO1.BIN')))
  outcomes=[row['torn'] for row in self.decoded()['records'] if row['channel']=='torn']
  self.assertEqual(len(outcomes),2)
  self.assertEqual(outcomes[0]['layout_faults'],['format','address-mode'])
  self.assertEqual(outcomes[1]['phase'],2)
  self.assertTrue(outcomes[1]['complete'])

class NativePlaneGraphControlTests(unittest.TestCase):
 word,graph_leaves=TornPipelineCurrentTests.word,TornPipelineCurrentTests.graph_leaves
 @classmethod
 def setUpClass(cls):
  from scripts import build_gr3_isp_effect_granulation as g
  js="import{readFileSync}from'node:fs';import{officialResources}from'./node/gr3-stock-presets.mjs';const{decoded:d,sections:s}=officialResources(readFileSync('bin/fwdc239b-gr3-official.bin'));process.stdout.write(d.subarray(s.RTOS.offset,s.RTOS.offset+s.RTOS.size));"
  rom=subprocess.check_output(['node','--input-type=module','-e',js],cwd=ROOT)
  code,cls.manifest=g.build(0x54190000,rom,enabled=True)
  image=bytearray(rom);off=0x1190000;image.extend(bytes(max(0,off+len(code)-len(image))));image[off:off+len(code)]=code
  for p in cls.manifest['patches']:struct.pack_into('<I',image,p['address']-0x53000000,p['replacement'])
  cls.image=bytes(image)
 def test_original_resize_plans_full_resolution_mask_without_reading_pixels(self):
  from scripts.border_resize_contract import probe
  from scripts.build_gr3_torn_overlay import MASK_WIDTH,MASK_HEIGHT
  rom=(ROOT/'builds/gr3-extension-validation/official-rtos.bin').read_bytes()
  result=probe(rom,6000,4000,fmt=2,source_format=2,
               source_size=(MASK_WIDTH,MASK_HEIGHT),source_stride=MASK_WIDTH,
               source_plane=0x54218000,destination_stride=6000,texture_research=True)
  self.assertEqual(result['assertions'],[])
  self.assertFalse(result['pixels_mapped'])
  self.assertTrue(result['scaler_configuration_executed'])
  luma,chroma=result['scaler_requests']
  self.assertEqual(luma['destination']['size'],[6000,4000])
  self.assertEqual(chroma['destination']['size'],[3000,2000])
 def test_original_graph_independent_mask_destination_then_inplace_y_uv(self):
  e=StockISP(self.image);ctx=e.alloc(0x40);src=e.alloc(32);dst=e.alloc(32);curves=e.alloc(1536)
  # Coefficients are bounded metadata; photo addresses stay unmapped.
  e.u.mem_write(curves,struct.pack('<768h',*([0]*256+list(range(256))*2)))
  record=self.graph_leaves(e,ctx)
  for source,destination,mask in ((0x70000000,0x76000000,0x70000000),(0x70000000,0x70000000,0x76000000),(0x74000000,0x74000000,0x76000000)):
   e.u.mem_write(src,struct.pack('<8I',1,source,0,0,640|(480<<16),640|(480<<16),0,2))
   e.u.mem_write(dst,struct.pack('<8I',1,destination,0,0,640|(480<<16),640|(480<<16),0,2))
   e.u.mem_write(0x5effff00,struct.pack('<3I',307200,640,curves))
   e.call(self.manifest['symbols']['m10v_isp_effect_granulation_plane'],ctx,dst,src,mask)
   self.assertEqual(e.u.reg_read(A.UC_ARM_REG_R0),1)
  self.assertEqual(record['bindings'],[(0x70000000,640),(0x76000000,640),(0x70000000,640),(0x70000000,640),(0x74000000,640),(0x74000000,640)])
  self.assertEqual(len(record['submit']),3);self.assertEqual(record['releases'],3);self.assertEqual(len(record['wait_events']),3);self.assertEqual(record['rng'],0)
  self.assertEqual(e.assertions,[])
