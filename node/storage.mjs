// Atomic computer-side storage for the exact official baseline.
import { createHash } from 'node:crypto';
import { mkdir, mkdtemp, readFile, rename, rm, stat, lstat, open } from 'node:fs/promises';
import path from 'node:path';
import { inspectFirmwareImport } from './firmware.mjs';

const hash = (data) => createHash('sha256').update(data).digest('hex');
const checkId = (id) => {
  if (!/^[0-9a-f]{64}$/.test(id)) throw new Error('invalid project id');
  return id;
};
async function regular(file) {
  const info = await lstat(file);
  if (!info.isFile() || info.isSymbolicLink()) throw new Error('unsafe project file');
  return info;
}
async function syncDirectory(directory) {
  const handle = await open(directory, 'r');
  try { await handle.sync(); } finally { await handle.close(); }
}
async function checkDirectory(directory) {
  try {
    const info = await lstat(directory);
    if (!info.isDirectory() || info.isSymbolicLink()) throw new Error('unsafe project directory');
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }
}

export class Store {
  constructor(root) { this.root = path.resolve(root); }
  folder(id) { return path.join(this.root, 'projects', checkId(id)); }

  async readProject(id) {
    const folder = this.folder(id);
    await checkDirectory(path.join(this.root, 'projects'));
    await checkDirectory(folder);
    const file = path.join(folder, 'project.json');
    const info = await regular(file);
    if (info.size > 8192) throw new Error('unsafe project record');
    const value = JSON.parse(await readFile(file, 'utf8'));
    if (!value || Object.keys(value).sort().join(',') !==
      'id,internal_version,model,public_version,sha256,size' ||
      value.id !== id || value.sha256 !== id) throw new Error('project identity mismatch');
    return value;
  }

  async readOriginal(id) {
    await this.readProject(id);
    const file = path.join(this.folder(id), 'original.bin');
    const info = await regular(file);
    if (info.size > 128 * 1024 * 1024 || (info.mode & 0o222)) throw new Error('unsafe original file');
    const data = await readFile(file);
    if (hash(data) !== id) throw new Error('stored original identity mismatch');
    inspectFirmwareImport(data);
    return data;
  }

  async importOfficial(data) {
    const report = inspectFirmwareImport(data);
    const record = {
      id: report.sha256, sha256: report.sha256, size: report.size,
      model: report.model, public_version: report.public_version,
      internal_version: report.internal_version,
    };
    await checkDirectory(this.root);
    await mkdir(this.root, { recursive: true });
    const projects = path.join(this.root, 'projects');
    await checkDirectory(projects);
    await mkdir(projects, { recursive: true });
    const destination = this.folder(record.id);
    await checkDirectory(destination);
    try {
      await stat(destination);
      const old = await this.readProject(record.id);
      if (Object.keys(record).some((key) => old[key] !== record[key]) ||
        !(await this.readOriginal(record.id)).equals(data)) throw new Error('existing project differs');
      return record;
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
    }
    const stage = await mkdtemp(path.join(projects, '.m10v-'));
    try {
      for (const [name, bytes] of [
        ['original.bin', data], ['project.json', Buffer.from(JSON.stringify(record) + '\n')],
      ]) {
        const file = path.join(stage, name);
        const handle = await open(file, 'wx', 0o400);
        try { await handle.writeFile(bytes); await handle.sync(); } finally { await handle.close(); }
      }
      await syncDirectory(stage);
      await rename(stage, destination);
      await syncDirectory(projects);
      return record;
    } finally {
      await rm(stage, { recursive: true, force: true });
    }
  }
}
