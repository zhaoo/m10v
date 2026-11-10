import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import * as native from './gr3-native-library.mjs';
const {prepareNative,generateNative}=native;
import {defaultConfiguration} from '../web/gr3/native-library-state.mjs';
const source=readFileSync(new URL('../bin/fwdc239b-gr3-official.bin',import.meta.url));
const identity={buildId:'11'.repeat(32),catalogHash:'22'.repeat(32),rendererHash:'33'.repeat(32)};
const options={pure_isp_effects:true,hdf_enabled:true,border_enabled:true,companion_identity:identity};
test('torn overlay is an explicit GR III pure ISP option bound to the accepted plan',async()=>{
 const c=defaultConfiguration(),off=prepareNative(source,c,options),on=prepareNative(source,c,{...options,torn_overlay:true});
 assert.equal(off.torn_overlay,false);assert.equal(on.torn_overlay,true);
 assert(on.features.includes('tornOverlay'));assert(!off.features.includes('tornOverlay'));
 assert.notEqual(on.configuration_sha256,off.configuration_sha256);
 await assert.rejects(()=>generateNative(source,c,off.configuration_sha256,{...options,torn_overlay:true}),/变化/);
 assert.throws(()=>prepareNative(source,c,{...options,torn_overlay:1}),/撕纸/);
 assert.throws(()=>prepareNative(source,c,{...options,pure_isp_effects:false,torn_overlay:true}),/撕纸/);
 assert.throws(()=>prepareNative(source,c,{...options,companion_identity:undefined,torn_overlay:true}),/撕纸/);
 const x=readFileSync(new URL('../bin/fwdc243b-gr3x-official.bin',import.meta.url));
 assert.throws(()=>prepareNative(x,c,{...options,torn_overlay:true}),/撕纸/);
});
test('a requested torn overlay cannot pass a missing or software manifest gate',()=>{
 assert.equal(typeof native.validateTornOverlayManifest,'function');
 const {validateTornOverlayManifest}=native;
 assert.throws(()=>validateTornOverlayManifest({},true),/撕纸/);
 for(const patch of [{cpu_pixel_processing:true},{owner_bytes:0x6d00},{recipe_bytes:0x57d8},{camera_model:'gr3x'},{backend:'CPU'}]){
  const m={enabled:true,camera_model:'gr3',backend:'native-IIP',cpu_pixel_processing:false,owner_offset:0x6d00,owner_bytes:0x6e00,shot_offset:0x57d8,shot_bytes:32,recipe_bytes:0x57f8,...patch};
  assert.throws(()=>validateTornOverlayManifest({torn_overlay:m},true),/撕纸/);
 }
 assert.doesNotThrow(()=>validateTornOverlayManifest({},false));
});
