import {MAX_NATIVE_RTOS_GROWTH} from './gr3-native-budget.mjs';
// Opt-in version metadata adaptation AFTER the native/composition audit.
// This is a second, differential audit; it does not replace that first audit.
import {createHash} from 'node:crypto';
import {decodeFrameMap,sum32} from './gr3-frames.mjs';

const profiles={gr3:{project:588,magic:0x024c024c,baseline:0x020a151b,ceiling:0x020affff,line:0x020a,label:'2.10'},gr3x:{project:609,magic:0x02610261,baseline:0x013c0b11,ceiling:0x013cffff,line:0x013c,label:'1.60'}};
const MAX_BYTES=128*1024*1024,RTOS_BYTES=17520064;
const rows=[['BOOTPARA',72,0xffff0005],['DRAMPARA',556,0xffff0001],
 ['PARTPARA',516,0xffff0002],['M0',44640,3],['BOOT',21816,4],
 ['RTOS',RTOS_BYTES,0x10004],['LINUX',3062784,0x50004],['INITFS',13899776,0x60004],
 ['SRIC',49152,0x20004],['CPU',131072,7],['SHELLCMD',37440,0x30004],
 ['ICONBIN',18354964,0x40004],['FDRVPARA',36,0xffff0008],['RES',6595272,0xffff0006]];
const need=(ok,message)=>{if(!ok)throw Error('version unlock: '+message);};
const hash=b=>createHash('sha256').update(b).digest('hex');
const text=word=>[word>>>24,(word>>>16)&255,(word>>>8)&255,word&255].join('.');
function word(value){
 need(typeof value==='string'&&/^\d{1,3}(\.\d{1,3}){3}$/.test(value),'完整 DSP/CPU 版本必须为四段十进制数字');
 const parts=value.split('.').map(Number);need(parts.every(v=>v<=255),'版本每段必须在 0–255 范围内');
 return parts.reduce((v,n)=>v*256+n,0);
}
export function normalizeVersionUnlock(input,model='gr3'){
 need(Object.hasOwn(profiles,model),'机型无效');const profile=profiles[model];
 if(input===undefined)return {enabled:false};
 need(input&&typeof input==='object'&&!Array.isArray(input)&&
  Object.keys(input).every(k=>['enabled','mode','dsp','cpu'].includes(k)),'配置字段无效');
 need(typeof input.enabled==='boolean','enabled 必须为布尔值');
 if(!input.enabled)return {enabled:false};
 if(input.mode==='dsp-package-only'){
  need(!Object.hasOwn(input,'dsp')&&!Object.hasOwn(input,'cpu'),'DSP 包版本模式不接受机身版本读数');
  return {enabled:true,mode:'dsp-package-only'};
 }
 need(input.mode===undefined||input.mode==='observed-versions','版本适配模式无效');
 const dsp=word(input.dsp),cpu=word(input.cpu);
 need((dsp>>>16)===profile.line&&(cpu>>>16)===profile.line,`仅支持同一 ${profile.label} 公共版本线的 DSP/CPU 完整版本`);
 return {...(input.mode?{enabled:true,mode:input.mode}:{enabled:true}),dsp:text(dsp),cpu:text(cpu)};
}
function targets(input,profile){return input.mode==='dsp-package-only'?{dsp:profile.ceiling,cpu:profile.baseline}:
 {dsp:Math.max(profile.baseline,word(input.dsp)),cpu:Math.max(profile.baseline,word(input.cpu))};}
function cpuSum(decoded,start){let n=0;for(let at=start;at<start+131072;at+=4)n=(n+decoded.readUInt32BE(at))>>>0;return n;}
function read(bytes){
 need(Buffer.isBuffer(bytes)&&bytes.length>=152&&bytes.length<MAX_BYTES&&!(bytes.length&3),'候选容器大小无效');
 const tail=bytes.length-24,encoded=bytes.readUInt32LE(tail+12),size=bytes.readUInt32LE(tail+16);
 const model=Object.keys(profiles).find(k=>bytes.readUInt32LE(0x30)===profiles[k].project&&bytes.readUInt32LE(0x78)===profiles[k].magic);
 need(model,'机型/标记无效');const profile=profiles[model];
 need(
  bytes.readUInt32LE(0x7c)===0xa55a5aa5&&bytes.readUInt32LE(tail)===profile.magic&&
  bytes.readUInt32LE(tail+4)===0xa55a5aa5&&bytes.readUInt32LE(tail+8)===2,'公共基线候选机型/标记无效');
 need(size>=59718388&&size<=59718388+MAX_NATIVE_RTOS_GROWTH&&!(size&3)&&
  ((128+encoded+3)&~3)===tail&&bytes.subarray(128+encoded,tail).every(v=>v===0),'容器布局无效');
 need(sum32(bytes)===0,'容器 checksum 无效');
 const {decoded,frames}=decodeFrameMap(bytes,size);need(sum32(decoded)===0,'decoded checksum 无效');
 let at=0;const sections={};
 for(const [name,fixed,flags] of rows){
  need(at+16<=decoded.length-4,'分区头越界');
  need(decoded.toString('ascii',at,at+8).split('\0')[0]===name&&decoded.readUInt32LE(at+8)===flags,'分区次序/类型无效');
  const field=decoded.readUInt32LE(at+12),length=name==='RTOS'?field:fixed;
  need((name==='RTOS'?length>=RTOS_BYTES&&length<=RTOS_BYTES+MAX_NATIVE_RTOS_GROWTH&&!(length&3):field===(name==='RES'?35:fixed))&&
   at+16+length<=decoded.length-4,'分区长度无效');
  sections[name]={offset:at+16,size:length};at+=16+length;
 }
 need(at+4===decoded.length,'分区尾部无效');
 const cpu=sections.CPU.offset;
 need(decoded.readUInt32LE(cpu+0x80)===profile.project,'CPU 项目编号无效');
 need(decoded.readUInt32BE(cpu+0x7c)!==0xffffffff&&cpuSum(decoded,cpu)===0,'CPU checksum 无效');
 return {decoded,frames,sections,tail,model,profile};
}
function versions(bytes,r){return {outer_dsp:bytes.readUInt32BE(0x38),outer_cpu:bytes.readUInt32BE(0x50),
 rtos:r.decoded.readUInt32BE(r.sections.RTOS.offset+0x2038),cpu:r.decoded.readUInt32BE(r.sections.CPU.offset+0x90)};}
function baseline(bytes,r){need(Object.values(versions(bytes,r)).every(v=>v===r.profile.baseline),`输入必须是已审计且尚未解锁版本的 ${text(r.profile.baseline)} 候选`);}
function repair(bytes){bytes.writeUInt32LE(0,bytes.length-4);bytes.writeUInt32LE(-sum32(bytes)>>>0,bytes.length-4);}
function pack(before,r,target){
 const chunks=[];
 for(const f of r.frames){
  const bytes=target.subarray(f.decoded_start,f.decoded_end);
  // An unchanged compressed frame can still refer to earlier changed bytes.
  const history=Math.min(8191,f.decoded_start);
  const sameHistory=target.subarray(f.decoded_start-history,f.decoded_end).equals(r.decoded.subarray(f.decoded_start-history,f.decoded_end));
  if(sameHistory)chunks.push(before.subarray(128+f.encoded_start,128+f.encoded_end));
  else for(let at=0;at<bytes.length;at+=0x6000){const p=bytes.subarray(at,at+0x6000),h=Buffer.alloc(2);h.writeUInt16BE(0x8000|p.length);chunks.push(h,p);}
 }
 chunks.push(Buffer.alloc(2));const payload=Buffer.concat(chunks),footer=Buffer.from(before.subarray(-24));
 footer.writeUInt32LE(payload.length,12);footer.writeUInt32LE(0,20);
 const out=Buffer.concat([before.subarray(0,128),payload,Buffer.alloc(-(128+payload.length)&3),footer]);repair(out);return out;
}
function equalOutside(a,b,ranges,message){
 need(a.length===b.length,message);let cursor=0;
 for(const [start,length] of [...ranges].sort((x,y)=>x[0]-y[0])){
  need(a.subarray(cursor,start).equals(b.subarray(cursor,start)),message);cursor=start+length;
 }
 need(a.subarray(cursor).equals(b.subarray(cursor)),message);
}
export function verifyVersionUnlock(before,after,input){
 const enabled=input?.enabled;
 const source=enabled?read(before):null;
 const option=normalizeVersionUnlock(input,source?.model);
 need(Buffer.isBuffer(before)&&Buffer.isBuffer(after),'候选必须为 Buffer');
 const common={schema:'m10v-gr3-version-unlock/v1',enabled:option.enabled,
  before_sha256:hash(before),candidate_sha256:hash(after),camera_verified:false};
 if(!option.enabled){need(before.equals(after),'关闭时禁止任何修改');return {...common,status:'disabled',checks:{non_target_unchanged:true}};}
 // Freshly decode both buffers; this verifier never calls the mutating builder.
 const a=source,b=read(after);need(a.model===b.model,'候选机型改变');baseline(before,a);const goal=targets(option,a.profile);
 const dspOnly=option.mode==='dsp-package-only';
 equalOutside(before.subarray(0,128),after.subarray(0,128),dspOnly?[[0x38,4]]:[[0x38,4],[0x50,4]],'外层非版本字段发生改变');
 equalOutside(before.subarray(-24),after.subarray(-24),[[12,4],[20,4]],'容器 footer 非目标字段发生改变');
 need(JSON.stringify(a.sections)===JSON.stringify(b.sections),'分区布局发生改变');
 const allowed=[[a.sections.RTOS.offset+0x2038,4],[a.decoded.length-4,4]];
 if(!dspOnly)allowed.push([a.sections.CPU.offset+0x90,4],[a.sections.CPU.offset+0x7c,4]);
 equalOutside(a.decoded,b.decoded,allowed,'非目标 decoded 字节发生改变');
 const cpu=a.sections.CPU;
 const cpuUnchanged=a.decoded.subarray(cpu.offset,cpu.offset+cpu.size).equals(b.decoded.subarray(cpu.offset,cpu.offset+cpu.size));
 if(dspOnly)need(cpuUnchanged,'DSP 包版本模式禁止修改 CPU 载荷');
 const expected={outer_dsp:goal.dsp,outer_cpu:goal.cpu,rtos:goal.dsp,cpu:goal.cpu},actual=versions(after,b);
 need(Object.keys(expected).every(k=>actual[k]===expected[k]),'版本回读与逐组件目标不符');
 return {...common,status:'version_unlock_offline_verified',mode:dspOnly?'dsp-package-only':'observed-versions',
  strategy:dspOnly?'dsp_package_public_line_ceiling_cpu_unchanged':'match_observed_component_versions',
  current_versions:dspOnly?null:{dsp:option.dsp,cpu:option.cpu},source_versions:{dsp:text(a.profile.baseline),cpu:text(a.profile.baseline)},
  target_versions:{dsp:text(goal.dsp),cpu:text(goal.cpu)},versions:Object.fromEntries(Object.entries(actual).map(([k,v])=>[k,text(v)])),
  checks:{outer_sum32:0,decoded_sum32:0,cpu_sum32_be:0,cpu_payload_unchanged:cpuUnchanged,non_target_unchanged:true,section_layout_unchanged:true,fresh_decode:true},
  ...(dspOnly?{version_scope:`DSP 目标仅为 ${a.profile.label} 公共线包头上限，不是机身实际版本；机身 CPU 版本未知且未修改，CPU 较高时原厂仍会拒绝`}:{}),
  hardware_scope:'版本比较局部门禁的离线验证；未验证纪念版机身、服务固件组件兼容性、整条刷写流程或恢复路径',
  blockers:[...(dspOnly?['current_cpu_version_unknown_stock_gate_may_reject']:[]),
   'anniversary_camera_acceptance_unverified','service_component_compatibility_unverified','hardware_recovery_unverified']};
}
export function applyVersionUnlock(candidate,input){
 const r=input?.enabled?read(candidate):null;
 const option=normalizeVersionUnlock(input,r?.model);
 need(Buffer.isBuffer(candidate),'候选必须为 Buffer');
 if(!option.enabled){const out=Buffer.from(candidate);return {candidate:out,receipt:verifyVersionUnlock(candidate,out,option)};}
 baseline(candidate,r);const goal=targets(option,r.profile);
 if(goal.dsp===r.profile.baseline&&goal.cpu===r.profile.baseline){const out=Buffer.from(candidate);return {candidate:out,receipt:verifyVersionUnlock(candidate,out,option)};}
 const target=Buffer.from(r.decoded),cpu=r.sections.CPU.offset;
 target.writeUInt32BE(goal.dsp,r.sections.RTOS.offset+0x2038);
 if(option.mode!=='dsp-package-only'){
  target.writeUInt32BE(goal.cpu,cpu+0x90);
  target.writeUInt32BE(0,cpu+0x7c);target.writeUInt32BE(-cpuSum(target,cpu)>>>0,cpu+0x7c);
 }
 repair(target);
 const out=pack(candidate,r,target);out.writeUInt32BE(goal.dsp,0x38);
 if(option.mode!=='dsp-package-only')out.writeUInt32BE(goal.cpu,0x50);
 repair(out);
 return {candidate:out,receipt:verifyVersionUnlock(candidate,out,option)};
}

// GRMod's raised-package + recoverable-updater mechanism, independently
// applied to ABI-pinned III/IIIx builds using the uploaded component version.
// This changes package versions, not the runtime's feature baseline.
const GR3_220_IMPORT='5c53760b3b564c87239dbf7f5c94d0f6fd91accd156ec4ba672ebfd6b861793e';
const UPDATE_GATE=0x6285dc;
export function updateCompatibilityPlan(buildSource={}) {
 // Retain the original internal 2.20 call contract; all new imports carry the
 // complete version metadata and do not need a release/hash registry.
 const legacy=buildSource.imported_sha256===GR3_220_IMPORT;
 if(!buildSource.normalized&&!legacy)return null;
 const model=buildSource.model||(legacy?'GR III':null);
 const key=model==='GR III'?'gr3':model==='GR IIIx'?'gr3x':null;
 need(key&&/^[0-9a-f]{64}$/.test(buildSource.imported_sha256||''),'上传来源机型或摘要无效');
 const imported=word(buildSource.imported_internal_version||(legacy?'2.20.20.28':''));
 const current=Math.max(imported,profiles[key].baseline);
 // Prefer advancing the service byte, retaining the previous 2.20 contract.
 const next=((current>>>8)&255)<255?current+256:current+1;
 need(next<=0xffffffff,'上传版本已达到版本字段上限');
 return {package_version:text(next),runtime_baseline:profiles[key].label,
  recoverable_updater:true,camera_verified:false,model};
}
export function verifyGr3UpdateCompatibility(before,after,buildSource={}){
 need(Buffer.isBuffer(before)&&Buffer.isBuffer(after),'候选必须为 Buffer');
 const plan=updateCompatibilityPlan(buildSource);
 if(!plan){need(before.equals(after),'无版本兼容来源时禁止修改');return {enabled:false};}
 const targetVersion=word(plan.package_version);
 const a=read(before),b=read(after);need(a.model===b.model&&plan.model===(a.model==='gr3'?'GR III':'GR IIIx'),'上传来源与构建机型不一致');baseline(before,a);
 need(JSON.stringify(a.sections)===JSON.stringify(b.sections),'分区布局发生改变');
 const rtos=a.sections.RTOS.offset,cpu=a.sections.CPU.offset;
 need(a.decoded.subarray(rtos+UPDATE_GATE,rtos+UPDATE_GATE+4).equals(Buffer.from('042803e3','hex')),'更新器 preimage 不符');
 need(b.decoded.subarray(rtos+UPDATE_GATE,rtos+UPDATE_GATE+4).equals(Buffer.from('e6ffffea','hex')),'恢复更新器分支不符');
 equalOutside(before.subarray(0,128),after.subarray(0,128),[[0x38,4],[0x50,4]],'外层非版本字段发生改变');
 equalOutside(before.subarray(-24),after.subarray(-24),[[12,4],[20,4]],'footer 非目标字段发生改变');
 equalOutside(a.decoded,b.decoded,[[rtos+0x2038,4],[rtos+UPDATE_GATE,4],[cpu+0x7c,4],[cpu+0x90,4],[a.decoded.length-4,4]],'非目标 decoded 字节发生改变');
 need(Object.values(versions(after,b)).every(v=>v===targetVersion),'更新版本副本不一致');
 return {schema:'m10v-gr3-update-compatibility/v2',enabled:true,status:'offline_verified',
  strategy:'raised_components_with_recoverable_updater',package_version:plan.package_version,
  imported_sha256:buildSource.imported_sha256,before_sha256:hash(before),candidate_sha256:hash(after),candidate_bytes:after.length,
  updater_patch:{address:'0x536285dc',before:'042803e3',after:'e6ffffea',destination:'0x5362857c'},
  checks:{outer_sum32:0,decoded_sum32:0,cpu_sum32_be:0,non_target_unchanged:true,section_layout_unchanged:true,fresh_decode:true},
  runtime_baseline:plan.runtime_baseline,model:plan.model,camera_verified:false,
  limitations:['not_an_uploaded_runtime_port','physical_update_and_recovery_pending']};
}
export function applyGr3UpdateCompatibility(candidate,buildSource={}){
 const plan=updateCompatibilityPlan(buildSource);
 if(!plan)return {candidate:Buffer.from(candidate),receipt:{enabled:false}};
 const targetVersion=word(plan.package_version);
 const r=read(candidate);need(plan.model===(r.model==='gr3'?'GR III':'GR IIIx'),'上传来源与构建机型不一致');baseline(candidate,r);
 const target=Buffer.from(r.decoded),rtos=r.sections.RTOS.offset,cpu=r.sections.CPU.offset;
 need(target.subarray(rtos+UPDATE_GATE,rtos+UPDATE_GATE+4).equals(Buffer.from('042803e3','hex')),'更新器 preimage 不符');
 target.writeUInt32BE(targetVersion,rtos+0x2038);target.writeUInt32BE(targetVersion,cpu+0x90);
 Buffer.from('e6ffffea','hex').copy(target,rtos+UPDATE_GATE);
 target.writeUInt32BE(0,cpu+0x7c);target.writeUInt32BE(-cpuSum(target,cpu)>>>0,cpu+0x7c);repair(target);
 const out=pack(candidate,r,target);out.writeUInt32BE(targetVersion,0x38);out.writeUInt32BE(targetVersion,0x50);repair(out);
 return {candidate:out,receipt:verifyGr3UpdateCompatibility(candidate,out,buildSource)};
}
