import test from 'node:test';import assert from 'node:assert/strict';import vm from 'node:vm';import {readFileSync} from 'node:fs';import {unwrapFirmwareDownload} from '../web/gr3/firmware-download.mjs';
const src=readFileSync(new URL('../web/gr3/studio.js',import.meta.url),'utf8');
const method=src.slice(src.indexOf('async function api('),src.indexOf('function selection()'));
test('studio requests body receipts and exposes HTML gateway failures with status',async()=>{
 for(const status of [502,504]){
  let options;const context=vm.createContext({gr4Workbench:false,state:{token:'test'},unwrapFirmwareDownload,fetch:async(p,o)=>{options=o;return new Response('<html>Bad Gateway</html>',{status});}});vm.runInContext(method,context);
  await assert.rejects(()=>context.api('/api/projects/id/native-library/build'),new RegExp('HTTP '+status));assert.equal(options.headers.Accept,'multipart/form-data');
 }
});
test('studio preserves backend errors and does not negotiate binary transport for GR IV',async()=>{
 let options;const context=vm.createContext({gr4Workbench:true,state:{token:'test'},unwrapFirmwareDownload,fetch:async(p,o)=>{options=o;return new Response(JSON.stringify({error:'另一个固件正在构建'}),{status:400});}});vm.runInContext(method,context);
 await assert.rejects(()=>context.api('/api/unmatched'),/另一个固件正在构建/);assert.equal(options.headers.Accept,undefined);
});
