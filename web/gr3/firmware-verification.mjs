const MAX_FIRMWARE_BYTES = 128 * 1024 * 1024;
const SHA256 = /^[a-f\d]{64}$/i;
const REQUIRED_CHECKS = ['pinned_source', 'camera_declaration', 'strict_decode', 'receipt_binding', 'exact_rebuild'];
const FIRMWARE_FILENAMES = { gr3: 'fwdc239b.bin', gr3x: 'fwdc243b.bin' };

function isRecord(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function sameSha256(value, expected) {
  return typeof value === 'string' && SHA256.test(value) && typeof expected === 'string'
    && SHA256.test(expected) && value.toLowerCase() === expected.toLowerCase();
}

/** Decode the server's required offline safety evidence without Latin-1 corruption. */
export function readFirmwareSafety(response) {
  try {
    const encoded = response?.headers?.get('X-M10V-Firmware-Safety');
    if (typeof encoded !== 'string' || encoded.length === 0 || encoded.length > 256 * 1024
        || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(encoded)) {
      throw new Error('invalid header');
    }
    const binary = atob(encoded);
    const decoded = new TextDecoder('utf-8', { fatal: true }).decode(Uint8Array.from(binary, char => char.charCodeAt(0)));
    const audit = JSON.parse(decoded);
    if (!isRecord(audit)) throw new Error('invalid audit');
    return audit;
  } catch {
    throw new Error('固件安全验证信息缺失或格式无效，已停止下载。');
  }
}

/** Verify local download bytes against offline evidence; this does not authorize installation. */
export async function verifyFirmwareBlob(blob, {
  audit, sourceSha256, configurationSha256, model, filename, receipt, artifactKind = 'firmware',
} = {}) {
  if (!isRecord(audit) || audit.schema !== 'm10v-web-firmware-safety/v1'
      || audit.status !== 'offline_verified_camera_unverified'
      || audit.download_allowed !== true || audit.installation_allowed !== false || audit.camera_tested !== false
      || !isRecord(audit.checks) || !REQUIRED_CHECKS.every(check => audit.checks[check] === true)) {
    throw new Error('固件安全验证未通过：缺少完整的离线验证证据。');
  }
  if (!['firmware', 'official_backup'].includes(artifactKind) || audit.artifact_kind !== artifactKind) {
    throw new Error('固件安全验证未通过：下载文件类型不匹配。');
  }
  if (!Object.hasOwn(FIRMWARE_FILENAMES, model) || audit.model !== model) {
    throw new Error('固件安全验证未通过：相机型号不匹配。');
  }
  const expectedFilename = artifactKind === 'official_backup' ? 'm10v-gr3-backup.zip' : FIRMWARE_FILENAMES[model];
  if (filename !== expectedFilename || audit.filename !== filename) {
    throw new Error('固件安全验证未通过：下载文件名不匹配。');
  }
  if (!sameSha256(audit.source_sha256, sourceSha256)) {
    throw new Error('固件安全验证未通过：来源固件摘要不匹配。');
  }
  if (!sameSha256(audit.configuration_sha256, configurationSha256)
      || (artifactKind === 'official_backup' && !sameSha256(configurationSha256, sourceSha256))) {
    throw new Error('固件安全验证未通过：配置摘要不匹配。');
  }
  if (!(blob instanceof Blob)) throw new Error('固件安全验证未通过：下载文件不是有效的 Blob。');
  if (blob.size > MAX_FIRMWARE_BYTES) throw new Error('固件文件大小超过 128 MiB 安全验证上限。');
  if (!Number.isSafeInteger(audit.candidate_bytes) || audit.candidate_bytes <= 0 || audit.candidate_bytes !== blob.size) {
    throw new Error('固件安全验证未通过：下载文件字节数不匹配。');
  }
  if (typeof audit.candidate_sha256 !== 'string' || !SHA256.test(audit.candidate_sha256)) {
    throw new Error('固件安全验证未通过：候选固件摘要缺失或无效。');
  }
  if (receipt !== undefined && receipt !== null) {
    if (!isRecord(receipt)) throw new Error('固件安全验证未通过：构建回执格式无效。');
    for (const field of ['candidate_sha256', 'source_sha256', 'configuration_sha256']) {
      if (Object.hasOwn(receipt, field) && !sameSha256(receipt[field], audit[field])) {
        throw new Error(`固件安全验证未通过：构建回执摘要不匹配（${field}）。`);
      }
    }
  }
  if (typeof globalThis.crypto?.subtle?.digest !== 'function') {
    throw new Error('当前浏览器无法执行 SHA-256 安全验证，已停止下载。');
  }
  let candidateSha256;
  try {
    const buffer = await blob.arrayBuffer();
    if (buffer.byteLength !== audit.candidate_bytes) throw new Error('invalid byte count');
    const digest = await globalThis.crypto.subtle.digest('SHA-256', buffer);
    candidateSha256 = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
  } catch {
    throw new Error('下载文件 SHA-256 安全验证失败，已停止下载。');
  }
  if (!sameSha256(candidateSha256, audit.candidate_sha256)) {
    throw new Error('固件安全验证未通过：下载文件 SHA-256 摘要不匹配。');
  }
  return audit;
}
