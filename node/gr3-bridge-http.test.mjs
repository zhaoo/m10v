import {test} from 'node:test';import assert from 'node:assert/strict';
import {mkdtemp,rm,readFile} from 'node:fs/promises';import os from 'node:os';import path from 'node:path';
import {createServer} from './server.mjs';import {Store} from './storage.mjs';
test('historical bridge HTTP stays locked even with a valid source and old acknowledgement',async()=>{
 const dir=await mkdtemp(path.join(os.tmpdir(),'m10v-bridge-http-')),store=new Store(dir),server=createServer(store);
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const base=`http://127.0.0.1:${server.address().port}`;
 try{
  const original=await readFile(new URL('../bin/fwdc239b-gr3-official.bin',import.meta.url)),record=await store.importOfficial(original);
  const url=`${base}/api/projects/${record.id}/bridge/`;
  assert.equal((await fetch(url+'prepare',{method:'POST',body:'{}'})).status,403);
  const token=(await(await fetch(base+'/api/status')).json()).session_token;
  const post=(route,data,extra={})=>fetch(url+route,{method:'POST',headers:{'X-M10V-Token':token,'Content-Type':'application/json',...extra},body:JSON.stringify(data)});
  assert.equal((await post('prepare',{}, {Origin:'https://invalid.example'})).status,403);
  for(const [route,body] of [['prepare',{}],['export',{}],['export',{accepted_plan_id:'stale',acknowledge_instructions:true}]]){
   const response=await post(route,body);assert.equal(response.status,423);
   assert.equal((await response.json()).code,'FIRMWARE_RELEASE_LOCKED');
   assert.doesNotMatch(response.headers.get('content-type'),/zip/);
  }
  const x=await store.importOfficial(await readFile(new URL('../bin/fwdc243b-gr3x-official.bin',import.meta.url)));
  const res=await fetch(`${base}/api/projects/${x.id}/bridge/prepare`,{method:'POST',headers:{'X-M10V-Token':token},body:'{}'});assert.equal(res.status,423);
 }finally{await new Promise(r=>server.close(r));await rm(dir,{recursive:true,force:true});}
});
