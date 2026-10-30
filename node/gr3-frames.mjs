// In-memory GR III frame replay used by the independently verified export path.
import { inspectOfficial } from './firmware.mjs';
import {MAX_DECODED_FIRMWARE_BYTES} from './gr3-native-budget.mjs';

function check(ok, message) { if (!ok) throw new Error(message); }
export function sum32(bytes) {
  check(bytes.length % 4 === 0, 'unaligned checksum');
  let sum = 0;
  for (let i = 0; i < bytes.length; i += 4) sum = (sum + bytes.readUInt32LE(i)) >>> 0;
  return sum;
}

export function decodeFrameMap(container, expectedDecodedSize) {
  check(Buffer.isBuffer(container) && container.length >= 152, 'invalid container');
  const footer = container.length - 24;
  const encodedSize = container.readUInt32LE(footer + 12);
  const decodedSize = container.readUInt32LE(footer + 16);
  expectedDecodedSize ??= decodedSize;
  check(decodedSize === expectedDecodedSize && decodedSize > 0 && decodedSize <= MAX_DECODED_FIRMWARE_BYTES &&
    128 + encodedSize <= footer, 'invalid frame sizes');
  const payload = container.subarray(128, 128 + encodedSize);
  const decoded = Buffer.allocUnsafe(expectedDecodedSize);
  const frames = [];
  let position = 0;
  let used = 0;
  for (;;) {
    check(position + 2 <= payload.length, 'missing frame terminator');
    const start = position;
    const prefix = payload.readUInt16BE(position);
    position += 2;
    if (prefix === 0) {
      check(position === payload.length && used === expectedDecodedSize, 'frame terminator or decoded length differs');
      return { decoded, frames };
    }
    const length = prefix & 0x7fff;
    const end = position + length;
    check(length > 0 && end <= payload.length, 'invalid frame length');
    const decodedStart = used;
    const literal = !!(prefix & 0x8000);
    if (literal) {
      check(used + length <= expectedDecodedSize, 'literal frame overrun');
      payload.copy(decoded, used, position, end);
      used += length;
    } else {
      let terminated = false;
      while (position < end && !terminated) {
        check(position + 2 <= end, 'truncated flags');
        const flags = payload.readUInt16BE(position);
        position += 2;
        for (let bit = 15; bit >= 0; bit--) {
          if (!(flags & (1 << bit))) {
            check(position < end && used < expectedDecodedSize, 'literal token overrun');
            decoded[used++] = payload[position++];
            continue;
          }
          check(position + 2 <= end, 'truncated back reference');
          const first = payload[position++];
          const second = payload[position++];
          const offset = ((first & 0xf8) << 5) | second;
          let count = first & 7;
          if (count === 7) {
            check(position < end, 'truncated count extension');
            count += payload[position++];
          }
          if (offset === 0) {
            check(position === end, 'trailing frame data');
            terminated = true;
            break;
          }
          if (count === 262) {
            let extra = 255;
            while (extra === 255) {
              check(position < end, 'truncated long extension');
              extra = payload[position++];
              count += extra;
            }
          }
          count += 3;
          check(offset <= used && used + count <= expectedDecodedSize, 'back reference overrun');
          for (let i = 0; i < count; i++) decoded[used + i] = decoded[used + i - offset];
          used += count;
        }
      }
      check(terminated, 'compressed frame lacks end marker');
    }
    frames.push({ encoded_start: start, encoded_end: end,
      decoded_start: decodedStart, decoded_end: used, literal });
    position = end;
  }
}

export function repackWithTarget(official, targetDecoded) {
  inspectOfficial(official);
  const { decoded, frames } = decodeFrameMap(official);
  check(Buffer.isBuffer(targetDecoded) && targetDecoded.length === decoded.length &&
    sum32(targetDecoded) === 0, 'target length or decoded checksum differs');
  if (targetDecoded.equals(decoded)) return { candidate: Buffer.from(official),
    reused_frames: frames.length, replaced_frames: 0 };
  const chunks = [];
  let reused = 0;
  let replaced = 0;
  for (const frame of frames) {
    const desired = targetDecoded.subarray(frame.decoded_start, frame.decoded_end);
    // Compressed frames can refer to the previous frame's 8191-byte history.
    const historyStart = Math.max(0, frame.decoded_start - 8191);
    if (targetDecoded.subarray(historyStart, frame.decoded_end)
      .equals(decoded.subarray(historyStart, frame.decoded_end))) {
      chunks.push(official.subarray(128 + frame.encoded_start, 128 + frame.encoded_end));
      reused++;
    } else {
      for (let position = 0; position < desired.length; position += 0x6000) {
        const slice = desired.subarray(position, position + 0x6000);
        const prefix = Buffer.alloc(2);
        prefix.writeUInt16BE(0x8000 | slice.length);
        chunks.push(prefix, slice);
      }
      replaced++;
    }
  }
  chunks.push(Buffer.alloc(2));
  const payload = Buffer.concat(chunks);
  const pad = Buffer.alloc(-(128 + payload.length) & 3);
  const footer = Buffer.from(official.subarray(-24));
  footer.writeUInt32LE(payload.length, 12);
  footer.writeUInt32LE(targetDecoded.length, 16);
  footer.writeUInt32LE(0, 20);
  const candidate = Buffer.concat([official.subarray(0, 128), payload, pad, footer]);
  candidate.writeUInt32LE(-sum32(candidate) >>> 0, candidate.length - 4);
  check(decodeFrameMap(candidate).decoded.equals(targetDecoded), 'fresh frame decode differs');
  return { candidate, reused_frames: reused, replaced_frames: replaced };
}
