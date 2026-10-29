#!/usr/bin/env python3
"""Original ARM BackResize crop/pitch and early JPEG Setup6 metadata proof."""
import argparse
import hashlib
import json
import struct
from pathlib import Path
from analyze_gr3_border_iip import BASE, HASHES, OriginalArm, validate

SPANS = {'backresize_module': (0x534ff294, 0x534ff4ac),
         'source_crop': (0x534fec98, 0x534fed34),
         'main_binding': (0x534fed34, 0x534fee94),
         'native_wait': (0x534feb04, 0x534fec98),
         'cleanup': (0x534ff1b8, 0x534ff294),
         'jpeg_setup_dispatch': (0x5350e624, 0x5350e6f8),
         'jpeg_setup6': (0x5350ea50, 0x5350eabc)}
SPANS.update({'stripe_constant_writer': (0x53660c68, 0x53660cbc),
              'stripe_status_copy': (0x5365e5e0, 0x5365e600),
              'stripe_output_binding': (0x53501f00, 0x53501f24)})


def fragment(p, start, end, registers):
    """Execute an original basic-block fragment with explicit metadata inputs."""
    for n in range(13):
        p.u.reg_write(getattr(p.A, f'UC_ARM_REG_R{n}'), 0)
    for name, value in registers.items():
        p.u.reg_write(getattr(p.A, 'UC_ARM_REG_' + name.upper()), value)
    p.u.emu_start(start, end, count=10000)
    if p.u.reg_read(p.A.UC_ARM_REG_PC) != end:
        raise AssertionError('original fragment exceeded instruction budget')


def probe_stripe_offsets(rom):
    """Writer -> original status-array copy -> three original output bindings.

    This executes the fixed writer fragment, not the camera initialization
    selector. The adapter must validate actual live offsets before use.
    """
    p = OriginalArm(rom)
    source, destination, frame, config, module = (
        0x55100000, 0x55110000, 0x55120000, 0x55130000, 0x55200000)
    p.words(frame - 0x78, source + 0x104)
    fragment(p, 0x53660c68, 0x53660cbc,
             {'sl': source, 'fp': frame, 'r3': 0x102})
    writer = list(struct.unpack('<3H', p.u.mem_read(source + 0x102, 6)))
    fragment(p, 0x5365e5e0, 0x5365e600,
             {'r1': source + 0xd8, 'r2': destination + 0xd8,
              'r5': source + 0xec, 'lr': destination + 0xec,
              'ip': source + 0x100, 'r0': destination + 0x100, 'r3': 10})
    copied = list(struct.unpack('<3H', p.u.mem_read(destination + 0x102, 6)))
    p.words(config + 0x18, 0x60180000, 0x64180000)
    bindings = []
    for index in range(3):
        fragment(p, 0x53501f00, 0x53501f24,
                 {'r2': destination + 0x102 + index * 2, 'r6': config,
                  'r4': module + 0x9000, 'r0': frame})
        bindings.append(p.read_words(module + 0x9950, 2))
    return {'writer_offsets': writer, 'copied_offsets': copied,
            'output_plane_bindings': bindings, 'pitch_read_by_binding': False,
            'camera_initialization_selector_executed': False,
            'assertions': p.assertions, 'pixels_mapped': False}


def image(p, address):
    b = bytes(p.u.mem_read(address, 32))
    return {'format': b[0], 'planes': p.read_words(address + 4, 3),
            'geometry': list(struct.unpack_from('<6H', b, 16)), 'layout': b[28]}


def write_image(p, address, w, h, stride, y, c, origin=(0, 0)):
    p.u.mem_write(address, b'\x01')
    p.words(address + 4, y, c, 0)
    p.u.mem_write(address + 16, struct.pack('<6H', w, h, stride, h, *origin))
    p.u.mem_write(address + 28, b'\x02')


def probe_backresize(rom, crop=(6000, 4000), stride=6336, mode=0,
                     origin=(0, 0), wait_result=1, source_planes=None):
    validate(rom)
    if not (0 < crop[0] <= 6000 and 0 < crop[1] <= 4000):
        raise ValueError('crop exceeds original visible image')
    p = OriginalArm(rom)
    module, config, status, settings, flags, source, main, preview, preview_out, thumb = (
        0x55100000, 0x55200000, 0x55210000, 0x55220000, 0x55230000,
        0x55240000, 0x55241000, 0x55242000, 0x55243000, 0x55244000)
    p.words(config + 0x30, status, settings, flags, source, main, preview, preview_out, thumb,
            0x72000000, 0x73000000, 0)
    p.words(module + 0x8a0c, 0x55250000)
    p.u.mem_write(settings + 0xb38, struct.pack('<2H', *crop))
    p.u.mem_write(settings + 0x7b8, struct.pack('<f', 1.0))
    y, c = source_planes if source_planes is not None else (0x60180000, 0x64180000)
    write_image(p, source, 6000, 4000, stride, y, c, origin)
    write_image(p, main, 6000, 4000, stride, y - 144 * stride, c - 144 * stride)
    for desc, w, h, pitch, base in ((preview, 720, 480, 720, 0x68000000),
                                    (preview_out, 720, 480, 720, 0x69000000),
                                    (thumb, 160, 120, 160, 0x6a000000)):
        write_image(p, desc, w, h, pitch, base, base + 0x100000)
    before = {'source': image(p, source), 'main': image(p, main)}
    record = {'before': before, 'events': [], 'pixels_mapped': False,
              'hardware_executed': False, 'wait_result_is_test_double': True}
    def dims():
        p.u.mem_write(p.u.reg_read(p.A.UC_ARM_REG_R3), struct.pack('<H', crop[0]))
        sp = p.u.reg_read(p.A.UC_ARM_REG_SP)
        p.u.mem_write(p.read_words(sp, 1)[0], struct.pack('<H', crop[1]))
    def zero_margins():
        for n in (2, 3):
            p.u.mem_write(p.u.reg_read(getattr(p.A, f'UC_ARM_REG_R{n}')), b'\x00\x00')
    def thumb_dims():
        p.u.mem_write(p.u.reg_read(p.A.UC_ARM_REG_R1), struct.pack('<H', 160))
        p.u.mem_write(p.u.reg_read(p.A.UC_ARM_REG_R2), struct.pack('<H', 120))
    def submit():
        request = p.u.reg_read(p.A.UC_ARM_REG_R1)
        params = p.read_words(request + 8, 1)[0]
        pointers = p.read_words(params, 5)
        record['native_request'] = {'opcode': p.read_words(request + 12, 1)[0],
            'parameter_pointers': pointers,
            'descriptors': [image(p, address) for address in pointers],
            'flags': list(p.u.mem_read(params + 0x18, 5))}
        record['events'].append('submit_boundary')
    def wait():
        record['events'].append('wait_boundary')
        return wait_result
    def cache():
        record['events'].append('cache_boundary')
    p.boundaries = {0x536a2a30: dims, 0x536a2f50: zero_margins,
        0x536a3008: zero_margins, 0x536a2f10: thumb_dims,
        0x536abd28: submit, 0x536a9dd4: lambda: 0,
        0x536a9e8c: wait, 0x536bbc30: lambda: 0, 0x536bbcc0: cache}
    p.call(0x534ff294, module, config, mode)
    record['source_after'] = image(p, source)
    record['main_after'] = image(p, main)
    record['scratch_crop'] = image(p, module + 0x8a48)
    record['assertions'] = p.assertions
    return record


def probe_setup6(rom):
    """Original metadata dispatch; native allocation calls fail the fixture."""
    validate(rom)
    p = OriginalArm(rom)
    recipe = 0x55080000
    p.words(recipe, 0x53d0fc90)
    p.words(recipe + 0x5c, 0x55200000)
    p.words(recipe + 0x44c8, 0x55210000)
    write_image(p, recipe + 0x70, 6000, 4000, 6336, 0x60180000, 0x64180000)
    p.words(recipe + 0x9b8, 0x53d0fbe0)
    p.u.mem_write(recipe + 0x9e8, b'\xa5' * 0x2c)
    before = bytes(p.u.mem_read(recipe + 0x9b8, 0x60))
    from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
    writes, calls = [], []
    def reject(u, pc, size, data):
        if pc in (0x536af2a8, 0x536af31c, 0x536af358, 0x536abd28):
            raise AssertionError('Setup6 unexpectedly allocates or publishes work')
    def changed(u, access, address, size, value, data):
        if recipe <= address < recipe + 0x5000:
            writes.append({'pc': u.reg_read(p.A.UC_ARM_REG_PC),
                           'recipe_offset': address - recipe, 'bytes': size})
    p.u.hook_add(UC_HOOK_CODE, reject)
    p.u.hook_add(UC_HOOK_MEM_WRITE, changed)
    p.call(0x5350e624, recipe, 5)
    unchanged_after5 = bytes(p.u.mem_read(recipe + 0x9b8, 0x60)) == before
    writes.clear()
    p.call(0x5350e624, recipe, 6)
    setup_writes = list(writes)
    after = bytes(p.u.mem_read(recipe + 0x9b8, 0x60))
    copy = bytes(p.u.mem_read(recipe + 0x110, 0x20))
    p.call(0x5350e624, recipe, 6)
    idempotent = bytes(p.u.mem_read(recipe + 0x9b8, 0x60)) == after
    source_matches = copy == bytes(p.u.mem_read(recipe + 0x70, 0x20))
    write_image(p, recipe + 0x70, 6320, 4640, 6336, 0x60000000, 0x64000000)
    p.call(0x5350e624, recipe, 6)
    refreshed = image(p, recipe + 0x110)
    return {'setup5_leaves_jpeg_context_unchanged': unchanged_after5,
        'setup6_idempotent_same_source': idempotent,
        'setup6_copies_source_to_110': source_matches,
        'later_setup6_refreshes_110': refreshed,
        'context_fields30_to58': p.read_words(recipe + 0x9e8, 11),
        'setup6_recipe_writes': setup_writes, 'assertions': p.assertions,
        'native_allocations': 0, 'work_published': False,
        'scheduler_concurrency_executed': False, 'camera_tested': False}


def analyze(rom, model):
    digest = validate(rom, model)
    return {'schema': 'm10v-border-backresize-contract/v1', 'model': model,
        'rtos_sha256': digest, 'analyzer_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'spans': {n: {'start': a, 'end': b,
            'sha256': hashlib.sha256(rom[a-BASE:b-BASE]).hexdigest()} for n, (a, b) in SPANS.items()},
        'full': probe_backresize(rom),
        'xpan_geometry_fixture': probe_backresize(rom, (6000, 2248)),
        'six_by_seven_geometry_fixture': probe_backresize(rom, (4664, 4000)),
        'nonzero_low_origin': probe_backresize(rom, (6000, 2248), origin=(12, 8)),
        'failed_wait': probe_backresize(rom, wait_result=0),
        'setup6_metadata': probe_setup6(rom),
        'stripe_offsets': probe_stripe_offsets(rom), 'activation_ready': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rtos', type=Path, required=True)
    parser.add_argument('--model', choices=sorted(HASHES), required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = json.dumps(analyze(args.rtos.read_bytes(), args.model), indent=2) + '\n'
    if args.output:
        args.output.write_text(result)
    else:
        print(result, end='')
