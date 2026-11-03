import {createHash} from 'node:crypto';
import {inspectOfficial,inspectFirmwareImport} from './firmware.mjs';
import {requireReleaseBaseline} from './firmware-release-policy.mjs';
import {checkCameraForInstall} from '../web/gr3/firmware-install-guide.mjs';
import {inspectBackup,restoreBytes} from './backup.mjs';

const hash=b=>createHash('sha256').update(b).digest('hex'),issued=new WeakMap();
function need(ok,message){if(!ok){const e=new Error('固件安全校验未通过：'+message);e.code='M10V_FIRMWARE_CHECK_FAILED';throw e;}}
const alive=signal=>signal?.throwIfAborted();
export function checkWebBuild(source,camera,options={}){
 let report;try{report=inspectOfficial(requireReleaseBaseline(source));}catch{need(false,'仅允许精确官方 GR III 2.10 / IIIx 1.60 来源。');}
 need(!options.version_unlock?.enabled,'版本适配和抬版本不允许生成。');
 const checked=checkCameraForInstall(report,camera,{requireProvenance:true});
 need(checked.ready,checked.message);return report;
}
function issue(source,candidate,configurationSha256,filename,artifactKind){
 const report=Object.freeze({schema:'m10v-web-firmware-safety/v1',status:'offline_verified_camera_unverified',
  artifact_kind:artifactKind,download_allowed:true,installation_allowed:false,camera_tested:false,
  model:source.model==='GR IIIx'?'gr3x':'gr3',public_version:source.public_version,
  source_sha256:source.sha256,configuration_sha256:configurationSha256,
  candidate_sha256:hash(candidate),candidate_bytes:candidate.length,filename,
  checks:Object.freeze({pinned_source:true,camera_declaration:true,strict_decode:true,receipt_binding:true,exact_rebuild:true})});
 issued.set(report,{digest:report.candidate_sha256,bytes:candidate.length});return report;
}
export async function verifyWebFirmware({source,candidate,receipt,configurationSha256,camera,filename,rebuild,signal}){
 alive(signal);const original=checkWebBuild(source,camera);
 need(Buffer.isBuffer(candidate),'最终 BIN 不存在。');
 const report=inspectFirmwareImport(candidate);
 need(report.model===original.model&&report.internal_version===original.internal_version,'机型或组件版本与官方基线不同。');
 need(filename===(original.model==='GR IIIx'?'fwdc243b.bin':'fwdc239b.bin'),'固件文件名与机型不符。');
 need(/^[a-f0-9]{64}$/.test(configurationSha256||''),'配置指纹不存在。');
 need(receipt?.source_sha256===original.sha256&&receipt?.candidate_sha256===hash(candidate)&&
  receipt?.candidate_bytes===candidate.length&&receipt?.configuration_sha256===configurationSha256,'最终 BIN、来源、配置与构建回执不符。');
 need(typeof rebuild==='function','缺少独立重建检查。');
 alive(signal);const repeated=await rebuild();alive(signal);
 const bytes=Buffer.isBuffer(repeated)?repeated:repeated?.candidate;
 need(Buffer.isBuffer(bytes)&&bytes.equals(candidate),'完整重建结果与待下载 BIN 不一致，已拦截下载。');
 return issue(original,candidate,configurationSha256,filename,'firmware');
}
export function verifyWebBackup({source,candidate,camera}){
 const original=checkWebBuild(source,camera),checked=inspectBackup(candidate);
 need(checked.original_sha256===original.sha256&&restoreBytes(candidate).equals(source),'备份内的官方原件不同。');
 return issue(original,candidate,original.sha256,'m10v-gr3-backup.zip','official_backup');
}
export function requireWebDownload(candidate,audit){
 const proof=issued.get(audit);
 need(proof&&Buffer.isBuffer(candidate)&&proof.bytes===candidate.length&&proof.digest===hash(candidate),'下载缺少本次校验记录，或校验后文件字节已变化。');
 return audit;
}
// Only the dedicated server worker channel calls this, never request JSON.
// Rebind its already reconstructed result to parent-owned source/config/bytes.
export function acceptVerifiedWorkerResult(source,camera,result,configurationSha256){
 const original=checkWebBuild(source,camera),a=result?.audit,b=result?.candidate;
 need(a?.schema==='m10v-web-firmware-safety/v1'&&a.status==='offline_verified_camera_unverified'&&
  a.download_allowed===true&&a.installation_allowed===false&&a.camera_tested===false&&
  ['pinned_source','camera_declaration','strict_decode','receipt_binding','exact_rebuild'].every(k=>a.checks?.[k]===true),'执行线程没有完成完整校验。');
 need(Buffer.isBuffer(b)&&a.source_sha256===original.sha256&&a.configuration_sha256===configurationSha256&&
  a.candidate_sha256===hash(b)&&a.candidate_bytes===b.length&&a.filename===result.filename,'执行线程结果与本次来源、配置或字节不符。');
 const decoded=inspectFirmwareImport(b);
 need(decoded.model===original.model&&decoded.internal_version===original.internal_version,'执行线程返回了不同机型或版本。');
 need(result.filename===(original.model==='GR IIIx'?'fwdc243b.bin':'fwdc239b.bin'),'执行线程返回的文件名不符。');
 return {...result,audit:issue(original,b,configurationSha256,result.filename,'firmware')};
}
