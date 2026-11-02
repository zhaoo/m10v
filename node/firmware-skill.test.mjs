import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {createServer} from './server.mjs';

test('public skill ZIP contains only allowlisted instructions, verifier and a matching manifest',async()=>{
 const server=createServer();await new Promise(r=>server.listen(0,'127.0.0.1',r));
 try{
  const base=`http://127.0.0.1:${server.address().port}`;
  const response=await fetch(base+'/downloads/m10v-firmware-safety-skill.zip');
  assert.equal(response.status,200);assert.match(response.headers.get('Content-Type'),/application\/zip/);
  const bytes=Buffer.from(await response.arrayBuffer());
  const decoded=spawnSync('python3',['-c',"import io,sys,zipfile,json,hashlib; z=zipfile.ZipFile(io.BytesIO(sys.stdin.buffer.read())); assert z.testzip() is None; print(json.dumps({n:hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist()})); print(z.read('m10v-firmware-safety/manifest.json').decode())"],{input:bytes,encoding:'utf8'});
  assert.equal(decoded.status,0,decoded.stderr);
  const [files,manifest]=decoded.stdout.trim().split('\n').map(JSON.parse);
  assert.deepEqual(Object.keys(files).sort(),['SKILL.md','references/firmware-safety.md','scripts/verify_source.py','manifest.json'].map(n=>'m10v-firmware-safety/'+n).sort());
  for(const [name,digest] of Object.entries(manifest.files))assert.equal(files['m10v-firmware-safety/'+name],digest);
  assert.equal(manifest.includes_firmware,false);
  const repeat=Buffer.from(await(await fetch(base+'/downloads/m10v-firmware-safety-skill.zip')).arrayBuffer());
  assert.equal(createHash('sha256').update(repeat).digest('hex'),createHash('sha256').update(bytes).digest('hex'));
 }finally{await new Promise(r=>server.close(r));}
});
