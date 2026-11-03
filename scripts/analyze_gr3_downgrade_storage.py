"""Read-only pinned GR III/IIIx downgrade storage evidence; emits JSON only.

No emulated storage calls, firmware edits, BIN/ZIP output, or device accesses.
Disassembly is bounded to enumerated ranges. A separate ARM schema comparison
loop consumes synthetic table input and stops before the error/default path.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import struct
import subprocess
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_R5, UC_ARM_REG_PC

ROOT = Path(__file__).resolve().parents[1]
BASE = 0x53000000
SOURCES = {
    'gr3_old': ('bin/fwdc239b-gr3-official.bin', 'd6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4'),
    'gr3_new': ('/Users/zhaoo/Desktop/fwdc239b.bin', '5c53760b3b564c87239dbf7f5c94d0f6fd91accd156ec4ba672ebfd6b861793e'),
    'gr3x_old': ('bin/fwdc243b-gr3x-official.bin', '708e79f3b7b96a7e1581b4acf4c412233050a1832718ef7f06c8397db1b431c7'),
    'gr3x_new': ('/Users/zhaoo/Desktop/fwdc243b.bin', 'aa8e3ae1349d94e83be381c20530e41d5e57b75c27ef24ba81c7b017d6c11592'),
}
RANGES = [
    (0x53628c94, 0x53628e80), (0x5362911c, 0x53629134),
    (0x536293c4, 0x536297ac), (0x53629a0c, 0x53629a94),
    (0x53629a94, 0x53629f50), (0x53629f50, 0x5362a314),
    (0x5362a558, 0x5362aa8c), (0x5362aa8c, 0x5362aae0),
    (0x5362c3f8, 0x5362c544), (0x5362c7b8, 0x5362caa4),
    (0x5362cb80, 0x5362cdb4), (0x536b9e8c, 0x536ba00c),
    (0x536c1c0c, 0x536c1c84), (0x5324b35c, 0x5324b7f0),
    (0x53827eec, 0x53827f40),
]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(label):
    name, expected = SOURCES[label]
    file = Path(name) if Path(name).is_absolute() else ROOT / name
    raw = file.read_bytes()
    require(sha(raw) == expected, f'{label} source identity differs')
    js = """import {readFileSync} from 'node:fs';
import {inspectFirmwareImport} from './node/firmware.mjs';
import {decodeFrameMap} from './node/gr3-frames.mjs';
const b=readFileSync(process.argv[1]);
process.stdout.write(JSON.stringify(inspectFirmwareImport(b))+'\\n');
process.stdout.write(decodeFrameMap(b).decoded);"""
    output = subprocess.check_output(['node', '--input-type=module', '-e', js, str(file)], cwd=ROOT, timeout=60)
    header, decoded = output.split(b'\n', 1)
    meta = json.loads(header)
    sections, at = {}, 0
    for row in meta['sections']:
        sections[row['name']] = decoded[at+16:at+row['size']]
        at += row['size']
    require(at+4 == len(decoded), 'decoded section boundary differs')
    return dict(source=str(file), sha256=expected, sections=sections, internal_version=meta['internal_version'])


def schema(rom):
    # Original compare loop: ldr ip,[r2,#4]!; add r3,#1;
    # ldr r0,[r1,#4]!; cmp ip,r0. One occurrence in each exact RTOS.
    pattern = bytes.fromhex('04c0b2e5013083e20400b1e500005ce1')
    at = rom.find(pattern)
    require(at >= 0 and rom.find(pattern, at+1) == -1, 'schema loop identity differs')
    load_at = at-12
    instruction = struct.unpack_from('<I', rom, load_at)[0]
    require(instruction & 0xfffff000 == 0xe59f1000, 'schema literal load differs')
    literal_at = load_at+8+(instruction & 0xfff)
    pointer = struct.unpack_from('<I', rom, literal_at)[0]
    require(rom[at-0x44:at-0x40] == bytes.fromhex('135400e3'), 'schema word-count preimage differs')
    count = 0x413
    start = pointer-BASE+4  # original LDR preincrements r1 before first compare
    data = rom[start:start+count*4]
    require(len(data) == count*4, 'schema table out of bounds')
    return dict(compare=hex(BASE+at), literal=hex(BASE+literal_at),
                pointer_base=hex(pointer), actual_compared_start=hex(pointer+4),
                words=count, bytes=len(data), sha256=sha(data),
                raw_compare_preimage=rom[at:at+28].hex())


def diffs(old, new):
    positions = [i for i, (a, b) in enumerate(zip(old, new)) if a != b]
    result = []
    for _, group in itertools.groupby(enumerate(positions), lambda v: v[1]-v[0]):
        block = [v for _, v in group]
        start, end = block[0], block[-1]+1
        result.append(dict(start=hex(start), end_exclusive=hex(end), old=old[start:end].hex(), new=new[start:end].hex()))
    return result


def schema_guard(rom, table, changed_word=None):
    """Execute only the real comparison loop; input is NOT a camera settings dump."""
    layout = schema(rom)
    require(len(table) == layout['bytes'], 'synthetic schema table length differs')
    data = bytearray(table)
    if changed_word is not None:
        require(isinstance(changed_word, int) and 0 <= changed_word < layout['words'], 'invalid changed word')
        data[changed_word*4] ^= 1
    entry = int(layout['compare'], 16)
    branch = struct.unpack_from('<I', rom, entry-BASE+16)[0]
    require(branch >> 24 == 0x1a, 'schema mismatch branch preimage differs')
    displacement = branch & 0xffffff
    if displacement & 0x800000:
        displacement -= 0x1000000
    mismatch, matched = entry+24+displacement*4, entry+28
    u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    u.mem_map(BASE, (len(rom)+4095) & ~4095)
    u.mem_write(BASE, rom)
    u.mem_map(0x55000000, 0x10000)
    stored = 0x55001000
    u.mem_write(stored, bytes(data))
    u.reg_write(UC_ARM_REG_R1, int(layout['pointer_base'], 16))
    u.reg_write(UC_ARM_REG_R2, stored-4)
    u.reg_write(UC_ARM_REG_R3, 0)
    u.reg_write(UC_ARM_REG_R5, layout['words'])
    boundaries = []
    def stop(cpu, address, size, userdata):
        boundaries.append(address)
        cpu.emu_stop()
    for address in (mismatch, matched):
        u.hook_add(UC_HOOK_CODE, stop, begin=address, end=address)
    u.emu_start(entry, 0, count=20000)
    expected = matched if changed_word is None else mismatch
    require(boundaries == [expected] and u.reg_read(UC_ARM_REG_PC) == expected, 'schema guard branch differs')
    return dict(entry=hex(entry), reached=hex(expected), accepted=changed_word is None,
                compared_words=u.reg_read(UC_ARM_REG_R3), changed_word=changed_word,
                synthetic_table_input=True, actual_settings_read=False,
                default_or_error_path_executed=False, persistent_write_executed=False)


def disassembly(rom, start, end):
    engine = Cs(CS_ARCH_ARM, CS_MODE_ARM)
    rows = []
    # Per-word decode does not stop at embedded jump-table words.
    for address in range(start, end, 4):
        data = rom[address-BASE:address-BASE+4]
        instructions = list(engine.disasm(data, address))
        row = dict(address=hex(address), preimage=data.hex())
        if instructions:
            row.update(mnemonic=instructions[0].mnemonic, operands=instructions[0].op_str)
        else:
            row['data_word'] = hex(struct.unpack('<I', data)[0])
        rows.append(row)
    return dict(start=hex(start), end_exclusive=hex(end), sha256=sha(rom[start-BASE:end-BASE]), instructions=rows)


def analyze():
    inputs = {label: load(label) for label in SOURCES}
    comparisons = {}
    schemas = {}
    for label, value in inputs.items():
        schemas[label] = schema(value['sections']['RTOS'])
    require(len({v['sha256'] for v in schemas.values()}) == 1, 'settings schema changed')
    schema_execution = []
    for label, value in inputs.items():
        other = label.rsplit('_', 1)[0]+('_new' if label.endswith('_old') else '_old')
        table_rom = inputs[other]['sections']['RTOS']
        start = int(schemas[other]['actual_compared_start'], 16)-BASE
        table = table_rom[start:start+schemas[other]['bytes']]
        for changed_word in (None, 0, 521, 1042):
            schema_execution.append(dict(receiver=label, table_source=other,
                **schema_guard(value['sections']['RTOS'], table, changed_word)))
    for model in ('gr3', 'gr3x'):
        old, new = [inputs[model+'_'+version]['sections'] for version in ('old', 'new')]
        rows = []
        for name, before in old.items():
            after = new[name]
            rows.append(dict(name=name, old_bytes=len(before), new_bytes=len(after),
                             identical=before == after, old_sha256=sha(before), new_sha256=sha(after)))
        cpu_diff = diffs(old['CPU'], new['CPU'])
        allowed = [(0x7c, 0x80), (0x91, 0x94), (0x12b, 0x13f), (0x5135, 0x5136)]
        positions = [i for i, (a, b) in enumerate(zip(old['CPU'], new['CPU'])) if a != b]
        require(len(positions) == 28 and all(any(lo <= p < hi for lo, hi in allowed) for p in positions), 'CPU diff differs')
        comparisons[model] = dict(sections=rows, cpu_changed_bytes=len(positions), cpu_diff=cpu_diff,
            cpu_unchanged_outside_ranges=allowed,
            cpu_metadata_only_proven=False)
    rom = inputs['gr3_new']['sections']['RTOS']
    require(inputs['gr3x_new']['sections']['RTOS'][0x628c94:0x62aa8c] == rom[0x628c94:0x62aa8c], 'model storage routines differ')
    part = inputs['gr3_new']['sections']['PARTPARA']
    require(len(part) == 4+32*16, 'partition parameter table size differs')
    area = []
    running = struct.unpack_from('<I', part)[0]
    for i in range(32):
        size, load_address, spare, jump = struct.unpack_from('<4I', part, 4+i*16)
        sectors = (size+511)//512
        area.append(dict(index=i, area_bytes=hex(size), load_address=hex(load_address),
                         raw_third_word=hex(spare), jump_address=hex(jump),
                         derived_start_sector_512=hex(running), sectors_512=hex(sectors)))
        running += sectors
    drives = rom[0x10516c8:0x10516d8].decode('ascii').split('\0')[:-1]
    require(drives == ['J', 'A', 'B', 'E', 'F', 'G', 'H', 'I'], 'resource drive list differs')
    matrix = rom[0xd3400c:0xd3404c]
    masks = {str(kind): [drives[i] for i in range(8) if matrix[8*i+kind]] for kind in range(7)}
    require(masks['0'] == ['J','A','F','G','H','I'] and masks['1'] == drives and masks['2'] == ['J','A','G','H'], 'resource format matrix differs')
    return dict(status='offline_static_storage_evidence', installation_allowed=False, camera_verified=False,
        stable=False, bin_emitted=False, flash_io_executed=False,
        inputs={k: {n: v[n] for n in ('source','sha256','internal_version')} for k,v in inputs.items()},
        comparisons=comparisons, userdata_schema=schemas, userdata_schema_arm_cases=schema_execution,
        storage_code_identical_between_new_models=True,
        partition_parameter_sha256=sha(part), partition_initial_sector=hex(struct.unpack_from('<I',part)[0]),
        partition_area_map_512_byte_sector_assumption=area,
        format_drive_names=drives, format_matrix_preimage=matrix.hex(), format_drives_by_footer_kind=masks,
        kind_setter={'dispatch_load':'0x53628d74','dispatch_stack_store':'0x53628d8c','setter_store':'0x53629a30',
                     'combined_pass':'0x5362aa60..0x5362aa80','same_as_footer_kind':True},
        raw_clear_partition_groups={'10..14':'0x5362a2f4','21..25':'0x5362a2b8 -> 0x536b9e8c',
                                    '26..30':'0x5362a25c -> 0x536c1c0c','21_and_26_groups_skipped_for_kind2':True},
        settings_store_path_evidence={'format_string':'0x54056460 F:\\KB%ld.DOM','constructor':'0x53827f18..0x53827f30',
                                      'alternate_path':'0x54056450 C:\\KB%ld.DOM',
                                      'normal_path_selection_not_fully_proven':True},
        disassembly=[disassembly(rom,a,z) for a,z in RANGES],
        boundaries=['no_full_storage_state_machine_execution','no_emmc_vtable_resolution',
                    'no_settings_value_semantic_or_all_domain_schema_compatibility_proof',
                    'no_rx_cpu_execution_or_flash_io','no_boot_or_hardware_recovery_validation'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    require(args.report.suffix == '.json', 'JSON report only')
    require(not args.report.exists(), 'refuse report overwrite')
    result = analyze()
    with args.report.open('x') as out:
        json.dump(result, out, indent=2)
        out.write('\n')
    print(json.dumps(dict(status=result['status'], report=str(args.report),
                         userdata_schema_sha256=result['userdata_schema']['gr3_new']['sha256'],
                         format_drives_by_footer_kind=result['format_drives_by_footer_kind'],
                         installation_allowed=False, bin_emitted=False)))
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
