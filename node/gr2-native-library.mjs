// GR II experimental build bridge. Production/device gates remain closed.
import {createHash} from 'node:crypto';
import {readFile,readdir,mkdtemp,writeFile,rm,access} from 'node:fs/promises';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import path from 'node:path';
import os from 'node:os';
import {fileURLToPath} from 'node:url';
import {normalizeConfiguration,defaultConfiguration} from '../web/gr2/native-library-state.mjs';
import {initialState} from '../compat/gr2-v1/node/gr3-native-library.mjs';
import {readUnityModelComponent} from './unity-firmware.mjs';
import {packGr2Candidate} from './gr2-candidate-container.mjs';
const root=fileURLToPath(new URL('..',import.meta.url)),run=promisify(execFile);
const sha=x=>createHash('sha256').update(x).digest('hex');
const need=(ok,message)=>{if(!ok)throw Error(message);};
export async function gr2BuildFingerprint(){
 const h=createHash('sha256');
 async function walk(relative){for(const entry of (await readdir(path.join(root,relative),{withFileTypes:true})).sort((a,b)=>a.name.localeCompare(b.name))){
  if(entry.name==='__pycache__')continue;
  const name=path.join(relative,entry.name);
  if(entry.isDirectory())await walk(name);
  else if(entry.isFile()){h.update(name+'\0');h.update(await readFile(path.join(root,name)));}
 }}
 for(const dir of ['native/gr2','compat/gr2-v1','scripts','node'])await walk(dir);
 for(const file of ['web/gr2/native-library-state.mjs','web/gr3/5207-lut.json','web/gr3/harman-luts.json','web/gr3/curated-luts.json','web/gr3/newstocks-luts.json','native/gr3/m10v_film_card.c','native/gr3/m10v_film_card.h','native/gr3/m10v_film_card_data.h']){h.update(file+'\0');h.update(await readFile(path.join(root,file)));}
 return h.digest('hex');
}
export async function prepareGr2Native(source,value=defaultConfiguration()){
 readUnityModelComponent(source,'gr2','b01firm8');
 const configuration=normalizeConfiguration(value);
 const source_sha256=sha(source),runtime_source_sha256=await gr2BuildFingerprint();
 const configuration_sha256=sha(JSON.stringify({source_sha256,runtime_source_sha256,configuration}));
 return {schema:'m10v-gr2-experimental-plan/v1',ready:true,status:'experimental_offline',model:'GR II',filename:'rg2_v003.frm',source_sha256,runtime_source_sha256,configuration_sha256,configuration,hardware_verified:false,release_ready:false,
  initial_settings_policy:'已有有效机内胶卷和 HDF 存档分别优先；确证首次使用才采用网页配置。',initial_hdf_strength:configuration.hdf,
  limitations:['完整启动、缓存和拍摄链尚待真机验证','第一版仅接入已实现的五槽胶卷、细节设置、SD 胶卷、时间戳与独立 HDF 菜单；配方及其他工具继续开发']};
}
let building=false;
export async function generateGr2Native(source,value,accepted,{signal}={}){
 signal?.throwIfAborted();
 const plan=await prepareGr2Native(source,value);
 need(accepted===plan.configuration_sha256,'配置或构建源码已变化，请重新预检');
 need(!building,'另一个 GR II 构建正在执行');building=true;let folder;
 try{
  folder=await mkdtemp(path.join(os.tmpdir(),'m10v-gr2-candidate-'));
  const original=readUnityModelComponent(source,'gr2','b01firm8');
  await writeFile(path.join(folder,'official.bin'),original);
  await writeFile(path.join(folder,'configuration.json'),JSON.stringify(plan.configuration));
  let python=path.join(root,'.venv/bin/python');try{await access(python);}catch{python='python3';}
  const options={cwd:root,signal,timeout:180000,maxBuffer:2*1024*1024,env:{...process.env,M10V_NODE:process.execPath}};
  await run(python,['scripts/build_gr2_runtime.py','--component',path.join(folder,'official.bin'),'--configuration',path.join(folder,'configuration.json'),'--out',path.join(folder,'runtime')],options);
  await run(python,['scripts/build_gr2_component.py','--official',path.join(folder,'official.bin'),'--runtime-audit',path.join(folder,'runtime/runtime-audit.json'),'--out',path.join(folder,'component.bin')],options);
  const runtime=JSON.parse(await readFile(path.join(folder,'runtime/runtime-audit.json'))),audit=JSON.parse(await readFile(path.join(folder,'component.bin.audit.json'))),component=await readFile(path.join(folder,'component.bin'));
  need(runtime.official_sha256===sha(original)&&audit.official_sha256===sha(original),'原厂组件绑定不一致');
  need(runtime.endianness==='big'&&runtime.be8===false&&runtime.base===0xa0798000&&runtime.memory_bytes<=0x68000,'GR II 运行体 ABI 或内存边界不一致');
  const bytes=Buffer.from(runtime.runtime_hex,'hex');
  need(bytes.length===runtime.code_bytes&&sha(bytes)===runtime.runtime_sha256&&audit.runtime_sha256===runtime.runtime_sha256,'原生运行体摘要不一致');
  need(runtime.initial_state_wire_hex===initialState(plan.configuration).toString('hex')&&runtime.initial_hdf_strength===plan.configuration.hdf,'初始配置回读不一致');
  need(sha(component)===audit.sha256&&audit.file_bytes===component.length,'组件摘要不一致');
  const reconstructed=Buffer.alloc(component.length);original.copy(reconstructed);
  const offset=512+Math.ceil((original.length-512)/512)*512;need(offset+bytes.length===component.length,'运行体追加边界不一致');bytes.copy(reconstructed,offset);
  const occupied=[];
  for(const p of audit.patches){const before=Buffer.from(p.expected_hex,'hex'),after=Buffer.from(p.replacement_hex,'hex');
   need(Number.isInteger(p.offset)&&p.offset>=0&&p.offset+p.bytes<=original.length&&before.length===p.bytes&&after.length===p.bytes,'补丁边界不一致');
   need(!occupied.some(([a,b])=>p.offset<b&&a<p.offset+p.bytes)&&original.subarray(p.offset,p.offset+p.bytes).equals(before),'补丁重叠或原始字节不一致');
   occupied.push([p.offset,p.offset+p.bytes]);after.copy(reconstructed,p.offset);
  }
  need(reconstructed.equals(component),'组件独立重建回读不一致');
  const nativeState=Buffer.from(runtime.initial_state_native_hex,'hex');need(nativeState.length===104&&bytes.includes(nativeState),'BE32 初始配置未写入运行体');
  need(await gr2BuildFingerprint()===plan.runtime_source_sha256,'构建中源码已变化，请重新构建');signal?.throwIfAborted();
  const packed=packGr2Candidate(source,component);
  return {...packed,plan,runtime,audit,receipt:{...packed.receipt,configuration_sha256:plan.configuration_sha256,runtime_source_sha256:plan.runtime_source_sha256,runtime_sha256:runtime.runtime_sha256,initial_hdf_strength:runtime.initial_hdf_strength,independent_component_reconstruction:true}};
 }finally{try{if(folder)await rm(folder,{recursive:true,force:true});}finally{building=false;}}
}
