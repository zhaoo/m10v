import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {FILM_GROUPS,FILM_DIRECTORY} from './gr3-film-directory.mjs';
import {initialState,nativeCatalog,prepareNative,readNativeOfficial} from './gr3-native-library.mjs';
import {defaultConfiguration,normalizeConfiguration,selectNativeFilm} from '../web/gr3/native-library-state.mjs';
import {buildSdFilmPack,auditSdFilmPack} from './gr3-sd-film-pack.mjs';
import {normalizeGr4Request} from './gr4-m10v-native-build.mjs';

test('E6 follows C41 and seven visible additions preserve stable identities',async()=>{
 const c=await nativeCatalog(),groups=FILM_GROUPS.map(g=>g.name);
 assert.equal(groups[groups.indexOf('C41')+1],'E6');
 assert.deepEqual(FILM_GROUPS.find(g=>g.name==='E6').films.map(f=>[f.id,f.name]),[[294,'Fuji Velvia 50'],[309,'Fuji Provia 100F'],[310,'Kodak Ektachrome E100'],[311,'5294']]);
 assert.equal(c.film_count,51);assert.equal(FILM_DIRECTORY.length,51);
 assert.ok(!c.films.some(f=>f.id>=306&&f.id<=308));
});
test('retained E6 SD package roundtrips and authentic main package still audits',()=>{
 const old=gunzipSync(readFileSync(new URL('../tests/fixtures/gr3-pre-anime-e6-films.m10.gz',import.meta.url)));
 assert.equal(auditSdFilmPack(old).count,37);
 const pack=buildSdFilmPack([294,309,310,311]);
 const result=auditSdFilmPack(pack);assert.equal(result.count,4);
});
test('new looks reject exports without the proven GR III ISP still path',async()=>{
 const source=await readNativeOfficial();const c=defaultConfiguration();c.slots[0].film=309;
 assert.throws(()=>prepareNative(source,c,{live_color:false,debug_mode:false}),/ISP/);
 const p=prepareNative(source,c);assert.equal(p.capture_pipeline,'gr3-native-v8');
 assert.equal(p.stock_detail.anime_mode,undefined);assert.ok(!p.stock_detail.ids.includes(30));assert.ok(!p.stock_detail.fields.includes('animeMode'));
});
test('all seven looks reject GR IV before any firmware build or CPU fallback',()=>{
 for(const film of [294,309,310,311]){
  const c=defaultConfiguration();c.slots[0].film=film;
  assert.throws(()=>normalizeGr4Request({configuration:c}),/ISP/);
 }
});
