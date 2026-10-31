import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm,readFile} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {createServer} from './server.mjs';
import {Store} from './storage.mjs';
import {Gr4Runtime} from './gr4-runtime.mjs';

test('GR IV uses the shared five-slot workbench and retains the reference editor',async()=>{
 const folder=await mkdtemp(path.join(os.tmpdir(),'m10v-gr4-web-'));
 const server=createServer(new Store(folder),undefined,new Gr4Runtime(path.join(folder,'gr4')));await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const base=`http://127.0.0.1:${server.address().port}`;
 try{
  const workspace=await(await fetch(base+'/gr4/')).text();
  for(const id of ['native-editor','recipe-dialog','firmware-disclaimer','debug-mode','build-firmware'])assert.ok(workspace.includes(`id="${id}"`),id);
  assert.ok(workspace.includes('/gr3/studio.js'));assert.ok(workspace.includes('value="gr4"'));
  const reference=await fetch(base+'/gr4/reference/');assert.equal(reference.status,200);assert.ok((await reference.text()).includes('/gr4/app.js'));
  const catalog=await(await fetch(base+'/api/gr4/native-library/catalog')).json();
  const gr3=await(await fetch(base+'/api/gr3/native-library/catalog')).json();
  assert.deepEqual(catalog.films,gr3.films.filter(f=>f.id<289).map((f,i)=>({...f,number:i+1})));assert.deepEqual(catalog.local_sources,['gr4']);
  assert.equal((await fetch(base+'/api/gr4/native-library/import-official',{method:'POST',body:'{}'})).status,403);
  const status=await(await fetch(base+'/api/status')).json();
  const sdHtml=await(await fetch(base+'/gr4/sd-library.html')).text();assert.ok(sdHtml.includes('GR IV · 胶卷库'));assert.ok(!sdHtml.includes('已获用户真机确认'));assert.ok(!sdHtml.includes('GR IIIx 暂不支持'));assert.ok(sdHtml.includes('配套 GR IV 1.11'));
  const sd=await fetch(base+'/api/gr4/native-library/sd-export',{method:'POST',headers:{'X-M10V-Token':status.session_token},body:JSON.stringify({ids:[33,66,67,68]})});assert.equal(sd.status,200);assert.ok(sd.headers.get('Content-Disposition').includes('M10V-GR4-SD-films.zip'));const sdBytes=Buffer.from(await sd.arrayBuffer());assert.equal(sdBytes.readUInt32LE(0),0x04034b50);for(const text of ['GR IV 1.11','左右选卷、上下翻页','MENU 取消当前编辑','SHA-256'])assert.ok(sdBytes.toString('utf8').includes(text),text);
  const invalid=await fetch(base+'/api/gr4/native-library/import',{method:'POST',headers:{'X-M10V-Token':status.session_token},body:Buffer.from('not official')});assert.equal(invalid.status,400);
  const imported=await fetch(base+'/api/gr4/native-library/import-official',{method:'POST',headers:{'X-M10V-Token':status.session_token},body:'{}'});assert.equal(imported.status,200,await imported.clone().text());const source=await imported.json();assert.equal(source.model,'GR IV');assert.equal(source.sha256,source.project_id);
  const backup=await fetch(base+'/api/gr4/native-library/backup',{method:'POST',headers:{'X-M10V-Token':status.session_token},body:JSON.stringify({project_id:source.project_id})});assert.equal(backup.status,200);assert.deepEqual(Buffer.from(await backup.arrayBuffer()),await readFile(new URL('../bin/fwdc248b-gr4-officical.bin',import.meta.url)));
 }finally{await new Promise(r=>server.close(r));await rm(folder,{recursive:true,force:true});}
});
