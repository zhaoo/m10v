import {MAX_NATIVE_RTOS_GROWTH} from './gr3-native-budget.mjs';
// Compose reviewed camera components with the native library, then compare every final byte.
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {inspectOfficial} from './firmware.mjs';
import {decodeFrameMap,sum32} from './gr3-frames.mjs';
import {auditGr3Candidate} from './gr3-candidate-audit.mjs';
import {auditNativeLibrary} from './gr3-m10v-native-build.mjs';
import {createStorePlan} from './gr3-store-plan.mjs';
import {runGr3Runtime} from './gr3-runtime.mjs';
import {planRawNr,rawNrEvidence} from './gr3-raw-nr.mjs';
import {normalizeExtensions,activeExtensions} from '../web/gr3/native-library-state.mjs';
const need=(ok,message)=>{if(!ok)throw Error(message);};
const sha=b=>createHash('sha256').update(b).digest('hex');
const LOAD=0x53000000, COMPONENT_BASE=0x540b6000, COMPONENT_END=0x540ba000;
const ASPECT_END=0x540be000, verifiedComponents=new WeakMap();
const pins={
 aspect:'c89c128aada72194d7282355a5f2f06409515ce8cea3a0da97e047bc9e046b82',
 level:'52a7c4d254cb6f117b2c891373c99ad6357a5df94519e038481c68f4661307ed',
 'aspect-level':'e8d9416c7c594e6af9934e91c63ae2880ca445c865a0b5123e66c034d5b24cec',
};
const resourceAdaptations=[
 [0x540b9448,0xe300032a,0xe30003a9],
 [0x540b8a18,0xe300c32a,0xe300c3a9],
 [0x540b8be4,0xe300c32a,0xe300c3a9],
 [0x540b8a4c,0xe3003311,0xe30033a8],
 [0x540b8a6c,0xe3003311,0xe30033a8],
 [0x540b8c14,0xe3003311,0xe30033a8],
];
export function integrationFingerprint(){
 return sha(JSON.stringify(['gr3-native-budget.mjs','gr3-integrated-components.mjs','gr3-raw-nr.mjs','gr3-stock-presets.mjs','gr3-native-library.mjs','gr3x-native-port.mjs','gr3-candidate-audit.mjs','gr3-version-unlock.mjs','gr3-m10v-native-build.mjs','gr3-runtime.mjs','gr3-runtime-worker.py','gr3-store-plan.mjs','../scripts/gr3_aspect_overlay.py','../native/gr3/m10v_aspect.c','../native/gr3/m10v_aspect_config.h','../native/gr3/m10v_aspect_hooks.S','../native/gr3/m10v_aspect_dng.c','../web/gr3/native-library-state.mjs','../web/gr3/model-capabilities.mjs'].map(n=>[n,sha(readFileSync(new URL(n,import.meta.url)))])));
}
function parts(source,candidate){
 const report=inspectOfficial(source),decoded=decodeFrameMap(candidate,candidate.readUInt32LE(candidate.length-8)).decoded;
 let at=0;const sections={};
 for(const section of report.sections){
  need(decoded.toString('ascii',at,at+8).split('\0')[0]===section.name,'composition section order differs');
  const size=section.name==='RTOS'?decoded.readUInt32LE(at+12):section.size-16;
  need(at+16+size<=decoded.length-4,'composition section bounds differ');
  sections[section.name]={offset:at+16,size};at+=size+16;
 }
 need(at+4===decoded.length,'composition trailer differs');
 const r=sections.RTOS;return {decoded,sections,rtos:decoded.subarray(r.offset,r.offset+r.size)};
}
const variant=e=>[e.aspect?'aspect':null,e.level?'level':null].filter(Boolean).join('-');
export async function buildCameraComponents(source,requested,{signal,halfFrame=true}={}){
 const e=normalizeExtensions(requested),key=variant(e);if(!key)return null;
 need(inspectOfficial(source).model==='GR III','组合扩展当前仅支持 GR III');
 const {candidate,receipt}=await runGr3Runtime(source,createStorePlan({variant:'street',features:key.split('-')}),'build',undefined,{signal,halfFrame});
 if(e.aspect){
  need(receipt.m10v_aspect?.schema==='m10v-gr3-aspect/v1'&&receipt.m10v_aspect.raw_id===5,'crop extension build receipt missing');
  need(receipt.m10v_aspect.half_frame?.enabled===halfFrame,'half-frame model gate differs');
  const p=parts(source,candidate);
  need(p.rtos.length===ASPECT_END-LOAD&&receipt.m10v_aspect.module_range?.[0]===0x540bc000&&sha(p.rtos.subarray(0x540bc000-LOAD))===receipt.m10v_aspect.module_sha256,'crop module readback differs');
  verifiedComponents.set(candidate,sha(p.rtos));
 }
 validateComponent(source,candidate,e);return candidate;
}
export function cameraComponentBase(source,component){return component?LOAD+parts(source,component).rtos.length:COMPONENT_BASE;}
function validateComponent(source,component,e){
 const key=variant(e);if(!key){need(component===null,'unexpected camera component');return null;}
 need(Buffer.isBuffer(component),'camera component missing');
 const structural=auditGr3Candidate(source,component);
 need(structural.changedSections.join('|')==='RTOS','camera component changed unrelated section');
 const p=parts(source,component);
 need((p.rtos.length===COMPONENT_END-LOAD&&sha(p.rtos)===pins[key])||
  (e.aspect&&p.rtos.length===ASPECT_END-LOAD&&sha(p.rtos)===verifiedComponents.get(component)),'camera component source pin differs');
 return p;
}
function expectedImage(source,nativeCandidate,runtime,manifest,component,requested){
 const e=normalizeExtensions(requested),nativeReceipt=auditNativeLibrary(source,nativeCandidate,runtime,manifest);
 need(inspectOfficial(source).model==='GR III'||!activeExtensions(e).length,'组合扩展当前仅支持 GR III');
 const original=parts(source,source),native=parts(source,nativeCandidate),c=validateComponent(source,component,e);
 const componentEnd=c?LOAD+c.rtos.length:COMPONENT_BASE;
 need(manifest.base===componentEnd,'composition native placement differs');
 const target=Buffer.from(native.decoded),rtos=target.subarray(native.sections.RTOS.offset,native.sections.RTOS.offset+native.sections.RTOS.size);
 let stockWords=0;
 if(c){
  for(let off=0;off<original.rtos.length;off+=4){
   const stock=original.rtos.subarray(off,off+4),addition=c.rtos.subarray(off,off+4);
   if(addition.equals(stock))continue;
   const current=rtos.subarray(off,off+4),address=LOAD+off;
   if(e.aspect&&address===0x536a2a30&&manifest.zoom?.enabled===true&&manifest.film_library_enabled!==false){
    const hook=manifest.zoom.patches.find(p=>p.address===address);
    const aspectBranch=(0xea000000|(((0x540b9450-address-8)>>2)&0xffffff))>>>0;
    need(stock.readUInt32LE()===0xeddf7af8&&addition.readUInt32LE()===aspectBranch&&
      hook&&current.readUInt32LE()===hook.replacement&&
      manifest.zoom.bindings.m10v_zoom_original_resolution===0x540b9450,'zoom/aspect resolution chain differs');
    // Zoom delegates canonical dimensions to the existing aspect dispatcher.
    // Preserve the verified zoom entry; the component body is copied below.
    stockWords++;continue;
   }
   const nativeBound=(0xe3003000|manifest.resources.last_id)>>>0;
   const router=e.aspect&&[0x533966d4,0x533970ec].includes(address);
   need(current.equals(stock)||(router&&current.readUInt32LE()===nativeBound),'camera components overlap native patch at '+address.toString(16));
   addition.copy(rtos,off);stockWords++;
  }
  need(rtos.subarray(original.rtos.length,componentEnd-LOAD).every(v=>v===0),'camera component allocation overlaps native module');
  c.rtos.subarray(original.rtos.length).copy(rtos,original.rtos.length);
  if(e.aspect){
   need(rtos.readUInt32LE(0x540b97e8-LOAD)===2,'component must disable its timestamp renderer');
   for(const [address,before,after] of resourceAdaptations){const off=address-LOAD;need(rtos.readUInt32LE(off)===before,'aspect resource preimage differs');const id=manifest.resources.last_id+(after===0xe30033a8?0:1);rtos.writeUInt32LE(((after&0xfffff000)|id)>>>0,off);}
   if(componentEnd===ASPECT_END){
    const wideMarker=Buffer.from('413746572d030000','hex'),wideAt=rtos.indexOf(wideMarker,COMPONENT_END-LOAD);
    need(wideAt>=0x540bc000-LOAD&&wideAt+8<=ASPECT_END-LOAD&&rtos.indexOf(wideMarker,wideAt+1)===-1,'16:9 resource binding differs');
    rtos.writeUInt32LE(manifest.resources.last_id+4,wideAt+4);
    const halfMarker=Buffer.from('413746482c03000000000000','hex'),halfAt=rtos.indexOf(halfMarker,COMPONENT_END-LOAD);
    if(manifest.camera_model==='gr3'){
     need(halfAt>=0x540bc000-LOAD&&halfAt+12<=ASPECT_END-LOAD&&rtos.indexOf(halfMarker,halfAt+1)===-1,'half-frame model/resource binding differs');
     rtos.writeUInt32LE(manifest.resources.last_id+3,halfAt+4);
     if(manifest.film_library_enabled!==false){need(manifest.half_frame_icon?.id===875,'half-frame icon missing');rtos.writeUInt32LE(875,halfAt+8);}
    }else need(halfAt===-1,'half-frame must be disabled for this model');
    const marker=Buffer.from('413752362b03000011030000','hex');
    const at=rtos.indexOf(marker,COMPONENT_END-LOAD);
    need(at>=COMPONENT_END-LOAD&&at+marker.length<=ASPECT_END-LOAD&&rtos.indexOf(marker,at+1)===-1,'6x7 resource binding differs');
    rtos.writeUInt32LE(manifest.resources.last_id+2,at+4);rtos.writeUInt32LE(manifest.resources.last_id,at+8);
    if(manifest.film_library_enabled!==false){
     const marker=Buffer.from('413741490000000000000000','hex'),iconAt=rtos.indexOf(marker,COMPONENT_END-LOAD);
     need(iconAt>=COMPONENT_END-LOAD&&iconAt+16<=ASPECT_END-LOAD&&rtos.indexOf(marker,iconAt+1)===-1,'aspect icon binding differs');
     const entry=rtos.readUInt32LE(iconAt+12),icons=manifest.aspect_icons;
     need(entry>=0x540bc000&&entry<ASPECT_END&&entry%4===0&&icons?.last_id===icons?.first_id+1,'aspect icon adapter differs');
     rtos.writeUInt32LE(icons.first_id,iconAt+4);rtos.writeUInt32LE(icons.last_id,iconAt+8);
    }
   }
  }
 }
 if(e.negativeGrain){
  need(rtos.readUInt32LE(0xb348c0)===9&&rtos.readUInt16LE(0xb3501e)===0,'negative grain preimage differs');
  rtos.writeUInt32LE(10,0xb348c0);rtos.writeUInt16LE(0x0f02,0xb3501e);
 }
 const rawEdits=planRawNr(source,e.rawNr);
 for(const edit of rawEdits){
  const expected=Buffer.from(edit.expectedHex,'hex'),replacement=Buffer.from(edit.replacementHex,'hex');
  need(rtos.subarray(edit.offset,edit.offset+expected.length).equals(expected),'RAW NR patch overlaps another component');
  replacement.copy(rtos,edit.offset);
 }
 target.writeUInt32LE(0,target.length-4);target.writeUInt32LE(-sum32(target)>>>0,target.length-4);
 return {target,nativeReceipt,composition:{schema:'m10v-gr3-integrated-components/v1',verified:true,extensions:e,
  component_variant:variant(e)||null,component_rtos_sha256:c?sha(c.rtos):null,
  component_range:c?[COMPONENT_BASE,componentEnd]:null,native_range:[manifest.base,manifest.base+runtime.length],
  native_resource_range:[786,manifest.resources.last_id],aspect_resource_id:e.aspect?manifest.resources.last_id+1:null,
  shared_resource_routes:e.aspect?2:0,adapted_resource_words:e.aspect?6:0,component_stock_words:stockWords,
  aspect_indicator:e.aspect&&componentEnd===ASPECT_END&&manifest.film_library_enabled!==false?{render_path:'native-grid-overlay/icon-blitter',first_id:manifest.aspect_icons.first_id,last_id:manifest.aspect_icons.last_id,width:60,height:40}:null,
  six_by_seven_resource_id:e.aspect&&componentEnd===ASPECT_END?manifest.resources.last_id+2:null,
  half_frame:{enabled:!!(e.aspect&&componentEnd===ASPECT_END&&manifest.camera_model==='gr3'),raw_id:6,
   resource_id:e.aspect&&manifest.camera_model==='gr3'?manifest.resources.last_id+3:null,
   icon_id:e.aspect&&manifest.camera_model==='gr3'&&manifest.film_library_enabled!==false?875:null},
  negative_grain_sites:e.negativeGrain?[0x53b348c0,0x53b3501e]:[],
  raw_nr:{configuration:e.rawNr,...rawNrEvidence(source,e.rawNr),patch_count:rawEdits.length,
   patched_bytes:rawEdits.reduce((n,p)=>n+p.replacementHex.length/2,0),
   patches_sha256:sha(JSON.stringify(rawEdits)),
   code_sites:e.rawNr.mode==='off'?rawEdits.map(({offset,expectedHex,replacementHex})=>({address:LOAD+offset,expected_hex:expectedHex,replacement_hex:replacementHex})):[],
   table_cleared_index_range:e.rawNr.mode==='threshold'?[36,Math.round(8*(Math.log2(e.rawNr.iso/3.125)-1))]:null},
  camera_tested:false}};
}
// Reuse compressed frames only when their entire backward-reference history is unchanged.
function encode(base,target){
 const {decoded,frames}=decodeFrameMap(base,base.readUInt32LE(base.length-8));
 need(decoded.length===target.length,'composition must retain allocated extent');const chunks=[];
 for(const f of frames){const from=f.decoded_start,to=f.decoded_end,history=Math.min(8191,from),bytes=target.subarray(from,to);
  if(target.subarray(from-history,to).equals(decoded.subarray(from-history,to)))chunks.push(base.subarray(128+f.encoded_start,128+f.encoded_end));
  else for(let at=0;at<bytes.length;at+=0x6000){const part=bytes.subarray(at,at+0x6000),prefix=Buffer.alloc(2);prefix.writeUInt16BE(0x8000|part.length);chunks.push(prefix,part);}
 }
 chunks.push(Buffer.alloc(2));const payload=Buffer.concat(chunks),footer=Buffer.from(base.subarray(-24));
 footer.writeUInt32LE(payload.length,12);footer.writeUInt32LE(target.length,16);footer.writeUInt32LE(0,20);
 const candidate=Buffer.concat([base.subarray(0,128),payload,Buffer.alloc(-(128+payload.length)&3),footer]);
 candidate.writeUInt32LE(-sum32(candidate)>>>0,candidate.length-4);return candidate;
}
export function auditIntegratedNative(source,candidate,nativeCandidate,runtime,manifest,component,extensions){
 auditGr3Candidate(source,candidate,{maxRtosGrowth:MAX_NATIVE_RTOS_GROWTH});
 const {target,composition}=expectedImage(source,nativeCandidate,runtime,manifest,component,extensions);
 need(parts(source,candidate).decoded.equals(target),'integrated final bytes differ from verified components');
 return composition;
}
export function composeNative(source,nativeCandidate,runtime,manifest,component,extensions){
 const {target}=expectedImage(source,nativeCandidate,runtime,manifest,component,extensions),candidate=encode(nativeCandidate,target);
 const composition=auditIntegratedNative(source,candidate,nativeCandidate,runtime,manifest,component,extensions);
 const structure=auditGr3Candidate(source,candidate,{maxRtosGrowth:MAX_NATIVE_RTOS_GROWTH});
 return {candidate,composition,structure};
}
