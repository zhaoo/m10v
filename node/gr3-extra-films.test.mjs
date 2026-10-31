import test from 'node:test';import assert from 'node:assert/strict';import{readFileSync}from'node:fs';
import{nativeCatalog,prepareNative,readNativeOfficial,initialState}from'./gr3-native-library.mjs';import{FILM_GROUPS}from'./gr3-film-directory.mjs';import{defaultConfiguration}from'../web/gr3/native-library-state.mjs';import{buildSdFilmPack,auditSdFilmPack}from'./gr3-sd-film-pack.mjs';
test('new monochrome and experimental films have correct groups and stable IDs',async()=>{
 const c=await nativeCatalog();for(const [id,name,group]of[[314,'ACROS II 100','黑白'],[315,'Double-X 5222','黑白'],[316,'LomoChrome Turquoise','创意']]){const f=c.films.find(f=>f.id===id);assert.equal(f?.name,name);assert.equal(f.group,group);assert.equal(f.camera_calibrated,false);}
 assert.ok(!FILM_GROUPS.some(g=>g.name==='D76'));assert.equal(c.film_count,51);
 assert.deepEqual(auditSdFilmPack(buildSdFilmPack([314,315,316])).ids,[314,315,316]);
});
test('both model exports serialize the new films and require native ISP',async()=>{
 for(const model of ['gr3','gr3x'])for(const film of[314,315,316]){const c=defaultConfiguration();c.slots[0].film=film;assert.equal(initialState(c).readUInt16LE(12),film);const source=await readNativeOfficial(model);assert.ok(prepareNative(source,c).external_film_pack);assert.throws(()=>prepareNative(source,c,{live_color:false}),/ISP/);}
});

test('monochrome previews are neutral and Turquoise swaps blue toward warm colours',()=>{
 const {stocks}=JSON.parse(readFileSync(new URL('../web/gr3/extra-films-luts.json',import.meta.url)));
 for(const stock of stocks.filter(s=>[314,315].includes(s.id)))for(let i=0;i<stock.native_values.length;i+=3){assert.equal(stock.native_values[i],stock.native_values[i+1]);assert.equal(stock.native_values[i],stock.native_values[i+2]);}
 const turquoise=stocks.find(s=>s.id===316).native_values;const blue=turquoise.slice(14*3,14*3+3);assert.ok(blue[0]>blue[2]&&blue[1]>blue[2]);
});
