import test from 'node:test';
import assert from 'node:assert/strict';
import {exportSdFilms} from './gr3-sd-film-export.mjs';
import {createHash} from 'node:crypto';
import {validateQualityBinding} from './gr3-fit-binding.mjs';
import {decodeCustomIspPayload} from './gr3-custom-isp.mjs';

const cube='LUT_3D_SIZE 2\n0 0 0\n1 0 0\n0 1 0\n1 1 0\n0 0 1\n1 0 1\n0 1 1\n1 1 1\n';
for (const model of ['gr3','gr3x']) test(`${model}: named cube exports with built-in film in one SD pack`,async()=>{
 const result=await exportSdFilms({model,ids:[33],customFilms:[{name:'My Film',filename:'test.cube',base64:Buffer.from(cube).toString('base64')}]});
 assert.equal(result.receipt.count,2);
 assert.deepEqual(result.receipt.ids,[33,79]);
 assert.ok(result.zip.includes(Buffer.from('My Film')));
});
test('duplicate user film names fail export',async()=>{
 const entry={name:'My Film',filename:'test.cube',base64:Buffer.from(cube).toString('base64')};
 await assert.rejects(async()=>exportSdFilms({ids:[],customFilms:[entry,entry]}),/重复/);
});

test('custom SD export includes bound ISP approximation and keeps source identity explicit',async()=>{
 const result=await exportSdFilms({ids:[],customFilms:[{name:'My Film',filename:'test.cube',base64:Buffer.from(cube).toString('base64')}]});
 const assessment=result.receipt.custom_lut_assessment;
 assert.equal(assessment.status,'isp-approximation');assert.equal(assessment.isp_fit,true);
 assert.equal(assessment.source_sha256.length,1);
 assert.equal(assessment.profiles[0].quality.camera_verified,false);
 assert.equal(assessment.profiles[0].quality.envelope.encodable,true);
 assert.equal(assessment.profiles[0].look.curves[0].length,256);
 // The native writer composes a RELATIVE matrix with the existing Standard
 // frame. An identity source must not apply Standard's absolute matrix twice.
 assert.ok(assessment.profiles[0].look.matrixQ13.every((v,i)=>Math.abs(v-(i%4===0?8192:0))<32));
 assert.equal(assessment.profiles[0].quality.source_sha256,assessment.source_sha256[0]);
 assert.ok(result.zip.includes(Buffer.from('MISP')));
});
test('nonidentity custom LUT exports the measured fitted parameters consumed by the camera',async()=>{
 const rows=['LUT_3D_SIZE 2'];
 for(let b=0;b<2;b++)for(let g=0;g<2;g++)for(let r=0;r<2;r++)rows.push([.92*r+.08*g,.97*g+.03*r,.9*b+.1*g].join(' '));
 const source=Buffer.from(rows.join('\n')+'\n');
 const result=await exportSdFilms({ids:[],customFilms:[{name:'Warm custom',filename:'warm.cube',base64:source.toString('base64')}]});
 const {profiles,source_sha256}=result.receipt.custom_lut_assessment,report=profiles[0];
 assert.equal(source_sha256[0],createHash('sha256').update(source).digest('hex'));
 assert.equal(validateQualityBinding(report.look,report.quality),true);
 assert.ok(Number.isFinite(report.quality.validation.mean));assert.ok(report.quality.validation.p95>=report.quality.validation.mean);
 const at=result.zip.indexOf(Buffer.from('MISP')),encoded=decodeCustomIspPayload(result.zip.subarray(at+16,at+16+1572));
 assert.deepEqual(encoded,{matrixQ13:report.look.matrixQ13,postQ512:report.look.postQ512,curves:report.look.curves});
 assert.notDeepEqual(report.look.postQ512,[512,0,0,0,512,0,0,0,512]);
});
test('builtin-only asynchronous export does not need custom fitting',async()=>{
 const result=await exportSdFilms({ids:[33]});assert.equal(result.receipt.count,1);
 assert.equal(result.receipt.custom_lut_assessment,undefined);
});
test('unencodable inverted LUT is rejected without silently reducing its source strength',async()=>{
 const rows=['LUT_3D_SIZE 2'];
 for(let b=0;b<2;b++)for(let g=0;g<2;g++)for(let r=0;r<2;r++)rows.push([1-r,1-g,1-b].join(' '));
 await assert.rejects(()=>exportSdFilms({ids:[],customFilms:[{name:'Invert',filename:'invert.cube',base64:Buffer.from(rows.join('\n')+'\n').toString('base64')}]}),/ISP.*范围/);
});
