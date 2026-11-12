import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {FILM_GROUPS,FILM_DIRECTORY,orderedFilmIds} from './gr3-film-directory.mjs';
import {nativeCatalog,initialState} from './gr3-native-library.mjs';
import {buildSdFilmPack,auditSdFilmPack,sdFilmRecord,sdCrc} from './gr3-sd-film-pack.mjs';
import {defaultConfiguration,normalizeConfiguration} from '../web/gr3/native-library-state.mjs';
import * as capabilities from '../web/gr3/model-capabilities.mjs';

const read=path=>readFileSync(new URL('../'+path,import.meta.url));
const additions=[
  [328,'SHD50','D76'],
  [329,'Revolog KOLOR','C41'],
  [330,'Pegasus','C41'],
];

test('three ISP films append to their processing groups without rebinding existing identities',async()=>{
  const catalog=await nativeCatalog();
  assert.equal(FILM_DIRECTORY.length,64);
  assert.equal(catalog.film_count,64);
  assert.equal(new Set(catalog.films.map(f=>f.id)).size,64);
  assert.deepEqual(FILM_GROUPS.find(g=>g.name==='C41').films.slice(-2).map(f=>f.id),[329,330]);
  assert.equal(FILM_GROUPS.find(g=>g.name==='D76').films.at(-1).id,328);
  for(const [id,name,group] of additions){
    const film=catalog.films.find(f=>f.id===id);
    assert.equal(film?.name,name);
    assert.equal(film.group,group);
    assert.equal(film.color_path,'native-isp-only');
    assert.deepEqual(film.supported_models,['gr3','gr3x']);
    assert.match(film.icon_url,new RegExp(`/${id}-large\\.png\\?`));
    assert.match(film.icon_compact_url,new RegExp(`/${id}\\.png\\?`));
  }
});

test('three identities survive state normalization with neutral default effects and reset values',()=>{
  const config=defaultConfiguration();
  config.slots=additions.map(([film])=>({...structuredClone(config.slots[0]),film}));
  const restored=normalizeConfiguration(JSON.parse(JSON.stringify(config)));
  assert.deepEqual(restored,config);
  const bytes=initialState(restored,{perFilmEffects:true});
  for(const [index,[film]] of additions.entries()){
    assert.equal(bytes.readUInt16LE(12+index*8),film);
    assert.deepEqual([...bytes.subarray(14+index*8,20+index*8)],[0,0,0,3,5,2]);
    assert.deepEqual([...bytes.subarray(96+index*8,104+index*8)],[0,0,0,4,0,0,0,0]);
  }
});

test('three films require native ISP still processing and support only GR III and IIIx',()=>{
  for(const [id] of additions){
    assert.equal(capabilities.requiresNativeIspFilm?.(id),true);
    assert.equal(capabilities.supportsNativeFilm('gr3',id),true);
    assert.equal(capabilities.supportsNativeFilm('gr3x',id),true);
    assert.equal(capabilities.supportsNativeFilm('gr4',id),false);
    assert.equal(capabilities.supportsNativeFilm('gr2',id),false);
  }
});

test('new SD records are unique while all 85 prior records remain byte-compatible',()=>{
  const ids=additions.map(([id])=>id);
  assert.deepEqual(auditSdFilmPack(buildSdFilmPack(ids)).ids,orderedFilmIds(ids));
  const records=ids.map(sdFilmRecord);
  assert.equal(new Set(records.map(record=>createHash('sha256').update(record).digest('hex'))).size,3);
  const previous=JSON.parse(read('node/gr3-sd-pre-three-films-contract.json'));
  assert.equal(previous.ids.length,85);
  for(const id of previous.ids){
    const record=sdFilmRecord(id);
    Buffer.from(previous.renderer,'hex').copy(record,8448);
    record.writeUInt32LE(sdCrc(record.subarray(0,-4)),12284);
    assert.equal(createHash('sha256').update(record).digest('hex'),previous.hashes[previous.ids.indexOf(id)],`prior recipe ${id}`);
  }
});
