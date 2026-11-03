import test from 'node:test';
import assert from 'node:assert/strict';
import {existsSync,readFileSync,mkdirSync,writeFileSync} from 'node:fs';
import {createHash,webcrypto} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';
import {createServer} from './server.mjs';
import {RELEASE_BASELINES} from './firmware-release-policy.mjs';
import {defaultConfiguration} from '../web/gr3/native-library-state.mjs';
import {unwrapFirmwareDownload} from '../web/gr3/firmware-download.mjs';
import {readFirmwareSafety,verifyFirmwareBlob} from '../web/gr3/firmware-verification.mjs';
if(!globalThis.crypto?.subtle)Object.defineProperty(globalThis,'crypto',{value:webcrypto,configurable:true});
const gr3=new URL('../bin/fwdc239b-gr3-official.bin',import.meta.url),gr3x=new URL('../bin/fwdc243b-gr3x-official.bin',import.meta.url);
const available=existsSync(gr3)&&existsSync(gr3x);
async function fixture(){
 const inputs=new Map([[RELEASE_BASELINES.gr3,readFileSync(gr3)],[RELEASE_BASELINES.gr3x,readFileSync(gr3x)]]);
 const server=createServer({readOriginal:async id=>inputs.get(id)});await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const base=`http://127.0.0.1:${server.address().port}`,token=(await(await fetch(base+'/api/status')).json()).session_token;
 return {server,base,post:(url,body,headers={})=>fetch(base+url,{method:'POST',headers:{'X-M10V-Token':token,'Content-Type':'application/json',...headers},body:JSON.stringify(body)}),close:()=>new Promise(r=>server.close(r))};
}
test('real generation routes require camera provenance and reject newer/stale/version-raised input',{skip:!available},async()=>{
 const f=await fixture(),route=`/api/projects/${RELEASE_BASELINES.gr3}/native-library/`;
 try{
  const configuration=defaultConfiguration(),plan=await(await f.post(route+'prepare',{configuration})).json();assert.equal(plan.ready,true);
  for(const camera of [undefined,{model:'gr3',version:'2.20',origin:'official'},{model:'gr3',version:'2.10',origin:'third-party'},{model:'gr3x',version:'1.60',origin:'official'}]){
   for(const action of ['jobs','build']){
    const r=await f.post(route+action,{configuration,camera,accepted_configuration_sha256:plan.configuration_sha256});
    assert.equal(r.status,412,await r.clone().text());assert.equal(r.headers.get('Content-Disposition'),null);
   }
  }
  const camera={model:'gr3',version:'2.10',origin:'official'};
  assert.equal((await f.post(route+'jobs',{configuration,camera,accepted_configuration_sha256:'0'.repeat(64)})).status,400);
  assert.equal((await f.post(route+'prepare',{configuration,version_unlock:{enabled:true,mode:'dsp-package-only'}})).status,400);
  const newer=await f.post('/api/projects/'+'5c53760b3b564c87239dbf7f5c94d0f6fd91accd156ec4ba672ebfd6b861793e'+'/native-library/jobs',{});
  assert.equal(newer.status,423);
  assert.equal((await fetch(f.base+'/api/firmware-jobs/'+'0'.repeat(48)+'/download')).status,404);
 }finally{await f.close();}
});
test('official backup requires provenance and passes browser digest checks',{skip:!available},async()=>{
 const f=await fixture(),route=`/api/projects/${RELEASE_BASELINES.gr3}/backup`;
 try{
  assert.equal((await f.post(route,{})).status,412);
  const camera=Buffer.from(JSON.stringify({model:'gr3',version:'2.10',origin:'official'})).toString('base64');
  const response=await f.post(route,{}, {'X-M10V-Camera':camera});assert.equal(response.status,200);
  const audit=readFirmwareSafety(response),blob=await response.blob();
  await verifyFirmwareBlob(blob,{audit,artifactKind:'official_backup',sourceSha256:RELEASE_BASELINES.gr3,configurationSha256:RELEASE_BASELINES.gr3,model:'gr3',filename:'m10v-gr3-backup.zip'});
 }finally{await f.close();}
});
test('a supported project ID cannot conceal the other model official bytes',{skip:!available},async()=>{
 const server=createServer({readOriginal:async()=>readFileSync(gr3x)});await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const base=`http://127.0.0.1:${server.address().port}`;
 try{
  const token=(await(await fetch(base+'/api/status')).json()).session_token;
  const response=await fetch(base+`/api/projects/${RELEASE_BASELINES.gr3}/native-library/prepare`,{method:'POST',headers:{'Content-Type':'application/json','X-M10V-Token':token},body:JSON.stringify({configuration:defaultConfiguration()})});
  assert.equal(response.status,400);assert.match((await response.json()).error,/来源不匹配/);
 }finally{await new Promise(r=>server.close(r));}
});
test('two real model jobs serialize full reconstruction, queued cancellation and exact verified download',
 {skip:!available||process.env.M10V_WEB_STRICT_INTEGRATION!=='1',timeout:300000},async()=>{
 const f=await fixture(),jobs=[],results=[];
 try{
  for(const [model,version] of [['gr3','2.10'],['gr3x','1.60']]){
   const configuration=defaultConfiguration(),route=`/api/projects/${RELEASE_BASELINES[model]}/native-library/`;
   const prepared=await f.post(route+'prepare',{configuration});assert.equal(prepared.status,200);const plan=await prepared.json();
   const input={configuration,camera:{model,version,origin:'official'},accepted_configuration_sha256:plan.configuration_sha256};
   const submitted=await f.post(route+'jobs',input);assert.equal(submitted.status,202,await submitted.clone().text());
   const {job}=await submitted.json();jobs.push({job,model,route,input,plan});
  }
  assert.equal(jobs[1].job.state,'queued');
  const third=await(await f.post(jobs[0].route+'jobs',jobs[0].input)).json();
  assert.equal((await f.post(`/api/firmware-jobs/${third.job.id}/cancel`,{})).status,200);
  const cancelled=(await(await fetch(f.base+`/api/firmware-jobs/${third.job.id}`)).json()).job;
  assert.equal(cancelled.state,'cancelled');
  assert.equal((await fetch(f.base+`/api/firmware-jobs/${third.job.id}/download`)).status,409);
  for(const item of jobs){
   let job=item.job,observed=new Set();
   while(job.state!=='ready'){
    assert.ok(!['failed','cancelled','expired'].includes(job.state),JSON.stringify(job));observed.add(job.state+':'+job.phase);
    await delay(300);
    try{job=(await(await fetch(f.base+`/api/firmware-jobs/${job.id}`)).json()).job;}
    catch(error){throw Error(`status polling failed: ${error.cause?.code||error.cause?.message||error.message}`,{cause:error});}
   }
   const raw=await fetch(f.base+`/api/firmware-jobs/${job.id}/download`,{headers:{Accept:'multipart/form-data'}});
   const response=await unwrapFirmwareDownload(raw);assert.equal(response.status,200);
   const audit=readFirmwareSafety(response),receipt=JSON.parse(Buffer.from(response.headers.get('X-M10V-Native-Receipt'),'base64').toString('utf8')),blob=await response.blob();
   const filename=item.model==='gr3'?'fwdc239b.bin':'fwdc243b.bin';
   await verifyFirmwareBlob(blob,{audit,receipt,sourceSha256:RELEASE_BASELINES[item.model],configurationSha256:item.plan.configuration_sha256,model:item.model,filename});
   const hash=createHash('sha256').update(Buffer.from(await blob.arrayBuffer())).digest('hex');
   assert.equal(hash,item.model==='gr3'?'2d8b93b1e9e4eb1df3941fc517f6961ec23df23e3e08fb06690c2c27ac34d8ce':'380135d0e61d73fd3622ce86e9e19a8f8fa53c29b1fb6c1bad7db5ed9e477a2b');
   results.push({model:item.model,sha256:hash,audit,observed:[...observed]});
  }
  assert.ok(results[0].observed.includes('running:verifying'));
  mkdirSync('builds/firmware-safety-web-20261103',{recursive:true});writeFileSync('builds/firmware-safety-web-20261103/http-models.json',JSON.stringify(results,null,2));
 }finally{for(const {job} of jobs)await f.post(`/api/firmware-jobs/${job.id}/cancel`,{}).catch(()=>{});await f.close();}
});
