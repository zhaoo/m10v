// Build the actual IIIx feature bundle; independently preserve its identity/CPU.
import assert from 'node:assert/strict';
import {readNativeOfficial,prepareNative,generateNative} from '../node/gr3-native-library.mjs';
import {defaultConfiguration} from '../web/gr3/native-library-state.mjs';
import {inspectOfficial} from '../node/firmware.mjs';
import {resolveIspEffectOptions} from '../node/gr3-isp-effect-options.mjs';
const source=await readNativeOfficial('gr3x'),report=inspectOfficial(source);
assert.equal(report.model,'GR IIIx');
const config=defaultConfiguration(),options=resolveIspEffectOptions(source,{debug_mode:true,pure_isp_effects:true,hdf_enabled:true,border_enabled:true,extensions:{aspect:true,level:true,negativeGrain:true,rawNr:{mode:'off'}}},report.model);
const plan=prepareNative(source,config,options);
assert.equal(plan.filename,'fwdc243b.bin');assert.equal(plan.external_film_pack,true);
const result=await generateNative(source,config,plan.configuration_sha256,options);
assert.equal(result.receipt.model,'GR IIIx');assert.equal(result.receipt.source_sha256,report.sha256);
assert.equal(result.candidate.readUInt32LE(0x30),609);assert.equal(result.candidate.readUInt32BE(0x38),0x013c0b11);
assert.ok(result.receipt.gr3x_port);assert.equal(result.receipt.debug_mode,true);
assert.equal(result.manifest.pure_isp_effects.enabled,true);
console.log(JSON.stringify({model:report.model,source_sha256:report.sha256,candidate_sha256:result.receipt.candidate_sha256,native_export:'offline_verified',filename:plan.filename,features:plan.features,port:result.receipt.gr3x_port,camera_tested:false}));
