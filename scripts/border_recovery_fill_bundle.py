#!/usr/bin/env python3
"""Bounded Fill bundle contract, original public enqueue/dispatcher, no pixels."""
import struct,unittest
from border_recovery_public_fill import PublicFill as _Public
from border_recovery_installer import InstalledRoutesGr3x as _InstalledX
from border_recovery_wait_guard import WaitGuard as _Wait
from border_recovery_contract import A
TAG=0x42464231
class FillBundle(unittest.TestCase):
 reg=_Wait.reg;put=_Wait.put;word=_Wait.word;call=_Wait.call;invoke=_Wait.invoke
 patch_bl=_Public.patch_bl;configure_other_owner=_Wait.configure_other_owner
 @classmethod
 def setUpClass(cls):_Public.setUpClass.__func__(cls)
 def setUp(self):
  _Public.setUp(self);self.bundle=0x55030000;self.descriptors=0x55032000
  self.put(self.client+36,0);self.put(self.worker+0x64,0)
  self.queue_calls=0;self.original_fill_calls=[];self.lower_packets=[]
  self.stop_at_yield=False;self.real_fill=True
  self.stubs.update({0x536a848c:1,0x536a8544:1,0x536a2954:0,0x536a29b4:0})
 def hook(self,u,pc,size,data):
  if pc==0x5376a370:self.lower_frame=u.reg_read(A.UC_ARM_REG_FP)
  if pc==0x536abd28:self.queue_calls+=1
  if pc==0x5365900c:
   self.original_fill_calls.append(bytes(u.mem_read(self.reg(1),12)))
   if not self.real_fill:
    u.reg_write(A.UC_ARM_REG_R0,0);u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR));return
  if pc==0x53769a78 and not getattr(self,'execute_inner',False):
   self.lower_packets.append(bytes(u.mem_read(self.reg(1),0x22)))
   u.reg_write(A.UC_ARM_REG_R0,0);u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR));return
  return _Wait.hook(self,u,pc,size,data)
 def make_bundle(self,count):
  self.put(self.bundle,TAG,count,12+count*12)
  for i in range(count):
   d=self.descriptors+i*32;raw=bytearray(32);raw[0]=0
   # Tokens stay UNMAPPED; independent shifted planes/rect dimensions.
   struct.pack_into('<3I',raw,4,0x70000000+i*64,0x74000000+i*64,0x78000000+i*64)
   struct.pack_into('<6H',raw,0x10,16+i,8,512,128,i,2)
   self.u.mem_write(d,bytes(raw))
   self.u.mem_write(self.bundle+12+i*12,struct.pack('<I4H',d,16+i,128+i,129+i,0))
 def start(self):
  self.stop_at_yield=True
  self.invoke(self.symbols['m10v_border_fill_bundle_submit'],(self.client,self.bundle))
 def dispatch_and_resume(self):
  waiting=self.u.context_save();self.stop_at_yield=False
  self.invoke(0x5365935c,(self.worker,self.enqueued_job),0x550dd000)
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x550ff000)
  self.u.context_restore(waiting);self.u.reg_write(A.UC_ARM_REG_R0,0)
  self.u.reg_write(A.UC_ARM_REG_PC,self.u.reg_read(A.UC_ARM_REG_LR))
  self.u.emu_start(self.u.reg_read(A.UC_ARM_REG_PC),0x550ff000,count=1000000)
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x550ff000)
 def test_bundle_full_public_route_one_enqueue_one_notify_distinct_rectangles_and_colors(self):
  self.make_bundle(3);self.start()
  self.assertEqual(self.queue_calls,1);self.assertEqual(self.original_fill_calls,[])
  self.assertEqual(self.word(self.word(self.enqueued_job+8)),self.bundle)
  self.assertEqual(self.word(self.client+36),1)
  self.dispatch_and_resume();self.assertEqual(self.reg(0),1)
  self.assertEqual(self.queue_calls,1);self.assertEqual(len(self.signal_state),1)
  self.assertEqual(self.word(self.client+44),1)
  self.assertEqual(len(self.original_fill_calls),3);self.assertEqual(len(self.lower_packets),3)
  for i,(params,packet) in enumerate(zip(self.original_fill_calls,self.lower_packets)):
   self.assertEqual(struct.unpack('<I4H',params),(self.descriptors+i*32,16+i,128+i,129+i,0))
   self.assertEqual(struct.unpack_from('<3H',packet,0x1c),(16+i,128+i,129+i))
   self.assertEqual(struct.unpack_from('<3I',packet,4),(0x70000000+i*64,0x74000000+i*64,0x78000000+i*64))
  self.assertNotIn(0x534ab1a4,self.visited);self.assertNotIn(0x534ab60c,self.visited)
 def test_maximum_132_bounded_rectangles_one_queue_no_pixel_access(self):
  self.make_bundle(132);self.real_fill=False;self.start();self.dispatch_and_resume()
  self.assertEqual(len(self.original_fill_calls),132);self.assertEqual(self.queue_calls,1)
  self.assertEqual(len(self.signal_state),1);self.assertEqual(self.reg(0),1)
 def test_invalid_header_count_extent_or_last_descriptor_reject_before_pending_or_queue(self):
  for field,value in ((0,0),(4,0),(4,133),(8,12),(12,0),(12,3)):
   self.make_bundle(2);self.put(self.client+36,0);self.put(self.bundle+field,value)
   self.assertEqual(self.call(self.symbols['m10v_border_fill_bundle_submit'],self.client,self.bundle),0)
   self.assertEqual(self.word(self.client+36),0);self.assertEqual(self.queue_calls,0)
  self.make_bundle(2);self.put(self.bundle+24,0)
  self.assertEqual(self.call(self.symbols['m10v_border_fill_bundle_submit'],self.client,self.bundle),0)
  self.assertEqual(self.queue_calls,0)
 def test_corruption_after_enqueue_fatally_retains_without_callback_or_body(self):
  self.make_bundle(2);self.start();self.put(self.bundle+4,133)
  self.invoke(0x5365935c,(self.worker,self.enqueued_job),0x550dd000)
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x536b0a74)
  self.assertEqual(self.original_fill_calls,[]);self.assertEqual(self.signal_state,[])
  self.assertEqual(self.word(self.client+36),1)
 def test_failed_inner_wait_keeps_bundle_public_worker_and_rectangle_frames(self):
  self.make_bundle(2);self.start();outer=self.u.context_save()
  outer_sp=self.u.reg_read(A.UC_ARM_REG_SP);outer_bytes=bytes(self.u.mem_read(outer_sp,0x550fd000-outer_sp))
  self.execute_inner=True;self.put(self.worker+0x44,0x55007000)
  self.u.reg_write(A.UC_ARM_REG_C1_C0_2,0xf00000);self.u.reg_write(A.UC_ARM_REG_FPEXC,0x40000000)
  self.stubs.update({0x5377079c:0,0x5376ebd0:0,0x5376eb14:0,
   0x5376b8bc:0,0x5377448c:0,0x5376eafc:0,0x5376e55c:0,0x5377077c:0})
  self.invoke(0x5365935c,(self.worker,self.enqueued_job),0x550dd000)
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x536b0a74)
  self.assertEqual(len(self.original_fill_calls),1);self.assertEqual(self.signal_state,[])
  self.assertEqual(self.word(self.worker+0x64),1)
  self.assertEqual(self.word(self.client+36),1)
  self.assertNotIn(0x5376a38c,self.visited)
  # Outer frame remains paused in real native public Fill/common wait.
  self.assertEqual(bytes(self.u.mem_read(outer_sp,len(outer_bytes))),outer_bytes)
  self.assertEqual(self.word(self.lower_frame-4),0x53659258)
  self.assertEqual(self.word(self.lower_frame-36),self.worker)
  self.assertLess(self.u.reg_read(A.UC_ARM_REG_SP),0x550dd000)
 def test_stock_client_remains_original_single_fill_even_with_bundle_tag_destination(self):
  self.make_bundle(1);self.real_fill=False
  self.call(0x534aacc8,self.client) # original 32-byte-vtable identity
  params=0x55035000;self.put(params,self.bundle,0,0)
  self.put(self.job+4,self.client);self.put(self.job+8,params,0x010e0004)
  self.invoke(0x5365935c,(self.worker,self.job),0x550dd000)
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x550ff000)
  self.assertEqual(len(self.original_fill_calls),1)
  self.assertEqual(self.word(self.client+36),0)
class FillBundleGr3x(FillBundle):
 @classmethod
 def setUpClass(cls):_InstalledX.setUpClass.__func__(cls)
if __name__=='__main__':unittest.main(defaultTest=['FillBundle','FillBundleGr3x'],verbosity=2)
