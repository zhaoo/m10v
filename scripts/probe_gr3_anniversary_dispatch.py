"""Pinned original ARM routing/partition research; JSON only, never Flash success.

Dispatch runs with synthetic object flags and explicitly skipped UI/delay calls.
Writers stop at entry, or the CPU writer returns injected FAILURE, never success.
The PARTPARA builder executes original ARM against RAM and an explicitly selected
512-byte device class; this does not read actual camera geometry or storage.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R4, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC

from scripts.probe_gr3_anniversary_container import machine, source, LOAD, RAM, DATA, STOP, require
from scripts.probe_gr3_anniversary_downgrade import PROFILES, read_source, ROOT

DISPATCH, COMBINED, PARTITIONS = 0x53628db0, 0x5362aa8c, 0x53629a94
CPU_WRITER, DSP_WRITER = 0x5362971c, 0x5362a5b0
IDENTITIES = {
    DISPATCH: (0xd0, '4ad51d5d26149ae3aa0c3d05b70c1a7c1e793d6c1e6ad9ade0765fc9a0fe8ba4'),
    COMBINED: (0x54, '56598ebb854c0e97037530f487bfe887351ad156174ce83ff8930dc0ea457d23'),
    PARTITIONS: (0x1b8, '0024fb028c1476c74ba71c3e078963d6573165670e6fd249ed52d1bf22fb17bf'),
    0x537fb0e4: (8, '732254e783751fcde0d42a21270c5e4b8f2ea029fe41215bd85bfbcc79455a7f'),
    0x5362aa14: (0x78, '9adb23b0578f960339cbe340c2275dc9fca1ba16358d95c3580a638690124f50'),
    0x5362bd64: (0x54, 'cc7ba5a1e251988e77cad36111e956065d79fa78c64ecb7db53cde327013230d'),
    0x5362911c: (0x220, '3566c8a42df9bb4a5ba02f482bb97e92fd505f407bc59e4111d5f63f74e4d340'),
}


def code_identity(rom, entries):
    for entry in entries:
        length, expected = IDENTITIES[entry]
        require(hashlib.sha256(rom[entry-LOAD:entry-LOAD+length]).hexdigest() == expected,
                f'original ARM code identity differs at {entry:#x}')


def put(u, address, value):
    u.mem_write(address, struct.pack('<I', value))


def ram_writes_only(u):
    def check(u, access, address, size, value, user):
        require(RAM <= address and address+size <= RAM+0x100000, 'non-RAM write attempted')
    u.hook_add(UC_HOOK_MEM_WRITE, check)


def start(u, entry, obj, count):
    u.reg_write(UC_ARM_REG_R0, obj)
    u.reg_write(UC_ARM_REG_SP, RAM+0xf0000)
    u.reg_write(UC_ARM_REG_LR, STOP)
    ram_writes_only(u)
    u.emu_start(entry, STOP, count=count)


def dispatch_case(rom, kind, *, cpu_enabled=True, dsp_enabled=True, cpu_failure=False):
    require(isinstance(kind, int) and 0 <= kind <= 6, 'unsupported footer kind')
    code_identity(rom, [DISPATCH, COMBINED])
    u = machine(rom, b'\0'*4)
    obj, dsp, cpu, ui, combined = (RAM+offset for offset in (0x1000, 0x2000, 0x3000, 0x4000, 0x5000))
    for offset, value in [(0x18, ui), (0x1c, dsp), (0x20, cpu), (0x24, combined), (0x2c, kind)]:
        put(u, obj+offset, value)
    put(u, combined+0x10, dsp)
    put(u, combined+0x14, cpu)
    u.mem_write(combined+0x28, bytes([bool(dsp_enabled)]))
    u.mem_write(combined+0x34, bytes([bool(cpu_enabled)]))
    writers, skipped, boundary = [], [], []
    ui_delay = {0x5362b58c: 'initial UI/delay', 0x5362b9a0: 'progress UI', 0x536b0b64: 'delay'}

    def route(u, address, size, user):
        if address in ui_delay:
            skipped.append(dict(address=hex(address), role=ui_delay[address]))
            u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))
        elif address in (CPU_WRITER, DSP_WRITER):
            writer = 'cpu' if address == CPU_WRITER else 'dsp'
            writers.append(writer)
            require(u.reg_read(UC_ARM_REG_R0) == (cpu if writer == 'cpu' else dsp), 'writer object differs')
            if writer == 'cpu' and cpu_failure:
                # Fault injection only. No real CPU protocol or flash body runs.
                u.reg_write(UC_ARM_REG_R0, 0)
                u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))
            else:
                boundary.append(writer+'_writer_entry')
                u.emu_stop()

    u.hook_add(UC_HOOK_CODE, route)
    start(u, DISPATCH, obj, 5000)
    pc = u.reg_read(UC_ARM_REG_PC)
    require(boundary or pc == STOP, 'dispatch instruction bound exceeded')
    return dict(footer_kind=kind, cpu_flag=bool(cpu_enabled), dsp_flag=bool(dsp_enabled),
        boundary=boundary[0] if boundary else 'returned',
        return_value=None if boundary else u.reg_read(UC_ARM_REG_R0), writer_entries=writers,
        fault_injection='CPU writer returns failure (0)' if cpu_failure and 'cpu' in writers else None,
        skipped_non_storage_calls=skipped, writer_body_executed=False, flash_write_executed=False,
        actual_cpu_protocol_executed=False)


def prepare_combined_cpu(rom, decoded, project):
    """Resume at CPU extraction using supplied decoded RAM, not a fake decoder.

This bounded block skips the earlier outer/decompression calls completely;
it cannot prove a complete update. It executes the actual section scan,
CPU-object setter, CPU validator and flag store without replacing them.
"""
    code_identity(rom, [0x5362aa14, 0x5362bd64, 0x5362911c])
    require(0 < len(decoded) <= 0x8000000, 'decoded length outside research bound')
    require(project in (588, 589, 609, 610), 'project outside research cases')
    u = machine(rom, decoded)
    obj, parser, cpu = RAM+0x1000, RAM+0x2000, RAM+0x3000
    for offset, value in [(0xc, parser), (0x14, cpu), (0x38, project), (0x3c, 2)]:
        put(u, obj+offset, value)
    put(u, parser+0x10, DATA)
    put(u, parser+0x14, len(decoded))
    u.reg_write(UC_ARM_REG_R4, obj)
    boundaries, getters = [], []

    def boundary(u, address, size, user):
        if address in (0x53547c9c, 0x53547ce0):
            getters.append(hex(address))
            raise ValueError('unexpected version getter in CPU preparation')
        if address in (CPU_WRITER, DSP_WRITER):
            raise ValueError('unexpected writer in CPU preparation')
        if address in (0x5362aa54, 0x5362a9ec):
            boundaries.append('cpu_flag_written' if address == 0x5362aa54 else 'cpu_section_not_found')
            u.emu_stop()

    u.hook_add(UC_HOOK_CODE, boundary)
    start(u, 0x5362aa14, obj, 2000000)
    require(boundaries, 'CPU preparation instruction bound exceeded')
    pointer, length = struct.unpack('<II', u.mem_read(cpu+0xc, 8))
    require(not pointer or DATA <= pointer and pointer+length <= DATA+len(decoded), 'CPU section pointer differs')
    payload = bytes(u.mem_read(pointer, length)) if pointer else b''
    return dict(boundary=boundaries[0], cpu_enabled=bool(u.mem_read(obj+0x34, 1)[0]),
        cpu_bytes=length, cpu_payload_sha256=hashlib.sha256(payload).hexdigest(),
        version_getters_called=getters, flash_write_executed=False,
        decoded_supplied_as_ram=True, hardware_decompression_executed=False,
        scope='CPU section scan, setter, validator and enabled flag only; earlier decoding is outside this block')


def partition_layout(rom, partpara, *, count=32, bank=0):
    require(len(partpara) == 516, 'PARTPARA length differs')
    require(isinstance(count, int) and 0 <= count <= 255, 'invalid partition count')
    require(bank in (0, 1), 'invalid RAM partition bank')
    code_identity(rom, [PARTITIONS, 0x537fb0e4])
    u = machine(rom, b'\0'*4)
    obj, device, vtable, controller, data, output = (RAM+offset for offset in (0x1000, 0x2000, 0x3000, 0x4000, 0x5000, 0x10000))
    u.mem_write(data, bytes(partpara))
    for offset, value in [(8, device), (0x40, data), (0x48, count), (0x4c, controller)]:
        put(u, obj+offset, value)
    put(u, device, vtable)
    # Actual original vtable getter returns 0x200. Selection of this device class
    # is a synthetic input, not a measured camera sector size.
    put(u, vtable+0x48, 0x537fb0e4)
    put(u, controller+0x14, output)
    u.mem_write(controller+0x10, bytes([bank]))
    start(u, PARTITIONS, obj, 200000)
    require(u.reg_read(UC_ARM_REG_PC) == STOP, 'partition builder instruction bound exceeded')
    names = ['declared_bytes', 'load_address', 'jump_address', 'start_sector', 'auxiliary_bytes', 'auxiliary_sectors']
    offsets = (0, 8, 0xc, 0x10, 0x14, 0x18)
    rows, expected = [], []
    sector = struct.unpack_from('<I', partpara)[0]
    for index in range(min(count, 32)):
        base = output+index*0x870
        # STR at 0x53629bf0 stores AreaSize outside the selected bank; the
        # other observed fields use the bank-adjusted pointer. Do not treat
        # both halves as fully independent copies of the complete record.
        values = [struct.unpack('<I', u.mem_read(base+offset+(bank*0x434 if offset else 0), 4))[0]
                  for offset in offsets]
        rows.append(dict(index=index, **dict(zip(names, values))))
        size, load, auxiliary, jump = struct.unpack_from('<4I', partpara, 4+index*16)
        expected.append(dict(index=index, **dict(zip(names, (size, load, jump, sector, auxiliary*512, auxiliary)))))
        sector = (sector+(size+511)//512) & 0xffffffff
    require(rows == expected, 'original ARM partition layout differs from independent calculation')
    return dict(partitions=rows, requested_count=count, effective_count=min(count, 32), bank=bank,
        matches_independent_layout=True, sector_bytes_assumption=512, actual_device_geometry_read=False,
        flash_write_executed=False, persistent_partition_table_written=False,
        partpara_sha256=hashlib.sha256(partpara).hexdigest())


def second_stage_decoded(file, model):
    require(model in PROFILES, 'unsupported model')
    # Identity and strict import are checked by read_source before a second,
    # memory-only decode of the same verified byte buffer. No arbitrary hash
    # override is accepted for the old official package.
    raw, _ = read_source(file, PROFILES[model]['old_sha'])
    js = """import {readFileSync} from 'node:fs';
import {decodeFrameMap} from './node/gr3-frames.mjs';
process.stdout.write(decodeFrameMap(readFileSync(0)).decoded);"""
    return subprocess.check_output(['node', '--input-type=module', '-e', js],
        cwd=ROOT, input=raw, timeout=60)


def probe(file, old_file, model):
    require(model in PROFILES, 'unsupported model')
    _, decoded, _, spans = source(file, model)
    sections = {name: decoded[a:b] for name, (a, b) in spans.items()}
    old_decoded = second_stage_decoded(old_file, model)
    rom = sections['RTOS']
    routes = [dispatch_case(rom, kind) for kind in range(7)]
    failures = [dispatch_case(rom, kind, cpu_failure=True) for kind in (2, 3, 4)]
    require(all(row['return_value'] == 0 and row['writer_entries'] == ['cpu'] for row in failures),
            'CPU failure did not stop combined dispatch')
    return dict(schema='m10v-anniversary-dispatch-research/v1', model=model,
        source_sha256=PROFILES[model]['new_sha'], status='bounded_ram_and_failure_branch_evidence',
        installation_allowed=False, camera_verified=False, stable=False, bin_emitted=False,
        routes=routes, combined_cpu_failure_cases=failures,
        disabled_cpu_case=dispatch_case(rom, 2, cpu_enabled=False),
        both_disabled_case=dispatch_case(rom, 2, cpu_enabled=False, dsp_enabled=False),
        cpu_preparation=prepare_combined_cpu(rom, decoded, PROFILES[model]['project']),
        second_stage_source_sha256=PROFILES[model]['old_sha'],
        second_stage_cpu_preparation=prepare_combined_cpu(rom, old_decoded, PROFILES[model]['project']),
        partition_builder=partition_layout(rom, sections['PARTPARA']),
        scope='Synthetic objects and default device class; no writer body or real hardware execution',
        remaining_blockers=['actual_cpu_protocol_and_hardware_decompression',
            'flash_erase_write_readback_and_power_failure_recovery', 'both_stage_cold_boot_and_actual_settings'])


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
        output = json.dumps(result, ensure_ascii=False, indent=2)+'\n'
        if args.report:
            with args.report.open('x') as file:
                file.write(output)
        print(output, end='')
        return 2  # Evidence remains incomplete; not a successful installation check.
    except Exception as error:
        print(json.dumps(dict(status='rejected', installation_allowed=False, bin_emitted=False, reason=str(error))))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
