import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {mkdtemp,readFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {buildNativeLibrary} from './gr3-m10v-native-build.mjs';
test('custom display resources preserve stock cards and independently reject LUT icon tampering',async()=>{
 const dir=await mkdtemp(path.join(tmpdir(),'m10v-custom-display-'));
 try{
  const manifest=JSON.parse(execFileSync(new URL('../.venv/bin/python',import.meta.url).pathname,['scripts/build_gr3_m10v_library.py','--sd-library','--out',dir],{cwd:new URL('..',import.meta.url).pathname}));
  const runtime=await readFile(path.join(dir,'m10v-library-arm.bin'));
  const source=readFileSync(new URL('../bin/fwdc239b-gr3-official.bin',import.meta.url));
  assert.deepEqual(manifest.custom_film_display.name_resources,[1007,1011]);
  assert.deepEqual(manifest.custom_film_display.appended_name_resources,[1111,1115]);
  assert.deepEqual(manifest.resources.texts.slice(988-786,991-786),['胶卷名称：关闭','胶卷名称：开启','胶卷名称水印']);
  assert.equal(buildNativeLibrary(source,runtime,manifest).receipt.camera_tested,false);
  const cards=manifest.film_cards;
  assert.equal(cards.width,128);assert.equal(cards.height,128);
  assert.equal(cards.descriptor_offset,10*cards.width*cards.height*4);
  assert.equal(cards.directory_offset,cards.descriptor_offset+10*8);
  assert.equal(cards.heap_bytes,cards.directory_offset+25*4);
  assert.throws(()=>buildNativeLibrary(source,runtime,{...manifest,film_cards:{...cards,width:120}}),/film card/);
  assert.equal(manifest.icons.payload_bytes,46*6400);
  assert.equal(manifest.icons.retired_generic_count,32);
  const original=readFileSync(new URL('../native/gr3/m10v_icons.rgba',import.meta.url));
  const generic=readFileSync(new URL('../native/gr3/m10v_custom_icon.rgba',import.meta.url));
  for(let i=0;i<78;i++){
   const descriptor=runtime.readUInt32LE(manifest.icons.table-manifest.base+(671+i)*4);
   const pixel=runtime.readUInt32LE(descriptor-manifest.base+4)*4-manifest.base;
   assert.deepEqual(runtime.subarray(pixel,pixel+6400),i<32?generic:original.subarray(i*6400,(i+1)*6400));
  }
  const aliased=Buffer.from(runtime);
  aliased.writeUInt32LE((manifest.icons.pixels+6400)/4,manifest.icons.descriptors-manifest.base+4);
  assert.throws(()=>buildNativeLibrary(source,aliased,{...manifest,code_sha256:createHash('sha256').update(aliased).digest('hex')}),/icon descriptor differs/);
  for(const offset of [manifest.icons.pixels+manifest.icons.payload_bytes-manifest.base,manifest.icons.descriptors+83*8+4-manifest.base]){
   const changed=Buffer.from(runtime);changed[offset]^=1;
   assert.throws(()=>buildNativeLibrary(source,changed,{...manifest,code_sha256:createHash('sha256').update(changed).digest('hex')}),/custom LUT icon differs/);
  }
  for(const offset of [manifest.icons.pixels+manifest.icons.payload_bytes+2*6400-manifest.base,manifest.icons.descriptors+85*8+4-manifest.base]){
   const changed=Buffer.from(runtime);changed[offset]^=1;
   assert.throws(()=>buildNativeLibrary(source,changed,{...manifest,code_sha256:createHash('sha256').update(changed).digest('hex')}),/Charmera color artwork differs/);
  }
 }finally{await rm(dir,{recursive:true,force:true});}
});
