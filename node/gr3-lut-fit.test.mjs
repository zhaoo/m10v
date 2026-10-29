import test from 'node:test';
import assert from 'node:assert/strict';
import { access } from 'node:fs/promises';
import { fitCube } from './gr3-lut-fit.mjs';

const available = await access(new URL('../.runtime/grlife/web/firmware-store/film-fit.js', import.meta.url))
  .then(() => true, () => false);
const identity = Buffer.from('LUT_3D_SIZE 2\n0 0 0\n1 0 0\n0 1 0\n1 1 0\n0 0 1\n1 0 1\n0 1 1\n1 1 1\n');

test('locally cached GRLife fitter turns a cube into both firmware fit options',
  { skip: !available }, async () => {
    const result = await fitCube(identity, 'identity.cube');
    assert.deepEqual(Object.keys(result.choices), ['tone', 'gamut']);
    assert.equal(result.choices.tone.look.curves[0].length, 256);
    assert.equal(result.choices.tone.look.knots[0].length, 33);
    assert.ok(result.choices.tone.note.fitMean < 0.01);
    assert.match(result.choices.tone.quality.provenance.fitter_sources['../.runtime/grlife/web/recipes/custom-recipe-core.js'],/^[0-9a-f]{64}$/);
  });

test('cube fit rejects wrong filenames and empty inputs', async () => {
  await assert.rejects(fitCube(identity, '../wrong.cube'), /sRGB/);
  await assert.rejects(fitCube(Buffer.alloc(0), 'empty.cube'), /non-empty|非空/);
});
test('cancelled fitting rejects instead of returning a stale result', async()=>{
 const controller=new AbortController();controller.abort();
 await assert.rejects(()=>fitCube(identity,'identity.cube',{signal:controller.signal}),/取消/);
});
test('abort while checking fitter availability cannot be missed', async()=>{
 const controller=new AbortController();const pending=fitCube(identity,'identity.cube',{signal:controller.signal});
 queueMicrotask(()=>controller.abort());await assert.rejects(pending,/取消/);
});
