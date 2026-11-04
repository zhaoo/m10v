import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {decodeFrameMap,sum32} from './gr3-frames.mjs';
import {inspectFirmwareImport} from './firmware.mjs';
import {auditFlashInputs} from './gr3-flash-safety.mjs';
import {prepareNative} from './gr3-native-library.mjs';
import {defaultConfiguration} from '../web/gr3/native-library-state.mjs';

const official=new URL('../bin/fwdc239b-gr3-official.bin',import.meta.url);
const available=existsSync(official);
const base=()=>({source:readFileSync(official),camera:{model:'gr3',version:'2.10',origin:'official'}});
test('unknown source is refused before candidate processing',async()=>{
 const r=await auditFlashInputs({source:Buffer.alloc(152)});
 assert.equal(r.status,'rejected');assert.equal(r.installation_allowed,false);
 assert.match(r.reasons.join(' '),/source/i);
});
test('CLI reports absent input and invalid options as structured rejections',()=>{
 for(const args of [[],['--flash-now']]){
  const result=spawnSync(process.execPath,['scripts/check_gr3_flash_safety.mjs',...args],{encoding:'utf8'});
  assert.equal(result.status,1);const report=JSON.parse(result.stdout);
  assert.equal(report.installation_allowed,false);assert.equal(report.status,'rejected');
 }
});
test('ADJ trace requires debug mode and has its own build identity',{skip:!available},()=>{
 const source=readFileSync(official),config=defaultConfiguration('gr3');
 assert.throws(()=>prepareNative(source,config,{adj_exit_trace:true}),/ADJ/);
 const regular=prepareNative(source,config,{debug_mode:true,adj_exit_trace:false});
 const trace=prepareNative(source,config,{debug_mode:true,adj_exit_trace:true});
 assert.equal(trace.debug_log.adj_exit_trace,true);
 assert.notEqual(trace.configuration_sha256,regular.configuration_sha256);
 assert.notEqual(trace.debug_log.build_id,regular.debug_log.build_id);
});
test('a matching public version cannot authorize unknown or third party camera firmware',{skip:!available},async()=>{
 for(const origin of ['unknown','third-party',undefined]){
  const input=base();input.camera.origin=origin;
  const r=await auditFlashInputs(input);
  assert.equal(r.status,'rejected');assert.match(r.reasons.join(' '),/provenance/i);
 }
});
test('anniversary camera version is refused even with the old pinned source',{skip:!available},async()=>{
 const input=base();input.camera.version='2.20';
 const r=await auditFlashInputs(input);
 assert.equal(r.status,'rejected');assert.match(r.reasons.join(' '),/version/i);
});
test('swapped camera model and absent candidate evidence fail closed',{skip:!available},async()=>{
 let input=base();input.camera.model='gr3x';
 assert.match((await auditFlashInputs(input)).reasons.join(' '),/model/i);
 input=base();const r=await auditFlashInputs(input);
 assert.equal(r.status,'rejected');assert.match(r.reasons.join(' '),/candidate/i);
});
for(const [env,model,version] of [['M10V_GR3_220_FIXTURE','gr3','2.20'],['M10V_GR3X_170_FIXTURE','gr3x','1.70']]){
 test(`${version} official source is blocked before any rebuild`,{skip:!process.env[env]},async()=>{
  const r=await auditFlashInputs({source:readFileSync(process.env[env]),camera:{model,version,origin:'official'}});
  assert.equal(r.status,'rejected');assert.match(r.reasons.join(' '),/source/i);
 });
}
for(const [env,model,version,name] of [['M10V_GR3_SAFETY_CANDIDATE','gr3','2.10','fwdc239b.bin'],['M10V_GR3X_SAFETY_CANDIDATE','gr3x','1.60','fwdc243b.bin']]){
 test(`${model} exact reproduced candidate is offline evidence and never installation approval`,{skip:!process.env[env]},async()=>{
  const folder=process.env[env];
  const source=readFileSync(new URL(`../bin/${model==='gr3'?'fwdc239b-gr3':'fwdc243b-gr3x'}-official.bin`,import.meta.url));
  const candidate=readFileSync(`${folder}/${name}`),receipt=JSON.parse(readFileSync(`${folder}/M10V-build-receipt.json`));
  const input={source,candidate,receipt,expectedSha256:process.env[env+'_SHA256'],camera:{model,version,origin:'official'}};
  const before=Buffer.from(candidate),r=await auditFlashInputs(input);
  assert.equal(r.status,'offline_verified_camera_unverified',JSON.stringify(r));
  assert.equal(r.checks.exact_rebuild,true);assert.equal(r.installation_allowed,false);assert.equal(r.camera_tested,false);
  assert.ok(r.remaining_device_checks.length);assert.ok(candidate.equals(before));
  const missing=await auditFlashInputs({...input,receipt:undefined});assert.equal(missing.status,'rejected');
  const swapped=await auditFlashInputs({...input,expectedSha256:'0'.repeat(64)});assert.equal(swapped.status,'rejected');
  const counterfeit=await auditFlashInputs({...input,receipt:{...receipt,source_sha256:'0'.repeat(64)}});
  assert.equal(counterfeit.status,'rejected');
  if(receipt.companion_identity){
   for(const altered of [
    {...receipt,companion_identity:undefined},
    {...receipt,companion_identity:{...receipt.companion_identity,buildId:'12'.repeat(32)}},
    {...receipt,preserve_existing:false},
    {...receipt,features:receipt.features.filter(f=>f!=='companion')}
   ]){
    const rejected=await auditFlashInputs({...input,receipt:altered});
    assert.equal(rejected.status,'rejected');
    assert.match(rejected.reasons.join(' '),/companion identity|fingerprint/);
   }
  }
  if(model==='gr3'){
   // Simulate an altered RTOS instruction with all structural checksums and
   // supplied receipt/digest repaired. It must still fail exact reproduction.
   const data=Buffer.from(decodeFrameMap(candidate).decoded);data[0x10870+0x100]^=1;
   data.writeUInt32LE(0,data.length-4);data.writeUInt32LE(-sum32(data)>>>0,data.length-4);
   const chunks=[];
   for(let at=0;at<data.length;at+=0x6000){const b=data.subarray(at,at+0x6000),h=Buffer.alloc(2);h.writeUInt16BE(0x8000|b.length);chunks.push(h,b);}
   chunks.push(Buffer.alloc(2));const payload=Buffer.concat(chunks),footer=Buffer.from(candidate.subarray(-24));
   footer.writeUInt32LE(payload.length,12);footer.writeUInt32LE(0,20);
   const changed=Buffer.concat([candidate.subarray(0,128),payload,Buffer.alloc(-(128+payload.length)&3),footer]);
   changed.writeUInt32LE(-sum32(changed)>>>0,changed.length-4);
   assert.equal(inspectFirmwareImport(changed).public_version,'2.10');
   const digest=createHash('sha256').update(changed).digest('hex');
   const result=await auditFlashInputs({...input,candidate:changed,expectedSha256:digest,
    receipt:{...receipt,candidate_sha256:digest,candidate_bytes:changed.length}});
   assert.equal(result.status,'rejected');assert.match(result.reasons.join(' '),/exact rebuild mismatch/);
  }
 });
}
