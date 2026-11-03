import {parentPort,workerData} from 'node:worker_threads';
import {exportAnniversaryDowngrade} from './gr3-anniversary-downgrade.mjs';
const bytes=v=>Buffer.from(v.buffer,v.byteOffset,v.byteLength);
try{
 const {model,input}=workerData,newSource=bytes(workerData.newSource),oldSource=bytes(workerData.oldSource);
 const first=exportAnniversaryDowngrade(newSource,oldSource,model,input);
 const candidate=first.zip.byteOffset===0&&first.zip.buffer.byteLength===first.zip.length
  ?new Uint8Array(first.zip.buffer):Uint8Array.from(first.zip);
 parentPort.postMessage({type:'result',candidate,receipt:first.receipt,filename:first.filename},[candidate.buffer]);
}catch(error){parentPort.postMessage({type:'error',message:error?.message||'降级套件构建失败'});}
finally{parentPort.close();}
