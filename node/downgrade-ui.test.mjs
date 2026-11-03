import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { validateCameraDeclaration, validatePreparedPlan, readDowngradeSafety, verifyDowngradeBlob, runDowngradeJob, downgradeJobProgress } from '../web/gr3/downgrade.js';
const hash = value => createHash('sha256').update(value).digest('hex');
const camera = {model:'gr3', version:'2.20', origin:'official'};
const plan = {ready:true, plan_id:'a'.repeat(64), model:'gr3', from_version:'2.20', to_version:'2.10', filename:'m10v-gr3-downgrade.zip', source_sha256:'b'.repeat(64), restore_sha256:'c'.repeat(64)};
const bytes = Buffer.from('PK\x03\x04actual ZIP bytes');
const audit = {...plan, schema:'m10v-anniversary-downgrade-safety/v1', candidate_sha256:hash(bytes), candidate_bytes:bytes.length, exact_rebuild:true, camera_tested:false, installation_allowed:false};
const reply = (record=audit, body=bytes) => new Response(body,{headers:{'Content-Type':'application/zip','Content-Disposition':`attachment; filename="${record.filename}"`,'X-M10V-Downgrade-Safety':Buffer.from(JSON.stringify(record)).toString('base64')}});

test('declaration never defaults model, version or official origin and already-target is not a downgrade',()=>{
 assert.deepEqual(validateCameraDeclaration(camera),camera);
 for(const declaration of [{}, {...camera,model:''}, {...camera,version:''}, {...camera,origin:''}, {...camera,origin:'m10v'}, {...camera,version:'2.10'}, {...camera,model:'gr3x'}])assert.throws(()=>validateCameraDeclaration(declaration));
 assert.throws(()=>validateCameraDeclaration({...camera,version:'2.10'}),/已是目标版本/);
 assert.deepEqual(validateCameraDeclaration({model:'gr3x',version:'1.70',origin:'official'}),{model:'gr3x',version:'1.70',origin:'official'});
});
test('prepared plan must bind exact camera, official source and restore hashes',()=>{
 assert.deepEqual(validatePreparedPlan(plan,camera),plan);
 for(const change of [{ready:false},{model:'gr3x'},{from_version:'2.10'},{to_version:'2.20'},{source_sha256:''},{restore_sha256:''},{plan_id:'../other'},{filename:'../other.zip'}])assert.throws(()=>validatePreparedPlan({...plan,...change},camera));
});
test('download requires authenticated audit and local ZIP bytes hash before it can be saved',async()=>{
 const response=reply(),record=readDowngradeSafety(response);
 assert.deepEqual(await verifyDowngradeBlob(await response.blob(),{plan,camera,audit:record,response}),record);
 for(const change of [{plan_id:undefined},{plan_id:'f'.repeat(64)},{schema:'other'},{model:'gr3x'},{from_version:'2.10'},{to_version:'1.60'},{filename:'other.zip'},{source_sha256:'d'.repeat(64)},{restore_sha256:'d'.repeat(64)},{candidate_sha256:'d'.repeat(64)},{candidate_bytes:bytes.length+1},{exact_rebuild:false},{camera_tested:true},{installation_allowed:true}]){
  const response=reply({...audit,...change});await assert.rejects(verifyDowngradeBlob(await response.blob(),{plan,camera,audit:readDowngradeSafety(response),response}));
 }
 const corrupted=reply(audit,Buffer.from('corrupted'));await assert.rejects(verifyDowngradeBlob(await corrupted.blob(),{plan,camera,audit,response:corrupted}));
 assert.throws(()=>readDowngradeSafety(new Response('missing')),/验证/);
});
test('redownload binds the final receipt and validates response filename and MIME again',async()=>{
 for(const changes of [{'Content-Type':'text/html'},{'Content-Disposition':'attachment; filename="other.zip"'}]){
  const response=reply();for(const [key,value] of Object.entries(changes))response.headers.set(key,value);
  await assert.rejects(verifyDowngradeBlob(await response.blob(),{plan,camera,audit,response,expectedAudit:audit}));
 }
 const response=reply();await assert.rejects(verifyDowngradeBlob(await response.blob(),{plan,camera,audit,response,expectedAudit:{...audit,candidate_sha256:'d'.repeat(64)}}));
});
const jobId='e'.repeat(48);
test('real queue phases lead to a ZIP download without firmware multipart parsing',async()=>{
 const calls=[],states=['running','ready'];
 const api=async(path,options={})=>{calls.push([path,options]);if(path.endsWith('/download'))return reply();return Response.json({job:{id:jobId,state:path.endsWith('/jobs')?'queued':states.shift(),phase:'verifying'}});};
 const phases=[];const result=await runDowngradeJob(api,plan,camera,{intervalMs:0,onProgress:job=>phases.push(job.state)});
 assert.deepEqual(phases,['queued','running','ready']);assert.equal(result.job.id,jobId);
 assert.equal(calls[0][0],'/api/downgrade/gr3/jobs');assert.deepEqual(JSON.parse(calls[0][1].body),{camera,accepted_plan_id:plan.plan_id,acknowledge_instructions:true});
 assert.equal(calls.at(-1)[1].headers.Accept,'application/zip');
});
test('cancel during creation keeps job identity then cancels the actual server job',async()=>{
 const calls=[];let finish;const created=new Promise(resolve=>{finish=resolve;});const controller=new AbortController();
 const api=async(path,options={})=>{calls.push([path,options]);if(path.endsWith('/jobs')){await created;return Response.json({job:{id:jobId,state:'queued'}});}return Response.json({job:{id:jobId,state:'cancelled'}});};
 const pending=runDowngradeJob(api,plan,camera,{signal:controller.signal,intervalMs:0});controller.abort();finish();await assert.rejects(pending,/取消/);
 assert.equal(calls.filter(([path])=>path.endsWith('/cancel')).length,1);assert.equal(calls.at(-1)[1].keepalive,true);assert.equal(calls.at(-1)[1].signal,undefined);
 assert.equal(calls.some(([path])=>path.endsWith('/download')),false);
});
test('failed, expired, mismatched or unknown jobs never download',async()=>{
 for(const job of [{id:jobId,state:'failed'},{id:jobId,state:'expired'},{id:jobId,state:'unknown'},{id:'../elsewhere',state:'ready'}]){
  const calls=[];const api=async path=>{calls.push(path);return Response.json({job});};await assert.rejects(runDowngradeJob(api,plan,camera,{intervalMs:0}));assert.equal(calls.some(path=>path.endsWith('/download')),false);
 }
});
test('usable two-stage UI has explicit declarations, download receipt, cancellation and separate stage instructions',async()=>{
 const html=await readFile(new URL('../web/gr3/downgrade.html',import.meta.url),'utf8');
 for(const id of ['downgrade-model','downgrade-version','downgrade-origin','downgrade-prepare','downgrade-generate','downgrade-cancel','downgrade-again','downgrade-receipt'])assert.ok(html.includes(`id="${id}"`),id);
 assert.match(html,/第一阶段/);assert.match(html,/第二阶段/);assert.match(html,/重启/);assert.match(html,/尚未实机验证/);assert.doesNotMatch(html,/尚未开放|离线研究中|不提供降级包/);
 const guide=await readFile(new URL('../web/guide.html',import.meta.url),'utf8');assert.match(guide,/href="\/gr3\/downgrade.html"/);assert.doesNotMatch(guide,/不进行适配或提供降级包|不支持适配或降级/);
});

test('queue progress reads the real queue position field',()=>{
 assert.equal(downgradeJobProgress({state:'queued',position:3}),'等待生成 · 队列位置 3');
 assert.equal(downgradeJobProgress({state:'queued',position:0}),'等待生成');
 assert.match(downgradeJobProgress({state:'running',phase:'verifying'}),/离线回读校验/);
});
