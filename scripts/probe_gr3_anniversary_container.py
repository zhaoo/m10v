"""Offline, memory-only container research; never creates update BIN/ZIP files.

Host frame replay and strict decode are separate evidence from real ARM outer,
decoded checksum and CPU validators. The hardware decompressor, complete parser,
flash dispatch, boot and persistent settings are deliberately not substituted.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC

ROOT = Path(__file__).resolve().parents[1]
PROFILES = {
    'gr3': ('5c53760b3b564c87239dbf7f5c94d0f6fd91accd156ec4ba672ebfd6b861793e', 588, 0x0214141c),
    'gr3x': ('aa8e3ae1349d94e83be381c20530e41d5e57b75c27ef24ba81c7b017d6c11592', 609, 0x01461412),
}
LOAD, RAM, DATA, STOP = 0x53000000, 0x55000000, 0x56000000, 0x550ffff0
OUTER, DECODED_SUM, CPU, FULL_PARSER, DECOMPRESS = (0x5362be30, 0x5362bf98, 0x536291b8, 0x5362c218, 0x5362c038)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def sum32(data, endian='<'):
    require(len(data) % 4 == 0, 'unaligned checksum')
    return sum(word[0] for word in struct.iter_unpack(endian+'I', data)) & 0xffffffff


def repair(data, offset, endian='<'):
    struct.pack_into(endian+'I', data, offset, 0)
    struct.pack_into(endian+'I', data, offset, -sum32(data, endian) & 0xffffffff)


def source(file, model):
    require(model in PROFILES, 'unsupported model')
    raw = Path(file).read_bytes()
    require(sha(raw) == PROFILES[model][0], 'official source SHA-256 differs')
    js = """import {readFileSync} from 'node:fs';
import {inspectFirmwareImport} from './node/firmware.mjs';
import {decodeFrameMap} from './node/gr3-frames.mjs';
const b=readFileSync(process.argv[1]);const report=inspectFirmwareImport(b);
const {decoded,frames}=decodeFrameMap(b);
process.stdout.write(JSON.stringify({report,frames})+'\\n');process.stdout.write(decoded);"""
    output = subprocess.check_output(['node', '--input-type=module', '-e', js, str(Path(file).resolve())], cwd=ROOT, timeout=60)
    header, decoded = output.split(b'\n', 1)
    meta = json.loads(header)
    sections, at = {}, 0
    for row in meta['report']['sections']:
        sections[row['name']] = (at+16, at+row['size'])
        at += row['size']
    require(at+4 == len(decoded), 'section boundary differs')
    return raw, decoded, meta['frames'], sections


def replay(raw, original, decoded, frames):
    """Replay unaffected original frames; replace dependent frames with literals."""
    chunks, reused, replaced = [], 0, 0
    for frame in frames:
        start, end = frame['decoded_start'], frame['decoded_end']
        history = max(0, start-8191)
        desired = decoded[start:end]
        if desired == original[start:end] and decoded[history:start] == original[history:start]:
            chunks.append(raw[128+frame['encoded_start']:128+frame['encoded_end']])
            reused += 1
        else:
            for at in range(0, len(desired), 0x6000):
                part = desired[at:at+0x6000]
                chunks.extend((struct.pack('>H', 0x8000 | len(part)), part))
            replaced += 1
    payload = b''.join(chunks)+b'\0\0'
    footer = bytearray(raw[-24:])
    struct.pack_into('<III', footer, 12, len(payload), len(decoded), 0)
    result = bytearray(raw[:128]+payload+bytes(-(128+len(payload)) & 3)+footer)
    repair(result, len(result)-4)
    return result, reused, replaced


def strict_decode(raw, expected=None):
    js = """import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {inspectFirmwareImport} from './node/firmware.mjs';
import {decodeFrameMap} from './node/gr3-frames.mjs';
try{const b=readFileSync(0);const r=inspectFirmwareImport(b);
const d=decodeFrameMap(b).decoded;
process.stdout.write(JSON.stringify({accepted:true,sha256:r.sha256,decoded_sha256:createHash('sha256').update(d).digest('hex'),proof:r.proof,source_authenticity:r.source_authenticity??'pinned_official'}));}
catch(e){process.stdout.write(JSON.stringify({accepted:false,reason:e.message}));}"""
    result = json.loads(subprocess.check_output(['node', '--input-type=module', '-e', js], cwd=ROOT, input=raw, timeout=60))
    if expected is not None:
        require(result['accepted'] == expected, 'strict host result differs: '+str(result))
    return result


def machine(rom, data):
    u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    u.mem_map(LOAD, (len(rom)+65535) & ~65535)
    u.mem_write(LOAD, rom)
    u.mem_map(RAM, 0x100000)
    u.mem_map(DATA, (len(data)+4095) & ~4095)
    u.mem_write(DATA, bytes(data))
    def logger(u, address, size, user):
        u.reg_write(UC_ARM_REG_R0, 0)
        u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))
    u.hook_add(UC_HOOK_CODE, logger, begin=0x536b83c4, end=0x536b83c4)
    return u


def arm(rom, data, entry, fields, stop=STOP, outputs=False):
    u = machine(rom, data)
    obj = RAM+0x1000
    for offset, value in fields:
        u.mem_write(obj+offset, struct.pack('<I', value))
    u.reg_write(UC_ARM_REG_R0, obj)
    u.reg_write(UC_ARM_REG_R1, RAM+0x2000)
    u.reg_write(UC_ARM_REG_R2, RAM+0x2004)
    u.reg_write(UC_ARM_REG_SP, RAM+0xff000)
    u.reg_write(UC_ARM_REG_LR, STOP)
    u.emu_start(entry, stop, count=400000000)
    require(u.reg_read(UC_ARM_REG_PC) == stop, 'ARM probe did not reach expected boundary')
    result = u.reg_read(UC_ARM_REG_R0)
    return (result, struct.unpack('<II', u.mem_read(RAM+0x2000, 8))) if outputs else result


def outer(rom, data, project):
    return arm(rom, data, OUTER, [(8, DATA), (12, len(data)), (24, project), (28, 2)])


def construct(raw, decoded, frames, sections, model):
    _, project, current = PROFILES[model]
    proposed = current+256
    target = bytearray(decoded)
    rs, re = sections['RTOS']
    cs, ce = sections['CPU']
    rtos, cpu = decoded[rs:re], decoded[cs:ce]
    require(rtos[0x6286cc:0x6286d0] == bytes.fromhex('e42103e3'), 'updater patch preimage differs')
    struct.pack_into('>I', target, rs+0x2038, proposed)
    target[rs+0x6286cc:rs+0x6286d0] = bytes.fromhex('e6ffffea')
    new_cpu = bytearray(cpu)
    struct.pack_into('>I', new_cpu, 0x90, proposed)
    repair(new_cpu, 0x7c, '>')
    require(struct.unpack_from('<I', new_cpu, 0x80)[0] == project, 'CPU project differs')
    target[cs:ce] = new_cpu
    repair(target, len(target)-4)
    allowed = [(rs+0x2038, 4), (rs+0x6286cc, 4), (cs+0x7c, 4), (cs+0x90, 4), (len(target)-4, 4)]
    changes = [at for at, (old, new) in enumerate(zip(decoded, target)) if old != new]
    require(all(any(start <= at < start+size for start, size in allowed) for at in changes), 'non-target decoded bytes changed')
    candidate, reused, replaced = replay(raw, decoded, target, frames)
    for at in (0x38, 0x50):
        struct.pack_into('>I', candidate, at, proposed)
    repair(candidate, len(candidate)-4)
    allowed_header = set(range(0x38, 0x3c)) | set(range(0x50, 0x54))
    require(all(a == b or at in allowed_header for at, (a, b) in enumerate(zip(raw[:128], candidate[:128]))), 'non-target outer header changed')
    require(candidate[-24:-12] == raw[-24:-12], 'footer project, marker or type changed')
    return candidate, target, rtos, new_cpu, dict(
        version='.'.join(str((proposed >> shift) & 255) for shift in (24, 16, 8, 0)),
        changed_decoded_bytes=len(changes), changed_decoded_offsets=[hex(at) for at in changes],
        unchanged_sections=[name for name, (start, end) in sections.items() if decoded[start:end] == target[start:end]],
        original_frames_reused=reused, original_frames_replaced=replaced,
        decoded_sha256=sha(target), candidate_sha256=sha(candidate), candidate_size=len(candidate))


def probe(file, model):
    raw, decoded, frames, sections = source(file, model)
    candidate, target, rom, cpu, preservation = construct(raw, decoded, frames, sections, model)
    project = PROFILES[model][1]
    host = strict_decode(candidate, True)
    require(host['decoded_sha256'] == sha(target), 'independent strict decode differs')
    require(host['source_authenticity'] == 'unverified', 'synthetic candidate called official')
    require(outer(rom, raw, project) == 1, 'official ARM outer validation failed')
    require(outer(rom, candidate, project) == 1, 'memory candidate ARM outer validation failed')
    rows = []
    for mode in ('bad_sum', 'wrong_model_repaired', 'wrong_type_repaired', 'truncated_repaired'):
        data = bytearray(candidate)
        if mode == 'bad_sum':
            data[0x38] ^= 1
        elif mode == 'wrong_model_repaired':
            other = 609 if model == 'gr3' else 588
            for at, value in ((0x30, other), (0x78, other | other << 16), (len(data)-24, other | other << 16)):
                struct.pack_into('<I', data, at, value)
        elif mode == 'wrong_type_repaired':
            struct.pack_into('<I', data, len(data)-16, 5)
        else:
            data = data[:128]+data[-24:]
        if mode != 'bad_sum':
            repair(data, len(data)-4)
        accepted = bool(outer(rom, data, project))
        # Outer validation has no frame-bounds/decompression check: a physically
        # truncated payload with its intact footer and repaired sum passes it.
        require(accepted == (mode == 'truncated_repaired'), 'ARM negative result differs: '+mode)
        host_result = strict_decode(data, False)
        rows.append(dict(case=mode, arm_outer_accepted=accepted, strict_host=host_result))
    # Whole decoded stream checksum, executing original ARM independently of
    # the host decoder. This entry does not parse the individual sections.
    for changed in (False, True):
        data = bytearray(target)
        if changed:
            data[0x200] ^= 1
        accepted = bool(arm(rom, data, DECODED_SUM, [(16, DATA), (20, len(data))]))
        require(accepted != changed, 'ARM decoded checksum result differs')
        rows.append(dict(case='decoded_bad_sum' if changed else 'decoded_sum', arm_decoded_checksum_accepted=accepted))
    found, (pointer, length) = arm(rom, target, 0x5362bd64,
        [(16, DATA), (20, len(target))], outputs=True)
    cs, ce = sections['CPU']
    require(found == 1 and pointer == DATA+cs and length == ce-cs, 'original CPU section lookup differs')
    rows.append(dict(case='cpu_section_lookup', arm_found=True,
        decoded_offset=hex(pointer-DATA), payload_bytes=length))
    for kind in (5, 7):
        accepted = bool(arm(rom, cpu, 0x53628c94, [(0x2c, kind)]))
        require(not accepted, 'unsupported dispatch type accepted')
        rows.append(dict(case='unsupported_dispatch_type', kind=kind, arm_dispatch_accepted=accepted))
    for mode in ('proposed', 'bad_sum', 'wrong_model_repaired'):
        data = bytearray(cpu)
        if mode == 'bad_sum':
            data[0x93] ^= 1
        elif mode == 'wrong_model_repaired':
            struct.pack_into('<I', data, 0x80, 609 if model == 'gr3' else 588)
            repair(data, 0x7c, '>')
        accepted = bool(arm(rom, data, CPU, [(12, DATA), (20, project)]))
        require(accepted == (mode == 'proposed'), 'ARM CPU result differs: '+mode)
        rows.append(dict(case='cpu_'+mode, arm_cpu_accepted=accepted))
    # Execute complete-parser entry only until its original decompression
    # routine is reached; never substitute a successful decoder return.
    arm(rom, candidate, FULL_PARSER, [(8, DATA), (12, len(candidate)), (24, project), (28, 2)], stop=DECOMPRESS)
    return dict(status='offline_partial_evidence', model=model, source_sha256=sha(raw),
        installation_allowed=False, camera_verified=False, stable=False, bin_emitted=False,
        preservation=preservation, strict_host_candidate=host, cases=rows, count=len(rows)+3,
        original_arm_entries={'outer': hex(OUTER), 'decoded_checksum': hex(DECODED_SUM), 'cpu': hex(CPU)},
        full_parser_boundary={'entry': hex(FULL_PARSER), 'reached': hex(DECOMPRESS),
            'completed': False, 'hardware_mmio_base': '0x1b030000',
            'configuration_functions': ['0x538580d0', '0x53858140'],
            'hardware_start': '0x53857fbc', 'status_and_interrupt_wait': '0x53857fd8'},
        remaining_blockers=['original_hardware_decompression_not_executed', 'complete_section_parser_not_executed',
            'flash_dispatch_not_executed', 'flash_erase_write_and_readback_not_executed',
            'minimal_bridge_boot_not_verified', 'persistent_settings_downgrade_not_verified',
            'old_official_boot_and_hardware_recovery_not_verified', 'shop_service_updater_unknown'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--new', required=True, type=Path)
    parser.add_argument('--model', required=True, choices=PROFILES)
    parser.add_argument('--report', type=Path, help='optional new JSON report only')
    args = parser.parse_args()
    try:
        if args.report:
            require(args.report.suffix.lower() == '.json', 'research output must be JSON, never firmware')
        result = probe(args.new, args.model)
        output = json.dumps(result, indent=2)+'\n'
        if args.report:
            with args.report.open('x') as file:
                file.write(output)
        print(output, end='')
        return 2
    except Exception as error:
        print(json.dumps(dict(status='rejected', installation_allowed=False, bin_emitted=False, reason=str(error))))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
