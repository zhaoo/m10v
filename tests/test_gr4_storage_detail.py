"""GR IV storage ABI and native detail controls, executed as ARM code.
Filesystem services are controlled substitutes; this is not a camera test.
"""
import hashlib,json,os,struct,subprocess,tempfile,unittest,zlib
from pathlib import Path
from scripts.build_gr3_m10v_library import build,link_object,FLAGS
from scripts.build_gr4_native_detail import build_detail,RTOS_SHA256
ROOT=Path(__file__).resolve().parents[1]

class Gr4StorageDetailTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
  cls.folder=Path(cls.tmp.name);cls.shared=build(cls.folder)
  cls.images=[(cls.shared['base'],(cls.folder/'m10v-library-arm.bin').read_bytes())]
  cls.symbols=dict(cls.shared['symbols'])
  def compile_one(name,base,prefix,externals):
   obj=cls.folder/(Path(name).name+'.o')
   subprocess.run([os.environ.get('M10V_LLVM_CLANG','clang'),*FLAGS,'-I',str(ROOT/'native/gr3'),'-c',str(ROOT/'native/gr4'/name),'-o',str(obj)],check=True)
   # Same explicit unsupported API inventory as the production GR IV builder.
   camera_omitted=('custom_profile','preview','preview_init','preview_clear','mutation_begin','mutation_end','mutation_busy','remove','shooting_count','menu_index','reconcile_legacy_selection','select_custom','film_name_stamp')
   sd_omitted=('custom_record','custom_name','catalog_name','directory_item','directory_install','directory_extent')
   raw,symbols=link_object(obj.read_bytes(),base,externals,prefix,omitted_exports=tuple('m10v_camera_library_'+n for n in camera_omitted) if prefix=='m10v_camera_library_' else tuple('m10v_sd_camera_'+n for n in sd_omitted) if prefix=='m10v_sd_camera_' else ())
   cls.images.append((base,raw));cls.symbols.update(symbols);return symbols
  compile_one('../gr3/m10v_sd_library.c',0x54470000,'m10v_sd_',cls.symbols)
  compile_one('m10v_library_camera.c',0x54480000,'m10v_camera_library_',cls.symbols)
  compile_one('m10v_sd_camera.c',0x54490000,'m10v_sd_camera_',cls.symbols)
  blob,detail=build_detail(0x544b0000,{'m10v_detail_table':0x544a0000,'m10v_detail_control':0x544a0100})
  ext=dict(cls.symbols)
  ext.update(m10v_detail_tables=detail['variant_tables']['halo'],m10v_detail_common_tables=detail['variant_tables']['common'],m10v_detail_red_tables=detail['variant_tables']['red'],m10v_detail_phoenix_tables=detail['variant_tables']['phoenix'])
  compile_one('m10v_detail.c',0x544a0000,'m10v_detail_',ext)
  cls.blob,cls.detail=build_detail(0x544b0000,cls.symbols)
  cls.images.append((0x544b0000,cls.blob))
  cls.pack=subprocess.check_output(['node','--input-type=module','-e',"import {buildSdFilmPack} from './node/gr3-sd-film-pack.mjs';process.stdout.write(buildSdFilmPack());"],cwd=ROOT)
 def setUp(self):
  from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
  self.u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
  self.u.mem_map(0x53000000,0x1500000);self.u.mem_map(0x55000000,0x100000)
  self.u.mem_write(0x53000000,(ROOT/'data/research/gr4/RTOS.bin').read_bytes())
  for a,raw in self.images:self.u.mem_write(a,raw)
  for p in self.detail['patches']:self.u.mem_write(p['address'],bytes.fromhex(p['replacement']))
  self.files={};self.card=self.pack;self.position=0;self.short=False;self.fail_save=False;self.bad_load=False;self.opened=0;self.allocations=0;self.calls=[];self.fail_allocate=False
  self.w(0x55001014,0x55002000);self.w(0x55002000,0x53900000)
  for i in [7,8,9,11,12,13]:self.w(0x53900000+4*i,0x53900100+i*16)
  self.w(0x55003008,0x55004000);self.w(0x55004004,0x55005000);self.w(0x5500502c,0x55006000);self.u.mem_write(0x5500504c,b'\1')
  self.u.hook_add(UC_HOOK_CODE,self.hook)
 def w(self,a,v):self.u.mem_write(a,struct.pack('<I',v&0xffffffff))
 def n(self,a):return struct.unpack('<I',self.u.mem_read(a,4))[0]
 def string(self,a):return bytes(self.u.mem_read(a,64)).split(b'\0')[0].decode()
 def hook(self,u,pc,size,data):
  from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC
  a=[u.reg_read(r) for r in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]];extra=self.n(u.reg_read(UC_ARM_REG_SP));ret=None
  if pc==0x53798938:ret=0x55001000
  elif pc==0x538e09b0:
   ret=0 if self.fail_allocate else 0x55020000
   if ret:self.allocations+=1
  elif pc==0x538e09ec:self.allocations-=1;ret=0
  elif pc==0x53900170:
   self.assertEqual(self.string(a[1]),'C:\\M10V\\FILMS.M10');self.position=0;self.opened+=1;self.w(a[3],0x55009000);self.w(extra,0);ret=1
  elif pc==0x53900180:self.opened-=1;self.w(a[2],0);ret=1
  elif pc==0x53900190:
   length=min(a[3],len(self.card)-self.position);length=max(0,length-int(self.short));u.mem_write(a[2],self.card[self.position:self.position+length]);self.position+=length;self.w(extra,0);ret=1
  elif pc==0x539001b0:self.position=a[2];self.w(extra,0);ret=1
  elif pc==0x539001c0:self.w(a[2],len(self.card));self.w(a[3],0);ret=1
  elif pc==0x539001d0:self.w(a[2],self.position);self.w(a[3],0);ret=1
  elif pc==0x53a81480:ret=0x55003000
  elif pc==0x53a7fb1c:
   name=self.string(a[1]);self.calls.append(('save',name));ret=int(not self.fail_save)
   if ret:self.files[name]=bytes(u.mem_read(a[3],a[2]))
  elif pc==0x5383b154:
   self.assertEqual(a[0],0x55006000);value=self.files.get(self.string(a[1]).split('\\')[-1]);ret=len(value)+8 if value else 0
  elif pc==0x5383b288:
   self.assertEqual(a[0],0x55006000);value=self.files.get(self.string(a[1]).split('\\')[-1]);raw=struct.pack('<II',0xa55a5aa5,0)+(value or b'')
   if self.bad_load:raw=raw[:-1]
   u.mem_write(0x55040000,raw);self.w(a[2],0x55040000 if value else 0);self.w(a[3],len(raw));ret=0
  elif pc==0x53a7ee80:self.w(a[3],a[1]-8);self.w(extra,a[2]+8);ret=1
  elif pc==0x53838afc:ret=1
  elif pc==0x5357b7d4:self.calls.append(('range',a[1],a[2],a[3]));ret=0
  elif pc==0x5357b830:self.calls.append(('default',a[1]));ret=0
  elif pc in [0x5323ea84,0x5323f928,0x5357b850,0x5357b968,0x535885a4,0x531c69b4]:ret=0
  elif pc==0x5357b44c:self.calls.append(('slider_restore',a[1]));ret=0
  elif pc==0x5357338c:self.calls.append(('caption',a[1]));ret=0
  if ret is not None:u.reg_write(UC_ARM_REG_R0,ret&0xffffffff);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
 def call(self,name,*args):
  from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_LR,UC_ARM_REG_PC,UC_ARM_REG_SP
  u=self.u;sp=0x550fe000;u.reg_write(UC_ARM_REG_SP,sp)
  for r,v in zip([UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3],args):u.reg_write(r,v)
  for i,v in enumerate(args[4:]):self.w(sp+4*i,v)
  u.reg_write(UC_ARM_REG_LR,0x550ff000);u.emu_start(self.symbols.get(name,name),0x550ff000,count=10000000)
  self.assertEqual(u.reg_read(UC_ARM_REG_PC),0x550ff000);self.assertEqual(u.reg_read(UC_ARM_REG_SP),sp);return u.reg_read(UC_ARM_REG_R0)
 def test_sd_pages_exact_read_and_handle_cleanup(self):
  for page,row,want in [(0,0,33),(0,3,68),(4,7,57),(5,7,65),(6,0,0),(32,0,0)]:self.assertEqual(self.call('m10v_sd_camera_item',page,row),want)
  self.short=True;self.assertEqual(self.call('m10v_sd_camera_item',0,0),0)
  self.assertEqual((self.opened,self.allocations),(0,0))
 def test_imported_marlboro_journal_is_compacted_in_memory_without_writing_storage(self):
  from tests.test_gr3_four_looks_native import state_bytes
  saved=bytes(state_bytes([34,327,66]))
  self.files['M10V6A.bin']=saved;self.files['M10V6B.bin']=saved
  self.assertEqual(self.call('m10v_camera_library_load',0x5500a000),0)
  actual=bytes(self.u.mem_read(0x5500a000,184))
  self.assertEqual([struct.unpack_from('<H',actual,12+i*8)[0] for i in range(10)],[34,66]+[0]*8)
  self.assertEqual(actual[12:20],saved[12:20]);self.assertEqual(actual[20:28],saved[28:36])
  self.assertEqual(actual[96:104],saved[96:104]);self.assertEqual(actual[104:112],saved[112:120])
  self.assertEqual(zlib.crc32(actual[:180]),struct.unpack_from('<I',actual,180)[0])
  self.assertEqual(self.call('m10v_camera_library_select',0x5500a000,0,327),0xffffffff)
  self.assertFalse(any(c[0]=='save' for c in self.calls));self.assertEqual(self.files['M10V6A.bin'],saved)
 def test_complete_sd_snapshot_before_journal_and_without_card(self):
  self.assertEqual(self.call('m10v_sd_camera_install',0,3,68,2),0)
  self.assertEqual(self.calls[0],('save','M10VS68.bin'))
  self.assertEqual(self.files['M10VS68.bin'],self.pack[4096+3*12288:4096+4*12288])
  self.card=b'';self.assertEqual(self.call('m10v_camera_library_load',0x5500a000),0)
  self.assertEqual(struct.unpack('<H',self.u.mem_read(0x5500a000+28,2))[0],68)
  self.assertEqual((self.opened,self.allocations),(0,0))
 def test_bad_snapshot_or_failed_write_never_commits_slot(self):
  for attribute in ['bad_load','fail_save']:
   setattr(self,attribute,True);self.assertNotEqual(self.call('m10v_sd_camera_install',0,3,68,2),0);setattr(self,attribute,False)
  self.assertFalse(any(name.startswith('M10V5') for name in self.files))
 def prepare_detail(self):
  ui=0x5500b000;self.u.mem_write(ui+0x19c,bytes([36,0,0,0,0,0]));self.w(ui+0x168,0x5500c000);self.w(ui+0x164,0x5500d000)
  self.assertEqual(self.call('m10v_camera_library_load',0x5500a000),1)
  self.assertEqual(self.call('m10v_camera_library_select',0x5500a000,0,33),0)
  return ui
 def test_detail_journals_halation_and_restores_failed_slider(self):
  ui=self.prepare_detail()
  for field,value in [(0,2),(1,3),(2,5)]:
   self.assertEqual(self.call('m10v_detail_control',2,ui,(field<<8)|value),1)
   self.assertEqual(self.call('m10v_detail_control',1,ui,field),value)
  before=dict(self.files)
  for field in range(3,10):
   self.assertEqual(self.call('m10v_detail_control',2,ui,(field<<8)|1),0)
  self.assertEqual(self.files,before)
  self.fail_save=True;self.assertEqual(self.call('m10v_detail_control',2,ui,1),0)
  self.assertIn(('slider_restore',2),self.calls)
  self.assertEqual(self.call('m10v_detail_control',1,ui,0),2)
 def test_halation_edit_clears_legacy_grain_without_changing_other_slots(self):
  ui=self.prepare_detail();self.call('m10v_camera_library_load',0x5500a000)
  old=bytearray(self.u.mem_read(0x5500a000,104));old[14]=3
  struct.pack_into('<I',old,8,100);struct.pack_into('<I',old,100,zlib.crc32(old[:100]))
  self.files['M10V5A.bin']=bytes(old)
  self.assertEqual(self.call('m10v_detail_control',2,ui,6),1)
  self.assertEqual(self.call('m10v_camera_library_load',0x5500a000),0)
  saved=bytes(self.u.mem_read(0x5500a000,104))
  self.assertEqual((saved[16],saved[14]),(6,0));self.assertEqual(saved[20:52],old[20:52])

 def test_native_selector_uses_gr4_private_ids(self):
  ui=self.prepare_detail();self.w(ui+0x198,0x5500d000)
  # The first private row follows the untouched nine official rows.
  self.w(0x5500d110,9)
  self.assertEqual(self.call(0x531ca630,ui),19)
 def test_real_stock_slider_setup_keeps_range_and_handles_allocation_failure(self):
  ui=self.prepare_detail();self.w(ui+0x198,0x5500d000);self.w(0x5500d110,9)
  self.fail_allocate=True
  self.call(0x531cab84,ui)
  self.assertIn(('range',0,8,45),self.calls)
  self.assertTrue(any(row[0]=='default' for row in self.calls))
  self.assertEqual(self.allocations,0)
 def test_patch_preimages_and_all_80_stock_lists_are_preserved(self):
  rtos=(ROOT/'data/research/gr4/RTOS.bin').read_bytes();self.assertEqual(hashlib.sha256(rtos).hexdigest(),RTOS_SHA256)
  for patch in self.detail['patches']:
   at=patch['address']-0x53000000;self.assertEqual(rtos[at:at+len(bytes.fromhex(patch['expected']))].hex(),patch['expected'])
  for variant,ids in self.detail['variant_ids'].items():
   address=self.detail['variant_tables'][variant]
   for index in range(80):
    old,n=struct.unpack_from('<II',rtos,0xd9a458+index*8);new,count=struct.unpack('<II',self.u.mem_read(address+index*8,8))
    self.assertEqual(count,n+len(ids));self.assertEqual(bytes(self.u.mem_read(new,n*2)),rtos[old-0x53000000:old-0x53000000+n*2])
