import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createFirmwareBuildQueue } from './firmware-build-queue.mjs';

function gate() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

const built = (value = 'firmware') => ({ candidate: Buffer.from(value), filename: 'firmware.bin' });
const code = (expected) => (error) => error.code === expected;

test('keeps generation and strict verification in one FIFO execution slot', async (t) => {
  const queue = createFirmwareBuildQueue();
  t.after(() => queue.close());
  const generating = gate();
  const verifying = gate();
  const inVerification = gate();
  const events = [];
  const first = queue.submit(async ({ setPhase }) => {
    events.push('first generating');
    await generating.promise;
    setPhase('verifying');
    events.push('first verifying');
    inVerification.resolve();
    await verifying.promise;
    return built('one');
  });
  const second = queue.submit(async () => {
    events.push('second generating');
    return built('two');
  });
  assert.match(first.id, /^[0-9a-f]{48}$/);
  assert.notEqual(first.id, second.id);
  assert.equal(queue.get(second.id).position, 1);
  generating.resolve();
  await inVerification.promise;
  assert.equal(queue.get(first.id).phase, 'verifying');
  assert.equal(queue.get(second.id).state, 'queued');
  assert.deepEqual(events, ['first generating', 'first verifying']);
  verifying.resolve();
  assert.equal((await queue.wait(first.id)).candidate.toString(), 'one');
  assert.equal((await queue.wait(second.id)).candidate.toString(), 'two');
  assert.deepEqual(events, ['first generating', 'first verifying', 'second generating']);
  assert.equal(queue.result(first.id).candidate.toString(), 'one');
  assert.equal((await queue.wait(first.id)).candidate.toString(), 'one');
});

test('bounds queued work separately from the active job and rejects overload', async (t) => {
  const queue = createFirmwareBuildQueue({ maxPending: 1 });
  t.after(() => queue.close());
  const hold = gate();
  const first = queue.submit(async () => { await hold.promise; return built(); });
  const second = queue.submit(async () => built());
  assert.throws(() => queue.submit(async () => built()), code('M10V_BUILD_QUEUE_FULL'));
  assert.equal(queue.cancel(second.id).state, 'cancelled');
  const third = queue.submit(async () => built());
  assert.equal(queue.get(third.id).position, 1);
  hold.resolve();
  await queue.wait(first.id);
  await queue.wait(third.id);
});

test('queued cancellation never executes its callback and rejects existing waiters', async (t) => {
  const queue = createFirmwareBuildQueue();
  t.after(() => queue.close());
  const hold = gate();
  const first = queue.submit(async () => { await hold.promise; return built(); });
  let executed = false;
  const second = queue.submit(async () => { executed = true; return built(); });
  const rejected = assert.rejects(queue.wait(second.id), code('M10V_BUILD_CANCELLED'));
  assert.equal(queue.cancel(second.id).state, 'cancelled');
  await rejected;
  hold.resolve();
  await queue.wait(first.id);
  assert.equal(executed, false);
  assert.equal(queue.result(second.id), null);
});

test('running cancellation aborts, prevents publication, and holds the slot until settled', async (t) => {
  const queue = createFirmwareBuildQueue();
  t.after(() => queue.close());
  const started = gate();
  const settle = gate();
  const nextStarted = gate();
  let signal;
  const first = queue.submit(async (context) => {
    signal = context.signal;
    started.resolve();
    await settle.promise;
    context.setPhase('verifying');
    return built('cancelled bytes');
  });
  const second = queue.submit(async () => { nextStarted.resolve(); return built('next'); });
  await started.promise;
  const rejected = assert.rejects(queue.wait(first.id), code('M10V_BUILD_CANCELLED'));
  assert.equal(queue.cancel(first.id).state, 'cancelled');
  assert.equal(signal.aborted, true);
  assert.equal(queue.get(second.id).state, 'queued');
  await rejected;
  settle.resolve();
  await nextStarted.promise;
  await queue.wait(second.id);
  assert.equal(queue.get(first.id).state, 'cancelled');
  assert.equal(queue.result(first.id), null);
});

test('failures and invalid or oversized results release the slot without retaining bytes', async (t) => {
  const queue = createFirmwareBuildQueue({ maxResultBytes: 4 });
  t.after(() => queue.close());
  const failure = new Error('build failed');
  const failed = queue.submit(async () => { throw failure; });
  await assert.rejects(queue.wait(failed.id), (error) => error === failure);
  assert.equal(queue.get(failed.id).state, 'failed');
  const invalid = queue.submit(async () => ({ candidate: 'not bytes', filename: 'x.bin' }));
  await assert.rejects(queue.wait(invalid.id), code('M10V_BUILD_RESULT_INVALID'));
  const oversized = queue.submit(async () => built('12345'));
  await assert.rejects(queue.wait(oversized.id), code('M10V_BUILD_RESULT_TOO_LARGE'));
  assert.equal(queue.result(oversized.id), null);
  const next = queue.submit(async () => built('1234'));
  assert.equal((await queue.wait(next.id)).candidate.length, 4);
});

test('evicts oldest ready results to enforce retained count and byte bounds', async (t) => {
  const queue = createFirmwareBuildQueue({ maxResults: 2, maxRetainedBytes: 5 });
  t.after(() => queue.close());
  const first = queue.submit(async () => built('123'));
  await queue.wait(first.id);
  const second = queue.submit(async () => built('456'));
  await queue.wait(second.id);
  assert.equal(queue.get(first.id).state, 'expired');
  assert.equal(queue.result(first.id), null);
  await assert.rejects(queue.wait(first.id), code('M10V_BUILD_EXPIRED'));
  const third = queue.submit(async () => built('7'));
  await queue.wait(third.id);
  const fourth = queue.submit(async () => built('8'));
  await queue.wait(fourth.id);
  assert.equal(queue.get(second.id).state, 'expired');
  assert.equal(queue.result(third.id).candidate.toString(), '7');
  assert.equal(queue.result(fourth.id).candidate.toString(), '8');
});

test('expires results lazily at the TTL boundary without consuming successful waits', async (t) => {
  let now = 100;
  const queue = createFirmwareBuildQueue({ ttlMs: 10, now: () => now });
  t.after(() => queue.close());
  const job = queue.submit(async () => built());
  await queue.wait(job.id);
  now = 109;
  assert.equal((await queue.wait(job.id)).candidate.toString(), 'firmware');
  now = 110;
  assert.equal(queue.result(job.id), null);
  assert.equal(queue.get(job.id).state, 'expired');
  await assert.rejects(queue.wait(job.id), code('M10V_BUILD_EXPIRED'));
});

test('metadata eviction removes old terminal jobs but never queued or active jobs', async (t) => {
  const queue = createFirmwareBuildQueue({ maxJobs: 2 });
  t.after(() => queue.close());
  const hold = gate();
  const first = queue.submit(async () => { await hold.promise; return built(); });
  const second = queue.submit(async () => built());
  assert.throws(() => queue.submit(async () => built()), code('M10V_BUILD_QUEUE_FULL'));
  queue.cancel(second.id);
  const third = queue.submit(async () => built());
  assert.equal(queue.get(second.id), null);
  assert.equal(queue.get(first.id).state, 'running');
  hold.resolve();
  await queue.wait(first.id);
  await queue.wait(third.id);
});

test('public snapshots exclude binary payloads, headers and audit internals', async (t) => {
  const queue = createFirmwareBuildQueue();
  t.after(() => queue.close());
  const job = queue.submit(async () => ({
    ...built('secret bytes'),
    headers: { 'X-Private': 'secret header' },
    audit: { binary: Buffer.from('secret audit') },
  }));
  await queue.wait(job.id);
  const snapshot = queue.get(job.id);
  const serialized = JSON.stringify(snapshot);
  assert.equal(serialized.includes('secret'), false);
  assert.equal('candidate' in snapshot, false);
  assert.equal('headers' in snapshot, false);
  assert.equal('audit' in snapshot, false);
  snapshot.state = 'failed';
  assert.equal(queue.get(job.id).state, 'ready');
  assert.equal(queue.cancel(job.id).state, 'cancelled');
  assert.equal(queue.result(job.id), null);
});

test('close aborts active work, cancels pending jobs and prevents further submissions', async () => {
  const queue = createFirmwareBuildQueue();
  const started = gate();
  const settle = gate();
  let signal;
  const first = queue.submit(async (context) => {
    signal = context.signal;
    started.resolve();
    await settle.promise;
    return built();
  });
  const second = queue.submit(async () => built());
  await started.promise;
  const firstRejected = assert.rejects(queue.wait(first.id), code('M10V_BUILD_CANCELLED'));
  const secondRejected = assert.rejects(queue.wait(second.id), code('M10V_BUILD_CANCELLED'));
  queue.close();
  assert.equal(signal.aborted, true);
  await Promise.all([firstRejected, secondRejected]);
  assert.equal(queue.result(first.id), null);
  assert.throws(() => queue.submit(async () => built()), code('M10V_BUILD_QUEUE_CLOSED'));
  settle.resolve();
  assert.equal(queue.get('unknown'), null);
  assert.equal(queue.cancel('unknown'), null);
  await assert.rejects(queue.wait('unknown'), code('M10V_BUILD_NOT_FOUND'));
});
