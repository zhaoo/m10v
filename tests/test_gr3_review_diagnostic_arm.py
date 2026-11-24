"""Read-only JPEG boundary observers; native wait ownership stays unchanged."""
from pathlib import Path
import struct
import json
import os
import subprocess
import unittest
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm_const as A
from scripts.build_gr3_roll_capture import build_observers, CAPTURE_API
ROOT=Path(__file__).resolve().parents[1]
class ReviewDiagnosticArmTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.stock=(ROOT/'builds/gr3-extension-validation/official-rtos.bin').read_bytes()
  candidate=os.environ.get('M10V_REVIEW_DIAGNOSTIC_CANDIDATE')
  if candidate:
   folder=Path(candidate);manifest=json.loads((folder/'M10V-runtime-manifest.json').read_text())
   receipt=json.loads((folder/'M10V-build-receipt.json').read_text())
   import hashlib
   binary=folder/receipt['filename']
   assert hashlib.sha256(binary.read_bytes()).hexdigest()==receipt['candidate_sha256']
   js="import{readFileSync}from'node:fs';import{decodeFrameMap}from'./node/gr3-frames.mjs';const b=readFileSync(process.argv[1]),d=decodeFrameMap(b,b.readUInt32LE(b.length-8)).decoded;process.stdout.write(d.subarray(0x10870,0x10870+d.readUInt32LE(0x1086c)));"
   image=subprocess.check_output(['node','--input-type=module','-e',js,str(binary)],cwd=ROOT)
   cls.report=manifest['roll_capture'];at=cls.report['base']-0x53000000
   cls.code=image[at:at+cls.report['bytes']];cls.imports=manifest['symbols']
   assert hashlib.sha256(cls.code).hexdigest()==cls.report['sha256']
   for p in cls.report['patches']:assert image[p['address']-0x53000000:p['address']-0x53000000+4]==struct.pack('<I',p['replacement'])
   return
  # Explicit function-boundary tokens, not candidate overlays or ROM guesses.
  # JPEG observer tests call only the channel getter; other imports stay idle.
  names=(*CAPTURE_API,'m10v_roll_device_capture_channel','m10v_film_identity_owned',
         'm10v_film_identity_read','m10v_recorded_film_read')
  cls.imports={name:0x54380000+i*4 for i,name in enumerate(names)}
  cls.code,cls.report=build_observers(cls.stock,0x54400000,cls.imports,debug=True)
 def machine(self):
  u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0x53000000,0x1500000);u.mem_write(0x53000000,self.stock);u.mem_write(self.report['base'],self.code)
  u.mem_map(0x56000000,0x10000);u.mem_map(0x57000000,0x10000)
  u.reg_write(A.UC_ARM_REG_FPEXC,0x40000000)
  channel,context,main,extra=0x56002000,0x56001000,0x56003000,0x56003100
  def put(at,value):u.mem_write(at,struct.pack('<I',value))
  put(context+0x50,main);put(context+0x54,extra);put(main+12,123456);put(extra+12,789)
  events=[]
  def hook(uc,at,size,_):
   if at==self.imports['m10v_roll_device_capture_channel']:
    for i in range(32):uc.reg_write(getattr(A,'UC_ARM_REG_D'+str(i)),0xdead0000+i)
    uc.reg_write(A.UC_ARM_REG_FPSCR,0x00400000)
    uc.reg_write(A.UC_ARM_REG_R0,channel);uc.reg_write(A.UC_ARM_REG_PC,uc.reg_read(A.UC_ARM_REG_LR))
   elif at==0x536a9e8c:
    events.append(('native-wait',uc.reg_read(A.UC_ARM_REG_SP)))
    uc.reg_write(A.UC_ARM_REG_PC,uc.reg_read(A.UC_ARM_REG_LR))
   elif at==0x5320ad88:
    events.append(('native-root',uc.reg_read(A.UC_ARM_REG_SP)));uc.reg_write(A.UC_ARM_REG_PC,uc.reg_read(A.UC_ARM_REG_LR))
   elif at in (0x53504948,0x53504950,0x535180c4,0x534bbeb8,0x534bbee4,0x534bbf04,0x535211f4,0x532d5470):uc.emu_stop()
   elif at in (0x535847d8,0x536af2a8,0x536af31c):self.fail('diagnostic attempted filesystem/allocation')
  u.hook_add(UC_HOOK_CODE,hook)
  return u,channel,context,events
 def run_site(self,site):
  u,channel,context,events=self.machine()
  p=next(p for p in self.report['patches'] if p['address']==site)
  u.mem_write(site,struct.pack('<I',p['replacement']))
  regs=[getattr(A,'UC_ARM_REG_R'+str(i))for i in range(13)]
  for i,r in enumerate(regs):u.reg_write(r,0x10000000+i)
  u.reg_write(A.UC_ARM_REG_R4,context);u.reg_write(A.UC_ARM_REG_SP,0x5700ff00)
  for i in range(32):u.reg_write(getattr(A,'UC_ARM_REG_D'+str(i)),0x1234567800000000+i)
  u.reg_write(A.UC_ARM_REG_FPSCR,0x01000000)
  before=[u.reg_read(r)for r in regs];fp=[u.reg_read(getattr(A,'UC_ARM_REG_D'+str(i)))for i in range(32)]
  u.emu_start(site,0x5700fff4,count=50000)
  expected=before[:]
  if site==0x5350494c:expected[3]=0x56003000
  self.assertEqual([u.reg_read(r)for r in regs],expected)
  self.assertEqual(u.reg_read(A.UC_ARM_REG_SP),0x5700ff00)
  self.assertEqual([u.reg_read(getattr(A,'UC_ARM_REG_D'+str(i)))for i in range(32)],fp)
  self.assertEqual(u.reg_read(A.UC_ARM_REG_FPSCR),0x01000000)
  return struct.unpack('<5I',u.mem_read(channel+140,20)),events
 def test_before_wait_only_counts_and_preserves_original_native_wait(self):
  facts,events=self.run_site(0x53504944)
  self.assertEqual(facts,(1,0,0x56001000,0,0));self.assertEqual(events,[('native-wait',0x5700ff00)])
 def test_after_wait_reads_only_two_descriptor_lengths(self):
  facts,events=self.run_site(0x5350494c)
  self.assertEqual(facts,(0,1,0x56001000,123456,789));self.assertEqual(events,[])
 def test_six_real_handoffs_preserve_abi_and_copy_only_scalar_metadata(self):
  sites=(0x535180c0,0x534bbeb4,0x534bbee0,0x534bbf00,0x535211f0,0x532d546c)
  for stage,site in enumerate(sites,1):
   with self.subTest(stage=stage):
    u,channel,context,events=self.machine()
    def put(at,v):u.mem_write(at,struct.pack('<I',v))
    words=tuple(range(10,18));source=0x56003000
    owner=0x56004000;sp=0x5700fc00;fp=0x5700fd00
    regs=[getattr(A,'UC_ARM_REG_R'+str(i))for i in range(13)]
    for i,r in enumerate(regs):u.reg_write(r,0x10000000+i)
    u.reg_write(A.UC_ARM_REG_SP,sp);u.reg_write(A.UC_ARM_REG_R11,fp)
    u.reg_write(A.UC_ARM_REG_R4,owner)
    if stage==1:
     u.reg_write(A.UC_ARM_REG_R8,source-4);u.reg_write(A.UC_ARM_REG_R10,context);value=context
     put(context+0x304,0x62000000);put(context+0x364,72000000)
     for n,off in enumerate((0x38,0x40,0x44,0x48,0x4c)):put(owner+off,20+n)
    elif stage==2:u.reg_write(A.UC_ARM_REG_R6,source);value=owner
    elif stage==3:source=fp-0x68;u.reg_write(A.UC_ARM_REG_R0,0);value=0
    elif stage==4:put(owner+12,source);u.reg_write(A.UC_ARM_REG_R0,1);value=1
    elif stage==5:source=context;u.reg_write(A.UC_ARM_REG_R0,context);value=0x62000000;u.reg_write(A.UC_ARM_REG_R2,value)
    else:source=owner+4;u.reg_write(A.UC_ARM_REG_R5,owner);value=owner
    u.mem_write(source,struct.pack('<8I',*words))
    p=next(p for p in self.report['patches']if p['address']==site);u.mem_write(site,struct.pack('<I',p['replacement']))
    before=[u.reg_read(r)for r in regs]
    u.reg_write(A.UC_ARM_REG_CPSR,(u.reg_read(A.UC_ARM_REG_CPSR)&0xfffffff)|0xa0000000)
    for i in range(32):u.reg_write(getattr(A,'UC_ARM_REG_D'+str(i)),0x1234567800000000+i)
    u.reg_write(A.UC_ARM_REG_FPSCR,0x01000000)
    fp_before=[u.reg_read(getattr(A,'UC_ARM_REG_D'+str(i)))for i in range(32)]
    u.emu_start(site,0x5700fff4,count=50000)
    expected=before[:]
    if stage==1:expected[3]=1
    elif stage==2:expected[1]=before[8]
    elif stage in (3,4):expected[6]=before[0]
    elif stage==5:expected[3]=words[2]
    self.assertEqual([u.reg_read(r)for r in regs],expected)
    self.assertEqual(u.reg_read(A.UC_ARM_REG_SP),sp)
    self.assertEqual(u.reg_read(A.UC_ARM_REG_CPSR)&0xf0000000,0x60000000 if stage==3 else 0xa0000000)
    self.assertEqual([u.reg_read(getattr(A,'UC_ARM_REG_D'+str(i)))for i in range(32)],fp_before)
    self.assertEqual(u.reg_read(A.UC_ARM_REG_FPSCR),0x01000000)
    self.assertEqual(struct.unpack('<10I',u.mem_read(channel+160+(stage-1)*40,40)),(2,value,*words))
    self.assertEqual(bytes(u.mem_read(source,32)),struct.pack('<8I',*words))
    if stage==1:self.assertEqual(struct.unpack('<7I',u.mem_read(channel+400,28)),(0x62000000,72000000,20,21,22,23,24))
    self.assertEqual(events,[('native-root',sp)]if stage==6 else [])

 def test_handoff_sequence_orders_different_native_stages(self):
  u,channel,context,_=self.machine()
  for stage in (2,3,2):
   for reg,value in ((A.UC_ARM_REG_R0,stage),(A.UC_ARM_REG_R1,context),
                     (A.UC_ARM_REG_R2,0),(A.UC_ARM_REG_R3,0),
                     (A.UC_ARM_REG_SP,0x5700ff00),(A.UC_ARM_REG_LR,0x5700fff0)):
    u.reg_write(reg,value)
   u.emu_start(self.report['exports']['m10v_roll_camera_review'],0x5700fff0,count=50000)
  self.assertEqual(struct.unpack('<I',u.mem_read(channel+200,4))[0],6)
  self.assertEqual(struct.unpack('<I',u.mem_read(channel+240,4))[0],4)

 def test_independent_node_guard_authenticates_every_debug_wrapper(self):
  fixture={'report':self.report,'code':self.code.hex(),'imports':self.imports}
  js="""import{rollCapturePatches}from'./node/gr3-m10v-native-build.mjs';
import{createHash}from'node:crypto';import assert from'node:assert/strict';
let input='';for await(const chunk of process.stdin)input+=chunk;const f=JSON.parse(input);
const base=0x54000000,runtime=Buffer.alloc(0x500000),roll=f.report;
Buffer.from(f.code,'hex').copy(runtime,roll.base-base);
const m={base,camera_model:'gr3',debug_mode:true,flags:[],companion:{extensions:{features:{live:false}}},
 appended_slots:{photo_recipe:{setter:1}},roll_capture:roll,symbols:{...f.imports,...roll.exports}};
assert.equal(rollCapturePatches(runtime,m).length,17);
assert.throws(()=>rollCapturePatches(runtime,{...m,debug_mode:false}),/diagnostics/);
const missing=structuredClone(m);missing.roll_capture.patches.pop();
assert.throws(()=>rollCapturePatches(runtime,missing),/inventory/);
const wrong=structuredClone(m);wrong.roll_capture.patches[12].expected^=1;
assert.throws(()=>rollCapturePatches(runtime,wrong),/hook/);
const bad=Buffer.from(runtime),changed=structuredClone(m),at=roll.patches[11].entry-base+24;
bad.writeUInt32LE((bad.readUInt32LE(at)^1)>>>0,at);
changed.roll_capture.sha256=createHash('sha256').update(bad.subarray(roll.base-base,roll.base-base+roll.bytes)).digest('hex');
assert.throws(()=>rollCapturePatches(bad,changed),/wrapper differs/);
console.log('PASS exact17debugsites; rejects nondebug, missing, preimage and wrapper mutations');
"""
  result=subprocess.run(['node','--input-type=module','-e',js],input=json.dumps(fixture),cwd=ROOT,capture_output=True,text=True)
  self.assertEqual(result.returncode,0,result.stdout+result.stderr)

 def test_formal_default_has_no_new_sites_or_diagnostic_exports(self):
  _,report=build_observers(self.stock,0x54400000,self.imports)
  self.assertEqual(len(report['patches']),9)
  self.assertFalse(any('jpeg_'in n for n in report['exports']))
 def test_new_preimages_remain_exactly_protected(self):
  damaged=bytearray(self.stock);damaged[0x504944]^=1
  with self.assertRaisesRegex(ValueError,'exact GR III'):build_observers(bytes(damaged),0x54400000,self.imports,debug=True)
if __name__=='__main__':unittest.main()
