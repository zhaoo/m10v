"""Final-candidate producer/Granulation control proof; no ISP pixels emulated.

The original producer, owned hooks, graph constructors, reservation, submit
header, event wait, release and encoder admission execute. Hardware drivers,
unit-reset services, OS locks/events, allocation and cache are explicit leaves.
No test writes a torn snapshot or recipe native-completion field.
"""
import hashlib,json,os,struct,subprocess,unittest,zlib
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
  runtime=cls.image[off:off+cls.manifest['code_bytes']]
  power=receipt.get('power_images') or {}
  album=cls.shutdown_album=power.get('shutdown_album_menu')
  if album:
   assert hashlib.sha256(runtime).hexdigest()==power['runtime_sha256']
   marker=cls.manifest['symbols']['m10v_settings_controller_shutdown_config']-cls.manifest['base']
   assert runtime[marker:marker+8]==struct.pack('<II',0x3141534d,album['entries'])
   runtime=runtime[:marker+4]+bytes(4)+runtime[marker+8:]
  assert hashlib.sha256(runtime).hexdigest()==cls.manifest['code_sha256']
 def test_setup_shutdown_row_reaches_its_own_controller(self):
  if not self.shutdown_album:self.skipTest('candidate has no shutdown images')
  e=StockISP(self.image)
  settings=self.manifest['settings_menu']
  hdf=self.manifest['hdf_menu']
  index=len(hdf['rows'])
  route=self.word(e,0x53b36c88+index*4)
  self.assertEqual(route,self.shutdown_album['route'])
  owner=e.alloc(settings['owner_bytes'])
  self.assertEqual(self.word(e,0x53b36bd0+index*8),settings['exports']['m10v_shutdown_album_row'])
  e.w32(0x55063910,1)
  e.w32(0x55063988,owner)
  e.w32(owner+0x13bc,settings['vtable'])
  manager,link,fs=e.alloc(12),e.alloc(4),e.alloc(0x24)
  e.w32(manager+8,link);e.w32(link,fs);e.u.mem_write(fs+0x20,b'\1')
  records,captions={},{}
  closed,displayed=[],[]
  def services(u,at,size,_):
   args=[u.reg_read(getattr(A,f'UC_ARM_REG_R{i}')) for i in range(4)]
   if at==settings['exports']['m10v_settings_factory_original']:
    self.assertEqual(args[1],0x0200004a)
    result=owner
   elif at==0x53828014:result=manager
   elif at in (0x53825648,0x53825fa8):
    name=bytes(u.mem_read(args[1],12)).split(b'\0')[0]
    self.assertIn(name,(b'M10VSA0.BIN',b'M10VSA1.BIN'))
    self.assertEqual(args[2],16)
    if at==0x53825fa8:
     records[name]=bytes(u.mem_read(args[3],16));result=1
    else:
     result=int(name in records)
     if result:u.mem_write(args[3],records[name])
   elif at==0x53396f80:captions[args[0]]=args[1];result=0
   elif at==0x5316ca28:closed.append(args[0]);result=0
   elif at==0x5322e4a8:displayed.append(args[1]);result=0
   elif at in (0x5316d354,0x533ad3c0,0x53393e00,0x5339658c,
               self.manifest['symbols'].get('m10v_debug_log')):result=0
   else:return
   u.reg_write(A.UC_ARM_REG_R0,result)
   u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
  e.u.hook_add(UC_HOOK_CODE,services)
  def open_controller(route):
   e.call(0x5316f3b8,0,route)
   return e.u.reg_read(A.UC_ARM_REG_R0)
  page=open_controller(route)
  self.assertEqual(page,owner+0x13bc+0x6c0)
  self.assertEqual(open_controller(0x0200f108),owner+hdf['owner_offset'])
  self.assertEqual(self.manifest['resources']['texts'][444],'关机图')
  widgets=[e.alloc(0x110) for _ in range(53)]
  for i,widget in enumerate(widgets):e.w32(page+0x158+i*4,widget)
  e.w32(page+0x158+56*4,len(widgets))
  self.assertEqual(self.call(e,'m10v_settings_controller_ready',page,route),1)
  self.call(e,'m10v_settings_controller_enter',page,route,0)
  self.assertEqual(captions[widgets[2]],1230)
  self.assertEqual([captions[w] for w in widgets[44:48]],[1231,1232,1233,1234])
  event=e.alloc(8)
  def press(key):
   e.w32(event,key)
   self.assertEqual(self.call(e,'m10v_settings_controller_key',page,event),1)
  press(0xd1)
  press(0xd8)
  data=records[b'M10VSA1.BIN']
  self.assertEqual(struct.unpack('<4I',data),(0x3141534d,1,1,zlib.crc32(data[:12])))
  press(0xd1)
  press(0x86)
  self.assertEqual(closed,[page])
  self.assertEqual(list(records.values()),[data])
  self.run_call_site(e,0x5319f234,0,2,0,0)
  self.assertEqual(displayed,[13])
 def word(self,e,p):return struct.unpack('<I',e.u.mem_read(p,4))[0]
 def test_jpg_and_dng_makernote_constructors_extend_stock_ifd(self):
  if not self.manifest['appended_slots'].get('photo_recipe'):self.skipTest('candidate has no photo recipe')
  e=StockISP(self.image)
  service,methods,creator,creator_methods=[e.alloc(n) for n in (4,24,4,24)]
  e.w32(0x5536c7c8,service);e.w32(service,methods);e.w32(methods+8,0x5e000010)
  e.w32(creator,creator_methods);e.w32(creator_methods+0x10,0x5e000014)
  def native_resource(u,at,size,data):
   if at==0x535d0d6c:
    result=creator
   elif at==0x5e000010:
    result=e.alloc(u.reg_read(A.UC_ARM_REG_R1))
   elif at==0x5e000014:
    result=e.alloc(24)
    u.mem_write(result+4,struct.pack('<H',u.reg_read(A.UC_ARM_REG_R1)))
   else:
    return
   u.reg_write(A.UC_ARM_REG_R0,result)
   u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
  e.u.hook_add(UC_HOOK_CODE,native_resource)
  for constructor,count in ((0x536094e4,88),(0x535f9b54,91)):
   writer,vector=e.alloc(0x2a0),e.alloc(122*4)
   ifd=writer+0x134
   e.w32(ifd+0xc,vector);e.w32(ifd+0x10,vector);e.w32(ifd+0x14,vector+122*4)
   e.call(constructor,writer)
   self.assertEqual(self.word(e,writer+0x128),ifd)
   self.assertEqual(self.word(e,ifd+0x10),vector+(count+1)*4)
   entry=self.word(e,vector+count*4)
   self.assertEqual(self.word(e,entry+4),0x0007c7f1)
   self.assertEqual(self.word(e,entry+8),176)
   self.assertNotEqual(self.word(e,entry+16),0)
 def test_native_exposure_lease_reaches_makernote_and_clears_on_reuse(self):
  if not self.manifest['appended_slots'].get('photo_recipe'):self.skipTest('candidate has no photo recipe')
  first,recipe,_,_,si,_,data=self.fixture(66,stage=0)
  self.publish_owner(first,data)
  owned_si=first.alloc(0x74330)
  first.u.mem_write(owned_si,bytes(first.u.mem_read(si,0x74270)))
  si=owned_si
  first.w32(recipe+0x44c8,si)
  first.u.mem_write(recipe+0x4a08,bytes(1796))
  first.w32(recipe+0x510c,0x42524400) # Verified default border decision.
  manager=first.alloc(0x218)
  first.w32(0x55345328,manager);first.w32(manager+0x20,0x74330);first.w32(manager+0x88,si)
  first.w32(si+0xb60,0x40800000)
  first.u.mem_write(si+0x76c,bytes((14,12,15,0,0xe0,0x15)))
  self.enqueue(first,recipe,19)
  payload=si+0x74280
  self.assertEqual(self.word(first,payload),0x3252434d)
  second,second_si=[first.alloc(n) for n in (self.manifest['torn_overlay']['recipe_bytes'],0x74330)]
  first.u.mem_write(second_si,bytes(first.u.mem_read(si,0x74270)))
  first.w32(second_si+0xb60,0x40a00000)
  first.w32(second,0x53d0fc90);first.w32(second+0x4778,0x31545653)
  first.w32(second+0x44c8,second_si);first.w32(second+0x510c,0x42524400)
  first.w32(manager+0x8c,second_si)
  self.call(first,'m10v_isp_effects_shot_reserve',second)
  self.enqueue(first,second,19)
  setter,entry,destination,registry=[first.alloc(n) for n in (0x28,0x18,176,0x100)]
  first.call(0x535fc234,registry)
  first.w32(setter+4,registry);first.w32(entry+4,0x0007c7f1)
  first.w32(entry+8,176);first.w32(entry+16,destination)
  first.u.mem_write(entry+0x14,b'\x01')
  for shot,apex in ((second_si,0x40a00000),(si,0x40800000)):
   first.call(0x535fc2d0,registry,shot)
   first.call(0x53603f18,setter)
   first.call(0x53606738,setter,entry)
   self.assertEqual(first.u.reg_read(A.UC_ARM_REG_R0),1)
   self.assertEqual(bytes(first.u.mem_read(destination,176)),bytes(first.u.mem_read(shot+0x74280,176)))
   self.assertEqual(self.word(first,destination+48),apex)
   self.assertEqual(bytes(first.u.mem_read(destination+68,2)),struct.pack('<H',5600))
   self.assertEqual(bytes(first.u.mem_read(destination+74,2)),bytes((12,15)))
   identity=self.manifest['companion']['identity']
   self.assertEqual(bytes(first.u.mem_read(destination+108,32)),bytes.fromhex(identity['catalogHash']))
   self.assertEqual(bytes(first.u.mem_read(destination+140,32)),bytes.fromhex(identity['rendererHash']))
   self.assertEqual(first.u.mem_read(entry+0x14,1),b'\x01')
  self.call(first,'m10v_isp_frame_identity_clear',si)
  first.call(0x53606738,setter,entry)
  self.assertEqual(first.u.reg_read(A.UC_ARM_REG_R0),1)
  self.assertEqual(first.u.mem_read(entry+0x14,1),b'\x01')
  self.assertEqual(bytes(first.u.mem_read(destination,176)),bytes(176))
 def test_custom_exposure_carries_the_hash_of_its_cached_record(self):
  if not self.manifest['appended_slots'].get('photo_recipe'):self.skipTest('candidate has no photo recipe')
  e,recipe,_,_,stock_si,_,data=self.fixture(79,stage=0)
  self.publish_owner(e,data)
  si,manager=e.alloc(0x74330),e.alloc(0x218)
  e.u.mem_write(si,bytes(e.u.mem_read(stock_si,0x74270)))
  e.w32(recipe+0x44c8,si);e.w32(recipe+0x510c,0x42524400)
  e.w32(0x55345328,manager);e.w32(manager+0x20,0x74330);e.w32(manager+0x88,si)
  e.u.mem_write(recipe+0x4a08,bytes(1796))
  record=bytearray(12288)
  struct.pack_into('<I',record,6688,0x5053494d)
  reads=[]
  def storage(u,at,n,d):
   if at!=self.manifest['symbols']['m10v_sd_camera_custom_record']:return
   reads.append(at)
   u.mem_write(u.reg_read(A.UC_ARM_REG_R2),bytes(record))
   u.reg_write(A.UC_ARM_REG_R0,1);u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
  h=e.u.hook_add(UC_HOOK_CODE,storage)
  self.assertEqual(self.call(e,'m10v_camera_library_mutation_begin'),1)
  self.call(e,'m10v_camera_library_mutation_end',data)
  self.assertEqual(len(reads),1)
  self.enqueue(e,recipe,19)
  e.u.hook_del(h)
  self.assertEqual(len(reads),1)
  self.assertEqual(bytes(e.u.mem_read(si+0x74280+76,32)),hashlib.sha256(record).digest())
 def run_call_site(self,e,site,*args):
  for index,value in enumerate(args):
   e.u.reg_write(getattr(A,f'UC_ARM_REG_R{index}'),value)
  e.u.reg_write(A.UC_ARM_REG_SP,0x5effff00)
  e.u.emu_start(site,site+4,count=2000000)
  self.assertEqual(e.u.reg_read(A.UC_ARM_REG_PC),site+4)
 def test_adj_highlight_cancel_and_confirm_use_the_live_and_stock_routes(self):
  e,_,_,_,_,_,data=self.fixture(66)
  self.publish_owner(e,data)
  obj=e.cursor
  _,_,shot=e.make(11,1,True,actual_live=True)
  frame=obj+0x1400
  controller,rows,event=[e.alloc(n) for n in (0x280,0x80,8)]
  model=0x55068200
  e.w32(controller,0x53b394e0)
  e.w32(controller+0x124,0x02000000)
  e.w32(controller+0x1f0,rows)
  e.w32(event,0x35)
  e.u.mem_write(0x55006004,struct.pack('<I',0x55007000))
  e.u.mem_write(0x550071c2,b'\x0b')
  writes,closes,events=[],[],[]
  def service(u,address,_,data):
   arg=u.reg_read(A.UC_ARM_REG_R1)
   if address==0x5320ad88 or address==0x5320b31c:result=0x55006000
   elif address==0x5320ba9c:result=model
   elif address==0x531a2820:result=12
   elif address==0x53394820:result=14
   elif address==0x532bd6d4:result=0
   elif address==0x532bd6b4:result=u.mem_read(0x550071c2,1)[0]
   elif address==0x532c26c0:
    writes.append(arg)
    return  # Use the genuine stock setter.
   elif address in (0x532bd61c,0x532750f8):result=0
   elif address==0x531a1998:closes.append(address);result=0
   elif address==self.manifest['settings_menu']['exports']['m10v_ab_adj_event_original']:
    events.append(bytes(u.mem_read(event,2)));result=0
   elif address==self.manifest['symbols'].get('m10v_debug_log'):result=0
   else:return
   u.reg_write(A.UC_ARM_REG_R0,result);u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
  e.u.hook_add(UC_HOOK_CODE,service)
  before=bytes(e.u.mem_read(shot-0x71248,0x80000))
  live=self.word(e,0x53dbd954)
  def banks():
   e.call(live,obj,frame)
   return bytes(e.u.mem_read(frame+0x120,0x4f68))
  initial=banks()
  e.call(0x531a0ba0,controller,14)
  candidate=banks()
  self.assertNotEqual(candidate,initial)
  self.assertEqual(self.word(e,obj+0x210),0x100)
  self.assertEqual(bytes(e.u.mem_read(shot-0x71248,0x80000)),before)
  e.call(self.manifest['symbols']['m10v_hdf_adj_event'],controller,event)
  self.assertEqual(events,[b'\x35\x00'])
  self.assertEqual(banks(),initial)
  self.assertEqual(writes,[])
  self.assertEqual(e.u.mem_read(0x550071c2,1),b'\x0b')
  e.call(0x531a0ba0,controller,14)
  self.assertEqual(banks(),candidate)
  self.run_call_site(e,0x531a4eac,controller)
  self.assertEqual(writes,[25])
  self.assertEqual(e.u.mem_read(0x550071c2,1),b'\x19')
  self.assertEqual(closes,[0x531a1998])
  self.assertEqual(self.call(e,'m10v_camera_library_adj_tone'),0)
  self.assertEqual(bytes(e.u.mem_read(shot-0x71248,0x80000)),before)
  self.assertEqual(e.assertions,[])
 def test_save_and_dial_routes_full_library_to_independent_boxes(self):
  e,_,_,_,_,_,data=self.fixture(66)
  owner=self.publish_owner(e,data)
  for site in (0x531d147c,0x5322421c,0x53224268):
   self.assertNotIn(self.word(e,site),(0xeb01e8b7,0xeb01575f,0xeb01574c))
  header=e.alloc(4)
  e.w32(0x55063ed0,1);e.w32(0x55063f30,header)
  e.w32(owner+0x13bc,self.manifest['settings_menu']['vtable'])
  filesystem,manager,app=e.alloc(0x24),e.alloc(12),e.alloc(4)
  e.w32(manager+8,app);e.w32(app,filesystem);e.u.mem_write(filesystem+0x20,b'\1')
  journal={'M10V7B.bin':bytes(e.u.mem_read(data,184))}
  stock_calls=[]
  def service(u,address,size,_):
   reg=lambda n:u.reg_read(getattr(A,f'UC_ARM_REG_R{n}'))
   if address==0x5324b760:
    stock_calls.append(('save',reg(1)));result=0
   elif address==0x53279fa0:
    stock_calls.append(('load',reg(1)));u.mem_write(header,bytes([reg(1)]));result=0
   elif address==0x53828014:result=manager
   elif address in (0x53825648,0x53825fa8):
    name=bytes(u.mem_read(reg(1),12)).split(b'\0')[0].decode()
    if address==0x53825fa8:
     journal[name]=bytes(u.mem_read(reg(3),reg(2)));result=1
    else:
     record=journal.get(name);result=int(record is not None)
     if result:u.mem_write(reg(3),record)
   elif address==self.manifest['symbols'].get('m10v_debug_log'):result=0
   else:return
   u.reg_write(A.UC_ARM_REG_R0,result);u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
  e.u.hook_add(UC_HOOK_CODE,service)
  # Drive the same hooks installed in the final BIN, exposing stock's
  # dedicated storage operations as boundaries.
  # Model the successfully booted TopMenu controller.
  e.w32(owner+0x13bc+0x358,1)
  self.run_call_site(e,0x5322421c,0x55063f30,0)
  vtable=self.manifest['settings_menu']['vtable']
  self.assertEqual(self.word(e,owner+0x13bc),vtable)
  e.w32(owner+0x613c+0x194,0x43464448)
  strength=e.alloc(4)
  self.call(e,'m10v_hdf_load',strength)
  self.call(e,'m10v_border_camera_refresh',owner)
  changed=bytearray(journal['M10V7B.bin'])
  struct.pack_into('<H',changed,12,67)
  struct.pack_into('<I',changed,180,zlib.crc32(changed[:180]))
  for box in range(1,4):
   self.assertEqual(self.call(e,'m10v_hdf_save',box-1),0)
   self.assertEqual(self.call(e,'m10v_border_camera_save',owner,box-1),0)
   if box==2:
    e.u.mem_write(data,bytes(changed))
    self.assertEqual(self.call(e,'m10v_camera_library_mutation_begin'),1)
    self.call(e,'m10v_camera_library_mutation_end',data)
   self.run_call_site(e,0x531d147c,0x55063f30,box)
   self.assertIn(f'U{box}HD1.BIN',journal)
   self.assertIn(f'U{box}BD1.BIN',journal)
   self.assertIn(f'U{box}FX1.BIN',journal)
  self.assertTrue(all(f'M10VU{n}A.BIN' in journal for n in range(1,4)))
  self.assertEqual(stock_calls,[('load',0),('save',1),('save',2),('save',3)])
  for box,film in ((1,66),(2,67),(3,67),(0,66)):
   self.run_call_site(e,0x53224268 if box else 0x5322421c,0x55063f30,box)
   self.assertEqual(self.call(e,'m10v_camera_library_preview',data),1)
   self.assertEqual(struct.unpack('<H',e.u.mem_read(data+12,2))[0],film)
   self.assertEqual(self.call(e,'m10v_hdf_cached',strength),0)
   self.assertEqual(self.word(e,strength),box-1 if box else 2)
   self.assertEqual(self.call(e,'m10v_border_camera_cached'),box-1 if box else 2)
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
