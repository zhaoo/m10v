// Queue jobs cover both complete builds. No unverified result leaves this module.
import {createHash} from 'node:crypto';
import {resolveBuildSource} from './firmware-build-source.mjs';
import {requireReleaseBaseline} from './firmware-release-policy.mjs';
import {prepareNative,generateNative} from './gr3-native-library.mjs';
import {resolveIspEffectOptions} from './gr3-isp-effect-options.mjs';
import {bindPowerPreparation,applyPowerImages} from './gr3-power-images.mjs';
import {prepareCustomization,buildCustomization} from './gr3-customization.mjs';
import {prepare800T,build800T} from './gr3-800t-build.mjs';
import {buildStreetCandidate} from './candidate.mjs';
import {checkWebBuild,verifyWebFirmware} from './firmware-web-safety.mjs';
const sha=b=>createHash('sha256').update(b).digest('hex');
const encoded=x=>Buffer.from(JSON.stringify(x)).toString('base64');
export async function readCheckedProject(store,id){
 const resolved=await resolveBuildSource(requireReleaseBaseline(await store.readOriginal(id)));
 if(resolved.report.sha256!==id)throw Error('项目与实际官方固件来源不匹配。');
 return resolved;
}
export function prepareCheckedNative(source,input){
 requireReleaseBaseline(source);
 if(input.version_unlock?.enabled)throw Error('网页安全校验禁止抬高版本，请关闭版本适配。');
 const model=source.readUInt32LE(0x30)===609?'GR IIIx':'GR III';
 const options=resolveIspEffectOptions(source,input,model);
 const base=prepareNative(source,input.configuration,options);
 return {options,base,plan:bindPowerPreparation(base,source,input.power_images)};
}
export function checkedFirmwareJob(store,id,input,kind='native'){
 // Capture small request data, not a 30 MiB original for every queued job.
 const request=structuredClone(input);
 return async({signal,setPhase})=>{
  signal=AbortSignal.any([signal,AbortSignal.timeout(5*60*1000)]);
  signal.throwIfAborted();
  const {source,report}=await readCheckedProject(store,id);
  checkWebBuild(source,request.camera,request);
  let once,plan,header;
  if(kind==='native'){
   const checked=prepareCheckedNative(source,request);plan=checked.plan;header='X-M10V-Native-Receipt';
   once=async()=>{
    const native=await generateNative(source,request.configuration,checked.base.configuration_sha256,{...checked.options,signal});
    signal.throwIfAborted();
    const power=applyPowerImages(source,native.candidate,request.power_images),candidate=power.candidate;
    const receipt={...native.receipt,build_source:report.build_source,
     ...(checked.plan.power_images?{power_images:power.receipt,configuration_sha256:plan.configuration_sha256,
      candidate_sha256:sha(candidate),candidate_bytes:candidate.length}:{})};
    return {candidate,receipt};
   };
  }else if(kind==='edit'){
   plan=await prepareCustomization(source,request.selection,{signal});header='X-M10V-Build-Receipt';
   once=()=>buildCustomization(source,request.selection,plan.configuration_sha256,{signal});
  }else if(kind==='800t'){
   plan=prepare800T(source,request.selection);header='X-M10V-800T-Receipt';
   once=()=>build800T(source,request.selection,plan.configuration_sha256);
  }else if(kind==='shutdown'){
   const jpeg=Buffer.from(request.jpeg),configuration_sha256=sha(Buffer.concat([Buffer.from(id),jpeg]));
   plan={ready:true,configuration_sha256,filename:'fwdc239b.bin'};header='X-M10V-Build-Receipt';
   once=()=>{const result=buildStreetCandidate(source,jpeg);return {candidate:result.candidate,receipt:{...result.report,configuration_sha256}};};
  }else throw Error('未知构建类型。');
  if(!plan.ready||request.accepted_configuration_sha256!==plan.configuration_sha256)
   throw Error('方案已变化或预检未通过，请重新核验。');
  setPhase('generating');const result=await once();signal.throwIfAborted();
  const receipt={...result.receipt,build_source:report.build_source};
  const auditReceipt={...receipt,candidate_bytes:receipt.candidate_bytes??result.candidate.length};
  setPhase('verifying');
  const audit=await verifyWebFirmware({source,candidate:result.candidate,receipt:auditReceipt,
   configurationSha256:plan.configuration_sha256,camera:request.camera,filename:plan.filename,
   rebuild:async()=>(await once()).candidate,signal});
  const completeReceipt={...receipt,safety:audit};
  return {candidate:result.candidate,filename:plan.filename,audit,
   headers:{[header]:encoded(completeReceipt),'X-M10V-Build-Source':encoded(report.build_source)}};
 };
}
