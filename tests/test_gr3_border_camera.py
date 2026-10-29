"""Execute actual border journal/cache and Effects menu on compiled ARM.

Only stock RTOS filesystem/widget services are substituted. Journal bytes and
CRC expectations are independent Python fixtures; capture getter has no FS.
"""
import struct, subprocess, tempfile, unittest, zlib
from pathlib import Path
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm_const as A
from scripts.build_gr3_m10v_library import FLAGS, link_object

ROOT = Path(__file__).resolve().parents[1]


class BorderCameraTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
  cls.base=0x540b6000
  cls.symbols={};cls.code=bytearray()
  for file,prefix,flags,externals in [
   ('m10v_border_camera.c','m10v_border_',[],{}),
   ('m10v_hdf_menu.c','m10v_hdf_menu_', ['-DM10V_BORDER_ENABLED=1','-DM10V_HDF_GROUPED=1'],
    {'m10v_hdf_load':0x53000100,'m10v_hdf_save':0x53000104,
     'm10v_hdf_menu_parent_ctor':0x5319aa68,'m10v_hdf_menu_parent_dtor':0x53000108,
     'm10v_hdf_menu_parent_factory':0x5300010c,'m10v_hdf_menu_parent_key_route':0x53000110,
     'm10v_hdf_menu_vtable':0x53000114})]:
   obj=Path(cls.tmp.name)/(file+'.o')
   subprocess.run(['clang',*FLAGS,'-DM10V_HDF_OWNER_OFFSET=0x223c',
                   '-DM10V_BORDER_CACHE_OWNER_OFFSET=0x23e4',*flags,'-c',str(ROOT/'native/gr3'/file),'-o',str(obj)],check=True,capture_output=True)
   while len(cls.code)%16:cls.code.append(0)
   code,symbols=link_object(obj.read_bytes(),cls.base+len(cls.code),{**cls.symbols,**externals},prefix)
   cls.code.extend(code);cls.symbols.update(symbols)
 def setUp(self):
  self.u=u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
  u.mem_map(0x53000000,0x1500000);u.mem_write(self.base,bytes(self.code));u.mem_map(0x55000000,0x100000)
  self.owner=0x55010000;self.page=self.owner+0x223c;self.cache=self.owner+0x23e4
  self.files={};self.reads=[];self.writes=[];self.fail_write=False;self.fail_verify=False;self.verify_pending=False;self.fs_ready=True;self.forbid_capture_services=False;self.fail_reads=0
  self.cursor=0x55040000;self.captions=[];self.closed=[];self.hdf=0;self.hdf_writes=[]
  self.put(0x55002008,0x55002100);self.put(0x55002100,0x55002200);u.mem_write(0x55002220,b'\x01')
  self.put(0x55063910,1);self.put(0x55063988,self.owner)
  self.put(0x55009028,0x55009100);self.put(0x55009034,0x55009104)
  def service(uc,a,n,d):
   r=[uc.reg_read(getattr(A,'UC_ARM_REG_R'+str(i))) for i in range(4)];result=0
   if a in (0x53828014,0x53825648,0x53825fa8,0x536af2a8):self.assertFalse(self.forbid_capture_services,'capture getter called FS/allocator')
   if a==0x53828014:result=0x55002000 if self.fs_ready else 0
   elif a in (0x53825648,0x53825fa8):
    self.assertEqual(r[0],0x55002200);self.assertEqual(r[2],24)
    name=bytes(uc.mem_read(r[1],12)).split(b'\0')[0].decode()
    self.assertIn(name,('BORDERA.BIN','BORDERB.BIN'))
    if a==0x53825648:
     self.reads.append(name)
     if self.fail_reads:self.fail_reads-=1
     elif self.verify_pending:self.verify_pending=False;self.fail_verify=False
     elif name in self.files:uc.mem_write(r[3],self.files[name]);result=1
    elif not self.fail_write:self.files[name]=bytes(uc.mem_read(r[3],24));self.writes.append(name);self.verify_pending=self.fail_verify;result=1
   elif a==0x53000100:self.put(r[0],self.hdf)
   elif a==0x53000104:self.hdf=r[0];self.hdf_writes.append(r[0])
   elif a==0x536af2a8:result=self.cursor;self.cursor+=0x200
   elif a in (0x5339199c,0x53393d84,0x53396944):self.put(r[0],0x55009000);result=r[0]
   elif a==0x5316ca28:self.closed.append(r[0])
   elif a==0x53396f80:self.captions.append((r[0],r[1]))
   elif a in (0x5319aa68,0x5316c8d4,0x5316ce8c,0x5316c774,0x5316cde8,0x533aba64,0x53393e00,0x5339658c,0x533ad3c0,0x533ad308,0x5316d354,0x55009100,0x55009104,0x53000108,0x5300010c,0x53000110,0x53000114):result=r[0]
   else:return
   uc.reg_write(A.UC_ARM_REG_R0,result);uc.reg_write(A.UC_ARM_REG_PC,uc.reg_read(A.UC_ARM_REG_LR))
  u.hook_add(UC_HOOK_CODE,service)
 def put(self,a,n):self.u.mem_write(a,struct.pack('<I',n))
 def get(self,a):return struct.unpack('<I',self.u.mem_read(a,4))[0]
 def call(self,name,*args):
  u=self.u
  for i in range(13):u.reg_write(getattr(A,'UC_ARM_REG_R'+str(i)),args[i] if i<len(args) else 0)
  u.reg_write(A.UC_ARM_REG_SP,0x550ff000);u.reg_write(A.UC_ARM_REG_LR,0x550ff800)
  u.emu_start(self.symbols[name],0x550ff800,count=200000)
  self.assertEqual(u.reg_read(A.UC_ARM_REG_PC),0x550ff800);self.assertEqual(u.reg_read(A.UC_ARM_REG_SP),0x550ff000)
  v=u.reg_read(A.UC_ARM_REG_R0);return v if v<0x80000000 else v-0x100000000
 def ready(self):
  self.call('m10v_hdf_menu_top_ctor',self.owner)
  self.assertEqual(self.call('m10v_hdf_menu_ready',self.page,0),1)
 def key(self,k):self.u.mem_write(0x55006000,struct.pack('<H',k));return self.call('m10v_hdf_menu_key',self.page,0x55006000)
 @staticmethod
 def record(sequence,style):
  b=struct.pack('<5I',0x31524442,1,sequence,style,0);return b+struct.pack('<I',zlib.crc32(b))
 def test_missing_records_default_off_and_capture_getter_never_reads_files(self):
  self.assertEqual(self.call('m10v_border_camera_cached'),0)
  self.assertEqual(self.reads,[])
  self.assertEqual(self.call('m10v_border_camera_refresh',self.owner),0)
  self.forbid_capture_services=True
  before=list(self.reads);self.assertEqual(self.call('m10v_border_camera_cached'),0);self.assertEqual(self.reads,before)
  self.assertEqual(self.writes,[])
 def test_snapshot_status_distinguishes_off_from_unavailable_without_clobber(self):
  out=0x55007000;self.put(out,0xdeadbeef)
  self.assertEqual(self.call('m10v_border_camera_snapshot',out),0);self.assertEqual(self.get(out),0xdeadbeef)
  self.call('m10v_border_camera_refresh',self.owner)
  self.forbid_capture_services=True
  self.assertEqual(self.call('m10v_border_camera_snapshot',out),1);self.assertEqual(self.get(out),0)
  self.put(out,0xdeadbeef);self.put(self.cache+4,3)
  self.assertEqual(self.call('m10v_border_camera_snapshot',out),0);self.assertEqual(self.get(out),0xdeadbeef)
  self.put(self.cache+4,2);self.put(self.cache+8,3)
  self.assertEqual(self.call('m10v_border_camera_snapshot',out),0);self.assertEqual(self.get(out),0xdeadbeef)
  self.assertEqual(self.call('m10v_border_camera_snapshot',0),0)
 def test_save_readback_restart_and_corrupt_latest_fallback(self):
  self.assertEqual(self.call('m10v_border_camera_save',self.owner,1),0)
  self.assertEqual(self.files['BORDERB.BIN'],self.record(1,1));self.assertEqual(self.call('m10v_border_camera_cached'),1)
  self.assertEqual(self.call('m10v_border_camera_save',self.owner,2),0)
  self.assertEqual(self.files['BORDERA.BIN'],self.record(2,2))
  b=bytearray(self.files['BORDERA.BIN']);b[12]^=1;self.files['BORDERA.BIN']=bytes(b)
  self.u.mem_write(self.cache,bytes(16))
  self.assertEqual(self.call('m10v_border_camera_refresh',self.owner),0);self.assertEqual(self.call('m10v_border_camera_cached'),1)
 def test_invalid_enum_overflow_and_failed_write_preserve_cached_style(self):
  self.call('m10v_border_camera_save',self.owner,1)
  before=dict(self.files)
  self.assertLess(self.call('m10v_border_camera_save',self.owner,3),0);self.assertEqual(self.files,before)
  self.fail_write=True;self.assertLess(self.call('m10v_border_camera_save',self.owner,2),0)
  self.assertEqual(self.call('m10v_border_camera_cached'),1)
  self.fail_write=False;self.files['BORDERA.BIN']=self.record(0xffffffff,2)
  self.assertLess(self.call('m10v_border_camera_save',self.owner,0),0);self.assertEqual(self.call('m10v_border_camera_cached'),1)
 def test_failed_verification_never_publishes_unverified_then_refresh_reconciles(self):
  self.call('m10v_border_camera_save',self.owner,1);self.fail_verify=True
  self.assertLess(self.call('m10v_border_camera_save',self.owner,2),0)
  self.assertEqual(self.call('m10v_border_camera_cached'),1)
  self.call('m10v_border_camera_refresh',self.owner);self.assertEqual(self.call('m10v_border_camera_cached'),2)
 def test_crc_valid_unknown_style_version_or_reserved_falls_back(self):
  self.files['BORDERB.BIN']=self.record(1,1)
  for words in [(0x31524442,1,2,3,0),(0x31524442,2,2,2,0),(0x31524442,1,2,2,1)]:
   b=struct.pack('<5I',*words);self.files['BORDERA.BIN']=b+struct.pack('<I',zlib.crc32(b))
   self.assertEqual(self.call('m10v_border_camera_refresh',self.owner),0)
   self.assertEqual(self.call('m10v_border_camera_cached'),1)
 def test_transient_initial_reads_do_not_rewind_authenticated_sequence(self):
  self.call('m10v_border_camera_save',self.owner,1)
  self.call('m10v_border_camera_save',self.owner,2)
  self.fail_reads=2
  self.assertEqual(self.call('m10v_border_camera_save',self.owner,0),0)
  self.assertEqual(self.files['BORDERB.BIN'],self.record(3,0))
  self.call('m10v_border_camera_refresh',self.owner)
  self.assertEqual(self.call('m10v_border_camera_cached'),0)
 def test_unpublished_cache_cannot_report_success_for_an_older_journal_write(self):
  self.files={'BORDERA.BIN':self.record(2,2),'BORDERB.BIN':self.record(1,1)}
  self.fail_reads=2
  self.assertLess(self.call('m10v_border_camera_save',self.owner,0),0)
  self.call('m10v_border_camera_refresh',self.owner)
  self.assertEqual(self.call('m10v_border_camera_cached'),2)
 def test_unavailable_filesystem_and_unpublished_or_mutating_cache_fail_off(self):
  self.fs_ready=False;self.assertLess(self.call('m10v_border_camera_refresh',self.owner),0)
  self.assertEqual(self.call('m10v_border_camera_cached'),0)
  self.fs_ready=True;self.call('m10v_border_camera_save',self.owner,2)
  self.put(self.cache+4,3);self.assertEqual(self.call('m10v_border_camera_cached'),0)
  self.put(self.cache+4,2);self.put(0x55063910,0);self.assertEqual(self.call('m10v_border_camera_cached'),0)
 def test_border_menu_cancel_and_confirm_are_global_and_preserve_hdf(self):
  self.ready();self.key(0xd1);self.key(0xd8) # down, enter border
  self.assertNotIn(1158,[id for _,id in self.captions],'hidden fourth choice must not resolve an unallocated resource')
  self.key(0xcf);self.key(0xcf);self.key(0xda) # draft2 cancel
  self.assertEqual(self.writes,[]);self.assertEqual(self.call('m10v_border_camera_cached'),0)
  self.key(0xd8);self.key(0xcf);self.key(0xd8)
  self.assertEqual(self.files['BORDERB.BIN'],self.record(1,1));self.assertEqual(self.hdf_writes,[])
  self.key(0xce);self.key(0xd8);self.key(0xcf);self.key(0xd8) # up,HDF,weak,save
  self.assertEqual(self.hdf_writes,[1]);self.assertEqual(self.call('m10v_border_camera_cached'),1)
 def test_failed_menu_save_stays_open_and_reconciles_actual_record(self):
  self.ready();self.key(0xd1);self.key(0xd8);self.key(0xcf);self.fail_verify=True;self.key(0xd8)
  self.assertEqual(self.closed,[]);self.assertEqual(self.get(self.page+0x188),1)
  self.assertEqual(self.call('m10v_border_camera_cached'),1)
  self.key(0xda);self.key(0xd8);self.assertEqual(self.get(self.page+0x180),1)
 def test_border_only_menu_links_without_hdf_and_saves(self):
  obj=Path(self.tmp.name)/'border-only-menu.o'
  subprocess.run(['clang',*FLAGS,'-DM10V_HDF_OWNER_OFFSET=0x223c','-DM10V_BORDER_CACHE_OWNER_OFFSET=0x23e4',
                  '-DM10V_BORDER_ENABLED=1','-DM10V_HDF_ENABLED=0','-DM10V_HDF_GROUPED=1',
                  '-c',str(ROOT/'native/gr3/m10v_hdf_menu.c'),'-o',str(obj)],check=True,capture_output=True)
  # Link without HDF load/save symbols: a hidden dependency is a hard failure.
  external={k:v for k,v in self.symbols.items() if k.startswith('m10v_border_')}
  external.update({'m10v_hdf_menu_parent_ctor':0x5319aa68,'m10v_hdf_menu_parent_dtor':0x53000108,
                   'm10v_hdf_menu_parent_factory':0x5300010c,'m10v_hdf_menu_parent_key_route':0x53000110,
                   'm10v_hdf_menu_vtable':0x53000114})
  code,symbols=link_object(obj.read_bytes(),0x540c6000,external,'m10v_hdf_menu_')
  self.u.mem_write(0x540c6000,code);self.symbols={**self.symbols,**symbols}
  self.ready();self.key(0xd8);self.key(0xcf);self.key(0xcf);self.key(0xd8)
  self.assertEqual(self.call('m10v_border_camera_cached'),2);self.assertEqual(self.hdf_writes,[])


if __name__=='__main__':unittest.main()
