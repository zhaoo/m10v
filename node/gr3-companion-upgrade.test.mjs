import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
import {prepareNative} from './gr3-native-library.mjs';
import {defaultConfiguration} from '../web/gr3/native-library-state.mjs';
const official=new URL('../bin/fwdc239b-gr3-official.bin',import.meta.url);
test('preserve-existing policy is explicit, fingerprinted and boolean', {skip:!existsSync(official)},()=>{
 const source=readFileSync(official),config=defaultConfiguration();
 const plain=prepareNative(source,config),upgrade=prepareNative(source,config,{preserve_existing:true});
 assert.equal(upgrade.preserve_existing,true);
 assert.notEqual(upgrade.configuration_sha256,plain.configuration_sha256);
 assert.equal(upgrade.initial_state_hex,plain.initial_state_hex);
 assert.equal(upgrade.zoom_seed,null);
 assert.throws(()=>prepareNative(source,config,{preserve_existing:'yes'}),/preserve_existing/);
});
test('companion gate stays exact official GRIII 2.10', {skip:!existsSync(official)},()=>{
 const source=readFileSync(official),identity={buildId:'11'.repeat(32),catalogHash:'22'.repeat(32),rendererHash:'33'.repeat(32)};
 const options={companion_identity:identity,preserve_existing:true};
 assert.deepEqual(prepareNative(source,defaultConfiguration(),options).companion_identity,identity);
 for(const override of [{film_library:false},{appended_slots:false},{live_color:false}])
  assert.throws(()=>prepareNative(source,defaultConfiguration(),{...options,...override}),/companion|preserve_existing/);
});
