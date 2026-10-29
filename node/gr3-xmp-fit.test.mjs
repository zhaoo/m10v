import test from 'node:test';import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';
import * as xmp from './gr3-xmp-fit.mjs';
test('complete identity Look is rendered locally and fitted to GR III matrices',async()=>{
 const bytes=readFileSync(new URL('../tests/fixtures/gr3-identity.xmp',import.meta.url));
 const result=await xmp.fitXmp(bytes,'identity.xmp');
 assert.match(result.choices.tone.quality.provenance.fitter_sources['../vendor/gr4/gr4_editor/offline_look.py'],/^[0-9a-f]{64}$/);
 assert.equal(result.provenance.targetModel,'GR III');assert.equal(result.provenance.approximate,true);
 assert.ok(result.choices.tone.note.fitMean<0.05);assert.equal(result.choices.tone.look.curves[0].length,256);
});
test('incomplete profiles, external entities and wrong input types fail explicitly',async()=>{
 for(const bytes of [Buffer.from('<root/>'),Buffer.from('<!DOCTYPE x [<!ENTITY y SYSTEM "file:///etc/passwd">]><x/>')])
   await assert.rejects(()=>xmp.fitXmp(bytes,'bad.xmp'),/Look|DOCTYPE|XMP/);
 await assert.rejects(()=>xmp.fitXmp(Buffer.alloc(0),'empty.xmp'),/XMP/);
});
