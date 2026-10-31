import test from 'node:test';
import assert from 'node:assert/strict';
import {readNativeOfficial,prepareNative} from './gr3-native-library.mjs';
import {defaultConfiguration} from '../web/gr3/native-library-state.mjs';

test('A/B is opt-in and its switch is bound to the accepted build configuration',async()=>{
 const source=await readNativeOfficial('gr3'),config=defaultConfiguration();
 const off=prepareNative(source,config),on=prepareNative(source,config,{ab_enabled:true});
 assert.equal(off.ab_enabled,false);assert.equal(on.ab_enabled,true);
 assert.notEqual(on.configuration_sha256,off.configuration_sha256);
 assert.ok(on.features.includes('abCompare'));assert.ok(!off.features.includes('abCompare'));
 assert.throws(()=>prepareNative(source,config,{ab_enabled:1}),/A\/B/);
 assert.throws(()=>prepareNative(source,config,{film_library:false,ab_enabled:true}),/A\/B/);
});
