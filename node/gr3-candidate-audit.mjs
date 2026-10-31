import {MAX_NATIVE_RTOS_GROWTH} from './gr3-native-budget.mjs';
import { createHash } from 'node:crypto';
import { inspectFirmwareImport as inspectOfficial } from './firmware.mjs';
import { decodeFrameMap, sum32 } from './gr3-frames.mjs';

const sha = (bytes) => createHash('sha256').update(bytes).digest('hex');
const fail = (message) => { throw new Error(message); };

function sections(decoded, sourceSections) {
  let offset = 0;
  const result = [];
  for (const original of sourceSections) {
    if (offset + 16 > decoded.length - 4) fail('candidate section header overrun');
    const name = decoded.toString('ascii', offset, offset + 8).split('\0', 1)[0];
    if (name !== original.name) fail(`candidate section order mismatch at ${original.name}`);
    const size = name === 'RTOS' ? decoded.readUInt32LE(offset + 12) : original.size - 16;
    if (size <= 0 || offset + 16 + size > decoded.length - 4) fail(`candidate ${name} size invalid`);
    if (name !== 'RES' && decoded.readUInt32LE(offset + 12) !== size) fail(`${name} header length mismatch`);
    const block = decoded.subarray(offset, offset + 16 + size);
    result.push({ name, size: block.length, sha256: sha(block) });
    offset += block.length;
  }
  if (offset + 4 !== decoded.length) fail('candidate decoded section length mismatch');
  return result;
}

export function auditGr3Candidate(official, candidate, {maxRtosGrowth=64*1024,minRtosGrowth=1}={}) {
  const source = inspectOfficial(official);
  if (!Buffer.isBuffer(candidate) || candidate.length < 152 || candidate.equals(official))
    fail('candidate missing or unchanged');
  if (sum32(candidate) !== 0) fail('candidate outer checksum mismatch');
  if (!candidate.subarray(0, 128).equals(official.subarray(0, 128)))
    fail('candidate header differs from the official source');
  const footer = candidate.length - 24;
  if (candidate.readUInt32LE(footer) !== official.readUInt32LE(official.length - 24) ||
      candidate.readUInt32LE(footer + 4) !== 0xa55a5aa5 ||
      candidate.readUInt32LE(footer + 8) !== 2) fail('candidate footer identity mismatch');
  const encodedSize = candidate.readUInt32LE(footer + 12);
  const decodedSize = candidate.readUInt32LE(footer + 16);
  if (((128 + encodedSize + 3) & ~3) !== footer) fail('candidate encoded size mismatch');
  const { decoded, frames } = decodeFrameMap(candidate, decodedSize);
  if (sum32(decoded) !== 0) fail('candidate decoded checksum mismatch');
  const rows = sections(decoded, source.sections);
  const growth = rows.find((row) => row.name === 'RTOS').size -
    source.sections.find((row) => row.name === 'RTOS').size;
  if (![0,1].includes(minRtosGrowth) || ![64*1024,512*1024,544*1024,672*1024,MAX_NATIVE_RTOS_GROWTH].includes(maxRtosGrowth) || growth < minRtosGrowth || growth > maxRtosGrowth) fail('candidate RTOS growth outside supported range');
  const changedSections = rows.filter((row, index) => row.sha256 !== source.sections[index].sha256)
    .map((row) => row.name);
  if (changedSections.some((name) => !['RTOS', 'ICONBIN'].includes(name)))
    fail('candidate changed an unrelated section');
  return { sourceSha256: source.sha256, candidateSha256: sha(candidate),
    candidateBytes: candidate.length, decodedBytes: decoded.length,
    frameCount: frames.length, rtosGrowth: growth, changedSections, sections: rows };
}
