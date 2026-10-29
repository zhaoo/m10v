#!/usr/bin/env python3
"""Hash-locked ORIGINAL ARM IIP recovery evidence; no pixel or silicon emulation.
Run: shared .venv/bin/python scripts/border_recovery_contract.py
All hardware-facing register images are ordinary RAM. Explicit hooks replace
only logger, synchronization, and callback endpoints, never stop/status logic.
"""
from pathlib import Path
import hashlib, struct, unittest
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_PROT_READ, UC_PROT_EXEC
from unicorn import arm_const as A
ROOT=Path(__file__).resolve().parents[1]
SHA='8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67'
BASE=0x53000000
class RecoveryContract(unittest.TestCase):
 def setUp(self):
  b=(ROOT/'builds/gr3-extension-validation/official-rtos.bin').read_bytes()
  self.assertEqual(hashlib.sha256(b).hexdigest(),SHA)
  self.u=Uc(UC_ARCH_ARM,UC_MODE_ARM);self.u.ctl_set_cpu_model(A.UC_CPU_ARM_CORTEX_A9)
  self.u.mem_map(BASE,(len(b)+4095)&~4095);self.u.mem_write(BASE,b)
  self.u.mem_protect(BASE,(len(b)+4095)&~4095,UC_PROT_READ|UC_PROT_EXEC)
  self.u.mem_map(0x55000000,0x100000)
  self.visited=[];self.calls=[];self.stubs={0x536b82d4:0,0x536ae71c:0,0x536ae870:0}
  self.h=self.u.hook_add(UC_HOOK_CODE,self.hook)
 def reg(self,n):return self.u.reg_read(getattr(A,'UC_ARM_REG_R'+str(n)))
 def put(self,p,*v):self.u.mem_write(p,struct.pack('<'+'I'*len(v),*v))
 def word(self,p):return struct.unpack('<I',self.u.mem_read(p,4))[0]
 def hook(self,u,pc,size,data):
  self.visited.append(pc)
  if pc==0x536ae71c and hasattr(self,'stop_at_shared_lock'):
   self.assertEqual(self.reg(0),self.stop_at_shared_lock);u.emu_stop();return
  if pc==0x5376ef18 and hasattr(self,'second_status'):self.put(0x55004004,self.second_status)
  if pc in self.stubs:
   args=tuple(self.reg(i) for i in range(4));self.calls.append((pc,args))
   u.reg_write(A.UC_ARM_REG_R0,self.stubs[pc]);u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
 def call(self,pc,*args):
  for i,v in enumerate(args):self.u.reg_write(getattr(A,'UC_ARM_REG_R'+str(i)),v)
  self.u.reg_write(A.UC_ARM_REG_SP,0x550fd000);self.u.reg_write(A.UC_ARM_REG_LR,0x550ff000)
  self.u.emu_start(pc,0x550ff000,count=500000)
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x550ff000)
  return self.reg(0)
 def test_original_resolution_owner_cancel_executes_chain_without_ack(self):
  owner,svc,driver,regs=0x55001000,0x55002000,0x55003000,0x55004000
  self.put(owner+0x38,svc);self.put(svc+0x24,driver);self.put(driver+0x14,regs)
  for status in range(8):
   self.put(regs,0x12345678,status,0xa5a50003);self.visited.clear();self.calls.clear()
   self.call(0x537709b0,owner+8)
   for pc in (0x5377096c,0x5376daf0,0x5377876c):self.assertIn(pc,self.visited)
   self.assertEqual(bytes(self.u.mem_read(regs,12)),struct.pack('<III',0x12345678,status,0xa5a50000))
   self.assertEqual([c[0] for c in self.calls],[0x536b82d4])
   self.assertFalse({0x53778474,0x53778490,0x536a9e8c,0x536a9dd4}&set(self.visited))
 def test_axi_error_irq_only_logs_and_returns_no_stop(self):
  svc,driver,regs=0x55002000,0x55003000,0x55004000
  self.put(svc+0x24,driver);self.put(driver+0x14,regs)
  self.put(regs+0x140,0xfeed,0xface)
  self.put(regs+4,3,0xa5a50003)
  self.assertEqual(self.call(0x5376d0e8,svc,0x5a,4),0)
  self.assertEqual([c[0] for c in self.calls],[0x536b82d4])
  self.assertEqual(self.word(regs+4),3);self.assertEqual(self.word(regs+8),0xa5a50003)
  self.assertNotIn(0x5377876c,self.visited)
 def test_original_irq_completion_routes_to_current_owner_mask(self):
  svc=0x55002000;self.stubs[0x535628dc]=0
  for index in range(3):
   self.put(svc+0x100,*[1 if i==index else 0 for i in range(3)])
   self.calls.clear();self.visited.clear()
   self.assertEqual(self.call(0x5376d0e8,svc,0x5a,1),0)
   self.assertEqual([(pc,args[:3]) for pc,args in self.calls],[(0x535628dc,(svc+(0x3c,0x58,0x74)[index],0x02150001,0))])
   self.assertEqual(self.word(svc+0x100+4*index),1,'IRQ dispatch does not clear ownership mask')
 def test_original_singleton_and_pointer_wiring_alias_fill_and_graph_service(self):
  factory,svc,fill,graph,pipe,pipe_factory=0x5536f568,0x55002000,0x55007000,0x55008000,0x55009000,0x5500a000
  self.u.mem_map(0x5536f000,0x1000);self.put(0x5536f5b0,1)
  self.assertEqual(self.call(0x537700a0),factory)
  self.put(factory+4,svc);self.put(factory+0x3c,fill);self.put(factory+0x2c,graph)
  self.put(pipe_factory+4,pipe)
  def section(start,end,registers):
   for n,v in registers.items():self.u.reg_write(getattr(A,'UC_ARM_REG_R'+str(n)),v)
   self.u.emu_start(start,end,count=1000);self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),end)
  # Original setup stores FillContext+0xc from singleton factory+4.
  section(0x5376fef4,0x5376ff00,{4:factory})
  # Original setup stores graph-owner+4 from the SAME singleton factory+4.
  section(0x53770084,0x53770094,{4:factory})
  # Frame pipe factory stored singleton+0x3c in r8 before allocating the pipe.
  section(0x53658a30,0x53658a3c,{6:pipe_factory,8:self.word(factory+0x3c)})
  self.assertEqual(self.word(pipe+0x44),fill)
  self.assertEqual(self.word(self.word(pipe+0x44)+0xc),svc)
  self.assertEqual(self.word(graph+4),svc)
 def test_new_reservation_reaches_global_lock_before_count_or_owner_change(self):
  svc,driver,regs=0x55002000,0x55003000,0x55004000
  self.put(svc+0x24,driver);self.put(driver+0x14,regs);self.u.mem_write(svc+0xfc,b'\x01')
  self.put(svc+0x100,0x111,0x222,0x333)
  self.stop_at_shared_lock=svc+0x90
  self.stubs.update({0x536b00c8:1,0x5356284c:0})
  self.u.reg_write(A.UC_ARM_REG_R0,svc);self.u.reg_write(A.UC_ARM_REG_R1,0x55007000)
  self.u.reg_write(A.UC_ARM_REG_R2,1);self.u.reg_write(A.UC_ARM_REG_R3,0)
  self.u.reg_write(A.UC_ARM_REG_SP,0x550fd000);self.u.reg_write(A.UC_ARM_REG_LR,0x550ff000)
  self.u.emu_start(0x5376ebd0,0x550ff000,count=1000)
  self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x536ae71c)
  self.assertEqual(bytes(self.u.mem_read(svc+0xfc,1)),b'\x01')
  self.assertEqual([self.word(svc+0x100+i*4) for i in range(3)],[0x111,0x222,0x333])
  self.assertEqual([(args[0],args[1]) for pc,args in self.calls if pc==0x536b00c8],[(svc+0xcc,0xffffffff),(svc+0xcc,0xffffffff),(svc+0xd8,0xffffffff)])
  del self.stop_at_shared_lock
 def test_submit_overwrites_owner_mask_before_shared_lock_acquisition(self):
  svc,info=0x55002000,0x55006000
  self.stop_at_shared_lock=svc+0xa4
  for index in range(3):
   self.put(svc+0x100,0,0,0);self.u.mem_write(info+3,bytes([index]));self.put(info+0x78,0x1234)
   self.u.reg_write(A.UC_ARM_REG_R0,svc);self.u.reg_write(A.UC_ARM_REG_R1,info)
   self.u.reg_write(A.UC_ARM_REG_SP,0x550fd000);self.u.reg_write(A.UC_ARM_REG_LR,0x550ff000)
   self.u.emu_start(0x5376e55c,0x550ff000,count=1000)
   self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC),0x536ae71c)
   self.assertEqual([self.word(svc+0x100+i*4) for i in range(3)],[0x1234 if i==index else 0 for i in range(3)])
  del self.stop_at_shared_lock
 def test_release_real_driver_predicates_distinguish_two_observations(self):
  svc,driver,regs,info=0x55002000,0x55003000,0x55004000,0x55006000
  self.stubs.update({p:0 for p in (0x536a848c,0x536a8544,0x53562910,0x536b0014,
   0x53784de0,0x5376eb2c,0x536b93d0,0x536b0a74)})
  for first_status,second_status,lines in ((4,4,[]),(5,5,[]),(6,6,[]),(7,4,[]),
       (0,4,[0x348]),(4,7,[0x354])):
   self.u.mem_write(svc,bytes(0x120));self.u.mem_write(info,bytes(0x80))
   self.put(svc+0x24,driver);self.put(driver+0x14,regs)
   self.u.mem_write(svc+0xfc,b'\x01');self.u.mem_write(info+0x74,b'\x01')
   self.put(regs+4,first_status,0xa5a50003);self.second_status=second_status
   self.visited.clear();self.calls.clear();self.call(0x5376ed74,svc,0,info)
   self.assertEqual([args[3] for pc,args in self.calls if pc==0x536b93d0 and args[0]==0],lines)
   self.assertEqual(self.visited.count(0x53778490),5002 if first_status==0 else 1)
   self.assertEqual(self.visited.count(0x53778474),5002 if second_status==7 else 1)
   self.assertIn(0x5376ef2c,self.visited,'cleanup executes even after failed observation')
  del self.second_status
 def test_original_service_initialization_returns_success_without_idle_ack(self):
  svc,driver,regs,top=0x55002000,0x55003000,0x55004000,0x55005000
  self.put(svc+0x24,driver);self.put(svc+0x38,top);self.put(driver+0x14,regs)
  self.put(regs+4,3,0xa5a50003)
  # These are top-control CONFIGURATION backends, not simulated reset responses.
  self.stubs.update({0x5377c4d4:0,0x5377d780:0})
  self.assertEqual(self.call(0x5376cffc,svc),1)
  self.assertEqual(self.word(regs+4)&7,3)
  self.assertEqual(self.word(regs+8),0xa5a50003)
  self.assertFalse({0x53778474,0x53778490,0x536a9e8c}&set(self.visited))
  self.assertEqual([(p,a[:3]) for p,a in self.calls if p==0x5377c4d4],[(0x5377c4d4,(top,15,1)),(0x5377c4d4,(top,15,0))])
 def test_macro_disable_is_reference_counted_configuration_not_ack(self):
  svc,top=0x55002000,0x55005000;self.put(svc+0x38,top)
  self.stubs[0x5377c4d4]=0
  self.put(svc+0x10c,2);self.call(0x5376eb2c,svc,0)
  self.assertEqual(self.word(svc+0x10c),1);self.assertNotIn(0x5377c4d4,self.visited)
  self.visited.clear();self.call(0x5376eb2c,svc,0)
  self.assertEqual(self.word(svc+0x10c),0);self.assertIn(0x5377c4d4,self.visited)
  self.assertFalse({0x53778474,0x53778490,0x536a9e8c}&set(self.visited))
def disassemble():
 from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM
 b=(ROOT/'builds/gr3-extension-validation/official-rtos.bin').read_bytes()
 assert hashlib.sha256(b).hexdigest()==SHA
 print('GR III 2.10 ORIGINAL RTOS SHA256',SHA)
 m=Cs(CS_ARCH_ARM,CS_MODE_ARM)
 for title,start,end in [
  ('reserve_capacity_and_category_start',0x5376ebd0,0x5376ec28),
  ('reserve_global_lock_and_count',0x5376ec8c,0x5376ecf4),
  ('reserve_category0',0x5376ed00,0x5376ed28),
  ('singleton_factory',0x537700a0,0x5377014c),
  ('frame_pipe_factory_root',0x53658988,0x53658a5c),
  ('factory_one_iipservice',0x5376fcf4,0x5376fd5c),
  ('factory_fillcontext_root',0x5376feac,0x5376ff00),
  ('factory_graphowner_root',0x53770030,0x53770094),
  ('fill_pipe_lock_scope',0x536590d0,0x53659120),
  ('fill_pipe_unlock',0x53659228,0x53659258),
  ('fill_wait_pre_release_hook',0x5376a338,0x5376a3b4),
  ('submit_lock_after_owner_write_entry',0x5376e55c,0x5376e5d0),
  ('submit_owner_write0_1',0x5376e858,0x5376e870),
  ('submit_owner_write2',0x5376e7d8,0x5376e7e4),
  ('submit_unlock',0x5376e7c8,0x5376e7d8),
  ('resolution_owner_cancel',0x5377096c,0x537709b8),
  ('service_abort_forward',0x5376daf0,0x5376dafc),
  ('driver_abort_no_ack',0x5377876c,0x537787dc),
  ('service_initialization',0x5376cffc,0x5376d0e8),
  ('irq_dispatch_and_axi_error',0x5376d0e8,0x5376d198),
  ('irq_owner_completion',0x5376d4fc,0x5376d514),
  ('macro_reference_count',0x5376eb2c,0x5376ebd0),
  ('release_idle_polls',0x5376eec0,0x5376ef70),
  ('release_timeout_continue',0x5376f118,0x5376f160),
  ('driver_status_command_and_predicates',0x53778458,0x537784a4),
  ('driver_factory_register_roots',0x537797a8,0x537797cc),
  ('clock_backend',0x5377f548,0x5377f6b8),
 ]:
  print('\n'+title,hex(start),hex(end),'range_sha256',hashlib.sha256(b[start-BASE:end-BASE]).hexdigest())
  for i in m.disasm(b[start-BASE:end-BASE],start):print(f'{i.address:08x} {i.bytes.hex():8s} {i.mnemonic:8s} {i.op_str}')
if __name__=='__main__':
 import sys
 if sys.argv[1:]==['--disassemble']:disassemble()
 else:unittest.main(verbosity=2)
