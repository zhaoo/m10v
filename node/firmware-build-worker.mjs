import {parentPort,workerData} from 'node:worker_threads';
import {checkedFirmwareJob} from './firmware-checked-build.mjs';
const controller=new AbortController();
parentPort.on('message',message=>{if(message?.type==='cancel')controller.abort();});
try{
 const source=Buffer.from(workerData.source.buffer,workerData.source.byteOffset,workerData.source.byteLength);
 const store={readOriginal:async id=>{if(id!==workerData.id)throw Error('执行线程项目身份不符。');return source;}};
 const result=await checkedFirmwareJob(store,workerData.id,workerData.input,workerData.kind)({
  signal:controller.signal,setPhase:phase=>parentPort.postMessage({type:'phase',phase})});
 if(controller.signal.aborted)throw controller.signal.reason;
 parentPort.postMessage({type:'result',result},[result.candidate.buffer]);
}catch(error){parentPort.postMessage({type:'error',error:{name:error?.name,code:error?.code,message:error?.message||'固件构建失败。'}});}
finally{parentPort.close();}
