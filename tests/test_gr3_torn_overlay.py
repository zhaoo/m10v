"""ARM session behavior. Photo planes remain unmapped; IIP leaf is recorded."""
import os,struct,unittest
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn import arm_const as A
ROOT=Path(__file__).resolve().parents[1]
class TornTests(unittest.TestCase):
 def test_session_component_exists(self):
  self.assertTrue((ROOT/'scripts/build_gr3_torn_overlay.py').exists(),'missing ISP-only session component')
 def setUp(self):
  if not (ROOT/'scripts/build_gr3_torn_overlay.py').exists():return
  from scripts import build_gr3_torn_overlay as b
  debug=self._testMethodName=='test_debug_trace_distinguishes_raw_rejection_from_stock_passthrough'
  names=b.EXTERNALS+((b.TRACE_EXTERNAL,) if debug else ())
  self.b=b;self.ext={n:0x54f00000+4*i for i,n in enumerate(names)}
  fixture=Path(os.environ.get('M10V_GR3_RTOS',str(ROOT/'builds/gr3-extension-validation/official-rtos.bin')))
  if not fixture.exists():fixture=Path.home()/'Desktop/code/zhaoo/m10v/builds/gr3-extension-validation/official-rtos.bin'
  self.rom=fixture.read_bytes()
  code,m=b.build(0x54d00000,self.rom,self.ext,enabled=True,debug=debug);self.sym=m['symbols']
  self.u=Uc(UC_ARCH_ARM,UC_MODE_ARM);self.u.mem_map(0x53000000,0x2000000);self.u.mem_write(0x54d00000,code)
  self.u.mem_map(0x55000000,0x1000000);self.u.reg_write(A.UC_ARM_REG_SP,0x55fe0000)
  self.owner=0x55080000;self.r=0x55100000;self.si=0x55200000;self.photo=0x55070000
  self.put(0x55063910,1);self.put(0x55063988,self.owner);self.put(self.r,0x53d0fc90);self.put(self.r+0x44c8,self.si)
  self.put(self.photo,1,0x70000000,0x74000000,0,640|(480<<16),640|(480<<16),0,2)
  self.calls=[];self.descriptors=[];self.leases=[];self.alloc_ok=True;self.eligible=True;self.camera_busy=False;self.raw_status=2;self.during_graph=None
  self.masks=[];self.resize_ok=True
  self.u.hook_add(UC_HOOK_CODE,self.hook);self.call('m10v_torn_init',self.owner)
 def put(self,p,*v):self.u.mem_write(p,struct.pack('<'+'I'*len(v),*v))
 def words(self,p,n):return struct.unpack('<'+'I'*n,self.u.mem_read(p,n*4))
 def reg(self,n):return self.u.reg_read(getattr(A,'UC_ARM_REG_R'+str(n)))
 def hook(self,u,pc,size,data):
  if pc in self.ext.values():
   name=next(n for n,p in self.ext.items() if p==pc);self.calls.append((name,[self.reg(i) for i in range(4)],self.words(self.reg(13),4)))
   result=1
   if name=='m10v_torn_eligible':result=int(self.eligible)
   elif name=='m10v_torn_camera_busy':result=int(self.camera_busy)
   elif name=='m10v_save_trace_recipe_raw_status':result=self.raw_status
   elif name=='m10v_isp_effect_transfer_plan_format':self.masks.append(self.words(self.reg(0),5))
   elif name=='m10v_isp_effect_transfer_execute':result=int(self.resize_ok)
   elif name=='m10v_isp_effect_granulation_plane':
    self.leases.append((self.words(self.owner+0x6d04,1)[0],len([c for c in self.calls if c[0]=='free'])))
    self.descriptors.append((self.words(self.reg(1),8),self.words(self.reg(2),8)))
    if self.during_graph:self.during_graph()
  elif pc==0x53050b7c:result=0
  elif pc==0x536a2424:result=0x55060000
  elif pc==0x536a27e8:result=0x76000000 if self.alloc_ok else 0;self.calls.append(('alloc',[],[]))
  elif pc==0x536a248c:result=1;self.calls.append(('free',[self.reg(0),self.reg(1)],[]))
  elif pc==0x5383c8a8:result=0;self.calls.append(('cache',[self.reg(0),self.reg(1)],[]))
  else:return
  u.reg_write(A.UC_ARM_REG_R0,result);u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
 def call(self,name,*args):
  if not hasattr(self,'sym'):self.skipTest('component missing')
  sp=0x55fe0000;self.u.reg_write(A.UC_ARM_REG_SP,sp)
  for i,v in enumerate(args):
   if i<4:self.u.reg_write(getattr(A,'UC_ARM_REG_R'+str(i)),v)
   else:self.put(sp+(i-4)*4,v)
  self.u.reg_write(A.UC_ARM_REG_LR,0x55ff0000);self.u.emu_start(self.sym[name],0x55ff0000,count=100000)
  return self.reg(0)
 def stage(self):
  self.assertEqual(self.call('m10v_torn_state',0x55071000,0x55071004),1);return self.words(0x55071000,2)
 def freeze(self,r=None):
  r=r or self.r;self.call('m10v_torn_reserve',r);return self.call('m10v_torn_freeze',r)
 def graphs(self):return [c for c in self.calls if c[0]=='m10v_isp_effect_granulation_plane']
 def test_off_freeze_stays_off_after_later_start(self):
  self.freeze();self.assertEqual(self.call('m10v_torn_set',self.owner,1),0)
  self.assertEqual(self.call('m10v_torn_execute',self.r,0x55072000,self.photo),1);self.assertFalse(self.graphs())
 def test_every_shutter_composites_and_consecutive_masks_differ(self):
  self.assertEqual(self.call('m10v_torn_set',self.owner,1),0);self.freeze()
  self.assertEqual(self.call('m10v_torn_execute',self.r,0x55072000,self.photo),1);self.assertEqual(self.stage()[0],1)
  self.assertEqual(len(self.graphs()),3);self.assertEqual(self.call('m10v_torn_encoder_admit',self.r,self.si),1)
  self.freeze();self.assertEqual(self.call('m10v_torn_execute',self.r,0x55072000,self.photo),1)
  self.assertEqual(self.stage()[0],1);self.assertEqual(len(self.graphs()),6)
  self.assertNotEqual(self.masks[0][0],self.masks[1][0])
  self.assertEqual(self.call('m10v_torn_set',self.owner,0),0)
  self.assertEqual(len([c for c in self.calls if c[0]=='free']),1)
  self.assertEqual(self.descriptors[2][0][1],0x74000000)
  self.assertTrue(all(not s[2] and not d[2] for d,s in self.descriptors))
 def test_resize_error_preserves_original_and_reports_failure(self):
  self.call('m10v_torn_set',self.owner,1);self.freeze();self.resize_ok=False
  self.assertEqual(self.call('m10v_torn_execute',self.r,0x55072000,self.photo),0xffffffff)
  self.assertEqual(self.call('m10v_torn_encoder_admit',self.r,self.si),1)
  self.assertEqual(self.stage()[0],4);self.assertFalse(self.graphs())
 def test_busy_freeze_cannot_cancel_the_lease_holders_first_shot(self):
  self.call('m10v_torn_set',self.owner,1);self.freeze()
  # Model a second producer hitting the first shot's execution lease.
  self.put(self.owner+0x6d04,1)
  other=self.r+0x10000;self.put(other,0x53d0fc90);self.put(other+0x44c8,self.si);self.freeze(other)
  self.assertEqual(self.stage()[0],1)
  self.assertEqual(self.call('m10v_torn_encoder_admit',other,self.si),1)
  self.put(self.owner+0x6d04,0)
  self.assertEqual(self.call('m10v_torn_execute',self.r,0x55072000,self.photo),1)
  self.assertEqual(self.stage()[0],1)
 def test_debug_trace_distinguishes_raw_rejection_from_stock_passthrough(self):
  self.call('m10v_torn_set',self.owner,1);self.freeze();self.raw_status=0
  self.assertEqual(self.call('m10v_torn_execute',self.r,0x55072000,self.photo),0xffffffff)
  self.assertEqual(self.call('m10v_torn_encoder_admit',self.r,self.si),1)
  tags={regs[2]:(regs[3],stack[0]) for name,regs,stack in self.calls if name==self.b.TRACE_EXTERNAL}
  self.assertEqual(tags[0x544f5201],(0x100,2))
  self.assertEqual(tags[0x544f5203],(640|(480<<16),640|(480<<16)))
  self.assertEqual(tags[0x544f5204],(0x110,2))
  self.assertEqual(tags[0x544f5205],(0x01ff0001,2))
  self.assertFalse(self.graphs())
 def test_24mp_planes_stay_unmapped_and_worker_never_allocates(self):
  self.put(self.photo+16,6000|(4000<<16),6016|(4000<<16))
  self.assertEqual(self.call('m10v_torn_set',self.owner,1),0)
  allocations=len([c for c in self.calls if c[0]=='alloc'])
  for _ in range(2):
   self.freeze();self.assertEqual(self.call('m10v_torn_execute',self.r,0x55072000,self.photo),1)
   self.assertEqual(self.stage()[0],1)
  self.assertEqual(len(self.graphs()),6)
  self.assertEqual(len([c for c in self.calls if c[0]=='alloc']),allocations)
  self.assertEqual(self.descriptors[0][0][5],6000|(4000<<16))
  self.assertEqual(self.leases,[(1,0)]*6)
  self.assertEqual(len([c for c in self.calls if c[0]=='alloc']),1)
 def test_pending_capture_busy_and_second_queue_fails_preserving_pixels(self):
  self.call('m10v_torn_set',self.owner,1);self.freeze();self.assertEqual(self.call('m10v_torn_busy'),1)
  self.assertEqual(self.call('m10v_torn_set',self.owner,0),0xffffffff)
  other=self.r+0x10000;self.put(other,0x53d0fc90);self.put(other+0x44c8,self.si);self.freeze(other)
  self.assertEqual(self.stage()[0],1);self.assertEqual(self.call('m10v_torn_encoder_admit',other,self.si),1)
  self.assertEqual(self.call('m10v_torn_execute',self.r,0x55072000,self.photo),1)
  self.assertEqual(len(self.graphs()),3)
 def test_allocation_failure_and_ineligible_do_not_start(self):
  self.alloc_ok=False;self.assertEqual(self.call('m10v_torn_set',self.owner,1),0xffffffff);self.assertEqual(self.stage()[0],0)
  self.alloc_ok=True;self.eligible=False;self.assertEqual(self.call('m10v_torn_set',self.owner,1),0xffffffff);self.assertFalse(self.graphs())
 def test_wrong_si_encoder_duplicate_and_geometry_rejection(self):
  self.call('m10v_torn_set',self.owner,1);self.freeze();self.assertEqual(self.call('m10v_torn_encoder_admit',self.r,self.si+4),0)
  self.assertEqual(self.call('m10v_torn_encoder_admit',self.r,self.si),0)
  self.call('m10v_torn_execute',self.r,0x55072000,self.photo);self.assertEqual(self.call('m10v_torn_execute',self.r,0x55072000,self.photo),1);self.assertEqual(len(self.graphs()),3)
  self.freeze();self.put(self.photo+16,319|(480<<16));self.assertEqual(self.call('m10v_torn_execute',self.r,0x55072000,self.photo),0xffffffff);self.assertEqual(len(self.graphs()),3)
 def test_cancel_queued_via_destroy_releases_once(self):
  self.call('m10v_torn_set',self.owner,1);self.freeze();self.call('m10v_torn_destroy',self.owner)
  self.assertEqual(len([c for c in self.calls if c[0]=='free']),1);self.assertEqual(self.call('m10v_torn_execute',self.r,0x55072000,self.photo),0xffffffff)
  self.assertEqual(self.call('m10v_torn_encoder_admit',self.r,self.si),1)
 def test_raw_alias_and_changed_frozen_direction_reject_before_graph(self):
  self.call('m10v_torn_set',self.owner,1);self.freeze();self.put(self.r+0x60,0x70000000);self.put(self.r+0x230,0x55075000);self.put(0x55075000,640|(480<<16))
  self.assertEqual(self.call('m10v_torn_execute',self.r,0x55072000,self.photo),0xffffffff);self.assertFalse(self.graphs())
 def test_direction_changed_after_freeze_rejects(self):
  self.call('m10v_torn_set',self.owner,1);self.freeze();self.u.mem_write(self.si+0xc8,b'\x01')
  self.assertEqual(self.call('m10v_torn_execute',self.r,0x55072000,self.photo),0xffffffff);self.assertFalse(self.graphs())
 def test_unaligned_uv_second_phase_rejects_before_either_channel(self):
  self.call('m10v_torn_set',self.owner,1);self.freeze();self.call('m10v_torn_execute',self.r,0x55072000,self.photo);self.freeze()
  self.put(self.photo+8,0x74000001);self.assertEqual(self.call('m10v_torn_execute',self.r,0x55072000,self.photo),0xffffffff);self.assertEqual(len(self.graphs()),3)
 def test_native_pitch_rounding_rejects_before_first_pass(self):
  self.call('m10v_torn_set',self.owner,1);self.freeze();self.put(self.photo+16,642|(480<<16));self.put(self.photo+20,644|(480<<16))
  self.assertEqual(self.call('m10v_torn_execute',self.r,0x55072000,self.photo),0xffffffff);self.assertFalse(self.graphs())
 def test_absent_raw_pointer_requires_authenticated_release(self):
  self.call('m10v_torn_set',self.owner,1);self.freeze();self.raw_status=0
  self.assertEqual(self.call('m10v_torn_execute',self.r,0x55072000,self.photo),0xffffffff);self.assertFalse(self.graphs())
 def test_second_channel_alias_of_native_request_is_preflight_rejected(self):
  self.call('m10v_torn_set',self.owner,1);self.freeze();self.call('m10v_torn_execute',self.r,0x55072000,self.photo);self.freeze()
  self.put(self.r+0x5c,0x74000000)
  self.assertEqual(self.call('m10v_torn_execute',self.r,0x55072000,self.photo),0xffffffff);self.assertEqual(len(self.graphs()),3)
 def test_generic_plane_export_validates_roi_stride_and_nonalias_before_native(self):
  from scripts import build_gr3_isp_effect_granulation as g
  code,m=g.build(0x54b00000,self.rom,enabled=True);self.assertIn('m10v_isp_effect_granulation_plane',m['symbols'])
  self.u.mem_write(0x54b00000,code);self.sym.update(m['symbols']);native=[]
  def native_call(u,pc,size,data):
   if pc!=self.sym['m10v_isp_effect_granulation_call']:return
   native.append([self.reg(i) for i in range(4)]);info=self.words(self.reg(13)+4,1)[0]
   self.put(info+32,1);self.put(info+40,1);self.put(info+48,1)
   u.reg_write(A.UC_ARM_REG_R0,1);u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
  self.u.hook_add(UC_HOOK_CODE,native_call);dst=0x55073000;src=0x55073020;curves=0x55074000
  self.put(src,1,0x70000000,0,0,640|(480<<16),640|(480<<16),0,2);self.put(dst,1,0x74000000,0,0,640|(480<<16),640|(480<<16),0,2)
  self.assertEqual(self.call('m10v_isp_effect_granulation_plane',0x55072000,dst,src,0x76000000,307200,640,curves),1);self.assertEqual(len(native),1)
  self.put(src+24,2);self.assertEqual(self.call('m10v_isp_effect_granulation_plane',0x55072000,dst,src,0x76000000,307200,640,curves),0xffffffff);self.assertEqual(len(native),1)
  self.put(src+24,0);self.put(dst+4,0x70000004);self.assertEqual(self.call('m10v_isp_effect_granulation_plane',0x55072000,dst,src,0x76000000,307200,640,curves),0xffffffff);self.assertEqual(len(native),1)
if __name__=='__main__':unittest.main()
