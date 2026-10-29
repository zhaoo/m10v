import test from 'node:test';
import assert from 'node:assert/strict';
import {customFilmRecord,buildSdFilmPack,auditSdFilmPack,sdCrc} from './gr3-sd-film-pack.mjs';

const film=()=>({name:'Warm custom',rgb:Buffer.alloc(6591),sha256:'a'.repeat(64)});
const profile=()=>{
 const b=Buffer.alloc(1572);
 [8192,0,0,0,8192,0,0,0,8192,512,0,0,0,512,0,0,0,512].forEach((v,i)=>b.writeInt16LE(v,i*2));
 for(let c=0;c<3;c++)for(let i=0;i<256;i++)b.writeUInt16LE(i*64,36+(c*256+i)*2);
 return b;
};
test('custom SD record carries versioned ISP profile beside unchanged source LUT',()=>{
 const f=film(),legacy=customFilmRecord(f,79),b=customFilmRecord({...f,ispProfile:profile()},79);
 assert.equal(b.readUInt32LE(6688),0x5053494d);
 assert.equal(b.readUInt32LE(6692),1);assert.equal(b.readUInt32LE(6696),1572);
 assert.equal(b.readUInt32LE(6700),sdCrc(profile()));
 assert.deepEqual(b.subarray(6704,8276),profile());
 assert.deepEqual(b.subarray(8276,8448),Buffer.alloc(172));
 assert.deepEqual(b.subarray(0,6688),legacy.subarray(0,6688));
 assert.deepEqual(legacy.subarray(6688,8448),Buffer.alloc(1760));
 assert.equal(auditSdFilmPack(buildSdFilmPack([],[{...f,ispProfile:profile()}])).count,1);
 assert.equal(auditSdFilmPack(buildSdFilmPack([],[f])).count,1);
});
test('invalid ISP profile cannot be emitted even with a valid original LUT',()=>{
 for(const mutate of [b=>b.subarray(1),b=>{b.writeInt16LE(8191);return b;},b=>{b.writeUInt16LE(16384,36);return b;},b=>{b.writeUInt16LE(0,40);return b;}]){
  assert.throws(()=>customFilmRecord({...film(),ispProfile:mutate(profile())},79),/ISP/);
 }
});
test('independent SD audit rejects rehashed profile corruption and reserved-byte tampering',()=>{
 const pack=buildSdFilmPack([],[{...film(),ispProfile:profile()}]);
 for(const [offset,value] of [[6692,2],[6696,1570],[6700,0],[6704,0],[8276,1]]){
  const b=Buffer.from(pack),record=b.subarray(4096);
  record.writeUInt32LE(value,offset);record.writeUInt32LE(sdCrc(record.subarray(0,-4)),12284);
  b.writeUInt32LE(record.readUInt32LE(12284),68);b.writeUInt32LE(sdCrc(b.subarray(0,4092)),4092);
  assert.throws(()=>auditSdFilmPack(b),/ISP|保留/);
 }
});
