import {MAX_NATIVE_RTOS_GROWTH} from './gr3-native-budget.mjs';
import {createHash} from 'node:crypto';
import {inspectFirmwareImport} from './firmware.mjs';
import {decodeFrameMap,sum32} from './gr3-frames.mjs';
import {auditGr3Candidate} from './gr3-candidate-audit.mjs';
import {officialResources} from './gr3-stock-presets.mjs';
const hash=b=>createHash('sha256').update(b).digest('hex');
const need=(v,m)=>{if(!v)throw new Error(m);};
function sectionMap(decoded,rows){
 let offset=0;const map={};
 for(const row of rows){
  need(decoded.toString('ascii',offset,offset+8).split('\0')[0]===row.name,'候选分区次序不符');
  const size=row.name==='RTOS'?decoded.readUInt32LE(offset+12):row.size-16;
  need(size>0&&offset+16+size<=decoded.length-4,'候选分区越界');
  map[row.name]={offset:offset+16,size};offset+=16+size;
 }
 need(offset+4===decoded.length,'候选分区尾部不符');return map;
}
function pack(base,target){
 const size=base.readUInt32LE(base.length-8),{decoded,frames}=decodeFrameMap(base,size),chunks=[];
 for(const frame of frames){
  const bytes=target.subarray(frame.decoded_start,frame.decoded_end);
  const historyStart=Math.max(0,frame.decoded_start-8191);
  if(target.subarray(historyStart,frame.decoded_end).equals(decoded.subarray(historyStart,frame.decoded_end)))chunks.push(base.subarray(128+frame.encoded_start,128+frame.encoded_end));
  else for(let at=0;at<bytes.length;at+=0x6000){const part=bytes.subarray(at,at+0x6000),prefix=Buffer.alloc(2);prefix.writeUInt16BE(0x8000|part.length);chunks.push(prefix,part);}
 }
 chunks.push(Buffer.alloc(2));const payload=Buffer.concat(chunks),footer=Buffer.from(base.subarray(-24));
 footer.writeUInt32LE(payload.length,12);footer.writeUInt32LE(0,20);
 const out=Buffer.concat([base.subarray(0,128),payload,Buffer.alloc(-(128+payload.length)&3),footer]);
 out.writeUInt32LE(-sum32(out)>>>0,out.length-4);return out;
}
export function applyPatchPlan(official,base,edits){
 const report=inspectFirmwareImport(official),source=officialResources(official);
 if(!base.equals(official))auditGr3Candidate(official,base,{maxRtosGrowth:MAX_NATIVE_RTOS_GROWTH});
 const size=base.readUInt32LE(base.length-8),{decoded}=decodeFrameMap(base,size);
 const map=sectionMap(decoded,report.sections),target=Buffer.from(decoded),spans=[];
 for(const row of report.sections){
   const current=map[row.name].offset-16,old=source.sections[row.name].offset-16;
   need(decoded.readUInt32LE(current+8)===source.decoded.readUInt32LE(old+8),'分区更新类型不符');
   if(row.name!=='RTOS')need(decoded.readUInt32LE(current+12)===source.decoded.readUInt32LE(old+12),'分区长度字段不符');
 }
 for(const edit of edits){
  need(['RTOS','ICONBIN'].includes(edit.section),'不允许修改该分区');
  need(Number.isSafeInteger(edit.offset)&&edit.offset>=0&&
    typeof edit.expectedHex==='string'&&typeof edit.replacementHex==='string'&&
    /^[0-9a-f]+$/.test(edit.expectedHex)&&/^[0-9a-f]+$/.test(edit.replacementHex)&&
    edit.expectedHex.length%2===0&&edit.expectedHex.length===edit.replacementHex.length,'补丁结构无效');
  const before=Buffer.from(edit.expectedHex,'hex'),after=Buffer.from(edit.replacementHex,'hex');
  const section=map[edit.section],original=source.sections[edit.section],end=edit.offset+before.length;
  need(end<=original.size&&end<=section.size,'补丁范围越界');
  need(edit.section!=='RTOS'||![[0x620000,0x640000],[0x820000,0x840000],[0x2038,0x203c]].some(([a,b])=>edit.offset<b&&end>a),'更新器或版本保护范围不可修改');
  need(!spans.some(e=>e.section===edit.section&&edit.offset<e.end&&e.offset<end),'补丁范围重叠');
  need(source.decoded.subarray(original.offset+edit.offset,original.offset+end).equals(before)&&
    decoded.subarray(section.offset+edit.offset,section.offset+end).equals(before),'补丁前像与已有功能冲突');
  spans.push({...edit,end});after.copy(target,section.offset+edit.offset);
 }
 target.writeUInt32LE(0,target.length-4);target.writeUInt32LE(-sum32(target)>>>0,target.length-4);
 const candidate=pack(base,target),fresh=decodeFrameMap(candidate,size).decoded;
 need(sum32(candidate)===0&&sum32(fresh)===0&&fresh.equals(target),'独立回读与补丁计划不一致');
 for(const [a,b] of [[0x620000,0x640000],[0x820000,0x840000],[0x2038,0x203c]])
   need(fresh.subarray(map.RTOS.offset+a,map.RTOS.offset+b).equals(source.decoded.subarray(source.sections.RTOS.offset+a,source.sections.RTOS.offset+b)),'更新器或版本保护字节变化');
 // Compare every gap against base, including other sections and their headers.
 const ranges=spans.map(e=>[map[e.section].offset+e.offset,map[e.section].offset+e.end]).sort((a,b)=>a[0]-b[0]);
 let at=0;for(const [a,b] of [...ranges,[fresh.length-4,fresh.length]]){
  need(fresh.subarray(at,a).equals(decoded.subarray(at,a)),'非目标字节改变');at=b;
 }
 const changedSections=report.sections.filter(row=>{
  const a=map[row.name],b=source.sections[row.name];
  return a.size!==b.size||!fresh.subarray(a.offset,a.offset+a.size).equals(source.decoded.subarray(b.offset,b.offset+b.size));
 }).map(row=>row.name);
 return {candidate,audit:{sourceSha256:report.sha256,baseCandidateSha256:hash(base),candidateSha256:hash(candidate),
   changedSections,rtosGrowth:map.RTOS.size-source.sections.RTOS.size,patchCount:edits.length,
   affectedLanguages:[...new Set(edits.flatMap(e=>e.affectedLanguages||[]))],cameraTested:false}};
}
