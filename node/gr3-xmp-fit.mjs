import {sha256} from './gr3-fit-binding.mjs';
import {execFile} from 'node:child_process';import {promisify} from 'node:util';
import {mkdtemp,writeFile,rm} from 'node:fs/promises';import path from 'node:path';import os from 'node:os';
import {fileURLToPath} from 'node:url';import {fitCube} from './gr3-lut-fit.mjs';
const exec=promisify(execFile);
export async function fitXmp(bytes,filename='Imported.xmp',{signal,model='gr3',approximationStrength}={}){
 if(!Buffer.isBuffer(bytes)||bytes.length===0||bytes.length>8*1024*1024||!/^[^/\\\0]{1,100}\.xmp$/i.test(filename))
  throw new Error('请选择非空且不超过8 MiB的XMP文件');
 const folder=await mkdtemp(path.join(os.tmpdir(),'m10v-gr3-xmp-'));
 try{
  const input=path.join(folder,'input.xmp');await writeFile(input,bytes,{mode:0o600});
  let converted;
  try{const {stdout}=await exec(process.env.M10V_XMP_PYTHON||fileURLToPath(new URL('../.venv/bin/python3.12',import.meta.url)),
    [fileURLToPath(new URL('./gr3-xmp-worker.py',import.meta.url)),input],{signal,timeout:30000,maxBuffer:8*1024*1024});
   converted=JSON.parse(stdout);
  }catch(error){if(signal?.aborted)throw new Error('XMP转换已取消');throw new Error((error.stderr||error.message).trim().slice(-1000));}
  const result=await fitCube(Buffer.from(converted.cube),filename.replace(/\.xmp$/i,'.cube'),{signal,model,approximationStrength,sourceSha256:sha256(bytes),inputType:'xmp',provenance:{base_profile_reconstructed:false,inventory:converted.inventory,grid_size:converted.gridSize}});
  return {...result,provenance:{...result.provenance,targetModel:model==='gr3x'?'GR IIIx':'GR III',approximate:true,baseProfileReconstructed:false,
    gridSize:converted.gridSize,inventory:converted.inventory}};
 }finally{await rm(folder,{recursive:true,force:true});}
}
