import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {FILM_DIRECTORY,FILM_GROUPS} from './gr3-film-directory.mjs';
import {nativeCatalog,initialState,prepareNative,readNativeOfficial} from './gr3-native-library.mjs';
import {defaultConfiguration,defaultHalo,toggleNativeFilm,resetNativeTexture} from '../web/gr3/native-library-state.mjs';
import {sdFilmRecord,buildSdFilmPack,auditSdFilmPack,sdCrc} from './gr3-sd-film-pack.mjs';
import {renderPreviewPixels} from '../web/gr3/film-preview.mjs';
import {supportsNativeFilm} from '../web/gr3/model-capabilities.mjs';
import {normalizeGr4Request} from './gr4-m10v-native-build.mjs';
const read=p=>readFileSync(new URL('../'+p,import.meta.url));

test('Marlboro appends to creative with a new stable identity and its own artwork',async()=>{
 const catalog=await nativeCatalog(),entry=catalog.films.find(f=>f.id===327);
 assert.equal(entry?.name,'Marlboro');assert.equal(entry.group,'创意');
 assert.equal(FILM_DIRECTORY.length,57);
 assert.equal(FILM_GROUPS.find(g=>g.name==='创意').films.at(-1).id,327);
 assert.match(entry.icon_url,/327-large\.png\?/);
 assert.equal(entry.color_path,'native-isp-only');
});
test('Marlboro inherits 800T defaults, reset and serialized per-film halo fields',()=>{
 assert.deepEqual(defaultHalo(327),defaultHalo(33));
 const config=toggleNativeFilm(defaultConfiguration(),327),slot=config.slots.length-1;
 config.slots[slot].halo={gain:2,spread:8,threshold:1,profile:4};
 const bytes=initialState(config,{universal:true});
 assert.deepEqual(Array.from(bytes.subarray(16+8*slot,20+8*slot)),[2,8,1,4]);
 assert.equal(bytes.readUInt16LE(12+8*slot),327);
 assert.deepEqual(resetNativeTexture(config,slot).slots[slot].halo,defaultHalo(33));
});
test('Marlboro forces owned native color even with preview disabled on the existing adapters',async()=>{
 for(const model of ['gr2','gr4'])assert.equal(supportsNativeFilm(model,327),false);
 const gr4=defaultConfiguration();gr4.slots[0].film=327;
 assert.throws(()=>normalizeGr4Request({configuration:gr4,extensions:{aspect:false,level:false,negativeGrain:false}}),/ISP/);
 for(const model of ['gr3','gr3x']){
  assert.equal(supportsNativeFilm(model,327),true);
  const source=await readNativeOfficial(model),config=toggleNativeFilm(defaultConfiguration(model),327);
  const plan=prepareNative(source,config,{live_color:false});
  assert.equal(plan.capture_pipeline,'gr3-native-v7');
  assert.ok(plan.stock_detail.halation_dedicated_films.includes(327));
 }
});
test('Marlboro SD recipe and previous engine records remain independently authenticated',()=>{
 const record=sdFilmRecord(327),lut=JSON.parse(read('web/gr3/marlboro-luts.json'));
 assert.equal(record.readUInt32LE(12),3);
 assert.deepEqual(record.subarray(64,96),createHash('sha256').update(Buffer.from(lut.stocks[0].native_values)).digest());
 assert.deepEqual(auditSdFilmPack(buildSdFilmPack([33,327])).ids,[33,327]);
 const previous=JSON.parse(read('node/gr3-sd-pre-marlboro-contract.json'));
 for(const id of previous.ids){
  const r=sdFilmRecord(id);Buffer.from(previous.renderer,'hex').copy(r,8448);r.writeUInt32LE(sdCrc(r.subarray(0,-4)),12284);
  assert.equal(createHash('sha256').update(r).digest('hex'),previous.hashes[previous.ids.indexOf(id)],`preserved recipe ${id}`);
 }
 const pack=buildSdFilmPack(FILM_DIRECTORY.filter(f=>f.id!==327).map(f=>f.id)),ids=Array.from({length:pack.readUInt32LE(16)},(_,i)=>pack.readUInt32LE(64+12*i));
 ids.forEach((id,i)=>{
  const r=pack.subarray(4096+i*12288,4096+(i+1)*12288);
  Buffer.from(previous.renderer,'hex').copy(r,8448);r.writeUInt32LE(sdCrc(r.subarray(0,-4)),12284);
  assert.equal(createHash('sha256').update(r).digest('hex'),previous.hashes[previous.ids.indexOf(id)]);
  pack.writeUInt32LE(r.readUInt32LE(12284),68+12*i);
 });
 pack.writeUInt32LE(sdCrc(pack.subarray(0,4092)),4092);
 assert.deepEqual(auditSdFilmPack(pack).ids,ids);
});
test('Marlboro browser base is neutral and retains alpha without modifying input',async()=>{
 const originalFetch=globalThis.fetch;
 globalThis.fetch=async url=>({ok:true,json:async()=>JSON.parse(readFileSync(url))});
 try{
  const source=Uint8ClampedArray.from([20,130,240,120,220,45,30,255]),before=source.slice();
  const result=await renderPreviewPixels(source,{film:327},2,1);
  assert.deepEqual(source,before);
  for(let i=0;i<result.length;i+=4){assert.equal(result[i],result[i+1]);assert.equal(result[i+1],result[i+2]);assert.equal(result[i+3],source[i+3]);}
 }finally{globalThis.fetch=originalFetch;}
});
