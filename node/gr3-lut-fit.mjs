import {loadFitEnvelope} from './gr3-fit-envelope.mjs';
import { access } from 'node:fs/promises';
import { Worker } from 'node:worker_threads';

const workerUrl = new URL('./gr3-lut-worker.mjs', import.meta.url);
const moduleUrl = new URL('../.runtime/grlife/web/firmware-store/film-fit.js', import.meta.url);

export async function fitCube(bytes, filename = 'Imported LUT.cube', {signal,model='gr3',approximationStrength,sourceSha256,inputType,provenance} = {}) {
  if(signal?.aborted) throw new Error('LUT拟合已取消');
  if (!Buffer.isBuffer(bytes) || bytes.length === 0 || bytes.length > 8 * 1024 * 1024)
    throw new Error('LUT 文件必须非空且不超过 8 MiB');
  if (!/^[^/\\\0]{1,100}\.cube$/i.test(filename)) throw new Error('选择 sRGB .cube 文件');
  if(!['gr3','gr3x'].includes(model))throw new Error('不支持的拟合机型');
  if(approximationStrength!==undefined&&(!Number.isFinite(approximationStrength)||approximationStrength<0||approximationStrength>=1))throw new Error('近似强度须为0至小于1');
  await access(moduleUrl);
  const envelope=await loadFitEnvelope(model);
  if(signal?.aborted) throw new Error('LUT拟合已取消');
  return await new Promise((resolve, reject) => {
    const worker = new Worker(workerUrl, { execArgv: [],
      workerData: { cube: bytes.toString('utf8'), filename,model,approximationStrength,sourceSha256,inputType,provenance,envelope } });
    const abort=()=>{worker.terminate();clearTimeout(timeout);signal?.removeEventListener('abort',abort);reject(new Error('LUT拟合已取消'));};
    signal?.addEventListener('abort',abort,{once:true});
    const timeout = setTimeout(() => { worker.terminate(); reject(new Error('LUT 拟合超时')); }, 90000);
    worker.once('message', (result) => {
      clearTimeout(timeout);signal?.removeEventListener('abort',abort);
      worker.terminate();
      result.error ? reject(new Error(result.error)) : resolve(result);
    });
    worker.once('error', (error) => { clearTimeout(timeout);signal?.removeEventListener('abort',abort); reject(error); });
    worker.once('exit', (code) => {
      signal?.removeEventListener('abort',abort);
      if (code !== 0) { clearTimeout(timeout); reject(new Error('LUT 拟合进程异常退出')); }
    });
  });
}
