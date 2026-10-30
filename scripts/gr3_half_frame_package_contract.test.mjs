import test from 'node:test';
import assert from 'node:assert/strict';
import {auditHalfPair,validateChecks,packageReadme,LOG_FILES} from './gr3_half_frame_package_contract.mjs';
function fixture(){
 const runtime=Buffer.alloc(128),base=0x540be000,callsite=base+16,target=base+64;
 runtime.writeUInt32LE((0xeb000000|((target-callsite-8)>>2))>>>0,16);
 const p={enabled:true,schema:'m10v-half-pair/v1',storage:'C:\\M10V\\HALFPAIR.BIN',first_original_preserved:true,camera_tested:false,handoff:{callsite,target}};
 return {manifest:{base,half_pair:p},receipt:{composition:{half_pair:structuredClone(p)}},runtime};
}
test('accepts pair capability with an actual bounded ARM call',()=>{
 const f=fixture();assert.equal(auditHalfPair(f.manifest,f.receipt,f.runtime),f.manifest.half_pair);
});
test('rejects old crop-only receipt even when Half is enabled',()=>{
 const f=fixture();delete f.receipt.composition.half_pair;f.receipt.composition.half_frame={enabled:true};
 assert.throws(()=>auditHalfPair(f.manifest,f.receipt,f.runtime),/capability/);
});
test('rejects unbound handoff, outside runtime, false original-preservation and false camera acceptance',()=>{
 for(const mutate of [f=>f.runtime.writeUInt32LE(0xe1a00000,16),f=>f.runtime.writeUInt32LE(0xeb000001,16),
 f=>{f.manifest.half_pair.handoff.callsite=f.manifest.base-4;},
 f=>{f.manifest.half_pair.first_original_preserved=false;},f=>{f.manifest.half_pair.camera_tested=true;}]){
  const f=fixture();mutate(f);assert.throws(()=>auditHalfPair(f.manifest,f.receipt,f.runtime));
 }
});
test('checks require fresh explicit logs and successful required status',()=>{
 const valid={checks:[{name:'Final ARM caller',log:'/tmp/final.log',exit_code:0}]};
 assert.equal(validateChecks(valid),valid.checks);
 assert.throws(()=>validateChecks({checks:[]}));
 assert.throws(()=>validateChecks({checks:[{...valid.checks[0],exit_code:1}]}));
 assert.throws(()=>validateChecks({checks:[valid.checks[0],valid.checks[0]]}));
 const historical={checks:[{name:'Full suite',log:'all.log',exit_code:1,required:false}]};
 assert.equal(validateChecks(historical)[0].exit_code,1);
});
test('readme binds candidate identity, eight log files and actual checks without camera claims',()=>{
 const text=packageReadme({buildId:'12345678',binSha:'abcd',officialSha:'ef01',checks:[{name:'Final callers',exit_code:0}]});
 for(const file of LOG_FILES)assert.ok(text.includes(file));
 assert.ok(text.includes('12345678'));assert.ok(text.includes('第一张仍保存原始单张 JPEG'));
 assert.ok(text.includes('设备尚未验收'));assert.ok(text.includes('Final callers：exit 0'));
 assert.ok(!text.includes('403通过'));
});
