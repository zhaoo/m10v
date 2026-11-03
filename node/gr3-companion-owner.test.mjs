import test from 'node:test';
import assert from 'node:assert/strict';
import {companionOwnerBytes,validateCompanionIdentity,companionSourceFingerprint} from './gr3-companion-owner.mjs';
test('companion owner extends allocation after unchanged effects regions',()=>{
 assert.equal(companionOwnerBytes({},0x613c),0x613c);
 const identity={buildId:'11'.repeat(32),catalogHash:'22'.repeat(32),rendererHash:'33'.repeat(32)};
 const m={companion:{enabled:true,schema:'m10v-companion-owner/v2',base:0x54100000,bytes:0x8000,descriptor_offset:0x6400,descriptor_bytes:64,owner_bytes:0x6440,payloadBytes:1024,identity,symbols:Object.fromEntries(['init','start','stop','timer'].map((n,i)=>['m10v_companion_ui_'+n,0x54100000+i*16]))}};
 assert.equal(companionOwnerBytes(m,0x613c),0x6440);
 for(const bad of [{...m.companion,descriptor_offset:0x613c},{...m.companion,enabled:false},{...m.companion,symbols:{}}])assert.throws(()=>companionOwnerBytes({companion:bad},0x613c));
 assert.deepEqual(validateCompanionIdentity(identity),identity);
 assert.throws(()=>validateCompanionIdentity({...identity,unknown:true}));
 assert.throws(()=>validateCompanionIdentity({...identity,buildId:'0'.repeat(64)}));
 assert.match(companionSourceFingerprint(),/^[a-f0-9]{64}$/);
});
