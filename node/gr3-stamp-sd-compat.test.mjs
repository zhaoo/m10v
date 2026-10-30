import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {buildSdFilmPack,auditSdFilmPack,sdCrc} from './gr3-sd-film-pack.mjs';
import {preSquareArtRecord} from './test-support/pre-square-records.mjs';
const prior=JSON.parse(readFileSync(new URL('./gr3-sd-pre-oriented-stamp-contract.json',import.meta.url)));
export function priorStampPack(){
 const pack=buildSdFilmPack([33,314,316]);
 for(let i=0;i<pack.readUInt32LE(16);i++){
  const r=pack.subarray(4096+i*12288,4096+(i+1)*12288),id=r.readUInt32LE(8);
  preSquareArtRecord(id).copy(r);
  Buffer.from(prior.renderer,'hex').copy(r,8448);
  r.writeUInt32LE(sdCrc(r.subarray(0,-4)),12284);
  assert.equal(createHash('sha256').update(r).digest('hex'),prior.hashes[prior.ids.indexOf(id)],'reconstruct exact delivered recipe, not an invented compatibility fixture');
  pack.writeUInt32LE(r.readUInt32LE(12284),68+i*12);
 }
 pack.writeUInt32LE(sdCrc(pack.subarray(0,4092)),4092);return pack;
}
test('orientation-only renderer update accepts the exact last delivered SD recipes',()=>{
 const result=auditSdFilmPack(priorStampPack());assert.ok(result);
});
test('orientation compatibility does not authorize a modified recipe with repaired CRCs',()=>{
 const pack=priorStampPack(),record=pack.subarray(4096,4096+12288);record[64]^=1;
 record.writeUInt32LE(sdCrc(record.subarray(0,-4)),12284);pack.writeUInt32LE(record.readUInt32LE(12284),68);pack.writeUInt32LE(sdCrc(pack.subarray(0,4092)),4092);
 assert.throws(()=>auditSdFilmPack(pack),/校验|兼容/);
});
