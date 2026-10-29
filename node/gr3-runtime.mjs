import { execFile } from 'node:child_process';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import { inspectOfficial } from './firmware.mjs';

const execFileAsync = promisify(execFile);
const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const worker = path.join(root, 'node', 'gr3-runtime-worker.py');
const defaultRuntime = path.join(root, '.runtime', 'grlife');
const currentRuntime = path.join(root, '.runtime', 'grlife-current');
const runtimeManifests = new Map([
  [defaultRuntime,'c42f0caf8163bb4db95bc864befc4d5f9fcaf41ade444bf027863d3574c2938d'],
  [currentRuntime,'1dff66f9e243329ed4ab95b9b7bb4bef74846848f62ae29172d8f3c74574688b'],
]);

export async function runtimeAvailable(runtimeDir = currentRuntime) {
  try {
    if (!runtimeManifests.has(runtimeDir)) {
      await readFile(path.join(runtimeDir, 'reconstruction', 'firmware_store', 'browser_engine.py'));
      return true;
    }
    const integrity = JSON.parse(await readFile(path.join(runtimeDir, 'm10v-integrity.json')));
    if (integrity.manifestSha256 !== runtimeManifests.get(runtimeDir))
      return false;
    for (const [name, expected] of Object.entries(integrity.files)) {
      if (name.startsWith('/') || name.split('/').includes('..')) return false;
      const bytes = await readFile(path.join(runtimeDir, name));
      if (createHash('sha256').update(bytes).digest('hex') !== expected) return false;
    }
    if (Object.keys(integrity.files).length < 59) return false;
    return true;
  } catch { return false; }
}

export async function runGr3Runtime(source, plan, action, runtimeDir, { signal, timeoutMs = 180_000, buildTimeoutMs = 300_000, halfFrame=true } = {}) {
  if(signal?.aborted) throw new Error("操作已取消");
  inspectOfficial(source);
  if(typeof halfFrame!=='boolean')throw new Error('invalid half-frame model gate');
  if (!['prepare', 'build'].includes(action)) throw new Error('invalid runtime action');
  // Low-memory deployment throttles CPU and swaps: a valid IIIx feature build
  // can exceed three minutes. Keep both operations bounded, without changing
  // the worker input or firmware output; the deployment unit also caps 600s.
  const deadlineMs = action === 'build' ? buildTimeoutMs : timeoutMs;
  if (!Number.isInteger(deadlineMs) || deadlineMs <= 0 || deadlineMs > 300_000)
    throw new Error('invalid runtime timeout');
  runtimeDir??=currentRuntime;
  if (!await runtimeAvailable(runtimeDir)) throw new Error('GRLife 兼容运行时未安装在本机');
  const folder = await mkdtemp(path.join(os.tmpdir(), 'm10v-gr3-build-'));
  const sourcePath = path.join(folder, 'source.bin');
  const planPath = path.join(folder, 'plan.json');
  const outputPath = path.join(folder, 'candidate.bin');
  try {
    await Promise.all([writeFile(sourcePath, source, { mode: 0o600 }),
      writeFile(planPath, JSON.stringify(plan), { mode: 0o600 })]);
    let stdout;
    try {
      ({ stdout } = await execFileAsync(process.env.M10V_PYTHON || '/opt/homebrew/bin/python3.12',
        [worker, action, sourcePath, planPath, outputPath], {
          signal, env: { ...process.env, PYTHONPATH: runtimeDir, M10V_HALF_FRAME:halfFrame?'1':'0' }, timeout: deadlineMs, maxBuffer: 1024 * 1024,
        }));
    } catch (error) {
      if(signal?.aborted) throw new Error('操作已取消');
      if (error.killed && error.signal === 'SIGTERM' && error.code !== 'ERR_CHILD_PROCESS_STDIO_MAXBUFFER')
        throw new Error(`GR III runtime ${action} timed out after ${deadlineMs}ms`);
      throw new Error((error.stderr || error.message || 'GR III runtime failed').trim().slice(-1200));
    }
    const receipt = JSON.parse(stdout);
    const candidate = action === 'build' ? await readFile(outputPath) : null;
    return { receipt, candidate };
  } finally { await rm(folder, { recursive: true, force: true }); }
}
