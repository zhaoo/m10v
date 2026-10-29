import test from 'node:test';import assert from 'node:assert/strict';
import {nativeCatalog,prepareNative,readNativeOfficial} from './gr3-native-library.mjs';
import {defaultConfiguration,normalizeConfiguration,migrateRetiredFilms} from '../web/gr3/native-library-state.mjs';
import {buildSdFilmPack} from './gr3-sd-film-pack.mjs';
test('three retired anime styles are absent from catalog and new exports',async()=>{
 const catalog=await nativeCatalog();assert.ok(!catalog.films.some(f=>f.id>=306&&f.id<=308));
 for(const film of [306,307,308]){const c=defaultConfiguration();c.slots[0].film=film;assert.throws(()=>normalizeConfiguration(c));assert.throws(()=>buildSdFilmPack([film]));}
 for(const film of [309,310,311,312,313])assert.ok(catalog.films.some(f=>f.id===film));
});
test('ADJ Fn detailed settings no longer expose anime mode',async()=>{
 const p=prepareNative(await readNativeOfficial(),defaultConfiguration());
 assert.ok(!p.stock_detail.ids.includes(30));assert.ok(!p.stock_detail.fields.includes('animeMode'));assert.equal(p.stock_detail.anime_mode,undefined);
});

test('restoring old drafts removes only retired films and preserves other controls',()=>{
 const c=defaultConfiguration();c.stamp=2;c.hdf=3;c.slots[0].film=306;c.slots[0].effects.animeMode=3;c.slots[2].film=308;c.slots[2].effects.animeMode=1;
 const actual=migrateRetiredFilms(c);assert.deepEqual(actual.slots.map(s=>s.film),[35,37,33]);assert.equal(actual.stamp,2);assert.equal(actual.hdf,3);assert.deepEqual(actual.zoom,c.zoom);assert.ok(!JSON.stringify(actual).includes('animeMode'));
});
