import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {nativeCatalog,initialState} from './gr3-native-library.mjs';
import {buildSdFilmPack,auditSdFilmPack,sdFilmRecord,sdCrc} from './gr3-sd-film-pack.mjs';
import {defaultConfiguration} from '../web/gr3/native-library-state.mjs';
const ids=[322,323,324,325,326];
test('five C41 stocks are independently selectable and produce distinct SD recipes',async()=>{
 const catalog=await nativeCatalog();
 assert.deepEqual(catalog.films.filter(f=>ids.includes(f.id)).map(f=>[f.id,f.name,f.group]),[
  [322,'Harman Phoenix 200','C41'],[323,'Kodak ColorPlus 200','C41'],
  [324,'Fujifilm Natura 1600','C41'],[325,'Lomo Redscale XR','C41'],[326,'Agfa Vista 200','C41']]);
 for(const film of ids){const c=defaultConfiguration();c.slots[0].film=film;assert.equal(initialState(c).readUInt16LE(12),film);}
 assert.deepEqual(auditSdFilmPack(buildSdFilmPack(ids)).ids,ids);
 assert.equal(new Set(ids.map(id=>sdFilmRecord(id).subarray(64,96).toString('hex'))).size,5);
 assert.notDeepEqual(sdFilmRecord(322).subarray(64,96),sdFilmRecord(67).subarray(64,96));
});
test('previous production built-in and custom packs remain admissible by exact frozen digests',()=>{
 const selected=[33,67,312,313,318,319,320,321];
 const prior=JSON.parse(readFileSync(new URL('./gr3-sd-pre-five-c41-contract.json',import.meta.url)));
 for(const customFilms of [[],[{name:'Legacy',rgb:Buffer.alloc(6591),sha256:'a'.repeat(64)}]]){
  const pack=buildSdFilmPack(selected,customFilms);
  const count=pack.readUInt32LE(16);
  for(let i=0;i<count;i++){
   const record=pack.subarray(4096+i*12288,4096+(i+1)*12288);
   Buffer.from(prior.renderer,'hex').copy(record,8448);
   record.writeUInt32LE(sdCrc(record.subarray(0,-4)),12284);
   pack.writeUInt32LE(record.readUInt32LE(12284),68+i*12);
   const id=record.readUInt32LE(8);
   if(id!==79)assert.equal(createHash('sha256').update(record).digest('hex'),prior.hashes[prior.ids.indexOf(id)]);
  }
  pack.writeUInt32LE(sdCrc(pack.subarray(0,4092)),4092);
  assert.equal(auditSdFilmPack(pack).count,8+customFilms.length);
 }
});
