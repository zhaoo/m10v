"""ARM execution of journal adapter and eight-byte owned cache."""
import pathlib,struct,subprocess,tempfile,unittest
from scripts.build_gr3_m10v_library import FLAGS,link_object
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import *
ROOT=pathlib.Path(__file__).resolve().parents[1];RAM=0x60000000;OWNER=RAM+0x2000;PAGE=OWNER+0x13bc;STOP=RAM+0xff000
class CameraZoom(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.symbols={'m10v_zoom_bits':0x540b0000,'m10v_zoom_live_apply':0x540b0004,'m10v_zoom_native_back_bits':0x540b0008,'m10v_zoom_native_front_bits':0x540b000c};cls.blobs=[]
  with tempfile.TemporaryDirectory() as tmp:
   for name,addr in [('m10v_zoom.c',0x540c0000),('m10v_zoom_camera.c',0x540d0000)]:
    obj=pathlib.Path(tmp)/'a.o';subprocess.run(['clang',*FLAGS,*getattr(cls,'seed_flags',[]),*getattr(cls,'companion_flags',[]),'-c',str(ROOT/'native/gr3'/name),'-o',str(obj)],check=True,capture_output=True)
    exports=['m10v_zoom_'+n for n in (['load','open','adjust','save','replace'] if name=='m10v_zoom.c' else ['camera_load','camera_save','camera_bits','camera_slot','camera_select'])]
    if name=='m10v_zoom_camera.c' and getattr(cls,'companion_flags',[]):exports+=['m10v_zoom_camera_snapshot','m10v_zoom_camera_prime']
    b,s=link_object(obj.read_bytes(),addr,cls.symbols,prefix='m10v_settings_',omitted_exports=('m10v_settings_open','m10v_settings_key'),additional_exports=exports);cls.symbols.update(s);cls.blobs.append((addr,b))
 def setUp(self):
  self.u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u=self.u
  for a,n in [(0x53000000,0x2000000),(0x55000000,0x1000000),(RAM,0x100000)]:u.mem_map(a,n)
  for a,b in self.blobs:u.mem_write(a,b)
  self.word(0x55063910,1);self.word(0x55063988,OWNER);self.word(RAM+0x108,RAM+0x120);self.word(RAM+0x120,RAM+0x140);u.mem_write(RAM+0x160,b'\x01')
  self.files={};self.fail_next_read=False;self.fail_verify_once=False;self.reads=0;self.writes=0;self.apply=[];self.fail_write=False;self.fail_marker=False;self.fail_apply=False;self.actual_bits=struct.unpack('<I',struct.pack('<f',35/28))[0]
  u.reg_write(UC_ARM_REG_SP,RAM+0xe0000)
  def hook(uc,a,size,data):
   r=[uc.reg_read(reg) for reg in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]];v=0
   if a==0x53828014:v=RAM+0x100
   elif a in [0x53825648,0x53825fa8]:
    name=bytes(uc.mem_read(r[1],12)).split(b'\0')[0]
    if a==0x53825648:
     self.reads+=1
     if self.fail_next_read:self.fail_next_read=False
     elif name in self.files:uc.mem_write(r[3],self.files[name]);v=1
    else:
     self.writes+=1
     if not self.fail_write and not (self.fail_marker and name==b'M10VZW.bin'):self.files[name]=bytes(uc.mem_read(r[3],r[2]));v=1
     if self.fail_verify_once:self.fail_verify_once=False;self.fail_next_read=True
   elif a==0x540b0000:v=struct.unpack('<I',struct.pack('<f',r[0]/28))[0]
   elif a==0x53525d5c:self.word(RAM+0x180,RAM+0x190);v=RAM+0x180
   elif a in (0x540b0008,0x540b000c):v=self.actual_bits
   elif a in (0x5320ad88,0x5320b31c):v=RAM+0x1c0
   elif a==0x540b0004:self.apply.append(r[0]);v=0xffffffff if self.fail_apply else 0
   else:return
   uc.reg_write(UC_ARM_REG_R0,v);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
  u.hook_add(UC_HOOK_CODE,hook)
 def word(self,a,v):self.u.mem_write(a,struct.pack('<I',v))
 def call(self,name,*args):
  for r,v in zip([UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3],args):self.u.reg_write(r,v)
  self.u.reg_write(UC_ARM_REG_LR,STOP);self.u.emu_start(self.symbols['m10v_zoom_'+name],STOP,count=100000);return self.u.reg_read(UC_ARM_REG_R0)
 def test_lazy_cache_load_once_and_unchanged_stride(self):
  self.u.mem_write(PAGE+852,b'KEEP');self.call('camera_bits',0);n=self.reads
  self.call('camera_bits',1);self.assertEqual(self.reads,n);self.assertEqual(n,2);self.assertEqual(bytes(self.u.mem_read(PAGE+852,4)),b'KEEP')
 def test_durable_commit_then_active_apply(self):
  s=RAM+0x800;e=RAM+0x900;self.call('camera_load',s);self.call('camera_select',0)
  self.u.mem_write(e,struct.pack('<III',0,0,36));self.assertEqual(self.call('camera_save',s,e),0)
  self.assertEqual(self.apply,[0]);self.assertEqual(self.writes,1);self.assertIn(b'M10VZB.bin',self.files);self.assertEqual(len(self.files[b'M10VZB.bin']),24)
  self.assertEqual(struct.unpack('<HH',self.u.mem_read(s+4,4)),(36,50))
 def test_initial_native_active_slot_is_reapplied_without_cached_preference(self):
  s=RAM+0x800;e=RAM+0x900;self.call('camera_load',s)
  self.u.mem_write(e,struct.pack('<III',0,0,36));self.assertEqual(self.call('camera_save',s,e),0);self.assertEqual(self.apply,[0])
 def test_external_native_change_prevents_wrong_slot_reapply(self):
  s=RAM+0x800;e=RAM+0x900;self.call('camera_load',s);self.call('camera_select',0)
  self.actual_bits=struct.unpack('<I',struct.pack('<f',50/28))[0]
  self.u.mem_write(e,struct.pack('<III',0,0,36));self.assertEqual(self.call('camera_save',s,e),0);self.assertFalse(self.apply)
 def test_write_failure_does_not_apply_or_publish(self):
  s=RAM+0x800;e=RAM+0x900;self.call('camera_load',s);self.call('camera_select',0);self.fail_write=True
  self.u.mem_write(e,struct.pack('<III',0,0,36));self.assertEqual(self.call('camera_save',s,e),0xffffffff);self.assertFalse(self.apply);self.assertEqual(struct.unpack('<HH',self.u.mem_read(PAGE+844,4)),(35,50))
 def test_apply_failure_preserves_durable_new_value(self):
  s=RAM+0x800;e=RAM+0x900;self.call('camera_load',s);self.call('camera_select',0);self.fail_apply=True
  self.u.mem_write(e,struct.pack('<III',0,0,36));self.assertEqual(self.call('camera_save',s,e),0xffffffff);self.assertEqual(struct.unpack('<HH',self.u.mem_read(s+4,4)),(36,50))
 def test_failed_apply_retry_reapplies_instead_of_reporting_false_success(self):
  s=RAM+0x800;e=RAM+0x900;self.call('camera_load',s);self.call('camera_select',0);self.fail_apply=True
  self.u.mem_write(e,struct.pack('<III',0,0,36));self.assertEqual(self.call('camera_save',s,e),0xffffffff)
  self.u.mem_write(e,struct.pack('<III',1,0,36));self.assertEqual(self.call('camera_save',s,e),0xffffffff)
  self.assertEqual(self.apply,[0,0]);self.assertEqual(self.writes,1)
  self.fail_apply=False;self.assertEqual(self.call('camera_save',s,e),0)
  self.assertEqual(self.apply,[0,0,0]);self.assertEqual(struct.unpack('<I',self.u.mem_read(PAGE+848,4))[0]&4,0)
 def test_other_slot_save_preserves_pending_and_manual_selection_clears_it(self):
  s=RAM+0x800;e=RAM+0x900;self.call('camera_load',s);self.call('camera_select',0);self.fail_apply=True
  self.u.mem_write(e,struct.pack('<III',0,0,36));self.assertEqual(self.call('camera_save',s,e),0xffffffff)
  self.u.mem_write(e,struct.pack('<III',1,1,49));self.assertEqual(self.call('camera_save',s,e),0)
  self.assertEqual(self.apply,[0]);self.assertEqual(struct.unpack('<I',self.u.mem_read(PAGE+848,4))[0]&7,4)
  self.call('camera_load',s);self.assertEqual(struct.unpack('<I',self.u.mem_read(PAGE+848,4))[0]&7,4)
  self.call('camera_select',1);self.assertEqual(struct.unpack('<I',self.u.mem_read(PAGE+848,4))[0]&7,1)
  self.actual_bits=struct.unpack('<I',struct.pack('<f',49/28))[0]
  self.u.mem_write(e,struct.pack('<III',2,0,36));self.assertEqual(self.call('camera_save',s,e),0);self.assertEqual(self.apply,[0])
 def test_invalid_save_does_not_touch_storage(self):
  self.assertEqual(self.call('camera_save',0,RAM+0x900),0xffffffff)
  self.assertEqual(self.call('camera_save',RAM+0x800,0),0xffffffff)
  self.assertEqual(self.reads,0);self.assertEqual(self.writes,0)
 def test_no_owner_does_not_lazy_read(self):
  self.word(0x55063910,0);self.call('camera_bits',0);self.assertEqual(self.reads,0)
class SeedZoom(CameraZoom):
 seed_flags=['-DM10V_ZOOM_SEED_LO=123u','-DM10V_ZOOM_SEED_HI=456u','-DM10V_ZOOM_SEED_FIRST=40u','-DM10V_ZOOM_SEED_SECOND=48u']
 # Inherited tests describe the disabled configuration; only seed tests apply.
 def test_seed_writes_both_slots_once_and_preserves_later_camera_changes(self):
  s=RAM+0x800;e=RAM+0x900
  self.assertNotEqual(self.call('camera_load',s),0xffffffff)
  self.assertEqual(struct.unpack('<HH',self.u.mem_read(s+4,4)),(40,48))
  self.assertIn(b'M10VZW.bin',self.files);writes=self.writes
  self.call('camera_load',s);self.assertEqual(self.writes,writes)
  seq=struct.unpack('<I',self.u.mem_read(s,4))[0]
  self.u.mem_write(e,struct.pack('<III',seq,1,47));self.assertEqual(self.call('camera_save',s,e),0)
  self.call('camera_load',s);self.assertEqual(struct.unpack('<HH',self.u.mem_read(s+4,4)),(40,47))
 def test_failed_marker_keeps_error_until_retry_and_does_not_publish(self):
  s=RAM+0x800;self.fail_marker=True
  self.assertEqual(self.call('camera_load',s),0xffffffff)
  self.assertEqual(struct.unpack('<HH',self.u.mem_read(PAGE+844,4)),(0,0))
  self.fail_marker=False;self.assertNotEqual(self.call('camera_load',s),0xffffffff)
  self.assertEqual(struct.unpack('<HH',self.u.mem_read(PAGE+844,4)),(40,48))
# Avoid rerunning the disabled-only cases against the enabled build.
for _name in list(CameraZoom.__dict__):
 if _name.startswith('test_'):setattr(SeedZoom,_name,None)
if __name__=='__main__':unittest.main()

class CompanionZoomSnapshot(CameraZoom):
 companion_flags=['-DM10V_COMPANION_ENABLED=1']
 def test_cold_prime_enables_snapshot_without_persistent_write_or_crop_change(self):
  out=RAM+0xa00
  self.assertEqual(self.call('camera_snapshot',out),0xffffffff)
  self.assertEqual(self.call('camera_prime'),0)
  self.assertEqual(self.call('camera_snapshot',out),0)
  self.assertEqual(struct.unpack('<IHH',self.u.mem_read(out,8)),(0,35,50))
  self.assertEqual(self.writes,0)
  self.assertEqual(self.apply,[])
 def test_failed_verify_cannot_report_durable_value_as_effective_without_repair(self):
  s=RAM+0x800;e=RAM+0x900;out=RAM+0xa00
  self.call('camera_load',s);self.call('camera_select',0);self.fail_verify_once=True
  self.u.mem_write(e,struct.pack('<III',0,0,36));self.assertEqual(self.call('camera_save',s,e),0xffffffff)
  self.assertEqual(self.writes,1);self.assertEqual(self.apply,[])
  self.assertEqual(struct.unpack('<HH',self.u.mem_read(PAGE+844,4)),(35,50))
  self.u.mem_write(out,b'KEEPDATA');before=self.reads
  self.assertEqual(self.call('camera_snapshot',out),0xffffffff)
  self.assertEqual(bytes(self.u.mem_read(out,8)),b'KEEPDATA')
  self.assertEqual(self.writes,1);self.assertEqual(self.apply,[]);self.assertGreater(self.reads,before)
 def test_published_slots_with_failed_live_apply_remain_unavailable(self):
  s=RAM+0x800;e=RAM+0x900;out=RAM+0xa00
  self.call('camera_load',s);self.call('camera_select',0);self.fail_apply=True
  self.u.mem_write(e,struct.pack('<III',0,0,36));self.assertEqual(self.call('camera_save',s,e),0xffffffff)
  self.assertEqual(struct.unpack('<HH',self.u.mem_read(PAGE+844,4)),(36,50));self.assertEqual(self.apply,[0])
  self.assertEqual(self.call('camera_snapshot',out),0xffffffff);self.assertEqual(self.writes,1);self.assertEqual(self.apply,[0])

 def test_consistent_snapshot_is_read_only_and_preserves_outputs_on_backend_divergence(self):
  s=RAM+0x800;out=RAM+0xa00
  self.call('camera_load',s);self.call('camera_select',0)
  self.assertEqual(self.call('camera_snapshot',out),0);self.assertEqual(struct.unpack('<IHH',self.u.mem_read(out,8)),(0,35,50))
  self.actual_bits=struct.unpack('<I',struct.pack('<f',39/28))[0];self.u.mem_write(out,b'KEEPDATA')
  self.assertEqual(self.call('camera_snapshot',out),0xffffffff);self.assertEqual(bytes(self.u.mem_read(out,8)),b'KEEPDATA')
  self.assertEqual(self.writes,0);self.assertEqual(self.apply,[])
