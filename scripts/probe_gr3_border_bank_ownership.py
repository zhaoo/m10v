"""Execute original ARM developed-YUV bank ownership; never patch firmware.

Pool alloc/free and unrelated logging/thumbnail-size services are boundaries.
Registry, request-size, id5 assignment, native manager counters and release
instructions execute from the hash-locked original RTOS.
"""
import argparse, hashlib, json, struct
from pathlib import Path
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import *

SHA='8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67'

def probe(blob):
 assert hashlib.sha256(blob).hexdigest()==SHA,'Original GR III2.10 RTOS required'
 u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0x53000000,(len(blob)+4095)&~4095);u.mem_write(0x53000000,blob);u.mem_map(0x55000000,0x20000)
 recipe,manager=0x55000000,0x55010000;allocations=[];frees=[]
 def put(a,v):u.mem_write(a,struct.pack('<I',v))
 def get(a):return struct.unpack('<I',u.mem_read(a,4))[0]
 def service(u,a,n,d):
  if a==0x536a27e8:
   allocations.append({'bytes':u.reg_read(UC_ARM_REG_R1),'policy':u.reg_read(UC_ARM_REG_R2)})
   u.reg_write(UC_ARM_REG_R0,0x60000000+(len(allocations)-1)*0x5000000)
  elif a==0x536a248c:frees.append(u.reg_read(UC_ARM_REG_R1));u.reg_write(UC_ARM_REG_R0,1)
  elif a==0x536a2424:u.reg_write(UC_ARM_REG_R0,0x55018000)
  elif a==0x536a2f10:
   u.mem_write(u.reg_read(UC_ARM_REG_R1),struct.pack('<H',160));u.mem_write(u.reg_read(UC_ARM_REG_R2),struct.pack('<H',120))
  elif a in (0x536b93d0,0x536b9f1c,0x536b82d4):u.reg_write(UC_ARM_REG_R0,0)
  else:return
  u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
 u.hook_add(UC_HOOK_CODE,service)
 def call(a,*args):
  for i,r in enumerate((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)):u.reg_write(r,args[i] if len(args)>i else 0)
  u.reg_write(UC_ARM_REG_SP,0x5501f000);u.reg_write(UC_ARM_REG_LR,0x5501ff00)
  try:u.emu_start(a,0x5501ff00,count=100000)
  except Exception as e:raise RuntimeError(f'Original ARM entry {a:#x} failed at {u.reg_read(UC_ARM_REG_PC):#x}') from e
  assert u.reg_read(UC_ARM_REG_PC)==0x5501ff00,'Instruction budget exhausted'
  return u.reg_read(UC_ARM_REG_R0)
 put(recipe,0x53d0fc90);u.mem_write(recipe+0x2dd,b'\x01');put(recipe+0x364,0x4000000)
 u.mem_write(recipe+0x252,struct.pack('<8H',6016,0,6000,4000,0,720,480,720))
 call(0x53520ea8,manager);assert get(manager+4)==1 and get(manager+8)==2
 assert call(0x5352125c,manager,recipe)==1
 assert get(manager+4)==2
 assert call(0x535216d0,manager,recipe,5,0)==1
 assert get(manager+4)==1 and get(recipe+0x304)==0x60000000 and get(manager+0x14)==1
 call(0x53521d14,manager,recipe,5)
 assert get(recipe+0x304)==0 and get(manager+0xc)==0x60000000 and get(manager+0x14)==0 and not frees
 put(recipe+0x364,0x8000000)
 assert call(0x5352125c,manager,recipe)==1
 assert call(0x535216d0,manager,recipe,5,0)==1
 assert len(allocations)==2 and all(r['bytes']==0x4000000 for r in allocations)
 retained=[get(manager+0xc),get(manager+0x10)];normal_frees=list(frees)
 # Deliberate counter-zero negative control, not a claimed native UI event.
 # It proves the no-free result above comes from the original manager hold.
 put(manager+4,0);call(0x53521d14,manager,recipe,5)
 assert frees==retained and get(manager+0xc)==0 and get(manager+0x10)==0
 return {'rtos_sha256':SHA,'public_id':5,'recipe_backing_offset':0x304,'recipe_size_offset':0x364,
         'native_bank_pointers':retained,'allocations':allocations,'physical_frees_after_normal_release':normal_frees,
         'physical_frees_after_forced_counter_zero':frees,
         'checks':{'manager_baseline_hold':True,'register_acquire_counter_balanced':True,'recipe_release_keeps_native_bank':True,
                   'later_larger_query_does_not_resize_existing_bank':True,'counter_zero_negative_control_frees_both_banks':True},
         'limitations':['Pool alloc/free are intercepted; actual pool, DMA, UI concurrency and camera are not executed.',
                       'Synthetic request sizes prove native cache reuse policy, not accepted image capacity.',
                       'No per-view refcount inferred; stop/reuse ordering remains a separate integration obligation.']}

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--rtos',type=Path,required=True);p.add_argument('--output',type=Path)
 a=p.parse_args();r=probe(a.rtos.read_bytes());s=json.dumps(r,indent=2)+'\n'
 if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(s)
 print(s,end='')

if __name__=='__main__':main()
