import test from 'node:test';
import assert from 'node:assert/strict';
import {nativeCatalog} from './gr3-native-library.mjs';
import {catalogFilms,catalogGroups} from '../web/gr3/film-catalog-view.mjs';
import {supportsNativeFilm} from '../web/gr3/model-capabilities.mjs';
import {defaultConfiguration,toggleNativeFilm} from '../web/gr3/native-library-state.mjs';

test('workbench and library expose the full model catalog in the same order',async()=>{
 const {films}=await nativeCatalog();
 for(const model of ['gr3','gr3x']){
  const visible=catalogFilms(films,model);
  assert.deepEqual(visible,films.filter(film=>supportsNativeFilm(model,film.id)));
  assert.ok(visible.length>10);
  assert.ok(visible.some(film=>film.name==='Marlboro'));
  assert.deepEqual(catalogGroups(visible),[...new Set(visible.map(film=>film.group))]);
  assert.equal(catalogGroups(visible).length,6);
  for(const group of catalogGroups(visible))
   assert.deepEqual(catalogFilms(films,model,{group}),visible.filter(film=>film.group===group));
  assert.deepEqual(catalogFilms(films,model,{query:'  MARLBORO  '}),visible.filter(film=>film.name==='Marlboro'));
 }
});

test('ten selected catalog films retain their order and parameters; an eleventh is rejected',async()=>{
 const films=catalogFilms((await nativeCatalog()).films,'gr3x');
 let configuration={...defaultConfiguration('gr3x'),slots:[]};
 for(const film of films.slice(0,10))configuration=toggleNativeFilm(configuration,film.id);
 configuration.slots[9].grain=3;
 assert.deepEqual(configuration.slots.map(slot=>slot.film),films.slice(0,10).map(film=>film.id));
 assert.throws(()=>toggleNativeFilm(configuration,films[10].id),/10/);
 assert.equal(configuration.slots[9].grain,3);
 configuration=toggleNativeFilm(configuration,films[0].id);
 configuration=toggleNativeFilm(configuration,films[10].id);
 assert.equal(configuration.slots.length,10);
 assert.equal(configuration.slots[8].grain,3);
 assert.equal(configuration.slots[9].film,films[10].id);
});
