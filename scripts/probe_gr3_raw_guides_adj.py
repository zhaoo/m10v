"""Audit RAW identity, guide hook sites, and stock ADJ bounds on two final BINs."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM
from unicorn import arm_const as arm


ROOT = Path(__file__).resolve().parents[1]
ROM = 0x53000000
RAM = 0x55000000
ENTRY, SI, METADATA, SP, STOP = [RAM + n for n in (0x1000, 0x2000, 0x80000, 0xfe000, 0xff000)]
RAW_READER = 0x535bf7a8
PLAYBACK_READER = 0x535c24ec
RAW_LIST_COUNT = 0x53283358
RAW_DIAL_COUNT = 0x53283c08
SITES = {
    'raw_record_decode': (0x535bf7c4, 0xe2400c01),
    'raw_tag_dispatch_exif': (0x535eefdc, 0xebff41f1),
    'raw_tag_dispatch_dng': (0x53618d74, 0xebfe9a8b),
    'raw_tag_dispatch_alt': (0x5361ef0c, 0xebfe8225),
    'raw_option_list': (0x53283358, 0xe5d03005),
    'raw_option_capacity': (0x532833bc, 0xe3a0000f),
    'raw_option_base': (0x532834d0, 0xe5d03005),
    'raw_option_tone': (0x532834f0, 0xe1a0c00d),
    'raw_enum_to_tone': (0x53289058, 0xe1a0c00d),
    'raw_tone_to_enum': (0x53288d5c, 0xe241100b),
    'raw_apply': (0x53289240, 0xe1a0c00d),
    'canvas_draw': (0x53391b14, 0xe1a0c00d),
    'canvas_children': (0x53391be0, 0xeb000850),
    'live_view_update': (0x5317681c, 0xe1a0c00d),
    'adj_slot_dispatch_bound': (0x531a2840, 0xe3540004),
    'adj_icon_pointer': (0x531a425c, 0xe5987184),
    'adj_cell_pointer': (0x531a4264, 0xe598616c),
    'adj_render_bound': (0x531a42bc, 0xe3550005),
    'adj_fifth_stock_setting': (0x53270bb4, 0xe5d0e920),
    'adj_adjacent_stock_setting': (0x53270bbc, 0xe5d0a922),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def decode(path):
    return subprocess.check_output(['node', '--input-type=module', '-e', """
import {readFileSync} from 'node:fs';
import {decodeFrameMap} from './node/gr3-frames.mjs';
const b=readFileSync(process.argv[1]);
const d=decodeFrameMap(b,b.readUInt32LE(b.length-8)).decoded;
if(d.toString('ascii',0x10860,0x10864)!=='RTOS') throw Error('RTOS section mismatch');
process.stdout.write(d.subarray(0x10870,0x10870+d.readUInt32LE(0x1086c)));
""", str(path)], cwd=ROOT)


def call(cpu, address, *args, stop=STOP):
    for reg, arg in zip((arm.UC_ARM_REG_R0, arm.UC_ARM_REG_R1, arm.UC_ARM_REG_R2), args):
        cpu.reg_write(reg, arg)
    cpu.reg_write(arm.UC_ARM_REG_SP, SP)
    cpu.reg_write(arm.UC_ARM_REG_LR, stop)
    cpu.emu_start(address, stop, count=500_000)
    assert cpu.reg_read(arm.UC_ARM_REG_PC) == stop, hex(address)
    return cpu.reg_read(arm.UC_ARM_REG_R0)


def read_tone(cpu, code, out_of_line=False):
    cpu.mem_write(ENTRY + 12, struct.pack('<H2xI', code, ENTRY + 0x100 if out_of_line else 0))
    if out_of_line:
        cpu.mem_write(ENTRY + 0x100, struct.pack('<H', code))
    cpu.mem_write(SI + 0x77c, b'\xa5')
    call(cpu, RAW_READER, 0, ENTRY, SI)
    tone = cpu.mem_read(SI + 0x77c, 1)[0]
    call(cpu, PLAYBACK_READER, 0, METADATA + 0x18c, ENTRY)
    tag, = struct.unpack('<I', cpu.mem_read(METADATA + 0x220, 4))
    return tone, tag


def probe_recipe_copy(cpu):
    # Exercise the original copy through the final BIN's existing identity
    # trampoline. The source's allocation ends at the last stock SI byte.
    # Neither the copy nor the lease-clear adapter may read its tail.
    source, destination, owner = 0x55500d90, 0x55600000, RAM + 0x90000
    stock_bytes = 0x74270
    cpu.mem_map(0x55500000, 0x75000)
    cpu.mem_map(destination, 0x75000)
    cpu.mem_map(0x55345000, 0x1000)
    cpu.mem_write(0x55345328, struct.pack('<I', owner))
    cpu.mem_write(owner + 0x20, struct.pack('<I', stock_bytes + 16))
    cpu.mem_write(owner + 0x88, struct.pack('<I', destination))
    source_data = bytearray([0x5a]) * stock_bytes
    source_data[0x77c] = 11
    cpu.mem_write(source, bytes(source_data))
    cpu.mem_write(destination + stock_bytes, struct.pack('<4I', 0x31444946, 6, 0x1021, 0))
    call(cpu, 0x53510830, destination, source, stock_bytes, stop=0x53510834)
    assert cpu.mem_read(destination, stock_bytes) == source_data
    magic, generation, code, check = struct.unpack('<4I', cpu.mem_read(destination + stock_bytes, 16))
    assert (magic, generation, code, check) == (0, 7, 0, 0)
    return {'stock_copy_bytes': stock_bytes, 'identity_retained': False, 'destination_generation': generation}


def probe(model, candidate):
    path = candidate / ('fwdc239b.bin' if model == 'gr3' else 'fwdc243b.bin')
    manifest = json.loads((candidate / 'M10V-runtime-manifest.json').read_text())
    receipt = json.loads((candidate / 'M10V-build-receipt.json').read_text())
    assert manifest['camera_model'] == model
    assert receipt['public_version'] == ('2.10' if model == 'gr3' else '1.60')
    assert sha(path.read_bytes()) == receipt['candidate_sha256']
    assert manifest['experimental_capture']['spatial_neon']
    rom = decode(path)
    start = manifest['base'] - ROM
    assert sha(rom[start:start + manifest['code_bytes']]) == manifest['code_sha256']

    cpu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    cpu.ctl_set_cpu_model(arm.UC_CPU_ARM_CORTEX_A9)
    cpu.reg_write(arm.UC_ARM_REG_C1_C0_2, 0xf00000)
    cpu.reg_write(arm.UC_ARM_REG_FPEXC, 0x40000000)
    cpu.mem_map(ROM, (len(rom) + 4095) & ~4095)
    cpu.mem_write(ROM, rom)
    cpu.mem_map(RAM, 0x100000)
    guide_sites = {patch['address']: patch for patch in manifest.get('camera_guides', {}).get('patches', [])}
    observed = {}
    for name, (address, expected) in SITES.items():
        actual, = struct.unpack('<I', cpu.mem_read(address, 4))
        patch = guide_sites.get(address)
        if patch:
            assert name in ('canvas_draw', 'canvas_children', 'live_view_update')
            assert patch['expected'] == expected
            expected = patch['replacement']
        assert actual == expected, (model, name, hex(actual), hex(expected))
        observed[name] = {'address': hex(address), 'instruction': hex(actual)}

    assert call(cpu, RAW_DIAL_COUNT, SI) == 12
    assert call(cpu, RAW_LIST_COUNT, SI) == 14
    cpu.mem_write(SI + 5, b'\x01')
    assert call(cpu, RAW_LIST_COUNT, SI) == 15

    stock_tones = [read_tone(cpu, code) for code in range(0x100, 0x10c)]
    assert sorted(tone for tone, _ in stock_tones) == list(range(11, 23))
    assert sorted(tag for _, tag in stock_tones) == list(range(1, 13))
    cases = []
    for code, tone, tag, icon in (
        (0x100, 11, 1, None),
        (0x10c, 11, 0x1000c, 876),
        (0x1021, 11, 0x20f21, 703),
        (0x1043, 11, 0x20f43, 737),
        (0x2000, 11, 0x21f00, 754),
        (0xe0c5, 11, 0x2dfc5, 754),
        (0xffff, 11, 0, 0),
    ):
        assert read_tone(cpu, code) == (tone, tag), hex(code)
        assert read_tone(cpu, code, out_of_line=True) == (tone, tag), hex(code)
        if icon is not None:
            assert call(cpu, manifest['symbols']['m10v_menu_recorded_icon'], tag) == icon, hex(code)
        cases.append({'maker_note': hex(code), 'as_shot_tone': tone, 'playback_tag': hex(tag),
                      'recorded_film_icon': icon})
    return {'firmware_sha256': receipt['candidate_sha256'], 'hook_preimages': observed,
            'maker_note_cases': cases, 'stock_tones': stock_tones, 'recipe_copy': probe_recipe_copy(cpu),
            'camera_tested': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('gr3', type=Path)
    parser.add_argument('gr3x', type=Path)
    args = parser.parse_args()
    print(json.dumps({model: probe(model, getattr(args, model)) for model in ('gr3', 'gr3x')}, indent=2))


if __name__ == '__main__':
    main()
