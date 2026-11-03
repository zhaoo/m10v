import test from 'node:test';
import assert from 'node:assert/strict';
import { runFirmwareJob } from '../web/gr3/firmware-job-client.mjs';

const projectId = 'a'.repeat(64);
const jobId = 'b'.repeat(48);
const otherJobId = 'c'.repeat(48);
const response = job => Response.json({ job });
const gate = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };

function service({ snapshots = [], creation, statusGate, failPoll = false } = {}) {
  const events = [];
  let cancelled = 0;
  let downloads = 0;
  let polls = 0;
  let current = { id: jobId, state: 'queued', phase: null };
  const api = async (path, options = {}) => {
    if (path === `/api/projects/${projectId}/native-library/jobs`) {
      events.push('create');
      assert.equal(options.method, 'POST');
      assert.deepEqual(JSON.parse(options.body), { film: 'test' });
      assert.equal(options.signal, undefined, 'creation must survive caller cancellation until its ID is known');
      if (creation) current = await creation.promise;
      return response(current);
    }
    if (path === `/api/firmware-jobs/${jobId}/cancel`) {
      assert.equal(options.method, 'POST');
      assert.deepEqual(JSON.parse(options.body), {});
      assert.equal(options.keepalive, true);
      assert.equal(options.signal, undefined);
      cancelled++;
      current = { ...current, state: 'cancelled' };
      events.push('cancel');
      return response(current);
    }
    if (path === `/api/firmware-jobs/${jobId}/download`) {
      assert.equal(current.state, 'ready', 'an unready server result cannot be downloaded');
      assert.equal(options.headers.Accept, 'multipart/form-data');
      downloads++;
      events.push('download');
      return new Response('verified candidate');
    }
    if (path === `/api/firmware-jobs/${jobId}`) {
      polls++;
      if (statusGate) await statusGate.promise;
      if (failPoll) throw new Error('https://private.example/internal/error');
      current = snapshots.shift() || current;
      events.push(`poll:${current.state}:${current.phase || ''}`);
      return response(current);
    }
    throw new Error(`Unexpected URL ${path}`);
  };
  return { api, events, get cancelled() { return cancelled; }, get downloads() { return downloads; }, get polls() { return polls; } };
}

test('waits through queue, generation, and verification before returning download bytes', async () => {
  const server = service({ snapshots: [
    { id: jobId, state: 'running', phase: 'generating' },
    { id: jobId, state: 'running', phase: 'verifying' },
    { id: jobId, state: 'ready', phase: 'verifying' },
  ] });
  const progress = [];
  const controller = new AbortController();
  const result = await runFirmwareJob(server.api, projectId, { film: 'test' }, {
    intervalMs: 0, signal: controller.signal,
    onProgress: job => { progress.push(`${job.state}:${job.phase || ''}`); assert.equal(server.downloads, 0); },
  });
  assert.equal(await result.text(), 'verified candidate');
  assert.deepEqual(progress, ['queued:', 'running:generating', 'running:verifying', 'ready:verifying']);
  assert.equal(server.downloads, 1);
  controller.abort();
  await Promise.resolve();
  assert.equal(server.cancelled, 0, 'finished download must detach cancellation');
});

test('failed, cancelled, and expired jobs never yield a download', async () => {
  for (const state of ['failed', 'cancelled', 'expired']) {
    const server = service({ snapshots: [{ id: jobId, state, error: { message: 'https://secret.example/' } }] });
    await assert.rejects(runFirmwareJob(server.api, projectId, { film: 'test' }, { intervalMs: 0 }), error => /失败|取消|过期/.test(error.message) && !error.message.includes('https:'));
    assert.equal(server.downloads, 0);
  }
});

test('cancels queued job once and interrupts a long polling wait', async () => {
  const server = service();
  const controller = new AbortController();
  const result = runFirmwareJob(server.api, projectId, { film: 'test' }, {
    signal: controller.signal, intervalMs: 60_000,
    onProgress: () => controller.abort(),
  });
  await assert.rejects(result, /取消/);
  assert.equal(server.cancelled, 1);
  assert.equal(server.downloads, 0);
  assert.equal(server.polls, 0);
});

test('cancellation during creation waits for returned job ID then cancels it', async () => {
  const creation = gate();
  const server = service({ creation });
  const controller = new AbortController();
  const result = runFirmwareJob(server.api, projectId, { film: 'test' }, { signal: controller.signal, intervalMs: 0 });
  controller.abort();
  assert.equal(server.cancelled, 0);
  creation.resolve({ id: jobId, state: 'queued' });
  await assert.rejects(result, /取消/);
  assert.equal(server.cancelled, 1);
  assert.equal(server.downloads, 0);
  assert.deepEqual(server.events, ['create', 'cancel']);
});

test('aborted in-flight polling cannot download a later ready result', async () => {
  const statusGate = gate();
  const server = service({ statusGate, snapshots: [{ id: jobId, state: 'ready' }] });
  const controller = new AbortController();
  const enteredPoll = gate();
  const api = (path, options) => { const pending = server.api(path, options); if (path === `/api/firmware-jobs/${jobId}`) enteredPoll.resolve(); return pending; };
  const result = runFirmwareJob(api, projectId, { film: 'test' }, { signal: controller.signal, intervalMs: 0 });
  await enteredPoll.promise;
  controller.abort();
  await assert.rejects(result, /取消/);
  statusGate.resolve();
  await Promise.resolve();
  assert.equal(server.cancelled, 1);
  assert.equal(server.downloads, 0);
});

test('rejects malformed and stale job identities without downloading arbitrary URLs', async () => {
  for (const snapshot of [
    { id: '../download', state: 'ready' }, { id: 'https://secret.example', state: 'ready' },
    { id: otherJobId, state: 'ready' }, { id: jobId, state: 'unknown' },
    { id: jobId, state: 'ready', expiresAt: Date.now() - 1 },
  ]) {
    const server = service({ snapshots: [snapshot] });
    await assert.rejects(runFirmwareJob(server.api, projectId, { film: 'test' }, { intervalMs: 0 }), /任务|过期/);
    assert.equal(server.downloads, 0);
    assert.equal(server.cancelled, 1);
  }
  const creation = gate(); creation.resolve({ id: 'https://secret.example', state: 'ready' });
  const server = service({ creation });
  await assert.rejects(runFirmwareJob(server.api, projectId, { film: 'test' }), /任务/);
  assert.deepEqual(server.events, ['create']);
});

test('poll API failure cancels the known job and exposes only a local Chinese error', async () => {
  const server = service({ failPoll: true });
  await assert.rejects(runFirmwareJob(server.api, projectId, { film: 'test' }, { intervalMs: 0 }), error => /任务|构建/.test(error.message) && !error.message.includes('https:'));
  assert.equal(server.cancelled, 1);
  assert.equal(server.downloads, 0);
});

test('already aborted callers and invalid project IDs do not create jobs', async () => {
  const server = service();
  const controller = new AbortController(); controller.abort();
  await assert.rejects(runFirmwareJob(server.api, projectId, {}, { signal: controller.signal }), /取消/);
  await assert.rejects(runFirmwareJob(server.api, '../elsewhere', {}), /项目/);
  assert.deepEqual(server.events, []);
});
