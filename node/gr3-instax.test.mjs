import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {FILM_GROUPS} from './gr3-film-directory.mjs';
import {buildSdFilmPack,auditSdFilmPack,sdFilmRecord,sdCrc} from './gr3-sd-film-pack.mjs';
import {initialState} from './gr3-native-library.mjs';
import {defaultConfiguration} from '../web/gr3/native-library-state.mjs';
import {preSquareArtRecord} from './test-support/pre-square-records.mjs';
test('Instax appends identity 317 under creative and serializes an ISP builtin',()=>{
 const group=FILM_GROUPS.find(g=>g.name==='创意');
 assert.deepEqual(group.films.at(-1),{id:317,name:'Instax Color'});
 const stocks=JSON.parse(readFileSync(new URL('../web/gr3/extra-films-luts.json',import.meta.url))).stocks;
 assert.deepEqual(stocks.map(s=>s.id),[314,315,316,317]);
 const f=stocks.at(-1);assert.equal(f.iso,800);assert.equal(f.camera_calibrated,false);
 assert.equal(f.native_values.length,10125);assert.notDeepEqual(f.native_values,f.values);
 const config=defaultConfiguration();config.slots[0].film=317;
 assert.equal(initialState(config).readUInt16LE(12),317);
 assert.deepEqual(auditSdFilmPack(buildSdFilmPack([317])).ids,[317]);
});
test('all 46 prior display identities and group order stay unchanged',()=>{
 const previous=FILM_GROUPS.flatMap(g=>g.films.filter(f=>f.id!==317).map(f=>[g.name,f.id,f.name]));
 assert.equal(createHash('sha256').update(JSON.stringify(previous)).digest('hex'),'f7120c7e0bc7f5cbfc5a58d5f924a971aed0e94a73494f0cab9eeaeffdc3c4bc');
});
test('browser Instax preview uses the quantized camera target and preserves alpha',async()=>{
 const lut=JSON.parse(readFileSync(new URL('../web/gr3/extra-films-luts.json',import.meta.url)));
 const saved=globalThis.fetch;
 globalThis.fetch=async url=>{assert.ok(String(url).endsWith('/extra-films-luts.json'));return {ok:true,json:async()=>lut};};
 try{
  const {renderPreviewPixels}=await import('../web/gr3/film-preview.mjs');
  const out=await renderPreviewPixels(new Uint8ClampedArray([0,0,255,123]),{film:317},1,1);
  assert.deepEqual([...out],[...lut.stocks.at(-1).native_values.slice(42,45),123]);
 }finally{globalThis.fetch=saved;}
});
test('all 46 visible pre-Instax builtin records remain accepted with original renderer',()=>{
 const prior=JSON.parse(readFileSync(new URL('./gr3-sd-pre-instax-contract.json',import.meta.url)));
 const visible=new Set(FILM_GROUPS.flatMap(g=>g.films.map(f=>f.id)));
 const pack=buildSdFilmPack(prior.ids.filter(id=>visible.has(id))),hash=bytes=>createHash('sha256').update(bytes).digest('hex');
 const ordered=auditSdFilmPack(pack).ids;
 for(let i=0;i<ordered.length;i++){
  const id=ordered[i],r=preSquareArtRecord(id);Buffer.from(prior.renderer,'hex').copy(r,8448);
  r.writeUInt32LE(sdCrc(r.subarray(0,-4)),12284);
  assert.equal(hash(r),prior.hashes[prior.ids.indexOf(id)],`authentic old record ${id}`);
  r.copy(pack,4096+i*12288);pack.writeUInt32LE(r.readUInt32LE(12284),68+i*12);
 }
 pack.writeUInt32LE(sdCrc(pack.subarray(0,4092)),4092);
 assert.deepEqual(auditSdFilmPack(pack).ids,ordered);
});
