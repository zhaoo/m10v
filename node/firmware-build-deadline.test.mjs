import test from 'node:test';
import assert from 'node:assert/strict';
import {runFirmwareBuildPhase} from './firmware-build-deadline.mjs';

test('generation and independent reconstruction each receive a full bounded phase', async t => {
  t.mock.timers.enable({apis:['setTimeout']});
  const controller = new AbortController();
  const build = signal => new Promise(resolve => setTimeout(() => resolve(signal.aborted ? 'aborted' : 'built'), 40));
  const first = runFirmwareBuildPhase(controller.signal, build, 50);
  t.mock.timers.tick(40);
  assert.equal(await first, 'built');
  const repeated = runFirmwareBuildPhase(controller.signal, build, 50);
  t.mock.timers.tick(40);
  assert.equal(await repeated, 'built');
  assert.equal(controller.signal.aborted, false);
});

test('a stalled phase aborts its subprocess signal and reports a timeout', async t => {
  t.mock.timers.enable({apis:['setTimeout']});
  let childSignal;
  const pending = runFirmwareBuildPhase(new AbortController().signal, signal => {
    childSignal = signal;
    return new Promise((resolve,reject) => signal.addEventListener('abort', () => reject(Error('操作已取消')), {once:true}));
  }, 50);
  const rejected = assert.rejects(pending, {code:'M10V_BUILD_TIMEOUT'});
  t.mock.timers.tick(50);
  await rejected;
  assert.equal(childSignal.aborted, true);
});

test('caller cancellation still stops a running phase and preserves its reason', async () => {
  const controller = new AbortController(), reason = Error('cancelled by user');
  const pending = runFirmwareBuildPhase(controller.signal, signal => new Promise((resolve,reject) => {
    signal.addEventListener('abort', () => reject(signal.reason), {once:true});
  }));
  controller.abort(reason);
  await assert.rejects(pending, error => error === reason);
});

test('a phase cannot publish a late result after ignoring its deadline', async t => {
  t.mock.timers.enable({apis:['setTimeout']});
  const pending = runFirmwareBuildPhase(new AbortController().signal, () => new Promise(resolve => setTimeout(() => resolve('late firmware'),60)),50);
  const rejected = assert.rejects(pending, {code:'M10V_BUILD_TIMEOUT'});
  t.mock.timers.tick(60);
  await rejected;
});
