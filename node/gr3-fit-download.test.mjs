import test from 'node:test';
import assert from 'node:assert/strict';
let createFitApi;
try{({createFitApi}=await import('../web/gr3/fit-api.mjs'));}catch(error){if(error.code!=='ERR_MODULE_NOT_FOUND')throw error;}
test('LUT build requests body-carried receipts and restores the binary response',async()=>{
 assert.equal(typeof createFitApi,'function','LUT workbench needs the shared safe download transport');
 const bytes=new Uint8Array([0,255,13,10,7]),receipt='r'.repeat(48*1024),form=new FormData();
 form.set('metadata',JSON.stringify({headers:{'Content-Type':'application/octet-stream','Content-Length':String(bytes.length),'X-M10V-Build-Receipt':receipt}}));
 form.set('firmware',new Blob([bytes]),'fwdc239b.bin');
 let requested;
 const api=createFitApi(()=> 'local-session',async(path,options)=>{requested={path,options};return new Response(form);});
 const response=await api('/api/projects/test/edit/build',{method:'POST',body:'{}'});
 assert.equal(requested.options.headers.Accept,'multipart/form-data');
 assert.equal(requested.options.headers['X-M10V-Token'],'local-session');
 assert.equal(response.headers.get('X-M10V-Build-Receipt'),receipt);
 assert.deepEqual(new Uint8Array(await response.arrayBuffer()),bytes);
});
test('LUT fit JSON and import requests keep their ordinary transport',async()=>{
 assert.equal(typeof createFitApi,'function');let sent;
 const api=createFitApi(()=> 'local-session',async(path,options)=>{sent=options;return Response.json({choices:{}});});
 assert.deepEqual(await(await api('/api/gr3/film/fit',{method:'POST',headers:{'X-M10V-Filename':'look.cube'}})).json(),{choices:{}});
 assert.equal(sent.headers.Accept,undefined);assert.equal(sent.headers['X-M10V-Filename'],'look.cube');
});
