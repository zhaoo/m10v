"""Real ARM adapter/hook tests; pixel addresses deliberately unmapped."""
from pathlib import Path
import struct,unittest,sys
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn import arm_const as A
from scripts import build_gr3_isp_effect_granulation as build
ROOT=Path(__file__).resolve().parents[1]
BASE=0x54190000
class GranulationTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.rom=(ROOT/'builds/gr3-pure-isp-feasibility-20261031/gr3-official-rtos.bin').read_bytes()
  cls.code,cls.manifest=build.build(BASE,cls.rom,enabled=True);cls.symbols=cls.manifest['symbols']
 def put(self,p,*v):self.u.mem_write(p,struct.pack('<'+'I'*len(v),*v))
 def word(self,p):return struct.unpack('<I',self.u.mem_read(p,4))[0]
 def reg(self,n):return self.u.reg_read(getattr(A,'UC_ARM_REG_R'+str(n)))
 def setUp(self):
  self.u=Uc(UC_ARCH_ARM,UC_MODE_ARM);self.u.mem_map(0x53000000,(len(self.rom)+4095)&~4095);self.u.mem_write(0x53000000,self.rom)
  self.u.mem_map(BASE,0x10000);self.u.mem_write(BASE,self.code);self.u.mem_map(0x55000000,0x100000)
  self.u.reg_write(A.UC_ARM_REG_C1_C0_2,0xf00000);self.u.reg_write(A.UC_ARM_REG_FPEXC,0x40000000)
  self.ctx,self.dst,self.src,self.info=0x55001000,0x55002000,0x55003000,0x55004000
  self.plane=0x70000000;self.graph=0x55008000;self.stop=0x550f0000
  for p in (self.dst,self.src):
   self.put(p,1,0x71000000);self.u.mem_write(p+0x10,struct.pack('<HHH',31,17,40))
  self.put(self.info,544,0x474e5031,self.ctx,self.plane,544,0,0x474e5031^self.info^self.ctx^self.plane,0,0,0,0,0,0)
  self.u.reg_write(A.UC_ARM_REG_SP,0x550e0000);self.put(0x550e0000,self.plane,self.info)
  for n,v in enumerate((self.ctx,self.dst,self.src,2)):self.u.reg_write(getattr(A,'UC_ARM_REG_R'+str(n)),v)
  self.u.reg_write(A.UC_ARM_REG_LR,self.stop)
  self.u.emu_start(self.symbols['m10v_isp_effect_granulation_call'],0x5367ae14,count=1000)
  self.frame=self.u.reg_read(A.UC_ARM_REG_FP);self.calls=[];self.wait_results=[1];self.driver_busy=0
  self.u.hook_add(UC_HOOK_CODE,self.hook)
 def hook(self,u,pc,size,data):
  if pc==0x5376cd10 and getattr(self,'real_submit',False):return
  if pc==0x536b0a74 and getattr(self,'stop_on_hold',False):u.emu_stop();return
  if pc in (0x5368a92c,0x5376cd10,0x5368a510,0x5376c044,0x536b0a74,0x536ae71c,0x536a848c,0x536a8544,0x536ae870,0x53778490,0x53778458,0x53778474,0x5376ebd0,0x5376e55c):
   self.calls.append((pc,[self.reg(i) for i in range(4)],self.u.reg_read(A.UC_ARM_REG_SP)))
   r=self.wait_results.pop(0) if pc==0x5368a510 else 1
   if pc in (0x53778490,0x53778474):r=self.driver_busy
   if pc==0x5376c044:self.put(self.reg(0)+0x9c,0);self.u.mem_write(self.reg(0)+0x40,b'\0')
   u.reg_write(A.UC_ARM_REG_R0,r);u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
 def invoke(self,name,args):
  for n,v in enumerate(args):self.u.reg_write(getattr(A,'UC_ARM_REG_R'+str(n)),v)
  self.u.reg_write(A.UC_ARM_REG_LR,self.stop);self.u.emu_start(self.symbols[name],self.stop,count=100000);return self.reg(0)
 def test_original_frame_and_exact_nonce_binding_skip_rng_without_pixels(self):
  self.assertEqual(self.word(self.frame-4),self.symbols['m10v_isp_effect_granulation_return'])
  self.assertEqual([self.word(self.frame+n) for n in (4,8)],[self.plane,self.info])
  self.assertEqual(self.word(self.frame-0x648),self.plane)
  self.assertEqual(self.invoke('m10v_isp_effect_granulation_rng',[self.frame]),1)
  self.assertEqual(self.word(self.info+40),1);self.assertFalse(self.calls)
  self.put(self.frame-4,0x12345678);self.put(self.frame+8,0x72000000)
  self.assertEqual(self.invoke('m10v_isp_effect_granulation_rng',[self.frame]),0)
 def test_rng_hook_preserves_registers_status_all_vfp_and_stock_tail(self):
  for owned in (True,False):
   self.put(self.info+40,0);self.put(self.frame-4,self.symbols['m10v_isp_effect_granulation_return'] if owned else 0x12345678)
   for n in range(13):self.u.reg_write(getattr(A,'UC_ARM_REG_R'+str(n)),self.frame if n==11 else 0x100+n)
   for n in range(32):self.u.reg_write(getattr(A,'UC_ARM_REG_D'+str(n)),0x1234567800000000+n)
   self.u.reg_write(A.UC_ARM_REG_FPSCR,0x01000000);self.u.reg_write(A.UC_ARM_REG_CPSR,(self.u.reg_read(A.UC_ARM_REG_CPSR)&0xfffffff)|0xa0000000)
   self.u.reg_write(A.UC_ARM_REG_LR,self.stop);before=[self.reg(n) for n in range(15)]
   self.u.emu_start(self.symbols['granulation_rng_hook'],self.stop,count=100000)
   if not owned:before[0]=1
   self.assertEqual([self.reg(n) for n in range(15)],before)
   self.assertEqual(self.u.reg_read(A.UC_ARM_REG_CPSR)&0xf0000000,0xa0000000)
   self.assertEqual(self.u.reg_read(A.UC_ARM_REG_FPSCR),0x01000000)
   self.assertEqual([self.u.reg_read(getattr(A,'UC_ARM_REG_D'+str(n))) for n in range(32)],[0x1234567800000000+n for n in range(32)])
  self.assertEqual([c[0] for c in self.calls],[0x5368a92c])
 def setup_graph(self):
  self.put(self.info+40,1);self.put(self.graph+0x38,self.ctx+4)
  for n,(a,b) in enumerate(((0x5c,0x64),(0x6c,0x70),(0x60,0x68))):
   self.put(self.graph+a,0x55010000+n*0x200);self.put(self.graph+b,0x55010000+n*0x200)
  self.put(self.graph+0x74,*([256]*6))
 def test_stock_signed_coefficients_untouched_and_custom_curves_copy_only_768(self):
  self.setup_graph();old=struct.pack('<768h',*([-3,258]*384));self.u.mem_write(0x55010000,old)
  self.invoke('m10v_isp_effect_granulation_submit',[self.frame,self.graph]);self.assertEqual(bytes(self.u.mem_read(0x55010000,1536)),old)
  self.put(self.info+44,0);self.put(self.info+20,0x55020000);curves=struct.pack('<768h',*([n%256 for n in range(768)]));self.u.mem_write(0x55020000,curves)
  self.invoke('m10v_isp_effect_granulation_submit',[self.frame,self.graph]);self.assertEqual(bytes(self.u.mem_read(0x55010000,1536)),curves)
 def test_owned_wait_retries_real_failures_and_unowned_wait_once(self):
  self.setup_graph();self.put(self.info+44,self.graph);self.wait_results=[0,0,1]
  self.assertEqual(self.invoke('m10v_isp_effect_granulation_wait',[self.ctx,0x400,self.frame]),1)
  self.assertEqual(self.word(self.info+32),1);self.assertEqual(self.word(self.info+36),2)
  self.put(self.frame-4,0x12345678);self.wait_results=[0]
  self.assertEqual(self.invoke('m10v_isp_effect_granulation_wait',[self.ctx,0x400,self.frame]),0)
 def setup_release(self):
  self.setup_graph();self.wrapper=0x55028000;self.service=0x55030000;self.driver=0x55040000
  self.put(self.ctx+8,self.wrapper);self.put(self.wrapper+4,self.service);self.put(self.graph+0x9c,self.service);self.u.mem_write(self.graph+0x40,b'\x01')
  self.put(self.info+44,self.graph);self.put(self.info+32,1)
  self.u.mem_write(self.graph+0xa3,b'\x01');self.u.mem_write(self.graph+0x114,b'\x01');self.put(self.graph+0x118,0x20)
  self.put(self.service+0x104,0x20);self.put(self.service+0x5c,self.ctx+4);self.u.mem_write(self.service+0xfc,b'\x01');self.put(self.service+0x24,self.driver)
 def test_release_observes_native_reservation_and_driver_under_both_locks(self):
  self.setup_release();self.assertEqual(self.invoke('m10v_isp_effect_granulation_release',[self.graph,self.frame]),1)
  self.assertEqual(self.word(self.info+48),1)
  self.assertEqual([c[0] for c in self.calls],[0x536ae71c,0x536a848c,0x53778490,0x53778458,0x53778474,0x536a8544,0x536ae870,0x5376c044])
 def test_actual_original_submit_resolves_nested_service_then_guard_releases_distinct_owners(self):
  self.setup_release();self.real_submit=True
  self.put(self.graph+0x9c,0);self.u.mem_write(self.graph+0x40,b'\0')
  for n,v in enumerate((self.wrapper,self.graph,0,0)):self.u.reg_write(getattr(A,'UC_ARM_REG_R'+str(n)),v)
  self.u.reg_write(A.UC_ARM_REG_LR,self.stop);self.u.emu_start(0x5376cd10,self.stop,count=10000)
  self.assertNotEqual(self.wrapper,self.service);self.assertEqual(self.word(self.ctx+8),self.wrapper)
  self.assertEqual(self.word(self.wrapper+4),self.service);self.assertEqual(self.word(self.graph+0x9c),self.service)
  self.assertEqual(bytes(self.u.mem_read(self.graph+0x40,1)),b'\x01')
  self.assertEqual([c[1][0] for c in self.calls if c[0] in (0x5376ebd0,0x5376e55c)],[self.service,self.service])
  self.calls=[];self.assertEqual(self.invoke('m10v_isp_effect_granulation_release',[self.graph,self.frame]),1)
  self.assertEqual(self.word(self.info+48),1);self.assertEqual(self.calls[0][1][0],self.service+0x90)
 def test_actual_full_copy_graph_submit_owner_store_matches_both_official_models(self):
  sys.path.insert(0,str(ROOT/'scripts'))
  from scripts import border_copy_contract as original
  baseline=original.OriginalArm;observed=[]
  class Observe(baseline):
   def __init__(p,rom):
    super().__init__(rom)
    def trace(u,pc,size,data):
     if pc==0x5376c6f4:
      graph=u.reg_read(A.UC_ARM_REG_R5);wrapper=u.reg_read(A.UC_ARM_REG_R8)
      observed.append((wrapper,p.read_words(wrapper+4,1)[0],p.read_words(graph+0x9c,1)[0]))
    p.u.hook_add(UC_HOOK_CODE,trace)
  original.OriginalArm=Observe
  try:
   for model in ('gr3','gr3x'):
    rom=(ROOT/f'builds/gr3-pure-isp-feasibility-20261031/{model}-official-rtos.bin').read_bytes()
    result=original.probe(rom);self.assertEqual(result['assertions'],[])
    self.assertEqual(observed[-1],(0x55081000,0x55084000,0x55084000))
    geometry=result['geometry'];self.assertEqual([r['plane'] for r in result['format_register_fixture']],[0x70000000,geometry['destination']])
    self.assertEqual(result['format_register_fixture'][1]['stride'],geometry['stride'])
    self.assertIn(dict(address=geometry['destination'],bytes=geometry['stride']*geometry['height']),result['cache'])
  finally:original.OriginalArm=baseline
 def test_wrong_wrapper_or_nested_service_retains_before_any_release_lock(self):
  for target,value in (('graph',0x55028000),('nested',0x55030004),('wrapper',0),('wrapper',0x55028001)):
   self.setUp();self.setup_release();self.stop_on_hold=True
   if target=='graph':self.put(self.graph+0x9c,value)
   elif target=='nested':self.put(self.wrapper+4,value)
   else:self.put(self.ctx+8,value)
   self.invoke('m10v_isp_effect_granulation_release',[self.graph,self.frame])
   self.assertEqual(self.word(self.info+28),1);self.assertEqual(self.word(self.info+48),0);self.assertFalse(self.calls)
 def test_busy_driver_or_invalid_nonce_retains_without_original_release_or_rng(self):
  self.setup_release();self.driver_busy=1
  self.invoke('m10v_isp_effect_granulation_release',[self.graph,self.frame])
  self.assertNotIn(0x5376c044,[c[0] for c in self.calls]);self.assertEqual(self.word(self.info+48),0)
  self.assertEqual(self.word(self.graph+0x9c),self.service)
  self.put(self.info+24,0);self.calls=[]
  self.invoke('m10v_isp_effect_granulation_rng',[self.frame]);self.assertNotIn(0x5368a92c,[c[0] for c in self.calls]);self.assertEqual(self.word(self.info+28),1)
 def test_submit_hook_retains_original_stack_varargs_and_unowned_hooks_tail_original(self):
  self.put(self.frame-4,0x12345678)
  for name,target in (('submit',0x5376cd10),('wait',0x5368a510),('release',0x5376c044)):
   original_sp=self.u.reg_read(A.UC_ARM_REG_SP);self.put(original_sp,0xaabbccdd,0x11223344,0x55667788,0x99887766)
   self.invoke('granulation_'+name+'_hook',[self.graph,0x400,0x100,0x200])
   call=self.calls[-1];self.assertEqual(call[0],target);self.assertEqual(call[1],[self.graph,0x400,0x100,0x200]);self.assertEqual(call[2],original_sp)
   self.assertEqual(self.word(original_sp),0xaabbccdd)
 def test_builder_both_models_opt_in_and_rejects_changed_image(self):
  self.assertEqual(build.build()[0],b'')
  for model in ('gr3','gr3x'):
   code,m=build.build(BASE,(ROOT/f'builds/gr3-pure-isp-feasibility-20261031/{model}-official-rtos.bin').read_bytes(),enabled=True,camera_model=model)
   self.assertEqual(code,self.code);self.assertEqual(len(m['patches']),5)
  for options in ({'stock':self.rom[:-1]},{'base':BASE+1},{'enabled':1}):
   kw=dict(base=BASE,stock=self.rom,enabled=True);kw.update(options)
   with self.assertRaises(ValueError):build.build(**kw)
 def test_strided_luma_setup_keeps_roi_address_pitch_capacity_and_only_three_registers_change(self):
  # Exercise the real original prologue and new B trampoline, including a
  # four-byte ROI and upper-bank photo source. No image memory is mapped.
  p=next(p for p in self.manifest['patches'] if p['symbol']=='granulation_setup_hook')
  self.put(p['address'],p['replacement'])
  self.u.ctl_remove_cache(p['address'],p['address']+4)
  for photo,pitch in ((0x71000004,416),(0xb1000004,832)):
   n=pitch*17
   self.put(self.info,n,0x474e5031,self.ctx,photo,n,0,
            0x474e5031^self.info^self.ctx^photo^pitch,0,0,0,0,0,0,pitch)
   self.u.reg_write(A.UC_ARM_REG_SP,0x550e0000);self.put(0x550e0000,photo,self.info)
   for k,v in enumerate((self.ctx,self.dst,self.src,1)):self.u.reg_write(getattr(A,'UC_ARM_REG_R'+str(k)),v)
   self.u.reg_write(A.UC_ARM_REG_LR,self.stop)
   self.u.emu_start(self.symbols['m10v_isp_effect_granulation_call'],0x5367ae14,count=10000)
   frame=self.u.reg_read(A.UC_ARM_REG_FP)
   self.assertEqual(self.word(frame-0x648),photo)
   self.assertEqual(self.word(frame-0x650),pitch)
   self.assertEqual(self.reg(4),n);self.assertEqual(self.reg(6),photo)
   self.assertEqual(self.invoke('m10v_isp_effect_granulation_rng',[frame]),1)
 def test_setup_stock_and_default_preimage_preserves_registers_flags_and_vfp(self):
  for owned in (False,True):
   self.put(self.frame-4,self.symbols['m10v_isp_effect_granulation_return'] if owned else 0x12345678)
   for n in range(13):self.u.reg_write(getattr(A,'UC_ARM_REG_R'+str(n)),self.frame if n==11 else 0x100+n)
   for n in range(32):self.u.reg_write(getattr(A,'UC_ARM_REG_D'+str(n)),0x1234567800000000+n)
   self.u.reg_write(A.UC_ARM_REG_LR,32);self.u.reg_write(A.UC_ARM_REG_FPSCR,0x01000000)
   self.u.reg_write(A.UC_ARM_REG_CPSR,0xa8000013)
   before=[self.reg(n) for n in range(15)]
   self.u.emu_start(self.symbols['granulation_setup_hook'],0x5367adb0,count=10000)
   self.assertEqual([self.reg(n) for n in range(15)],before)
   self.assertEqual(self.word(self.frame-0x650),32)
   self.assertEqual(self.u.reg_read(A.UC_ARM_REG_CPSR)&0xf8000000,0xa8000000)
   self.assertEqual(self.u.reg_read(A.UC_ARM_REG_FPSCR),0x01000000)
   self.assertEqual([self.u.reg_read(getattr(A,'UC_ARM_REG_D'+str(n))) for n in range(32)],[0x1234567800000000+n for n in range(32)])
if __name__=='__main__':unittest.main()
