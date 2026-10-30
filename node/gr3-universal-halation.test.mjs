import test from 'node:test';
import assert from 'node:assert/strict';
import {readNativeOfficial,prepareNative} from './gr3-native-library.mjs';
import {defaultConfiguration} from '../web/gr3/native-library-state.mjs';
import {normalizeWorkbenchDraft} from '../web/gr3/workbench-state.mjs';
test('universal halation is explicit GR III film capability, bound into plan and defaults off',async()=>{
 const source=await readNativeOfficial(),config=defaultConfiguration();
 config.slots[4].halo.gain=8;
 const off=prepareNative(source,config),on=prepareNative(source,config,{halation_enabled:true});
 assert.equal(off.halation_enabled,false);assert.equal(on.halation_enabled,true);
 assert.notEqual(on.configuration_sha256,off.configuration_sha256);
 assert.ok(on.features.includes('halation'));
 const initial=Buffer.from(on.initial_state_hex,'hex');
 for(let i=0;i<10;i++){assert.equal(initial[16+i*8],0);assert.ok(initial[19+i*8]<4);}
 assert.equal(config.slots[4].halo.gain,8,'input configuration is not mutated');
 assert.deepEqual(on.stock_detail.halation_modes,['off','spill','streak']);
 assert.equal(on.stock_detail.halation_films,'all');
 assert.ok(on.stock_detail.ids.includes(22));assert.ok(on.stock_detail.fields.includes('halationMode'));
 assert.throws(()=>prepareNative(source,config,{halation_enabled:'yes'}),/光晕/);
 assert.throws(()=>prepareNative(source,config,{halation_enabled:true,film_library:false}),/光晕/);
 assert.throws(()=>prepareNative(source,config,{halation_enabled:true,live_color:false}),/光晕/);
 const x=await readNativeOfficial('gr3x');assert.equal(prepareNative(x,config,{halation_enabled:true}).halation_enabled,true);
});
test('web draft preserves the independent halation write toggle',()=>{
 const draft=normalizeWorkbenchDraft({profile:'native',features:['film','halation'],nativeConfiguration:defaultConfiguration()});
 assert.ok(draft.features.includes('halation'));
 assert.ok(!normalizeWorkbenchDraft().features.includes('halation'));
});

test('latest-main SD records remain accepted and repaired corruption stays rejected',async()=>{
 const {preSquareArtRecord}=await import('./test-support/pre-square-records.mjs');
 const {readFileSync}=await import('node:fs');
 const {buildSdFilmPack,auditSdFilmPack,sdCrc}=await import('./gr3-sd-film-pack.mjs');
 const frozen=JSON.parse(readFileSync(new URL('./gr3-sd-pre-universal-halation-contract.json',import.meta.url)));
 const pack=buildSdFilmPack(auditSdFilmPack(buildSdFilmPack()).ids.filter(id=>frozen.ids.includes(id)&&id!==294));const count=pack.readUInt32LE(16);
 for(let i=0;i<count;i++){
  const record=pack.subarray(4096+i*12288,4096+(i+1)*12288);
  preSquareArtRecord(record.readUInt32LE(8)).copy(record);
  Buffer.from(frozen.renderer,'hex').copy(record,8448);
  record.writeUInt32LE(sdCrc(record.subarray(0,-4)),12284);pack.writeUInt32LE(record.readUInt32LE(12284),68+i*12);
 }
 pack.writeUInt32LE(sdCrc(pack.subarray(0,4092)),4092);assert.equal(auditSdFilmPack(pack).count,count);
 const r=pack.subarray(4096,4096+12288);r[64]^=1;r.writeUInt32LE(sdCrc(r.subarray(0,-4)),12284);
 pack.writeUInt32LE(r.readUInt32LE(12284),68);pack.writeUInt32LE(sdCrc(pack.subarray(0,4092)),4092);
 assert.throws(()=>auditSdFilmPack(pack),/校验|不兼容/);
});

test('restoring HDF-only draft removes dependent halation capability',()=>{
 const restored=normalizeWorkbenchDraft({profile:'native',features:['digitalHdf','halation'],nativeConfiguration:defaultConfiguration()});
 assert.ok(!restored.features.includes('film'));assert.ok(!restored.features.includes('halation'));
});
