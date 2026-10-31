import test from 'node:test';import assert from 'node:assert/strict';import http from 'node:http';
import {readFileSync,existsSync} from 'node:fs';import {mkdtemp,rm} from 'node:fs/promises';
import os from 'node:os';import path from 'node:path';import {createHash} from 'node:crypto';
import {createServer} from './server.mjs';import {Store} from './storage.mjs';
import {defaultConfiguration} from '../web/gr3/native-library-state.mjs';
import {unwrapFirmwareDownload} from '../web/gr3/firmware-download.mjs';
import {inspectFirmwareImport} from './firmware.mjs';

const fixture=process.env.M10V_GR3_220_FIXTURE;
test('the actual 2.20 save route accepts disabled images and downloads through an 8 KiB header client',
 {skip:!fixture||!existsSync(fixture)},async()=>{
 const folder=await mkdtemp(path.join(os.tmpdir(),'m10v-220-http-')),server=createServer(new Store(folder));
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port;
 try{
  const {session_token:token}=await(await fetch(base+'/api/status')).json();
  const post=(route,body)=>fetch(base+route,{method:'POST',headers:{'X-M10V-Token':token},body:Buffer.isBuffer(body)?body:JSON.stringify(body)});
  const original=readFileSync(fixture),imported=await post('/api/import',original);assert.equal(imported.status,200);
  const project=await imported.json(),route='/api/projects/'+project.project_id+'/native-library/';
  const input={configuration:defaultConfiguration(),film_library:true,hdf_enabled:false,power_images:{}};
  const pre=await post(route+'prepare',input);assert.equal(pre.status,200,await pre.clone().text());
  const plan=await pre.json();assert.equal(plan.ready,true);assert.equal(plan.build_source.sha256,project.sha256);
  const payload=JSON.stringify({...input,accepted_configuration_sha256:plan.configuration_sha256});
  const response=await new Promise((resolve,reject)=>{
   const req=http.request(base+route+'build',{method:'POST',maxHeaderSize:8192,headers:{Accept:'multipart/form-data','X-M10V-Token':token,'Content-Length':Buffer.byteLength(payload)}},res=>{
    const chunks=[];res.on('data',c=>chunks.push(c));res.on('end',()=>resolve(new Response(Buffer.concat(chunks),{status:res.statusCode,headers:res.headers})));res.on('error',reject);
   });req.on('error',reject);req.end(payload);
  });
  assert.equal(response.status,200,await response.clone().text());
  const download=await unwrapFirmwareDownload(response),candidate=Buffer.from(await download.arrayBuffer());
  const receipt=JSON.parse(Buffer.from(download.headers.get('X-M10V-Native-Receipt'),'base64'));
  assert.equal(receipt.source_sha256,project.sha256);
  assert.equal(receipt.candidate_sha256,createHash('sha256').update(candidate).digest('hex'));
  assert.equal(inspectFirmwareImport(candidate).internal_version,'2.20.20.28');
  assert.equal(receipt.native_target.verified,true);
 }finally{await new Promise(r=>server.close(r));await rm(folder,{recursive:true,force:true});}
});
