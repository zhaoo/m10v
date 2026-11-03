"""Lab-only combined bridge variant preserving the entire official CPU image.

This variant deliberately has distinct DSP/CPU package versions. The production
importer MUST continue rejecting it. Only in-memory containers, exact-source
byte comparisons and bounded original ARM gate calls are used; no BIN is emitted.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from scripts.probe_gr3_anniversary_container import (
    source, replay, repair, sum32, outer, arm, strict_decode, CPU, DECODED_SUM, DATA,
)
from scripts.probe_gr3_anniversary_downgrade import PROFILES, read_source, gate, require, version
from scripts.probe_gr3_anniversary_decompress_contract import driver_prefix, frame_shapes

ROOT = Path(__file__).resolve().parents[1]


def decoded_hash(raw):
    js = """import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {decodeFrameMap} from './node/gr3-frames.mjs';
const {decoded}=decodeFrameMap(readFileSync(0));
process.stdout.write(createHash('sha256').update(decoded).digest('hex'));"""
    return subprocess.check_output(['node', '--input-type=module', '-e', js], cwd=ROOT,
                                   input=raw, timeout=60).decode()


def preserve_compressed_trailer(raw, original, target, repacked, frame):
    """Patch checksum literal tokens, preserving the final compressed frame shape."""
    require(not frame['literal'] and frame['decoded_end'] == len(target), 'last original frame shape differs')
    start, used = frame['decoded_start'], frame['decoded_start']
    require(original[max(0, start-8191):-4] == target[max(0, start-8191):-4], 'last frame dictionary or body changed')
    block = bytearray(raw[128+frame['encoded_start']:128+frame['encoded_end']])
    at, literals, terminated = 2, {}, False
    while at < len(block) and not terminated:
        require(at+2 <= len(block), 'truncated trailer flags')
        flags = struct.unpack_from('>H', block, at)[0]
        at += 2
        for bit in range(15, -1, -1):
            if not flags & (1 << bit):
                require(at < len(block), 'truncated trailer literal')
                if used >= len(target)-4:
                    literals[used] = at
                used += 1
                at += 1
                continue
            require(at+2 <= len(block), 'truncated trailer reference')
            first, second = block[at:at+2]
            at += 2
            offset, count = ((first & 0xf8) << 5) | second, first & 7
            if count == 7:
                require(at < len(block), 'truncated trailer extension')
                count += block[at]
                at += 1
            if offset == 0:
                require(at == len(block), 'trailing compressed frame bytes')
                terminated = True
                break
            if count == 262:
                extra = 255
                while extra == 255:
                    require(at < len(block), 'truncated long trailer reference')
                    extra = block[at]
                    at += 1
                    count += extra
            require(offset <= used and used+count+3 <= len(target), 'invalid trailer reference')
            used += count+3
    require(terminated and used == len(target) and set(literals) == set(range(len(target)-4, len(target))),
            'decoded trailer is not four direct literal tokens')
    for position, encoded in literals.items():
        block[encoded] = target[position]
    # The existing conservative replay made this final frame a literal block.
    # Replace only that block; preserve all prior replay decisions and framing.
    at, end, last = 128, 128+struct.unpack_from('<I', repacked, len(repacked)-12)[0], None
    while at+2 <= end:
        prefix = struct.unpack_from('>H', repacked, at)[0]
        if prefix == 0:
            require(at+2 == end, 'replayed trailer terminator differs')
            break
        last = at
        at += 2+(prefix & 0x7fff)
    require(last is not None and repacked[last+2:at] == target[start:], 'replayed last literal differs')
    payload = bytes(repacked[128:last])+bytes(block)+b'\0\0'
    footer = bytearray(repacked[-24:])
    struct.pack_into('<I', footer, 12, len(payload))
    result = bytearray(repacked[:128]+payload+bytes(-(128+len(payload)) & 3)+footer)
    repair(result, len(result)-4)
    return result, dict(original_compressed_bytes=len(block),
        changed_literal_offsets=[hex(v) for v in literals.values()],
        flags_references_and_frame_length_preserved=True)


def probe(new_file, old_file, model):
    require(model in PROFILES, 'unsupported model')
    profile = PROFILES[model]
    raw, decoded, frames, sections = source(new_file, model)
    old_raw, old_sections = read_source(old_file, profile['old_sha'])
    start, end = sections['RTOS']
    cs, ce = sections['CPU']
    rom, cpu = decoded[start:end], decoded[cs:ce]
    current, proposed = profile['new_version'], profile['new_version']+256
    require(rom[0x6286cc:0x6286d0] == bytes.fromhex('e42103e3'), 'updater instruction preimage differs')
    require(cpu[0x5132:0x5136] == bytes.fromhex('76310014'), 'RX version getter instruction differs')
    # Independently identified RX OR #0x1400,r1, not an ARM instruction.
    runtime_cpu_component = struct.unpack_from('<H', cpu, 0x5134)[0] >> 8
    require(runtime_cpu_component == ((current >> 8) & 255), 'official CPU getter/header disagree')
    target = bytearray(decoded)
    struct.pack_into('>I', target, start+0x2038, proposed)
    target[start+0x6286cc:start+0x6286d0] = bytes.fromhex('e6ffffea')
    repair(target, len(target)-4)
    allowed = [(start+0x2038, 4), (start+0x6286cc, 4), (len(target)-4, 4)]
    changed = [i for i, (before, after) in enumerate(zip(decoded, target)) if before != after]
    require(all(any(at <= i < at+size for at, size in allowed) for i in changed), 'non-target decoded bytes changed')
    require(target[cs:ce] == cpu, 'CPU image changed')
    candidate, reused, replaced = replay(raw, decoded, target, frames)
    candidate, trailer = preserve_compressed_trailer(raw, decoded, target, candidate, frames[-1])
    struct.pack_into('>I', candidate, 0x38, proposed)  # DSP outer version, NOT CPU
    repair(candidate, len(candidate)-4)
    require(candidate[0x50:0x54] == raw[0x50:0x54], 'outer CPU version changed')
    require(candidate[-24:-12] == raw[-24:-12] and struct.unpack_from('<I', candidate, len(candidate)-16)[0] == 2,
            'combined footer kind changed')
    require(all(a == b or 0x38 <= i < 0x3c for i, (a, b) in enumerate(zip(raw[:128], candidate[:128]))),
            'unapproved outer header change')
    require(sum32(candidate) == 0 and sum32(target) == 0 and sum32(cpu, '>') == 0, 'additive checksum differs')
    require(decoded_hash(candidate) == hashlib.sha256(target).hexdigest(), 'independent frame replay differs')
    rejection = strict_decode(candidate, False)
    require(rejection['reason'] == 'version: component copies differ', 'unexpected production import result')
    require(outer(rom, candidate, profile['project']) == 1, 'original outer validator rejected the memory variant')
    require(arm(rom, target, DECODED_SUM, [(16, DATA), (20, len(target))]) == 1, 'original decoded checksum differs')
    require(arm(rom, cpu, CPU, [(12, DATA), (20, profile['project'])]) == 1, 'original CPU validator rejected unchanged official CPU')
    first = []
    for kind in (0, 1, 2, 3, 4, 6):
        for dsp, actual_cpu, expected in (
                (current, current, True), (proposed, current, True),
                (proposed+1, current, kind == 6), (current, current+1, kind in (0, 1))):
            accepted = gate(rom, dsp, actual_cpu, candidate, cpu, kind)
            require(accepted == expected, 'separate component admission differs')
            first.append(dict(kind=kind, current_dsp=version(dsp), current_cpu=version(actual_cpu), accepted=accepted))
    patched = bytes(target[start:end])
    second = []
    for updated in (False, True):
        accepted = gate(patched if updated else rom, current, current, old_raw, old_sections['CPU'], 2)
        require(accepted == updated, 'exact old official gate result differs')
        second.append(dict(kind=2, patched=updated, accepted=accepted))
    driver = driver_prefix(rom, candidate)
    return dict(schema='m10v-anniversary-cpu-preserved-research/v1', model=model,
        status='lab_gate_evidence_production_import_rejected', source_sha256=profile['new_sha'],
        restore_sha256=profile['old_sha'], installation_allowed=False, camera_verified=False,
        stable=False, bin_emitted=False, candidate_authenticity='unverified',
        combined_footer_kind=2, dsp_package_version=version(proposed), cpu_package_version=version(current),
        cpu_payload_sha256=hashlib.sha256(cpu).hexdigest(), cpu_entirely_preserved=True,
        cpu_getter_third_component=runtime_cpu_component,
        prior_all_fields_raised_model=dict(declared_third_component=(proposed >> 8) & 255,
            actual_getter_third_component=runtime_cpu_component, internally_consistent=False,
            original_probe_replaced_getters=True),
        changed_decoded_bytes=len(changed), changed_decoded_offsets=[hex(i) for i in changed],
        unchanged_sections=[name for name, (a, b) in sections.items() if decoded[a:b] == target[a:b]],
        original_frames_reused=reused, original_frames_replaced=replaced,
        original_frames_replaced_with_literals=replaced-1,
        original_compressed_trailer_preserved=trailer,
        frame_replay_matches_target=True, production_import=rejection,
        original_frames=frame_shapes(raw), memory_variant_frames=frame_shapes(candidate),
        decompressor_driver_prefix=driver,
        original_arm_outer_accepted=True, original_arm_decoded_checksum_accepted=True,
        original_arm_cpu_accepted=True, first_stage_version_cases=first, second_stage_version_cases=second,
        scope='Original ARM local admission with explicit version getter inputs; no real CPU communication or boot',
        remaining_blockers=['production_policy_intentionally_rejects_mixed_component_versions',
            'candidate_hardware_decompression_not_verified', 'original_cpu_update_state_machine_not_executed',
            'flash_write_readback_and_two_stage_boot_not_verified', 'actual_settings_and_recovery_not_verified'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--new', required=True, type=Path)
    parser.add_argument('--old', required=True, type=Path)
    parser.add_argument('--model', required=True, choices=PROFILES)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    try:
        if args.report:
            require(args.report.suffix.lower() == '.json', 'research output must be JSON, never firmware')
            require(not args.report.exists(), 'research report already exists')
        result = probe(args.new, args.old, args.model)
        output = json.dumps(result, ensure_ascii=False, indent=2)+'\n'
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
