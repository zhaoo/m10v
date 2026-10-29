import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {nativeCatalog,initialState,prepareNative,readNativeOfficial} from './gr3-native-library.mjs';
import {FILM_GROUPS} from './gr3-film-directory.mjs';
import {buildSdFilmPack,auditSdFilmPack} from './gr3-sd-film-pack.mjs';
import {defaultConfiguration} from '../web/gr3/native-library-state.mjs';
import {normalizeGr4Request} from './gr4-m10v-native-build.mjs';
test('C41 exposes independent OptiColour 200 and NC500 identities',async()=>{
 const c=await nativeCatalog();
 assert.deepEqual(FILM_GROUPS.find(g=>g.name==='C41').films.slice(-2),[{id:312,name:'OptiColour 200'},{id:313,name:'NC500'}]);
 for(const id of [312,313]){const f=c.films.find(f=>f.id===id);assert.ok(f);assert.equal(f.group,'C41');assert.equal(f.film_calibrated,false);assert.equal(f.approximation,true);}
});
test('C41 serializes new IDs for both GR3 and GR3x with native ISP required',async()=>{
 for(const model of ['gr3','gr3x'])for(const film of [312,313]){
  const c=defaultConfiguration();c.slots[0].film=film;
  assert.equal(initialState(c).readUInt16LE(12),film);
  const source=await readNativeOfficial(model);
  assert.ok(prepareNative(source,c).external_film_pack);
  assert.throws(()=>prepareNative(source,c,{live_color:false}),/ISP/);
  assert.throws(()=>normalizeGr4Request({configuration:c}),/ISP/);
 }
});
test('C41 SD recipes roundtrip while original main builtin/custom records remain valid',()=>{
 assert.deepEqual(auditSdFilmPack(buildSdFilmPack([312,313])).ids,[312,313]);
 const old=gunzipSync(readFileSync(new URL('../tests/fixtures/gr3-pre-c41-films.m10.gz',import.meta.url)));
 assert.equal(auditSdFilmPack(old).count,45);
});
