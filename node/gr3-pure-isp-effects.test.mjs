import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,mkdtempSync,rmSync,existsSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import path from 'node:path';
import os from 'node:os';
import {pureIspEffectSources,pureIspEffectPatches,auditPureIspReservationShim,auditPureIspCaptureWrappers} from './gr3-m10v-native-build.mjs';
import {borderPatches,borderSources} from './gr3-border.mjs';
import {readNativeOfficial,prepareNative,validatePureIspEffectsManifest} from './gr3-native-library.mjs';
import {defaultConfiguration} from '../web/gr3/native-library-state.mjs';

test('pure ISP opt-in preserves default plan and defaults, binds distinct fingerprint',async()=>{
 const source=await readNativeOfficial('gr3'),configuration=defaultConfiguration();
 const options={film_library:true,live_color:true,hdf_enabled:true,border_enabled:true};
 const normal=prepareNative(source,configuration,options);
 assert.deepEqual(normal,prepareNative(source,configuration,{...options,pure_isp_effects:false}));
 assert.equal(Object.hasOwn(normal,'pure_isp_effects'),false);
 const pure=prepareNative(source,configuration,{...options,pure_isp_effects:true});
 assert.equal(pure.pure_isp_effects,true);assert.equal(pure.capture_pipeline,'gr3-native-v8');
 assert.notEqual(pure.configuration_sha256,normal.configuration_sha256);
 const previewOff=prepareNative(source,configuration,{...options,pure_isp_effects:true,live_color:false});
 assert.notEqual(pure.configuration_sha256,previewOff.configuration_sha256);
 assert.equal(pure.configuration.hdf,0);assert.deepEqual(pure.configuration,normal.configuration);
 assert.deepEqual(pure.stock_detail,normal.stock_detail);
 for(const feature of ['ispLightLeak','ispGrain','ispBlur'])assert.ok(pure.features.includes(feature));
 assert.equal(pure.camera_tested,false);
 const x=await readNativeOfficial('gr3x');assert.equal(prepareNative(x,configuration,{...options,pure_isp_effects:true}).camera_model,'gr3x');
});

test('pure ISP rejects bad types and missing required native components',async()=>{
 const source=await readNativeOfficial('gr3'),c=defaultConfiguration();
 for(const pure_isp_effects of [1,'true',null])assert.throws(()=>prepareNative(source,c,{pure_isp_effects}),/ISP/);
 for(const invalid of [{film_library:false},{hdf_enabled:false},{border_enabled:false}]){
  assert.throws(()=>prepareNative(source,c,{film_library:true,live_color:true,hdf_enabled:true,border_enabled:true,pure_isp_effects:true,...invalid}));
 }
 const previewOff=prepareNative(source,c,{film_library:true,live_color:false,hdf_enabled:true,border_enabled:true,pure_isp_effects:true});
 assert.equal(previewOff.live_color,false);assert.equal(previewOff.capture_pipeline,'gr3-native-v8');
});

test('pure ISP manifest validation rejects wrong capability and untrusted assets',()=>{
 assert.doesNotThrow(()=>validatePureIspEffectsManifest({},false));
 assert.throws(()=>validatePureIspEffectsManifest({pure_isp_effects:{enabled:true}},false),/ISP/);
 for(const manifest of [{},{pure_isp_effects:{enabled:false}},{pure_isp_effects:{enabled:true}}])
  assert.throws(()=>validatePureIspEffectsManifest(manifest,true,Buffer.alloc(4096)),/ISP/);
});

test('CLI propagates pure ISP through normal precheck and audited generation',()=>{
 const source=readFileSync(new URL('../scripts/export_gr3_m10v_native.mjs',import.meta.url),'utf8');
 assert.match(source,/--pure-isp-effects/);
 assert.match(source,/prepareNative\(/);assert.match(source,/generateNative\(/);
});

test('trusted runtime modulation bytes and closed patch inventory survive readback',()=>{
 const directory=mkdtempSync(path.join(os.tmpdir(),'m10v-isp-assets-'));
 try{
  const python=process.env.M10V_PYTHON||(existsSync(new URL('../.venv/bin/python',import.meta.url))?new URL('../.venv/bin/python',import.meta.url).pathname:'python3');
  execFileSync(python,['-c','from scripts.build_gr3_isp_effect_textures import build_resources,pack_runtime_resources; import sys; from pathlib import Path; p=Path(sys.argv[1]); a,b=build_resources(p/"full",seed=20261031);pack_runtime_resources(a,p/"runtime")',directory],{cwd:new URL('..',import.meta.url)});
  const assets=JSON.parse(readFileSync(path.join(directory,'runtime.json'))),raw=readFileSync(path.join(directory,'runtime.raw'));
  const base=0x543ff000,runtime=Buffer.concat([Buffer.alloc(4096),raw]);
  const branch=(at,link)=>((link?0xeb000000:0xea000000)|(((base-at-8)>>2)&0xffffff))>>>0;
  const patches=[[0x53771620,0xe51b12d4,false],[0x5367adac,0xe50be650,false],[0x5367ae14,0xeb003ec4,true],[0x5367b404,0xeb03c641,true],[0x5367b410,0xeb003c3e,true],[0x5367b41c,0xeb03c308,true],[0x535033e8,0xeb05f673,true]].map(([address,expected,link])=>({address,expected,replacement:branch(address,link)}));
  const manifest={base,camera_model:'gr3',film_library_enabled:true,hdf_enabled:true,border:{enabled:true},capture_lifecycle:{snapshot:{live_color:true},native_grain:{query_entry:base}},flags:['-DM10V_PURE_ISP_EFFECTS=1','-DM10V_ISP_EFFECTS_SHOT_OFFSET=0x5778'],pure_isp_effects:{enabled:true,recipe_bytes:0x57d8,menu_resource_ids:Array.from({length:23},(_,i)=>1163+i),runtime_assets:{base:0x54400000,bytes:raw.length,sha256:assets.blob_sha256,manifest:assets},patches}};
  assert.equal(pureIspEffectPatches(runtime,manifest).length,7);
  const original=patches[0].replacement;patches[0].replacement=branch(patches[0].address,true);
  assert.throws(()=>pureIspEffectPatches(runtime,manifest),/branch kind/);patches[0].replacement=original;
  patches.push({...patches[0]});assert.throws(()=>pureIspEffectPatches(runtime,manifest),/duplicate/);patches.pop();
  runtime[runtime.length-1]^=1;assert.throws(()=>validatePureIspEffectsManifest(manifest,true,runtime),/payload hash/);
  assert.equal(pureIspEffectSources.length,24);
  assert.equal(pureIspEffectSources.filter(name=>name==='native/gr3/m10v_isp_effect_memory.h').length,1);
  for(const name of pureIspEffectSources)assert.ok(readFileSync(new URL('../'+name,import.meta.url)).length);
 }finally{rmSync(directory,{recursive:true,force:true});}
});

test('real border component admits exactly the added Resize status helper',()=>{
 const directory=mkdtempSync(path.join(os.tmpdir(),'m10v-isp-border-'));
 try{
  const python=process.env.M10V_PYTHON||(existsSync(new URL('../.venv/bin/python',import.meta.url))?new URL('../.venv/bin/python',import.meta.url).pathname:'python3');
  execFileSync(python,['-c',`from pathlib import Path
from scripts.build_gr3_border_runtime import build,REUSED
import sys
r=Path('builds/gr3-pure-isp-feasibility-20261031/gr3-official-rtos.bin').read_bytes()
build(0x54160000,r,{n:0x540c0000+i*0x100 for i,n in enumerate(REUSED)},camera_model='gr3',enabled=True,out_dir=sys.argv[1])`,directory],{cwd:new URL('..',import.meta.url)});
  const h=JSON.parse(readFileSync(path.join(directory,'m10v-border-runtime-arm.json'))),block=readFileSync(path.join(directory,'m10v-border-runtime-arm.bin'));
  const base=0x540b6000,runtime=Buffer.alloc(h.base-base+block.length);block.copy(runtime,h.base-base);
  const callsite=base+0x1000,target=h.symbols.m10v_border_runtime_jpeg;
  h.jpeg_handoff={callsite,target,original_target:h.reused_central_symbols.m10v_capture_library};
  runtime.writeUInt32LE((0xeb000000|(((target-callsite-8)>>2)&0xffffff))>>>0,callsite-base);
  const sha=b=>createHash('sha256').update(b).digest('hex');
  const m={base,camera_model:'gr3',symbols:{...h.reused_central_symbols,...h.symbols},sources:Object.fromEntries(borderSources.map(name=>[name,sha(readFileSync(new URL('../'+name,import.meta.url)))])),border:{enabled:true,pixel_pipeline_enabled:true,hardware_component:h}};
  assert.equal(borderPatches(runtime,m).length,20);
  assert.ok(Number.isInteger(h.guard.symbols.m10v_border_effect_resize_status));
  delete h.guard.symbols.m10v_border_effect_resize_status;
  assert.throws(()=>borderPatches(runtime,m),/symbols inventory/);
 }finally{rmSync(directory,{recursive:true,force:true});}
});

test('actual pure reservation builder preserves the complete exact reset shim',()=>{
 const directory=mkdtempSync(path.join(os.tmpdir(),'m10v-isp-reservation-'));
 try{
  const python=process.env.M10V_PYTHON||(existsSync(new URL('../.venv/bin/python',import.meta.url))?new URL('../.venv/bin/python',import.meta.url).pathname:'python3');
  execFileSync(python,['-c',`from pathlib import Path
from scripts.build_gr3_isp_recipe_color import build
from scripts.build_gr3_native_grain_hooks import build as build_grain
import sys,json
p=Path(sys.argv[1]);r=Path('builds/gr3-pure-isp-feasibility-20261031/gr3-official-rtos.bin').read_bytes()
names=('m10v_library_valid','m10v_library_tables','m10v_camera_library_preview','m10v_camera_library_custom_profile','m10v_camera_library_mutation_busy','m10v_hdf_reserve','m10v_hdf_task_snapshot','m10v_hdf_settings','m10v_hdf_done','m10v_isp_effects_shot_freeze','m10v_isp_effects_shot_reserve','m10v_isp_effects_shot_read','m10v_isp_effects_pipeline_settings','m10v_isp_effects_pipeline_workspace','m10v_isp_effects_pipeline_execute')
exports={name:0x54110000+i*4 for i,name in enumerate(names)}
owner={'storage':{'color_offset':0x4a08,'color_bytes':1796,'extended_recipe_bytes':0x57d8,'stamp_offset':0x5140,'stamp_bytes':16},'patches':[{'address':0x53523e0c}]}
code,manifest=build(p,r,exports,owner,base=0x54180000,observer=False,producer_snapshot=True,native_color=True,native_grain=True,shared_hdf=True,pure_isp_effects=True)
exports.update(manifest['exports'])
build_grain(p,0x541a0000,exports,r,pure_isp_effects=True)
build_grain(p/'append',0x541a0000,exports,r,appended_slots=True,pure_isp_effects=True)
(p/'exports.json').write_text(json.dumps(exports))`,directory],{cwd:new URL('..',import.meta.url)});
  const h=JSON.parse(readFileSync(path.join(directory,'isp-recipe-color.json'))),block=readFileSync(path.join(directory,'isp-recipe-color.bin'));
  const g=JSON.parse(readFileSync(path.join(directory,'native-grain-hooks.json'))),grain=readFileSync(path.join(directory,'native-grain-hooks.bin'));
  const m={base:0x54100000,symbols:JSON.parse(readFileSync(path.join(directory,'exports.json'))),pure_isp_effects:{enabled:true},capture_lifecycle:{native_grain:g}};
  const ga=JSON.parse(readFileSync(path.join(directory,'append/native-grain-hooks.json'))),appended=readFileSync(path.join(directory,'append/native-grain-hooks.bin'));
  const runtime=Buffer.alloc(g.base-m.base+Math.max(grain.length,appended.length));block.copy(runtime,h.base-m.base);grain.copy(runtime,g.base-m.base);
  for(const row of h.patches.slice(2,4))assert.doesNotThrow(()=>auditPureIspReservationShim(runtime,m,row));
  assert.doesNotThrow(()=>auditPureIspCaptureWrappers(runtime,m));
  const queryByte=g.query_entry-m.base+40,original=runtime[queryByte];runtime[queryByte]^=4;
  assert.throws(()=>auditPureIspCaptureWrappers(runtime,m),/capture wrapper instruction/);runtime[queryByte]=original;
  appended.copy(runtime,ga.base-m.base);m.appended_slots=true;m.capture_lifecycle.native_grain=ga;
  assert.doesNotThrow(()=>auditPureIspCaptureWrappers(runtime,m));
  const row=h.patches[2];runtime[row.entry-m.base+24]^=4;
  assert.throws(()=>auditPureIspReservationShim(runtime,m,row),/wrapper instruction/);
 }finally{rmSync(directory,{recursive:true,force:true});}
});
