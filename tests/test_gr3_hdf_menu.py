"""Run the independent HDF menu and its actual journal on compiled ARM."""
import struct,tempfile,unittest,zlib
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn import arm_const as A
from scripts.build_gr3_m10v_library import build
from scripts.build_gr3_digital_hdf import official_rtos

class HdfMenuTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
  cls.m=build(cls.tmp.name,sd_library=True,film_library=False);cls.b=(Path(cls.tmp.name)/'m10v-library-arm.bin').read_bytes();cls.rom=official_rtos()
 def setUp(self):
  self.u=u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
  u.mem_map(0x53000000,0x1500000);u.mem_write(0x53000000,self.rom);u.mem_write(self.m['base'],self.b);u.mem_map(0x55000000,0x100000)
  self.files={};self.writes=[];self.reads=[];self.fail_write=False;self.fail_verify=False;self.allocate=True;self.cursor=0x55040000;self.closed=[];self.captions=[];self.destroyed=[];self.live=set();self.freed=[]
  self.put(0x55002008,0x55002100);self.put(0x55002100,0x55002200);u.mem_write(0x55002220,b'\x01');self.owner=0x55010000;self.page=self.owner+0x13bc
  self.put(0x55009000+0x28,0x55009100);self.put(0x55009000+0x34,0x55009104)
  def service(uc,a,n,d):
   r=[uc.reg_read(getattr(A,'UC_ARM_REG_R'+str(i))) for i in range(4)]
   result=0
   if a==0x53828014:result=0x55002000
   elif a in (0x53825648,0x53825fa8):
    self.assertEqual(r[0],0x55002200);self.assertEqual(r[2],24)
    name=bytes(uc.mem_read(r[1],12)).split(b'\0')[0].decode();self.assertIn(name,('M10VHD0.BIN','M10VHD1.BIN'))
    if a==0x53825648:
     self.reads.append(name)
     if self.fail_verify and self.writes:
      self.fail_verify=False
     elif name in self.files:uc.mem_write(r[3],self.files[name]);result=1
    elif not self.fail_write:self.files[name]=bytes(uc.mem_read(r[3],24));self.writes.append(name);result=1
   elif a==0x536af2a8:
    if self.allocate:result=self.cursor;self.cursor+=0x200;self.live.add(result)
   elif a in (0x5339199c,0x53393d84,0x53396944):self.put(r[0],0x55009000);result=r[0]
   elif a==0x5319aa68:result=r[0]
   elif a==0x5316cde8:
    self.destroyed.append((r[1],r[2]))
    for w in struct.unpack('<'+'I'*r[2],uc.mem_read(r[1],r[2]*4)):
     self.assertIn(w,self.live);self.live.remove(w)
   elif a==0x536af2e4:self.assertIn(r[0],self.live);self.live.remove(r[0]);self.freed.append(r[0])
   elif a==0x5316ca28:self.closed.append(r[0])
   elif a==0x53396f80:self.captions.append((r[0],r[1]))
   elif a in (0x5316c8d4,0x5316ce8c,0x5316c774,0x533aba64,0x53393e00,0x5339658c,0x533ad3c0,0x533ad308,0x5316d354,0x55009100,0x55009104):result=r[0]
   else:return
   uc.reg_write(A.UC_ARM_REG_R0,result);uc.reg_write(A.UC_ARM_REG_PC,uc.reg_read(A.UC_ARM_REG_LR))
  u.hook_add(UC_HOOK_CODE,service)
 def put(self,a,n):self.u.mem_write(a,struct.pack('<I',n))
 def get(self,a):return struct.unpack('<I',self.u.mem_read(a,4))[0]
 def call(self,name,*args):
  u=self.u
  for i in range(13):u.reg_write(getattr(A,'UC_ARM_REG_R'+str(i)),args[i] if i<len(args) else 0)
  u.reg_write(A.UC_ARM_REG_SP,0x550ff000);u.reg_write(A.UC_ARM_REG_LR,0x550ff800)
  u.emu_start(self.m['symbols'][name],0x550ff800,count=200000)
  self.assertEqual(u.reg_read(A.UC_ARM_REG_PC),0x550ff800);self.assertEqual(u.reg_read(A.UC_ARM_REG_SP),0x550ff000)
  v=u.reg_read(A.UC_ARM_REG_R0);return v if v<0x80000000 else v-0x100000000
 def key(self,k):self.u.mem_write(0x55006000,struct.pack('<H',k));return self.call('m10v_hdf_menu_key',self.page,0x55006000)
 def ready(self):
  self.call('m10v_hdf_menu_top_ctor',self.owner)
  self.assertEqual(self.call('m10v_hdf_menu_ready',self.page,0),1)
 def test_independent_menu_round_trip_and_cancel_without_film_state(self):
  self.files['M10V6A.bin']=bytes([0xa5])*104
  self.ready();self.assertEqual(self.get(self.page+0x17c),9)
  self.call('m10v_hdf_menu_enter',self.page,0,0)
  self.assertIn(970,[id for _,id in self.captions]);self.assertEqual(self.get(self.page+0x180),0)
  self.key(0xcf);self.key(0xcf);self.assertEqual(self.get(self.page+0x180),2)
  self.key(0xda);self.assertEqual(self.writes,[]);self.assertEqual(self.closed,[self.page])
  self.assertEqual(self.call('m10v_hdf_menu_ready',self.page,0),1);self.assertEqual(self.get(self.page+0x180),0)
  self.key(0xcf);self.key(0xcf);self.key(0xd8);self.assertEqual(self.writes,['M10VHD1.BIN'])
  self.assertEqual(self.call('m10v_hdf_menu_ready',self.page,0),1);self.assertEqual(self.get(self.page+0x180),2)
  self.assertEqual(self.files['M10V6A.bin'],bytes([0xa5])*104)
 def test_failed_save_retains_saved_setting_and_does_not_close(self):
  self.ready();self.key(0xcf);self.fail_write=True;self.key(0xd8)
  self.assertEqual(self.closed,[]);self.assertEqual(self.get(self.page+0x180),0);self.assertEqual(self.get(self.page+0x188),1);self.assertIn(976,[i for _,i in self.captions])
 def test_successful_write_with_failed_readback_reconciles_display_with_capture_setting(self):
  self.ready();self.key(0xcf);self.key(0xcf);self.fail_verify=True;self.key(0xd8)
  self.assertEqual(self.closed,[]);self.assertEqual(self.get(self.page+0x188),1)
  self.assertEqual(self.call('m10v_hdf_load',0x55007000),0)
  self.assertEqual(self.get(self.page+0x180),self.get(0x55007000))
  self.assertEqual(self.get(self.page+0x184),2)
 def test_corrupt_latest_record_falls_back_and_invalid_strength_does_not_write(self):
  self.assertEqual(self.call('m10v_hdf_save',1),0);first=self.files['M10VHD1.BIN']
  self.assertEqual(self.call('m10v_hdf_save',3),0);b=bytearray(self.files['M10VHD0.BIN']);b[12]^=1;self.files['M10VHD0.BIN']=bytes(b)
  self.assertEqual(self.call('m10v_hdf_load',0x55007000),0);self.assertEqual(self.get(0x55007000),1);self.assertEqual(self.files['M10VHD1.BIN'],first)
  before=dict(self.files);self.assertLess(self.call('m10v_hdf_save',4),0);self.assertEqual(self.files,before)
 def test_allocation_failure_releases_partial_page_and_never_calls_constructor_on_null(self):
  self.call('m10v_hdf_menu_top_ctor',self.owner);self.allocate=False
  self.assertEqual(self.call('m10v_hdf_menu_ready',self.page,0),0);self.assertEqual(self.get(self.page+0x17c),0)
 def test_destroy_cleans_only_its_owned_nine_widgets(self):
  self.ready();style=self.get(self.page+0x1bc);self.call('m10v_hdf_menu_destroy',self.page)
  self.assertEqual(self.destroyed,[(style,8),(self.page+0x158,9)]);self.assertEqual(self.get(self.page+0x17c),0)
  self.assertEqual(self.freed,[style]);self.assertEqual(self.live,set());self.assertEqual(self.get(self.page+0x1bc),0)
