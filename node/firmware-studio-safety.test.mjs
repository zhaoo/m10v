import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {createHash,webcrypto} from 'node:crypto';
import {verifyFirmwareBlob} from '../web/gr3/firmware-verification.mjs';
import {mountBuildCompletion} from '../web/gr3/full-library.mjs';
if(!globalThis.crypto?.subtle)Object.defineProperty(globalThis,'crypto',{value:webcrypto,configurable:true});
const bytes=Buffer.from('firmware download bytes'),sha=createHash('sha256').update(bytes).digest('hex');
const verification={sourceSha256:'a'.repeat(64),configurationSha256:'b'.repeat(64),model:'gr3',filename:'fwdc239b.bin',
 audit:{schema:'m10v-web-firmware-safety/v1',status:'offline_verified_camera_unverified',artifact_kind:'firmware',download_allowed:true,installation_allowed:false,camera_tested:false,
 source_sha256:'a'.repeat(64),configuration_sha256:'b'.repeat(64),model:'gr3',filename:'fwdc239b.bin',candidate_bytes:bytes.length,candidate_sha256:sha,
 checks:{pinned_source:true,camera_declaration:true,strict_decode:true,receipt_binding:true,exact_rebuild:true}}};
test('real studio download creates no URL or anchor until all browser checks pass',async()=>{
 const source=readFileSync(new URL('../web/gr3/studio.js',import.meta.url),'utf8');
 const block=source.slice(source.indexOf('async function download('),source.indexOf('async function prepare('));
 let clicks=0,urls=0;
 const context=vm.createContext({verifyFirmwareBlob,URL:{createObjectURL(){urls++;return 'blob:test';},revokeObjectURL(){}},document:{createElement:()=>({click(){clicks++;}})},setTimeout(){},Error});
 vm.runInContext(block,context);
 await assert.rejects(()=>context.download(new Response(bytes),'fwdc239b.bin'),/校验|验证/);
 await assert.rejects(()=>context.download(new Response(Buffer.from('altered')),'fwdc239b.bin',verification),/验证/);
 await assert.rejects(()=>context.download(new Response(bytes),'fwdc239b.bin',verification,()=>false),/变化|取消/);
 assert.equal(clicks,0);assert.equal(urls,0);
 await context.download(new Response(bytes),'fwdc239b.bin',verification);
 assert.equal(clicks,1);assert.equal(urls,1);
});
test('completion re-download verifies its stored Blob again and blocks corrupt or missing evidence',async()=>{
 const nodes=new Map(),node=selector=>{if(!nodes.has(selector))nodes.set(selector,{hidden:false,disabled:false,textContent:''});return nodes.get(selector);};
 const saved={window:globalThis.window,document:globalThis.document,timeout:globalThis.setTimeout,create:URL.createObjectURL,revoke:URL.revokeObjectURL};let clicks=0;
 globalThis.window={addEventListener(){}};globalThis.document={createElement:()=>({click(){clicks++;}})};
 globalThis.setTimeout=()=>0;URL.createObjectURL=()=> 'blob:test';URL.revokeObjectURL=()=>{};
 try{
  const root={querySelector:node},completion=mountBuildCompletion(root,{api:async()=>{throw Error('not used');}});
  const value={firmwareBlob:new Blob([bytes]),filename:'fwdc239b.bin',model:'gr3',catalog:[],filmLibrary:false,record:{},verification};
  completion.show({...value,verification:undefined});await node('[data-firmware-download]').onclick();assert.equal(clicks,0);
  completion.show({...value,firmwareBlob:new Blob(['bad'])});await node('[data-firmware-download]').onclick();assert.equal(clicks,0);
  completion.show(value);await node('[data-firmware-download]').onclick();assert.equal(clicks,1);
  await node('[data-firmware-download]').onclick();assert.equal(clicks,2);
 }finally{globalThis.window=saved.window;globalThis.document=saved.document;globalThis.setTimeout=saved.timeout;URL.createObjectURL=saved.create;URL.revokeObjectURL=saved.revoke;}
});
