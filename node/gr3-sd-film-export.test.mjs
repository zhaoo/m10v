import test from 'node:test';
import assert from 'node:assert/strict';
import {exportSdFilms} from './gr3-sd-film-export.mjs';

const cube='LUT_3D_SIZE 2\n0 0 0\n1 0 0\n0 1 0\n1 1 0\n0 0 1\n1 0 1\n0 1 1\n1 1 1\n';
for (const model of ['gr3','gr3x']) test(`${model}: named cube exports with built-in film in one SD pack`,()=>{
 const result=exportSdFilms({model,ids:[33],customFilms:[{name:'My Film',filename:'test.cube',base64:Buffer.from(cube).toString('base64')}]});
 assert.equal(result.receipt.count,2);
 assert.deepEqual(result.receipt.ids,[33,79]);
 assert.ok(result.zip.includes(Buffer.from('My Film')));
});
test('duplicate user film names fail export',()=>{
 const entry={name:'My Film',filename:'test.cube',base64:Buffer.from(cube).toString('base64')};
 assert.throws(()=>exportSdFilms({ids:[],customFilms:[entry,entry]}),/重复/);
});

test('raw SD LUT manifest explicitly records unassessed CPU path without pretending ISP fit',()=>{const result=exportSdFilms({ids:[],customFilms:[{name:'My Film',filename:'test.cube',base64:Buffer.from(cube).toString('base64')}]});assert.equal(result.receipt.custom_lut_assessment.status,'legacy-unassessed');assert.equal(result.receipt.custom_lut_assessment.isp_fit,false);assert.equal(result.receipt.custom_lut_assessment.source_sha256.length,1);});
