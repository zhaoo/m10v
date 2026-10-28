#!/usr/bin/env python3
"""Original public Fill ABI -> native queue -> worker completion, no pixel buffers.
All kernel queue/signal endpoints are doubles. No hardware or scheduler proof.
"""
import struct,unittest
from border_recovery_installer import InstalledRoutes as _Installed,InstalledRoutesGr3x as _InstalledX
from border_recovery_wait_guard import WaitGuard as _Wait
from border_recovery_contract import A,ROOT
from analyze_gr3_border_iip import probe_fill_driver,OriginalArm
def probe_fill_roi(rom,width,height,left,top,stride=6336,allocation_rows=4640,fmt=0,trace_spf=False):
 """Original Fill->packet->GPC/Store construction; no mapped pixel planes."""
 p=OriginalArm(rom);context,args,descriptor=0x55080000,0x55081000,0x55082000
 bases=(0x70000000,0x74000000,0 if fmt in (1,2) else 0x78000000)
 p.words(descriptor,fmt);p.words(descriptor+4,*bases)
 p.u.mem_write(descriptor+0x10,struct.pack('<6H',width,height,stride,allocation_rows,left,top))
 p.words(args,descriptor);p.u.mem_write(args+4,struct.pack('<3H',255,128,128));packets=[]
 def packet():packets.append(bytes(p.u.mem_read(p.u.reg_read(p.A.UC_ARM_REG_R1),0x22)))
 p.boundaries={0x536a848c:lambda:1,0x536a8544:lambda:1,0x53769a78:packet}
 p.call(0x5365900c,context,args);results=[]
 for raw in packets:
  q=OriginalArm(rom);q.u.mem_write(args,raw)
  saved=[]
  record={'packet_format':raw[0], 'packet_layout':raw[1],
          'packet_planes':struct.unpack_from('<3I',raw,4),
          'packet_geometry':struct.unpack_from('<6H',raw,0x10)}
  def gpc():
   config=q.u.reg_read(q.A.UC_ARM_REG_R1)
   planes=[q.read_words(config+off,1)[0] for off in (0x20,0x30,0x40)]
   record['gpc_constants']=[q.read_words(plane+0x44,1)[0] for plane in planes]
  def store():
   config=q.u.reg_read(q.A.UC_ARM_REG_R1);info=q.read_words(config+0x50,1)[0]
   record['store_origin']=struct.unpack('<2H',q.u.mem_read(config+0xa,4))
   record['store_size']=struct.unpack('<2H',q.u.mem_read(config+0x1c,4))
   record['store_stride']=q.read_words(info+0x1c,1)[0]
   record['store_layout']=q.u.mem_read(info+6,1)[0]
   record['store_pixel_format']=q.u.mem_read(info+8,1)[0]
   record['store_info_size']=struct.unpack('<2H',q.u.mem_read(info+0x20,4))
   record['store_planes']=tuple(q.read_words(info+0x24,3))
   if trace_spf:saved.append((bytes(q.u.mem_read(config,0x54)),bytes(q.u.mem_read(info,0x40))))
  q.boundaries={0x5377079c:lambda:0,0x5376ebd0:lambda:0,0x5376eb14:lambda:0,
   0x5376b8bc:gpc,0x5377448c:store,0x5376eafc:lambda:0,0x536a9dd4:lambda:0,
   0x5376e55c:lambda:0,0x536a9e8c:lambda:1,0x5376ed74:lambda:0,0x5377077c:lambda:0}
  q.call(0x53769a78,context,args);record['lower_assertions']=list(q.assertions)
  if trace_spf:
   service,root,regs,cfg,info=0x55083000,0x55084000,0x55085000,0x55086000,0x55087000
   q.u.mem_write(cfg,saved[0][0]);q.u.mem_write(info,saved[0][1]);q.words(cfg+0x50,info)
   q.words(service+0x28,root);q.words(root+0x14,regs)
   q.boundaries={0x536ae71c:lambda:1,0x536ae870:lambda:1}
   q.call(0x53773c58,service,cfg)
   record['spf_layout']=(q.read_words(regs,1)[0]>>8)&15
   frame=q.read_words(regs+0x20,1)[0]
   record['spf_frame']=(frame&0x7fff,(frame>>16)&0x3fff)
   record['spf_strides']=q.read_words(regs+0x10,3)
   record['spf_planes']=q.read_words(regs+0x24,3)
   record['spf_assertions']=list(q.assertions)
  results.append(record)
 return {'requests':results,'pipe_assertions':p.assertions,'pixels_mapped':False}
def probe_low_cache_spans(rom,fmt,stride,rows):
 """Execute native pre/post span arithmetic; cache backends only are doubles."""
 p=OriginalArm(rom);d=0x55082000;p.words(d,fmt);p.words(d+4,0x70000000,0x74000000,0)
 p.u.mem_write(d+0x10,struct.pack('<6H',stride,rows,stride,rows,0,0))
 result={'pre':[],'post':[]}
 def record(kind):
  result[kind].append((p.u.reg_read(p.A.UC_ARM_REG_R1),p.u.reg_read(p.A.UC_ARM_REG_R2)))
 p.boundaries={0x536bbc30:lambda:0x55083000,0x536bbc3c:lambda:record('pre'),0x536bbcc0:lambda:record('post')}
 p.call(0x534ab1a4,0,d);p.call(0x534ab60c,0,d);result['assertions']=p.assertions
 return result
class PublicFill(unittest.TestCase):
 reg=_Wait.reg;put=_Wait.put;word=_Wait.word;call=_Wait.call;invoke=_Wait.invoke
 patch_bl=_Installed.patch_bl;configure_other_owner=_Wait.configure_other_owner
 @classmethod
 def setUpClass(cls):_Installed.setUpClass.__func__(cls)
 def setUp(self):
  _Installed.setUp(self)
  self.factory=0x55008000;self.destination=0x55009000
  self.configure_other_owner('fill');self.put(self.factory+4,self.worker)
  self.stubs[0x53658a68]=self.factory
  self.observed_packet=None
 def hook(self,u,pc,size,data):
  if pc==0x53769a78:
   self.observed_packet=bytes(u.mem_read(self.reg(1),0x22))
   u.reg_write(A.UC_ARM_REG_R0,0);u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR));return
  return _Wait.hook(self,u,pc,size,data)
 def run_public(self,y,cb,cr):
  # Pixel address tokens deliberately unmapped. Only native descriptor is RAM.
  raw=bytearray(0x20);raw[0]=0
  struct.pack_into('<3I',raw,4,0x70000000,0x74000000,0x78000000)
  struct.pack_into('<6H',raw,0x10,160,120,192,128,4,6)
  self.u.mem_write(self.destination,bytes(raw));self.stop_at_yield=True
  self.invoke(0x534abc18,(self.client,self.destination,y,cb,cr,1))
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x536b0a74)
  self.assertEqual(self.word(self.client+36),1)
  job=self.enqueued_job;params=self.word(job+8)
  self.assertEqual(self.word(job+4),self.client)
  self.assertEqual(self.word(job+12),0x010e0004)
  self.assertEqual(self.word(params),self.destination)
  self.assertEqual(struct.unpack('<3H',self.u.mem_read(params+4,6)),(y&65535,cb&65535,cr&65535))
  self.assertEqual(self.waits[-1],(self.client+4,0x10,0xffffffff))
  self.assertNotIn(0x534ab1a4,self.visited);self.assertNotIn(0x534ab60c,self.visited)
  return job,params
 def test_public_fill_queue_original_body_constants_and_native_completion_retention(self):
  job,params=self.run_public(0x1234,0x5678,0x9abc)
  paused=self.u.context_save();sp=self.u.reg_read(A.UC_ARM_REG_SP)
  held=bytes(self.u.mem_read(sp,0x550fd000-sp))
  self.stop_at_yield=False
  # Execute original small-frame body until the IIP function boundary.
  self.stubs.update({0x536a848c:1,0x536a8544:1})
  self.invoke(0x5365900c,(self.worker,params),0x550dd000)
  packet=self.observed_packet;self.assertIsNotNone(packet)
  self.assertEqual(struct.unpack_from('<3I',packet,4),(0x70000000,0x74000000,0x78000000))
  self.assertEqual(struct.unpack_from('<3H',packet,0x1c),(0x1234,0x5678,0x9abc))
  # Execute ORIGINAL OnMessage and wrapped notify; body endpoint doubled only
  # here to avoid executing hardware start. Full event + mask verified.
  self.observe_other_body=True;self.body_calls=0
  self.stubs.update({0x536a2954:0,0x536a29b4:0})
  self.invoke(0x5365935c,(self.worker,job),0x550dd000)
  self.assertEqual(self.body_calls,1)
  self.assertEqual(self.signal_state,[(1,1,self.client+4,0x10)])
  self.assertEqual(self.word(self.client+36),0);self.assertEqual(self.word(self.client+40),0)
  self.assertEqual(bytes(self.u.mem_read(sp,len(held))),held)
  self.u.context_restore(paused);self.u.reg_write(A.UC_ARM_REG_R0,0)
  self.u.reg_write(A.UC_ARM_REG_PC,self.u.reg_read(A.UC_ARM_REG_LR))
  self.u.emu_start(self.u.reg_read(A.UC_ARM_REG_PC),0x550ff000,count=100000)
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x550ff000)
  self.assertEqual(self.call(self.symbols['m10v_border_client_destroy_if_done'],self.client),1)
 def test_public_fill_constants_are_native_halfwords_not_packed_rgb(self):
  self.run_public(0x10001,0x20002,0x30003)
 def test_original_gpc_constant_channels_preserve_three_public_argument_positions(self):
  rom=self.stock
  result=probe_fill_driver(rom,160,120,(0x1234,0x5678,0x9abc))
  self.assertEqual(result['constants'],[0x1234,0x5678,0x9abc])
  self.assertFalse(result['pixels_mapped']);self.assertFalse(result['failure_quiescence_proven'])
 def test_all_three_initialized_factory_getters_do_not_create_workers(self):
  self.u.mem_map(0x55363000,0x1000);self.u.mem_map(0x5536b000,0x2000)
  roots=((0x53658a68,0x55363278,0x5536327c,4),
         (0x5369a0e8,0x5536c018,0x5536c00c,4),
         (0x53672c48,0x5536bf6c,0x5536bf5c,12))
  for getter,guard,factory,offset in roots:
   self.stubs.pop(getter,None);self.put(guard,1);self.put(factory+offset,0)
   self.visited.clear();self.assertEqual(self.call(getter),factory)
   self.assertEqual(self.word(factory+offset),0)
   self.assertNotIn(0x536af2a8,self.visited)
   self.assertNotIn(0x53699fc4,self.visited)
   self.assertNotIn(0x53658988,self.visited)
   self.assertNotIn(0x536729ec,self.visited)
 def test_nonzero_bar_and_hole_roi_keep_plane_base_and_store_exact_coordinates(self):
  bases=(0x70000000,0x74000000,0x78000000)
  for width,height,left,top in ((160,4000,160,160),(120,180,40,100)):
   result=probe_fill_roi(self.stock,width,height,left,top)
   self.assertEqual(result['pipe_assertions'],[]);self.assertEqual(len(result['requests']),1)
   r=result['requests'][0]
   self.assertEqual(r['packet_planes'],bases);self.assertEqual(r['store_planes'],bases)
   self.assertEqual(r['packet_geometry'],(6336,height,width,height,left,top))
   self.assertEqual(r['store_origin'],(left,top));self.assertEqual(r['store_size'],(width,height))
   self.assertEqual(r['store_info_size'],(width,height));self.assertEqual(r['store_stride'],6336)
   self.assertEqual(r['gpc_constants'],[255,128,128]);self.assertEqual(r['lower_assertions'],[])
   self.assertFalse(result['pixels_mapped'])
 def test_native_large_roi_split_offsets_only_rows_and_stays_inside_target_but_logs_assert(self):
  result=probe_fill_roi(self.stock,320,4000,160,160)
  self.assertEqual(len(result['requests']),2)
  # Original code does log the tight-layout assertion for padded nonzero ROI.
  self.assertEqual(result['pipe_assertions'],[{'caller':0x53659228,'line':0x1c0}])
  intervals=[]
  for i,r in enumerate(result['requests']):
   self.assertEqual(r['store_origin'],(160,0));self.assertEqual(r['store_size'],(320,2000))
   self.assertEqual(r['packet_geometry'],(6336,2000,320,2000,160,0))
   for plane,base in zip(r['store_planes'],(0x70000000,0x74000000,0x78000000)):
    self.assertEqual(plane-base,6336*(160+2000*i))
   self.assertEqual(r['store_planes'],r['packet_planes']);self.assertEqual(r['store_stride'],6336)
   row=(r['store_planes'][0]-0x70000000)//6336+r['store_origin'][1]
   intervals.append((row,row+r['store_size'][1]))
  self.assertEqual(intervals,[(160,2160),(2160,4160)])
  # Every horizontal span is [160,480); no plane has a second x displacement.
  self.assertTrue(all(r['store_origin'][0]+r['store_size'][0]==480 for r in result['requests']))
 def test_6336_by_160_horizontal_bar_stays_below_native_split_threshold(self):
  for top in (0,4480):
   result=probe_fill_roi(self.stock,6336,160,0,top)
   self.assertEqual(result['pipe_assertions'],[]);self.assertEqual(len(result['requests']),1)
   r=result['requests'][0];self.assertEqual(r['store_origin'],(0,top))
   self.assertEqual(r['store_size'],(6336,160));self.assertEqual(r['store_planes'][0],0x70000000)
 def test_format1_interleaved_chroma_roi_bars_holes_keep_y_c_bases_and_gpc_constants(self):
  bases=(0x70000000,0x74000000,0)
  for width,height,left,top in ((160,4000,160,160),(120,180,40,100),(6336,160,0,0),(6336,160,0,4480)):
   result=probe_fill_roi(self.stock,width,height,left,top,fmt=1)
   self.assertEqual(result['pipe_assertions'],[]);self.assertEqual(len(result['requests']),1)
   r=result['requests'][0]
   self.assertEqual(r['packet_format'],0);self.assertEqual(r['packet_layout'],0)
   self.assertEqual(r['store_layout'],0);self.assertEqual(r['store_pixel_format'],0)
   self.assertEqual(r['packet_planes'],bases);self.assertEqual(r['store_planes'],bases)
   self.assertEqual(r['packet_geometry'],(6336,height,width,height,left,top))
   self.assertEqual(r['store_origin'],(left,top));self.assertEqual(r['store_size'],(width,height))
   self.assertEqual(r['store_info_size'],(width,height));self.assertEqual(r['store_stride'],6336)
   self.assertEqual(r['gpc_constants'],[255,128,128]);self.assertEqual(r['lower_assertions'],[])
 def test_small_format2_fill_native_spf_layout_and_half_chroma_cache_contract(self):
  for fmt in (1,2):
   result=probe_fill_roi(self.stock,160,120,0,0,160,120,fmt,True)
   self.assertEqual(result['pipe_assertions'],[]);self.assertEqual(len(result['requests']),1)
   r=result['requests'][0];layout=0 if fmt==1 else 2
   self.assertEqual((r['packet_format'],r['packet_layout']),(0,layout))
   self.assertEqual((r['store_pixel_format'],r['store_layout']),(0,layout))
   self.assertEqual(r['packet_planes'],(0x70000000,0x74000000,0))
   self.assertEqual(r['store_planes'],(0x70000000,0x74000000,0))
   self.assertEqual(r['store_origin'],(0,0));self.assertEqual(r['store_size'],(160,120))
   self.assertEqual(r['spf_layout'],layout);self.assertEqual(r['spf_frame'],(160,120))
   self.assertEqual(r['spf_strides'],[160,160,160]);self.assertEqual(r['spf_planes'],[0x70000000,0x74000000,0])
   self.assertEqual(r['gpc_constants'],[255,128,128]);self.assertEqual(r['spf_assertions'],[])
   cache=probe_low_cache_spans(self.stock,fmt,160,120)
   spans=[(0x70000000,19200),(0x74000000,19200 if fmt==1 else 9600)]
   self.assertEqual(cache['pre'],spans);self.assertEqual(cache['post'],spans)
   self.assertEqual(cache['assertions'],[])
class PublicFillGr3x(PublicFill):
 @classmethod
 def setUpClass(cls):_InstalledX.setUpClass.__func__(cls)
if __name__=='__main__':unittest.main(defaultTest=['PublicFill','PublicFillGr3x'],verbosity=2)
