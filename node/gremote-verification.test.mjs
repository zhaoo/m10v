import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash,webcrypto} from 'node:crypto';
import {readGRemotePackageSafety,verifyGRemotePackageBlob} from '../web/gr3/gremote-verification.mjs';

if(!globalThis.crypto?.subtle)Object.defineProperty(globalThis,'crypto',{value:webcrypto,configurable:true});
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const sourceSha256='d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4',configurationSha256='b'.repeat(64);
const firmwareBytes=new TextEncoder().encode('original verified firmware bytes'),zipBytes=new TextEncoder().encode('PK packaged service and firmware');
const identity={buildId:'1'.repeat(64),catalogHash:'2'.repeat(64),rendererHash:'3'.repeat(64)};
const firmware={schema:'m10v-web-firmware-safety/v1',status:'offline_verified_camera_unverified',artifact_kind:'firmware',download_allowed:true,installation_allowed:false,camera_tested:false,model:'gr3',public_version:'2.10',filename:'fwdc239b.bin',source_sha256:sourceSha256,configuration_sha256:configurationSha256,candidate_sha256:hash(firmwareBytes),candidate_bytes:firmwareBytes.length,checks:{pinned_source:true,camera_declaration:true,strict_decode:true,receipt_binding:true,exact_rebuild:true}};
const audit={schema:'m10v-gremote-delivery-safety/v1',status:'offline_verified_camera_unverified',artifact_kind:'gremote_connection_package',download_allowed:true,installation_allowed:false,camera_tested:false,model:'gr3',public_version:'2.10',filename:'m10v-gr3-gremote.zip',candidate_sha256:hash(zipBytes),candidate_bytes:zipBytes.length,firmware,service_sha256:'4'.repeat(64),companion_identity:identity,pairing_policy:'camera-hotspot-per-boot',apk_included:false,film_pack_included:true,checks:{firmware_proof:true,runtime_binding:true,independent_service_build:true,elf_and_pairing:true,archive_hashes:true}};
const receipt={model:'GR III',camera_model:'gr3',public_version:'2.10',filename:'fwdc239b.bin',source_sha256:sourceSha256,configuration_sha256:configurationSha256,candidate_sha256:firmware.candidate_sha256,candidate_bytes:firmware.candidate_bytes,companion_identity:identity,safety:firmware};
const options=(changes={})=>({audit:structuredClone(audit),receipt:structuredClone(receipt),sourceSha256,configurationSha256,model:'gr3',filename:'m10v-gr3-gremote.zip',...changes});
const blob=()=>new Blob([zipBytes]);
const response=value=>new Response('',{headers:value===undefined?{}:{'X-M10V-GRemote-Package-Receipt':value}});
const encoded=value=>Buffer.from(JSON.stringify(value)).toString('base64');

test('reads package safety as strict base64 UTF-8 with bounded headers',()=>{
 const expected={...audit,note:'离线通过，真机尚未验收'};
 assert.deepEqual(readGRemotePackageSafety(response(encoded(expected))),expected);
 for(const value of [undefined,'','%%%bad','A===',encoded(null),encoded([]),encoded(3),Buffer.from('bad json').toString('base64'),Buffer.from([0xff]).toString('base64'),'A'.repeat(256*1024+4)])assert.throws(()=>readGRemotePackageSafety(response(value)),/GRemote|安全|验证/);
});

test('verifies ZIP digest while binding firmware receipt to nested firmware evidence',async()=>{
 const args=options(),original=structuredClone(args);
 assert.equal(await verifyGRemotePackageBlob(blob(),args),args.audit);
 assert.deepEqual(args,original);
 assert.notEqual(args.audit.candidate_sha256,args.receipt.candidate_sha256);
 assert.equal(args.audit.installation_allowed,false);assert.equal(args.audit.camera_tested,false);
});

test('requires all package declarations and each independent package check',async()=>{
 for(const [field,wrong] of [['schema','other'],['status','camera_passed'],['artifact_kind','firmware'],['download_allowed',false],['installation_allowed',true],['camera_tested',true],['pairing_policy','shared'],['apk_included',true],['film_pack_included','true'],['service_sha256','bad']]){
  const changed=structuredClone(audit);changed[field]=wrong;
  await assert.rejects(verifyGRemotePackageBlob(blob(),options({audit:changed})),/GRemote|安全|验证/);
  delete changed[field];await assert.rejects(verifyGRemotePackageBlob(blob(),options({audit:changed})),/GRemote|安全|验证/);
 }
 for(const key of Object.keys(audit.checks))for(const wrong of [undefined,false,'true'])await assert.rejects(verifyGRemotePackageBlob(blob(),options({audit:{...audit,checks:{...audit.checks,[key]:wrong}}})),/GRemote|安全|验证/);
});

test('rejects changed source, configuration, model, version and package filename before reading ZIP',async()=>{
 for(const changed of [{sourceSha256:'e'.repeat(64)},{configurationSha256:'e'.repeat(64)},{model:'gr3x'},{filename:'fwdc239b.bin'},{filename:'../m10v-gr3-gremote.zip'}])await assert.rejects(verifyGRemotePackageBlob(blob(),options(changed)),/GRemote|安全|验证/);
 for(const [field,value] of [['model','gr3x'],['public_version','2.20'],['filename','other.zip']])await assert.rejects(verifyGRemotePackageBlob(blob(),options({audit:{...audit,[field]:value}})),/GRemote|安全|验证/);
 const changed=structuredClone(audit);changed.firmware.source_sha256='e'.repeat(64);
 const wrongReceipt={...receipt,source_sha256:'e'.repeat(64),safety:changed.firmware};
 await assert.rejects(verifyGRemotePackageBlob(blob(),options({audit:changed,receipt:wrongReceipt,sourceSha256:'e'.repeat(64)})),/GRemote|安全|验证/);
});

test('nested firmware must carry exact model, version, source and all five offline checks',async()=>{
 for(const [field,wrong] of [['schema','other'],['status','camera_passed'],['artifact_kind','official_backup'],['download_allowed',false],['installation_allowed',true],['camera_tested',true],['model','gr3x'],['public_version','2.20'],['filename','fwdc243b.bin'],['configuration_sha256','e'.repeat(64)],['candidate_sha256','bad'],['candidate_bytes',0]]){
  const changed=structuredClone(audit);changed.firmware[field]=wrong;
  await assert.rejects(verifyGRemotePackageBlob(blob(),options({audit:changed})),/GRemote|安全|验证/);
 }
 for(const key of Object.keys(firmware.checks)){
  const changed=structuredClone(audit);delete changed.firmware.checks[key];
  await assert.rejects(verifyGRemotePackageBlob(blob(),options({audit:changed})),/GRemote|安全|验证/);
 }
});

test('requires original firmware receipt digests, exact identity and unverified receipt safety',async()=>{
 for(const value of [undefined,null,{},[],3])await assert.rejects(verifyGRemotePackageBlob(blob(),options({receipt:value})),/GRemote|安全|验证/);
 for(const [field,wrong] of [['source_sha256','e'.repeat(64)],['configuration_sha256','e'.repeat(64)],['candidate_sha256',audit.candidate_sha256],['candidate_bytes',firmware.candidate_bytes+1],['model','GR IIIx'],['camera_model','gr3x'],['public_version','2.20'],['filename','fwdc243b.bin']]){
  const changed=structuredClone(receipt);changed[field]=wrong;
  await assert.rejects(verifyGRemotePackageBlob(blob(),options({receipt:changed})),/GRemote|安全|验证/);
  delete changed[field];await assert.rejects(verifyGRemotePackageBlob(blob(),options({receipt:changed})),/GRemote|安全|验证/);
 }
 for(const change of [{buildId:'e'.repeat(64)},{catalogHash:'0'.repeat(64)},{rendererHash:'bad'},{extra:'e'.repeat(64)}])await assert.rejects(verifyGRemotePackageBlob(blob(),options({receipt:{...receipt,companion_identity:{...identity,...change}}})),/GRemote|安全|验证/);
 for(const change of [{camera_tested:true},{installation_allowed:true},{candidate_sha256:'e'.repeat(64)}])await assert.rejects(verifyGRemotePackageBlob(blob(),options({receipt:{...receipt,safety:{...firmware,...change}}})),/GRemote|安全|验证/);
});

test('rejects modified ZIP bytes, truncation, byte counts and invalid payloads',async()=>{
 const changed=zipBytes.slice();changed[2]^=1;
 for(const value of [new Blob([changed]),new Blob([zipBytes.slice(1)]),new Blob([]),undefined,zipBytes,{}])await assert.rejects(verifyGRemotePackageBlob(value,options()),/GRemote|安全|验证|摘要|字节|Blob/);
 for(const count of [undefined,0,-1,1.5,String(zipBytes.length),zipBytes.length+1])await assert.rejects(verifyGRemotePackageBlob(blob(),options({audit:{...audit,candidate_bytes:count}})),/GRemote|安全|验证|字节/);
});

test('rejects ZIPs larger than 70 MiB before arrayBuffer and unavailable WebCrypto',async()=>{
 let read=false;
 class Oversized extends Blob{get size(){return 70*1024*1024+1;}async arrayBuffer(){read=true;throw Error('must not allocate');}}
 const oversized=new Oversized();
 await assert.rejects(verifyGRemotePackageBlob(oversized,options({audit:{...audit,candidate_bytes:oversized.size}})),/70|大小|上限/);
 assert.equal(read,false);
 const descriptor=Object.getOwnPropertyDescriptor(globalThis,'crypto');
 try{Object.defineProperty(globalThis,'crypto',{value:undefined,configurable:true});await assert.rejects(verifyGRemotePackageBlob(blob(),options()),/SHA|浏览器|安全/);}
 finally{Object.defineProperty(globalThis,'crypto',descriptor);}
});
