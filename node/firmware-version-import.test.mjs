import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {mkdtemp,rm} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {inspectModelFirmware} from './model-firmware.mjs';
import {resolveBuildSource} from './firmware-build-source.mjs';
import {Store} from './storage.mjs';
import {createServer} from './server.mjs';
import {defaultConfiguration} from '../web/gr3/native-library-state.mjs';
import {prepareNative,generateNative} from './gr3-native-library.mjs';
import {createBackup,restoreBytes} from './backup.mjs';
import {inspectOfficial,inspectFirmwareImport} from './firmware.mjs';
import {decodeFrameMap,repackWithTarget,sum32} from './gr3-frames.mjs';
import {applyPatchPlan} from './gr3-patch-plan.mjs';
import {createStockEdits} from './gr3-stock-presets.mjs';
import {portNativeToGr3x} from './gr3x-native-port.mjs';
const stock=model=>readFileSync(new URL(`../bin/fwdc${model==='gr3'?239:243}b-${model}-official.bin`,import.meta.url));
const repair=b=>{b.writeUInt32LE(0,b.length-4);b.writeUInt32LE(-sum32(b)>>>0,b.length-4);};
// A future public version with independently repaired RTOS/CPU/outer copies.
function future(model,version,changeCode=false){
 const original=stock(model),d=Buffer.from(decodeFrameMap(original).decoded);let at=0,cpu;
 while(at<d.length-4){const name=d.toString('ascii',at,at+8).split('\0')[0];if(name==='RTOS'){d.writeUInt32BE(version,at+16+0x2038);if(changeCode)d[at+16+0x3000]^=1;}if(name==='CPU'){cpu=at+16;break;}at+=16+d.readUInt32LE(at+12);}
 d.writeUInt32BE(version,cpu+0x90);d.writeUInt32BE(0,cpu+0x7c);let total=0;for(let p=cpu;p<cpu+131072;p+=4)total=(total+d.readUInt32BE(p))>>>0;d.writeUInt32BE(-total>>>0,cpu+0x7c);repair(d);
 const b=repackWithTarget(original,d).candidate;b.writeUInt32BE(version,0x38);b.writeUInt32BE(version,0x50);repair(b);return b;
}
for(const [model,version,publicVersion,target] of [['gr3',0x021e0304,'2.30','2.30.4.4'],['gr3x',0x01500304,'1.80','1.80.4.4']]){
 test(`${model} imports an unseen version and length without substituting an older executable`,async()=>{
  const uploaded=future(model,version),report=await inspectModelFirmware(uploaded);
  assert.equal(report.public_version,publicVersion);assert.equal(report.workspace_url,'/gr3/');assert.equal(report.proof.identity,false);assert.equal(report.proof.container,true);
  assert.throws(()=>inspectOfficial(uploaded));
  assert.ok(restoreBytes(createBackup(uploaded)).equals(uploaded));
  const resolved=await resolveBuildSource(uploaded);assert.ok(resolved.source.equals(uploaded));assert.equal(resolved.report.build_source.normalized,false);
  assert.equal(resolved.report.build_source.update_compatibility,undefined);
  const folder=await mkdtemp(path.join(os.tmpdir(),'m10v-version-import-'));try{const store=new Store(folder);const record=await store.importOfficial(uploaded);assert.ok((await store.readOriginal(record.id)).equals(uploaded));}finally{await rm(folder,{recursive:true,force:true});}
  const plan=prepareNative(resolved.source,defaultConfiguration());
  assert.equal(plan.public_version,publicVersion);assert.equal(plan.source_sha256,report.sha256);
  if(model==='gr3')assert.throws(()=>prepareNative(resolved.source,defaultConfiguration(),{extensions:{aspect:true,level:false,negativeGrain:false,rawNr:{mode:'stock'}}}),/组合扩展/);
  assert.throws(()=>prepareNative(resolved.source,defaultConfiguration(),{version_unlock:{enabled:true,mode:'dsp-package-only'}}),/旧版版本适配/);
  const built=await generateNative(resolved.source,defaultConfiguration(),plan.configuration_sha256);
  const final=await inspectModelFirmware(built.candidate);
  assert.equal(final.internal_version,report.internal_version);assert.equal(final.model,report.model);
  assert.equal(built.receipt.source_sha256,report.sha256);
 });
}
for(const [env,model,version,target] of [['M10V_GR3_220_FIXTURE','GR III','2.20','2.20.21.28'],['M10V_GR3X_170_FIXTURE','GR IIIx','1.70','1.70.21.18']])test(`${model} latest real input imports and resolves a compatible package`,{skip:!process.env[env]},async()=>{
 const b=readFileSync(process.env[env]),report=await inspectModelFirmware(b);assert.equal(report.model,model);assert.equal(report.public_version,version);
 const resolved=await resolveBuildSource(b);assert.equal(resolved.report.build_source.update_compatibility,undefined);
 assert.ok(resolved.source.equals(b));assert.equal(sum32(resolved.source),0);
});
test('unseen versions still reject corruption, wrong models, inconsistent copies and allocation bombs',async()=>{
 const good=future('gr3',0x021e0304);
 for(const change of [b=>{b[200]^=1;},b=>{b.writeUInt32LE(999,48);repair(b);},b=>{b.writeUInt32BE(0x021f0304,0x38);repair(b);},b=>{b.writeUInt32LE(0xfffffffc,b.length-8);repair(b);}]){const b=Buffer.from(good);change(b);await assert.rejects(()=>inspectModelFirmware(b));}
});
test('a structurally valid unseen source with changed executable bytes is rejected before native build',()=>{
 const source=future('gr3',0x021e0304,true);
 assert.throws(()=>prepareNative(source,defaultConfiguration()),error=>error.code==='M10V_NATIVE_ABI_NOT_PORTED');
});
test('native ABI compatibility does not ignore unrelated outer header fields',()=>{
 const source=future('gr3',0x021e0304);source[0x40]^=1;repair(source);
 assert.throws(()=>prepareNative(source,defaultConfiguration()),error=>error.code==='M10V_NATIVE_ABI_NOT_PORTED');
});
test('IIIx metadata versions may share service bytes or the whole version word with the GR III reference',()=>{
 const gr3=stock('gr3');
 const candidate=applyPatchPlan(gr3,gr3,createStockEdits(gr3,{presets:[{slot:2,name:'Clear'}]})).candidate;
 for(const version of [0x0150151b,0x020a151b]){
  const uploaded=future('gr3x',version),ported=portNativeToGr3x(gr3,uploaded,candidate);
  assert.equal(ported.candidate.readUInt32BE(0x38),version);
  assert.equal(ported.candidate.readUInt32BE(0x50),version);
  assert.equal(inspectFirmwareImport(ported.candidate).internal_version,inspectFirmwareImport(uploaded).internal_version);
 }
});

for(const [env,model,version,target] of [['M10V_GR3_220_FIXTURE','GR III','2.20','2.20.21.28'],['M10V_GR3X_170_FIXTURE','GR IIIx','1.70','1.70.21.18']])test(`${model} real upload keeps backup and exports through HTTP`,{skip:!process.env[env]},async()=>{
 const b=readFileSync(process.env[env]),folder=await mkdtemp(path.join(os.tmpdir(),'m10v-upload-http-'));
 const store=new Store(folder),server=createServer(store);await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const base=`http://127.0.0.1:${server.address().port}`;
 try{
  const token=(await(await fetch(base+'/api/status')).json()).session_token;
  const post=(url,body)=>fetch(base+url,{method:'POST',headers:{'X-M10V-Token':token},body:Buffer.isBuffer(body)?body:JSON.stringify(body)});
  const imported=await post('/api/import',b);assert.equal(imported.status,200,await imported.clone().text());
  const report=await imported.json(),route=`/api/projects/${report.project_id}`;
  assert.equal(report.model,model);assert.equal(report.public_version,version);assert.equal(report.build_source.update_compatibility,undefined);
  const backup=await post(route+'/backup',{});assert.equal(backup.status,200,await backup.clone().text());assert.ok(restoreBytes(Buffer.from(await backup.arrayBuffer())).equals(b));
  const prepared=await post(route+'/native-library/prepare',{configuration:defaultConfiguration()});assert.equal(prepared.status,400);assert.match((await prepared.json()).error,/原生 ABI 尚未适配/);
  const selection={variant:'street',features:['presets'],stockPresets:[{slot:2,name:'Clear'}]};
  const p=await post(route+'/edit/prepare',{selection});assert.equal(p.status,200,await p.clone().text());const plan=await p.json();
  const built=await post(route+'/edit/build',{selection,accepted_configuration_sha256:plan.configuration_sha256});assert.equal(built.status,200,await built.clone().text());
  const candidate=Buffer.from(await built.arrayBuffer()),receipt=JSON.parse(Buffer.from(built.headers.get('X-M10V-Build-Receipt'),'base64'));
  assert.equal(receipt.update_compatibility,undefined);assert.equal(receipt.build_source.imported_sha256,report.sha256);assert.equal(sum32(candidate),0);
  assert.equal((await inspectModelFirmware(candidate)).internal_version,report.internal_version);
  assert.equal(candidate.readUInt32LE(48),model==='GR III'?588:609);
 }finally{await new Promise(r=>server.close(r));await rm(folder,{recursive:true,force:true});}
});
