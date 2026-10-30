import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,mkdtempSync,rmSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {halfPairIipPatches,halfPairIipSources} from './gr3-half-pair-iip.mjs';
import {borderSources} from './gr3-border.mjs';
const sha=b=>createHash('sha256').update(b).digest('hex');
const cached=new Map();
function fixture(shared=false){
 if(!cached.has(shared)){
  const dir=mkdtempSync(join(tmpdir(),'half-iip-audit-'));
  try{
   const script=`from pathlib import Path
import json,struct,subprocess,shutil,sys
from scripts.build_gr3_border_wait_guard import build as guard_build,FLAGS
from scripts.build_gr3_border_runtime import build as border_build,REUSED
out=Path(sys.argv[1]);shared=sys.argv[2]=='1';rom=Path('builds/gr3-extension-validation/official-rtos.bin').read_bytes()
base=0x540be000;guard_base=0x54160000;pair_base=0x54200000
if shared:
 block,h=border_build(guard_base,rom,{n:base+0x1000+i*0x100 for i,n in enumerate(REUSED)},enabled=True,camera_model='gr3')
 g=h['guard'];external=h['symbols'];symbols={**h['reused_central_symbols'],**external}
 h['jpeg_handoff']={'callsite':base+0x800,'target':h['symbols']['m10v_border_runtime_jpeg'],'original_target':h['reused_central_symbols']['m10v_capture_library']}
else:
 block,g=guard_build(guard_base,rom,border_enabled=True,internal_guard_research=True)
 h=None;external=g['symbols'];symbols=dict(external)
obj=out/'iip.o'
subprocess.run([shutil.which('clang'),*FLAGS,'-fno-jump-tables','-c','native/gr3/m10v_half_pair_iip.c','-o',str(obj)],check=True,capture_output=True)
ld=out/'link.ld';ld.write_text('\\n'.join(f'{name} = {value};' for name,value in external.items())+f'\\nSECTIONS {{ . = {pair_base}; .text : {{ *(.text*) }} .rodata : {{ *(.rodata*) }} /DISCARD/ : {{ *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }} }}')
elf=out/'iip.elf';subprocess.run([shutil.which('ld.lld'),'-T',str(ld),'--entry=m10v_half_pair_iip_ready',str(obj),'-o',str(elf)],check=True,capture_output=True)
b=elf.read_bytes();sh=struct.unpack_from('<I',b,32)[0];n=struct.unpack_from('<H',b,48)[0];rows=[struct.unpack_from('<10I',b,sh+40*i) for i in range(n)];code=bytearray();exports={}
for row in rows:
 if row[2]&2 and row[5]:
  assert row[1]==1 and not row[2]&1;at=row[3]-pair_base;code.extend(bytes(max(0,at+row[5]-len(code))));code[at:at+row[5]]=b[row[4]:row[4]+row[5]]
 if row[1]==2:
  sr=rows[row[6]];strings=b[sr[4]:sr[4]+sr[5]]
  for at in range(row[4],row[4]+row[5],16):
   name,value,_,info,_,section=struct.unpack_from('<IIIBBH',b,at);name=strings[name:].split(b'\\0',1)[0].decode();assert section or not name
   if name.startswith('m10v_half_pair_iip_') and info&15==2:exports[name]=value
runtime=bytearray(pair_base-base+len(code));runtime[guard_base-base:guard_base-base+len(block)]=block;runtime[pair_base-base:]=code
if h:
 call=h['jpeg_handoff']['callsite'];target=h['jpeg_handoff']['target'];struct.pack_into('<I',runtime,call-base,0xeb000000|(((target-call-8)>>2)&0xffffff))
import hashlib
m={'base':base,'camera_model':'gr3','symbols':{**symbols,**exports},'half_pair':{'enabled':True,'schema':'m10v-half-pair/v1','backend':'native-IIP','storage':'owned-native-bank','frame_filesystem_calls':0,'cpu_pixel_reads':0,'cpu_pixel_writes':0,'first_original_preserved':True,'camera_tested':False,'iip_guard':g,'iip_component':{'base':pair_base,'code_bytes':len(code),'code_sha256':hashlib.sha256(code).hexdigest(),'symbols':exports}}}
if h:m['border']={'enabled':True,'pixel_pipeline_enabled':True,'hardware_component':h}
(out/'runtime.bin').write_bytes(runtime);(out/'manifest.json').write_text(json.dumps(m))
`;
   execFileSync(new URL('../.venv/bin/python',import.meta.url).pathname,['-c',script,dir,shared?'1':'0'],{cwd:new URL('..',import.meta.url),stdio:'pipe'});
   const runtime=readFileSync(join(dir,'runtime.bin')),m=JSON.parse(readFileSync(join(dir,'manifest.json')));
   m.sources=Object.fromEntries([...new Set([...halfPairIipSources,...(shared?borderSources:[])])].map(file=>[file,sha(readFileSync(new URL('../'+file,import.meta.url)))]));
   cached.set(shared,{runtime,m});
  }finally{rmSync(dir,{recursive:true,force:true});}
 }
 const value=cached.get(shared);return {runtime:Buffer.from(value.runtime),m:structuredClone(value.m)};
}
test('absent Half leaves native modes untouched; disabled linked component rejects',()=>{
 assert.deepEqual(halfPairIipPatches(Buffer.alloc(0),{}),[]);
 assert.throws(()=>halfPairIipPatches(Buffer.alloc(0),{half_pair:{enabled:false,iip_guard:{}}}),/Half IIP/);
});
test('actual separately linked native IIP and guard yield exactly18 independently checked patches',()=>{
 const {runtime,m}=fixture(),out=halfPairIipPatches(runtime,m);
 assert.equal(out.length,18);assert.equal(new Set(out.map(p=>p.address)).size,18);
 assert.equal(out[0].address,0x5369a010);assert.equal(out[0].expected,0xe3a00044);assert.equal(out[0].replacement,0xe3a00058);
 assert.equal(out.find(p=>p.address===0x534aae28).symbol,'m10v_border_client_wait');
});
test('retired SD frame storage, CPU compositor and inaccurate zero-pixel declarations reject',()=>{
 for(const change of [
  ({m})=>m.half_pair.backend='cpu',({m})=>m.half_pair.storage='HALFPAIR.BIN',
  ({m})=>m.half_pair.frame_filesystem_calls=1,({m})=>m.half_pair.cpu_pixel_reads=1,({m})=>m.half_pair.cpu_pixel_writes=1,
  ({m})=>m.symbols.m10v_half_pair_compose=m.half_pair.iip_component.base,
  ({runtime})=>Buffer.from('HALFPAIR.BIN').copy(runtime,32),
  ({runtime})=>Buffer.from('HALFPAIR.BIN','utf16le').copy(runtime,32),
 ]){const f=fixture();change(f);assert.throws(()=>halfPairIipPatches(f.runtime,f.m),/Half IIP/);}
});
test('source, model, worker ABI, original word and target forgeries reject',()=>{
 for(const change of [
  m=>m.camera_model='gr3x',m=>m.base=0x540b6000,m=>m.half_pair.iip_guard.original_rtos_sha256='0'.repeat(64),
  m=>m.sources['native/gr3/m10v_half_pair_iip.c']='0'.repeat(64),m=>m.half_pair.iip_guard.sources['native/gr3/m10v_border_wait_guard.c']='0'.repeat(64),
  m=>m.half_pair.iip_guard.worker_allocations.transfer_first.owned=0x44,
  m=>m.half_pair.iip_guard.contract.private_client_bytes=32,m=>m.half_pair.iip_guard.patches.pop(),
  m=>m.half_pair.iip_guard.patches[0].expected^=4,m=>m.half_pair.iip_guard.patches[1].target+=4,
  m=>m.symbols.m10v_half_pair_iip_copy+=4,
 ]){const {runtime,m}=fixture();change(m);assert.throws(()=>halfPairIipPatches(runtime,m),/Half IIP/);}
});
test('guard and native IIP binary subranges must match declared hashes and distinct export bounds',()=>{
 for(const mode of ['guard-byte','iip-byte','guard-binding','iip-bounds']){
  const {runtime,m}=fixture(),p=m.half_pair;
  if(mode==='guard-byte')runtime[p.iip_guard.base-m.base]^=1;
  if(mode==='iip-byte')runtime[p.iip_component.base-m.base]^=1;
  if(mode==='guard-binding')m.symbols.m10v_border_client_wait+=4;
  if(mode==='iip-bounds')p.iip_component.symbols.m10v_half_pair_iip_copy=p.iip_component.base+p.iip_component.code_bytes;
  assert.throws(()=>halfPairIipPatches(runtime,m),/Half IIP/);
 }
});
test('full border runtime reuses the exact same checked guard with zero duplicate patches',()=>{
 const {runtime,m}=fixture(true);assert.deepEqual(halfPairIipPatches(runtime,m),[]);
 const other=structuredClone(m.half_pair.iip_guard);other.patches[0].expected^=4;m.half_pair.iip_guard=other;
 assert.throws(()=>halfPairIipPatches(runtime,m),/Half IIP/);
});
