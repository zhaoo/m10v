import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
test('GR II pinned source closure has exact recorded hashes',async()=>{
 const root=new URL('../compat/gr2-v1/',import.meta.url),report=JSON.parse(await readFile(new URL('PROVENANCE.json',root)));
 assert.match(report.revision,/^[a-f0-9]{40}$/);
 for(const [file,expected]of Object.entries(report.files)){
  assert.ok(!file.includes('..')&&!file.startsWith('/'));
  assert.equal(createHash('sha256').update(await readFile(new URL(file,root))).digest('hex'),expected,file);
 }
});

test('GR II square artwork closure remains pinned before GR III-only looks',async()=>{
 const root=new URL('../compat/gr2-square-v1/',import.meta.url),report=JSON.parse(await readFile(new URL('PROVENANCE.json',root)));
 assert.equal(report.revision,'a901016cd4f1ebfe917dbe195d2c5711af9309a1');
 assert.deepEqual(Object.keys(report.files).sort(),['native/gr3/m10v_film_card.c','native/gr3/m10v_film_card.h','native/gr3/m10v_film_card_data.h']);
 for(const [file,expected]of Object.entries(report.files))
  assert.equal(createHash('sha256').update(await readFile(new URL(file,root))).digest('hex'),expected,file);
});
