import {test} from 'node:test';
import assert from 'node:assert/strict';
import {existsSync,readFileSync} from 'node:fs';
import {mkdtemp,rm} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {createServer} from './server.mjs';
import {Store} from './storage.mjs';
import {resolveBuildSource} from './firmware-build-source.mjs';

const fixture=process.env.M10V_GR3_220_FIXTURE;
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
test('official 2.20 bytes can be inspected while upload and all project builders stay locked',
 {skip:!fixture||!existsSync(fixture)},async()=>{
 const original=readFileSync(fixture),folder=await mkdtemp(path.join(os.tmpdir(),'m10v-build-source-'));
 const {source,report}=await resolveBuildSource(original);
 assert.equal(report.public_version,'2.20');
 assert.ok(source.equals(original));
 const server=createServer(new Store(folder));
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const base=`http://127.0.0.1:${server.address().port}`;
 try{
  const token=(await(await fetch(base+'/api/status')).json()).session_token;
  const post=(url,body)=>fetch(base+url,{method:'POST',headers:{'X-M10V-Token':token},body});
  for(const [url,body] of [['/api/import',original],...['native-library/prepare','native-library/build','edit/prepare','edit/build'].map(route=>[`/api/projects/${report.sha256}/${route}`,'{}'])]){
   const response=await post(url,body);
   assert.equal(response.status,423,url);
   const result=await response.json();
   assert.equal(result.code,'FIRMWARE_RELEASE_LOCKED');
  }
 }finally{await new Promise(resolve=>server.close(resolve));await rm(folder,{recursive:true,force:true});}
});
