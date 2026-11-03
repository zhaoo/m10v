import {Worker} from 'node:worker_threads';
import {createHash} from 'node:crypto';
import {ANNIVERSARY_DOWNGRADE_PROFILES as profiles} from './gr3-anniversary-downgrade.mjs';
const issued=new WeakMap(),hash=b=>createHash('sha256').update(b).digest('hex');
function need(ok,message){if(!ok)throw Object.assign(Error('降级校验未通过：'+message),{code:'M10V_FIRMWARE_CHECK_FAILED'});}
export function checkDowngradeCamera(model,camera){
 const p=profiles[model];need(p&&camera&&typeof camera==='object'&&!Array.isArray(camera),'请选择实际机型与固件来源。');
 need(camera.model===model&&camera.version===p.from_version&&camera.origin==='official',
  `此路线仅适用于官方 ${p.model_label} ${p.from_version}；已是 ${p.to_version} 的机身使用普通工作台。`);
 return p;
}
function withAbort(promise,signal){
 return new Promise((resolve,reject)=>{
  const stop=()=>{signal.removeEventListener('abort',stop);reject(signal.reason||Error('任务已取消。'));};
  signal.addEventListener('abort',stop,{once:true});
  Promise.resolve(promise).then(value=>{signal.removeEventListener('abort',stop);resolve(value);},error=>{signal.removeEventListener('abort',stop);reject(error);});
  if(signal.aborted)stop();
 });
}
export function anniversaryDowngradeJob(loadSources,model,request,preparedPlan){
 const input=structuredClone(request),p=checkDowngradeCamera(model,input.camera),plan=Object.freeze({...preparedPlan});
 need(plan.model===model&&plan.source_sha256===p.source_sha256&&plan.restore_sha256===p.restore_sha256&&
  input.accepted_plan_id===plan.plan_id&&input.acknowledge_instructions===true,'请先核验并确认两阶段方案。');
 return async({signal,setPhase})=>{
  signal=AbortSignal.any([signal,AbortSignal.timeout(5*60*1000)]);
  signal.throwIfAborted();const {newSource,oldSource}=await withAbort(loadSources(model),signal);signal.throwIfAborted();
  const run=async()=>{
   signal.throwIfAborted();const newCopy=Uint8Array.from(newSource),oldCopy=Uint8Array.from(oldSource);
   const worker=new Worker(new URL('./anniversary-downgrade-worker.mjs',import.meta.url),{
    workerData:{model,newSource:newCopy,oldSource:oldCopy,input:{accepted_plan_id:plan.plan_id,acknowledge_instructions:true}},
    transferList:[newCopy.buffer,oldCopy.buffer]});
   const cancel=()=>{void worker.terminate();};signal.addEventListener('abort',cancel,{once:true});if(signal.aborted)cancel();
   try{
    return await new Promise((resolve,reject)=>{
     worker.on('message',message=>{
      if(message.type==='result')resolve(message);
      else if(message.type==='error')reject(Error(message.message));
     });
     worker.once('error',reject);worker.once('exit',()=>reject(Error('降级执行线程结束，未交付校验结果。')));
    });
   }finally{signal.removeEventListener('abort',cancel);await worker.terminate();}
  };
  // Destroy the first worker before the fresh second rebuild. Large decoded
  // buffers cannot accumulate across passes in the production process.
  setPhase('generating');const result=await run();signal.throwIfAborted();
  setPhase('verifying');const repeated=await run();signal.throwIfAborted();
  const candidate=Buffer.from(result.candidate.buffer,result.candidate.byteOffset,result.candidate.byteLength);
  const second=Buffer.from(repeated.candidate.buffer,repeated.candidate.byteOffset,repeated.candidate.byteLength),r=result.receipt;
  need(candidate.equals(second)&&r.candidate_sha256===repeated.receipt?.candidate_sha256,'两次完整构建的降级套件不同。');
   need(r?.source_sha256===p.source_sha256&&r.restore_sha256===p.restore_sha256&&
    r.model===model&&result.filename===p.zip_filename,'线程结果与本次来源或机型不符。');
   const audit=Object.freeze({schema:'m10v-anniversary-downgrade-safety/v1',model,from_version:p.from_version,to_version:p.to_version,
    plan_id:plan.plan_id,source_sha256:p.source_sha256,restore_sha256:p.restore_sha256,
    candidate_sha256:hash(candidate),candidate_bytes:candidate.length,filename:p.zip_filename,
    exact_rebuild:true,download_allowed:true,camera_tested:false,installation_allowed:false,
    stage_one_sha256:r.candidate_sha256,receipt:r});
   issued.set(audit,{hash:audit.candidate_sha256,bytes:candidate.length});
   return {candidate,filename:p.zip_filename,audit};
 };
}
export function requireAnniversaryDownload(candidate,audit){
 const proof=issued.get(audit);need(proof&&Buffer.isBuffer(candidate)&&candidate.length===proof.bytes&&hash(candidate)===proof.hash,
  '下载缺少本次完整校验记录或字节已变化。');return audit;
}
