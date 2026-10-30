"""Execute the paired-save ARM adapter; native task/FS/pool leaves are doubles.
This proves bytes, ownership guards and fallback, never physical task admission.
"""
import struct,subprocess,tempfile,unittest,zlib
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn import arm_const as A
from scripts.build_gr3_m10v_library import FLAGS,link_object
ROOT=Path(__file__).resolve().parents[1]
class PairCameraTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.build_id=123
  cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup);folder=Path(cls.tmp.name)
  helper=folder/'offset.c';helper.write_text('#include <stdio.h>\n#include <stddef.h>\n#include "m10v_settings_controller.h"\nint main(){printf("%u",(unsigned)(M10V_SETTINGS_OWNER_BYTES+offsetof(m10v_settings_controller,half_pair)));}')
  subprocess.run(['clang','-I',str(ROOT/'native/gr3'),str(helper),'-o',str(folder/'offset')],check=True,capture_output=True)
  cls.offset=int(subprocess.check_output([str(folder/'offset')]))
  cls.base=0x540b6000;cls.image=bytearray();cls.symbols={}
  for file,prefix,extra in [('m10v_half_pair.c','m10v_half_pair_',()),('m10v_half_pair_camera.c','m10v_half_pair_camera',('m10v_half_pair_reset','m10v_half_pair_init','m10v_half_pair_select','m10v_half_pair_destroy'))]:
   obj=folder/(file+'.o');subprocess.run(['clang',*FLAGS,'-O2','-fno-jump-tables','-DM10V_HALF_PAIR_BUILD_ID=123','-DM10V_DEBUG_MODE=1','-c',str(ROOT/'native/gr3'/file),'-o',str(obj)],check=True,capture_output=True)
   while len(cls.image)%16:cls.image.append(0)
   code,symbols=link_object(obj.read_bytes(),cls.base+len(cls.image),{**cls.symbols,'m10v_save_trace_recipe_mark':0x53000100,'m10v_save_trace_recipe_raw_status':0x53000104,'m10v_debug_log':0x53000108},prefix,additional_exports=extra)
   cls.image.extend(code);cls.symbols.update(symbols)
 def setUp(self):
  self.u=u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0x53000000,0x1500000);u.mem_write(self.base,bytes(self.image));u.mem_map(0x55000000,0x1000000);u.mem_map(0x60000000,0x100000)
  self.recipe=0x55010000;self.context=self.recipe+0x9b8;self.si=0x55100000;self.req=0x55020000;self.bank=0x60000000;self.owner=0x55030000;self.state=self.owner+self.offset;self.scratch=0x60040000
  self.events=[];self.fs_calls=[];self.files={};self.handles={};self.next_handle=1;self.fail_alloc=False;self.short_read=False;self.fail_write=False;self.cancel_during_read=False;self.setter_calls=[];self.sleeps=[];self.allocations=[];self.freed=[]
  self.put(0x55063910,1);self.put(0x55063988,self.owner)
  self.put(self.recipe,0x53d0fc90);self.put(self.recipe+0x4778,0x31545653);self.put(self.recipe+0x44c8,self.si);self.put(self.recipe+0x5c,self.req);self.put(self.req,0x53d0fe60);u.mem_write(self.req+12,b'\1\0');u.mem_write(self.si+0x7b6,b'\6');u.mem_write(self.recipe+0x140,b'\1')
  for off,val in [(0,0x53d0fbe0),(0x30,self.recipe+0x1a8),(0x34,self.si),(0x38,self.req),(0x3c,self.recipe+0xb0),(0x40,self.recipe+0xd0),(0x44,self.recipe+0xf0),(0x48,self.recipe+0x110),(0x4c,self.recipe+0x130)]:self.put(self.context+off,val)
  self.put(self.recipe+0x304,self.bank);self.put(self.recipe+0x364,8192)
  self.descriptor=[1,self.bank+64,self.bank+128,0,2|(2<<16),2|(2<<16),0,2]
  for off in (0x70,0xb0,0x110):self.words(self.recipe+off,*self.descriptor)
  for off in (0xd0,0xf0):self.words(self.recipe+off,1,self.bank+256,self.bank+512,0,16|(16<<16),16|(16<<16),0,2)
  self.set_pixels(20,70,180)
  self.put(0x55001014,0x55002000);self.put(0x55002000,0x53e00000)
  for i in range(7,14):self.put(0x53e00000+4*i,0x53000200+4*i)
  u.hook_add(UC_HOOK_CODE,self.service)
  self.call('m10v_half_pair_init',self.owner)
 def put(self,addr,val):self.u.mem_write(addr,struct.pack('<I',val))
 def words(self,addr,*values):self.u.mem_write(addr,struct.pack('<'+'I'*len(values),*values))
 def get(self,addr):return struct.unpack('<I',self.u.mem_read(addr,4))[0]
 def set_pixels(self,y,cb,cr):self.u.mem_write(self.bank+64,bytes([y,y+1,y+2,y+3]));self.u.mem_write(self.bank+128,bytes([cb,cr,cb+1,cr+1]))
 def service(self,u,pc,n,data):
  r=[u.reg_read(getattr(A,'UC_ARM_REG_R'+str(i))) for i in range(4)];ret=0
  if pc==0x535847d8:self.fs_calls.append('manager');ret=0x55001000
  elif 0x5300021c<=pc<=0x53000234:
   i=(pc-0x53000200)//4;self.fs_calls.append(i)
   if i==7:
    path=bytes(u.mem_read(r[1],32)).split(b'\0')[0];self.assertEqual(path,b'C:\\M10V\\HALFPAIR.BIN')
    error=self.get(u.reg_read(A.UC_ARM_REG_SP));self.put(error,0)
    if r[2]==0:self.files[path]=bytearray()
    if path in self.files:
     handle=self.next_handle;self.next_handle+=1;self.handles[handle]=[path,0,r[2]];self.put(r[3],handle);ret=1
   elif i==8:self.assertIn(r[1],self.handles);del self.handles[r[1]];self.put(r[2],0);ret=1
   elif i in (9,10):
    path,pos,mode=self.handles[r[1]]
    if i==9 and pos>=40 and self.cancel_during_read:self.put(self.state+12,self.get(self.state+12)|2)
    error=self.get(u.reg_read(A.UC_ARM_REG_SP));self.put(error,0);size=r[3]
    if i==9:
     b=bytes(self.files[path][pos:pos+size]);b=b[:-1] if self.short_read and pos>=40 else b;u.mem_write(r[2],b);size=len(b);ret=1
    elif not self.fail_write:
     end=pos+size;self.files[path].extend(bytes(max(0,end-len(self.files[path]))));self.files[path][pos:end]=bytes(u.mem_read(r[2],size));ret=1
    else:size=0
    self.handles[r[1]][1]+=size
   elif i==11:self.handles[r[1]][1]=r[2];self.put(self.get(u.reg_read(A.UC_ARM_REG_SP)),0);ret=1
   elif i==12:self.put(r[2],len(self.files[self.handles[r[1]][0]]));self.put(r[3],0);ret=1
   elif i==13:self.put(r[2],self.handles[r[1]][1]);self.put(r[3],0);ret=1
  elif pc==0x536a2424:ret=0x55004000
  elif pc==0x536a27e8:self.assertEqual(r[0],0x55004000);self.assertEqual(r[2],2);self.allocations.append(r[1]);ret=0 if self.fail_alloc else self.scratch
  elif pc==0x536a248c:self.assertEqual(r[:2],[0x55004000,self.scratch]);self.freed.append(r[1])
  elif pc==0x532525a4:self.setter_calls.append(r[:2]);ret=42
  elif pc==0x536b0a74:self.sleeps.append(r[0]);self.put(self.state+4,self.get(self.state+4)&~1)
  elif pc==0x5383c8a8:pass
  elif pc==0x53000100:self.events.append(r)
  elif pc==0x53000104:ret=2
  elif pc==0x53000108:self.events.append(r+[self.get(u.reg_read(A.UC_ARM_REG_SP))])
  else:return
  u.reg_write(A.UC_ARM_REG_R0,ret);u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
 def call(self,name,*args):
  for i in range(13):self.u.reg_write(getattr(A,'UC_ARM_REG_R'+str(i)),args[i] if i<len(args) else 0)
  self.u.reg_write(A.UC_ARM_REG_SP,0x55ffe000);self.u.reg_write(A.UC_ARM_REG_LR,0x55fff000)
  self.u.emu_start(self.symbols[name],0x55fff000,count=2000000)
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x55fff000)
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_SP),0x55ffe000)
  r=self.u.reg_read(A.UC_ARM_REG_R0);return r if r<0x80000000 else r-0x100000000
 def capture(self):return self.call('m10v_half_pair_camera',self.context)
 def test_ordinary_capture_is_zero_io_allocation_and_pixel_work(self):
  self.u.mem_write(self.si+0x7b6,b'\0');before=bytes(self.u.mem_read(self.bank,8192));self.assertEqual(self.capture(),0);self.assertEqual(self.fs_calls,[]);self.assertEqual(self.allocations,[]);self.assertEqual(bytes(self.u.mem_read(self.bank,8192)),before)
 def test_two_real_adapter_calls_commit_packed_copy_and_pair_descriptors(self):
  before=bytes(self.u.mem_read(self.bank,8192));self.assertEqual(self.capture(),1);self.assertEqual(bytes(self.u.mem_read(self.bank,8192)),before)
  record=next(iter(self.files.values()));header=struct.unpack('<10I',record[:40]);self.assertEqual(header[:7],(0x32504648,2,self.build_id,2,2,1,8));self.assertEqual(header[7],zlib.crc32(record[40:]));self.assertEqual(header[9],zlib.crc32(record[:36]));self.assertEqual(record[40:],bytes([20,21,22,23,70,180,71,181]))
  self.set_pixels(90,100,130);self.assertEqual(self.capture(),2)
  out=struct.unpack('<8I',self.u.mem_read(self.recipe+0xb0,32));self.assertEqual(out[4],4|(2<<16));self.assertEqual(out[1:3],(self.bank,self.bank+1024));self.assertEqual(bytes(self.u.mem_read(self.bank,4)),bytes([20,21,90,91]));self.assertEqual(bytes(self.u.mem_read(self.bank+1024,4)),bytes([70,180,100,130]))
  for off in (0x70,0x110):self.assertEqual(bytes(self.u.mem_read(self.recipe+off,32)),struct.pack('<8I',*out))
  preview=struct.unpack('<8I',self.u.mem_read(self.recipe+0xd0,32));self.assertEqual(bytes(self.u.mem_read(preview[1]+4*16,16)),bytes([20]*4+[21]*4+[90]*4+[91]*4))
  self.assertEqual(self.freed,[self.scratch]);self.assertEqual(self.handles,{});self.assertEqual(self.get(self.state+12),0)
 def test_allocation_failure_preserves_second_jpeg_and_pending_first(self):
  self.assertEqual(self.capture(),1);self.set_pixels(90,100,130);self.fail_alloc=True;before=bytes(self.u.mem_read(self.bank,8192));descs=bytes(self.u.mem_read(self.recipe+0x70,192));self.assertEqual(self.capture(),-8);self.assertEqual(bytes(self.u.mem_read(self.bank,8192)),before);self.assertEqual(bytes(self.u.mem_read(self.recipe+0x70,192)),descs);self.assertEqual(self.handles,{});self.assertEqual(self.freed,[]);self.assertEqual(self.get(self.state+12),1)
 def test_short_read_and_corrupt_first_cannot_mutate_second(self):
  for corrupt in (False,True):
   with self.subTest(corrupt=corrupt):
    self.setUp();self.assertEqual(self.capture(),1);self.set_pixels(90,100,130);self.short_read=not corrupt
    if corrupt:next(iter(self.files.values()))[-1]^=1
    before=bytes(self.u.mem_read(self.bank,8192));self.assertEqual(self.capture(),-9);self.assertEqual(bytes(self.u.mem_read(self.bank,8192)),before);self.assertEqual(self.handles,{});self.assertEqual(self.get(self.state+8),0)
    self.short_read=False;self.assertEqual(self.capture(),1);self.assertEqual(next(iter(self.files.values()))[40],90)
 def test_boot_init_cancels_old_pending_before_new_first(self):
  self.assertEqual(self.capture(),1);self.set_pixels(90,100,130);self.call('m10v_half_pair_init',self.owner);self.assertEqual(self.capture(),1);self.assertEqual(next(iter(self.files.values()))[40],90)
 def test_orientation_change_starts_new_group(self):
  self.assertEqual(self.capture(),1);self.u.mem_write(self.si+0xc8,b'\3');self.set_pixels(90,100,130);self.assertEqual(self.capture(),1);self.assertEqual(struct.unpack('<10I',next(iter(self.files.values()))[:40])[5],6)
 def test_busy_and_overlapping_raw_guard_never_touch_images(self):
  self.put(self.state+4,1);self.assertEqual(self.capture(),-11);self.assertEqual(self.fs_calls,[]);self.put(self.state+4,0)
  self.put(self.recipe+0x60,self.bank);self.put(self.recipe+0x230,0x55005000);self.u.mem_write(0x55005000,struct.pack('<HH',2,2));before=bytes(self.u.mem_read(self.bank,8192));self.assertEqual(self.capture(),-4);self.assertEqual(bytes(self.u.mem_read(self.bank,8192)),before)
 def test_portrait_orientation_places_first_on_displayed_left(self):
  self.u.mem_write(self.si+0xc8,b'\3');self.assertEqual(self.capture(),1);self.set_pixels(90,100,130);self.assertEqual(self.capture(),2)
  out=struct.unpack('<8I',self.u.mem_read(self.recipe+0xb0,32));self.assertEqual(out[4],2|(4<<16));self.assertEqual(bytes(self.u.mem_read(self.bank,2)),bytes([90,91]));self.assertEqual(bytes(self.u.mem_read(self.bank+128,2)),bytes([20,21]))
 def test_failed_reset_write_preserves_image_and_boot_state(self):
  self.fail_write=True;before=bytes(self.u.mem_read(self.bank,8192));self.assertEqual(self.capture(),-12);self.assertEqual(bytes(self.u.mem_read(self.bank,8192)),before);self.assertEqual(self.get(self.state+8),0);self.assertEqual(self.get(self.state+4),0);self.assertEqual(self.handles,{})
 def test_real_selection_cancels_without_io_and_preserves_setter_result(self):
  self.assertEqual(self.capture(),1);self.fs_calls=[];self.assertEqual(self.call('m10v_half_pair_select',0x55009000,0),42);self.assertEqual(self.setter_calls,[[0x55009000,0]]);self.assertEqual(self.fs_calls,[]);self.assertEqual(self.get(self.state+12),3)
  self.assertEqual(self.call('m10v_half_pair_select',0x55009000,6),42);self.set_pixels(90,100,130);self.assertEqual(self.capture(),1);self.assertEqual(next(iter(self.files.values()))[40],90)
 def test_selection_cancel_during_io_is_not_lost_by_completion(self):
  self.assertEqual(self.capture(),1);self.cancel_during_read=True;self.set_pixels(90,100,130);self.assertEqual(self.capture(),2);self.assertEqual(self.get(self.state+12),2)
  # The native owner recreates its descriptors for the next capture.
  for off in (0x70,0xb0,0x110):self.words(self.recipe+off,*self.descriptor)
  self.cancel_during_read=False;self.set_pixels(30,80,150);self.assertEqual(self.capture(),1);self.assertEqual(next(iter(self.files.values()))[40],30)
 def test_owner_destroy_closes_entry_and_drains_busy_before_delete(self):
  self.put(self.state+4,1);self.call('m10v_half_pair_destroy',self.owner);self.assertEqual(self.sleeps,[1]);self.assertEqual(self.get(self.state),0);self.assertEqual(self.get(self.state+4),2);self.fs_calls=[];self.assertEqual(self.capture(),-10);self.assertEqual(self.fs_calls,[])
 def test_failed_mode_cancel_reset_must_retry_before_pair(self):
  self.assertEqual(self.capture(),1);self.call('m10v_half_pair_select',0x55009000,0);self.fail_write=True;self.assertEqual(self.capture(),-12);self.assertEqual(self.get(self.state+8),0);self.fail_write=False;self.set_pixels(90,100,130);self.assertEqual(self.capture(),1)
 def test_unaligned_native_bank_and_cropped_visible_footprint(self):
  # A four-byte-aligned pool token is legal; original layout aligns its canvas.
  # The final C visible byte fits, although C+pitch*allocated_rows does not.
  self.put(self.recipe+0x304,self.bank+4);self.put(self.recipe+0x364,8188)
  d=[1,self.bank+64,self.bank+8180,0,2|(2<<16),4|(2<<16),0,2]
  for off in (0x70,0xb0,0x110):self.words(self.recipe+off,*d)
  self.u.mem_write(self.bank+64,bytes([20,21,0,0,22,23]));self.u.mem_write(self.bank+8180,bytes([70,180,0,0,71,181]))
  self.assertEqual(self.capture(),1);self.assertEqual(next(iter(self.files.values()))[40:],bytes([20,21,22,23,70,180,71,181]))
  self.u.mem_write(self.bank+64,bytes([90,91,0,0,92,93]));self.u.mem_write(self.bank+8180,bytes([100,130,0,0,101,131]));self.assertEqual(self.capture(),2)
  out=struct.unpack('<8I',self.u.mem_read(self.recipe+0xb0,32));self.assertEqual(out[1],self.bank+64);self.assertEqual(bytes(self.u.mem_read(out[1],4)),bytes([20,21,90,91]))
 def test_original_arm_backresize_geometry_matches_reported_camera_address(self):
  import sys
  sys.path.insert(0,str(ROOT/'scripts'))
  from border_backresize_contract import probe_backresize
  from scripts.probe_gr3_border_encoded_bank import setup,RECIPE
  rom=(ROOT/'builds/gr3-extension-validation/official-rtos.bin').read_bytes()
  raw_bank=0x6211a928
  p=setup(rom,0,6000,4000);p.u.mem_write(RECIPE+0x252,struct.pack('<H',6144));p.call(0x5350d7e8,RECIPE,5,raw_bank)
  source=p.read_words(RECIPE+0x70,8)
  result=probe_backresize(rom,(2992,4000),6144,source_planes=tuple(source[1:3]))
  final=result['main_after'];self.assertEqual(final['planes'][0],0x621f2f20);self.assertEqual(final['geometry'],[2992,4000,6144,4000,0,0]);self.assertEqual(result['assertions'],[])
  # Execute our adapter using ORIGINAL computed addresses; stop at unavailable
  # FS before reading any photo bytes. Stage-6 proves topology was admitted.
  self.u.mem_map(0x62000000,0x8000000)
  self.put(self.recipe+0x304,raw_bank);self.put(self.recipe+0x364,74907648)
  desc=[1,*final['planes'],2992|(4000<<16),6144|(4000<<16),0,2]
  for off in (0x70,0xb0,0x110):self.words(self.recipe+off,*desc)
  self.put(self.state+8,1);self.put(0x55001014,0)
  self.assertEqual(self.capture(),-6)
  self.assertTrue(any(e[0]==218 and e[2]==0xfffffffa for e in self.events))
 def test_original_arm_sensor_capacity_includes_4064_rows(self):
  from scripts.probe_gr3_border_encoded_bank import setup,RECIPE
  rom=(ROOT/'builds/gr3-extension-validation/official-rtos.bin').read_bytes()
  expected={4000:73728000,4064:74907648}
  for sensor_rows,capacity in expected.items():
   p=setup(rom,0,6000,4000);p.u.mem_write(RECIPE+0x5004,struct.pack('<H',sensor_rows));p.u.mem_write(RECIPE+0x252,struct.pack('<H',6144));p.call(0x53510cec,RECIPE)
   self.assertEqual(p.call(0x5350d47c,RECIPE,5),capacity);self.assertEqual(capacity,3*6144*sensor_rows);self.assertEqual(p.assertions,[])
 def configure_actual_device_bank(self,width=2,height=2):
  old=bytes(self.u.mem_read(self.recipe,0x7000));self.u.mem_map(0x5c000000,0x100000);self.recipe=0x5c000028;self.context=self.recipe+0x9b8;self.u.mem_write(self.recipe,old)
  for off,value in ((0x30,self.recipe+0x1a8),(0x3c,self.recipe+0xb0),(0x40,self.recipe+0xd0),(0x44,self.recipe+0xf0),(0x48,self.recipe+0x110),(0x4c,self.recipe+0x130)):self.put(self.context+off,value)
  self.u.mem_map(0x62000000,0x8000000);self.bank=0x6211a940;self.scratch=0x68000000
  self.put(self.recipe+0x304,self.bank);self.put(self.recipe+0x364,74907648)
  self.descriptor=[1,0x621f2f20,0x63a3af60,0,width|(height<<16),6144|(4000<<16),0,2]
  for off in (0x70,0xb0,0x110):self.words(self.recipe+off,*self.descriptor)
  self.put(self.recipe+0x60,0xa2aeca70);self.put(self.recipe+0x230,0x55005000);self.u.mem_write(0x55005000,struct.pack('<HH',6144,4064))
  # Deliberately leave sensor-info pointer UNMAPPED; admission consumes only
  # the native allocation receipt and never dereferences released metadata.
  self.put(self.recipe+0x23c,0x90000000)
 def test_actual_capacity_owner_and_cropped_addresses_complete_two_shots(self):
  self.configure_actual_device_bank();y,c=self.descriptor[1:3]
  self.u.mem_write(y,bytes([20,21]));self.u.mem_write(y+6144,bytes([22,23]));self.u.mem_write(c,bytes([70,180]));self.u.mem_write(c+6144,bytes([71,181]))
  self.assertEqual(self.capture(),1);record=next(iter(self.files.values()));self.assertEqual(record[40:],bytes([20,21,22,23,70,180,71,181]))
  self.u.mem_write(y,bytes([90,91]));self.u.mem_write(y+6144,bytes([92,93]));self.u.mem_write(c,bytes([100,130]));self.u.mem_write(c+6144,bytes([101,131]))
  self.assertEqual(self.capture(),2);out=struct.unpack('<8I',self.u.mem_read(self.recipe+0xb0,32));self.assertEqual(out[1],0x6211a940);self.assertEqual(bytes(self.u.mem_read(out[1],4)),bytes([20,21,90,91]));self.assertEqual(self.freed,[0x68000000]);self.assertEqual(self.handles,{})
 def test_exact_full_device_descriptor_and_released_metadata_reach_transaction(self):
  self.configure_actual_device_bank(2992,4000);self.put(self.recipe+0x60,0);self.put(self.recipe+0x230,0x90000004);self.put(self.state+8,1);self.put(0x55001014,0)
  self.assertEqual(self.capture(),-6)
  self.assertTrue(any(e==[219,0x6211a940,74907648,0x621f2f20,0x63a3af60] for e in self.events))
  self.assertTrue(any(e==[220,self.recipe,2992|(4000<<16),6144|(4000<<16),0] for e in self.events))
 def test_oversized_unowned_capacity_is_rejected_before_pixels_or_io(self):
  self.put(self.recipe+0x364,3*6144*4064+4);self.put(self.state+8,1);self.assertEqual(self.capture(),-3);self.assertFalse(self.allocations)
 def test_original_native_preview_and_jpeg_setup_pass_every_admission_guard(self):
  import sys
  sys.path.insert(0,str(ROOT/'scripts'))
  from border_backresize_contract import fragment,image
  from scripts.probe_gr3_border_encoded_bank import setup,RECIPE,SI
  rom=(ROOT/'builds/gr3-extension-validation/official-rtos.bin').read_bytes()
  p=setup(rom,0,6000,4000)
  # Execute the actual original constructor fragment that initializes all
  # image formats, layout tags and reserved fields. Do not fabricate tag2.
  fragment(p,0x5350f1d4,0x5350f3f0,{'r4':RECIPE,'r5':0})
  p.words(RECIPE+0x5c,RECIPE+0x6000)
  p.u.mem_write(RECIPE+0x252,struct.pack('<H',6144));p.u.mem_write(RECIPE+0x5004,struct.pack('<H',4064))
  # Encoded sizing uses the original full-aspect policy, matching the paired
  # candidate's separately checked encoded-only query adapter.
  p.call(0x53510cec,RECIPE);p.call(0x5350d7e8,RECIPE,4,0x60000000);p.call(0x5350d7e8,RECIPE,5,0x6211a940)
  module,config=0x55200000,0x55210000
  p.words(config+0x30,RECIPE+0x1a8,SI,RECIPE+0x6000,RECIPE+0x70,RECIPE+0xb0,RECIPE+0x90,RECIPE+0xd0,RECIPE+0xf0,0x72000000,0x73000000,0)
  p.words(module+0x8a0c,0x55250000);p.u.mem_write(SI+0xb38,struct.pack('<HH',2992,4000));p.u.mem_write(SI+0x7b6,b'\6')
  def dims():
   p.u.mem_write(p.u.reg_read(p.A.UC_ARM_REG_R3),struct.pack('<H',2992));p.u.mem_write(p.read_words(p.u.reg_read(p.A.UC_ARM_REG_SP),1)[0],struct.pack('<H',4000))
  def margins():
   for n in (2,3):p.u.mem_write(p.u.reg_read(getattr(p.A,f'UC_ARM_REG_R{n}')),b'\0\0')
  def thumb():
   p.u.mem_write(p.u.reg_read(p.A.UC_ARM_REG_R1),struct.pack('<H',160));p.u.mem_write(p.u.reg_read(p.A.UC_ARM_REG_R2),struct.pack('<H',120))
  # Only private Half size/margins and RTOS transport/cache/wait leaves are
  # doubles. Constructor, allocation layout, crop, alias and Setup6 run ARM.
  p.boundaries={0x536a2a30:dims,0x536a2f50:margins,0x536a3008:margins,0x536a2f10:thumb,0x536abd28:lambda:0,0x536a9dd4:lambda:0,0x536a9e8c:lambda:1,0x536bbc30:lambda:0,0x536bbcc0:lambda:0}
  p.call(0x534ff294,module,config,0);p.call(0x5350e624,RECIPE,6)
  self.assertEqual(p.assertions,[])
  views={hex(off):image(p,RECIPE+off) for off in (0x70,0xb0,0xd0,0xf0,0x110)}
  self.assertEqual(views['0xd0']['geometry'],[720,480,720,480,0,0]);self.assertEqual(views['0xf0']['geometry'],[160,120,160,120,0,0])
  for off in ('0x70','0xb0','0xd0','0xf0','0x110'):self.assertEqual((views[off]['format'],views[off]['layout']),(1,2))
  self.assertEqual(views['0xb0']['planes'],[0x621f2f20,0x63a3af60,0])
  self.configure_actual_device_bank(2992,4000)
  for off in (0x70,0xb0,0xd0,0xf0,0x110):self.u.mem_write(self.recipe+off,bytes(p.u.mem_read(RECIPE+off,32)))
  self.u.mem_write(self.recipe+0x130,bytes(p.u.mem_read(RECIPE+0x130,24)))
  self.put(self.state+8,1);self.put(0x55001014,0)
  self.assertEqual(self.capture(),-6)
  self.native_report={'descriptors':views,'jpeg_control130':p.read_words(RECIPE+0x130,6),'native_assertions':p.assertions,'adapter_result':-6,'stop_boundary':'deliberately unavailable FS, after every geometry/RAW/preview/JPEG guard','original_execution':'descriptor constructor5350f1d4..5350f3f0; query53510cec; setters5350d7e8; BackResize534ff294; Setup6via5350e624','doubles':'Half resolution/margins; thumbnail size query; RTOS submit/wait/cache; FS/pool admission','hardware_executed':False}
 def test_pair_status_does_not_depend_on_full_recipe_diagnostic_ring(self):
  self.put(self.recipe+0x477c,32);self.put(self.recipe+0x4780,99)
  self.assertEqual(self.capture(),1);self.assertTrue(any(e[:3]==[218,self.recipe,1] for e in self.events))
 def test_nonhalf_capture_cancels_pending_once_then_zero_work(self):
  self.assertEqual(self.capture(),1);self.u.mem_write(self.si+0x7b6,b'\0');self.assertEqual(self.capture(),3);self.fs_calls=[];self.assertEqual(self.capture(),0);self.assertEqual(self.fs_calls,[])
if __name__=='__main__':unittest.main()
