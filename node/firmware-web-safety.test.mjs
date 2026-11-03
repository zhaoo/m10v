import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {decodeFrameMap,repackWithTarget,sum32} from './gr3-frames.mjs';
import {createBackup} from './backup.mjs';
import {checkWebBuild,verifyWebFirmware,verifyWebBackup,requireWebDownload,acceptVerifiedWorkerResult} from './firmware-web-safety.mjs';
const file=new URL('../bin/fwdc239b-gr3-official.bin',import.meta.url),available=existsSync(file);
const camera={model:'gr3',version:'2.10',origin:'official'},digest=b=>createHash('sha256').update(b).digest('hex');
const config='a'.repeat(64);
function fixture(){
 const source=readFileSync(file),d=Buffer.from(decodeFrameMap(source).decoded);d[0x10870+0x10000]^=1;
 d.writeUInt32LE(0,d.length-4);d.writeUInt32LE(-sum32(d)>>>0,d.length-4);
 const candidate=repackWithTarget(source,d).candidate;
 return {source,candidate,camera,filename:'fwdc239b.bin',configurationSha256:config,
  receipt:{source_sha256:digest(source),candidate_sha256:digest(candidate),candidate_bytes:candidate.length,configuration_sha256:config},
  rebuild:async()=>Buffer.from(candidate)};
}
test('pre-generation gate rejects missing camera, unknown provenance and version spoofing',{skip:!available},()=>{
 const source=readFileSync(file);
 for(const c of [undefined,{...camera,version:'2.20'},{...camera,origin:'third-party'},{...camera,model:'gr3x'},{...camera,origin:'m10v-verified'}])
  assert.throws(()=>checkWebBuild(source,c),/机身|来源|M10V|版本|型号/);
 assert.equal(checkWebBuild(source,camera).public_version,'2.10');
 assert.throws(()=>checkWebBuild(source,camera,{version_unlock:{enabled:true}}),/版本/);
});
test('download gate refuses hand-made audit and mutated bytes after verification',{skip:!available},async()=>{
 const input=fixture(),audit=await verifyWebFirmware(input);
 assert.equal(audit.download_allowed,true);assert.equal(audit.installation_allowed,false);
 assert.equal(requireWebDownload(input.candidate,audit),audit);
 assert.throws(()=>requireWebDownload(input.candidate,{...audit}),/校验/);
 const changed=Buffer.from(input.candidate);changed[200]^=1;
 assert.throws(()=>requireWebDownload(changed,audit),/校验/);
});
test('strict reconstruction and receipt binding reject repaired evidence',{skip:!available},async()=>{
 const input=fixture();
 await assert.rejects(()=>verifyWebFirmware({...input,rebuild:async()=>input.source}),/重建/);
 await assert.rejects(()=>verifyWebFirmware({...input,receipt:{...input.receipt,configuration_sha256:'f'.repeat(64)}}),/回执|配置/);
 const controller=new AbortController();controller.abort();
 await assert.rejects(()=>verifyWebFirmware({...input,signal:controller.signal}),{name:'AbortError'});
});
test('official backup is bound to its exact pinned original and egress digest',{skip:!available},()=>{
 const source=readFileSync(file),candidate=createBackup(source),audit=verifyWebBackup({source,candidate,camera});
 assert.equal(audit.artifact_kind,'official_backup');assert.equal(requireWebDownload(candidate,audit),audit);
 const wrong=Buffer.from(candidate);wrong[100]^=1;
 assert.throws(()=>verifyWebBackup({source,candidate:wrong,camera}));
});
test('worker result must rebind to the parent source, config and actual bytes',{skip:!available},async()=>{
 const input=fixture(),audit=await verifyWebFirmware(input),result={candidate:input.candidate,filename:input.filename,audit:structuredClone(audit)};
 const rebound=acceptVerifiedWorkerResult(input.source,camera,result,config);
 assert.equal(requireWebDownload(rebound.candidate,rebound.audit),rebound.audit);
 assert.throws(()=>acceptVerifiedWorkerResult(input.source,camera,result,'b'.repeat(64)),/校验/);
 assert.throws(()=>acceptVerifiedWorkerResult(input.source,camera,{...result,audit:{...result.audit,checks:{...result.audit.checks,exact_rebuild:false}}},config),/校验/);
});
