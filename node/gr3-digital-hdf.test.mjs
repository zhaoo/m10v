import test from 'node:test';
import assert from 'node:assert/strict';
import {defaultConfiguration,normalizeConfiguration,resetNativeTexture} from '../web/gr3/native-library-state.mjs';
import {initialState,prepareNative,readNativeOfficial,generateNative} from './gr3-native-library.mjs';
import {hdfPatches} from './gr3-digital-hdf.mjs';

test('digital HDF is independent of films and retired soft values never become HDF',()=>{
 const old=defaultConfiguration();delete old.hdf;old.slots[0].soft=3;
 const c=normalizeConfiguration(old);
 assert.equal(c.hdf,0);assert.ok(c.slots.every(s=>s.soft===0));
 c.hdf=2;assert.equal(resetNativeTexture(c,0).hdf,2);
 assert.deepEqual(initialState(c),initialState({...c,hdf:0}));
 for(const hdf of [-1,4,1.5,'2',null])assert.throws(()=>normalizeConfiguration({...c,hdf}));
});
test('exported HDF candidate independently verifies coefficients and rejects changed ARM instructions',{timeout:120000},async()=>{
 const source=await readNativeOfficial(),c=defaultConfiguration();c.hdf=2;
 const plan=prepareNative(source,c),result=await generateNative(source,c,plan.configuration_sha256);
 assert.equal(result.receipt.configuration.hdf,2);assert.equal(result.manifest.hdf_default,2);assert.equal(result.receipt.camera_tested,false);
 assert.equal(hdfPatches(result.runtime,result.manifest).length,3);
 for(const address of [result.manifest.digital_hdf.rows,result.manifest.digital_hdf.entries.request,result.manifest.digital_hdf.rows-48]){
  const broken=Buffer.from(result.runtime);broken[address-result.manifest.base]^=1;
  assert.throws(()=>hdfPatches(broken,result.manifest),/digital HDF/);
 }
});
test('HDF strength is covered by the export hash and readback plan',async()=>{
 const source=await readNativeOfficial(),c=defaultConfiguration();c.hdf=1;
 const weak=prepareNative(source,c);c.hdf=3;const strong=prepareNative(source,c);
 assert.notEqual(weak.configuration_sha256,strong.configuration_sha256);
 assert.equal(strong.configuration.hdf,3);assert.ok(strong.features.includes('digitalHdf'));
 assert.ok(!strong.features.includes('soft'));
});
test('GR III with HDF enabled at off strength still installs the camera menu',{timeout:120000},async()=>{
 const source=await readNativeOfficial(),configuration=defaultConfiguration();
 configuration.filmNameStamp=true;
 const plan=prepareNative(source,configuration,{hdf_enabled:true});
 const result=await generateNative(source,configuration,plan.configuration_sha256,{hdf_enabled:true});
 assert.equal(result.manifest.hdf_enabled,true);
 assert.equal(result.manifest.hdf_default,0);
 assert.equal(result.manifest.hdf_menu.route,0x0200f102);
 assert.deepEqual(result.manifest.hdf_menu.resource_ids,[970,971,972,973,974,975,976,977]);
 assert.equal(result.receipt.configuration.hdf,0);
 assert.equal(result.receipt.configuration.filmNameStamp,true);
});

test('HDF alone preserves original film entry points and has an independent menu',{timeout:120000},async()=>{
 const source=await readNativeOfficial(),c=defaultConfiguration();c.hdf=2;
 const options={film_library:false},plan=prepareNative(source,c,options);
 assert.deepEqual(plan.features,['digitalHdf']);assert.equal(plan.film_count,0);
 assert.notEqual(plan.configuration_sha256,prepareNative(source,c).configuration_sha256);
 const result=await generateNative(source,c,plan.configuration_sha256,options);
 assert.ok(result.receipt.verified_hooks>20,'independent ADJ and icon routing add audited hooks');assert.equal(result.receipt.film_library_enabled,false);
 assert.equal(result.manifest.hdf_adj.function_id,20);assert.equal(result.manifest.hdf_adj.record_count,21);
 assert.equal(result.manifest.hdf_adj.original_table_bytes,20*0x44);
 assert.equal(result.manifest.hdf_menu.owner_offset,0x13bc);assert.equal(result.manifest.hdf_default,2);
 const {decodeFrameMap}=await import('./gr3-frames.mjs');
 const rtos=bytes=>{const d=decodeFrameMap(bytes,bytes.readUInt32LE(bytes.length-8)).decoded;for(let at=0;at<d.length;){const n=d.readUInt32LE(at+12);if(d.toString('ascii',at,at+4)==='RTOS')return d.subarray(at+16,at+16+n);at+=16+n;}throw Error('RTOS missing');};
 const before=rtos(source),after=rtos(result.candidate);
 for(const address of [0x531ab78c,0x531b05e4,0x532922b4,0x532935dc,0x535239c0])assert.deepEqual(after.subarray(address-0x53000000,address-0x53000000+4),before.subarray(address-0x53000000,address-0x53000000+4));
});
