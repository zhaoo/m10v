import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {prepareGr2Native,generateGr2Native} from './gr2-native-library.mjs';
import {defaultConfiguration} from '../web/gr2/native-library-state.mjs';
const source=()=>readFile(new URL('../bin/rg2_v003.frm',import.meta.url));
// New square artwork changes the runtime while the frozen recipe ABI stays v4.
const defaultSquareRuntimeSha='8f677dc16efa9e0c07413dd5de8c67639a3def545d95c37565e72ead7fd9dd1f';
test('GR2 plan binds independent initial HDF and rejects invalid grades',async()=>{
 const b=await source(),c=defaultConfiguration(),a=await prepareGr2Native(b,c);c.slots[0].grain=2;
 assert.notEqual((await prepareGr2Native(b,c)).configuration_sha256,a.configuration_sha256);
 await assert.rejects(generateGr2Native(b,c,a.configuration_sha256),/重新预检/);
 const hashes=new Set();for(const strength of [0,1,2,3]){c.hdf=strength;const plan=await prepareGr2Native(b,c);assert.equal(plan.initial_hdf_strength,strength);hashes.add(plan.configuration_sha256);}assert.equal(hashes.size,4);c.hdf=4;await assert.rejects(prepareGr2Native(b,c),/HDF/);
 const abort=new AbortController();abort.abort();await assert.rejects(generateGr2Native(b,c,'',{signal:abort.signal}),{name:'AbortError'});
});
test('GR2 actual native build reconstructs and packages exact candidate',async()=>{
 const b=await source(),c=defaultConfiguration(),plan=await prepareGr2Native(b,c),result=await generateGr2Native(b,c,plan.configuration_sha256);
 assert.equal(result.receipt.verified,true);assert.equal(result.receipt.independent_component_reconstruction,true);
 assert.equal(result.receipt.hardware_verified,false);assert.equal(result.receipt.release_ready,false);
 assert.equal(result.runtime.runtime_sha256,defaultSquareRuntimeSha);assert.equal(result.runtime.can_package,false);assert.equal(result.audit.activation_ready,false);
});

test('GR II ABI remains five slots while GR III uses ten-slot v5',async()=>{
 const {normalizeConfiguration}=await import('../web/gr2/native-library-state.mjs');
 const {initialState}=await import('../compat/gr2-v1/node/gr3-native-library.mjs');
 const c=defaultConfiguration();c.slots[0].grain=3;c.slots[0].effects.leakGain=4;
 assert.equal(initialState(c).length,104);assert.equal(initialState(c).readUInt16LE(4),4);
 assert.equal(normalizeConfiguration(c).slots[0].effects.leakGain,4);
 assert.throws(()=>normalizeConfiguration({...c,slots:[...c.slots,...c.slots]}));
});

test('GR2 nonzero initial HDF is compiled and bound into the verified candidate receipt',async()=>{
 const b=await source(),c=defaultConfiguration();c.hdf=3;
 const plan=await prepareGr2Native(b,c),result=await generateGr2Native(b,c,plan.configuration_sha256);
 assert.equal(result.runtime.initial_hdf_strength,3);assert.equal(result.receipt.initial_hdf_strength,3);
 assert.equal(result.plan.configuration.hdf,3);assert.equal(result.receipt.configuration_sha256,plan.configuration_sha256);
 assert.notEqual(result.runtime.runtime_sha256,defaultSquareRuntimeSha);
 assert.equal(result.receipt.hardware_verified,false);assert.equal(result.receipt.release_ready,false);
});
