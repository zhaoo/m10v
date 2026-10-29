import test from 'node:test';import assert from 'node:assert/strict';import http from 'node:http';import {createHash} from 'node:crypto';import {readFile,mkdtemp,rm,writeFile,mkdir} from 'node:fs/promises';import os from 'node:os';import path from 'node:path';
import {createServer} from './server.mjs';import {Store} from './storage.mjs';import {defaultConfiguration} from '../web/gr3/native-library-state.mjs';import {unwrapFirmwareDownload} from '../web/gr3/firmware-download.mjs';import {inspectFirmwareImport} from './firmware.mjs';
for(const [model,env,expected] of [['gr3','M10V_GR3_220_FIXTURE','2.20.21.28'],['gr3x','M10V_GR3X_170_FIXTURE','1.70.21.18']])test(`${model} real newer input builds full native firmware through an 8 KiB header client`,{skip:!process.env[env]},async()=>{
 const dir=await mkdtemp(path.join(os.tmpdir(),'m10v-download-http-')),server=createServer(new Store(dir));await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port;
 try{
  const token=(await(await fetch(base+'/api/status')).json()).session_token;
  const post=(url,body)=>fetch(base+url,{method:'POST',headers:{'X-M10V-Token':token},body:Buffer.isBuffer(body)?body:JSON.stringify(body)});
  const imported=await post('/api/import',await readFile(process.env[env]));assert.equal(imported.status,200);const input=await imported.json(),route='/api/projects/'+input.project_id+'/native-library/';
  const body={configuration:defaultConfiguration(model),debug_mode:true,film_library:true,hdf_enabled:true,halation_enabled:true,extensions:{aspect:true,level:true,negativeGrain:true,rawNr:{mode:'off'}}};
  const pre=await post(route+'prepare',body);assert.equal(pre.status,200);const plan=await pre.json();assert.equal(plan.ready,true);
  const payload=JSON.stringify({...body,accepted_configuration_sha256:plan.configuration_sha256});
  const raw=await new Promise((resolve,reject)=>{const req=http.request(base+route+'build',{method:'POST',maxHeaderSize:8192,headers:{Accept:'multipart/form-data','X-M10V-Token':token,'Content-Length':Buffer.byteLength(payload)}},res=>{const chunks=[];res.on('data',c=>chunks.push(c));res.on('end',()=>resolve(new Response(Buffer.concat(chunks),{status:res.statusCode,headers:res.headers})));res.on('error',reject);});req.on('error',reject);req.end(payload);});
  assert.equal(raw.status,200);assert.match(raw.headers.get('Content-Type'),/^multipart\/form-data/);assert.equal(raw.headers.get('X-M10V-Native-Receipt'),null);
  const response=await unwrapFirmwareDownload(raw),candidate=Buffer.from(await response.arrayBuffer()),receipt=JSON.parse(Buffer.from(response.headers.get('X-M10V-Native-Receipt'),'base64'));
  assert.equal(receipt.configuration_sha256,plan.configuration_sha256);assert.deepEqual(receipt.configuration,plan.configuration);assert.equal(receipt.candidate_sha256,createHash('sha256').update(candidate).digest('hex'));assert.equal(receipt.update_compatibility.package_version,expected);assert.equal(receipt.camera_tested,false);assert.equal(receipt.update_compatibility.camera_verified,false);
  const parsed=inspectFirmwareImport(candidate);assert.equal(parsed.internal_version,expected);assert.equal(parsed.model,model==='gr3'?'GR III':'GR IIIx');
  if(process.env.M10V_DOWNLOAD_OUTPUT){const out=path.join(process.env.M10V_DOWNLOAD_OUTPUT,model);await mkdir(out,{recursive:true});await writeFile(path.join(out,receipt.filename),candidate);await writeFile(path.join(out,'receipt.json'),JSON.stringify(receipt,null,2));await writeFile(path.join(out,'configuration.json'),JSON.stringify(body,null,2));}
 }finally{await new Promise(r=>server.close(r));await rm(dir,{recursive:true,force:true});}
});
