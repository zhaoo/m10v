import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {sendFirmwareDownload} from './firmware-download.mjs';
import {unwrapFirmwareDownload} from '../web/gr3/firmware-download.mjs';

// A real, size-limited HTTP client must receive an unchanged BIN and the complete
// audit record even when that record alone exceeds a proxy's header budget.
test('large firmware receipts survive an 8 KiB response-header limit',async()=>{
 const candidate=Buffer.from([0,255,1,13,10,42]);
 const record={candidate_sha256:'a'.repeat(64),configuration:{slots:Array.from({length:10},()=>({film:33}))},audit:'x'.repeat(40000)};
 const encoded=Buffer.from(JSON.stringify(record)).toString('base64');
 const server=http.createServer((req,res)=>{res.setHeader('X-M10V-Native-Receipt',encoded);res.setHeader('X-M10V-Build-Source','source');sendFirmwareDownload(req,res,candidate,'fwdc243b.bin');});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 try{
  const raw=await new Promise((resolve,reject)=>{const req=http.get(`http://127.0.0.1:${server.address().port}`,{maxHeaderSize:8192,headers:{Accept:'multipart/form-data'}},res=>{const chunks=[];res.on('data',c=>chunks.push(c));res.on('end',()=>resolve(new Response(Buffer.concat(chunks),{headers:res.headers})));});req.on('error',reject);});
  assert.equal(raw.headers.get('X-M10V-Native-Receipt'),null);
  const result=await unwrapFirmwareDownload(raw);
  assert.deepEqual(Buffer.from(await result.arrayBuffer()),candidate);
  assert.deepEqual(JSON.parse(Buffer.from(result.headers.get('X-M10V-Native-Receipt'),'base64')),record);
  assert.equal(result.headers.get('X-M10V-Build-Source'),'source');
  assert.match(result.headers.get('Content-Disposition'),/fwdc243b.bin/);
 }finally{await new Promise(r=>server.close(r));}
});
test('ordinary binary responses remain readable by existing download clients',async()=>{
 const r=new Response('binary',{headers:{'Content-Type':'application/octet-stream','X-M10V-Native-Receipt':'old'}});
 assert.equal(await unwrapFirmwareDownload(r),r);
});
test('malformed multipart downloads cannot be saved as firmware',async()=>{
 const form=new FormData();form.append('metadata',JSON.stringify({headers:{}}));
 await assert.rejects(()=>unwrapFirmwareDownload(new Response(form)),/下载/);
});
test('cancelled body downloads preserve AbortError for the existing cancel UI',async()=>{
 const stream=new ReadableStream({start(controller){controller.error(new DOMException('cancelled','AbortError'));}});
 const response=new Response(stream,{headers:{'Content-Type':'multipart/form-data; boundary=cancelled'}});
 await assert.rejects(()=>unwrapFirmwareDownload(response),{name:'AbortError'});
});
