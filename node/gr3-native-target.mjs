// Apply a typed, audited runtime delta to a separately identified target.
// The reference is a compiler/audit input; stock bytes always come from upload.
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {inspectFirmwareImport} from './firmware.mjs';
import {decodeFrameMap,sum32} from './gr3-frames.mjs';
import {stockResourceLayout,officialResources} from './gr3-stock-presets.mjs';
import {auditGr3Candidate} from './gr3-candidate-audit.mjs';
import {MAX_NATIVE_RTOS_GROWTH} from './gr3-native-budget.mjs';

const profile=JSON.parse(readFileSync(new URL('./gr3-220-native-target.json',import.meta.url)));
const LOAD=0x53000000,sha=b=>createHash('sha256').update(b).digest('hex');
const need=(value,message)=>{if(!value)throw Error('原生目标重定位：'+message);};
const repair=b=>{b.writeUInt32LE(0,b.length-4);b.writeUInt32LE(-sum32(b)>>>0,b.length-4);};
const imm=w=>((w>>>4)&0xf000)|(w&0xfff);
const move=(w,v)=>((w&~0x000f0fff)|((v&0xf000)<<4)|(v&0xfff))>>>0;
const branchTarget=(site,w)=>site+8+((w<<8)>>6);
function branch(site,target,word){
 const d=target-site-8;need(!(d&3)&&d>=-0x2000000&&d<0x2000000,'分支超出范围');
 return ((word&0xff000000)|((d>>2)&0xffffff))>>>0;
}
function mapAddress(address){
 const value=profile.addresses['0x'+address.toString(16)];
 need(typeof value==='string','缺少地址证明 0x'+address.toString(16));return Number(value);
}
export function nativeTargetReport(source){
 if(sha(source)!==profile.source_sha256)return null;
 const report=inspectFirmwareImport(source);
 need(report.model===profile.model&&report.public_version===profile.public_version,'输入机型或版本不符');
 return {...report,native_target:'gr3-2.20'};
}
function parts(container,rows,original=false){
 const {decoded,frames}=original?officialResources(container):decodeFrameMap(container),sections={};let at=0;
 for(const row of rows){
  const n=row.name==='RTOS'?decoded.readUInt32LE(at+12)+16:row.size;
  need(decoded.toString('ascii',at,at+8).split('\0')[0]===row.name&&at+n<=decoded.length-4,'分区布局不符');
  sections[row.name]={offset:at+16,size:n-16,bytes:decoded.subarray(at+16,at+n)};at+=n;
 }
 need(at+4===decoded.length,'分区尾部不符');return {decoded,frames,sections};
}
function checkProfile(reference,source){
 need(sha(reference)===profile.reference_sha256&&sha(source)===profile.source_sha256,'来源身份不符');
 const old=inspectFirmwareImport(reference),target=inspectFirmwareImport(source);
 const a=parts(reference,old.sections,true),b=parts(source,target.sections,true);
 need(a.sections.RTOS.size===profile.reference_rtos_bytes&&b.sections.RTOS.size===profile.target_rtos_bytes,'RTOS 大小不符');
 for(const [key,p] of [['reference',a],['target',b]])
  need(profile.startup[key].every((v,i)=>p.sections.RTOS.bytes.readUInt32LE(0x450+i*4)===v),'启动复制与 BSS 边界不符');
 // Prove the non-content-addressable globals through their owning getters
 // and member accesses. Zero-filled BSS similarity is never a witness.
 const pair=(raw,at)=>{
  const low=raw.readUInt32LE(at-LOAD),high=raw.readUInt32LE(at+4-LOAD);
  need((low&0x0ff00000)===0x03000000&&(high&0x0ff00000)===0x03400000&&
   (low&0xf000)===(high&0xf000),'全局对象的 MOVW/MOVT 类型不符');
  return (imm(low)|(imm(high)<<16))>>>0;
 };
 for(const [getter,global] of [[0x5320b31c,0x55063ed0],[0x5320b19c,0x55064398]]){
  need(pair(a.sections.RTOS.bytes,getter+8)===global&&
   pair(b.sections.RTOS.bytes,mapAddress(getter)+8)===mapAddress(global),'原厂对象 guard 归属不同');
 }
 need(pair(a.sections.RTOS.bytes,0x5320ba9c+0x20)===0x55068200&&
  pair(b.sections.RTOS.bytes,mapAddress(0x5320ba9c)+0x20)===mapAddress(0x55068200)&&
  mapAddress(0x55068200)+0x1f===mapAddress(0x5506821f),'影像控制调试字节的对象归属不同');
 need(pair(a.sections.RTOS.bytes,0x535157b4+0x20)===0x55344d7c&&
  pair(b.sections.RTOS.bytes,mapAddress(0x535157b4)+0x20)===mapAddress(0x55344d7c)&&
  mapAddress(0x55344d7c)+0x5ac===mapAddress(0x55345328),'ShootingInfo 池单例归属不同');
 for(const [address,expected] of [[0x53515620,0xe58425ac],[0x5351581c,0xe58015ac],[0x53515820,0xe58010b8],[0x5352051c,0xe59005ac]]){
  const mapped=address===0x53515820?mapAddress(0x5351581c)+4:mapAddress(address);
  need(a.sections.RTOS.bytes.readUInt32LE(address-LOAD)===expected&&
   b.sections.RTOS.bytes.readUInt32LE(mapped-LOAD)===expected,'ShootingInfo 池成员 ABI 不同');
 }
 need(branchTarget(0x53520520,a.sections.RTOS.bytes.readUInt32LE(0x53520520-LOAD))===0x53523a20&&
  branchTarget(mapAddress(0x5352051c)+4,b.sections.RTOS.bytes.readUInt32LE(mapAddress(0x5352051c)+4-LOAD))===mapAddress(0x53523a20)&&
  branchTarget(mapAddress(0x53523a20),b.sections.RTOS.bytes.readUInt32LE(mapAddress(0x53523a20)-LOAD))===mapAddress(0x53523980),'ShootingInfo 池构造调用链不同');
 return {old,target,a,b};
}
function relocateRuntime(raw,records,base,icons,source,reference){
 need(Array.isArray(records)&&records.length>100,'缺少有类型的运行体引用');
 const output=Buffer.from(raw),used=new Set(),directory=icons.table;
 for(const row of records){
  need(['branch','pointer','mov_pair'].includes(row.kind)&&row.sites.length===row.words.length&&
   row.sites.length===(row.kind==='mov_pair'?2:1),'引用类型不符');
  for(let i=0;i<row.sites.length;i++){
   const site=row.sites[i];need(Number.isSafeInteger(site)&&!(site&3)&&site>=base&&site+4<=base+raw.length,'引用越界');
   need(raw.readUInt32LE(site-base)===row.words[i]&&!used.has(site),'引用前像不符或重叠');used.add(site);
  }
  // The factory icon pointers have a typed index contract. Copy their target
  // directory rather than guessing between repeated blank icon descriptors.
  if(row.sites[0]>=directory&&row.sites[0]<directory+671*4){
   need(row.kind==='pointer','原厂图标目录引用类型不符');continue;
  }
  const to=mapAddress(row.target);
  if(row.kind==='branch'){
   const w=row.words[0],site=row.sites[0];
   need((w&0x0e000000)===0x0a000000&&(w>>>28)!==15&&branchTarget(site,w)===row.target,'分支引用不符');
   output.writeUInt32LE(branch(site,to,w),site-base);
  }else if(row.kind==='pointer'){
   need(row.words[0]===row.target,'指针引用不符');output.writeUInt32LE(to,row.sites[0]-base);
  }else{
   const [low,high]=row.words;
   need((low&0x0ff00000)===0x03000000&&(high&0x0ff00000)===0x03400000&&
    (low&0xf000)===(high&0xf000)&&((imm(low)|(imm(high)<<16))>>>0)===row.target,'MOVW/MOVT 引用不符');
   output.writeUInt32LE(move(low,to&65535),row.sites[0]-base);
   output.writeUInt32LE(move(high,to>>>16),row.sites[1]-base);
  }
 }
 const oldLayout=stockResourceLayout(reference),layout=stockResourceLayout(source);
 need(oldLayout.iconCount===671&&layout.iconCount===671,'原厂图标索引合同不符');
 const report=inspectFirmwareImport(source),p=parts(source,report.sections,true),rtos=p.sections.RTOS.bytes;
 const dataSource=rtos.readUInt32LE(0x450),destination=rtos.readUInt32LE(0x454);
 const at=dataSource-LOAD+layout.iconDirectory-destination;
 need(directory>=base&&directory+671*4<=base+raw.length,'运行体图标目录越界');
 rtos.copy(output,directory-base,at,at+671*4);
 return output;
}
function encode(source,original,target,insertion,growth){
 const chunks=[];
 for(const f of original.frames){
  const start=f.decoded_start+(f.decoded_start>insertion?growth:0),end=f.decoded_end+(f.decoded_end>insertion?growth:0);
  const bytes=target.subarray(start,end),history=Math.min(8191,f.decoded_start);
  if(bytes.equals(original.decoded.subarray(f.decoded_start,f.decoded_end))&&
   target.subarray(start-history,start).equals(original.decoded.subarray(f.decoded_start-history,f.decoded_start)))
   chunks.push(source.subarray(128+f.encoded_start,128+f.encoded_end));
  else for(let off=0;off<bytes.length;off+=0x6000){const p=bytes.subarray(off,off+0x6000),h=Buffer.alloc(2);h.writeUInt16BE(0x8000|p.length);chunks.push(h,p);}
 }
 chunks.push(Buffer.alloc(2));const payload=Buffer.concat(chunks),footer=Buffer.from(source.subarray(-24));
 footer.writeUInt32LE(payload.length,12);footer.writeUInt32LE(target.length,16);footer.writeUInt32LE(0,20);
 const out=Buffer.concat([source.subarray(0,128),payload,Buffer.alloc(-(128+payload.length)&3),footer]);repair(out);return out;
}
export function portNativeTarget(reference,source,referenceCandidate,records,manifest){
 const {old,target,a,b}=checkProfile(reference,source);
 auditGr3Candidate(reference,referenceCandidate,{maxRtosGrowth:MAX_NATIVE_RTOS_GROWTH});
 const built=parts(referenceCandidate,old.sections),raw=built.sections.RTOS.bytes,base=manifest.base;
 need(base>=LOAD+b.sections.RTOS.size&&base<=LOAD+a.sections.RTOS.size+0x1000,'运行体放置不符');
 need(manifest.target_relocations?.schema===1&&manifest.target_relocations.count===records.length&&
  manifest.target_relocations.sha256===sha(JSON.stringify(records))&&
  manifest.target_relocations.runtime_sha256===sha(raw.subarray(base-LOAD)),'运行体引用清单缺失、截断或与构建不同');
 const runtime=relocateRuntime(raw.subarray(base-LOAD),records,base,manifest.icons,source,reference);
 if(manifest.hdf_adj){
  const table=manifest.hdf_adj.table,stockTable=mapAddress(manifest.hdf_adj.original_table),bytes=manifest.hdf_adj.original_table_bytes;
  need(bytes===20*68&&table>=base&&table+bytes<=base+runtime.length&&
   runtime.subarray(table-base,table-base+bytes).equals(b.sections.RTOS.bytes.subarray(stockTable-LOAD,stockTable-LOAD+bytes)),
   'ADJ 原厂记录及字段布局不同');
 }
 const stock=b.sections.RTOS.bytes,table=stock.readUInt32LE(0x434)-LOAD,domains=stock.readUInt32LE(0x438);
 need(table>=0&&table+16384<=stock.length,'目标 MMU 表越界');
 for(let address=base;address<base+runtime.length;address=(address&0xfff00000)+0x100000){
  const descriptor=stock.readUInt32LE(table+(address>>>20)*4),domain=(descriptor>>>5)&15;
  need((descriptor&3)===2&&!(descriptor&16)&&((descriptor>>>10)&3)===2&&(descriptor&(1<<15))&&
   ((domains>>>(domain*2))&3)===1&&(descriptor>>>20)===(address>>>20),'目标完整运行体 MMU/RX 映射不符');
 }
 const output=Buffer.concat([b.decoded.subarray(0,b.sections.RTOS.offset),
  b.sections.RTOS.bytes,Buffer.alloc(base-LOAD-b.sections.RTOS.size),runtime,
  b.decoded.subarray(b.sections.RTOS.offset+b.sections.RTOS.size)]);
 const growth=base-LOAD+runtime.length-b.sections.RTOS.size,insertion=b.sections.RTOS.offset+b.sections.RTOS.size;
 need(growth>0&&output.length<=128*1024*1024,'运行体长度超出封包边界');
 output.writeUInt32LE(b.sections.RTOS.size+growth,b.sections.RTOS.offset-4);
 const patches=[];
 for(let off=0;off<a.sections.RTOS.size;off+=4){
  const before=a.sections.RTOS.bytes.readUInt32LE(off),word=raw.readUInt32LE(off);if(before===word)continue;
  const site=LOAD+off,to=mapAddress(site);let replacement=word;
  need(to>=LOAD&&to+4<=LOAD+b.sections.RTOS.size,'原厂补丁地址越界');
  need(!patches.some(p=>p.target===to),'原厂补丁地址重叠');
  if((word&0x0e000000)===0x0a000000&&(word>>>28)!==15){
   const destination=branchTarget(site,word);
   replacement=branch(to,destination>=base?destination:mapAddress(destination),word);
  }else if(word>=LOAD&&word<LOAD+a.sections.RTOS.size)replacement=mapAddress(word);
  output.writeUInt32LE(replacement,b.sections.RTOS.offset+to-LOAD);
  patches.push({reference:site,target:to,expected:b.sections.RTOS.bytes.readUInt32LE(to-LOAD),replacement});
 }
 repair(output);const candidate=encode(source,b,output,insertion,growth),fresh=parts(candidate,target.sections);
 need(fresh.decoded.equals(output),'独立封包回读不同');
 for(const [name,row] of Object.entries(b.sections))if(name!=='RTOS')
  need(fresh.sections[name].bytes.equals(row.bytes),'非目标分区被修改 '+name);
 // Independently compare every gap against the uploaded RTOS, including the
 // updated manufacturer's shutdown behavior, startup copies and version word.
 let cursor=0;for(const p of [...patches].sort((x,y)=>x.target-y.target)){
  const end=p.target-LOAD;
  need(fresh.sections.RTOS.bytes.subarray(cursor,end).equals(b.sections.RTOS.bytes.subarray(cursor,end)),'非补丁 RTOS 字节被修改');cursor=end+4;
 }
 need(fresh.sections.RTOS.bytes.subarray(cursor,b.sections.RTOS.size).equals(b.sections.RTOS.bytes.subarray(cursor)),'原厂 RTOS 尾部被修改');
 const final=inspectFirmwareImport(candidate);
 need(final.internal_version===target.internal_version&&candidate.subarray(0,128).equals(source.subarray(0,128)),'上传版本或容器身份被修改');
 return {candidate,runtime,receipt:{schema:profile.schema,verified:true,source_sha256:target.sha256,reference_source_sha256:old.sha256,
  candidate_sha256:sha(candidate),rtos_growth:growth,relocated_references:records.length,patches,
  runtime_sha256:sha(runtime),runtime_base:base,runtime_bytes:runtime.length,
  component_versions_preserved:true,unrelated_sections_preserved:true,uploaded_rtos_gaps_preserved:true,camera_tested:false}};
}
