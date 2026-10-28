// Independent native installation/readback contract, not a camera acceptance.
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';

const modules=[
 ['native/gr3/m10v_border.c',['m10v_border_layout','m10v_border_storage_layout','m10v_border_preview_fit']],
 ['native/gr3/m10v_border_bank.c',['m10v_border_bank_shape','m10v_border_bank_plan']],
 ['native/gr3/m10v_border_canvas.c',['m10v_border_canvas_plan']],
 ['native/gr3/m10v_border_fill_plan.c',['m10v_border_fill_plan']],
 ['native/gr3/m10v_border_prepare.c',['m10v_border_prepare']],
 ['native/gr3/m10v_border_runtime.c',['m10v_border_runtime_before_submit','m10v_border_runtime_after_resize']],
];
const guardSources=['native/gr3/m10v_border_wait_guard.c','native/gr3/m10v_border_wait_guard.h',
 'scripts/border_recovery_wait_guard.S','scripts/border_recovery_wait_guard_contract.json',
 'scripts/build_gr3_border_wait_guard.py','native/gr3/m10v_border_fill_bundle.h'];
const componentSources=[...new Set([...modules.flatMap(([file])=>[file,file.replace(/\.c$/,'.h')]),
 ...guardSources,'scripts/build_gr3_border_runtime.py','native/gr3/m10v_border_shot.h'])].sort();
export const borderSources=[...new Set([...componentSources,'native/gr3/m10v_border_camera.c',
 'native/gr3/m10v_border_camera.h','native/gr3/m10v_border_shot.c'])].sort();
const reused=['m10v_border_shot_read','m10v_border_shot_orientation','m10v_border_shot_phase',
 'm10v_border_shot_transition','m10v_capture_library'];
const guardNames=[...['client_construct','client_prepare','client_notify','client_done','client_destroy_if_done',
 'client_wait','transfer_construct','transfer_body','transfer_wait','fill_bundle_submit','fill_construct',
 'resize_construct','fill_body','resize_body','fill_wait','resize_wait','resize_dma_wait','fill_release',
 'resize_release','stage_enter','stage_leave'].map(n=>'m10v_border_'+n),
 ...['transfer_body','transfer_wait','fill_body','resize_body','fill_wait','resize_wait','resize_dma_wait',
 'fill_release','resize_release'].map(n=>'border_recovery_'+n+'_hook')];
const hookNames=['m10v_border_runtime_submit_hook','m10v_border_runtime_resize_hook'];
// Independently locked original words. Do not derive this inventory from Python
// source or from the untrusted builder's patch array.
const guardHooks=[
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
const identities={gr3:['2.10','8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67'],
 gr3x:['1.60','0f11b0d28bc67932d044c5d01bc0314844a756057c89984278c73a23449a24c6']};
const need=(v,s)=>{if(!v)throw Error('border: '+s);};
const sha=b=>createHash('sha256').update(b).digest('hex');
const keys=(object,want,label)=>need(object&&typeof object==='object'&&!Array.isArray(object)&&
 JSON.stringify(Object.keys(object).sort())===JSON.stringify([...want].sort()),label+' inventory differs');
const same=(got,want,label)=>need(got?.length===want.length&&want.every((n,i)=>got[i]===n),label+' differs');
const branch=(at,target,link=false)=>{const delta=target-at-8;
 need(Number.isInteger(at)&&Number.isInteger(target)&&at%4===0&&target%4===0&&
 delta>=-(2**25)&&delta<2**25,'ARM branch range');
 return ((link?0xeb000000:0xea000000)|((delta>>2)&0xffffff))>>>0;};

export function borderPatches(runtime,m){
 const b=m.border;
 if(!b||b.enabled===false){need(!b?.pixel_pipeline_enabled&&!b?.hardware_component,'disabled component present');return [];}
 need(b.enabled===true&&b.pixel_pipeline_enabled===true&&b.hardware_component,'metadata-only border cannot export');
 const h=b.hardware_component,g=h.guard,identity=identities[m.camera_model];
 need(Buffer.isBuffer(runtime)&&Number.isInteger(m.base)&&m.base%16===0&&m.symbols,'runtime extent missing');
 need(identity&&h.camera_model===m.camera_model&&h.original_version===identity[0]&&h.original_rtos_sha256===identity[1],
 'official model identity differs');
 need(h.schema==='m10v-border-runtime-component/v1'&&h.enabled===true&&h.installed_software_layer===true&&
 h.metadata_allocation_bytes===5820&&h.mutable_static_bytes===0&&h.tls_bytes===0&&h.cpu_raster_pass===false&&
 h.native_jpeg_encoded_capacity_preserved===true&&h.hardware_ready===false&&h.hardware_activation===false&&
 h.camera_tested===false&&h.physical_model_support_verified===false&&h.firmware_artifact===false,
 'runtime ownership/performance/evidence contract differs');
 const inside=(at,n=4,lo=m.base,hi=m.base+runtime.length)=>Number.isInteger(at)&&Number.isInteger(n)&&n>0&&
 at%4===0&&at>=lo&&at+n<=hi;
 need(h.base%16===0&&h.code_budget_bytes===65536&&h.code_bytes<=65536&&inside(h.base,h.code_bytes),
 'component extent differs');
 const end=h.base+h.code_bytes;
 need(sha(runtime.subarray(h.base-m.base,end-m.base))===h.code_sha256,'component code SHA differs');
 function sources(got,want,label){keys(got,want,label);for(const file of want)
  need(got[file]===sha(readFileSync(new URL('../'+file,import.meta.url))),label+' source hash differs: '+file);}
 sources(h.sources,componentSources,'component');sources(g?.sources,guardSources,'guard');
 for(const file of borderSources)need(m.sources?.[file]===sha(readFileSync(new URL('../'+file,import.meta.url))),
 'central source hash differs: '+file);
 same(h.compiled_sources,modules.map(([file])=>file),'compiled modules');
 need(g.schema==='m10v-border-guard-component/v1'&&g.enabled===true&&g.internal_research===true&&
 g.camera_model===m.camera_model&&g.original_rtos_sha256===identity[1]&&g.original_version===identity[0]&&
 g.mutable_static_bytes===0&&g.tls_bytes===0&&g.hardware_activation===false&&g.pixel_pipeline_enabled===false&&
 g.contract?.serialized_private_chain_required===true,'guard contract differs');
 for(const [name,stock,owned] of [['transfer_first',0x44,0x58],['fill',0x58,0x68],['resize',0x48,0x58]])
  need(g.worker_allocations?.[name]?.stock===stock&&g.worker_allocations[name].owned===owned,'worker allocation differs');
 need(g.worker_allocations.transfer_first.gate_offset===0x54&&g.worker_allocations.transfer_second_preserved===0x44,
 'transfer worker gate differs');
 const sectionNames=['guard',...modules.map(([file])=>file),'runtime_hooks'];
 need(Array.isArray(h.sections)&&h.sections.length===8,'section inventory differs');
 let next=h.base;
 for(let i=0;i<8;i++){
  const s=h.sections[i];need(s?.name===sectionNames[i]&&s.address===next&&inside(s.address,s.bytes,h.base,end),
   'section placement differs');
  const stop=s.address+s.bytes,aligned=(stop+15)&~15;
  if(i<7)for(let at=stop;at<aligned;at++)need(runtime[at-m.base]===0,'nonzero section padding');
  next=i===7?stop:aligned;
 }
 need(next===end&&h.sections[7].bytes===124,'component end/hook size differs');
 need(g.base===h.base&&g.code_bytes===h.sections[0].bytes&&inside(g.base,g.code_bytes,h.base,end)&&
 sha(runtime.subarray(g.base-m.base,g.base-m.base+g.code_bytes))===g.code_sha256,'guard subrange SHA differs');
 need(Array.isArray(g.sections)&&g.sections.length===2&&g.sections[0].name==='.text'&&g.sections[1].name==='.rodata',
 'guard code sections differ');
 let guardEnd=g.base;
 for(const s of g.sections){need(inside(s.address,s.bytes,g.base,g.base+g.code_bytes)&&s.address>=guardEnd,'guard section bounds');guardEnd=s.address+s.bytes;}
 need(g.sections[0].address===g.base&&guardEnd===g.base+g.code_bytes,'guard section extent differs');
 const allNames=[...guardNames,...modules.flatMap(([,names])=>names),...hookNames];
 keys(h.symbols,allNames,'component symbols');keys(g.symbols,guardNames,'guard symbols');
 function symbols(table,want,section){keys(table,want,'section symbols');for(const name of want){const address=table[name];
  need(inside(address,4,section.address,section.address+section.bytes)&&h.symbols[name]===address&&m.symbols[name]===address,
   'symbol location differs: '+name);}}
 symbols(g.symbols,guardNames,g.sections[0]);
 modules.forEach(([,names],i)=>symbols(h.sections[i+1].symbols,names,h.sections[i+1]));
 symbols(h.sections[7].symbols,hookNames,h.sections[7]);
 need(new Set(Object.values(h.symbols)).size===allNames.length,'aliased component functions');
 keys(h.reused_central_symbols,reused,'reused central symbols');
 for(const name of reused)need(h.reused_central_symbols[name]===m.symbols[name]&&
 inside(m.symbols[name])&&!(m.symbols[name]>=h.base&&m.symbols[name]<end),'reused central export differs');
 const patch=(address,expected,target,link=true)=>({address,expected,replacement:typeof target==='string'?
 branch(address,h.symbols[target],link):target,name:'border '+(typeof target==='string'?target:address.toString(16)),
 ...(typeof target==='string'?{symbol:target,target:h.symbols[target]}:{})});
 const out=guardHooks.map(([at,old,target])=>patch(at,old,target));
 out.push(patch(0x53501f98,0xeb06a762,hookNames[0]),patch(0x534ff458,0xe51b2028,hookNames[1],false));
 function inventory(got,want,label){need(Array.isArray(got)&&got.length===want.length,label+' patch count differs');
  want.forEach((p,i)=>need(got[i]?.address===p.address&&got[i]?.expected===p.expected&&got[i]?.replacement===p.replacement&&
   got[i]?.target===p.target&&got[i]?.symbol===p.symbol,
   label+' patch inventory differs'));}
 inventory(g.patches,out.slice(0,18),'guard');inventory(h.patches,out,'component');
 // Exact ARM templates independently preserve all general registers, LR,
 // CPSR and the incoming SP, including an originally unaligned stack.
 const save=[0xe92d5fff,0xe10fc000,0xe52dc004,0xe1a0c00d,0xe3cdd007,0xe24dd008,0xe58dc000];
 const restore=[0xe59dd000,0xe49dc004,0xe12ff00c,0xe8bd5fff];
 function check(at,words){need(inside(at,words.length*4,h.sections[7].address,end),'hook bounds');
  words.forEach((word,i)=>need(runtime.readUInt32LE(at-m.base+i*4)===(Array.isArray(word)?
   branch(at+i*4,word[0],word[1]):word>>>0),'full-context shim instruction differs'));}
 const submit=h.symbols[hookNames[0]],resize=h.symbols[hookNames[1]];
 need(submit===h.sections[7].address&&resize===submit+60&&resize+64===end,'hook layout differs');
 check(submit,[...save,0xe2440a09,0xe1a01006,[h.symbols.m10v_border_runtime_before_submit,true],...restore,[0x536abd28,false]]);
 check(resize,[...save,0xe1a00007,0xe1a01004,[h.symbols.m10v_border_runtime_after_resize,true],...restore,0xe51b2028,[0x534ff45c,false]]);
 return out;
}
