"""Current ten-slot Live ABI with actual native Make and native phase dispatcher.

The stock tuning registers/curve packer execute ARM. No display/IIP DMA pixels
or task scheduler is simulated. Candidate fixture is the known failed r4 image;
only the current source Live wrapper is rebuilt on its audited native exports.
"""
import hashlib,json,os,struct,tempfile,unittest,zlib
from pathlib import Path
from unicorn import UC_HOOK_CODE
from unicorn import arm_const as A
from scripts.build_gr3_isp_recipe_color import build
from tests.test_gr3_isp_base import StockISP,ROOT

class CurrentLiveColorTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  final=os.environ.get('M10V_LIVE_FINAL')
  folder=Path(final or os.environ.get('M10V_LIVE_CANDIDATE',ROOT/'builds/gr3-half-frame-r4-debug-final-20261030'))
  cls.manifest=json.loads((folder/'manifest.json').read_text());cls.original=(ROOT/'builds/gr3-extension-validation/official-rtos.bin').read_bytes()
  cls.failed=(folder/'final-rtos.bin').read_bytes()
  if final:
   cls.live=cls.manifest['capture_lifecycle']['snapshot'];cls.image=cls.failed
   cls.entry=next(p['entry']for p in cls.live['patches']if p['address']==0x53dbd954)
   assert struct.unpack_from('<I',cls.image,0x53dbd954-0x53000000)[0]==cls.entry
   base=cls.manifest['base']-0x53000000;size=cls.manifest['code_bytes']
   assert hashlib.sha256(cls.image[base:base+size]).hexdigest()==cls.manifest['code_sha256']
  else:
   cls.temp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.temp.cleanup)
   code,cls.live=build(cls.temp.name,cls.original,cls.manifest['symbols'],cls.manifest['capture_lifecycle']['owner'],base=0x54800000,observer=False,producer_snapshot=True,native_color=True,live_color=True,appended_slots=True)
   image=bytearray(cls.failed);at=cls.live['base']-0x53000000;image.extend(bytes(max(0,at+len(code)-len(image))));image[at:at+len(code)]=code
   patch=next(p for p in cls.live['patches']if p['address']==0x53dbd954);cls.entry=patch['entry'];struct.pack_into('<I',image,patch['address']-0x53000000,cls.entry);cls.image=bytes(image)

 def fixture(self,film):
  e=StockISP(self.image);e.make(25,1,True,actual_live=True);obj=0x60000000;f=0x60001400
  owner=e.alloc(self.manifest['settings_menu']['owner_bytes']);e.w32(0x55063910,1);e.w32(0x55063988,owner);e.w32(owner+0x213c,0x3856504d);e.w32(owner+0x2140,2)
  state=bytearray(184);struct.pack_into('<IHHI',state,0,0x5630314d,5,184,7);struct.pack_into('<H6B',state,12,film,0,0,0,3,5,2);struct.pack_into('<I',state,180,zlib.crc32(state[:180]));e.u.mem_write(owner+0x2144,bytes(state))
  # Native5365c13c dispatch reads message+268 and chooses tuning+48 for1/2.
  worker=e.alloc(0x64);message=e.alloc(0x26c);e.w32(worker+0x48,obj);e.w32(message+0x268,f)
  e.w32(worker+0x44,0);e.w32(worker+0x50,0)
  hits=[];peak=[0x5effff00]
  def observe(u,at,n,data):
   peak[0]=min(peak[0],u.reg_read(A.UC_ARM_REG_SP))
   if at in (self.live['exports']['m10v_isp_native_look_apply'],0x5383c8a8,0x536af2a8,0x536af31c,0x536a27e8,0x535847d8,0x53828014):hits.append(at)
  e.u.hook_add(UC_HOOK_CODE,observe)
  return e,obj,f,worker,message,hits,peak
 def dispatch(self,e,frame,worker,message,phase):
  e.u.mem_write(frame+0x82ac,bytes([phase]));e.w32(message+0x268,frame);e.call(0x5365c13c,worker,message)
 def banks(self,e,f):
  # Exclude phase selector/SI pointer; compare all ISP color parameter banks.
  return bytes(e.u.mem_read(f+0x120,0x5088-0x120))
 def test_native_dispatch_stage1_and_stage2_both_apply_same_selected_color(self):
  for film,independent,ratio,first_phase in __import__('itertools').product((35,317),(False,True),(0,2,6),(1,2)):
    with self.subTest(film=film,independent=independent,ratio=ratio,first_phase=first_phase):
     e,obj,f,worker,message,hits,peak=self.fixture(film);si=struct.unpack('<I',e.u.mem_read(f+0x82d0,4))[0];e.u.mem_write(si+0x71248+0x7b6,bytes([ratio]));second=e.alloc(0x9000)if independent else f
     if independent:e.u.mem_write(second,bytes(e.u.mem_read(f,0x9000)))
     expected=None
     for iteration in range(6):
      frame=second if iteration%2 else f;phase=3-first_phase if iteration%2 else first_phase
      self.dispatch(e,frame,worker,message,phase)
      if expected is None:expected=self.banks(e,frame)
      self.assertEqual(hashlib.sha256(self.banks(e,frame)).hexdigest(),hashlib.sha256(expected).hexdigest(),(film,independent,phase,iteration))
     self.assertEqual(hits.count(self.live['exports']['m10v_isp_native_look_apply']),6)
     self.assertFalse(any(a in hits for a in(0x5383c8a8,0x536af2a8,0x536af31c,0x536a27e8,0x535847d8,0x53828014)),hits)
     self.assertEqual(e.assertions,[])
     # Original ImageDevelopmentPipe task0x3a reserves10KiB; this bound
     # covers dispatcher+wrapper only, not scheduler/caller overhead.
     self.assertLessEqual(0x5effff00-peak[0],10240)
 def test_original_noncarrier_live_modes_preserve_stock_banks_and_shooting_metadata(self):
  for tone in (11,13,17,22):
   for phase in(1,2):
    e,obj,f,worker,message,hits,peak=self.fixture(317)
    si=struct.unpack('<I',e.u.mem_read(f+0x82d0,4))[0];e.u.mem_write(si+0x71248+0x77c,bytes([tone]));e.u.mem_write(f+0x82ac,bytes([phase]))
    shooting=bytes(e.u.mem_read(si,0x80000));frame=bytes(e.u.mem_read(f,0x9000));tuning=bytes(e.u.mem_read(obj,0x400))
    e.call(0x536ddecc,obj,f);expected=self.banks(e,f)
    e.u.mem_write(f,frame);e.u.mem_write(obj,tuning);e.call(self.entry,obj,f)
    self.assertEqual(self.banks(e,f),expected);self.assertEqual(bytes(e.u.mem_read(si,0x80000)),shooting)
    self.assertNotIn(self.live['exports']['m10v_isp_native_look_apply'],hits)
 def test_non_live_phases_and_foreign_tuning_are_untouched_by_helpers(self):
  for phase in(0,3,255):
   e,obj,f,*_=self.fixture(317);e.u.mem_write(f+0x82ac,bytes([phase]));si=struct.unpack('<I',e.u.mem_read(f+0x82d0,4))[0];e.u.mem_write(si+0x77c,b'\x19');before=bytes(e.u.mem_read(f,0x9000));tuning=bytes(e.u.mem_read(obj,0x400))
   for name in('m10v_isp_frame_live_prepare','m10v_isp_frame_live_color'):e.call(self.live['exports'][name],obj,f)
   self.assertEqual(bytes(e.u.mem_read(f,0x9000)),before);self.assertEqual(bytes(e.u.mem_read(obj,0x400)),tuning)
  e,obj,f,*_=self.fixture(317);e.w32(obj,0x53dbd8a0);before=bytes(e.u.mem_read(f,0x9000));e.call(self.live['exports']['m10v_isp_frame_live_color'],obj,f);self.assertEqual(bytes(e.u.mem_read(f,0x9000)),before)
if __name__=='__main__':unittest.main()
