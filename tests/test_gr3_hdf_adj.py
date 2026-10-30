"""Independent ADJ ID20: exact-stock relocation and genuine-controller probes."""
import struct,unittest
from scripts.build_gr3_digital_hdf import official_rtos

class HdfAdjLayoutTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rom=official_rtos()
 def build(self):
  from scripts.build_gr3_hdf_adj import build
  names=('enter','draw','current','set','count','available','event','live_enter')
  return build(0x54180000,{'m10v_hdf_adj_'+n:0x54170000+16*i for i,n in enumerate(names)},self.rom,icon_id=855)
 def test_adds_twenty_first_record_without_replacing_flash_or_gf2(self):
  code,m=self.build();self.assertEqual(m['function_id'],20);self.assertEqual(m['record_count'],21)
  at=m['table']-m['base'];self.assertEqual(code[at:at+20*0x44],self.rom[0xb39a14:0xb39f64])
 def test_every_assignment_list_preserves_original_order_and_appends_independent_option(self):
  code,m=self.build()
  for row in m['lists']:
   start=row['address']-m['base'];self.assertEqual(code[start:start+19],self.rom[row['original']-0x53000000:row['original']-0x53000000+19]);self.assertEqual(code[start+19],20)
  self.assertEqual(len(m['lists']),5)
 def test_every_original_table_reader_and_constructor_length_is_patched(self):
  code,m=self.build();self.assertEqual(len(m['table_readers']),19)
  addresses={p['address'] for p in m['patches']};self.assertIn(0x531a1e54,addresses)
  self.assertTrue(all(a in addresses and z in addresses for a,z in m['table_readers']))
 def test_rejects_changed_official_input(self):
  from scripts.build_gr3_hdf_adj import build
  b=bytearray(self.rom);b[0x19fff8]^=1
  with self.assertRaisesRegex(ValueError,'exact'):build(0x54180000,{},bytes(b),icon_id=855)

class HdfAdjArmTests(unittest.TestCase):
 """Run real official getters/lists/controller dispatch against relocated table.
 Hardware/widget/filesystem services are the only substituted boundaries.
 """
 @classmethod
 def setUpClass(cls):
  import tempfile,subprocess,shutil
  from pathlib import Path
  from scripts.build_gr3_m10v_library import FLAGS,link_object
  from scripts.build_gr3_hdf_adj import build
  cls.rom=official_rtos();cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
  cls.images=[];cls.symbols={};base=0x54140000
  cls.parents={'m10v_hdf_adj_parent_event':0x550e1000}
  for filename,prefix,ext in [('m10v_digital_hdf.c','m10v_hdf_',{}),('m10v_hdf_adj.c','m10v_hdf_adj_',cls.parents)]:
   out=Path(cls.tmp.name)/filename.replace('.c','.o')
   subprocess.run([shutil.which('clang'),*FLAGS,'-DM10V_HDF_UI_CACHE=1','-DM10V_HDF_OWNER_OFFSET=0x13bc','-c','native/gr3/'+filename,'-o',str(out)],check=True,capture_output=True)
   code,entries=link_object(out.read_bytes(),base,{**cls.symbols,**ext},prefix)
   cls.images.append((base,code));cls.symbols.update(entries);base=(base+len(code)+15)&~15
  code,cls.manifest=build(base,cls.symbols,cls.rom);cls.images.append((base,code))
  out=Path(cls.tmp.name)/'shared-hdf.o'
  subprocess.run([shutil.which('clang'),*FLAGS,'-DM10V_HDF_UI_CACHE=1','-DM10V_HDF_OWNER_OFFSET=0x13bc','-DM10V_HDF_SHARED_RECIPE=1','-c','native/gr3/m10v_digital_hdf.c','-o',str(out)],check=True,capture_output=True)
  code,cls.shared_symbols=link_object(out.read_bytes(),0x54160000,{},'m10v_hdf_',omitted_exports=('m10v_hdf_alloc',))
  cls.images.append((0x54160000,code))
 def setUp(self):
  from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
  from unicorn import arm_const as A
  self.A=A;self.u=u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0x53000000,0x1500000);u.mem_write(0x53000000,self.rom);u.mem_map(0x55000000,0x100000)
  for at,code in self.images:u.mem_write(at,code)
  for p in self.manifest['patches']:self.put(p['address'],p['replacement'])
  self.owner=0x55010000;self.cache=self.owner+0x13bc+0x190;self.c=0x55020000;self.model=0x55030000;self.settings=0x55040000
  self.put(0x55063910,1);self.put(0x55063988,self.owner);self.put(self.cache+4,0x43464448)
  for index in range(1,9):self.put(self.model+index*4,self.settings)
  self.put(0x55002008,0x55002100);self.put(0x55002100,0x55002200);u.mem_write(0x55002220,b'\x01')
  self.files={};self.reads=[];self.writes=[];self.fail_write=False;self.fail_verify=False;self.cursor=0;self.parent_keys=[];self.captions=[];self.genuine_parent=False;self.queued=[];self.destroyed=[];self.icons=[];self.visibility=[]
  from scripts.build_gr3_menu_patches import assembly
  u.mem_write(0x550e1000,assembly('ldrh r3,[r1];b 0x531a4dbc',0x550e1000))
  self.put(self.c+0x1f0,0x55050000);self.put(self.c+0x160,0x55050100)
  def service(uc,a,n,d):
   r=[uc.reg_read(getattr(A,'UC_ARM_REG_R'+str(i))) for i in range(4)];result=0
   if a in (0x5320ad88,0x5320b31c,0x5320b73c,0x5320aefc):result=self.model
   elif a==0x5320ba9c:result=0x550c0000
   elif a==0x532b0f08:uc.mem_write(r[0],struct.pack('<II',0x55090000,0x55090008))
   elif a==0x536af31c:result=0x550a0000
   elif a==0x53525d5c:self.put(0x550b0000,self.model);result=0x550b0000
   elif a==0x535493ac:result=2
   elif a==0x532288b0:self.queued.append(r[1])
   elif a in (0x536af2e4,0x536af358,0x53394610,0x533958a8,0x533958b4,0x5316c774):pass
   elif a==0x5316cde8:self.destroyed.append((r[0],r[1],r[2]))
   elif a==0x53828014:result=0x55002000
   elif a in (0x53825648,0x53825fa8):
    name=bytes(uc.mem_read(r[1],12)).split(b'\0')[0].decode()
    if a==0x53825648:
     self.reads.append(name)
     if self.fail_verify and self.writes:self.fail_verify=False
     elif name in self.files:uc.mem_write(r[3],self.files[name]);result=1
    elif not self.fail_write:self.files[name]=bytes(uc.mem_read(r[3],24));self.writes.append(name);result=1
   elif a==0x53394820:result=self.cursor
   elif a==0x53394758:result=0x55050200+r[1]*8
   elif a in (0x53396f80,0x533a1808):self.captions.append(r[:3])
   elif a==0x5339a9a0:self.icons.append((r[0],r[1]))
   elif a==0x533ad3c0:self.visibility.append((r[0],r[1]))
   elif a==0x53393e00:pass
   elif a==0x550e1000 and self.genuine_parent:return
   elif a==0x550e1000:self.parent_keys.append(int.from_bytes(uc.mem_read(r[1],2),'little'));result=77
   else:return
   uc.reg_write(A.UC_ARM_REG_R0,result);uc.reg_write(A.UC_ARM_REG_PC,uc.reg_read(A.UC_ARM_REG_LR))
  u.hook_add(UC_HOOK_CODE,service)
 def put(self,a,v):self.u.mem_write(a,struct.pack('<I',v))
 def get(self,a):return int.from_bytes(self.u.mem_read(a,4),'little')
 def call(self,fn,*args):
  A=self.A;u=self.u
  for i in range(13):u.reg_write(getattr(A,'UC_ARM_REG_R'+str(i)),args[i] if i<len(args) else 0)
  u.reg_write(A.UC_ARM_REG_SP,0x550ff000);u.reg_write(A.UC_ARM_REG_LR,0x550ff800)
  u.emu_start(self.symbols.get(fn,fn) if isinstance(fn,str) else fn,0x550ff800,count=300000)
  self.assertEqual(u.reg_read(A.UC_ARM_REG_PC),0x550ff800);self.assertEqual(u.reg_read(A.UC_ARM_REG_SP),0x550ff000)
  n=u.reg_read(A.UC_ARM_REG_R0);return n if n<0x80000000 else n-0x100000000
 def assign(self,slot,function):self.u.mem_write(self.settings+0x918+slot*2,bytes([function]))
 def key(self,k):self.u.mem_write(0x55006000,struct.pack('<H',k));return self.call('m10v_hdf_adj_event',self.c,0x55006000)
 def render_slot_icons(self):
  # Execute the real renderer through its five-slot loop, stopping before the
  # unrelated header and list refresh. No table dispatch or predicate is stubbed.
  for slot in range(5):
   self.put(self.c+0x184+4*slot,0x55051000+slot*0x100)
   self.put(self.c+0x16c+4*slot,0x55052000+slot*0x100)
  A=self.A;self.u.reg_write(A.UC_ARM_REG_R0,self.c)
  self.u.reg_write(A.UC_ARM_REG_SP,0x550ff000);self.u.reg_write(A.UC_ARM_REG_LR,0x550ff800)
  self.u.emu_start(0x531a4168,0x531a4314,count=100000)
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x531a4314)
 def test_original_five_slot_renderer_shows_assigned_hdf_with_cold_or_warm_cache(self):
  for marker in (0,0x100,0x103):
   self.put(self.cache,marker)
   for slot in range(5):
    for other in range(5):self.assign(other,20 if other==slot else 0)
    self.icons.clear();self.visibility.clear();reads=len(self.reads)
    self.render_slot_icons()
    self.assertEqual(self.icons,[(0x55051000+i*0x100,874 if i==slot else 0) for i in range(5)])
    self.assertEqual(self.visibility,[(0x55052000+i*0x100,int(i==slot)) for i in range(5)])
    self.assertEqual(len(self.reads),reads);self.assertEqual(self.writes,[])
 def test_original_initial_slot_selection_accepts_hdf_in_each_of_five_slots(self):
  for slot in range(5):
   for other in range(5):self.assign(other,20 if other==slot else 0)
   self.u.mem_write(self.settings+0x914,bytes([(slot+4)%5]));reads=len(self.reads)
   self.call(0x531a2a7c,self.c)
   self.assertEqual(self.u.mem_read(self.c+0x1f4,1),bytes([slot]))
   self.assertEqual(len(self.reads),reads);self.assertEqual(self.writes,[])
 def test_original_renderer_hides_hdf_when_owner_is_unavailable(self):
  self.put(0x55063988,0)
  for slot in range(5):self.assign(slot,20)
  self.render_slot_icons()
  self.assertEqual(self.icons,[(0x55051000+i*0x100,0) for i in range(5)])
  self.assertEqual(self.visibility,[(0x55052000+i*0x100,0) for i in range(5)])
 def test_original_entry_selects_hdf_and_bootstraps_cold_cache_before_drawing(self):
  for slot in range(5):
   for other in range(5):self.assign(other,20 if other==slot else 0)
   self.put(self.cache,0);self.u.mem_write(self.settings+0x914,bytes([(slot+4)%5]))
   A=self.A;self.u.reg_write(A.UC_ARM_REG_R0,self.c)
   self.u.reg_write(A.UC_ARM_REG_SP,0x550ff000);self.u.reg_write(A.UC_ARM_REG_LR,0x550ff800)
   # Includes stock mode/assignment reads, exclusion dispatch and ID20 enter.
   self.u.emu_start(0x531a4554,0x531a45bc,count=100000)
   self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x531a45bc)
   self.assertEqual(self.u.mem_read(self.c+0x1f4,1),bytes([slot]))
   self.assertEqual(self.get(self.cache),0x100)
   self.assertEqual(self.get(self.cache+8),self.c)
   self.assertEqual(self.get(self.cache+12),0);self.assertEqual(self.writes,[])
 def test_all_five_genuine_assignment_setters_getters_and_list_counts(self):
  for slot in range(5):
   for index,fn in enumerate((*range(5),16,5,6,7,8,9,18,19,10,11,12,13,17,14,20)):
    self.call(0x531b71b4+slot*0x30,self.c,index)
    self.assertEqual(self.call(0x5324633c+slot*12,self.model),fn)
    self.assertEqual(self.u.mem_read(self.settings+0x918+slot*2,1),bytes([fn]))
   self.assertEqual(self.call(0x531b3bac+slot*8),20)
   self.assign(slot,255);self.assertEqual(self.call(0x5324633c+slot*12,self.model),0)
   self.assertEqual(self.u.mem_read(self.settings+0x918+slot*2,1),b'\xff')
 def test_real_count_dispatch_first_last_new_and_every_original_callback_target(self):
  from unicorn import UC_HOOK_CODE
  for fn in range(21):
   self.assign(0,fn)
   if fn==0:self.assertEqual(self.call(0x531a31ac,self.c),0);continue
   target=(self.symbols['m10v_hdf_adj_count'] if fn==20 else struct.unpack_from('<I',self.rom,0xb39a14+fn*0x44+0x30)[0]);seen=[]
   def target_probe(uc,a,n,d):
    if a==target:seen.append(a);uc.emu_stop()
   h=self.u.hook_add(UC_HOOK_CODE,target_probe)
   A=self.A;self.u.reg_write(A.UC_ARM_REG_R0,self.c);self.u.reg_write(A.UC_ARM_REG_SP,0x550ff000);self.u.reg_write(A.UC_ARM_REG_LR,0x550ff800)
   self.u.emu_start(0x531a31ac,0x550ff800,count=10000);self.u.hook_del(h);self.assertEqual(seen,[target],fn)
  for fn,expected in ((0,0),(19,2),(20,4)):
   self.assign(0,fn);self.assertEqual(self.call(0x531a31ac,self.c),expected)
 def test_genuine_current_and_set_controller_route_without_filesystem_per_item(self):
  self.assign(0,20);self.call('m10v_hdf_bootstrap');reads=len(self.reads)
  self.call('m10v_hdf_adj_enter',self.c)
  for level in range(4):
   self.cursor=level;self.call(0x531a3100,self.c)
   for i in range(32):
    self.assertEqual(self.call(0x531a3d94,self.c,i),int(i==level))
    self.call('m10v_hdf_adj_draw',self.c,i)
  self.assertEqual(len(self.reads),reads);self.assertEqual(self.writes,[])
 def test_browse_cancel_and_capture_power_keys_never_commit(self):
  self.assign(0,20);self.call('m10v_hdf_bootstrap');self.call('m10v_hdf_adj_enter',self.c);reads=len(self.reads)
  for key in (0x35,1,0x89,0xaa):
   self.call('m10v_hdf_adj_enter',self.c);self.call('m10v_hdf_adj_set',self.c,3)
   self.assertEqual(self.key(key),77)
  self.assertEqual(self.writes,[]);self.assertEqual(len(self.reads),reads);self.assertEqual(self.get(self.cache),0x100)
 def test_confirm_updates_same_journal_and_cache_as_menu_load_save(self):
  self.assign(0,20);self.call('m10v_hdf_adj_enter',self.c);self.cursor=2
  self.assertEqual(self.key(0xd8),77);self.assertEqual(self.writes,['M10VHD1.BIN']);self.assertEqual(self.get(self.cache),0x102)
  self.assertEqual(self.call('m10v_hdf_load',0x55007000),0);self.assertEqual(self.get(0x55007000),2)
  self.assertEqual(self.call('m10v_hdf_save',3),0);self.call('m10v_hdf_adj_enter',self.c)
  self.assertEqual(self.call(0x531a3d94,self.c,3),1)
 def test_save_failure_stays_open_with_error_and_readback_reconciles_partial_success(self):
  self.assign(0,20);self.call('m10v_hdf_adj_enter',self.c);self.cursor=3;self.fail_write=True
  self.assertEqual(self.key(0xd8),1);self.assertEqual(self.parent_keys,[]);self.assertEqual(self.get(self.cache),0x100);self.assertEqual(self.captions[-1][1],976)
  self.fail_write=False;self.fail_verify=True;self.assertEqual(self.key(0xd8),1)
  self.assertEqual(self.get(self.cache),0x103);self.assertEqual(self.get(self.cache+12),3)
 def test_cold_busy_invalid_or_destroyed_cache_never_reads_storage(self):
  for marker in (0,0x80000102,0xffffffff):
   self.put(self.cache,marker);before=len(self.reads)
   self.assertEqual(self.call('m10v_hdf_cached',0x55007000),-1);self.assertEqual(len(self.reads),before)
  self.put(self.cache,0x103);self.put(self.cache+4,0);self.assertEqual(self.call('m10v_hdf_cached',0x55007000),-1)
 def test_actual_native_u_recall_copy_preserves_all_original_and_added_slot_bytes(self):
  source=0x55060000;dest=0x55070000
  for ids in ((0,1,9,19,20),(20,20,20,20,20),(255,0,1,18,19)):
   for i,v in enumerate(ids):self.u.mem_write(source+0x918+2*i,bytes([v]))
   self.u.reg_write(self.A.UC_ARM_REG_R0,source);self.u.reg_write(self.A.UC_ARM_REG_R2,dest)
   self.u.emu_start(0x53270ba4,0x53270bec,count=100)
   self.assertEqual(tuple(self.u.mem_read(dest+0x918+2*i,1)[0] for i in range(5)),ids)
 def test_name_and_icon_preserve_all_twenty_stock_functions(self):
  for fn in range(21):
   self.assertEqual(self.call(0x53292810,0,fn),970 if fn==20 else self.stock_lookup(0x53292810,fn))
   self.assertEqual(self.call(0x53293a30,0,fn),874 if fn==20 else self.stock_lookup(0x53293a30,fn))
 def stock_lookup(self,a,fn):
  p=next(p for p in self.manifest['patches'] if p['address']==(0x532928b0 if a==0x53292810 else 0x53293ad0))
  self.put(p['address'],p['expected'])
  try:return self.call(a,0,fn)
  finally:self.put(p['address'],p['replacement'])

 def test_actual_constructor_walks_all21_counts_and_stock_destructor_remains_owned(self):
  from unicorn import UC_HOOK_CODE
  counts=[];targets={struct.unpack_from('<I',self.rom,0xb39a14+fn*0x44+0x30)[0] for fn in range(1,20)}|{self.symbols['m10v_hdf_adj_count']}
  def observe(uc,a,n,d):
   if a in targets:counts.append(a)
  h=self.u.hook_add(UC_HOOK_CODE,observe);self.call(0x531a1e34,self.c);self.u.hook_del(h)
  self.assertEqual(len(counts),20);self.assertIn(self.symbols['m10v_hdf_adj_count'],counts)
  self.assertEqual(self.u.mem_read(self.c+0x271,1),b'\x20')
  self.assertEqual(bytes(self.u.mem_read(0x550a0000,32)),bytes([0x19])*32)
  self.assertEqual(self.call(0x5319ff24,self.c),self.c)
  self.assertEqual(self.destroyed,[(self.c,self.c+0x15c,0x25)])
 def test_genuine_native_ok_and_halfpress_event_routes_preserve_exit_services(self):
  self.genuine_parent=True;self.assign(0,20);self.call('m10v_hdf_adj_enter',self.c)
  self.cursor=1;self.assertEqual(self.key(0xd8),0);self.assertEqual(self.queued,[0x86]);self.assertEqual(self.get(self.cache),0x101)
  reads=len(self.reads);writes=len(self.writes)
  self.call('m10v_hdf_adj_enter',self.c);self.call('m10v_hdf_adj_set',self.c,3)
  self.assertEqual(self.key(0x35),0);self.assertEqual(self.queued,[0x86,0xb8])
  self.assertEqual((len(self.reads),len(self.writes)),(reads,writes));self.assertEqual(self.get(self.cache),0x101)
 def test_native_hdf_producer_only_reads_published_cache_and_freezes_each_recipe(self):
  recipe=0x55080000;self.put(recipe,0x53d0fc90);self.put(recipe+0x4778,0x31464448)
  self.call('m10v_hdf_producer',recipe);self.assertEqual(self.get(recipe+0x477c),128);self.assertEqual(self.reads,[])
  self.call('m10v_hdf_bootstrap');self.call('m10v_hdf_save',2);reads=len(self.reads)
  self.call('m10v_hdf_producer',recipe);self.assertEqual(self.get(recipe+0x477c),1);self.assertEqual(self.get(recipe+0x4780),2);self.assertEqual(len(self.reads),reads)
  self.call('m10v_hdf_save',3);reads=len(self.reads)
  self.assertEqual(self.get(recipe+0x4780),2)
  self.call('m10v_hdf_producer',recipe);self.assertEqual(self.get(recipe+0x4780),3);self.assertEqual(len(self.reads),reads)

 def test_shared_recipe_hdf5134_preserves_raw_color_and_new_stamp_tail(self):
  recipe=0x55080000;self.put(recipe,0x53d0fc90);self.put(recipe+0x4778,0x3254534d)
  # Shared owner check uses current trace magic and explicit raw token owner.
  from pathlib import Path
  import re
  text=Path('native/gr3/m10v_save_trace.h').read_text()
  magic=int(re.search(r'#define M10V_SAVE_TRACE_MAGIC (0x[0-9a-fA-F]+)',text)[1],16)
  self.put(recipe+0x4778,magic);self.put(recipe+0x5110,0x31574c52);self.put(recipe+0x5114,recipe)
  self.u.mem_write(recipe+0x5140,bytes([0xa5])*16)
  before=bytes(self.u.mem_read(recipe+0x4a08,0x72c))
  self.call('m10v_hdf_bootstrap');self.call('m10v_hdf_save',3);reads=len(self.reads)
  self.call(self.shared_symbols['m10v_hdf_producer'],recipe)
  self.assertEqual(tuple(struct.unpack('<3I',self.u.mem_read(recipe+0x5134,12))),(1,3,0))
  self.assertEqual(bytes(self.u.mem_read(recipe+0x4a08,0x72c)),before)
  self.assertEqual(bytes(self.u.mem_read(recipe+0x5140,16)),bytes([0xa5])*16)
  self.assertEqual(len(self.reads),reads)

 def test_native_settings_default_merge_uses_existing_flags_without_clamping_id20(self):
  source=0x55060000;dest=0x55070000
  for i,value in enumerate((20,19,9,1,0)):
   self.u.mem_write(source+0x918+i*2,bytes([value]));self.u.mem_write(dest+0x918+i*2,bytes([7,1]))
  self.u.reg_write(self.A.UC_ARM_REG_R4,dest);self.u.reg_write(self.A.UC_ARM_REG_R5,source)
  self.u.emu_start(0x5324a310,0x5324a360,count=100)
  self.assertEqual(tuple(self.u.mem_read(dest+0x918+2*i,1)[0] for i in range(5)),(20,19,9,1,0))
