import {test} from 'node:test';
import assert from 'node:assert/strict';
import {existsSync,readFileSync} from 'node:fs';
import {mkdtemp,rm} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {createServer} from './server.mjs';
import {Store} from './storage.mjs';
import {restoreBytes} from './backup.mjs';
import {defaultConfiguration} from '../web/gr3/native-library-state.mjs';
import {decodeFrameMap} from './gr3-frames.mjs';
import {resolveBuildSource} from './firmware-build-source.mjs';

const fixture=process.env.M10V_GR3_220_FIXTURE;
const baselineSha='d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4';
for(const [file,model,version] of [
 ['fwdc239b-gr3-official.bin','GR III','2.10'],
 ['fwdc243b-gr3x-official.bin','GR IIIx','1.60'],
])test(`${model} ${version} remains on its own verified build baseline`,async()=>{
 const uploaded=readFileSync(new URL('../bin/'+file,import.meta.url));
 const {source,report}=await resolveBuildSource(uploaded);
 assert.ok(source.equals(uploaded));assert.equal(report.build_source.normalized,false);
 assert.equal(report.build_source.model,model);assert.equal(report.build_source.public_version,version);
 assert.equal(report.build_source.sha256,report.sha256);
 const changed=Buffer.from(uploaded);changed[200]^=1;
 await assert.rejects(()=>resolveBuildSource(changed),/identity/);
});
test('2.20 upload keeps its backup and builds data edits from the uploaded firmware',
 {skip:!fixture||!existsSync(fixture)},async()=>{
 const original=readFileSync(fixture),folder=await mkdtemp(path.join(os.tmpdir(),'m10v-build-source-'));
 const store=new Store(folder),server=createServer(store);
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const base=`http://127.0.0.1:${server.address().port}`;
 try{
  const token=(await(await fetch(base+'/api/status')).json()).session_token;
  const post=(url,body)=>fetch(base+url,{method:'POST',headers:{'X-M10V-Token':token},body:Buffer.isBuffer(body)?body:JSON.stringify(body)});
  const imported=await post('/api/import',original);assert.equal(imported.status,200,await imported.clone().text());
  const report=await imported.json(),id=report.project_id;
  assert.equal(report.public_version,'2.20');assert.equal(report.build_source.public_version,'2.20');
  assert.equal(report.build_source.sha256,report.sha256);assert.equal(report.build_source.normalized,false);
  const reread=await(await fetch(base+`/api/projects/${id}`)).json();assert.deepEqual(reread.build_source,report.build_source);
  assert.ok((await store.readOriginal(id)).equals(original));
  const backup=await post(`/api/projects/${id}/backup`,{});
  assert.ok(restoreBytes(Buffer.from(await backup.arrayBuffer())).equals(original));
  const stock=await fetch(base+`/api/projects/${id}/stock-presets`);assert.equal(stock.status,200,await stock.clone().text());
  assert.equal((await stock.json()).length,12);
  const prepared=await post(`/api/projects/${id}/native-library/prepare`,{configuration:defaultConfiguration()});
  assert.equal(prepared.status,400);assert.match((await prepared.json()).error,/原生 ABI 尚未适配/);
  const incompatible=await post(`/api/projects/${id}/native-library/prepare`,{configuration:defaultConfiguration(),version_unlock:{enabled:true,mode:'dsp-package-only'}});
  assert.equal(incompatible.status,400);assert.match((await incompatible.json()).error,/原生 ABI 尚未适配/);
  const selection={variant:'street',features:['presets'],stockPresets:[{slot:2,name:'Clear'}]};
  const editPlan=await post(`/api/projects/${id}/edit/prepare`,{selection});
  assert.equal(editPlan.status,200,await editPlan.clone().text());const edit=await editPlan.json();assert.equal(edit.ready,true);
  const built=await post(`/api/projects/${id}/edit/build`,{selection,accepted_configuration_sha256:edit.configuration_sha256});
  assert.equal(built.status,200,await built.clone().text());
  const receipt=JSON.parse(Buffer.from(built.headers.get('X-M10V-Build-Receipt'),'base64'));
  assert.equal(receipt.build_source.imported_sha256,id);assert.equal(receipt.build_source.sha256,id);
  const candidate=Buffer.from(await built.arrayBuffer());
  assert.equal(candidate.readUInt32BE(0x38),0x0214141c);assert.equal(candidate.readUInt32BE(0x50),0x0214141c);
  assert.equal(receipt.update_compatibility,undefined);assert.equal(decodeFrameMap(candidate).decoded.length,59798532);
  const bridge=await post(`/api/projects/${id}/bridge/prepare`,{});
  assert.equal(bridge.status,400);assert.match((await bridge.json()).error,/exact official GR III 2.10/);
 }finally{await new Promise(resolve=>server.close(resolve));await rm(folder,{recursive:true,force:true});}
});
