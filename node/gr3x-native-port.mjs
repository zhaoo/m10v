import {MAX_NATIVE_RTOS_GROWTH} from './gr3-native-budget.mjs';
// Differential port of an already audited GR III native image onto exact GR IIIx stock.
import {createHash} from 'node:crypto';
import {inspectNativeSource as inspectOfficial} from './gr3-native-source.mjs';
import {auditGr3Candidate} from './gr3-candidate-audit.mjs';
import {decodeFrameMap,sum32} from './gr3-frames.mjs';
const MAX=128*1024*1024,need=(v,m)=>{if(!v)throw Error('GR IIIx native port: '+m);};
const sha=b=>createHash('sha256').update(b).digest('hex');
const repair=b=>{b.writeUInt32LE(0,b.length-4);b.writeUInt32LE(-sum32(b)>>>0,b.length-4);};
function read(bytes,layout){
 need(Buffer.isBuffer(bytes)&&bytes.length>=152&&bytes.length<MAX&&!(bytes.length&3),'invalid container size');
 const tail=bytes.length-24,n=bytes.readUInt32LE(tail+12),size=bytes.readUInt32LE(tail+16);
 need(((128+n+3)&~3)===tail&&bytes.subarray(128+n,tail).every(v=>v===0)&&sum32(bytes)===0,'container layout/checksum differs');
 const {decoded,frames}=decodeFrameMap(bytes,size);need(sum32(decoded)===0,'decoded checksum differs');
 let at=0;const sections={};
 for(const row of layout){
  need(at+16<=decoded.length-4,'section header overrun');
  const length=row.name==='RTOS'?decoded.readUInt32LE(at+12):row.size-16;
  need(decoded.toString('ascii',at,at+8).split('\0')[0]===row.name&&length>0&&!(length&3)&&at+16+length<=decoded.length-4,'section layout differs');
  sections[row.name]={offset:at,size:length+16,block:decoded.subarray(at,at+16+length),payload:decoded.subarray(at+16,at+16+length)};at+=length+16;
 }
 need(at+4===decoded.length,'section trailer differs');return {decoded,frames,sections};
}
function expected(g,x,c){
 const chunks=[],words=[];let changed=0;
 need(Object.keys(g.sections).join('|')===Object.keys(x.sections).join('|'),'official section order differs');
 for(const [name,a] of Object.entries(g.sections)){
  const b=x.sections[name],p=c.sections[name];
  need(a.offset===b.offset&&a.size===b.size,'official section offsets differ at '+name);
  if(name==='RTOS'){
   need(p.size>=a.size&&p.size-a.size<=MAX_NATIVE_RTOS_GROWTH,'RTOS growth exceeds bounds');
   need(a.block.subarray(0,12).equals(p.block.subarray(0,12))&&a.block.subarray(0,16).equals(b.block.subarray(0,16)),'RTOS header differs');
   const target=Buffer.from(p.block);
   for(let off=0;off<a.payload.length;off+=4){
    const old=a.payload.subarray(off,off+4),other=b.payload.subarray(off,off+4),desired=p.payload.subarray(off,off+4);
    if(!old.equals(other)){
     need(desired.equals(old),'native patch overlaps model-specific RTOS word at 0x'+(0x53000000+off).toString(16));
     other.copy(target,16+off);words.push({offset:off,address:0x53000000+off,gr3_hex:old.toString('hex'),gr3x_hex:other.toString('hex')});
    }
   }
   for(let off=0;off<a.payload.length;off++)if(a.payload[off]!==p.payload[off])changed++;
   chunks.push(target);
  }else if(name==='ICONBIN'){
   need(a.block.equals(b.block)&&a.size===p.size&&a.block.subarray(0,16).equals(p.block.subarray(0,16)),'ICONBIN baseline/header differs');chunks.push(Buffer.from(p.block));
  }else{
   need(p.block.equals(a.block),'native candidate changed unrelated section '+name);chunks.push(Buffer.from(b.block));
  }
 }
 const target=Buffer.concat([...chunks,Buffer.alloc(4)]);repair(target);return {target,words,changed,growth:c.sections.RTOS.size-g.sections.RTOS.size};
}
function inputs(gr3official,xofficial,gr3candidate){
 const g=inspectOfficial(gr3official),x=inspectOfficial(xofficial);
 need(g.model==='GR III'&&x.model==='GR IIIx','exact GR III and GR IIIx baselines required');
 auditGr3Candidate(gr3official,gr3candidate,{minRtosGrowth:0,maxRtosGrowth:MAX_NATIVE_RTOS_GROWTH});
 const original=read(gr3official,g.sections),other=read(xofficial,x.sections),native=read(gr3candidate,g.sections);
 const intent=expected(original,other,native);
 // The component version is metadata, not a model-specific ABI word. It may
 // share any bytes (or all four) with the reference in a later upload.
 const modelWords=intent.words.filter(w=>w.offset!==0x2038);
 need(modelWords.length===18&&modelWords.reduce((n,w)=>n+Buffer.from(w.gr3_hex,'hex').reduce((m,v,i)=>m+(v!==Buffer.from(w.gr3x_hex,'hex')[i]),0),0)===27,'official RTOS parity differs');
 return {layout:x.sections,original,other,native,...intent};
}
function pack(base,original,target,identity){
 need(original.decoded.length===target.length,'pack extent differs');const chunks=[];let reused=0,replaced=0;
 for(const f of original.frames){const from=f.decoded_start,to=f.decoded_end,start=Math.max(0,from-8191);
  if(target.subarray(start,to).equals(original.decoded.subarray(start,to))){chunks.push(base.subarray(128+f.encoded_start,128+f.encoded_end));reused++;}
  else{for(let at=from;at<to;at+=0x6000){const p=target.subarray(at,Math.min(at+0x6000,to)),h=Buffer.alloc(2);h.writeUInt16BE(0x8000|p.length);chunks.push(h,p);}replaced++;}
 }
 chunks.push(Buffer.alloc(2));const payload=Buffer.concat(chunks),footer=Buffer.from(identity.subarray(-24));
 footer.writeUInt32LE(payload.length,12);footer.writeUInt32LE(target.length,16);footer.writeUInt32LE(0,20);
 const candidate=Buffer.concat([identity.subarray(0,128),payload,Buffer.alloc(-(128+payload.length)&3),footer]);
 need(candidate.length<MAX,'candidate exceeds 128 MiB');repair(candidate);return {candidate,reused_frames:reused,replaced_frames:replaced};
}
export function verifyGr3xNativePort(gr3official,xofficial,gr3candidate,xcandidate){
 // Derive intent again from the three source buffers. Never trust a builder receipt.
 const i=inputs(gr3official,xofficial,gr3candidate),actual=read(xcandidate,i.layout);
 need(xcandidate.subarray(0,128).equals(xofficial.subarray(0,128))&&xcandidate.subarray(-24,-12).equals(xofficial.subarray(-24,-12)),'GR IIIx outer identity/version differs');
 const want=readDecoded(i.target,i.layout);
 for(const [name,section] of Object.entries(want.sections))need(actual.sections[name].block.equals(section.block),'final section differs from independently derived intent: '+name);
 need(actual.decoded.equals(i.target),'final decoded trailer/bytes differ');
 return {schema:'m10v-gr3x-native-port/v1',verified:true,gr3_source_sha256:sha(gr3official),source_sha256:sha(xofficial),gr3_candidate_sha256:sha(gr3candidate),candidate_sha256:sha(xcandidate),candidate_bytes:xcandidate.length,rtos_growth:i.growth,rtos_changed_bytes:i.changed,model_words:i.words,checks:{fresh_decode:true,section_bytes:true,outer_sum32:0,decoded_sum32:0,cpu_payload_unchanged:true,model_words_preserved:true,outer_identity_preserved:true},camera_tested:false};
}
// Split a reconstructed decoded image using the same section boundaries as its intent.
function readDecoded(decoded,layout){let at=0;const sections={};for(const row of layout){const size=row.name==='RTOS'?decoded.readUInt32LE(at+12)+16:row.size;sections[row.name]={block:decoded.subarray(at,at+size)};at+=size;}need(at+4===decoded.length,'expected extent differs');return {sections};}
export function portNativeToGr3x(gr3official,xofficial,gr3candidate){
 const i=inputs(gr3official,xofficial,gr3candidate),encoded=pack(gr3candidate,i.native,i.target,xofficial);
 return {candidate:encoded.candidate,receipt:{...verifyGr3xNativePort(gr3official,xofficial,gr3candidate,encoded.candidate),reused_frames:encoded.reused_frames,replaced_frames:encoded.replaced_frames}};
}
// Pure codec/intent primitives for generated fixtures; public entry points always pin official hashes.
export const nativePortTestSupport=Object.freeze({read,expected,pack,repair});
