import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from './server.mjs';
import {existsSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {RELEASE_BASELINES} from './firmware-release-policy.mjs';

test('emergency policy blocks model exports, uploads and cached newer projects before any builder runs',async()=>{
 let reads=0,imports=0;
 const store={readOriginal:async()=>{reads++;throw Error('must not read blocked project');},importOfficial:async()=>{imports++;throw Error('must not import');}};
 const server=createServer(store);
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const base=`http://127.0.0.1:${server.address().port}`;
 try{
  const status=await(await fetch(base+'/api/status')).json(),id='5c53760b3b564c87239dbf7f5c94d0f6fd91accd156ec4ba672ebfd6b861793e';
  for(const route of ['/api/import','/api/backup/restore','/api/gr2/native-library/build','/api/gr4/native-library/build',`/api/gr4/customization/${id}/build`,`/api/projects/${id}/native-library/prepare`,`/api/projects/${id}/edit/build`,`/api/projects/${id}/sd/prepare`,...Object.values(RELEASE_BASELINES).flatMap(hash=>[`/api/projects/${hash}/bridge/prepare`,`/api/projects/${hash}/bridge/export`])]){
   const response=await fetch(base+route,{method:'POST',headers:{'X-M10V-Token':status.session_token,'Content-Type':'application/json'},body:'{}'});
   assert.equal(response.status,423,route);assert.equal((await response.json()).code,'FIRMWARE_RELEASE_LOCKED',route);
  }
  assert.equal(reads,0);assert.equal(imports,0);
  for(const model of ['gr2','gr4'])assert.match(await(await fetch(base+`/${model}/`)).text(),/固件导出已暂停/);
  const html=await(await fetch(base+'/gr3/')).text();assert.match(html,/仅支持内置基线/);assert.match(html,/<input[^>]+id="firmware-file"[^>]+disabled/);
  assert.equal(status.firmware_release_policy.uploads_allowed,false);
 }finally{await new Promise(r=>server.close(r));}
});

test('both pinned built-in baselines still load and prepare through HTTP',
 {skip:!existsSync(new URL('../bin/fwdc239b-gr3-official.bin',import.meta.url))||!existsSync(new URL('../bin/fwdc243b-gr3x-official.bin',import.meta.url))},async()=>{
 const inputs=new Map(),store={importOfficial:async bytes=>{const id=createHash('sha256').update(bytes).digest('hex');inputs.set(id,bytes);return{id,sha256:id};},readOriginal:async id=>inputs.get(id)};
 const server=createServer(store);await new Promise(r=>server.listen(0,'127.0.0.1',r));const base=`http://127.0.0.1:${server.address().port}`;
 try{
  const status=await(await fetch(base+'/api/status')).json();
  const post=(route,body)=>fetch(base+route,{method:'POST',headers:{'X-M10V-Token':status.session_token,'Content-Type':'application/json'},body:JSON.stringify(body)});
  for(const model of ['gr3','gr3x']){
   const imported=await post('/api/gr3/native-library/import-official',{model});assert.equal(imported.status,200,await imported.clone().text());
   const {project_id}=await imported.json();assert.equal(project_id,RELEASE_BASELINES[model]);
   const response=await post(`/api/projects/${project_id}/native-library/prepare`,{});
   assert.equal(response.status,200,await response.clone().text());assert.equal((await response.json()).ready,true);
  }
 }finally{await new Promise(r=>server.close(r));}
});

test('built-in import refuses a request that tries to select a newer source or extra bytes',async()=>{
 const server=createServer();await new Promise(r=>server.listen(0,'127.0.0.1',r));
 try{
  const base=`http://127.0.0.1:${server.address().port}`,token=(await(await fetch(base+'/api/status')).json()).session_token;
  for(const body of [{model:'gr3',version:'2.20'},{model:'gr3x',version:'1.70'},{model:'gr3',source:'custom.bin'}]){
   const response=await fetch(base+'/api/gr3/native-library/import-official',{method:'POST',headers:{'X-M10V-Token':token,'Content-Type':'application/json'},body:JSON.stringify(body)});
   assert.equal(response.status,400);assert.match((await response.json()).error,/内置来源/);
  }
 }finally{await new Promise(r=>server.close(r));}
});
