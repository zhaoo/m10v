// GR IV owns its firmware ABI. Only semantic configuration is shared with GR III.
import {createHash} from 'node:crypto';
import {readFile,writeFile,mkdtemp,rm} from 'node:fs/promises';
import {existsSync} from 'node:fs';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import path from 'node:path';
import os from 'node:os';
import {fileURLToPath} from 'node:url';
import {normalizeConfiguration,normalizeExtensions} from '../web/gr3/native-library-state.mjs';
const root=fileURLToPath(new URL('..',import.meta.url)),run=promisify(execFile);
export const GR4_OFFICIAL_SHA256='a2f664dfca034059eb0fd6e18ab08684c326b4a034d85c164dad7e1ec9b5655f';
const hash=b=>createHash('sha256').update(b).digest('hex');
export function validateGr4Source(source){if(!Buffer.isBuffer(source)||hash(source)!==GR4_OFFICIAL_SHA256)throw Error('GR IV 官方固件摘要不匹配');}
export function normalizeGr4Request(value={}){
 const configuration=normalizeConfiguration(value.configuration),extensions=normalizeExtensions(value.extensions);
 if(configuration.slots.some(s=>s.film===294||(s.film>=306&&s.film<=317)))throw Error('新滤镜需要 GR III 已接入的 ISP 成片管线');
 if(configuration.zoom.write)throw Error('裁切焦距写入仅支持 GR III');
 if(configuration.slots.length>5)throw Error('GR IV 暂不支持导出超过 5 款胶卷');
 if(configuration.slots.some(s=>s.grain>0))throw Error('颗粒仅支持 GR III 原厂原生成像管线，请关闭颗粒后导出 GR IV');
 if(configuration.hdf)throw Error('数字 HDF 模拟当前仅支持普通 GR III');
 if(configuration.filmNameStamp)throw Error('胶卷名称水印当前仅支持 GR III / GR IIIx');
 const debug_mode=value.debug_mode??false;if(typeof debug_mode!=='boolean')throw Error('调试模式必须为布尔值');
 const version_unlock=value.version_unlock??{enabled:false};if(version_unlock?.enabled!==false||Object.keys(version_unlock).some(k=>k!=='enabled'))throw Error('GR IV 版本适配尚未验证');
 return {configuration,extensions,debug_mode,version_unlock:{enabled:false}};
}
async function invoke(source,input,{check=false,signal}={}){
 validateGr4Source(source);const config=normalizeGr4Request(input);
 const folder=await mkdtemp(path.join(os.tmpdir(),'m10v-gr4-native-'));
 try{
  const firmware=path.join(folder,'official.bin'),output=path.join(folder,'fwdc248b.bin'),reportFile=path.join(folder,'receipt.json'),configuration=path.join(folder,'configuration.json');
  await writeFile(firmware,source,{mode:0o400});await writeFile(configuration,JSON.stringify(config));
  const bundled=path.join(root,'.venv/bin/python'),python=process.env.M10V_PYTHON||(existsSync(bundled)?bundled:'python3');
  await run(python,['scripts/build_gr4_m10v_firmware.py','--input',firmware,'--config',configuration,'--report',reportFile,...(check?['--check']:['--output',output])],{cwd:root,signal,timeout:300000,maxBuffer:2*1024*1024,env:{...process.env,M10V_NODE:process.execPath}});
  const report=JSON.parse(await readFile(reportFile,'utf8'));
  if(report.source_sha256!==GR4_OFFICIAL_SHA256||report.camera_tested!==false||!/^[0-9a-f]{64}$/.test(report.runtime_source_sha256||''))throw Error('GR IV 构建身份回读不一致');
  if(check){if(report.ready!==true)throw Error('GR IV 原生组件尚未通过构建核验');return {report,config};}
  const candidate=await readFile(output);
  if(report.candidate_sha256!==hash(candidate)||report.candidate_bytes!==candidate.length||report.filename!=='fwdc248b.bin')throw Error('GR IV 固件摘要回读不一致');
  return {candidate,report,config};
 }finally{await rm(folder,{recursive:true,force:true});}
}
export async function prepareGr4Native(source,input,{signal}={}){
 const {report,config}=await invoke(source,input,{check:true,signal});
 const configuration_sha256=hash(JSON.stringify({source:GR4_OFFICIAL_SHA256,...config,runtime_source_sha256:report.runtime_source_sha256}));
 return {...report,...config,model:'GR IV',filename:'fwdc248b.bin',source_sha256:GR4_OFFICIAL_SHA256,configuration_sha256,ready:true,external_film_pack:true,camera_tested:false};
}
export function gr4DownloadReceipt(report){
 const {runtime,resources,patches,package:packageProof,update_policy_installation:policy,...receipt}=report;
 const compactPolicy=p=>p?{status:p.status,policy:p.policy,installed:p.installed,gate_sha256:p.gate_sha256,hardware:p.hardware}:undefined;
 return {...receipt,update_policy_installation:compactPolicy(policy),runtime:{base:runtime?.base,code_bytes:runtime?.code_bytes,code_sha256:runtime?.code_sha256},
  verified_hooks:patches?.length||0,icon_count:resources?resources.icon_last-resources.icon_first+1:0,
  package:packageProof?{decoded_sha256:packageProof.decoded_sha256,rtos_sha256:packageProof.rtos_sha256,
   layout_proof:packageProof.layout_proof?{...packageProof.layout_proof,update_policy:compactPolicy(packageProof.layout_proof.update_policy)}:undefined}:undefined};
}
let building=false;
export async function generateGr4Native(source,input,{signal}={}){
 if(building)throw Error('另一个 GR IV 固件正在构建');building=true;
 try{
  const plan=await prepareGr4Native(source,input,{signal});
  if(input.accepted_configuration_sha256!==plan.configuration_sha256)throw Error('配置已变化，请重新预检');
  const {candidate,report}=await invoke(source,input,{signal});
  if(report.runtime_source_sha256!==plan.runtime_source_sha256)throw Error('GR IV 构建源已变化，请重新预检');
  return {candidate,receipt:gr4DownloadReceipt({...report,...normalizeGr4Request(input),configuration_sha256:plan.configuration_sha256,version_unlock:{enabled:false}})};
 }finally{building=false;}
}
