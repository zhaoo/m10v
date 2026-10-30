import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {buildNativeLibrary} from './gr3-m10v-native-build.mjs';

test('recorded identity binds SI lifetime hooks and verified capture snapshot',()=>{
 const folder=mkdtempSync(join(tmpdir(),'m10v-recorded-'));
 try{
  const m=JSON.parse(execFileSync(new URL('../.venv/bin/python',import.meta.url).pathname,['scripts/build_gr3_m10v_library.py','--sd-library','--appended-slots','--debug','--lifecycle-trace','--recipe-snapshot','--out',folder],{cwd:new URL('..',import.meta.url)}));
  const runtime=readFileSync(join(folder,'m10v-library-arm.bin'));
  const official=readFileSync(new URL('../bin/fwdc239b-gr3-official.bin',import.meta.url));
  assert.equal(m.appended_slots.playback.identity_enabled,true);
  assert.equal(buildNativeLibrary(official,runtime,m).receipt.camera_tested,false);
  const missing=structuredClone(m);missing.capture_lifecycle.snapshot.producer_sites=[];
  assert.throws(()=>buildNativeLibrary(official,runtime,missing),/recorded identity requires frozen snapshot/);
  for(const name of ['pool_init','checkout','return','copy','writer']){
   const broken=Buffer.from(runtime);broken[m.appended_slots.playback.identity_hooks[name]-m.base+4]^=1;
   assert.throws(()=>buildNativeLibrary(official,broken,{...m,code_sha256:createHash('sha256').update(broken).digest('hex')}),/recorded identity .* instructions differ/);
  }
 }finally{rmSync(folder,{recursive:true,force:true});}
});
