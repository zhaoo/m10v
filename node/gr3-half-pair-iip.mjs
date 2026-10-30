// Native IIP installation/readback audit. These checks bind declarations to
// source fingerprints, exported code ranges and exact original hook words;
// they do not establish physical DMA pixels or camera performance.
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {borderPatches} from './gr3-border.mjs';
const guardSources=['native/gr3/m10v_border_wait_guard.c','native/gr3/m10v_border_wait_guard.h',
 'scripts/border_recovery_wait_guard.S','scripts/border_recovery_wait_guard_contract.json',
 'scripts/build_gr3_border_wait_guard.py','native/gr3/m10v_border_fill_bundle.h'];
export const halfPairIipSources=[...new Set([...guardSources,
 'native/gr3/m10v_half_pair_iip.c','native/gr3/m10v_half_pair_iip.h',
 'native/gr3/m10v_border_fill_plan.h','native/gr3/m10v_border_canvas.h','native/gr3/m10v_border.h'])].sort();
const guardNames=[...['client_construct','client_prepare','client_notify','client_done','client_destroy_if_done',
 'client_wait','transfer_construct','transfer_body','transfer_wait','fill_bundle_submit','fill_construct',
 'resize_construct','fill_body','resize_body','fill_wait','resize_wait','resize_dma_wait','fill_release',
 'resize_release','stage_enter','stage_leave'].map(n=>'m10v_border_'+n),
 ...['transfer_body','transfer_wait','fill_body','resize_body','fill_wait','resize_wait','resize_dma_wait',
 'fill_release','resize_release'].map(n=>'border_recovery_'+n+'_hook')];
const iipNames=['m10v_half_pair_iip_ready','m10v_half_pair_iip_copy','m10v_half_pair_iip_compose'];
// Independent locked original instruction inventory, never imported from a
// generated Python report or inferred from its patch declarations.
const hooks=[
 [0x5369a010,0xe3a00044,0xe3a00058],
 [0x5369a01c,0xeb0000a7,'m10v_border_transfer_construct'],
 [0x5369ac4c,0xebffff3d,'border_recovery_transfer_body_hook'],
 [0x5369a478,0xeb003e83,'border_recovery_transfer_wait_hook'],
 [0x534aae28,0xeb07fc17,'m10v_border_client_wait'],
 [0x536589fc,0xe3a00058,0xe3a00068],
 [0x53658a08,0xeb00009a,'m10v_border_fill_construct'],
 [0x536594a0,0xebfffed9,'border_recovery_fill_body_hook'],
 [0x5376a370,0xebfcfec5,'border_recovery_fill_wait_hook'],
 [0x53672bac,0xe3a00048,0xe3a00058],
 [0x53672bb8,0xeb000094,'m10v_border_resize_construct'],
 [0x53674014,0xebfffc1f,'border_recovery_resize_body_hook'],
 [0x5377160c,0xebfce21e,'border_recovery_resize_wait_hook'],
 [0x53673244,0xeb00db10,'border_recovery_resize_dma_wait_hook'],
 [0x5367331c,0xeb00dada,'border_recovery_resize_dma_wait_hook'],
 [0x53673384,0xeb00dac0,'border_recovery_resize_dma_wait_hook'],
 [0x5376a38c,0xeb001278,'border_recovery_fill_release_hook'],
 [0x53771968,0xebfff501,'border_recovery_resize_release_hook'],
];
const original='8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67';
const need=(v,s)=>{if(!v)throw Error('Half IIP: '+s);};
const sha=b=>createHash('sha256').update(b).digest('hex');
const canonical=v=>JSON.stringify(sort(v));
function sort(v){return Array.isArray(v)?v.map(sort):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,sort(v[k])])):v;}
function keys(object,want,label){need(object&&typeof object==='object'&&!Array.isArray(object)&&
 canonical(Object.keys(object).sort())===canonical([...want].sort()),label+' inventory differs');}
function branch(at,target){const delta=target-at-8;need(Number.isInteger(at)&&Number.isInteger(target)&&at%4===0&&target%4===0&&delta>=-(2**25)&&delta<2**25,'ARM BL range');return (0xeb000000|((delta>>2)&0xffffff))>>>0;}
function sourceHashes(got,want,label,exact=false){
 if(exact)keys(got,want,label);
 for(const file of want)need(got?.[file]===sha(readFileSync(new URL('../'+file,import.meta.url))),label+' source hash differs: '+file);
}
export function halfPairIipPatches(runtime,m){
 const pair=m.half_pair;
 if(!pair||pair.enabled===false){need(!pair?.iip_guard&&!pair?.iip_component,'disabled pair contains IIP component');return [];}
 need(pair.enabled===true&&pair.schema==='m10v-half-pair/v1'&&pair.backend==='native-IIP'&&pair.storage==='owned-native-bank'&&
  pair.frame_filesystem_calls===0&&pair.cpu_pixel_reads===0&&pair.cpu_pixel_writes===0&&pair.first_original_preserved===true&&pair.camera_tested===false,
 'native backend/ownership/evidence contract differs');
 need(Buffer.isBuffer(runtime)&&Number.isInteger(m.base)&&m.base>=0x540be000&&m.base%16===0&&m.camera_model==='gr3'&&m.symbols,'GR III aspect runtime missing');
 need(!Object.hasOwn(m.symbols,'m10v_half_pair_compose'),'retired CPU compositor is linked');
 need(!runtime.includes(Buffer.from('HALFPAIR.BIN'))&&!runtime.includes(Buffer.from('HALFPAIR.BIN','utf16le')),'retired photo-file path is linked');
 sourceHashes(m.sources,halfPairIipSources,'central');
 const inside=(at,n=4,lo=m.base,hi=m.base+runtime.length)=>Number.isSafeInteger(at)&&Number.isSafeInteger(n)&&n>0&&at%4===0&&at>=lo&&at+n<=hi;
 const g=pair.iip_guard,c=pair.iip_component;
 need(g?.schema==='m10v-border-guard-component/v1'&&g.enabled===true&&g.internal_research===true&&g.camera_model==='gr3'&&g.original_version==='2.10'&&g.original_rtos_sha256===original&&
  g.mutable_static_bytes===0&&g.tls_bytes===0&&g.hardware_activation===false&&g.pixel_pipeline_enabled===false&&g.firmware_artifact===false&&g.camera_tested===false&&g.model_layout_verified===true&&g.physical_model_support_verified===false&&g.caller_address_ownership_required===true,'guard identity/ownership/evidence contract differs');
 const expectedContract={...JSON.parse(readFileSync(new URL('../scripts/border_recovery_wait_guard_contract.json',import.meta.url),'utf8')),abi_basis_model:'gr3',model:'gr3',firmware:'2.10',rtos_sha256:original};
 need(canonical(g.contract)===canonical(expectedContract),'guard callback/serialization ABI differs');
 const allocation={transfer_first:{stock:0x44,owned:0x58,gate_offset:0x54},fill:{stock:0x58,owned:0x68},resize:{stock:0x48,owned:0x58},transfer_second_preserved:0x44};
 need(canonical(g.worker_allocations)===canonical(allocation),'guard worker allocation/gate differs');
 sourceHashes(g.sources,guardSources,'guard',true);
 need(g.base%16===0&&g.code_bytes<=65536&&inside(g.base,g.code_bytes)&&sha(runtime.subarray(g.base-m.base,g.base-m.base+g.code_bytes))===g.code_sha256,'guard code extent/SHA differs');
 need(Array.isArray(g.sections)&&g.sections.length===2&&g.sections[0].name==='.text'&&g.sections[1].name==='.rodata','guard section inventory differs');
 let end=g.base;
 for(const s of g.sections){need(inside(s.address,s.bytes,g.base,g.base+g.code_bytes)&&s.address>=end,'guard section bounds');for(let at=end;at<s.address;at++)need(runtime[at-m.base]===0,'guard section padding');end=s.address+s.bytes;}
 need(g.sections[0].address===g.base&&end===g.base+g.code_bytes,'guard section extent differs');
 keys(g.symbols,guardNames,'guard symbols');
 for(const name of guardNames)need(inside(g.symbols[name],4,g.sections[0].address,g.sections[0].address+g.sections[0].bytes)&&m.symbols[name]===g.symbols[name],'guard export binding differs: '+name);
 need(c&&c.base%16===0&&c.code_bytes<=65536&&inside(c.base,c.code_bytes)&&sha(runtime.subarray(c.base-m.base,c.base-m.base+c.code_bytes))===c.code_sha256,'IIP code extent/SHA differs');
 need(c.base+c.code_bytes<=g.base||g.base+g.code_bytes<=c.base,'IIP/guard code overlaps');
 keys(c.symbols,iipNames,'IIP symbols');
 for(const name of iipNames)need(inside(c.symbols[name],4,c.base,c.base+c.code_bytes)&&m.symbols[name]===c.symbols[name],'IIP export binding differs: '+name);
 need(new Set([...Object.values(g.symbols),...Object.values(c.symbols)]).size===guardNames.length+iipNames.length,'aliased IIP/guard functions');
 const out=hooks.map(([address,expected,target])=>({address,expected,replacement:typeof target==='string'?branch(address,g.symbols[target]):target,
  name:'Half IIP '+(typeof target==='string'?target:address.toString(16)),...(typeof target==='string'?{symbol:target,target:g.symbols[target]}:{})}));
 need(Array.isArray(g.patches)&&g.patches.length===18,'guard patch count differs');
 out.forEach((p,i)=>need(g.patches[i]?.address===p.address&&g.patches[i]?.expected===p.expected&&g.patches[i]?.replacement===p.replacement&&g.patches[i]?.symbol===p.symbol&&g.patches[i]?.target===p.target,'guard original instruction/target inventory differs'));
 const shared=m.border?.hardware_component;
 if(shared){
  need(m.border.enabled===true&&canonical(shared.guard)===canonical(g),'shared border guard differs');
  // The full border auditor independently checks its20 patches, code/shims,
  // sources and JPEG handoff; our18 guard instructions must not be added twice.
  const border=borderPatches(runtime,m);
  need(border.length===20&&out.every(p=>border.some(q=>q.address===p.address&&q.expected===p.expected&&q.replacement===p.replacement&&q.symbol===p.symbol&&q.target===p.target)),'shared border guard installation differs');
  return [];
 }
 need(!m.border?.pixel_pipeline_enabled,'border declares runtime without shared component');
 return out;
}
