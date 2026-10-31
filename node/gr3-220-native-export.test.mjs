import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
import {prepareNative,generateNative} from './gr3-native-library.mjs';
import {defaultConfiguration} from '../web/gr3/native-library-state.mjs';
import {inspectFirmwareImport} from './firmware.mjs';
import {decodeFrameMap,sum32} from './gr3-frames.mjs';
import {createHash} from 'node:crypto';
import {portNativeTarget} from './gr3-native-target.mjs';

const fixture=process.env.M10V_GR3_220_FIXTURE;
test('real GR III 2.20 saves native films on the uploaded executable and preserves component versions',
 {skip:!fixture||!existsSync(fixture)},async()=>{
  const source=readFileSync(fixture),config=defaultConfiguration();
  const plan=prepareNative(source,config);
  assert.equal(plan.ready,true);assert.equal(plan.public_version,'2.20');
  const result=await generateNative(source,config,plan.configuration_sha256);
  const {candidate,receipt,runtime,manifest}=result;
  const before=inspectFirmwareImport(source),after=inspectFirmwareImport(candidate);
  assert.equal(after.internal_version,'2.20.20.28');
  assert.ok(candidate.subarray(0,128).equals(source.subarray(0,128)));
  assert.equal(receipt.source_sha256,before.sha256);
  assert.equal(receipt.native_target.source_sha256,before.sha256);
  assert.equal(receipt.native_target.verified,true);
  assert.deepEqual(receipt.configuration,plan.configuration);
  for(const section of before.sections.filter(s=>s.name!=='RTOS'))
   assert.equal(after.sections.find(s=>s.name===section.name).sha256,section.sha256,section.name);
  assert.equal(sum32(candidate),0);assert.equal(sum32(decodeFrameMap(candidate).decoded),0);
  assert.equal(receipt.camera_tested,false);
  const runtimeHash=createHash('sha256').update(runtime).digest('hex');
  assert.equal(runtimeHash,receipt.native_target.runtime_sha256);
  assert.equal(manifest.code_sha256,runtimeHash);
  assert.equal(receipt.runtime_sha256,runtimeHash);
  assert.equal(inspectFirmwareImport(result.nativeCandidate).internal_version,'2.20.20.28');
  const reference=readFileSync(new URL('../bin/fwdc239b-gr3-official.bin',import.meta.url));
  assert.throws(()=>portNativeTarget(reference,source,result.referenceNativeCandidate,
   result.runtimeRelocations.slice(1),result.referenceManifest??manifest),/引用清单/);
 });

test('new target refuses extensions whose extra executable components lack relocation coverage',
 {skip:!fixture||!existsSync(fixture)},()=>{
  assert.throws(()=>prepareNative(readFileSync(fixture),defaultConfiguration(),{
   extensions:{aspect:true,level:false,negativeGrain:false,rawNr:{mode:'stock'}},
  }),/扩展.*尚未适配/);
  assert.throws(()=>prepareNative(readFileSync(fixture),defaultConfiguration(),{
   debug_mode:true,hdf_enabled:true,
  }),/HDF.*调试日志组合尚未适配/);
 });
