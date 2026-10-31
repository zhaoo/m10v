import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm,readFile} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {createServer} from './server.mjs';
import {Store} from './storage.mjs';
import {defaultConfiguration} from '../web/gr3/native-library-state.mjs';
import {decodeFrameMap,sum32} from './gr3-frames.mjs';
import {unwrapFirmwareDownload} from '../web/gr3/firmware-download.mjs';
test('HTTP power preview, stale-plan rejection and native unified export read back both images',async()=>{
 const dir=await mkdtemp(path.join(os.tmpdir(),'m10v-power-')),server=createServer(new Store(dir));await new Promise(r=>server.listen(0,'127.0.0.1',r));const base=`http://127.0.0.1:${server.address().port}`;
 try{
  const status=await(await fetch(base+'/api/status')).json(),post=async(url,body,token=true)=>unwrapFirmwareDownload(await fetch(base+url,{method:'POST',headers:{'Content-Type':'application/json',...(url.endsWith('/build')?{Accept:'multipart/form-data'}:{}),...(token?{'X-M10V-Token':status.session_token}:{})},body:JSON.stringify(body)}));
  const source=await readFile(new URL('../bin/fwdc239b-gr3-official.bin',import.meta.url)),original=decodeFrameMap(source).decoded,jpeg_base64=original.subarray(59298689,59298689+112509).toString('base64');
  const power_images={startup:{jpeg_base64},shutdown:{jpeg_base64}};
  assert.equal((await post('/api/gr3/power-images/preview',power_images,false)).status,403);
  const preview=await post('/api/gr3/power-images/preview',power_images);assert.equal(preview.status,200);const previews=await preview.json();assert.ok(previews.startup.preview_data_url.startsWith('data:image/jpeg;base64,'));assert.equal(previews.startup.bytes,16687);assert.equal(previews.shutdown.bytes,112509);
  const imported=await(await post('/api/gr3/native-library/import-official',{})).json(),route=`/api/projects/${imported.project_id}/native-library/`,request={configuration:defaultConfiguration(),power_images};
  const prepare=await post(route+'prepare',request);assert.equal(prepare.status,200,await prepare.clone().text());const plan=await prepare.json();assert.equal(plan.power_images.startup.enabled,true);
  assert.equal((await post(route+'build',{...request,power_images:{shutdown:{jpeg_base64}},accepted_configuration_sha256:plan.configuration_sha256})).status,400);
  const built=await post(route+'build',{...request,accepted_configuration_sha256:plan.configuration_sha256});assert.equal(built.status,200,await built.clone().text());const candidate=Buffer.from(await built.arrayBuffer()),receipt=JSON.parse(Buffer.from(built.headers.get('X-M10V-Native-Receipt'),'base64'));
  assert.equal(receipt.configuration_sha256,plan.configuration_sha256);assert.equal(receipt.candidate_sha256,createHash('sha256').update(candidate).digest('hex'));assert.equal(receipt.power_images.non_target_bytes_unchanged,true);assert.equal(receipt.power_images.startup.display_verified,false);
  const actual=decodeFrameMap(candidate,candidate.readUInt32LE(candidate.length-8)).decoded;assert.equal(sum32(actual),0);assert.equal(sum32(candidate),0);assert.equal(actual[0x10870+0xb22adc],65);assert.equal(actual[0x10870+0xb2298c],65);assert.equal(actual.readUInt32LE(0x10870+0x107e0bc),0x53b5f520);for(const index of [1,2,9,10,11])assert.equal(actual.readUInt32LE(0x10870+0x107e0bc+index*4),0x53b5f508);
 }finally{await new Promise(r=>server.close(r));await rm(dir,{recursive:true,force:true});}
});
