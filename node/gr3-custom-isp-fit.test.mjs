import test from 'node:test';
import assert from 'node:assert/strict';
import {STANDARD_LOOK_Q13} from '../.runtime/grlife/web/firmware-store/film-camera-model.js';
import {relativeFrameLook,nativeFrameModel,assessFit} from './gr3-fit-quality.mjs';
const identity=[8192,0,0,0,8192,0,0,0,8192];
const absolute=()=>({matrixQ13:[...STANDARD_LOOK_Q13],postQ512:[512,0,0,0,512,0,0,0,512],
 curves:[0,1,2].map(()=>Array.from({length:256},(_,i)=>i*64)),knots:[0,1,2].map(()=>Array.from({length:33},(_,i)=>Math.min(16383,i*512)))});
test('absolute Standard converts to relative identity and preserves actual Standard frame fields',()=>{
 const look=relativeFrameLook(absolute()),frame=nativeFrameModel(look);
 assert.deepEqual(look.matrixQ13,identity);
 assert.deepEqual(frame.contract.cca_signed12,[436,-184,4,-48,400,-96,1,-104,359]);
 assert.deepEqual(frame.contract.csp_signed9,[77,150,29,-43,-85,128,128,-107,-21]);
 assert.deepEqual(frame.violations,[]);
 const q=assessFit({look,target:rgb=>rgb,sourceSha256:'a'.repeat(64),frameRelative:true});
 assert.ok(q.validation.mean<.1);assert.equal(q.provenance.native_frame.schema,'m10v-relative-frame-fit/v1');
});
test('frame composition rejects hardware field overflow within otherwise valid int16 protocol',()=>{
 const look=relativeFrameLook(absolute());look.postQ512=[2048,-1536,0,0,512,0,0,0,512];
 assert.ok(nativeFrameModel(look).violations.includes('native signed9 CSP overflow'));
 const q=assessFit({look,target:rgb=>rgb,sourceSha256:'a'.repeat(64),frameRelative:true});
 assert.equal(q.envelope.encodable,false);
});
