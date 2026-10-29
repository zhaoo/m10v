// Exact GR III baseline inspection. This module has no firmware writer.
import { createHash } from 'node:crypto';

export const SHA256 = 'd6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4';
export const GR3_220_SHA256 = '5c53760b3b564c87239dbf7f5c94d0f6fd91accd156ec4ba672ebfd6b861793e';
const FILE_SIZE = 30391780;
const DECODED_SIZE = 59718388;
const RTOS_HASH = '8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67';
const rules = [
  ['BOOTPARA', 72, 0xffff0005], ['DRAMPARA', 556, 0xffff0001],
  ['PARTPARA', 516, 0xffff0002], ['M0', 44640, 3], ['BOOT', 21816, 4],
  ['RTOS', 17520064, 0x10004], ['LINUX', 3062784, 0x50004],
  ['INITFS', 13899776, 0x60004], ['SRIC', 49152, 0x20004],
  ['CPU', 131072, 7], ['SHELLCMD', 37440, 0x30004],
  ['ICONBIN', 18354964, 0x40004], ['FDRVPARA', 36, 0xffff0008],
  ['RES', 6595272, 0xffff0006, 35],
];

const hash = (data) => createHash('sha256').update(data).digest('hex');
const requireValue = (condition, reason) => { if (!condition) throw new Error(reason); };

function sum32(data) {
  requireValue(data.length % 4 === 0, 'container: unaligned checksum');
  let value = 0;
  for (let i = 0; i < data.length; i += 4) value = (value + data.readUInt32LE(i)) >>> 0;
  return value;
}

function decode(payload, decodedSize = DECODED_SIZE) {
  const output = Buffer.allocUnsafe(decodedSize);
  let position = 0;
  let used = 0;
  let frames = 0;
  while (true) {
    requireValue(position + 2 <= payload.length, 'decoded: missing stream terminator');
    const prefix = payload.readUInt16BE(position);
    position += 2;
    if (prefix === 0) {
      requireValue(position === payload.length && used === decodedSize, 'decoded: length or terminator mismatch');
      return { output, frames };
    }
    const length = prefix & 0x7fff;
    const end = position + length;
    requireValue(length > 0 && end <= payload.length, 'decoded: invalid frame length');
    frames++;
    if (prefix & 0x8000) {
      requireValue(used + length <= decodedSize, 'decoded: literal overrun');
      payload.copy(output, used, position, end);
      used += length;
      position = end;
      continue;
    }
    let terminated = false;
    while (position < end && !terminated) {
      requireValue(position + 2 <= end, 'decoded: truncated flags');
      const flags = payload.readUInt16BE(position);
      position += 2;
      for (let bit = 15; bit >= 0; bit--) {
        if (!(flags & (1 << bit))) {
          requireValue(position < end && used < decodedSize, 'decoded: literal token overrun');
          output[used++] = payload[position++];
          continue;
        }
        requireValue(position + 2 <= end, 'decoded: truncated back-reference');
        const first = payload[position++];
        const second = payload[position++];
        const offset = ((first & 0xf8) << 5) | second;
        let count = first & 7;
        if (count === 7) {
          requireValue(position < end, 'decoded: truncated extension');
          count += payload[position++];
        }
        if (offset === 0) {
          requireValue(position === end, 'decoded: trailing bytes after frame terminator');
          terminated = true;
          break;
        }
        if (count === 262) {
          let extra = 255;
          while (extra === 255) {
            requireValue(position < end, 'decoded: truncated long extension');
            extra = payload[position++];
            count += extra;
          }
        }
        count += 3;
        requireValue(offset <= used && used + count <= decodedSize, 'decoded: invalid back-reference');
        for (let i = 0; i < count; i++) output[used + i] = output[used + i - offset];
        used += count;
      }
    }
    requireValue(terminated, 'decoded: frame has no end marker');
    position = end;
  }
}

export function inspectOfficial(data) {
  requireValue(Buffer.isBuffer(data), 'input: firmware must be bytes');
  const identity = hash(data);
  const isX = identity === '708e79f3b7b96a7e1581b4acf4c412233050a1832718ef7f06c8397db1b431c7';
  const is220 = identity === GR3_220_SHA256;
  const decodedBytes = is220 ? 59798532 : DECODED_SIZE;
  const sectionRules = rules.map(([name, size, flags, count]) => [name, is220 && name === 'RTOS' ? 17520384 : is220 && name === 'RES' ? 6675096 : size, flags, is220 && name === 'RES' ? 37 : count]);
  requireValue([FILE_SIZE, 30391788, 30472516].includes(data.length), 'size: unsupported firmware length');
  requireValue(identity === SHA256 || isX || is220, 'identity: full-file SHA-256 differs from supported official baseline');
  const project = isX ? 0x02610261 : 0x024c024c;
  const version = is220 ? 0x0214141c : isX ? 0x013c0b11 : 0x020a151b;
  const footer = data.length - 24;
  const encodedSize = data.readUInt32LE(footer + 12);
  const decodedSize = data.readUInt32LE(footer + 16);
  const payloadEnd = 128 + encodedSize;
  const metadataStart = (payloadEnd + 3) & ~3;
  requireValue(data.readUInt32LE(48) === (isX ? 609 : 588) && data.readUInt32LE(120) === project &&
    data.readUInt32LE(footer) === project, 'container: project mismatch');
  requireValue(data.readUInt32LE(124) === 0xa55a5aa5 && data.readUInt32LE(footer + 4) === 0xa55a5aa5 &&
    data.readUInt32LE(footer + 8) === 2, 'container: marker or type mismatch');
  requireValue(sum32(data) === 0, 'container: additive checksum failed');
  requireValue(payloadEnd <= footer && metadataStart <= footer && metadataStart === footer &&
    data.readUInt32LE(60) === 0 && decodedSize === decodedBytes, 'container: metadata or decoded length mismatch');
  const { output, frames } = decode(data.subarray(128, payloadEnd), decodedBytes);
  const sections = [];
  const rows = new Map();
  let position = 0;
  for (const [name, payloadSize, flags, resourceCount] of sectionRules) {
    const end = position + 16 + payloadSize;
    requireValue(end <= output.length - 4, `sections: ${name} exceeds decoded stream`);
    const actualName = output.toString('ascii', position, position + 8).split('\0', 1)[0];
    requireValue(actualName === name && output.readUInt32LE(position + 8) === flags,
      `sections: layout mismatch at ${name}`);
    const lengthField = output.readUInt32LE(position + 12);
    requireValue(lengthField === (name === 'RES' ? resourceCount : payloadSize),
      `sections: length mismatch at ${name}`);
    rows.set(name, output.subarray(position + 16, end));
    const block = output.subarray(position, end);
    sections.push({ name, size: block.length, sha256: hash(block) });
    position = end;
  }
  requireValue(position + 4 === output.length && sum32(output) === 0,
    'sections: decoded trailer or checksum mismatch');
  const rtos = rows.get('RTOS');
  const cpu = rows.get('CPU');
  requireValue(rtos.length === (is220 ? 17520384 : 17520064) && hash(rtos) === (is220 ? 'fb13f9b4e49abec5f036d3f9fc5e4d21ba2a4e65522efb849ac52a7151c87da9' : isX ? '0f11b0d28bc67932d044c5d01bc0314844a756057c89984278c73a23449a24c6' : RTOS_HASH),
    'rtos: unsupported baseline content');
  requireValue(rtos.readUInt32LE(0x450) === (is220 ? 0x5407b640 : 0x5407b540) &&
    rtos.readUInt32LE(0x454) === 0x55000000 && rtos.readUInt32LE(0x458) === (is220 ? 0x3a0c0 : 0x3a080),
  'rtos: startup copy layout mismatch');
  for (const [name, word] of [
    ['rtos', rtos.readUInt32BE(0x2038)], ['cpu', cpu.readUInt32BE(0x90)],
    ['outer_cpu', data.readUInt32BE(0x38)], ['outer_dsp', data.readUInt32BE(0x50)],
  ]) requireValue(word === version, `version: ${name} differs`);
  return {
    model: isX ? 'GR IIIx' : 'GR III', public_version: is220 ? '2.20' : isX ? '1.60' : '2.10', internal_version: is220 ? '2.20.20.28' : isX ? '1.60.11.17' : '2.10.21.27',
    sha256: identity, size: data.length, sections,
    proof: { identity: true, container: true, decoded: true, sections: true,
      versions: true, strict_frames: frames > 0 },
  };
}

export function readOfficialSection(data, name) {
  // Revalidate the entire exact baseline before exposing a read-only payload.
  const report = inspectOfficial(data);
  if (!rules.some((rule) => rule[0] === name)) throw new Error('unknown official section');
  const end = 128 + data.readUInt32LE(data.length - 12);
  const { output } = decode(data.subarray(128, end), data.readUInt32LE(data.length - 8));
  let offset = 0;
  for (const {name: sectionName, size: blockSize} of report.sections) {
    if (sectionName === name) return Buffer.from(output.subarray(offset + 16, offset + blockSize));
    offset += blockSize;
  }
  throw new Error('unknown official section');
}

// Import inventory is independent of the ABI-pinned patching interface above.
// Unknown releases are structurally checked, never authenticated as official or
// used as executable patch input. The build resolver selects a pinned baseline.
export function inspectFirmwareImport(data) {
  requireValue(Buffer.isBuffer(data), 'input: firmware must be bytes');
  requireValue(data.length >= 152 && data.length <= 128 * 1024 * 1024 && data.length % 4 === 0,
    'container: invalid firmware size');
  const identity = hash(data);
  if ([SHA256, GR3_220_SHA256, '708e79f3b7b96a7e1581b4acf4c412233050a1832718ef7f06c8397db1b431c7'].includes(identity))
    return inspectOfficial(data);
  const project = data.readUInt32LE(48), isX = project === 609;
  requireValue(project === 588 || isX, 'container: unsupported camera model');
  const magic = isX ? 0x02610261 : 0x024c024c, footer = data.length - 24;
  requireValue(data.readUInt32LE(120) === magic && data.readUInt32LE(footer) === magic,
    'container: project mismatch');
  requireValue(data.readUInt32LE(124) === 0xa55a5aa5 && data.readUInt32LE(footer + 4) === 0xa55a5aa5 &&
    data.readUInt32LE(footer + 8) === 2, 'container: marker or type mismatch');
  requireValue(sum32(data) === 0, 'identity: container additive checksum failed');
  const payloadEnd = 128 + data.readUInt32LE(footer + 12), decodedSize = data.readUInt32LE(footer + 16);
  requireValue(payloadEnd <= footer && ((payloadEnd + 3) & ~3) === footer && data.readUInt32LE(60) === 0 &&
    decodedSize >= 4 && decodedSize <= 128 * 1024 * 1024 && decodedSize % 4 === 0,
    'container: metadata or decoded length mismatch');
  const {output, frames} = decode(data.subarray(128, payloadEnd), decodedSize);
  requireValue(sum32(output) === 0, 'sections: decoded checksum failed');
  const sections = [], rows = new Map();
  let position = 0;
  for (const [name, , flags] of rules) {
    requireValue(position + 16 <= output.length - 4, 'sections: truncated header');
    requireValue(output.toString('ascii', position, position + 8).split('\0', 1)[0] === name &&
      output.readUInt32LE(position + 8) === flags, `sections: layout mismatch at ${name}`);
    const field = output.readUInt32LE(position + 12);
    const size = name === 'RES' ? output.length - 4 - position - 16 : field;
    requireValue(field > 0 && size > 0 && size % 4 === 0 && position + 16 + size <= output.length - 4,
      `sections: invalid length at ${name}`);
    const end = position + 16 + size;
    rows.set(name, output.subarray(position + 16, end));
    sections.push({name, size: end - position, sha256: hash(output.subarray(position, end))});
    position = end;
  }
  requireValue(position + 4 === output.length, 'sections: decoded trailer mismatch');
  const rtos = rows.get('RTOS'), cpu = rows.get('CPU');
  requireValue(rtos.length >= 0x203c && cpu.length >= 0x94 && cpu.readUInt32LE(0x80) === project,
    'sections: component project or version fields invalid');
  let cpuSum = 0;
  for (let at = 0; at < cpu.length; at += 4) cpuSum = (cpuSum + cpu.readUInt32BE(at)) >>> 0;
  requireValue(cpuSum === 0, 'sections: CPU checksum failed');
  const version = data.readUInt32BE(0x38);
  requireValue(version >>> 24 > 0 && [data.readUInt32BE(0x50), rtos.readUInt32BE(0x2038), cpu.readUInt32BE(0x90)]
    .every(value => value === version), 'version: component copies differ');
  const parts = [version >>> 24, (version >>> 16) & 255, (version >>> 8) & 255, version & 255];
  return {model: isX ? 'GR IIIx' : 'GR III', public_version: parts.slice(0, 2).join('.'),
    internal_version: parts.join('.'), sha256: identity, size: data.length, sections,
    proof: {identity: false, container: true, decoded: true, sections: true, versions: true,
      strict_frames: frames > 0}, source_authenticity: 'unverified', patch_source: false};
}
