"""Execute production owner callbacks through the original AppMain timer route."""
import ctypes as C,hashlib,os,struct,subprocess,tempfile,unittest,zlib
from pathlib import Path
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC
from tests.test_gr3_companion_timer_arm import TimerMachine,BASE,MODEL,RECORD,STOP
ROOT=Path(__file__).resolve().parents[1]
class ProductionOwner(unittest.TestCase):
 feature_flags=[]
 native_sources=[]
 @classmethod
 def setUpClass(cls):
  cls.source=ROOT/'native/gr3/m10v_companion_owner.c'
  cls.ready=cls.source.exists()
  if not cls.ready:return
  cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup);d=Path(cls.tmp.name)
  identity=d/'identity.h';identity.write_text('\n'.join('#define M10V_COMPANION_'+k+'_BYTES {'+','.join(['1']*32)+'}' for k in ['BUILD','CATALOG','RENDERER']))
  files=[cls.source,*[ROOT/'native/companion'/f for f in ['resident_bridge.c','auth.c','operations.c','json.c','transaction.c','extensions.c','runtime.c']],ROOT/'native/gr3/m10v_library.c',*[ROOT/name for name in cls.native_sources]];objects=[]
  for i,p in enumerate(files):
   obj=d/f'{i}.o';subprocess.run(['clang','--target=armv7-none-eabi','-mcpu=cortex-a9','-marm','-mfloat-abi=soft','-Os','-ffreestanding','-fno-builtin','-ffunction-sections','-fdata-sections','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-Wall','-Wextra','-Werror',*cls.feature_flags,'-DM10V_COMPANION_ENABLED=1','-DM10V_APPENDED_SLOTS=1','-DM10V_LIVE_COLOR=1','-include',str(identity),'-c',str(p),'-o',str(obj)],check=True,capture_output=True);objects.append(obj)
  cls.ports={name:0x54010000+i*64 for i,name in enumerate(['m10v_camera_library_read_current','m10v_camera_library_mutation_begin','m10v_camera_library_mutation_end','m10v_camera_library_mutation_busy','m10v_camera_library_commit_snapshot','m10v_sd_camera_custom_record','m10v_camera_library_shooting_count','m10v_settings_controller_remote_busy'])}
  elf=d/'owner.elf';subprocess.run(['ld.lld','-m','armelf_linux_eabi','--gc-sections','--entry=m10v_companion_ui_init','--undefined=m10v_companion_ui_stop','--undefined=m10v_companion_ui_storage_enter','--undefined=m10v_companion_ui_storage_leave','-Ttext=0x540c0000',*[f'--defsym={k}={v}' for k,v in cls.ports.items()],*[str(p) for p in objects],'-o',str(elf)],check=True,capture_output=True)
  cls.elf=elf.read_bytes();nm=subprocess.check_output(['/opt/homebrew/opt/llvm/bin/llvm-nm','--defined-only',str(elf)],text=True);cls.symbols={line.split()[2]:int(line.split()[0],16) for line in nm.splitlines() if len(line.split())==3}
  path=Path(os.environ.get('M10V_GR3_ORIGINAL_RTOS','/Users/zhaoo/.codex/worktrees/film-companion/diagnostic-20261101/source/builds/gr3-extension-validation/official-rtos.bin'));cls.firmware=path.read_bytes();assert hashlib.sha256(cls.firmware).hexdigest()=='8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67'
 def machine(self):
  m=TimerMachine(self.firmware,b'');m.instruction_budget=1000000;b=self.elf;phoff=struct.unpack_from('<I',b,28)[0];size,count=struct.unpack_from('<HH',b,42)
  for i in range(count):
   kind,off,at,_,n,_,_,_=struct.unpack_from('<8I',b,phoff+size*i)
   if kind==1:
    if not (0x53000000<=at<0x56000000):m.u.mem_map(at&~4095,((at%4096+n+4095)//4096)*4096)
    m.u.mem_write(at,b[off:off+n])
  m.set(0x55063910,1);m.set(0x55063988,0x55860000);m.saves=0;m.allocations=0;m.native_callback_locks=[];m.mutation=0;m.tone=25
  m.load_result=0;m.pause_on_load=False;m.fail_after_commit=False;m.state=bytearray(184);struct.pack_into('<IHHI',m.state,0,0x5630314d,5,184,17)
  for i in range(10):struct.pack_into('<HBBBBBB',m.state,12+8*i,34+i,0,0,0,3,5,6)
  struct.pack_into('<I',m.state,180,zlib.crc32(m.state[:180]))
  for guard in [0x55064398,0x55063ecc,0x55063dcc]:m.set(guard,1)
  m.u.mem_write(0x55067958+0x880,b'\x03')
  # Complete the native owner unlock between repeated queue turns; UI
  # presentation itself is a boundary, not part of the mailbox contract.
  m.set(0x56006000,0x56006100);m.set(0x56006100+0x2c,0x54018000);m.set(0x56006100+0x30,0x54018000);m.u.mem_write(0x54018000,bytes.fromhex('1eff2fe1'))
  m.drain_on_appmain=lambda:m.run(0x53207e88,stop=0x53228c20)
  def hook(u,pc,n,ctx):
   args=[u.reg_read(r) for r in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2]];result=None
   if pc==0x536af2a8:m.allocations+=1;self.assertLess(args[0],17000);result=0x55810000
   elif pc in [0x5383c834,0x5383c870]:result=0
   elif pc==0x53228a90:result=0x56006000
   elif pc==self.symbols['m10v_companion_ui_timer']:m.native_callback_locks.append((m.locks.get(0x550645f0+0x38,0),m.locks.get(0x550645f0+0x24,0)))
   elif pc==self.ports['m10v_camera_library_read_current']:
    u.mem_write(args[0],bytes(m.state));result=m.load_result
    if m.pause_on_load:u.emu_stop();return
   elif pc==self.ports['m10v_camera_library_mutation_begin']:
    result=int(not m.mutation);m.mutation=1
   elif pc==self.ports['m10v_camera_library_mutation_end']:m.mutation=0;result=0
   elif pc==self.ports['m10v_camera_library_mutation_busy']:result=m.mutation
   elif pc==self.ports['m10v_camera_library_commit_snapshot']:
    self.assertEqual(m.mutation,1);m.saves+=1;m.state=bytearray(u.mem_read(args[0],184));result=0
    if m.fail_after_commit:m.load_result=-1;result=-1
   elif pc==self.ports['m10v_settings_controller_remote_busy']:result=0
   elif pc==0x532bd6b4:result=m.tone
   elif pc==0x532bd6d4:result=0
   elif pc in self.ports.values():self.fail('unexpected settings service in HELLO lifecycle test')
   if result is not None:u.reg_write(UC_ARM_REG_R0,result);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
  m.u.hook_add(UC_HOOK_CODE,hook);return m
 def test_native_timer_hello_and_cancel_do_not_write_settings_or_free_mailbox(self):
  self.assertTrue(self.ready,'missing production UI owner')
  m=self.machine();m.run(self.symbols['m10v_companion_ui_init'],0x55860000)
  descriptor=0x55860000+0x6400;context=m.word(descriptor+12);wire=m.word(descriptor+16)
  self.assertGreaterEqual(context,0x55810000);self.assertEqual(wire%128,0);self.assertEqual(m.word(wire+12),0)
  m.run(self.symbols['m10v_companion_ui_start'],0x55860000);self.assertEqual(m.word(wire+12),1)
  request=wire+128;payload=bytes([7]*16);crc=zlib.crc32(struct.pack('<5I',2,1,len(payload),0,0)+payload)
  m.u.mem_write(request,struct.pack('<6I',2,1,len(payload),crc,0,0));m.u.mem_write(request+128,payload)
  m.alarm_active=False;m.queue_timer_wakeup();m.drain_on_appmain()
  response=wire+128+1152;self.assertEqual(m.word(response),2);self.assertEqual(m.word(response+20),0)
  self.assertEqual(m.native_callback_locks,[(1,0)]);self.assertEqual(m.saves,0)
  m.run(self.symbols['m10v_companion_ui_stop'],0x55860000);self.assertEqual(m.word(wire+12),0);self.assertEqual(m.word(RECORD+8),0);self.assertEqual(m.allocations,1)
  m.queue_timer_wakeup();m.drain_on_appmain();self.assertEqual(m.native_callback_locks,[(1,0)]);self.assertEqual(m.saves,0)

 def exchange(self,m,wire,sequence,command,payload=b''):
  request=wire+128;crc=zlib.crc32(struct.pack('<5I',sequence,command,len(payload),0,0)+payload)
  m.u.mem_write(request,struct.pack('<6I',sequence,command,len(payload),crc,0,0));m.u.mem_write(request+128,payload)
  m.alarm_active=False;m.queue_timer_wakeup();m.drain_on_appmain()
  response=wire+128+1152;self.assertEqual(m.word(response),sequence);self.assertEqual(m.word(response+16),crc)
  return m.word(response+20),bytes(m.u.mem_read(response+128,m.word(response+8)))
 def test_actual_owner_reads_ten_slots_commits_once_and_rejects_capture_busy(self):
  self.assertTrue(self.ready,'missing production UI owner')
  class Patch(C.Structure):
   _fields_=[('id',C.c_uint8*16),('boot',C.c_uint8*16),('revision',C.c_uint8*32),('catalog',C.c_uint8*32),('renderer',C.c_uint8*32),('fields',C.c_uint16*10),('values',(C.c_uint16*13)*10),('custom',(C.c_uint8*32)*10),('active',C.c_int8),('mask',C.c_uint16)]
  m=self.machine();m.run(self.symbols['m10v_companion_ui_init'],0x55860000);wire=m.word(0x55860000+0x6400+16);m.run(self.symbols['m10v_companion_ui_start'],0x55860000)
  self.assertEqual(self.exchange(m,wire,2,1,bytes([7]*16))[0],0)
  code,read=self.exchange(m,wire,4,2);self.assertEqual(code,0);self.assertEqual(struct.unpack_from('<III',read),(2,0,1));self.assertEqual(read[12:196],m.state)
  before=bytes(m.state);p=Patch();p.id[:]=bytes([9]*16);p.boot[:]=bytes([7]*16);p.revision[:]=read[548:580];p.catalog[:]=p.renderer[:]=bytes([1]*32);p.active=-1;p.mask=1<<9;p.fields[9]=1<<1;p.values[9][1]=2
  code,result=self.exchange(m,wire,6,3,bytes(p));self.assertEqual(code,0);self.assertEqual(struct.unpack_from('<III',result),(2,0,1));self.assertEqual(m.saves,1);self.assertEqual(m.state[86],2)
  for i in range(12,180):
   if i!=86:self.assertEqual(m.state[i],before[i])
  self.exchange(m,wire,6,3,bytes(p));self.assertEqual(m.saves,1)
  self.exchange(m,wire,8,3,bytes(p));self.assertEqual(m.saves,1)
  p.id[0]=10;p.revision[:]=result[548:580];p.values[9][1]=1;m.u.mem_write(0x55067958+0x2c,b'\x01')
  code,rejected=self.exchange(m,wire,10,3,bytes(p));self.assertEqual(code,6);self.assertEqual(m.saves,1);self.assertEqual(m.mutation,0)
  self.assertTrue(all(pair==(1,0) for pair in m.native_callback_locks))

 def test_shared_store_gate_rejects_nested_local_and_remote_writes(self):
  self.assertIn('m10v_companion_ui_storage_enter',self.symbols)
  m=self.machine();owner=0x55860000;m.run(self.symbols['m10v_companion_ui_init'],owner)
  enter=self.symbols['m10v_companion_ui_storage_enter'];leave=self.symbols['m10v_companion_ui_storage_leave']
  token=m.run(enter,0);self.assertGreater(token,1);self.assertEqual(m.run(enter,0),0);self.assertEqual(m.run(enter,1),0);self.assertEqual(m.run(leave,token),1)
  self.assertEqual(m.run(enter,1),0)
  token=m.run(enter,0);m.run(self.symbols['m10v_companion_ui_stop'],owner);self.assertEqual(m.run(leave,token),0)

 def test_migrated_or_default_state_is_never_a_current_remote_snapshot(self):
  for load_result in [1,2,3,4]:
   with self.subTest(load_result=load_result):
    m=self.machine();m.load_result=load_result;m.run(self.symbols['m10v_companion_ui_init'],0x55860000);wire=m.word(0x55860000+0x6400+16);m.run(self.symbols['m10v_companion_ui_start'],0x55860000)
    self.assertEqual(self.exchange(m,wire,2,1,bytes([7]*16))[0],0)
    code,result=self.exchange(m,wire,4,2);self.assertNotEqual(code,0);self.assertEqual(struct.unpack_from('<I',result,8)[0],0);self.assertEqual(m.saves,0)
 def test_read_during_local_store_or_mutation_is_busy_and_has_no_snapshot(self):
  for with_store in [False,True]:
   with self.subTest(with_store=with_store):
    m=self.machine();m.run(self.symbols['m10v_companion_ui_init'],0x55860000);wire=m.word(0x55860000+0x6400+16);m.run(self.symbols['m10v_companion_ui_start'],0x55860000)
    self.exchange(m,wire,2,1,bytes([7]*16));token=m.run(self.symbols['m10v_companion_ui_storage_enter'],0) if with_store else 0;m.mutation=1
    code,result=self.exchange(m,wire,4,2);self.assertEqual(code,6);self.assertEqual(struct.unpack_from('<I',result,8)[0],0);self.assertEqual(m.saves,0)
    m.mutation=0
    if token:self.assertEqual(m.run(self.symbols['m10v_companion_ui_storage_leave'],token),1)
    self.assertEqual(self.exchange(m,wire,6,2)[0],0)

 def test_local_store_completing_during_read_invalidates_snapshot(self):
  m=self.machine();m.run(self.symbols['m10v_companion_ui_init'],0x55860000);wire=m.word(0x55860000+0x6400+16);m.run(self.symbols['m10v_companion_ui_start'],0x55860000);self.exchange(m,wire,2,1,bytes([7]*16))
  m.pause_on_load=True
  with self.assertRaisesRegex(AssertionError,'ARM did not reach boundary'):self.exchange(m,wire,4,2)
  self.assertEqual(m.u.reg_read(UC_ARM_REG_PC),self.ports['m10v_camera_library_read_current'])
  u=m.u;saved=u.context_save()
  try:
   u.reg_write(UC_ARM_REG_SP,0x56008000);u.reg_write(UC_ARM_REG_LR,STOP);u.reg_write(UC_ARM_REG_R0,0);u.emu_start(self.symbols['m10v_companion_ui_storage_enter'],STOP,count=10000);token=u.reg_read(UC_ARM_REG_R0);self.assertGreater(token,1)
   u.reg_write(UC_ARM_REG_LR,STOP);u.reg_write(UC_ARM_REG_R0,token);u.emu_start(self.symbols['m10v_companion_ui_storage_leave'],STOP,count=10000);self.assertEqual(u.reg_read(UC_ARM_REG_R0),1)
  finally:u.context_restore(saved)
  m.pause_on_load=False;u.emu_start(u.reg_read(UC_ARM_REG_PC),STOP,count=1000000);self.assertEqual(u.reg_read(UC_ARM_REG_PC),0x53228c20)
  response=wire+128+1152;self.assertEqual(m.word(response),4);self.assertEqual(m.word(response+20),6);self.assertEqual(m.word(response+128+8),0)
  self.assertEqual(self.exchange(m,wire,6,2)[0],0)

 def test_extensions_stamp_single_commit_shared_revision_and_unsupported_gate(self):
  m=self.machine();owner=0x55860000;m.run(self.symbols['m10v_companion_ui_init'],owner);wire=m.word(owner+0x6400+16);m.run(self.symbols['m10v_companion_ui_start'],owner)
  self.assertEqual(self.exchange(m,wire,2,1,bytes([7]*16))[0],0)
  code,read=self.exchange(m,wire,4,5);self.assertEqual(code,0)
  self.assertEqual(struct.unpack_from('<I',read,12)[0],31<<12)
  before=bytes(m.state);contract=bytes.fromhex('9df047418574e23fd399a0c59491aecc9ea212dbf119a79ff29532aec6493628')
  def patch(ident,field,value,revision):return bytes([ident]*16)+bytes([7]*16)+contract+revision+struct.pack('<II',field,value)
  p=patch(9,12,2,read[-32:]);code,result=self.exchange(m,wire,6,6,p)
  self.assertEqual(code,0);self.assertEqual(struct.unpack_from('<III',result),(2,0,1));self.assertEqual(m.saves,1);self.assertEqual(m.state[92],2)
  self.assertEqual(m.state[12:92],before[12:92]);self.assertEqual(m.state[93:180],before[93:180])
  self.exchange(m,wire,8,6,p);self.assertEqual(m.saves,1)
  # Earlier extension revision is invalid after the shared journal commit.
  self.assertEqual(self.exchange(m,wire,10,6,patch(10,13,1,read[-32:]))[0],7)
  self.assertEqual(self.exchange(m,wire,12,6,patch(11,3,1,result[-32:]))[0],5)
  self.assertEqual(m.saves,1)

 def test_extension_uncertainty_blocks_local_film_store_until_poll_readback(self):
  m=self.machine();owner=0x55860000;m.run(self.symbols['m10v_companion_ui_init'],owner);wire=m.word(owner+0x6400+16);m.run(self.symbols['m10v_companion_ui_start'],owner)
  self.exchange(m,wire,2,1,bytes([7]*16));_,read=self.exchange(m,wire,4,5)
  ident=bytes([22]*16);contract=bytes.fromhex('9df047418574e23fd399a0c59491aecc9ea212dbf119a79ff29532aec6493628')
  payload=ident+bytes([7]*16)+contract+read[-32:]+struct.pack('<II',16,1)
  m.fail_after_commit=True;code,result=self.exchange(m,wire,6,6,payload)
  self.assertEqual(struct.unpack_from('<I',result)[0],4);self.assertEqual(m.saves,1)
  m.run(self.symbols['m10v_companion_ui_storage_enter'],0)
  from unicorn.arm_const import UC_ARM_REG_R0
  self.assertEqual(m.u.reg_read(UC_ARM_REG_R0),0)
  m.load_result=0;m.fail_after_commit=False;code,result=self.exchange(m,wire,8,7,ident)
  self.assertEqual(code,0);self.assertEqual(struct.unpack_from('<III',result),(2,0,1));self.assertEqual(m.saves,1)
  m.run(self.symbols['m10v_companion_ui_storage_enter'],0);token=m.u.reg_read(UC_ARM_REG_R0);self.assertNotEqual(token,0)
  m.run(self.symbols['m10v_companion_ui_storage_leave'],token)


class ProductionHdfDivergence(ProductionOwner):
 feature_flags=['-DM10V_COMPANION_EXT_HDF=1','-DM10V_HDF_UI_CACHE=1','-DM10V_HDF_SHARED_RECIPE=1','-DM10V_HDF_OWNER_OFFSET=0x613c']
 native_sources=['native/gr3/m10v_digital_hdf.c']
 def test_hdf_verify_failure_stays_unknown_without_rewrite_or_false_cache_publish(self):
  m=self.machine();owner=0x55860000;m.run(self.symbols['m10v_companion_ui_init'],owner);wire=m.word(owner+0x6400+16)
  cache=owner+0x613c+0x190;m.set(cache,0x101);m.set(cache+4,0x43464448)
  def record(seq,strength):
   b=struct.pack('<5I',0x31464448,1,seq,strength,0);return b+struct.pack('<I',zlib.crc32(b))
  files={b'M10VHD1.BIN':record(1,1)};writes=[];fail=[False]
  m.set(0x558f0008,0x558f0040);m.set(0x558f0040,0x558f0080);m.u.mem_write(0x558f00a0,b'\x01')
  from unicorn.arm_const import UC_ARM_REG_R3
  def fs(u,pc,n,ctx):
   args=[u.reg_read(r) for r in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]]
   if pc==0x53828014:answer=0x558f0000
   elif pc in (0x53825648,0x53825fa8):
    name=bytes(u.mem_read(args[1],12)).split(b'\0')[0]
    if pc==0x53825fa8:files[name]=bytes(u.mem_read(args[3],args[2]));writes.append(name);fail[0]=True;answer=1
    elif fail[0]:fail[0]=False;answer=0
    elif name in files:u.mem_write(args[3],files[name]);answer=1
    else:answer=0
   else:return
   u.reg_write(UC_ARM_REG_R0,answer);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
  m.u.hook_add(UC_HOOK_CODE,fs);m.run(self.symbols['m10v_companion_ui_start'],owner)
  self.exchange(m,wire,2,1,bytes([7]*16));code,read=self.exchange(m,wire,4,5);self.assertEqual(code,0)
  ident=bytes([33]*16);contract=bytes.fromhex('9df047418574e23fd399a0c59491aecc9ea212dbf119a79ff29532aec6493628')
  payload=ident+bytes([7]*16)+contract+read[-32:]+struct.pack('<II',3,3)
  code,result=self.exchange(m,wire,6,6,payload)
  self.assertEqual(struct.unpack_from('<I',result)[0],4);self.assertEqual(len(writes),1)
  self.assertEqual(m.word(cache),0x101);self.assertEqual(struct.unpack_from('<I',files[b'M10VHD0.BIN'],12)[0],3)
  # Same ID and polling must never replay the uncertain write or repair caches.
  self.exchange(m,wire,8,6,payload);code,result=self.exchange(m,wire,10,7,ident)
  self.assertEqual(struct.unpack_from('<I',result)[0],4);self.assertEqual(len(writes),1);self.assertEqual(m.word(cache),0x101)
  m.run(self.symbols['m10v_companion_ui_storage_enter'],0);self.assertEqual(m.u.reg_read(UC_ARM_REG_R0),0)
  # Direct read also fails closed, preserving caller outputs and cache.
  scratch=0x558e0000;m.set(scratch,99);m.set(scratch+4,88)
  m.run(self.symbols['m10v_hdf_remote_snapshot'],scratch,scratch+4);self.assertNotEqual(m.u.reg_read(UC_ARM_REG_R0),0)
  self.assertEqual((m.word(scratch),m.word(scratch+4)),(99,88));self.assertEqual(m.word(cache),0x101);self.assertEqual(len(writes),1)

for _case in list(ProductionOwner.__dict__):
 if _case.startswith("test_"):setattr(ProductionHdfDivergence,_case,None)
