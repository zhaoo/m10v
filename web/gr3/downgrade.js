const ROUTES = Object.freeze({gr3:{name:'GR III',from:'2.20',to:'2.10'},gr3x:{name:'GR IIIx',from:'1.70',to:'1.60'}});
const SHA256 = /^[a-f0-9]{64}$/i;
const JOB_ID = /^[a-f0-9]{48}$/;
const MAX_BYTES = 256 * 1024 * 1024;
const auditFields = ['plan_id','schema','model','from_version','to_version','source_sha256','restore_sha256','candidate_sha256','candidate_bytes','filename','exact_rebuild','camera_tested','installation_allowed'];
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const sameHash = (left,right) => typeof left === 'string' && typeof right === 'string' && SHA256.test(left) && SHA256.test(right) && left.toLowerCase() === right.toLowerCase();
const stopped = () => new Error('降级任务已取消。');

export function validateCameraDeclaration(camera) {
  if (!record(camera) || !Object.hasOwn(ROUTES,camera.model)) throw new Error('请明确选择相机型号。');
  const route=ROUTES[camera.model];
  if (camera.version === route.to) throw new Error(`当前已是目标版本 ${route.to}，无需二阶降级，可直接前往工作台。`);
  if (camera.version !== route.from) throw new Error(`请确认机身当前版本为 ${route.from}；其他版本不能使用此降级包。`);
  if (camera.origin !== 'official') throw new Error('请确认当前运行的是对应版本的理光官方固件。');
  return {model:camera.model,version:camera.version,origin:camera.origin};
}
export function validatePreparedPlan(plan,camera) {
  validateCameraDeclaration(camera);
  const route=ROUTES[camera.model];
  if (!record(plan) || plan.ready !== true || typeof plan.plan_id !== 'string' || !/^[a-zA-Z0-9_-]{16,128}$/.test(plan.plan_id)
      || plan.model !== camera.model || plan.from_version !== route.from || plan.to_version !== route.to
      || !sameHash(plan.source_sha256,plan.source_sha256) || !sameHash(plan.restore_sha256,plan.restore_sha256)
      || typeof plan.filename !== 'string' || !/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,150}\.zip$/.test(plan.filename)) {
    throw new Error('降级预检信息与相机声明不匹配，请重新预检。');
  }
  return plan;
}
export function readDowngradeSafety(response) {
  try {
    const encoded=response.headers.get('X-M10V-Downgrade-Safety');
    if (!encoded || encoded.length>64*1024 || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(encoded)) throw new Error();
    const binary=atob(encoded), audit=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(Uint8Array.from(binary,char=>char.charCodeAt(0))));
    if (!record(audit)) throw new Error();
    return audit;
  } catch { throw new Error('降级包验证信息缺失或格式无效，已停止下载。'); }
}
export async function verifyDowngradeBlob(blob,{plan,camera,audit,response,expectedAudit}={}) {
  validatePreparedPlan(plan,camera);
  if (!record(audit) || audit.schema!=='m10v-anniversary-downgrade-safety/v1' || audit.exact_rebuild!==true || audit.camera_tested!==false || audit.installation_allowed!==false) throw new Error('降级包离线验证证据不完整，已停止下载。');
  for (const field of ['model','from_version','to_version','filename']) if (audit[field]!==plan[field]) throw new Error('降级包型号、版本或文件名与预检不符，已停止下载。');
  for (const field of ['source_sha256','restore_sha256']) if (!sameHash(audit[field],plan[field])) throw new Error('降级包官方来源摘要与预检不符，已停止下载。');
  if (audit.plan_id!==plan.plan_id) throw new Error('降级包预检标识不匹配，已停止下载。');
  if (expectedAudit && (!record(expectedAudit) || auditFields.some(field=>audit[field]!==expectedAudit[field]))) throw new Error('降级包与上次下载回执不一致，请重新预检。');
  if (!(blob instanceof Blob) || !Number.isSafeInteger(audit.candidate_bytes) || audit.candidate_bytes<=0 || audit.candidate_bytes>MAX_BYTES || blob.size!==audit.candidate_bytes || !sameHash(audit.candidate_sha256,audit.candidate_sha256)) throw new Error('降级包大小或摘要信息无效，已停止下载。');
  for (const field of ['candidate_bytes','candidate_sha256']) if (Object.hasOwn(plan,field) && plan[field]!==audit[field]) throw new Error('降级包与预检产物不一致，已停止下载。');
  const mime=response?.headers?.get('Content-Type')?.split(';')[0].trim().toLowerCase();
  const disposition=response?.headers?.get('Content-Disposition')||'';
  const filename=/filename\s*=\s*"([^"]+)"/i.exec(disposition)?.[1] || /filename\s*=\s*([^;\s]+)/i.exec(disposition)?.[1];
  if (mime!=='application/zip' || filename!==plan.filename) throw new Error('下载响应的文件类型或文件名不匹配，已停止下载。');
  if (typeof globalThis.crypto?.subtle?.digest!=='function') throw new Error('当前浏览器无法进行 SHA-256 验证，请使用 HTTPS 或本机浏览器访问。');
  const buffer=await blob.arrayBuffer();
  const digest=await crypto.subtle.digest('SHA-256',buffer);
  const actual=Array.from(new Uint8Array(digest),byte=>byte.toString(16).padStart(2,'0')).join('');
  if (buffer.byteLength!==audit.candidate_bytes || !sameHash(actual,audit.candidate_sha256)) throw new Error('下载 ZIP 的 SHA-256 不匹配，已停止下载。');
  return audit;
}
export function downgradeJobProgress(job) {
  if(job.state==='queued')return `等待生成${Number.isInteger(job.position)&&job.position>0?` · 队列位置 ${job.position}`:''}`;
  if(job.state==='ready')return '生成完成，正在下载 ZIP…';
  if(job.phase==='verifying'||job.state==='verifying')return '正在执行离线回读校验…';
  return '正在生成两阶段降级包…';
}
function wait(ms,signal) {
  return new Promise((resolve,reject)=>{
    const abort=()=>{clearTimeout(timer);signal.removeEventListener('abort',abort);reject(stopped());};
    const timer=setTimeout(()=>{signal.removeEventListener('abort',abort);resolve();},ms);
    signal.addEventListener('abort',abort,{once:true});if(signal.aborted)abort();
  });
}
function abortable(promise,signal) {
  return new Promise((resolve,reject)=>{
    const abort=()=>reject(stopped());signal.addEventListener('abort',abort,{once:true});
    Promise.resolve(promise).then(value=>{signal.removeEventListener('abort',abort);signal.aborted?reject(stopped()):resolve(value);},error=>{signal.removeEventListener('abort',abort);reject(error);});
    if(signal.aborted)abort();
  });
}
export async function runDowngradeJob(api,plan,camera,{signal,onProgress,intervalMs=1000}={}) {
  validatePreparedPlan(plan,camera);
  if(!Number.isFinite(intervalMs)||intervalMs<0||intervalMs>60000)throw new Error('任务轮询间隔无效。');
  if(signal?.aborted)throw stopped();
  const lifecycle=new AbortController();let jobId,cancellationSent=false,timedOut=false;
  const cancel=()=>{if(!jobId||cancellationSent)return;cancellationSent=true;try{void Promise.resolve(api(`/api/firmware-jobs/${jobId}/cancel`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',keepalive:true})).catch(()=>{});}catch{}};
  const abort=()=>{lifecycle.abort();cancel();};signal?.addEventListener('abort',abort,{once:true});
  const timeout=setTimeout(()=>{timedOut=true;abort();},20*60*1000);
  const ensure=()=>{if(timedOut)throw new Error('降级任务等待超时，请重新生成。');if(signal?.aborted||lifecycle.signal.aborted)throw stopped();};
  const read=async response=>{const payload=await response.json(),job=payload?.job;if(!record(job)||typeof job.id!=='string'||!JOB_ID.test(job.id)||(jobId&&job.id!==jobId))throw new Error('降级任务标识无效或发生变化。');return job;};
  try {
    // Keep creation alive until its ID is known, so cancellation cannot orphan a build.
    let job=await read(await api(`/api/downgrade/${camera.model}/jobs`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({camera,accepted_plan_id:plan.plan_id,acknowledge_instructions:true})}));
    jobId=job.id;
    for(;;){
      ensure();
      if(job.state==='failed')throw new Error('降级包生成或离线验证失败，请重新生成。');
      if(job.state==='cancelled')throw stopped();
      if(job.state==='expired'||(job.expiresAt!=null&&(!Number.isFinite(job.expiresAt)||job.expiresAt<=Date.now())))throw new Error('降级包已过期，请重新生成。');
      if(!['queued','running','generating','verifying','ready'].includes(job.state))throw new Error('降级任务状态无效。');
      onProgress?.(job);ensure();
      if(job.state==='ready'){
        const response=await abortable(api(`/api/firmware-jobs/${jobId}/download`,{headers:{Accept:'application/zip'},signal:lifecycle.signal}),lifecycle.signal);ensure();
        if(!(response instanceof Response))throw new Error('降级包下载响应无效。');
        return {response,job};
      }
      await wait(intervalMs,lifecycle.signal);ensure();
      job=await abortable((async()=>read(await api(`/api/firmware-jobs/${jobId}`,{signal:lifecycle.signal})))(),lifecycle.signal);
    }
  }catch(error){cancel();ensure();throw error instanceof Error?error:new Error('降级任务请求失败。');}
  finally{clearTimeout(timeout);signal?.removeEventListener('abort',abort);}
}

async function mountDowngrade() {
  const $=id=>document.getElementById(id);
  let token='',availability=null,plan=null,finalResult=null,controller=null,busy=false,revision=0;
  const declaration=()=>({model:$('downgrade-model').value,version:$('downgrade-version').value,origin:$('downgrade-origin').value});
  const status=(message,error=false)=>{$('downgrade-status').textContent=message;$('downgrade-status').dataset.error=String(error);};
  const update=()=>{
    $('downgrade-prepare').disabled=busy||!token||!availability;
    $('downgrade-generate').disabled=busy||!plan||!$('downgrade-instructions').checked;
    $('downgrade-cancel').hidden=!busy;$('downgrade-again').hidden=!finalResult;
    $('downgrade-again').disabled=busy;$('downgrade-plan').hidden=!plan;
    $('downgrade-instructions').disabled=busy||!plan;
  };
  const api=async(path,options={})=>{
    const response=await fetch(path,{...options,headers:{'X-M10V-Token':token,...options.headers}});
    if(!response.ok){let message=`请求失败（HTTP ${response.status}），请重试。`;try{const body=await response.json();if(typeof body.error==='string'&&!/https?:\/\/|\/Users\/|Traceback/.test(body.error))message=body.error;}catch{}throw new Error(message);}return response;
  };
  const reset=()=>{revision++;controller?.abort();controller=null;busy=false;plan=null;finalResult=null;$('downgrade-receipt').hidden=true;$('downgrade-instructions').checked=false;update();};
  for(const id of ['downgrade-model','downgrade-version','downgrade-origin'])$(id).addEventListener('change',()=>{
    reset();
    if(id==='downgrade-model'){$('downgrade-version').value='';$('downgrade-origin').value='';}
    const route=ROUTES[$('downgrade-model').value];
    $('downgrade-route').textContent=route?`${route.name} ${route.from} → ${route.to}`:'GR III 2.20 → 2.10 · GR IIIx 1.70 → 1.60';
    status('请确认当前机身信息，再进行预检。');
  });
  $('downgrade-instructions').addEventListener('change',update);
  $('downgrade-cancel').addEventListener('click',()=>{reset();status('任务已取消，请重新预检。');});
  window.addEventListener('pagehide',()=>{revision++;controller?.abort();});
  $('downgrade-prepare').addEventListener('click',async()=>{
    reset();const current=revision;controller=new AbortController();const operation=controller;
    try{
      const camera=validateCameraDeclaration(declaration());const route=ROUTES[camera.model],available=availability?.models?.[camera.model];
      if(!available||available.available!==true||available.from_version!==route.from||available.to_version!==route.to)throw new Error('服务状态发生变化，请刷新后重试。');
      busy=true;update();status('正在核对官方来源与两阶段方案…');
      const response=await api(`/api/downgrade/${camera.model}/prepare`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({camera}),signal:operation.signal});
      const prepared=validatePreparedPlan(await response.json(),camera);if(operation.signal.aborted||current!==revision)return;
      plan=prepared;$('downgrade-plan-copy').textContent=`${route.name} ${plan.from_version} → ${plan.to_version} · ${plan.filename}`;
      status('预检通过。确认两阶段操作顺序后，即可生成下载。');
    }catch(error){if(current===revision)status(error.message,true);}finally{if(current===revision){busy=false;controller=null;update();}}
  });
  const save=async(response,expectedPlan,camera,job,expectedAudit,operation,current)=>{
    status('下载完成，正在核验 ZIP 字节与 SHA-256…');
    const audit=readDowngradeSafety(response),blob=await response.blob();
    await verifyDowngradeBlob(blob,{plan:expectedPlan,camera,audit,response,expectedAudit});
    if(operation.signal.aborted||current!==revision)throw stopped();
    finalResult={plan:expectedPlan,camera,job,audit};
    const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=expectedPlan.filename;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
    $('downgrade-receipt').hidden=false;$('downgrade-filename').textContent=expectedPlan.filename;$('downgrade-hash').textContent=audit.candidate_sha256;
    $('downgrade-bytes').textContent=`${audit.candidate_bytes.toLocaleString()} 字节 · 离线校验通过 · 尚未实机验证`;
    status('降级包已校验并下载。请严格按第一阶段、重启确认、第二阶段的顺序操作。');
  };
  $('downgrade-generate').addEventListener('click',async()=>{
    if(busy||!plan||!$('downgrade-instructions').checked)return;
    const expectedPlan=plan,camera=validateCameraDeclaration(declaration()),current=revision;
    const operation=new AbortController();controller=operation;busy=true;finalResult=null;$('downgrade-receipt').hidden=true;update();
    try{
      const {response,job}=await runDowngradeJob(api,expectedPlan,camera,{signal:operation.signal,onProgress:job=>{
        if(current!==revision)return;
        status(downgradeJobProgress(job));
      }});
      await save(response,expectedPlan,camera,job,null,operation,current);
    }catch(error){if(current===revision)status(error.message,true);}finally{if(current===revision){busy=false;controller=null;update();}}
  });
  $('downgrade-again').addEventListener('click',async()=>{
    if(busy||!finalResult)return;const result=finalResult,current=revision,operation=new AbortController();controller=operation;busy=true;update();
    try{const response=await api(`/api/firmware-jobs/${result.job.id}/download`,{headers:{Accept:'application/zip'},signal:operation.signal});await save(response,result.plan,result.camera,result.job,result.audit,operation,current);}
    catch(error){if(current===revision)status(error.message,true);}finally{if(current===revision){busy=false;controller=null;update();}}
  });
  update();
  try{
    const responses=await Promise.all([fetch('/api/status'),fetch('/api/downgrade/status')]);
    if(responses.some(response=>!response.ok))throw new Error('服务信息读取失败，请刷新重试。');
    const [session,available]=await Promise.all(responses.map(response=>response.json()));
    if(typeof session.session_token!=='string'||!session.session_token||!record(available.models))throw new Error('服务信息无效，请刷新重试。');
    token=session.session_token;availability=available;status('选择相机并确认当前固件信息，开始预检。');
  }catch(error){status(error.message,true);}finally{update();}
}
if(typeof document!=='undefined'&&document.getElementById('downgrade-model'))void mountDowngrade();
