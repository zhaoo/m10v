// Each complete build gets its own budget; verification must rebuild from source.
export async function runFirmwareBuildPhase(signal, run, timeoutMs = 5 * 60 * 1000) {
  signal.throwIfAborted();
  const deadline = new AbortController();
  const combined = AbortSignal.any([signal, deadline.signal]);
  const timer = setTimeout(() => deadline.abort(Object.assign(
    new Error('固件生成或独立校验超时，请稍后重试。'), {code:'M10V_BUILD_TIMEOUT'}
  )), timeoutMs);
  timer.unref?.();
  try {
    const result = await run(combined);
    combined.throwIfAborted();
    return result;
  } catch (error) {
    // Subprocess wrappers may translate AbortError into a generic cancellation.
    combined.throwIfAborted();
    throw error;
  } finally {
    clearTimeout(timer);
  }
}
