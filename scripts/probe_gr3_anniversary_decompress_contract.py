"""Trace original decompressor register programming, stopping BEFORE hardware wait.

Only reads the exact official input files and optionally creates a new JSON
report. The proposed container exists in memory. No decompressor completion,
decoded output, Flash IO or successful camera boot is simulated.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC

from scripts.probe_gr3_anniversary_container import (
    DATA, RAM, STOP, PROFILES, source, construct, machine, strict_decode, require,
)
from scripts.probe_gr3_anniversary_downgrade import read_source, PROFILES as IDENTITIES

DRIVER, WAIT, MMIO = 0x537f9438, 0x53857fd8, 0x1b030000
OUTPUT = 0x60000000
FUNCTIONS = ((0x53857fbc, 0x53857fd8), (0x538580d0, 0x53858128), (0x53858140, 0x538581d4))


def frame_shapes(raw):
    size = struct.unpack_from('<I', raw, len(raw)-12)[0]
    data = raw[128:128+size]
    at, literal, compressed = 0, [], []
    while at+2 <= len(data):
        prefix = struct.unpack_from('>H', data, at)[0]
        at += 2
        if prefix == 0:
            require(at == len(data), 'trailing frame bytes')
            return dict(frame_count=len(literal)+len(compressed), literal_count=len(literal),
                        literal_lengths=sorted(set(literal)), compressed_count=len(compressed))
        length = prefix & 0x7fff
        require(length > 0 and at+length <= len(data), 'invalid frame boundary')
        (literal if prefix & 0x8000 else compressed).append(length)
        at += length
    raise ValueError('missing frame terminator')


def driver_prefix(rom, raw, enabled=True):
    """Execute the exact original ARM prefix on virtual RAM/MMIO, then stop."""
    encoded_size = struct.unpack_from('<I', raw, len(raw)-12)[0]
    u = machine(rom, raw)
    u.mem_map(MMIO, 0x1000)
    # The original configuration function stores a callback in this RAM page.
    # It is not an emulated peripheral and is never used to synthesize a result.
    u.mem_map(0x55373000, 0x2000)
    engine, descriptor = RAM+0x1000, RAM+0x2000
    u.mem_write(engine+4, bytes([bool(enabled)]))
    u.mem_write(descriptor, struct.pack('<IIII', DATA+128, OUTPUT, encoded_size, 0))
    writes, boundaries = [], []

    def write(cpu, access, address, width, value, userdata):
        writes.append(dict(address=hex(address), width=width, value=value))

    def boundary(cpu, address, width, userdata):
        boundaries.append(address)
        cpu.emu_stop()

    u.hook_add(UC_HOOK_MEM_WRITE, write, begin=MMIO, end=MMIO+0xfff)
    for address in (WAIT, STOP):
        u.hook_add(UC_HOOK_CODE, boundary, begin=address, end=address)
    u.reg_write(UC_ARM_REG_R0, engine)
    u.reg_write(UC_ARM_REG_R1, descriptor)
    u.reg_write(UC_ARM_REG_SP, RAM+0xff000)
    u.reg_write(UC_ARM_REG_LR, STOP)
    u.emu_start(DRIVER, 0, count=100000)
    expected = WAIT if enabled else STOP
    require(boundaries == [expected] and u.reg_read(UC_ARM_REG_PC) == expected,
            'driver did not reach its declared boundary')
    values = {hex(at): struct.unpack('<I', u.mem_read(at, 4))[0]
              for at in (MMIO+4, MMIO+8, MMIO+0x18, MMIO+0x1c, MMIO+0x20, MMIO+0x24, MMIO+0x2c)}
    if enabled:
        require(values == {hex(MMIO+4): 1, hex(MMIO+8): 1, hex(MMIO+0x18): DATA+128,
                          hex(MMIO+0x1c): DATA+128+encoded_size, hex(MMIO+0x20): OUTPUT,
                          hex(MMIO+0x24): 0, hex(MMIO+0x2c): 1}, 'original register contract differs')
        require(len(writes) == 12, 'original MMIO write sequence differs')
    else:
        require(not writes and u.reg_read(UC_ARM_REG_R0) == 0,
                'disabled engine unexpectedly programmed hardware')
    return dict(entry=hex(DRIVER), reached=hex(expected), enabled=enabled,
                writes=writes, registers=values, encoded_bytes=encoded_size,
                wait_executed=False, interrupt_synthesized=False,
                hardware_decoded=False, completion_substituted=False)


def probe(new_file, old_file, model):
    require(model in PROFILES, 'unsupported model')
    raw, decoded, frames, sections = source(new_file, model)
    _, old_sections = read_source(old_file, IDENTITIES[model]['old_sha'])
    candidate, target, rom, cpu, preservation = construct(raw, decoded, frames, sections, model)
    host = strict_decode(candidate, True)
    require(host['decoded_sha256'] == preservation['decoded_sha256'], 'host replay differs')
    unchanged = []
    old_rom = old_sections['RTOS']
    for start, end in FUNCTIONS:
        code = rom[start-0x53000000:end-0x53000000]
        require(old_rom.count(code) == 1, 'old hardware register programmer is not an exact unique match')
        unchanged.append(dict(new_address=hex(start), old_address=hex(0x53000000+old_rom.index(code)),
                              bytes=len(code), sha256=hashlib.sha256(code).hexdigest()))
    official = driver_prefix(rom, raw)
    proposed = driver_prefix(rom, candidate)
    disabled = driver_prefix(rom, raw, False)
    differences = [key for key, value in official['registers'].items() if proposed['registers'][key] != value]
    require(differences in ([], [hex(MMIO+0x1c)]), 'non-length hardware configuration changed')
    return dict(schema='m10v-anniversary-decompress-contract/v1', model=model,
                source_sha256=IDENTITIES[model]['new_sha'], old_source_sha256=IDENTITIES[model]['old_sha'],
                status='offline_configuration_prefix_only', installation_allowed=False,
                camera_verified=False, stable=False, bin_emitted=False,
                original_driver_blocks_identical=unchanged,
                official_frames=frame_shapes(raw), in_memory_frames=frame_shapes(candidate),
                official=official, proposed=proposed, disabled_engine=disabled,
                differing_registers=differences, preservation=preservation,
                full_entry_scope='0x5362c218 runs outer admission then decompression and decoded checksum, not complete section validation',
                remaining_blockers=['hardware_decoder_output_and_error_status_not_observed',
                    'completion_event_and_cache_coherency_not_verified', 'full_section_write_dispatch_not_verified',
                    'flash_erase_write_readback_not_executed', 'two_stage_cold_boot_not_verified',
                    'actual_persistent_settings_not_observed', 'hardware_recovery_not_verified'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--new', type=Path, required=True)
    parser.add_argument('--old', type=Path, required=True)
    parser.add_argument('--model', choices=PROFILES, required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    try:
        if args.report:
            require(args.report.suffix.lower() == '.json', 'research output must be JSON, never firmware')
            require(not args.report.exists(), 'research report already exists')
        result = probe(args.new, args.old, args.model)
        text = json.dumps(result, ensure_ascii=False, indent=2)+'\n'
        if args.report:
            with args.report.open('x') as file:
                file.write(text)
        print(text, end='')
        return 2
    except Exception as error:
        print(json.dumps(dict(status='rejected', installation_allowed=False, bin_emitted=False, reason=str(error))))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
