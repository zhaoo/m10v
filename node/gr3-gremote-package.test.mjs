import test from 'node:test';
import assert from 'node:assert/strict';
import {existsSync,readFileSync} from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {readdir} from 'node:fs/promises';
import {setTimeout as pause} from 'node:timers/promises';
import {createHash} from 'node:crypto';
const moduleFile=new URL('./gr3-gremote-package.mjs',import.meta.url);
const available=existsSync(moduleFile),hash=b=>createHash('sha256').update(b).digest('hex');
test('public GRemote package module exists',()=>assert.equal(available,true,'GRemote package boundary is missing'));
test('download requires a privately issued proof, never forged JSON',{skip:!available},async()=>{
 const {createGRemotePackage,requireGRemotePackageDownload}=await import(moduleFile);
 const bytes=Buffer.from('PK');
 assert.throws(()=>requireGRemotePackageDownload(bytes,{schema:'m10v-gremote-delivery-safety/v1',candidate_sha256:hash(bytes),download_allowed:true}),/校验/);
 await assert.rejects(()=>createGRemotePackage({candidate:bytes,filename:'fwdc239b.bin',audit:{download_allowed:true}}),/校验/);
 const controller=new AbortController();controller.abort();
 await assert.rejects(()=>createGRemotePackage({}, {signal:controller.signal}),{name:'AbortError'});
});
const native=process.env.M10V_GREMOTE_PACKAGE_NATIVE;
test('real package is proven, rejects copied audit and altered ZIP, and exposes public metadata only',{skip:!available||!native,timeout:120000},async()=>{
 const {createGRemotePackage,requireGRemotePackageDownload}=await import(moduleFile);
 const {verifyWebFirmware}=await import('./firmware-web-safety.mjs');
 const find=(...names)=>names.map(n=>path.join(native,n)).find(existsSync);
 const candidate=readFileSync(find('fwdc239b.bin','01_FIRMWARE/SD_ROOT/fwdc239b.bin'));
 const receipt=JSON.parse(readFileSync(find('M10V-build-receipt.json','evidence/firmware-receipt.json')));
 const runtimeManifest=JSON.parse(readFileSync(find('M10V-runtime-manifest.json','evidence/runtime-manifest.json')));
 const source=readFileSync(new URL('../bin/fwdc239b-gr3-official.bin',import.meta.url));
 const audit=await verifyWebFirmware({source,candidate,receipt,configurationSha256:receipt.configuration_sha256,camera:{model:'gr3',version:'2.10',origin:'official'},filename:'fwdc239b.bin',rebuild:async()=>Buffer.from(candidate)});
 const input={candidate,filename:'fwdc239b.bin',audit,receipt:{...receipt,safety:audit},runtimeManifest};
 for(const changed of [{...input,filename:'fwdc243b.bin'},{...input,receipt:{...input.receipt,model:'GR IIIx'}},{...input,runtimeManifest:{...runtimeManifest,camera_model:'gr3x'}},{...input,receipt:{...input.receipt,companion_identity:{...receipt.companion_identity,buildId:'11'.repeat(32)}}}])
  await assert.rejects(()=>createGRemotePackage(changed),/GR III|身份|identity|机型|回执/);
 const result=await createGRemotePackage(input);
 assert.equal(result.headers['Cache-Control'],'private, no-store');
 assert.equal(result.filename,'m10v-gr3-gremote.zip');assert.equal(result.audit.schema,'m10v-gremote-delivery-safety/v1');
 assert.equal(result.audit.camera_tested,false);assert.equal(result.audit.installation_allowed,false);
 assert.equal(result.audit.status,'offline_verified_camera_unverified');assert.equal(requireGRemotePackageDownload(result.candidate,result.audit),result.audit);
 assert.throws(()=>requireGRemotePackageDownload(result.candidate,{...result.audit}),/校验/);
 const changed=Buffer.from(result.candidate);changed[100]^=1;assert.throws(()=>requireGRemotePackageDownload(changed,result.audit),/校验/);
 assert.equal(result.audit.candidate_sha256,hash(result.candidate));assert.ok(!JSON.stringify(result.headers).includes('keyHex'));
 const serialized=JSON.parse(Buffer.from(result.headers['X-M10V-GRemote-Package-Receipt'],'base64').toString());
 assert.equal(serialized.candidate_sha256,hash(result.candidate));assert.equal(serialized.installation_allowed,false);
 const before=new Set(await readdir(os.tmpdir())),controller=new AbortController();
 const pending=createGRemotePackage(input,{signal:controller.signal});
 const rejected=assert.rejects(pending,{name:'AbortError'});let privateFolder;
 for(let i=0;i<100;i++){
  const names=await readdir(os.tmpdir());privateFolder=names.find(n=>n.startsWith('m10v-gremote-download-')&&!before.has(n));
  if(privateFolder){
   const contents=await readdir(path.join(os.tmpdir(),privateFolder));
   if(contents.some(n=>n.startsWith('m10v-companion-build-')))break;
  }
  await pause(10);
 }
 assert.ok(privateFolder,'real package should create its private workspace before abort');
 controller.abort();await rejected;
 assert.equal(existsSync(path.join(os.tmpdir(),privateFolder)),false,'aborting must remove firmware, pairing and compiler temporary files');
});
