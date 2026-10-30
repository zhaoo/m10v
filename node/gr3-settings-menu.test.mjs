import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,readFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {execFileSync} from 'node:child_process';
import {buildNativeLibrary} from './gr3-m10v-native-build.mjs';
import {settingsPatches,checkSettings} from './gr3-settings-menu.mjs';
test('independent settings audit binds owned controllers, original fallback and root captions',()=>{
 const dir=mkdtempSync(join(tmpdir(),'m10v-settings-audit-'));
 try{
  execFileSync('.venv/bin/python',['scripts/build_gr3_m10v_library.py','--out',dir,'--sd-library','--appended-slots']);
  const m=JSON.parse(readFileSync(join(dir,'m10v-library-arm.json'))),r=readFileSync(join(dir,'m10v-library-arm.bin'));
  checkSettings(r,m);
  const p=settingsPatches(m);
  assert.equal(p.length,11);
  assert.equal(p.find(x=>x.address===0x53b37018).replacement,0x0200f105);
  assert.equal(m.settings_menu.rows.length,2);
  assert.deepEqual(m.settings_menu.private_routes,[0x0200f100,0x0200f101,0x0200f103,0x0200f104,0x0200f105]);
  const routes=[0x0200f100,0x0200f101];
  for(let i=0;i<2;i++){
   assert.equal(p.find(x=>x.address===0x53b36bd0+i*8).replacement,m.settings_menu.rows[i]);
   assert.equal(p.find(x=>x.address===0x53b36c88+i*4).replacement,routes[i]);
  }
  assert.equal(m.resources.texts[1024-786],'裁切焦距');
  const missingZoom=structuredClone(m);missingZoom.settings_menu.rows.pop();
  assert.throws(()=>settingsPatches(missingZoom),/route\/owner/);
  const wrongZoom=structuredClone(m);wrongZoom.settings_menu.private_routes[4]=0x0200004e;
  assert.throws(()=>settingsPatches(wrongZoom),/route\/owner/);
  assert.equal(p.find(x=>x.address===0x53b36adc).replacement,0x201d1b19);
  assert.equal(p.find(x=>x.address===0x5316fcec).replacement,0xe302013c);
  for(const a of [m.settings_menu.vtable,m.settings_menu.exports.m10v_settings_factory_original,m.settings_menu.rows[0]]){
   const broken=Buffer.from(r);broken[a-m.base]^=1;
   assert.throws(()=>checkSettings(broken,m),/instruction/);
  }
  const official=readFileSync('bin/fwdc239b-gr3-official.bin');
  buildNativeLibrary(official,r,m);
  for(const name of ['metadata_decode','icon','detail']){
   const broken=Buffer.from(r);broken[m.appended_slots.playback[name]-m.base+8]^=1;
   assert.throws(()=>buildNativeLibrary(official,broken,m));
  }
  const broken=structuredClone(m);broken.settings_menu.private_routes[0]=0x0200004e;
  assert.throws(()=>checkSettings(r,broken),/route/);
  const captions=structuredClone(m);captions.resources.texts[151]='Image Control';
  assert.throws(()=>checkSettings(r,captions),/captions/);
 }finally{rmSync(dir,{recursive:true,force:true});}
});
