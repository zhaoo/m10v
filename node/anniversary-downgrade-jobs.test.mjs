import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';
import {createServer} from './server.mjs';
import {checkDowngradeCamera,requireAnniversaryDownload,anniversaryDowngradeJob} from './anniversary-downgrade-jobs.mjs';
import {createFirmwareBuildQueue} from './firmware-build-queue.mjs';
import {ANNIVERSARY_DOWNGRADE_PROFILES} from './gr3-anniversary-downgrade.mjs';
import {officialFirmwareFromZip} from './anniversary-downgrade-sources.mjs';
import {encodeZip} from './gr3-sd-film-export.mjs';
const sha=b=>createHash('sha256').update(b).digest('hex');
const paths={gr3:process.env.M10V_GR3_220_FIXTURE,gr3x:process.env.M10V_GR3X_170_FIXTURE};
const available=Object.values(paths).every(p=>p&&existsSync(p));
async function fixture(loader){
 const server=createServer(undefined,undefined,undefined,{downgradeSources:loader});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const base=`http://127.0.0.1:${server.address().port}`,token=(await(await fetch(base+'/api/status')).json()).session_token;
 return {base,post:(route,body,auth=true)=>fetch(base+route,{method:'POST',headers:{'Content-Type':'application/json',...(auth?{'X-M10V-Token':token}:{})},body:JSON.stringify(body)}),close:()=>new Promise(r=>server.close(r))};
}
test('downgrade route rejects an existing target, cross-model and unknown provenance before source IO',async()=>{
 let reads=0;const f=await fixture(async()=>{reads++;throw Error('must not read');});
 try{
  for(const camera of [undefined,{model:'gr3',version:'2.10',origin:'official'},{model:'gr3x',version:'1.70',origin:'official'},
   {model:'gr3',version:'2.20',origin:'third-party'},{model:'gr3',version:'2.20',origin:'unknown'}]){
   const response=await f.post('/api/downgrade/gr3/prepare',{camera});assert.equal(response.status,412);
  }
  assert.equal((await f.post('/api/downgrade/gr3/prepare',{camera:{model:'gr3',version:'2.20',origin:'official'}},false)).status,403);
  assert.equal(reads,0);
  const {models}=await(await fetch(f.base+'/api/downgrade/status')).json();assert.equal(models.gr3.available,true);assert.equal(models.gr3x.to_version,'1.60');
 }finally{await f.close();}
});
test('download proof cannot be forged by request JSON or a correct digest',()=>{
 const candidate=Buffer.from('forged');
 assert.throws(()=>requireAnniversaryDownload(candidate,{schema:'m10v-anniversary-downgrade-safety/v1',candidate_sha256:sha(candidate),candidate_bytes:candidate.length}),/校验记录/);
 assert.throws(()=>checkDowngradeCamera('gr4',{}),/机型/);
});
test('cancelling source acquisition releases the queue slot before a shared loader completes',async()=>{
 let release;const waiting=new Promise(resolve=>{release=resolve;}),queue=createFirmwareBuildQueue();
 const plan={...ANNIVERSARY_DOWNGRADE_PROFILES.gr3,model:'gr3',plan_id:'a'.repeat(64)};
 const request={camera:{model:'gr3',version:'2.20',origin:'official'},accepted_plan_id:plan.plan_id,acknowledge_instructions:true};
 try{
  const first=queue.submit(anniversaryDowngradeJob(()=>waiting,'gr3',request,plan));await delay(0);
  const second=queue.submit(async()=>({candidate:Buffer.from('next'),filename:'next.bin'}));
  queue.cancel(first.id);await delay(20);
  assert.equal(queue.get(first.id).state,'cancelled');assert.equal(queue.get(second.id).state,'ready');
 }finally{queue.close();release({newSource:Buffer.alloc(0),oldSource:Buffer.alloc(0)});}
});
test('official ZIP extraction never accepts a different hash, duplicate entry or truncated directory',()=>{
 const bytes=Buffer.alloc(160,7),zip=encodeZip({'dir/fwdc239b.bin':bytes});
 assert.deepEqual(officialFirmwareFromZip(zip,'fwdc239b.bin',sha(bytes)),bytes);
 assert.throws(()=>officialFirmwareFromZip(zip,'fwdc239b.bin','0'.repeat(64)),/SHA-256/);
 assert.throws(()=>officialFirmwareFromZip(zip.subarray(0,-1),'fwdc239b.bin',sha(bytes)),/目录/);
 assert.throws(()=>officialFirmwareFromZip(encodeZip({'a/fwdc239b.bin':bytes,'b/fwdc239b.bin':bytes}),'fwdc239b.bin',sha(bytes)),/重复/);
});
test('real two-model downgrade jobs rebuild and deliver a bound ZIP through the common queue',{skip:!available,timeout:180000},async()=>{
 const source={};for(const model of ['gr3','gr3x'])source[model]={newSource:readFileSync(paths[model]),oldSource:readFileSync(new URL(model==='gr3'?'../bin/fwdc239b-gr3-official.bin':'../bin/fwdc243b-gr3x-official.bin',import.meta.url))};
 const f=await fixture(async model=>source[model]);
 try{
  const jobs=[];
  for(const [model,version] of [['gr3','2.20'],['gr3x','1.70']]){
   const camera={model,version,origin:'official'},route=`/api/downgrade/${model}`;
   const pre=await f.post(route+'/prepare',{camera});assert.equal(pre.status,200,await pre.clone().text());const plan=await pre.json();
   assert.equal(plan.ready,true);assert.ok(plan.filename.endsWith('.zip'));
   assert.equal((await f.post(route+'/jobs',{camera,accepted_plan_id:'0'.repeat(64),acknowledge_instructions:true})).status,400);
   const submitted=await f.post(route+'/jobs',{camera,accepted_plan_id:plan.plan_id,acknowledge_instructions:true});
   assert.equal(submitted.status,202,await submitted.clone().text());jobs.push({model,plan,job:(await submitted.json()).job});
  }
  for(const item of jobs){
   let job=item.job;
   while(job.state!=='ready'){
    assert.ok(!['failed','cancelled','expired'].includes(job.state),JSON.stringify(job));await delay(100);
    job=(await(await fetch(f.base+`/api/firmware-jobs/${job.id}`)).json()).job;
   }
   const response=await fetch(f.base+`/api/firmware-jobs/${job.id}/download`);assert.equal(response.status,200);
   const audit=JSON.parse(Buffer.from(response.headers.get('X-M10V-Downgrade-Safety'),'base64'));
   const bytes=Buffer.from(await response.arrayBuffer());assert.equal(sha(bytes),audit.candidate_sha256);assert.equal(bytes.length,audit.candidate_bytes);
   assert.equal(audit.exact_rebuild,true);assert.equal(audit.camera_tested,false);assert.equal(audit.model,item.model);
   assert.equal(audit.plan_id,item.plan.plan_id);assert.equal(audit.source_sha256,item.plan.source_sha256);assert.equal(audit.restore_sha256,item.plan.restore_sha256);
   assert.equal(response.headers.get('Content-Type'),'application/zip');assert.match(response.headers.get('Content-Disposition'),/\.zip/);
  }
 }finally{await f.close();}
});
