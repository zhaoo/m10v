import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {borderPatches,borderSources} from './gr3-border.mjs';
import {hdfPatches} from './gr3-digital-hdf.mjs';

const sha=b=>createHash('sha256').update(b).digest('hex');
const cached=new Map();
function fixture(model='gr3'){
 if(!cached.has(model)){
  const dir=mkdtempSync(join(tmpdir(),'border-node-readback-'));
  try{
   execFileSync('/Users/zhaoo/Desktop/code/zhaoo/m10v/.venv/bin/python',['-c',`from pathlib import Path
from scripts.build_gr3_border_runtime import build,REUSED
r=Path('builds/gr3-border-iip-20261027/${model}-official-rtos.bin').read_bytes()
build(0x54160000,r,{n:0x540c0000+i*0x100 for i,n in enumerate(REUSED)},camera_model=${JSON.stringify(model)},enabled=True,out_dir=${JSON.stringify(dir)})`],{cwd:new URL('..',import.meta.url),stdio:'pipe'});
   const h=JSON.parse(readFileSync(join(dir,'m10v-border-runtime-arm.json'))),block=readFileSync(join(dir,'m10v-border-runtime-arm.bin'));
   const base=0x540b6000,runtime=Buffer.alloc(h.base-base+block.length);block.copy(runtime,h.base-base);
   const callsite=base+0x1000,target=h.symbols.m10v_border_runtime_jpeg;
   h.jpeg_handoff={callsite,target,original_target:h.reused_central_symbols.m10v_capture_library};
   runtime.writeUInt32LE((0xeb000000|(((target-callsite-8)>>2)&0xffffff))>>>0,callsite-base);
   const sources=Object.fromEntries(borderSources.map(name=>[name,sha(readFileSync(new URL('../'+name,import.meta.url)))]));
   cached.set(model,{runtime,m:{base,camera_model:model,symbols:{...h.reused_central_symbols,...h.symbols},sources,
    border:{enabled:true,pixel_pipeline_enabled:true,hardware_component:h},hdf_enabled:false,hdf_default:0,hdf_menu:{route:0x0200f102}}});
  }finally{rmSync(dir,{recursive:true,force:true});}
 }
 return {runtime:Buffer.from(cached.get(model).runtime),m:structuredClone(cached.get(model).m)};
}
test('OFF has no border patches and metadata-only border cannot export',()=>{
 assert.deepEqual(borderPatches(Buffer.alloc(0),{}),[]);
 assert.throws(()=>borderPatches(Buffer.alloc(0),{border:{enabled:true,pixel_pipeline_enabled:false}}),/border/);
});
test('actual builder component independently produces twenty patches and permits border-only Effects',()=>{
 for(const model of ['gr3','gr3x']){
  const {runtime,m}=fixture(model),patches=borderPatches(runtime,m);
  assert.equal(patches.length,20);assert.equal(new Set(patches.map(p=>p.address)).size,20);
  assert.equal(patches.find(p=>p.address===0x53501f98).expected,0xeb06a762);
  assert.equal(patches.find(p=>p.address===0x534ff458).expected,0xe51b2028);
  assert.deepEqual(hdfPatches(runtime,m),[]);
 }
});
test('missing hook, partial table, source and central-symbol tampering are rejected',()=>{
 for(const change of [
  m=>m.border.hardware_component.patches.pop(),
  m=>m.border.hardware_component.guard.patches.pop(),
  m=>delete m.border.hardware_component.symbols.m10v_border_runtime_after_resize,
  m=>delete m.border.hardware_component.sections[2].symbols.m10v_border_bank_plan,
  m=>m.border.hardware_component.sources['native/gr3/m10v_border_runtime.c']='0'.repeat(64),
  m=>m.sources['native/gr3/m10v_border_camera.c']='0'.repeat(64),
  m=>m.border.hardware_component.reused_central_symbols.m10v_capture_library+=4,
  m=>m.border.hardware_component.metadata_allocation_bytes++,
  m=>m.border.hardware_component.mutable_static_bytes=4,
  m=>m.border.hardware_component.cpu_raster_pass=true,
  m=>m.border.hardware_component.native_jpeg_encoded_capacity_preserved=false,
  m=>m.border.hardware_component.camera_model='gr3x',
  m=>m.border.hardware_component.patches[1].target=0x70000000,
 ]){const {runtime,m}=fixture();change(m);assert.throws(()=>borderPatches(runtime,m),/border/);}
});
test('code, guard subrange and independent full-context shim readback reject tampering',()=>{
 for(const mode of ['code','guard-hash','submit-shim','resize-shim','patch-forgery']){
  const {runtime,m}=fixture(),h=m.border.hardware_component;
  if(mode==='code')runtime[h.base-m.base]^=1;
  if(mode==='guard-hash')h.guard.code_sha256='0'.repeat(64);
  if(mode.includes('shim')){
   const name=mode==='submit-shim'?'m10v_border_runtime_submit_hook':'m10v_border_runtime_resize_hook';
   runtime[h.symbols[name]-m.base]^=1;
   h.code_sha256=sha(runtime.subarray(h.base-m.base,h.base-m.base+h.code_bytes));
  }
  if(mode==='patch-forgery')h.patches[0].replacement^=4;
  assert.throws(()=>borderPatches(runtime,m),/border/);
 }
 const {runtime,m}=fixture();delete m.border;assert.throws(()=>hdfPatches(runtime,m),/HDF/);
});
