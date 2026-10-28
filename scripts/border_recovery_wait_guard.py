#!/usr/bin/env python3
"""Isolated native wait guard + hook prototype, no firmware emitted/activated."""
from pathlib import Path
import shutil,struct,subprocess,tempfile,unittest
from border_recovery_contract import RecoveryContract as _Harness,ROOT,A
from build_gr3_iip_graph import FLAGS
from unicorn import UC_PROT_READ,UC_PROT_EXEC,UC_PROT_WRITE
BASE=0x54160000
API={
 'm10v_border_fill_bundle_submit',
 'm10v_border_client_construct','m10v_border_client_prepare','m10v_border_client_notify',
 'm10v_border_client_done','m10v_border_client_destroy_if_done','m10v_border_client_wait',
 'm10v_border_transfer_construct','m10v_border_transfer_body','m10v_border_transfer_wait',
 'border_recovery_transfer_body_hook','border_recovery_transfer_wait_hook',
 'm10v_border_fill_construct','m10v_border_resize_construct','m10v_border_fill_body','m10v_border_resize_body',
 'm10v_border_fill_wait','m10v_border_resize_wait','m10v_border_resize_dma_wait',
 'border_recovery_fill_body_hook','border_recovery_resize_body_hook','border_recovery_fill_wait_hook',
 'border_recovery_resize_wait_hook','border_recovery_resize_dma_wait_hook',
 'm10v_border_fill_release','m10v_border_resize_release','border_recovery_fill_release_hook','border_recovery_resize_release_hook',
 'm10v_border_stage_enter','m10v_border_stage_leave'}
def build():
 folder=tempfile.TemporaryDirectory(prefix='border_recovery_wait_guard_');p=Path(folder.name)
 inputs=[ROOT/'native/gr3/m10v_border_wait_guard.c',ROOT/'scripts/border_recovery_wait_guard.S'];objects=[]
 for i,source in enumerate(inputs):
  obj=p/f'probe{i}.o';subprocess.run([shutil.which('clang'),*FLAGS,'-c',str(source),'-o',str(obj)],check=True,capture_output=True);objects.append(str(obj))
 (p/'link.ld').write_text(f'SECTIONS {{ . = {BASE}; .text : {{ *(.text*) }} .rodata : {{ *(.rodata*) }} /DISCARD/ : {{ *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }} }}')
 subprocess.run([shutil.which('ld.lld'),'-T',str(p/'link.ld'),'--entry=m10v_border_client_construct',*objects,'-o',str(p/'probe.elf')],check=True,capture_output=True)
 b=(p/'probe.elf').read_bytes();sh=struct.unpack_from('<I',b,32)[0];n=struct.unpack_from('<H',b,48)[0]
 rows=[struct.unpack_from('<10I',b,sh+i*40) for i in range(n)];image=bytearray();symbols={}
 for row in rows:
  if row[2]&2 and row[5]:
   assert row[1]==1 and not row[2]&1,'no mutable static registry/TLS is allowed'
   off=row[3]-BASE;assert 0<=off<65536
   if len(image)<off+row[5]:image.extend(bytes(off+row[5]-len(image)))
   image[off:off+row[5]]=b[row[4]:row[4]+row[5]]
  if row[1]==2:
   sr=rows[row[6]];strings=b[sr[4]:sr[4]+sr[5]]
   for at in range(row[4],row[4]+row[5],16):
    name,value,_,info,_,section=struct.unpack_from('<IIIBBH',b,at);name=strings[name:].split(b'\0',1)[0].decode();assert section or not name
    if name in API and info&15==2:symbols[name]=value
 assert set(symbols)==API
 return folder,bytes(image),symbols
class WaitGuard(unittest.TestCase):
 reg=_Harness.reg;put=_Harness.put;word=_Harness.word;call=_Harness.call
 @classmethod
 def setUpClass(cls):cls.folder,cls.code,cls.symbols=build()
 @classmethod
 def tearDownClass(cls):cls.folder.cleanup()
 def setUp(self):
  _Harness.setUp(self);self.u.mem_map(BASE,0x10000);self.u.mem_write(BASE,self.code)
  self.client,self.worker,self.job=0x55001000,0x55002000,0x55003000
  self.stubs.update({0x536a9bf8:0,0x536aa3a4:1,0x536aa34c:0,0x536abc78:0,0x536a9dd4:0})
  self.call(self.symbols['m10v_border_client_construct'],self.client)
  self.assertEqual(self.call(self.symbols['m10v_border_client_prepare'],self.client,0x03050006,0x400),1)
  self.put(self.job,0,self.client,0x55004000,0x010e8006,0)
  self.wait_results=[];self.waits=[];self.signal_state=[];self.yields=0;self.complete_on_yield=False;self.stop_at_yield=False
 def patch_bl(self,pc,target,original):
  self.assertEqual(self.word(pc),original)
  page=pc&~4095;self.u.mem_protect(page,4096,UC_PROT_READ|UC_PROT_WRITE|UC_PROT_EXEC)
  delta=(target-pc-8)//4;self.put(pc,0xeb000000|(delta&0xffffff))
  self.u.mem_protect(page,4096,UC_PROT_READ|UC_PROT_EXEC)
 def hook(self,u,pc,size,data):
  def ret(value):u.reg_write(A.UC_ARM_REG_R0,value);u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
  if pc==0x536af2a8 and hasattr(self,'allocations'):
   self.allocations.append(self.reg(0));ret(self.heap_results.pop(0));return
  if pc in (0x5365900c,0x53673098) and getattr(self,'observe_other_body',False):
   offset=0x58 if pc==0x5365900c else 0x48
   self.observed_tail=tuple(self.word(self.worker+offset+4*i) for i in range(4));self.body_calls+=1;ret(0x1234);return
  if pc==0x5369a948 and getattr(self,'observe_body',False):
   self.observed_tail=tuple(self.word(self.worker+0x44+4*i) for i in range(4));self.body_calls+=1;ret(0x1234);return
  if pc==0x536a9e8c:
   self.waits.append((self.reg(0),self.reg(1),self.reg(3)))
   result,bits=self.wait_results.pop(0) if self.wait_results else (0,0)
   if self.reg(2):self.put(self.reg(2),bits)
   ret(result);return
  if pc==0x536b0a74:
   self.yields+=1
   if self.stop_at_yield:u.emu_stop();return
   if self.complete_on_yield:
    # Schedule a separate callback CPU context outside this hook. Keep the
    # original public/worker frames untouched while the model runs callback.
    self.callback_due=True;u.emu_stop();return
   ret(0);return
  if pc==0x536a9d1c:
   if getattr(self,'pause_signal',False):u.emu_stop();return
   self.signal_state.append((self.word(self.client+36),self.word(self.client+40),self.reg(0),self.reg(1)))
   ret(1);return
  if pc==0x536abd28:
   result=self.word(u.reg_read(A.UC_ARM_REG_SP)+8);self.put(result,0,0);self.enqueued_job=self.reg(1);ret(1);return
  return _Harness.hook(self,u,pc,size,data)
 def invoke(self,fn,args=(),stack=0x550fd000):
  for i,value in enumerate(args):
   if i<4:self.u.reg_write(getattr(A,'UC_ARM_REG_R'+str(i)),value)
   else:self.put(stack+4*(i-4),value)
  self.u.reg_write(A.UC_ARM_REG_SP,stack);self.u.reg_write(A.UC_ARM_REG_LR,0x550ff000)
  self.u.emu_start(fn,0x550ff000,count=100000)
 def notify(self):
  self.invoke(self.word(self.word(self.client)+8),(self.client,0x03050006,0),0x550dd000)
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x550ff000)
 def test_private_notify_pending_outlives_real_native_signal_and_rejects_early_destroy(self):
  self.assertEqual(self.call(self.symbols['m10v_border_client_destroy_if_done'],self.client),0)
  self.notify();self.assertEqual(self.signal_state,[(1,1,self.client+4,0x400)])
  self.assertEqual(self.call(self.symbols['m10v_border_client_destroy_if_done'],self.client),1)
 def test_full_original_public_copy_keeps_both_stack_frames_on_failed_wait(self):
  src,dst,factory=0x55004000,0x55005000,0x55006000
  self.u.mem_write(src,b'\x01');self.u.mem_write(dst,b'\x01');self.put(factory+4,self.worker)
  self.stubs[0x5369a0e8]=factory
  self.patch_bl(0x534aae28,self.symbols['m10v_border_client_wait'],0xeb07fc17)
  self.stop_at_yield=True
  self.invoke(0x534ab7a0,(self.client,0,src,dst,1))
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x536b0a74)
  sp=self.u.reg_read(A.UC_ARM_REG_SP);self.assertLess(sp,0x550fcf40)
  job=self.enqueued_job;self.assertGreaterEqual(job,sp);self.assertLess(job,0x550fd000)
  pair=self.word(job+8);self.assertEqual((self.word(pair),self.word(pair+4)),(src,dst))
  self.assertNotIn(0x534aae48,self.visited);self.assertNotIn(0x534ab848,self.visited)
  self.assertEqual(self.word(self.client+36),1)
  held=bytes(self.u.mem_read(sp,0x550fd000-sp));paused=self.u.context_save()
  self.stop_at_yield=False;self.notify()
  self.assertEqual(bytes(self.u.mem_read(sp,len(held))),held)
  self.u.context_restore(paused)
  # Finish the yielded RTOS sleep without touching paused caller arguments.
  self.u.reg_write(A.UC_ARM_REG_R0,0);self.u.reg_write(A.UC_ARM_REG_PC,self.u.reg_read(A.UC_ARM_REG_LR))
  self.u.emu_start(self.u.reg_read(A.UC_ARM_REG_PC),0x550ff000,count=100000)
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x550ff000)
  self.assertIn(0x534aae48,self.visited);self.assertIn(0x534ab848,self.visited)
 def test_first_worker_constructor_owns_new_tail_without_touching_stock_neighbor(self):
  self.u.mem_write(self.worker+0x44,b'\xa5'*24)
  self.call(self.symbols['m10v_border_transfer_construct'],self.worker)
  self.assertEqual(self.word(self.worker+0x44),0x42575431)
  self.assertEqual(bytes(self.u.mem_read(self.worker+0x48,12)),bytes(12))
  self.assertEqual(self.word(self.worker+0x54),0)
  self.assertEqual(bytes(self.u.mem_read(self.worker+0x58,4)),b'\xa5'*4)
 def test_owned_inner_wait_retries_error_before_original_cleanup(self):
  self.call(self.symbols['m10v_border_transfer_construct'],self.worker)
  self.put(self.worker+0x44,0x42575431,self.client,self.job,1)
  self.put(self.client+60,self.worker,self.job)
  self.patch_bl(0x5369a478,self.symbols['border_recovery_transfer_wait_hook'],0xeb003e83)
  self.stubs.update({0x537e2814:0,0x537e29e4:0})
  self.wait_results=[(0,0),(1,0x03050001)]
  self.invoke(0x5369a40c,(self.worker,0x55007000))
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x550ff000)
  self.assertEqual(len(self.waits),2);self.assertEqual(self.yields,1)
  self.assertIn(0x537e29e4,self.visited)
 def test_factory_prototype_extends_only_first_allocation_and_initializes_tail(self):
  factory,dmafactory,second=0x55008000,0x55009000,0x5500a000
  self.put(dmafactory+4,0x5500b000)
  self.stubs.update({0x537e2d6c:dmafactory,0x536b93d0:0,0x5369a164:1,0x5369ad9c:1})
  self.allocations=[];self.heap_results=[self.worker,second]
  page=0x5369a000;self.u.mem_protect(page,4096,UC_PROT_READ|UC_PROT_WRITE|UC_PROT_EXEC)
  self.assertEqual(self.word(0x5369a010),0xe3a00044);self.put(0x5369a010,0xe3a00058)
  self.u.mem_protect(page,4096,UC_PROT_READ|UC_PROT_EXEC)
  self.patch_bl(0x5369a01c,self.symbols['m10v_border_transfer_construct'],0xeb0000a7)
  self.invoke(0x53699fc4,(factory,))
  self.assertEqual(self.allocations,[0x58,0x44])
  self.assertEqual((self.word(factory+4),self.word(factory+8)),(self.worker,second))
  self.assertEqual(self.word(self.worker+0x44),0x42575431)
  self.assertEqual(self.word(self.worker+0x34),self.word(second+0x34))
 def test_dispatch_body_binds_exact_owned_job_then_clears_tail_before_notification(self):
  self.call(self.symbols['m10v_border_transfer_construct'],self.worker)
  self.observe_body=True;self.body_calls=0
  self.patch_bl(0x5369ac4c,self.symbols['border_recovery_transfer_body_hook'],0xebffff3d)
  self.invoke(0x5369abc8,(self.worker,self.job))
  self.assertEqual(self.body_calls,1)
  self.assertEqual(self.observed_tail,(0x42575431,self.client,self.job,1))
  self.assertEqual(tuple(self.word(self.worker+0x48+4*i) for i in range(3)),(0,0,0))
  self.assertEqual((self.word(self.client+36),self.word(self.client+44)),(0,1))
  self.assertEqual(self.signal_state,[(1,1,self.client+4,0x400)])
  self.assertIn(0x534aab0c,self.visited)
 def test_consumed_outer_event_yields_for_callback_tail_without_second_wait(self):
  self.pause_signal=True
  self.invoke(self.word(self.word(self.client)+8),(self.client,0x03050006,0),0x550dd000)
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x536a9d1c)
  self.assertEqual((self.word(self.client+36),self.word(self.client+40)),(1,1))
  callback=self.u.context_save();self.pause_signal=False
  self.wait_results=[(1,0x400)];self.stop_at_yield=True
  self.invoke(self.symbols['m10v_border_client_wait'],(self.client+4,0x400,0,0xffffffff))
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x536b0a74)
  outer=self.u.context_save();self.assertEqual(len(self.waits),1)
  self.u.context_restore(callback);self.u.reg_write(A.UC_ARM_REG_R0,1)
  self.u.reg_write(A.UC_ARM_REG_PC,self.u.reg_read(A.UC_ARM_REG_LR))
  self.u.emu_start(self.u.reg_read(A.UC_ARM_REG_PC),0x550ff000,count=10000)
  self.assertEqual((self.word(self.client+36),self.word(self.client+40)),(0,0))
  self.u.context_restore(outer);self.stop_at_yield=False;self.u.reg_write(A.UC_ARM_REG_R0,0)
  self.u.reg_write(A.UC_ARM_REG_PC,self.u.reg_read(A.UC_ARM_REG_LR))
  self.u.emu_start(self.u.reg_read(A.UC_ARM_REG_PC),0x550ff000,count=10000)
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x550ff000)
  self.assertEqual(len(self.waits),1,'consumed completion is not waited on a second time')
 def configure_other_owner(self,kind):
  fill=kind=='fill';offset=0x58 if fill else 0x48;tag=0x42465731 if fill else 0x42525731
  self.put(self.client+36,0);self.put(self.client+40,0)
  self.assertEqual(self.call(self.symbols['m10v_border_client_prepare'],self.client,0x03070004 if fill else 0x03020002,0x10 if fill else 0x40),1)
  self.call(self.symbols['m10v_border_'+kind+'_construct'],self.worker)
  self.put(self.worker+offset,tag,self.client,self.job,1);self.put(self.client+60,self.worker,self.job)
  return offset,tag
 def test_fill_and_resize_owned_constructor_tails_are_appended_not_padding(self):
  for kind,offset,tag in (('fill',0x58,0x42465731),('resize',0x48,0x42525731)):
   self.u.mem_write(self.worker+offset,b'\xa5'*20)
   self.call(self.symbols['m10v_border_'+kind+'_construct'],self.worker)
   self.assertEqual(self.word(self.worker+offset),tag)
   self.assertEqual(bytes(self.u.mem_read(self.worker+offset+4,12)),bytes(12))
   self.assertEqual(bytes(self.u.mem_read(self.worker+offset+16,4)),b'\xa5'*4)
 def test_original_fill_lower_prologue_proves_parent_worker_and_wait_retry(self):
  self.configure_other_owner('fill');context=0x55007000;self.put(self.worker+0x44,context)
  self.patch_bl(0x5376a370,self.symbols['border_recovery_fill_wait_hook'],0xebfcfec5)
  for caller_lr in (0x536591cc,0x53659258):
   self.u.reg_write(A.UC_ARM_REG_R0,context);self.u.reg_write(A.UC_ARM_REG_R5,self.worker)
   self.u.reg_write(A.UC_ARM_REG_SP,0x550ed000);self.u.reg_write(A.UC_ARM_REG_LR,caller_lr)
   self.u.emu_start(0x53769a78,0x53769a98,count=1000)
   frame=self.u.reg_read(A.UC_ARM_REG_FP)
   self.assertEqual((self.word(frame-4),self.word(frame-36)),(caller_lr,self.worker))
   self.u.reg_write(A.UC_ARM_REG_R6,context);self.u.reg_write(A.UC_ARM_REG_R9,context+0x20)
   self.u.reg_write(A.UC_ARM_REG_R8,1);self.u.reg_write(A.UC_ARM_REG_R10,0)
   self.wait_results=[(0,0),(1,1)];before=len(self.waits)
   self.u.emu_start(0x5376a358,0x5376a374,count=100000)
   self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x5376a374)
   self.assertEqual(len(self.waits)-before,2);self.assertEqual(self.reg(0),1)
   self.assertNotIn(0x5376ed74,self.visited)
 def test_unverified_fill_parent_lr_is_stock_single_wait_without_worker_dereference(self):
  context,frame=0x55007000,0x5500d000
  self.put(frame-4,0xdeadbeef);self.put(frame-36,0x70000000)
  self.wait_results=[(0,0)]
  self.invoke(self.symbols['m10v_border_fill_wait'],(context+0x20,1,0,19,frame,context))
  self.assertEqual(self.reg(0),0);self.assertEqual(self.waits,[(context+0x20,1,19)])
 def test_original_resize_lower_prologue_proves_parent_r7_and_context_before_retry(self):
  self.configure_other_owner('resize');context=0x55007000;params=0x55008000;self.put(self.worker+0x34,context)
  self.u.reg_write(A.UC_ARM_REG_C1_C0_2,0xf00000);self.u.reg_write(A.UC_ARM_REG_FPEXC,0x40000000)
  self.u.reg_write(A.UC_ARM_REG_R0,context);self.u.reg_write(A.UC_ARM_REG_R1,params);self.u.reg_write(A.UC_ARM_REG_R2,2)
  self.u.reg_write(A.UC_ARM_REG_R7,self.worker);self.u.reg_write(A.UC_ARM_REG_SP,0x550ed000);self.u.reg_write(A.UC_ARM_REG_LR,0x536733e4)
  self.u.emu_start(0x53770bf0,0x53770c28,count=1000)
  frame=self.u.reg_read(A.UC_ARM_REG_FP)
  self.assertEqual((self.word(frame-4),self.word(frame-28),self.word(frame-0x2d0)),(0x536733e4,self.worker,context))
  self.put(frame-0x2e0,4);self.u.reg_write(A.UC_ARM_REG_R9,context+0x48)
  self.patch_bl(0x5377160c,self.symbols['border_recovery_resize_wait_hook'],0xebfce21e)
  self.wait_results=[(0,0),(1,4)]
  self.u.emu_start(0x537715ec,0x53771610,count=100000)
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x53771610)
  self.assertEqual(len(self.waits),2);self.assertEqual(self.reg(0),1)
 def test_resize_equal_size_dma_shortcut_wait_is_also_guarded(self):
  self.configure_other_owner('resize')
  for pc,preimage in ((0x53673244,0xeb00db10),(0x5367331c,0xeb00dada),(0x53673384,0xeb00dac0)):
   self.patch_bl(pc,self.symbols['border_recovery_resize_dma_wait_hook'],preimage)
   self.wait_results=[(0,0),(1,3)];before=len(self.waits)
   for n,v in enumerate((self.worker+0x3c,3,0,0xffffffff)):self.u.reg_write(getattr(A,'UC_ARM_REG_R'+str(n)),v)
   self.u.reg_write(A.UC_ARM_REG_R7,self.worker);self.u.reg_write(A.UC_ARM_REG_SP,0x550ed000)
   self.u.emu_start(pc,pc+4,count=100000)
   self.assertEqual(self.reg(0),1);self.assertEqual(len(self.waits)-before,2)
 def test_original_fill_and_resize_dispatchers_bind_owned_tail_then_notify(self):
  for kind,entry,callsite,preimage,opcode,offset,eventmask in (
   ('fill',0x5365935c,0x536594a0,0xebfffed9,0x010e0004,0x58,0x10),
   ('resize',0x53673f48,0x53674014,0xebfffc1f,0x00708002,0x48,0x40)):
   self.configure_other_owner(kind);self.put(self.worker+offset+12,0)
   self.put(self.job+12,opcode);self.observe_other_body=True;self.body_calls=0;self.signal_state=[]
   self.stubs.update({0x536a2954:0,0x536a29b4:0})
   self.patch_bl(callsite,self.symbols['border_recovery_'+kind+'_body_hook'],preimage)
   self.invoke(entry,(self.worker,self.job))
   self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x550ff000)
   self.assertEqual(self.body_calls,1)
   self.assertEqual(self.observed_tail[1:],(self.client,self.job,1))
   self.assertEqual(self.word(self.worker+offset+12),0)
   self.assertEqual(self.signal_state,[(1,1,self.client+4,eventmask)])
   self.assertEqual(self.word(self.client+36),0)
 def test_fill_factory_prototype_extends_real_allocation_and_constructor(self):
  factory,iipfactory,context=0x55008000,0x55009000,0x5500a000
  self.put(iipfactory+0x3c,context);self.put(iipfactory+0x44,0x5500b000)
  self.stubs.update({0x537700a0:iipfactory,0x536b93d0:0,0x53658aec:1})
  self.allocations=[];self.heap_results=[self.worker]
  page=0x53658000;self.u.mem_protect(page,4096,UC_PROT_READ|UC_PROT_WRITE|UC_PROT_EXEC)
  self.assertEqual(self.word(0x536589fc),0xe3a00058);self.put(0x536589fc,0xe3a00068)
  self.u.mem_protect(page,4096,UC_PROT_READ|UC_PROT_EXEC)
  self.patch_bl(0x53658a08,self.symbols['m10v_border_fill_construct'],0xeb00009a)
  self.invoke(0x53658988,(factory,))
  self.assertEqual(self.allocations,[0x68]);self.assertEqual(self.word(factory+4),self.worker)
  self.assertEqual(self.word(self.worker+0x44),context);self.assertEqual(self.word(self.worker+0x58),0x42465731)
 def test_resize_factory_third_allocation_slice_grows_only_owned_resize_worker(self):
  self.assertEqual(self.word(0x53672adc),0xe3a00060)
  self.assertEqual(self.word(0x53672b4c),0xe3a0004c)
  self.allocations=[];self.heap_results=[self.worker]
  page=0x53672000;self.u.mem_protect(page,4096,UC_PROT_READ|UC_PROT_WRITE|UC_PROT_EXEC)
  self.assertEqual(self.word(0x53672bac),0xe3a00048);self.put(0x53672bac,0xe3a00058)
  self.u.mem_protect(page,4096,UC_PROT_READ|UC_PROT_EXEC)
  self.patch_bl(0x53672bb8,self.symbols['m10v_border_resize_construct'],0xeb000094)
  self.u.reg_write(A.UC_ARM_REG_SP,0x550fd000)
  self.u.emu_start(0x53672bac,0x53672bbc,count=10000)
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x53672bbc)
  self.assertEqual(self.allocations,[0x58]);self.assertEqual(self.word(self.worker+0x48),0x42525731)
 def test_stock_client_wait_is_exact_single_pass_even_on_error(self):
  stock=0x55009000;self.put(stock,0x53c5b680)
  self.wait_results=[(0,0)]
  self.invoke(self.symbols['m10v_border_client_wait'],(stock+4,0x400,0,23))
  self.assertEqual(self.reg(0),0);self.assertEqual(self.waits,[(stock+4,0x400,23)]);self.assertEqual(self.yields,0)
if __name__=='__main__':unittest.main(defaultTest='WaitGuard',verbosity=2)
