import test from 'node:test';
import assert from 'node:assert/strict';
import {initialState} from './gr3-native-library.mjs';
import {defaultConfiguration, normalizeConfiguration, resetNativeTexture, toggleNativeFilm} from '../web/gr3/native-library-state.mjs';
import {readFileSync} from 'node:fs';
import {auditSdFilmPack,buildSdFilmPack,sdCrc,SD_RECORD_BYTES} from './gr3-sd-film-pack.mjs';
import {parseCustomCube} from './gr3-custom-lut.mjs';

test('per-film ISP settings are validated and seed only the selected film', () => {
 const input = defaultConfiguration();
 input.slots[1].filmEffects = {leakGain: 2, leakPosition: 4, leakSpread: 1, blur: 3};
 input.slots[1].grain = 3;
 assert.deepEqual(normalizeConfiguration(input).slots[1].filmEffects, input.slots[1].filmEffects);
 const state = initialState(input, {perFilmEffects: true});
 assert.deepEqual([...state.subarray(104,109)], [2,2,4,1,0x83]);
 assert.equal(state[100], 0);
 assert.throws(() => initialState(input), /胶片效果/);
 input.slots[1].filmEffects.leakPosition = 5;
 assert.throws(() => normalizeConfiguration(input), /胶片效果/);
});

test('fresh and reset FN effects enable only 800T halation at 7/7/5', () => {
 const input = toggleNativeFilm(defaultConfiguration(), 67);
 const state = initialState(input, {universal: true, perFilmEffects: true});
 for (const [index, slot] of input.slots.entries()){
  assert.deepEqual([...state.subarray(14 + index*8, 20 + index*8)],
   slot.film === 33 ? [0,0,7,7,5,4] : [0,0,0,3,5,2]);
  assert.equal(state[97 + index*8], 0);
 }
 input.slots[4].halo.gain = 0;
 assert.equal(initialState(input, {universal: true})[48], 0);
 assert.equal(resetNativeTexture(input, 4).slots[4].halo.gain, 7);
});

test('universal halation preserves independent ordinary and dedicated seeds', () => {
 const input = defaultConfiguration();
 input.slots[0].halo = {gain: 2, spread: 4, threshold: 6, profile: 5};
 input.slots[4].halo = {gain: 6, spread: 3, threshold: 5, profile: 2};
 const state = initialState(input, {universal: true});
 assert.deepEqual([...state.subarray(16,20)], [2,4,6,5]);
 assert.deepEqual([...state.subarray(48,52)], [6,3,5,4]);
});

test('the preceding production SD recipe survives the renderer revision', () => {
 const {renderer}=JSON.parse(readFileSync(new URL('./gr3-sd-pre-per-film-effects-contract.json',import.meta.url)));
 const pack=buildSdFilmPack([66]);
 const record=pack.subarray(4096);
 Buffer.from(renderer,'hex').copy(record,8448);
 const crc=sdCrc(record.subarray(0,-4));
 record.writeUInt32LE(crc,record.length-4);
 pack.writeUInt32LE(crc,68);
 pack.writeUInt32LE(sdCrc(pack.subarray(0,4092)),4092);
 assert.deepEqual(auditSdFilmPack(pack).ids,[66]);
});

test('RC1 built-in and custom SD recipes survive the exact halation acceleration', () => {
 const {renderer}=JSON.parse(readFileSync(new URL('./gr3-sd-per-film-rc1-contract.json',import.meta.url)));
 const identity=Buffer.from('LUT_3D_SIZE 2\n0 0 0\n1 0 0\n0 1 0\n1 1 0\n0 0 1\n1 0 1\n0 1 1\n1 1 1\n');
 const custom=parseCustomCube(identity,'identity.cube','RC1 Custom');
 for(const customFilms of [[],[custom]]){
  const pack=buildSdFilmPack([33,67],customFilms);
  const count=pack.readUInt32LE(16);
  for(let i=0;i<count;i++){
   const record=pack.subarray(4096+i*SD_RECORD_BYTES,4096+(i+1)*SD_RECORD_BYTES);
   Buffer.from(renderer,'hex').copy(record,8448);
   const crc=sdCrc(record.subarray(0,-4));
   record.writeUInt32LE(crc,record.length-4);
   pack.writeUInt32LE(crc,68+i*12);
  }
  pack.writeUInt32LE(sdCrc(pack.subarray(0,4092)),4092);
  assert.deepEqual(auditSdFilmPack(pack).ids,customFilms.length?[33,67,79]:[33,67]);
 }
});
