// Strict four-member computer-side backup. No camera recovery is implied.
import { createHash } from 'node:crypto';
import { inflateRawSync } from 'node:zlib';
import { inspectFirmwareImport } from './firmware.mjs';

const ORIGINAL = 'original/fwdc239b.bin';
const PROJECT = 'project.json';
const NOTICE = 'README-恢复说明.txt';
const NAMES = [ORIGINAL, PROJECT, NOTICE, 'manifest.json'];
const INSTRUCTIONS = Buffer.from('这是电脑端项目备份，不包含相机内部 Flash/NAND。\n请在 m10v 中导入并验证。原厂 BIN 不保证能降级刷回或修复变砖相机。\n');
const hash = (data) => createHash('sha256').update(data).digest('hex');
const fail = (reason) => { throw new Error(reason); };

function canonical(value) {
  const encode = (entry) => {
    if (Array.isArray(entry)) return `[${entry.map(encode).join(', ')}]`;
    if (entry !== null && typeof entry === 'object') return `{${Object.keys(entry).sort().map(
      (key) => `${JSON.stringify(key)}: ${encode(entry[key])}`).join(', ')}}`;
    return JSON.stringify(entry);
  };
  return Buffer.from(encode(value) + '\n');
}

function parseCanonical(data) {
  const value = JSON.parse(data.toString('utf8'));
  if (!canonical(value).equals(data)) fail('backup JSON is not canonical');
  return value;
}

const crcTable = Uint32Array.from({ length: 256 }, (_, index) => {
  let value = index;
  for (let i = 0; i < 8; i++) value = (value & 1) ? (0xedb88320 ^ (value >>> 1)) : value >>> 1;
  return value >>> 0;
});
function crc32(data) {
  let value = 0xffffffff;
  for (const byte of data) value = crcTable[(value ^ byte) & 255] ^ (value >>> 8);
  return (value ^ 0xffffffff) >>> 0;
}

function encodeZip(rows) {
  const local = [];
  const central = [];
  let offset = 0;
  for (const name of NAMES) {
    const bytes = rows[name];
    const filename = Buffer.from(name);
    const checksum = crc32(bytes);
    const header = Buffer.alloc(30);
    header.writeUInt32LE(0x04034b50);
    header.writeUInt16LE(20, 4);
    header.writeUInt16LE(0x800, 6);
    header.writeUInt32LE(checksum, 14);
    header.writeUInt32LE(bytes.length, 18);
    header.writeUInt32LE(bytes.length, 22);
    header.writeUInt16LE(filename.length, 26);
    local.push(header, filename, bytes);
    const record = Buffer.alloc(46);
    record.writeUInt32LE(0x02014b50);
    record.writeUInt16LE(0x0314, 4);
    record.writeUInt16LE(20, 6);
    record.writeUInt16LE(0x800, 8);
    record.writeUInt32LE(checksum, 16);
    record.writeUInt32LE(bytes.length, 20);
    record.writeUInt32LE(bytes.length, 24);
    record.writeUInt16LE(filename.length, 28);
    record.writeUInt32LE((0o100644 << 16) >>> 0, 38);
    record.writeUInt32LE(offset, 42);
    central.push(record, filename);
    offset += header.length + filename.length + bytes.length;
  }
  const centralSize = central.reduce((size, part) => size + part.length, 0);
  const ending = Buffer.alloc(22);
  ending.writeUInt32LE(0x06054b50);
  ending.writeUInt16LE(NAMES.length, 8);
  ending.writeUInt16LE(NAMES.length, 10);
  ending.writeUInt32LE(centralSize, 12);
  ending.writeUInt32LE(offset, 16);
  return Buffer.concat([...local, ...central, ending]);
}

function decodeZip(archive) {
  if (!Buffer.isBuffer(archive) || archive.length > 128 * 1024 * 1024) fail('backup ZIP exceeds size limit');
  let ending = -1;
  for (let i = archive.length - 22; i >= Math.max(0, archive.length - 65557); i--) {
    if (archive.readUInt32LE(i) === 0x06054b50 && i + 22 + archive.readUInt16LE(i + 20) === archive.length) {
      ending = i; break;
    }
  }
  if (ending < 0 || archive.readUInt16LE(ending + 8) !== NAMES.length ||
    archive.readUInt16LE(ending + 10) !== NAMES.length ||
    archive.readUInt16LE(ending + 4) || archive.readUInt16LE(ending + 6)) fail('invalid backup ZIP directory');
  const centralStart = archive.readUInt32LE(ending + 16);
  const centralEnd = centralStart + archive.readUInt32LE(ending + 12);
  if (centralEnd !== ending) fail('invalid backup ZIP central offset');
  let position = centralStart;
  let total = 0;
  const rows = {};
  for (let i = 0; i < NAMES.length; i++) {
    if (position + 46 > centralEnd || archive.readUInt32LE(position) !== 0x02014b50) fail('invalid ZIP member');
    const flags = archive.readUInt16LE(position + 8);
    const method = archive.readUInt16LE(position + 10);
    const checksum = archive.readUInt32LE(position + 16);
    const compressed = archive.readUInt32LE(position + 20);
    const size = archive.readUInt32LE(position + 24);
    const nameLength = archive.readUInt16LE(position + 28);
    const extraLength = archive.readUInt16LE(position + 30);
    const commentLength = archive.readUInt16LE(position + 32);
    const mode = (archive.readUInt32LE(position + 38) >>> 16) & 0o170000;
    const offset = archive.readUInt32LE(position + 42);
    const nameEnd = position + 46 + nameLength;
    if (nameEnd > centralEnd || (flags & 1) || ![0, 8].includes(method) ||
      size > 128 * 1024 * 1024 || ![0, 0o100000].includes(mode)) fail('unsafe ZIP member');
    const name = archive.toString('utf8', position + 46, nameEnd);
    if (!NAMES.includes(name) || Object.hasOwn(rows, name)) fail('unexpected or duplicate ZIP member');
    total += size;
    if (total > 256 * 1024 * 1024) fail('backup expands beyond limit');
    if (offset + 30 > centralStart || archive.readUInt32LE(offset) !== 0x04034b50 ||
      archive.readUInt16LE(offset + 8) !== method) fail('invalid ZIP local header');
    const localLength = archive.readUInt16LE(offset + 26);
    const localExtra = archive.readUInt16LE(offset + 28);
    const bodyStart = offset + 30 + localLength + localExtra;
    if (bodyStart + compressed > centralStart ||
      archive.toString('utf8', offset + 30, offset + 30 + localLength) !== name) fail('ZIP name or bounds mismatch');
    const body = archive.subarray(bodyStart, bodyStart + compressed);
    let value;
    try { value = method === 0 ? body : inflateRawSync(body, { maxOutputLength: size + 1 }); }
    catch { fail('invalid compressed backup member'); }
    if (value.length !== size || crc32(value) !== checksum) fail('backup member checksum differs');
    rows[name] = value;
    position = nameEnd + extraLength + commentLength;
  }
  if (position !== centralEnd || Object.keys(rows).length !== NAMES.length) fail('backup members differ');
  return rows;
}

function validateRows(rows) {
  const manifest = parseCanonical(rows['manifest.json']);
  if (manifest.schema_version !== 1 ||
    Object.keys(manifest.members || {}).sort().join(',') !== [ORIGINAL, PROJECT, NOTICE].sort().join(','))
    fail('unsupported backup manifest');
  for (const name of [ORIGINAL, PROJECT, NOTICE]) {
    const entry = manifest.members[name];
    if (!entry || Object.keys(entry).sort().join(',') !== 'sha256,size' ||
      entry.sha256 !== hash(rows[name]) || entry.size !== rows[name].length) fail('backup member hash or length differs');
  }
  if (!rows[NOTICE].equals(INSTRUCTIONS)) fail('backup recovery notice differs');
  const report = inspectFirmwareImport(rows[ORIGINAL]);
  const record = parseCanonical(rows[PROJECT]);
  const expected = {
    id: report.sha256, sha256: report.sha256, size: report.size,
    model: report.model, public_version: report.public_version,
    internal_version: report.internal_version,
  };
  if (canonical(record).toString() !== canonical(expected).toString()) fail('backup project identity mismatch');
  return { report, record };
}

export function createBackup(original) {
  const report = inspectFirmwareImport(original);
  const record = {
    id: report.sha256, sha256: report.sha256, size: report.size,
    model: report.model, public_version: report.public_version,
    internal_version: report.internal_version,
  };
  const rows = { [ORIGINAL]: original, [PROJECT]: canonical(record), [NOTICE]: INSTRUCTIONS };
  rows['manifest.json'] = canonical({ schema_version: 1, members: Object.fromEntries(
    Object.entries(rows).map(([name, bytes]) => [name, { sha256: hash(bytes), size: bytes.length }])) });
  const archive = encodeZip(rows);
  inspectBackup(archive);
  return archive;
}

export function inspectBackup(archive) {
  const rows = decodeZip(archive);
  const { report } = validateRows(rows);
  return { project_id: report.sha256, original_sha256: report.sha256, member_count: NAMES.length,
    recovery_scope: 'computer_official_package_only', camera_flash_included: false };
}

export function restoreBytes(archive) {
  const rows = decodeZip(archive);
  validateRows(rows);
  return rows[ORIGINAL];
}
