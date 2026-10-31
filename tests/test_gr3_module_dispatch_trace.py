"""Original scheduler topology and installed generic-handler ABI in CPU emulation."""
import hashlib,struct,tempfile,unittest
from unicorn import UC_HOOK_CODE,UC_PROT_READ,UC_PROT_EXEC
from unicorn import arm_const as A
from tests.test_gr3_isp_base import StockISP,ROOT,BASE
from scripts.build_gr3_module_dispatch_trace import build
class ModuleDispatchTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.rom=(ROOT/'builds/gr3-extension-validation/official-rtos.bin').read_bytes()
  with tempfile.TemporaryDirectory() as d:cls.code,cls.manifest=build(d,0x54160000,0x54170000)
 def em(self):
  b=bytearray(self.rom);o=self.manifest['base']-BASE;b.extend(bytes(max(0,o+len(self.code)-len(b))));b[o:o+len(self.code)]=self.code
  for patch in self.manifest['patches']:b[patch['address']-BASE:patch['address']-BASE+4]=bytes.fromhex(patch['replacement_hex'])
  e=StockISP(bytes(b));e.u.mem_map(0x54170000,4096);e.u.mem_write(0x54170000,bytes.fromhex('1eff2fe1'));e.events=[]
  def hook(u,at,size,data):
   if at==0x54170000:e.events.append([u.reg_read(getattr(A,'UC_ARM_REG_R'+str(i))) for i in range(4)]+[struct.unpack('<I',u.mem_read(u.reg_read(A.UC_ARM_REG_SP),4))[0]])
   if at==0x54170000 and getattr(e,'clobber_fp',False):
    for i in range(32):u.reg_write(getattr(A,'UC_ARM_REG_D'+str(i)),0xdeadbeef00000000+i)
    u.reg_write(A.UC_ARM_REG_FPSCR,0x00400000)
  e.u.hook_add(UC_HOOK_CODE,hook);return e
 def topology(self,e,kind):
  r=e.alloc(0x50c0);e.w32(r,0x53d0fc90);e.w32(r+0x4778,0x31545653);meta=r+0x5f0+kind*32;msg=r+0x3b0+kind*24;e.w32(meta+0x14,r);e.w32(msg+0xc,meta);return r,msg
 def test_all24_source_topologies_identify_exact_owner(self):
  for kind in range(24):
   e=self.em();r,msg=self.topology(e,kind);e.call(self.manifest['exports']['m10v_module_trace_mark'],0x60030000,msg,0x535047d4,204,0)
   self.assertEqual(e.events,[[r,204,kind,0x535047d4,0x60030000]])
 def test_foreign_or_inconsistent_packet_is_not_followed_as_owner(self):
  e=self.em();r,msg=self.topology(e,6);e.w32(msg+0xc,r+0x5f0+7*32);e.call(self.manifest['exports']['m10v_module_trace_mark'],0x60030000,msg,0x535047d4,204,0);self.assertEqual(e.events,[])
 def test_locked_rom_and_patch_sites(self):
  self.assertEqual(len(self.manifest['patches']),2)
  self.assertEqual([p['address'] for p in self.manifest['patches']],[0x53505d78,0x53505d7c])
  self.assertEqual(self.manifest['callback_filesystem_calls'],0)
  self.assertFalse(self.manifest['final_recipe_drain_proven'])

 def test_original_scheduler_packet_producer_matches_owner_topology(self):
  for kind in range(24):
   e=self.em();r=e.alloc(0x50c0);owner=e.alloc(0xb00);plan=e.alloc(0x300);e.w32(r,0x53d0fc90);e.w32(r+0x1c,plan);e.u.mem_write(plan+0x204,struct.pack('<H',kind));e.w32(owner+0x9b4+kind*4,0x60030000);seen=[]
   def services(u,at,size,data):
    if at in (0x5351e888,0x5350e624):u.reg_write(A.UC_ARM_REG_R0,0);u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
    elif at==0x536abd28:
     msg=u.reg_read(A.UC_ARM_REG_R1);meta=struct.unpack('<I',u.mem_read(msg+12,4))[0];seen.append((msg,meta,struct.unpack('<I',u.mem_read(meta+20,4))[0]));u.reg_write(A.UC_ARM_REG_R0,0);u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
   e.u.hook_add(UC_HOOK_CODE,services);e.call(0x5351ea9c,owner,r)
   self.assertEqual(seen,[(r+0x3b0+kind*24,r+0x5f0+kind*32,r)])
 def test_installed_site_preserves_handler_sp_args_registers_and_return(self):
  e=self.em();r,msg=self.topology(e,6);module=e.alloc(0x80);handler=0x535047d4;sp=0x5efffd00;fp=sp+0x60;seen=[]
  e.u.mem_write(fp-0x34,struct.pack('<I',0));e.u.mem_write(sp,struct.pack('<3I',0x12345678,0xabcdef01,0x11112222))
  e.clobber_fp=True
  fpregs=[0x1234567800000000+i for i in range(32)]
  for i,v in enumerate(fpregs):e.u.reg_write(getattr(A,'UC_ARM_REG_D'+str(i)),v)
  e.u.reg_write(A.UC_ARM_REG_FPSCR,0x00800000)
  before=[0x10101010+i for i in range(13)];before[0]=module;before[1]=msg;before[7]=msg;before[8]=module;before[9]=handler;before[11]=fp
  for i,v in enumerate(before):e.u.reg_write(getattr(A,'UC_ARM_REG_R'+str(i)),v)
  e.u.reg_write(A.UC_ARM_REG_SP,sp);e.u.reg_write(A.UC_ARM_REG_CPSR,0xa0000013)
  def intercept(u,at,size,data):
   if at==handler:
    seen.append(([u.reg_read(getattr(A,'UC_ARM_REG_R'+str(i))) for i in range(13)],u.reg_read(A.UC_ARM_REG_SP),bytes(u.mem_read(sp,12))))
    u.reg_write(A.UC_ARM_REG_R0,0x76543210);u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
   elif at==0x53505d80:u.emu_stop()
  e.u.hook_add(UC_HOOK_CODE,intercept);e.u.emu_start(0x53505d78,0x53505d80,count=10000)
  self.assertEqual(seen,[(before,sp,struct.pack('<3I',0x12345678,0xabcdef01,0x11112222))]);self.assertEqual(e.u.reg_read(A.UC_ARM_REG_R0),0x76543210);self.assertEqual(e.u.reg_read(A.UC_ARM_REG_SP),sp)
  self.assertEqual(e.events,[[r,204,6,handler,module],[r,205,6,handler,0x76543210]])
  self.assertEqual([e.u.reg_read(getattr(A,'UC_ARM_REG_D'+str(i))) for i in range(32)],fpregs)
  self.assertEqual(e.u.reg_read(A.UC_ARM_REG_FPSCR),0x00800000)

 def test_store_command_is_distinguished_without_filesystem_work(self):
  e=self.em();r,msg=self.topology(e,17);e.w32(msg+4,0x1000001);e.call(self.manifest['exports']['m10v_module_trace_mark'],0x60030000,msg,0x5350c764,204)
  self.assertEqual(e.events,[[r,204,17,0x5350c764,0x60030000],[r,206,17,0x1000001,0x60030000]])
 def test_optional_sink_only_drains_store_and_preserves_original_rejoin(self):
  with tempfile.TemporaryDirectory() as d:code,m=build(d,0x54160000,0x54170000,take=0x54170100,batch=0x54170200)
  b=bytearray(self.rom);off=m['base']-BASE;b.extend(bytes(max(0,off+len(code)-len(b))));b[off:off+len(code)]=code
  for p in m['patches']:b[p['address']-BASE:p['address']-BASE+4]=bytes.fromhex(p['replacement_hex'])
  e=StockISP(bytes(b));e.u.mem_map(0x54170000,4096)
  for a in(0x54170000,0x54170100,0x54170200):e.u.mem_write(a,bytes.fromhex('1eff2fe1'))
  r,msg=self.topology(e,17);meta=r+0x5f0+17*32;e.w32(meta+16,0x60775588);calls=[]
  def hook(u,at,size,data):
   if at==0x53050b7c:
    u.mem_write(u.reg_read(A.UC_ARM_REG_R0),struct.pack('<2I',456,123));u.reg_write(A.UC_ARM_REG_R0,0);u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
   elif at in(0x54170000,0x54170100,0x54170200):
    calls.append((at,[u.reg_read(getattr(A,'UC_ARM_REG_R'+str(i))) for i in range(3)]))
    if at==0x54170100:u.mem_write(u.reg_read(A.UC_ARM_REG_R1),bytes(20));u.reg_write(A.UC_ARM_REG_R0,1)
   elif at==0x53505dc0:u.emu_stop()
  e.u.hook_add(UC_HOOK_CODE,hook)
  for handler,expected in ((0x535047d4,0),(0x5350c764,3)):
   calls.clear();regs=[0x11110000+i for i in range(13)];regs[5]=meta;regs[9]=handler
   for i,v in enumerate(regs):e.u.reg_write(getattr(A,'UC_ARM_REG_R'+str(i)),v)
   e.u.reg_write(A.UC_ARM_REG_SP,0x5efffd00);e.u.reg_write(A.UC_ARM_REG_LR,0x53123400);e.u.reg_write(A.UC_ARM_REG_CPSR,0xb0000013)
   e.u.emu_start(0x53505dbc,0x53505dc0,count=50000)
   self.assertEqual(len(calls),expected);self.assertEqual(e.u.reg_read(A.UC_ARM_REG_R0),0x60775588)
   self.assertEqual([e.u.reg_read(getattr(A,'UC_ARM_REG_R'+str(i))) for i in range(1,13)],regs[1:]);self.assertEqual(e.u.reg_read(A.UC_ARM_REG_SP),0x5efffd00);self.assertEqual(e.u.reg_read(A.UC_ARM_REG_LR),0x53123400);self.assertEqual(e.u.reg_read(A.UC_ARM_REG_CPSR)&0xf0000000,0xb0000000)
  self.assertEqual(len(m['patches']),3);self.assertTrue(m['post_store_drain_attempted']);self.assertFalse(m['final_recipe_drain_proven'])

 def test_original_store_dispatch_selects_main_save_instead_of_old_probe(self):
  for opcode,target in ((0x1000001,0x5350bfb0),(0x1000002,0x5350b2fc)):
   e=self.em();module=e.alloc(0x9000);r,msg=self.topology(e,17);context=e.alloc(0x100);e.w32(msg+4,opcode);e.w32(msg+8,context);e.w32(msg+16,r+0xbd0);e.w32(msg+20,r+0x8f0);seen=[]
   def hook(u,at,size,data):
    if at in(0x5350bfb0,0x5350b2fc):seen.append((at,u.reg_read(A.UC_ARM_REG_R0),u.reg_read(A.UC_ARM_REG_R1)));u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
   e.u.hook_add(UC_HOOK_CODE,hook);e.call(0x5350c764,module,msg)
   self.assertEqual(seen,[(target,module,context)])

 def test_pure_effects_drain_before_spatial_worker_without_waiting_for_jpeg(self):
  with tempfile.TemporaryDirectory() as d:code,m=build(d,0x54160000,0x54170000,take=0x54170100,batch=0x54170200,pure_isp_debug=True)
  b=bytearray(self.rom);off=m['base']-BASE;b.extend(bytes(max(0,off+len(code)-len(b))));b[off:off+len(code)]=code
  e=StockISP(bytes(b));e.u.mem_map(0x54170000,4096)
  r=e.alloc(0x57d8);e.w32(r,0x53d0fc90);e.w32(r+0x4778,0x31545653)
  shot=r+0x5778
  for off,v in ((0,0x31584653),(4,r),(8,1),(16,1)):e.w32(shot+off,v)
  req=e.alloc(0x40);e.w32(r+0x5c,req);e.u.mem_write(req+0x24,b'\1')
  e.u.mem_write(r+0x4368,b'\1\0');meta=r+0x5f0+10*32;e.w32(meta+20,r)
  batches=[]
  def hook(u,at,size,data):
   if at==0x53050b7c:result=0
   elif at==0x54170000:result=1
   elif at==0x54170100:result=0
   elif at==0x54170200:
    p,n=u.reg_read(A.UC_ARM_REG_R0),u.reg_read(A.UC_ARM_REG_R1)
    batches.extend(struct.unpack('<5I',u.mem_read(p+i*20,20)) for i in range(n));result=1
   else:return
   u.reg_write(A.UC_ARM_REG_R0,result);u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
  e.u.hook_add(UC_HOOK_CODE,hook)
  e.call(m['exports']['m10v_module_trace_finish'],meta,0x53508638)
  self.assertEqual(batches,[(198,r,0x46584d00,10,0x101)])
  batches.clear();e.w32(shot+16,0)
  e.call(m['exports']['m10v_module_trace_finish'],meta,0x53508638)
  self.assertEqual(batches,[])
