const JOB_ID = /^[a-f0-9]{48}$/;
const PROJECT_ID = /^[a-f0-9]{64}$/;
const MAX_POLLING_MS = 20 * 60 * 1000;
const ACTIVE_STATES = new Set(['queued', 'running', 'generating', 'verifying', 'ready']);

class FirmwareJobError extends Error {}

function abortedError() {
  return new FirmwareJobError('固件构建任务已取消。');
}

function abortable(pending, signal) {
  return new Promise((resolve, reject) => {
    const abort = () => reject(abortedError());
    signal.addEventListener('abort', abort, { once: true });
    Promise.resolve(pending).then(value => {
      signal.removeEventListener('abort', abort);
      if (signal.aborted) reject(abortedError());
      else resolve(value);
    }, error => {
      signal.removeEventListener('abort', abort);
      reject(error);
    });
    if (signal.aborted) abort();
  });
}

function wait(ms, signal) {
  return new Promise((resolve, reject) => {
    const abort = () => { clearTimeout(timer); signal.removeEventListener('abort', abort); reject(abortedError()); };
    const timer = setTimeout(() => { signal.removeEventListener('abort', abort); resolve(); }, ms);
    signal.addEventListener('abort', abort, { once: true });
    if (signal.aborted) abort();
  });
}

/** Run one server build job, retaining its identity until cancellation can be delivered. */
export async function runFirmwareJob(api, projectId, input, { signal, onProgress, intervalMs = 1000 } = {}) {
  if (typeof projectId !== 'string' || !PROJECT_ID.test(projectId)) throw new FirmwareJobError('固件构建项目标识无效。');
  if (!Number.isFinite(intervalMs) || intervalMs < 0 || intervalMs > 60_000) throw new FirmwareJobError('固件构建任务轮询间隔无效。');
  if (signal?.aborted) throw abortedError();
  const lifecycle = new AbortController();
  let jobId;
  let cancellationSent = false;
  let timedOut = false;
  const cancel = () => {
    if (!jobId || cancellationSent) return;
    cancellationSent = true;
    try {
      // Do not reuse either aborted signal: the server still needs the cancellation.
      void Promise.resolve(api(`/api/firmware-jobs/${jobId}/cancel`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}', keepalive: true,
      })).catch(() => {});
    } catch { /* Cancellation is best effort when the network is unavailable. */ }
  };
  const abort = () => { lifecycle.abort(); cancel(); };
  signal?.addEventListener('abort', abort, { once: true });
  const timeout = setTimeout(() => { timedOut = true; abort(); }, MAX_POLLING_MS);
  const ensureActive = () => {
    if (timedOut) throw new FirmwareJobError('固件构建任务等待超时，请重新生成。');
    if (signal?.aborted || lifecycle.signal.aborted) throw abortedError();
  };
  const readJob = async result => {
    const payload = await result.json();
    const job = payload?.job;
    if (!job || typeof job !== 'object' || Array.isArray(job) || typeof job.id !== 'string' || !JOB_ID.test(job.id)
        || (jobId && job.id !== jobId)) throw new FirmwareJobError('固件构建任务标识无效或已变化，请重新生成。');
    return job;
  };
  try {
    // Creation intentionally has no caller signal. If cancelled in flight, obtain the
    // returned ID first so an orphaned server build can still be cancelled.
    let job = await readJob(await api(`/api/projects/${projectId}/native-library/jobs`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input),
    }));
    jobId = job.id;
    for (;;) {
      ensureActive();
      if (job.state === 'failed') throw new FirmwareJobError('固件构建或离线验证失败，请重新生成。');
      if (job.state === 'cancelled') throw abortedError();
      if (job.state === 'expired' || (job.expiresAt != null && (!Number.isFinite(job.expiresAt) || job.expiresAt <= Date.now()))) {
        throw new FirmwareJobError('固件构建任务结果已过期，请重新生成。');
      }
      if (!ACTIVE_STATES.has(job.state)) throw new FirmwareJobError('固件构建任务状态无效，请重新生成。');
      onProgress?.(job);
      ensureActive();
      if (job.state === 'ready') {
        const result = await abortable(api(`/api/firmware-jobs/${jobId}/download`, {
          method: 'GET', headers: { Accept: 'multipart/form-data' }, signal: lifecycle.signal,
        }), lifecycle.signal);
        ensureActive();
        if (!(result instanceof Response)) throw new FirmwareJobError('固件构建任务下载响应无效。');
        return result;
      }
      // Keep waits short and abortable; each status request completes before the next.
      const nextPoll = Date.now() + intervalMs;
      do {
        await wait(Math.min(1000, Math.max(0, nextPoll - Date.now())), lifecycle.signal);
        ensureActive();
      } while (Date.now() < nextPoll);
      job = await abortable((async () => readJob(await api(`/api/firmware-jobs/${jobId}`, {
        method: 'GET', signal: lifecycle.signal,
      })))(), lifecycle.signal);
    }
  } catch (error) {
    cancel();
    ensureActive();
    if (error instanceof FirmwareJobError) throw error;
    throw new FirmwareJobError('固件构建任务请求失败，请检查连接后重试。');
  } finally {
    clearTimeout(timeout);
    signal?.removeEventListener('abort', abort);
  }
}
