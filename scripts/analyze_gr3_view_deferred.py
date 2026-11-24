"""Execute original stock failing stop-reply sequence and patched retry in ARM."""
from pathlib import Path
import importlib.util,struct,tempfile
ROOT=Path(__file__).resolve().parents[1]
def main(delivery=None):
 from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
 import unicorn.arm_const as arm
 from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_LR,UC_ARM_REG_SP,UC_ARM_REG_PC
 spec=importlib.util.spec_from_file_location('builder',ROOT/'scripts/build_gr3_view_deferred.py');builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
 delivered=None
 if delivery:
  import json,subprocess,hashlib
  delivery=Path(delivery).resolve()
  manifest=json.loads((delivery/'M10V-runtime-manifest.json').read_text())['capture_lifecycle']['view_deferred']
  js="import {readFileSync} from 'node:fs';import {decodeFrameMap} from './node/gr3-frames.mjs';let b=readFileSync(process.argv[1]),d=decodeFrameMap(b,b.readUInt32LE(b.length-8)).decoded;process.stdout.write(d.subarray(0x10870,0x10870+d.readUInt32LE(0x1086c)));"
  delivered=subprocess.check_output(['node','--input-type=module','-e',js,str(delivery/'fwdc239b.bin')],cwd=ROOT)
  start=manifest['base']-0x53000000
  assert hashlib.sha256(delivered[start:start+manifest['bytes']]).hexdigest()==manifest['sha256']
  for p in manifest['patches']:assert delivered[p['address']-0x53000000:p['address']-0x53000000+4]==bytes.fromhex(p['replacement_hex'])
 else:
  with tempfile.TemporaryDirectory() as d:blob,manifest=builder.build(d)
 raw=(ROOT/'builds/gr3-extension-validation/official-rtos.bin').read_bytes()
 for patched in (False,True):
  image=delivered if patched and delivered is not None else raw
  u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0x53000000,(len(image)+4095)&~4095);u.mem_write(0x53000000,image)
  u.mem_map(0x55060000,0x10000);u.mem_map(0x58000000,0x10000);u.mem_map(0x58100000,0x10000)
  if delivered is None:
   u.mem_map(manifest['base'],0x2000);u.mem_write(manifest['base'],blob)
  elif not patched:
   # Stock comparison uses the same delivered observer helper at its real VA.
   u.mem_map(manifest['base']&~4095,0x2000);u.mem_write(manifest['base'],delivered[start:start+manifest['bytes']])
  if patched and delivered is None:
   for p in manifest['patches']:u.mem_write(p['address'],bytes.fromhex(p['replacement_hex']))
  u.reg_write(arm.UC_ARM_REG_FPEXC,0x40000000)
  q,model,msg,stop=0x58000000,0x55067958,0x58001000,0x5810fff0
  def put(a,v):u.mem_write(a,struct.pack('<I',v))
  put(0x55064398,1);put(model,0x53b4e7b0);put(0x55063910,1);put(0x550639ec,q);put(q,0x53b41380)
  transitions=[];posts=[];watch=[0]
  def hook(uc,a,size,data):
   if a==stop or a==watch[0]:uc.emu_stop();return
   # Explicit hardware-independent UI/OS boundaries. Real busy getter,
   # completion handler, dispatcher and stop-response bytes execute unchanged.
   if watch[0] and (a in (manifest['exports']['m10v_view_deferred_on_enter'],manifest['exports']['m10v_view_deferred_on_capture_start'],manifest['exports']['m10v_view_deferred_on_stop_reply'],manifest['exports']['m10v_view_deferred_on_producer']) or a==0x531cb7bc):
    for i in range(32):uc.reg_write(getattr(arm,'UC_ARM_REG_D'+str(i)),0xdeadbeef00000000+i)
    uc.reg_write(arm.UC_ARM_REG_FPSCR,0x00400000)
   if a in (0x5320ad88,0x5320aefc,0x53239ad8,0x531caa7c,0x5320b73c,0x532af2c8):
    uc.reg_write(UC_ARM_REG_R0,0);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
   elif a==0x532288b0:
    posts.append(uc.reg_read(UC_ARM_REG_R1));uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
   elif a==0x531cb7bc:
    obj,state=uc.reg_read(UC_ARM_REG_R0),uc.reg_read(UC_ARM_REG_R1);transitions.append(state);uc.mem_write(obj+0x16c,bytes([state]));uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
  u.hook_add(UC_HOOK_CODE,hook)
  def run(pc,obj=q,arg=msg):
   u.reg_write(UC_ARM_REG_R0,obj);u.reg_write(UC_ARM_REG_R1,arg);u.reg_write(UC_ARM_REG_SP,0x5810ff00);u.reg_write(UC_ARM_REG_LR,stop)

   try:u.emu_start(pc,stop+4,count=200000)
   except Exception as e:raise RuntimeError(f'patched={patched} pc={u.reg_read(UC_ARM_REG_PC):08x} entry={pc:08x}') from e
   assert u.reg_read(UC_ARM_REG_PC)==stop
  def reset():
   u.mem_write(q+0x16c,b'\x02');u.mem_write(model+0x2f,b'\x00\x01\x00');put(msg,0x169);put(msg+4,0);posts.clear();transitions.clear()
   run(manifest['exports']['m10v_view_deferred_on_enter'])
  reset();run(0x53236734,model);posts.clear();run(0x531cbfc4)
  assert bytes(u.mem_read(q+0x16c,1))==b'\x02' and not transitions
  # Real native stop-response clear must remain present, not manufactured.
  run(0x53239b80,model)
  assert bytes(u.mem_read(model+0x30,1))==b'\x00'
  assert bytes(u.mem_read(q+0x16c,1))==(b'\x00' if patched else b'\x02')
  assert transitions==([0] if patched else [])
  assert posts==([0x15d,0xf1] if patched else [0x15d])
  if patched:
   # Native producer queues169 BEFORE clearing31/2f. Permit the genuine
   # dispatcher to run at that exact instruction boundary, then resume the
   # producer and deliver its genuine stop reply. No busy flag is cleared by
   # the harness: the original instructions at36778/3677c do the clearing.
   reset();u.mem_write(model+0x2f,b'\x01\x01\x01')
   watch[0]=0x5323676c
   u.reg_write(UC_ARM_REG_R0,model);u.reg_write(UC_ARM_REG_SP,0x5810ff00);u.reg_write(UC_ARM_REG_LR,stop)
   u.emu_start(0x53236734,stop+4,count=200000)
   assert u.reg_read(UC_ARM_REG_PC)==watch[0]
   saved_regs=[getattr(arm,'UC_ARM_REG_R'+str(i)) for i in range(13)]+[UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC,arm.UC_ARM_REG_CPSR]
   saved=[u.reg_read(r) for r in saved_regs];watch[0]=0
   # Separate dispatcher stack models scheduling at the asynchronous sender.
   u.reg_write(UC_ARM_REG_R0,q);u.reg_write(UC_ARM_REG_R1,msg)
   u.reg_write(UC_ARM_REG_SP,0x5810ef00);u.reg_write(UC_ARM_REG_LR,stop)
   u.emu_start(0x531cbfc4,stop+4,count=200000)
   assert bytes(u.mem_read(q+0x16c,1))==b'\x02'
   for r,v in zip(saved_regs,saved):u.reg_write(r,v)
   u.emu_start(0x5323676c,stop+4,count=200000)
   assert bytes(u.mem_read(model+0x2f,3))==b'\x00\x01\x00'
   posts.clear();run(0x53239b80,model)
   assert transitions==[0], 'native169 delivered before producer clears31/2f was lost'
   assert posts==[0x15d,0xf1]
   # Re-enter or a fresh native capture invalidates pending prior completion.
   for invalidate in ('m10v_view_deferred_on_enter','m10v_view_deferred_on_capture_start'):
    reset();run(0x53236734,model);posts.clear();run(0x531cbfc4);run(manifest['exports'][invalidate],q if invalidate.endswith('enter') else model)
    run(0x53239b80,model);assert not transitions and bytes(u.mem_read(q+0x16c,1))==b'\x02'
   # A completion queued BEFORE a new capture start cannot attach to it.
   reset();run(0x53236734,model);posts.clear();run(manifest['exports']['m10v_view_deferred_on_capture_start'],model)
   run(0x531cbfc4);run(0x53239b80,model);assert not transitions
   # Without an actual native completion producer,169 alone cannot authorize retry.
   reset();run(0x531cbfc4);run(0x53239b80,model);assert not transitions
   # Duplicate response cannot replay completion twice.
   reset();run(0x53236734,model);posts.clear();run(0x531cbfc4);run(0x53239b80,model);run(0x53239b80,model);assert transitions==[0]
   # Exact instruction-boundary wrappers preserve all GPR/LR/SP/NZCV.
   import unicorn.arm_const as arm
   regs=[getattr(arm,'UC_ARM_REG_R'+str(i)) for i in range(13)]+[arm.UC_ARM_REG_LR,arm.UC_ARM_REG_SP]
   for site,cont,source in [(0x531cbdf0,0x531cbdf4,0),(0x5323abf8,0x5323abfc,0),(0x53239bc0,0x53239bc4,4)]:
    reset()
    for i,r in enumerate(regs):u.reg_write(r,0x10100000+i*0x100)
    u.reg_write(regs[source],q if site==0x531cbdf0 else model)
    u.reg_write(arm.UC_ARM_REG_R2,1);u.reg_write(arm.UC_ARM_REG_R3,6 if site==0x531cbdf0 else 0)
    u.reg_write(arm.UC_ARM_REG_SP,0x5810ff00);u.reg_write(arm.UC_ARM_REG_CPSR,(u.reg_read(arm.UC_ARM_REG_CPSR)&0x0fffffff)|0xa0000000)
    # Reply helper must actually call original completion and its clobbering UI service.
    if site==0x53239bc0:
     generation=struct.unpack('<I',u.mem_read(q+0x188,4))[0];put(q+0x18c,generation);put(q+0x190,generation)
    for i in range(32):u.reg_write(getattr(arm,'UC_ARM_REG_D'+str(i)),0x1234567800000000+i)
    u.reg_write(arm.UC_ARM_REG_FPSCR,0x01000000)
    fp_before=[u.reg_read(getattr(arm,'UC_ARM_REG_D'+str(i))) for i in range(32)]
    before=[u.reg_read(r) for r in regs];flags=u.reg_read(arm.UC_ARM_REG_CPSR)&0xf0000000
    watch[0]=cont
    try:u.emu_start(site,stop+4,count=200000)
    except Exception as e:raise RuntimeError(f"ABI site={site:08x} pc={u.reg_read(UC_ARM_REG_PC):08x}") from e
    assert u.reg_read(UC_ARM_REG_PC)==cont and [u.reg_read(r) for r in regs]==before
    assert u.reg_read(arm.UC_ARM_REG_CPSR)&0xf0000000==flags
    assert [u.reg_read(getattr(arm,'UC_ARM_REG_D'+str(i))) for i in range(32)]==fp_before
    assert u.reg_read(arm.UC_ARM_REG_FPSCR)==0x01000000
   # Producer is a BL boundary followed by original sender tail call; its
   # added pre-publication helper must preserve all incoming FP state as well.
   watch[0]=0;reset()
   for i,r in enumerate(regs):u.reg_write(r,0x10200000+i*0x100)
   u.reg_write(arm.UC_ARM_REG_R4,model);u.reg_write(arm.UC_ARM_REG_LR,stop);u.reg_write(arm.UC_ARM_REG_SP,0x5810ff00)
   for i in range(32):u.reg_write(getattr(arm,'UC_ARM_REG_D'+str(i)),0x1234567800000000+i)
   u.reg_write(arm.UC_ARM_REG_FPSCR,0x01000000)
   fp_before=[u.reg_read(getattr(arm,'UC_ARM_REG_D'+str(i))) for i in range(32)]
   before=[u.reg_read(r) for r in regs];watch[0]=stop
   u.emu_start(manifest['exports']['m10v_view_hook_producer'],stop+4,count=200000)
   assert [u.reg_read(r) for r in regs]==before
   assert [u.reg_read(getattr(arm,'UC_ARM_REG_D'+str(i))) for i in range(32)]==fp_before
   assert u.reg_read(arm.UC_ARM_REG_FPSCR)==0x01000000
 print('PASS: native169-before-clear31/2f interleaving recovered; stock ARM retains QuickView state2 after busy169+stop reply; patched ARM performs one native completion, invalidates on reentry/new capture, rejects duplicate reply. UI/OS services stubbed; no hardware claim.')
if __name__=='__main__':
 import sys
 main(sys.argv[1] if len(sys.argv)>1 else None)
