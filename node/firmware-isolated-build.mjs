import {Worker} from 'node:worker_threads';
import {readCheckedProject} from './firmware-checked-build.mjs';
import {checkWebBuild,acceptVerifiedWorkerResult} from './firmware-web-safety.mjs';
import {createGRemotePackage} from './gr3-gremote-package.mjs';

export function isolatedFirmwareJob(store,id,input,kind='native'){
 const request=structuredClone(input);
 return async({signal,setPhase})=>{
  signal.throwIfAborted();
  const {source}=await readCheckedProject(store,id);checkWebBuild(source,request.camera,request);
  const copy=Uint8Array.from(source); // Never detach the store's official buffer.
  const worker=new Worker(new URL('./firmware-build-worker.mjs',import.meta.url),{
   workerData:{source:copy,id,input:request,kind},transferList:[copy.buffer]});
  const cancel=()=>worker.postMessage({type:'cancel'});
  signal.addEventListener('abort',cancel,{once:true});if(signal.aborted)cancel();
  try{
   const value=await new Promise((resolve,reject)=>{
    worker.on('message',message=>{
     if(message.type==='phase'){setPhase(message.phase);return;}
     if(message.type==='result')resolve(message.result);
     if(message.type==='error')reject(Object.assign(new Error(message.error.message),message.error));
    });
    worker.once('error',reject);
    worker.once('exit',code=>reject(new Error(`固件执行线程退出（${code}），没有发布下载结果。`)));
   });
   signal.throwIfAborted();
   const candidate=Buffer.from(value.candidate.buffer,value.candidate.byteOffset,value.candidate.byteLength);
   const verified=acceptVerifiedWorkerResult(source,request.camera,{...value,candidate},request.accepted_configuration_sha256);
   if(kind==='native'&&request.gremote_enabled===true){
    setPhase('verifying');
    const packaged=await createGRemotePackage({...verified,receipt:{...value.receipt,safety:verified.audit}},{signal});
    return {...packaged,headers:{...verified.headers,...packaged.headers}};
   }
   return verified;
  }finally{signal.removeEventListener('abort',cancel);await worker.terminate();}
 };
}
