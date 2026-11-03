import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash, webcrypto } from 'node:crypto';
import { readFirmwareSafety, verifyFirmwareBlob } from '../web/gr3/firmware-verification.mjs';

if (!globalThis.crypto?.subtle) Object.defineProperty(globalThis, 'crypto', { value: webcrypto, configurable: true });

const sourceSha256 = 'a'.repeat(64);
const configurationSha256 = 'b'.repeat(64);
const bytes = new TextEncoder().encode('tiny verified candidate 固件');
const candidateSha256 = createHash('sha256').update(bytes).digest('hex');
const baseAudit = {
  schema: 'm10v-web-firmware-safety/v1',
  status: 'offline_verified_camera_unverified',
  download_allowed: true,
  installation_allowed: false,
  camera_tested: false,
  artifact_kind: 'firmware',
  source_sha256: sourceSha256,
  configuration_sha256: configurationSha256,
  model: 'gr3',
  filename: 'fwdc239b.bin',
  candidate_bytes: bytes.byteLength,
  candidate_sha256: candidateSha256,
  checks: { pinned_source: true, camera_declaration: true, strict_decode: true, receipt_binding: true, exact_rebuild: true },
};
const options = (changes = {}) => ({ audit: structuredClone(baseAudit), sourceSha256, configurationSha256, model: 'gr3', filename: 'fwdc239b.bin', ...changes });

test('reads required base64 audit as UTF-8 without corrupting Chinese metadata', () => {
  const expected = { ...baseAudit, note: '离线验证完成，尚未实机测试' };
  const response = new Response('', { headers: { 'X-M10V-Firmware-Safety': Buffer.from(JSON.stringify(expected)).toString('base64') } });
  assert.deepEqual(readFirmwareSafety(response), expected);
});

test('rejects missing, malformed, non-object, or invalid UTF-8 audit headers', () => {
  for (const value of [undefined, '', '%%%invalid', Buffer.from('not json').toString('base64'), Buffer.from('null').toString('base64'), Buffer.from('[]').toString('base64'), Buffer.from([0xff]).toString('base64')]) {
    const response = new Response('', { headers: value === undefined ? {} : { 'X-M10V-Firmware-Safety': value } });
    assert.throws(() => readFirmwareSafety(response), /安全|验证/);
  }
});

test('verifies unchanged blob and returns original audit for repeated downloads', async () => {
  const args = options({ receipt: { candidate_sha256: candidateSha256, source_sha256: sourceSha256, configuration_sha256: configurationSha256 } });
  const blob = new Blob([bytes]);
  assert.strictEqual(await verifyFirmwareBlob(blob, args), args.audit);
  assert.strictEqual(await verifyFirmwareBlob(blob, args), args.audit);
  assert.deepEqual(new Uint8Array(await blob.arrayBuffer()), bytes);
});

test('requires each safety declaration and all five offline checks', async () => {
  const badAudits = [undefined, null, [], {},
    ...['schema', 'status', 'download_allowed', 'installation_allowed', 'camera_tested', 'artifact_kind'].flatMap(key => {
      const missing = structuredClone(baseAudit); delete missing[key];
      return [missing, { ...baseAudit, [key]: 'invalid' }];
    }),
    { ...baseAudit, checks: undefined },
    ...Object.keys(baseAudit.checks).flatMap(key => [{ ...baseAudit, checks: { ...baseAudit.checks, [key]: false } }, { ...baseAudit, checks: { ...baseAudit.checks, [key]: 'true' } }]),
  ];
  for (const audit of badAudits) await assert.rejects(verifyFirmwareBlob(new Blob([bytes]), options({ audit })), /安全|验证/);
});

test('rejects changed, truncated, empty, or incorrectly counted downloaded bytes', async () => {
  for (const blob of [new Blob(['changed candidate content!!']), new Blob([bytes.slice(0, -1)]), new Blob([])]) {
    await assert.rejects(verifyFirmwareBlob(blob, options()), /字节|摘要|验证/);
  }
  const sameLength = bytes.slice(); sameLength[0] ^= 1;
  await assert.rejects(verifyFirmwareBlob(new Blob([sameLength]), options()), /摘要/);
  for (const candidate_bytes of [bytes.length + 1, String(bytes.length), 0, -1, 1.5, null, undefined]) {
    await assert.rejects(verifyFirmwareBlob(new Blob([bytes]), options({ audit: { ...baseAudit, candidate_bytes } })), /字节|验证/);
  }
});

test('binds source, configuration, camera model, artifact kind, and exact filename', async () => {
  const cases = [
    { sourceSha256: 'c'.repeat(64) }, { sourceSha256: '' }, { configurationSha256: 'c'.repeat(64) }, { configurationSha256: undefined },
    { model: 'gr3x' }, { model: 'gr2' }, { filename: 'fwdc243b.bin' }, { filename: '../fwdc239b.bin' }, { artifactKind: 'other' },
    ...['source_sha256', 'configuration_sha256', 'model', 'filename', 'candidate_sha256'].map(key => ({ audit: { ...baseAudit, [key]: 'invalid' } })),
    { audit: { ...baseAudit, candidate_sha256: 'c'.repeat(64) } },
  ];
  for (const change of cases) await assert.rejects(verifyFirmwareBlob(new Blob([bytes]), options(change)), /安全|验证|摘要|配置|来源|型号|文件/);
  const audit = { ...baseAudit, model: 'gr3x', filename: 'fwdc243b.bin' };
  assert.strictEqual(await verifyFirmwareBlob(new Blob([bytes]), options({ audit, model: 'gr3x', filename: 'fwdc243b.bin' })), audit);
});

test('binds optional native or legacy receipt fields whenever supplied', async () => {
  assert.ok(await verifyFirmwareBlob(new Blob([bytes]), options({ receipt: {} })));
  for (const key of ['candidate_sha256', 'source_sha256', 'configuration_sha256']) {
    for (const wrong of ['c'.repeat(64), 'invalid', null, '']) {
      await assert.rejects(verifyFirmwareBlob(new Blob([bytes]), options({ receipt: { [key]: wrong } })), /回执|摘要|配置|来源/);
    }
  }
  for (const receipt of [[], 'invalid', 1]) await assert.rejects(verifyFirmwareBlob(new Blob([bytes]), options({ receipt })), /回执/);
});

test('allows official backup only with its exact filename and source-bound configuration', async () => {
  for (const model of ['gr3', 'gr3x']) {
    const audit = { ...baseAudit, model, artifact_kind: 'official_backup', filename: 'm10v-gr3-backup.zip', configuration_sha256: sourceSha256 };
    const args = options({ audit, model, artifactKind: 'official_backup', filename: 'm10v-gr3-backup.zip', configurationSha256: sourceSha256 });
    assert.strictEqual(await verifyFirmwareBlob(new Blob([bytes]), args), audit);
    await assert.rejects(verifyFirmwareBlob(new Blob([bytes]), { ...args, configurationSha256, audit: { ...audit, configuration_sha256: configurationSha256 } }), /配置|来源/);
    await assert.rejects(verifyFirmwareBlob(new Blob([bytes]), { ...args, filename: 'backup.zip', audit: { ...audit, filename: 'backup.zip' } }), /文件/);
  }
});

test('rejects unavailable browser hashing and oversized or non-Blob payloads', async () => {
  for (const payload of [null, bytes, { size: bytes.length, arrayBuffer: async () => bytes.buffer }]) {
    await assert.rejects(verifyFirmwareBlob(payload, options()), /文件|Blob|验证/);
  }
  const oversized = new Blob([new Uint8Array(128 * 1024 * 1024 + 1)]);
  await assert.rejects(verifyFirmwareBlob(oversized, options({ audit: { ...baseAudit, candidate_bytes: oversized.size } })), /大小|128|上限/);
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, 'crypto');
  try {
    Object.defineProperty(globalThis, 'crypto', { value: undefined, configurable: true });
    await assert.rejects(verifyFirmwareBlob(new Blob([bytes]), options()), /SHA|浏览器|安全/);
  } finally {
    Object.defineProperty(globalThis, 'crypto', descriptor);
  }
});
