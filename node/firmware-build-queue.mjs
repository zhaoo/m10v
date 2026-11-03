import { randomBytes } from 'node:crypto';

const MiB = 1024 * 1024;
const terminalStates = new Set(['ready', 'failed', 'cancelled', 'expired']);

function buildError(code, message) {
  return Object.assign(new Error(message), { code });
}

/** A process-local FIFO queue. IDs are bearer capabilities; snapshots contain no result data. */
export function createFirmwareBuildQueue(options = {}) {
  const limits = {
    maxPending: options.maxPending ?? 4,
    maxJobs: options.maxJobs ?? 32,
    maxResults: options.maxResults ?? 2,
    maxResultBytes: options.maxResultBytes ?? 70 * MiB,
    maxRetainedBytes: options.maxRetainedBytes ?? 96 * MiB,
    ttlMs: options.ttlMs ?? 3 * 60 * 1000,
  };
  for (const [name, value] of Object.entries(limits)) {
    const minimum = name === 'maxPending' ? 0 : 1;
    if (!Number.isSafeInteger(value) || value < minimum) {
      throw new TypeError(`${name} must be an integer >= ${minimum}`);
    }
  }
  const now = options.now ?? Date.now;
  if (typeof now !== 'function') throw new TypeError('now must be a function');
  const jobs = new Map();
  const pending = [];
  const ready = [];
  let active = null;
  let retainedBytes = 0;
  let terminalOrder = 0;
  let closed = false;

  function snapshot(job) {
    return {
      id: job.id,
      state: job.state,
      phase: job.phase,
      position: job.state === 'queued' ? pending.indexOf(job) + 1 : 0,
      createdAt: job.createdAt,
      updatedAt: job.updatedAt,
      expiresAt: job.expiresAt,
      ...(job.error ? { error: { code: job.error.code ?? 'M10V_BUILD_FAILED', message: job.error.message } } : {}),
    };
  }

  function releaseResult(job) {
    if (!job.value) return;
    retainedBytes -= job.value.candidate.length;
    job.value = null;
    const index = ready.indexOf(job);
    if (index !== -1) ready.splice(index, 1);
  }

  function notify(job) {
    for (const waiter of job.waiters) {
      if (job.state === 'ready') waiter.resolve(job.value);
      else waiter.reject(job.error);
    }
    job.waiters = [];
  }

  function terminate(job, state, error) {
    releaseResult(job);
    job.state = state;
    job.error = error;
    job.updatedAt = now();
    job.terminalOrder = ++terminalOrder;
    job.run = null;
    notify(job);
  }

  function expire(job) {
    terminate(job, 'expired', buildError('M10V_BUILD_EXPIRED', 'Firmware build result expired'));
  }

  function sweep() {
    const time = now();
    for (const job of [...ready]) {
      if (time >= job.expiresAt) expire(job);
    }
  }

  function pump() {
    if (active || closed || pending.length === 0) return;
    const job = pending.shift();
    active = job;
    job.state = 'running';
    job.phase = 'generating';
    job.updatedAt = now();
    // Reserve the slot synchronously, but do not invoke user code inside submit().
    void execute(job);
  }

  async function execute(job) {
    try {
      await Promise.resolve();
      if (job.state !== 'running') return;
      const run = job.run;
      job.run = null;
      const value = await run({
        signal: job.controller.signal,
        setPhase(phase) {
          if (job.state !== 'running' || job.controller.signal.aborted) return;
          if (phase !== 'generating' && phase !== 'verifying') {
            throw new TypeError('Build phase must be generating or verifying');
          }
          job.phase = phase;
          job.updatedAt = now();
        },
      });
      // A run may ignore AbortSignal or finish concurrently with cancellation.
      if (job.state !== 'running' || job.controller.signal.aborted || closed) return;
      if (!value || !Buffer.isBuffer(value.candidate) || value.candidate.length === 0
        || typeof value.filename !== 'string' || value.filename.length === 0) {
        throw buildError('M10V_BUILD_RESULT_INVALID', 'Firmware build must return bytes and a filename');
      }
      if (value.candidate.length > limits.maxResultBytes
        || value.candidate.length > limits.maxRetainedBytes) {
        throw buildError('M10V_BUILD_RESULT_TOO_LARGE', 'Firmware build result exceeds the retained byte limit');
      }
      sweep();
      while (ready.length >= limits.maxResults
        || retainedBytes + value.candidate.length > limits.maxRetainedBytes) {
        expire(ready[0]);
      }
      job.value = {
        candidate: value.candidate,
        filename: value.filename,
        ...(value.headers === undefined ? {} : { headers: value.headers }),
        ...(value.audit === undefined ? {} : { audit: value.audit }),
      };
      retainedBytes += job.value.candidate.length;
      ready.push(job);
      job.state = 'ready';
      job.updatedAt = now();
      job.expiresAt = job.updatedAt + limits.ttlMs;
      job.terminalOrder = ++terminalOrder;
      notify(job);
    } catch (error) {
      if (job.state === 'running') {
        terminate(job, 'failed', error instanceof Error ? error : new Error(String(error)));
      }
    } finally {
      job.run = null;
      active = null;
      pump();
    }
  }

  function cancelJob(job) {
    if (job.state === 'failed' || job.state === 'cancelled' || job.state === 'expired') return;
    const index = pending.indexOf(job);
    if (index !== -1) pending.splice(index, 1);
    terminate(job, 'cancelled', buildError('M10V_BUILD_CANCELLED', 'Firmware build cancelled'));
    job.controller.abort(job.error);
  }

  return {
    submit(run) {
      sweep();
      if (closed) throw buildError('M10V_BUILD_QUEUE_CLOSED', 'Firmware build queue is closed');
      if (typeof run !== 'function') throw new TypeError('run must be a function');
      if (active && pending.length >= limits.maxPending) {
        throw buildError('M10V_BUILD_QUEUE_FULL', 'Firmware build queue is full');
      }
      while (jobs.size >= limits.maxJobs) {
        const oldest = [...jobs.values()]
          .filter((job) => job !== active && terminalStates.has(job.state))
          .sort((a, b) => a.terminalOrder - b.terminalOrder)[0];
        if (!oldest) throw buildError('M10V_BUILD_QUEUE_FULL', 'Firmware build metadata limit reached');
        releaseResult(oldest);
        jobs.delete(oldest.id);
      }
      let id;
      do { id = randomBytes(24).toString('hex'); } while (jobs.has(id));
      const time = now();
      const job = {
        id, state: 'queued', phase: null, createdAt: time, updatedAt: time,
        expiresAt: null, controller: new AbortController(), run, value: null,
        error: null, waiters: [], terminalOrder: 0,
      };
      jobs.set(id, job);
      pending.push(job);
      pump();
      return snapshot(job);
    },
    get(id) {
      sweep();
      const job = jobs.get(id);
      return job ? snapshot(job) : null;
    },
    result(id) {
      sweep();
      const job = jobs.get(id);
      return job?.state === 'ready' ? job.value : null;
    },
    cancel(id) {
      sweep();
      const job = jobs.get(id);
      if (!job) return null;
      cancelJob(job);
      return snapshot(job);
    },
    wait(id) {
      sweep();
      const job = jobs.get(id);
      if (!job) return Promise.reject(buildError('M10V_BUILD_NOT_FOUND', 'Firmware build not found'));
      if (job.state === 'ready') return Promise.resolve(job.value);
      if (terminalStates.has(job.state)) return Promise.reject(job.error);
      return new Promise((resolve, reject) => job.waiters.push({ resolve, reject }));
    },
    close() {
      closed = true;
      for (const job of jobs.values()) cancelJob(job);
    },
  };
}
