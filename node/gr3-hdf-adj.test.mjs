import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {existsSync} from 'node:fs';
import {hdfAdjPatches} from './gr3-hdf-adj.mjs';
const code=`import base64,json
from tests.test_gr3_hdf_adj import HdfAdjArmTests as T
T.setUpClass()
base=min(a for a,b in T.images);end=max(a+len(b) for a,b in T.images)
runtime=bytearray(end-base)
for a,b in T.images:runtime[a-base:a-base+len(b)]=b
print(json.dumps(dict(runtime=base64.b64encode(runtime).decode(),m=dict(base=base,symbols=T.symbols,hdf_adj=T.manifest,hdf_menu={},hdf_enabled=True))))
`;
const python=process.env.M10V_PYTHON||process.env.PYTHON||(existsSync('.venv/bin/python')?'.venv/bin/python':'python3');
const result=spawnSync(python,['-c',code],{encoding:'utf8',maxBuffer:2**22});
assert.equal(result.status,0,result.stderr);
const fixture=JSON.parse(result.stdout),runtime=Buffer.from(fixture.runtime,'base64'),manifest=fixture.m;
const copy=()=>({runtime:Buffer.from(runtime),m:structuredClone(manifest)});
test('independent verifier reconstructs82exact patches including every original consumer',()=>{
 const patches=hdfAdjPatches(runtime,manifest);assert.equal(patches.length,82);assert.equal(new Set(patches.map(p=>p.address)).size,82);
});
test('original-record tampering remains rejected after runtime and manifest hashes are refreshed',()=>{
 const {runtime:r,m}=copy();r[m.hdf_adj.table-m.base+9*0x44+0x28]^=1;m.code_sha256=createHash('sha256').update(r).digest('hex');
 assert.throws(()=>hdfAdjPatches(r,m),/original twenty records differ/);
});
test('all added function pointers and handler manifest must match genuine linked symbols',()=>{
 for(const field of ['draw','set','count','event']){const {runtime:r,m}=copy();m.hdf_adj.handlers[field]+=4;assert.throws(()=>hdfAdjPatches(r,m),/handler/);}
 const {runtime:r,m}=copy();r.writeUInt32LE(m.symbols.m10v_hdf_adj_draw+4,m.hdf_adj.table-m.base+0x550+0x18);assert.throws(()=>hdfAdjPatches(r,m),/instruction/);
});
test('constructor length/getter guard/name/icon/list mutations cannot be authorized by rehashing',()=>{
 for(const site of [0x531a1e54,0x53246340,0x532928b0,0x53293ad0]){
  const {runtime:r,m}=copy(),p=m.hdf_adj.patches.find(p=>p.address===site);let d=(p.replacement&0xffffff)<<2;if(d&0x2000000)d-=0x4000000;
  const at=site+8+d;r[at-m.base+4]^=1;m.code_sha256=createHash('sha256').update(r).digest('hex');assert.throws(()=>hdfAdjPatches(r,m),/instruction/);
 }
 for(let slot=0;slot<5;slot++){const {runtime:r,m}=copy();r[m.hdf_adj.lists[slot].address-m.base+10]=20;assert.throws(()=>hdfAdjPatches(r,m),/assignment/);}
});
test('forged patch preimages/extra patches/missing list reader or out-of-range table fail closed',()=>{
 for(const mutate of [m=>m.hdf_adj.patches[0].expected^=1,m=>m.hdf_adj.patches.pop(),m=>m.hdf_adj.table_readers.pop(),m=>m.hdf_adj.table=m.base+runtime.length,m=>m.hdf_adj.handlers.event=0x53000000]){
  const {runtime:r,m}=copy();mutate(m);assert.throws(()=>hdfAdjPatches(r,m),/HDF ADJ/);
 }
});
test('an enabled HDF menu cannot silently omit independent ADJ capability',()=>{
 assert.throws(()=>hdfAdjPatches(runtime,{hdf_enabled:true,hdf_menu:{}}),/missing/);
 assert.deepEqual(hdfAdjPatches(runtime,{hdf_enabled:false}),[]);
 assert.throws(()=>hdfAdjPatches(runtime,{hdf_enabled:true,hdf_menu:{},hdf_adj_capability:false}),/missing/);
 assert.throws(()=>hdfAdjPatches(runtime,{hdf_enabled:false,hdf_menu:{}}),/missing/);
});

test('resealed parent-event metadata cannot bypass original AB and poweroff composition',()=>{
 const {runtime:r,m}=copy();m.settings_menu={};m.symbols.m10v_settings_controller_ab_adj_event=m.symbols.m10v_hdf_adj_event+4;
 m.hdf_adj.parent_event=m.symbols.m10v_hdf_adj_event;assert.throws(()=>hdfAdjPatches(r,m),/parent event/);
 m.hdf_adj.parent_event=m.symbols.m10v_settings_controller_ab_adj_event;assert.equal(hdfAdjPatches(r,m).length,82);
});
