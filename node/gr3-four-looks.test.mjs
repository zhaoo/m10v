import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {FILM_GROUPS,FILM_DIRECTORY,orderedFilmIds} from './gr3-film-directory.mjs';
import {nativeCatalog,initialState,prepareNative,readNativeOfficial} from './gr3-native-library.mjs';
import {defaultConfiguration,normalizeConfiguration} from '../web/gr3/native-library-state.mjs';
import {buildSdFilmPack,auditSdFilmPack,sdFilmRecord,sdCrc} from './gr3-sd-film-pack.mjs';
import {renderPreviewPixels,previewNewStocksPixels} from '../web/gr3/film-preview.mjs';
import {supportsNativeFilm} from '../web/gr3/model-capabilities.mjs';
import {fullLibraryRequest} from '../web/gr3/full-library.mjs';
import {exportSdFilms} from './gr3-sd-film-export.mjs';

const read=path=>readFileSync(new URL('../'+path,import.meta.url));
const additions=[[318,'2383','ECN2'],[319,'Classic Negative','影像'],[320,'Classic Chrome','影像'],[321,'LomoChrome Purple','创意']];
const precedingGroups=[
 ['ECN2',[33,66,62,78,298,77]],
 ['C41',[69,37,70,73,56,36,35,58,74,34,71,67,68,292,312,313]],
 ['E6',[294,309,310,311]],
 ['黑白',[75,299,300,301,302,303,304,305,314,315]],
 ['创意',[289,72,293,296,290,76,316,317]],
 ['影像',[291,297,65]],
];
test('four ISP looks append to existing groups without rebinding any preceding identity',async()=>{
 const catalog=await nativeCatalog();
 assert.equal(FILM_DIRECTORY.length,51);assert.equal(catalog.film_count,51);
 assert.equal(new Set(catalog.films.map(f=>f.id)).size,51);
 assert.deepEqual(FILM_GROUPS.map(g=>g.name),precedingGroups.map(([name])=>name));
 for(const [name,ids] of precedingGroups){const group=FILM_GROUPS.find(g=>g.name===name);assert.deepEqual(group.films.filter(f=>f.id<318).map(f=>f.id),ids);}
 for(const [id,name,group] of additions){const film=catalog.films.find(f=>f.id===id);assert.equal(film?.name,name);assert.equal(film.group,group);assert.equal(film.camera_calibrated,false);assert.equal(film.approximation,true);assert.match(film.icon_url,new RegExp(`/${id}-large\\.png\\?`));assert.match(film.icon_compact_url,new RegExp(`/${id}\\.png\\?`));}
 assert.ok(catalog.films.every(f=>!Object.hasOwn(f,'values')&&!Object.hasOwn(f,'native_values')),'catalog metadata must not serialize preview tables');
 assert.deepEqual(FILM_GROUPS.find(g=>g.name==='影像').films.slice(-2).map(f=>f.id),[319,320]);
});
test('all four identities survive ten-slot state normalization and serialization with per-slot settings',()=>{
 const config=defaultConfiguration();
 config.slots=[318,319,320,321,33,34,35,36,37,66].map((film,i)=>({...structuredClone(config.slots[0]),film,grain:i%4}));
 const restored=normalizeConfiguration(JSON.parse(JSON.stringify(config)));
 assert.deepEqual(restored,config);assert.equal(restored.slots.length,10);
 const bytes=initialState(restored);assert.equal(bytes.length,184);
 restored.slots.forEach((s,i)=>{assert.equal(bytes.readUInt16LE(12+8*i),s.film);assert.equal(bytes[14+8*i],s.grain);assert.equal(bytes[15+8*i],s.soft);});
});
test('new looks require the verified GR III native pipeline and reject IIIx',async()=>{
 const gr3=await readNativeOfficial('gr3'),gr3x=await readNativeOfficial('gr3x');
 for(const [id] of additions){
  const config=defaultConfiguration();config.slots[0].film=id;
  assert.equal(prepareNative(gr3,config).capture_pipeline,'gr3-native-v8');
  assert.equal(prepareNative(gr3,config,{live_color:false,debug_mode:true}).capture_pipeline,'gr3-native-v7');
  assert.equal(prepareNative(gr3,config,{live_color:false}).capture_pipeline,'gr3-native-v7');
  const hdf=structuredClone(config);hdf.hdf=1;
  assert.equal(prepareNative(gr3,hdf,{live_color:false}).capture_pipeline,'gr3-native-v7');
  assert.equal(prepareNative(gr3,hdf,{film_library:false,live_color:false}).capture_pipeline,'gr3-native-hdf');
  assert.throws(()=>prepareNative(gr3x,config),/GR III.*ISP/);
  assert.throws(()=>prepareNative(gr3x,config,{live_color:false,debug_mode:true}),/GR III.*ISP/);
 }
});
test('selection and complete-library downloads keep unverified models away from new looks',async()=>{
 for(const [id] of additions){assert.equal(supportsNativeFilm('gr3',id),true);for(const model of ['gr3x','gr4','gr2'])assert.equal(supportsNativeFilm(model,id),false);}
 assert.equal(supportsNativeFilm('gr3x',317),true);
 const catalog=[{id:33},...additions.map(([id])=>({id}))];
 assert.deepEqual(fullLibraryRequest('gr3x',catalog).body.ids,[33]);
 assert.deepEqual(fullLibraryRequest('gr3',catalog).body.ids,catalog.map(f=>f.id));
 await assert.rejects(exportSdFilms({model:'gr3x',ids:[318]}),/GR III.*ISP/);
});
test('new SD records bind quantized ISP tables and artwork; the preceding47 package remains valid',()=>{
 const lut=JSON.parse(read('web/gr3/four-looks-luts.json'));
 const art=read('native/gr3/m10v_four_looks.rgba');assert.equal(art.length,4*6400);
 const ids=additions.map(([id])=>id),pack=buildSdFilmPack(ids);
 assert.deepEqual(auditSdFilmPack(pack).ids,orderedFilmIds(ids));
 for(const [i,id] of ids.entries()){
  const record=sdFilmRecord(id),stock=lut.stocks.find(s=>s.id===id);
  assert.equal(record.readUInt32LE(12),3);
  assert.deepEqual(record.subarray(64,96),createHash('sha256').update(Buffer.from(stock.native_values)).digest());
  assert.deepEqual(record.subarray(2048,8448),art.subarray(i*6400,(i+1)*6400));
 }
 const previous=JSON.parse(read('node/gr3-sd-pre-four-looks-contract.json'));
 const oldIds=precedingGroups.flatMap(([,ids])=>ids),legacy=buildSdFilmPack(oldIds);
 orderedFilmIds(oldIds).forEach((id,i)=>{
  const record=legacy.subarray(4096+i*12288,4096+(i+1)*12288);
  Buffer.from(previous.renderer,'hex').copy(record,8448);record.writeUInt32LE(sdCrc(record.subarray(0,-4)),12284);
  assert.equal(createHash('sha256').update(record).digest('hex'),previous.hashes[previous.ids.indexOf(id)],`unchanged preceding recipe ${id}`);
  legacy.writeUInt32LE(record.readUInt32LE(12284),68+12*i);
 });
 legacy.writeUInt32LE(sdCrc(legacy.subarray(0,4092)),4092);
 assert.deepEqual(auditSdFilmPack(legacy).ids,orderedFilmIds(oldIds));
});
test('browser previews use the fitted ISP table for all four looks',async()=>{
 const originalFetch=globalThis.fetch,requested=[];
 globalThis.fetch=async url=>{requested.push(String(url));return {ok:true,json:async()=>JSON.parse(readFileSync(url))};};
 try{
  const lut=JSON.parse(read('web/gr3/four-looks-luts.json'));
  const source=Uint8ClampedArray.from([40,130,220,153,210,72,45,255]);
  for(const [id] of additions){const stock=lut.stocks.find(s=>s.id===id);assert.deepEqual(await renderPreviewPixels(source,{film:id},2,1),previewNewStocksPixels(source,{...lut,stocks:[{id:298,values:stock.native_values}]},298));}
  assert.equal(requested.filter(url=>url.endsWith('/four-looks-luts.json')).length,1);
  assert.deepEqual(Array.from(source),[40,130,220,153,210,72,45,255]);
 }finally{globalThis.fetch=originalFetch;}
});
