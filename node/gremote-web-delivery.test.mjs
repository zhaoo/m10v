import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm,mkdir,writeFile} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {createServer} from './server.mjs';
import {Store} from './storage.mjs';
import {defaultConfiguration,defaultExtensions} from '../web/gr3/native-library-state.mjs';
import {unwrapFirmwareDownload} from '../web/gr3/firmware-download.mjs';
import {readGRemotePackageSafety,verifyGRemotePackageBlob} from '../web/gr3/gremote-verification.mjs';

// Expensive opt-in: actual public routes, worker, two complete native builds,
// independently compiled fresh service, queue, multipart and browser digest.
test('public GR III connection build downloads a verified matched private ZIP',{
 skip:process.env.M10V_TEST_GREMOTE_WEB_BUILD!=='1',timeout:600000,
},async()=>{
 const directory=await mkdtemp(path.join(os.tmpdir(),'m10v-gremote-web-test-'));
 const server=createServer(new Store(directory));
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const base='http://127.0.0.1:'+server.address().port;
 try{
  const token=(await(await fetch(base+'/api/status')).json()).session_token;
  const post=(url,input)=>fetch(base+url,{method:'POST',headers:{'X-M10V-Token':token,'Content-Type':'application/json'},body:JSON.stringify(input)});
  const imported=await post('/api/gr3/native-library/import-official',{model:'gr3'});
  assert.equal(imported.status,200);const id=(await imported.json()).project_id;
  const route=`/api/projects/${id}/native-library/`;
  // This declaration is an offline test fixture, not a claim about a device.
  const input={configuration:defaultConfiguration('gr3'),film_library:true,
   hdf_enabled:true,border_enabled:true,pure_isp_effects:true,ab_enabled:true,
   extensions:{...defaultExtensions(),aspect:true},gremote_enabled:true,
   camera:{model:'gr3',version:'2.10',origin:'official'}};
  const preflight=await post(route+'prepare',input);assert.equal(preflight.status,200,await preflight.clone().text());
  const plan=await preflight.json();assert.equal(plan.ready,true);
  const queued=await post(route+'jobs',{...input,accepted_configuration_sha256:plan.configuration_sha256});
  assert.equal(queued.status,202);const job=(await queued.json()).job;
  let current;
  do{
   await new Promise(resolve=>setTimeout(resolve,250));
   current=(await(await fetch(base+`/api/firmware-jobs/${job.id}`)).json()).job;
   assert.ok(!['failed','cancelled','expired'].includes(current.state),JSON.stringify(current.error));
  }while(current.state!=='ready');
  const raw=await fetch(base+`/api/firmware-jobs/${job.id}/download`,{headers:{Accept:'multipart/form-data'}});
  assert.equal(raw.status,200);assert.match(raw.headers.get('Cache-Control'),/no-store/);
  const response=await unwrapFirmwareDownload(raw),blob=await response.blob();
  const receipt=JSON.parse(Buffer.from(response.headers.get('X-M10V-Native-Receipt'),'base64'));
  const audit=readGRemotePackageSafety(response);
  const verification={audit,receipt,model:'gr3',sourceSha256:id,
   configurationSha256:plan.configuration_sha256,filename:'m10v-gr3-gremote.zip'};
  await verifyGRemotePackageBlob(blob,verification);
  assert.equal(audit.installation_allowed,false);assert.equal(audit.camera_tested,false);
  assert.equal(audit.firmware.candidate_sha256,receipt.candidate_sha256);
  assert.notEqual(audit.candidate_sha256,receipt.candidate_sha256);
  assert.equal(receipt.preserve_existing,undefined);
  await assert.rejects(()=>verifyGRemotePackageBlob(blob,{...verification,model:'gr3x'}),/型号|机型|GR III/);
  if(process.env.M10V_GREMOTE_DELIVERY_OUTPUT){
   const out=path.resolve(process.env.M10V_GREMOTE_DELIVERY_OUTPUT);await mkdir(out,{recursive:true,mode:0o700});
   await writeFile(path.join(out,'m10v-gr3-gremote.zip'),Buffer.from(await blob.arrayBuffer()),{mode:0o600});
   await writeFile(path.join(out,'web-delivery-receipt.json'),JSON.stringify({audit,receipt,source:id,configuration:input},null,2)+'\n',{mode:0o600});
  }
 }finally{await new Promise(resolve=>server.close(resolve));await rm(directory,{recursive:true,force:true});}
});
