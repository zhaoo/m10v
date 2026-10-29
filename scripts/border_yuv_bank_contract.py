#!/usr/bin/env python3
"""Hash-pinned original YUV bank sizing/layout study; never allocates image RAM."""
import argparse
import hashlib
import json
import struct
from pathlib import Path
from analyze_gr3_border_iip import BASE, HASHES, OriginalArm, validate

RECIPE = 0x55080000
BANK_BASE = 0x60000000
SPANS = {'develop_config_helper': (0x53501910, 0x53501ad4),
         'r2y_pack': (0x5366dc90, 0x5366e50c),
         'r2y_output_config': (0x537cb4e8, 0x537cbe78),
         'r2y_output_stride_setter': (0x537dd334, 0x537dd354),
         'r2y_output_crop_setters': (0x537dd520, 0x537dd5a0),
         'develop_b2r_helper': (0x5350177c, 0x53501910),
         'develop_plane_binding': (0x53501f04, 0x53501f24),
         'b2r_pack': (0x5363fb6c, 0x5363fecc),
         'channel_metadata_setters': (0x536a2148, 0x536a2424),
         'size_getter': (0x5350d47c, 0x5350d488),
         'bank_setter': (0x5350d7e8, 0x5350db3c),
         'size_query': (0x53510cec, 0x53510fa0),
         'yuv_layout': (0x5350db3c, 0x5350dfb4),
         'encoded_bank_layout': (0x53510fa0, 0x53511240)}


def setup(rom, width=6000, height=4000, stride=6016, raw_height=4000):
    p = OriginalArm(rom)
    p.words(RECIPE, 0x53d0fc90)
    p.words(RECIPE + 0x60, 0x70000000)  # RAW pointer token, never mapped
    p.words(RECIPE + 0x23c, RECIPE + 0x5000)
    p.u.mem_write(RECIPE + 0x5004, struct.pack('<H', raw_height))
    p.words(RECIPE + 0x5c, RECIPE + 0x6000)
    p.words(RECIPE + 0x44c8, RECIPE + 0x7000)
    p.u.mem_write(RECIPE + 0x252, struct.pack('<8H', stride, 0, width, height, 0, 720, 480, 720))
    def thumbnail():
        p.u.mem_write(p.u.reg_read(p.A.UC_ARM_REG_R1), struct.pack('<H', 160))
        p.u.mem_write(p.u.reg_read(p.A.UC_ARM_REG_R2), struct.pack('<H', 120))
    p.boundaries = {0x536a2f10: thumbnail,
        # Unrelated encoded-bank query; developed YUV size is computed by
        # original 53510e5c, independently of this explicit test boundary.
        0x53664c0c: lambda: 0}
    return p


def probe(rom, width=6000, height=4000, stride=6016):
    validate(rom)
    p = setup(rom, width, height, stride)
    before_raw = p.read_words(RECIPE + 0x60, 1)[0]
    p.call(0x53510cec, RECIPE)
    sizes = {str(i): p.call(0x5350d47c, RECIPE, i) for i in range(1, 10)}
    # Stock base setter with PUBLIC id5, not id4. Native virtual dispatch runs.
    p.call(0x5350d7e8, RECIPE, 5, BANK_BASE)
    descriptors = []
    for offset in (0x70, 0x90, 0xb0, 0xd0, 0xf0):
        b = bytes(p.u.mem_read(RECIPE + offset, 0x20))
        w, h, pitch, rows, x, y = struct.unpack_from('<6H', b, 0x10)
        planes = list(struct.unpack_from('<3I', b, 4))
        n = pitch * rows
        descriptors.append({'recipe_offset': offset, 'format': b[0],
            'size': [w, h], 'stride': pitch, 'rows': rows, 'origin': [x, y],
            'planes': planes, 'plane_bytes': n,
            'ends': [a + n for a in planes[:2] if a]})
    used_end = max(end for d in descriptors for end in d['ends'])
    return {'input': {'width': width, 'height': height, 'common_stride': stride,
                      'raw_height': 4000}, 'query_sizes': sizes,
        'public_yuv_bank_id': 5, 'bank_pointer_field': 0x304,
        'bank_size_field': 0x364, 'descriptors': descriptors,
        'maximum_descriptor_end': used_end,
        'covered_bytes': used_end - BANK_BASE,
        'native_capacity': sizes['5'],
        'tail_bytes': BANK_BASE + sizes['5'] - used_end,
        'raw_pointer_unchanged': p.read_words(RECIPE + 0x60, 1)[0] == before_raw,
        'assertions': p.assertions, 'pixels_mapped': False,
        'pool_allocation_executed': False, 'camera_tested': False}


def probe_develop_geometry(rom, override_stride=6016):
    """Execute Develop metadata -> actual R2Y packing -> original output register setters."""
    p = OriginalArm(rom)
    module, status, config, work = 0x55100000, 0x55200000, 0x55210000, 0x55220000
    output = module + 0x994c
    p.words(module + 0x9944, config)
    p.words(module + 0x9ba8, status)
    p.words(module + 0x9b54, work)
    # True public descriptor fields: output+10 width,+12 height,+14 stride.
    p.u.mem_write(output, b'\x01')
    p.words(output + 4, 0x600f78a0, 0x620f78a0, 0)
    p.u.mem_write(output + 0x10, struct.pack('<6H', 6000, 4000, 6016, 4000, 0, 0))
    p.u.mem_write(status + 0xaa, struct.pack('<2H', 6016, 4000))
    p.u.mem_write(status + 0xd0, b'\x01')
    p.u.mem_write(status + 0xd4, struct.pack('<H', 0))
    p.u.mem_write(status + 0xd8, struct.pack('<H', 4000))
    p.boundaries = {0x536a21f0: lambda: 0, 0x536a22d4: lambda: 0,
                    0x536a23c0: lambda: 0}
    p.call(0x53501910, module, 0)
    before = list(struct.unpack('<6H', p.u.mem_read(output + 0x10, 12)))
    # Candidate local OUTPUT descriptor override only; status/raw geometry unchanged.
    p.u.mem_write(output + 0x14, struct.pack('<H', override_stride))
    # Actual R2Y packer consumes params=module+9938. Its output image is inline
    # params+14, with stride atparams+28. Auxiliary configuration is zeroed RAM.
    p.words(module + 0x99dc, config, config)
    r2y_native = 0x55300000
    p.call(0x5366dc90, 0x55260000, r2y_native, module + 0x9938)
    r2y = {'stride': p.read_words(r2y_native + 0x4c, 1)[0],
           'planes': p.read_words(r2y_native + 0x90, 3),
           'format': p.u.mem_read(r2y_native + 0x3c, 1)[0]}
    service, devices, unit, registers = 0x55260000, 0x55270000, 0x55280000, 0x55290000
    p.words(service + 0x14, devices)
    p.words(devices + 0x2c, unit)
    p.words(unit + 4, registers)  # Original register setters write ordinary RAM.
    p.call(0x537cb4e8, service, 8, r2y_native)
    return {'original_r2y_packer_executed': True,
        'original_r2y_output_config_executed': True,
        'r2y_native_output': r2y, 'override_stride': override_stride,
        'native_initial_geometry': before,
        'output_geometry': list(struct.unpack('<6H', p.u.mem_read(output + 0x10, 12))),
        'output_stride_register_low17': p.read_words(registers + 0x144, 1)[0] & 0x1ffff,
        'status_stride_unchanged': struct.unpack('<H', p.u.mem_read(status + 0xaa, 2))[0] == 6016,
        'assertions': p.assertions, 'pixels_mapped': False, 'hardware_registers_written': False}


def probe_streaming_intermediates(rom, bank_base=0x60000000, output_base=None):
    """Normal path helpers + both original packers, with RGB plane tokens zero."""
    if output_base is None:
        output_base = bank_base
    p = OriginalArm(rom)
    module, status, cfg, rawinfo, coefficients = 0x55100000, 0x55200000, 0x55210000, 0x55220000, 0x55230000
    b2r_work, r2y_work, input_raw, colorcfg = 0x55240000, 0x55250000, 0x55260000, 0x55270000
    p.words(module + 0x9ba8, status)
    p.words(module + 0x9b50, b2r_work)
    p.words(module + 0x9b54, r2y_work)
    p.words(module + 0x9944, colorcfg)
    p.words(module + 0x99dc, colorcfg, colorcfg)
    p.words(module + 0x9910, input_raw)
    p.words(status + 0xa0, rawinfo)
    p.u.mem_write(rawinfo + 2, struct.pack('<2H', 4000, 6000))
    p.u.mem_write(status + 0xaa, struct.pack('<2H', 6016, 4000))
    p.u.mem_write(status + 0xd0, b'\x01')
    p.u.mem_write(status + 0xd8, struct.pack('<H', 4000))
    p.words(cfg + 0x10, bank_base, 72192000, output_base + 0x100000, output_base + 0x1900000)
    p.words(cfg + 0x40, coefficients)
    p.u.mem_write(input_raw, b'\x06')
    p.u.mem_write(module + 0x990c, struct.pack('<2H', 1, 1))
    rgb = []
    for n in range(4):
        address = 0x55400000 + n * 0x1000
        p.u.mem_write(address, b'\x08')
        p.words(module + 0x9914 + 4 * n, address)
        rgb.append(address)
    output = module + 0x994c
    p.u.mem_write(output, b'\x01')
    p.words(output + 4, 0, 0, 0)
    p.u.mem_write(output + 0x10, struct.pack('<6H', 6000, 4000, 6016, 4000, 0, 0))
    p.boundaries = {}  # Execute the real channel metadata setters as well.
    from unicorn import UC_HOOK_CODE
    def reject_allocation(u, pc, size, data):
        if pc in (0x536af2a8, 0x536af31c, 0x536af358):
            raise AssertionError('metadata fixture unexpectedly requested native heap')
    p.u.hook_add(UC_HOOK_CODE, reject_allocation)
    p.call(0x5350177c, module, cfg)
    p.call(0x53501910, module, cfg)
    # Original worker fragment binds cfg+18/+1c into the final inline planes.
    for n, value in ((4, module + 0x9000), (6, cfg), (2, 0), (0, input_raw), (12, 0)):
        p.u.reg_write(getattr(p.A, f'UC_ARM_REG_R{n}'), value)
    p.u.reg_write(p.A.UC_ARM_REG_LR, 6000)
    p.u.emu_start(0x53501f04, 0x53501f24, count=20)
    if p.u.reg_read(p.A.UC_ARM_REG_PC) != 0x53501f24:
        raise AssertionError('original plane binding did not reach boundary')
    b2r_native, r2y_native = 0x55500000, 0x55600000
    # The coefficient metadata pointer must be live, as it is in the original
    # configured request. No image addresses are supplied through it.
    p.call(0x5363fb6c, 0x55700000, b2r_native, module + 0x9904)
    p.call(0x5366dc90, 0x55700000, r2y_native, module + 0x9938)
    return {'bank_base_fixture': bank_base, 'output_base_fixture': output_base,
        'b2r_request_flags': list(p.u.mem_read(module + 0x9904, 8)),
        'b2r_native_flags': list(p.u.mem_read(b2r_native, 5)),
        'b2r_memory_output_flag': p.u.mem_read(b2r_native + 0x25, 1)[0],
        'b2r_native_rgb_planes': p.read_words(b2r_native + 0x38, 3),
        'rgb_descriptors': [{'format': p.u.mem_read(a, 1)[0],
                             'planes': p.read_words(a + 4, 3)} for a in rgb],
        'r2y_request_flags': list(p.u.mem_read(module + 0x9938, 8)),
        'r2y_input_descriptor_pointer': p.read_words(module + 0x99d8, 1)[0],
        'native_heap_allocations': 0,
        'r2y_native_input_selector': p.u.mem_read(r2y_native + 8, 1)[0],
        'r2y_native_rgb_input_planes': p.read_words(r2y_native + 0x10, 3),
        'r2y_yuv_output_planes': p.read_words(r2y_native + 0x90, 3),
        'assertions': p.assertions, 'pixels_mapped': False,
        'scope': 'normal helper/packer path; no scheduler or hardware; flags must be gated'}


def probe_native_halo(rom, stride=6336, index=0):
    """Real packer and register configuration with native three-stripe crop.

    The fixture supplies the native geometry builder's constants. It does not
    emulate pixels or claim physical register/DMA behavior.
    """
    if stride not in (6016,6144,6336) or index not in range(3):
        raise ValueError('unsupported explicit halo fixture')
    p=OriginalArm(rom)
    module,config,work,native,status=0x55100000,0x55210000,0x55220000,0x55300000,0x55200000
    column,roi_x,width=((0,68,1972),(1960,12,1996),(3944,12,2068))[index]
    p.words(module+0x9944,config)
    p.words(module+0x99dc,config,config)
    p.words(module+0x9b54,work)
    p.words(module+0x9ba8,status)
    p.u.mem_write(status+0xaa,struct.pack('<2H',6144,4000))
    p.u.mem_write(status+0xd0,b'\x01')
    p.u.mem_write(status+0xd4,struct.pack('<H',40))
    p.u.mem_write(status+0xd8,struct.pack('<H',4012))
    p.call(0x53501910,module,0)
    output=module+0x994c
    p.u.mem_write(output,b'\x01')
    p.words(output+4,0x60180000+column,0x64180000+column,0)
    p.u.mem_write(output+0x10,struct.pack('<6H',width,4012,stride,4000,roi_x,40))
    p.u.mem_write(output+0x1c,b'\x02')
    p.call(0x5366dc90,0x55260000,native,module+0x9938)
    service,devices,unit,registers=0x55260000,0x55270000,0x55280000,0x55290000
    p.words(service+0x14,devices);p.words(devices+0x2c,unit);p.words(unit+4,registers)
    p.call(0x537cb4e8,service,8,native)
    return {'stride':stride,'native_planes':p.read_words(native+0x90,3),
        'native_crop':p.read_words(native+0x60,4),
        'crop_registers':p.read_words(registers+0x178,2),
        'registers':p.read_words(registers,0x200//4),
        'assertions':p.assertions,'pixels_mapped':False,'hardware_executed':False}


def analyze(rom, model):
    digest = validate(rom, model)
    stock = probe(rom)
    # A GEOMETRY fixture only. This changes common stride for native execution;
    # never apply this mutation to a real capture recipe/RAW status.
    expanded = probe(rom, 6320, 4640, 6336)
    canvas_bytes = 6336 * 4640 * 2
    tail_canvas_start = (stock['maximum_descriptor_end'] + 63) & ~63
    required_capacity = tail_canvas_start - BANK_BASE + canvas_bytes
    return {'schema': 'm10v-border-yuv-bank-contract/v1', 'model': model,
        'rtos_sha256': digest,
        'analyzer_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'spans': {n: {'start': a, 'end': b,
            'sha256': hashlib.sha256(rom[a-BASE:b-BASE]).hexdigest()}
            for n, (a, b) in SPANS.items()},
        'develop_geometry_stock': probe_develop_geometry(rom),
        'develop_geometry_local_override': probe_develop_geometry(rom, 6336),
        'native_halo_registers': [{'old':probe_native_halo(rom,6144,i),
                                   'new':probe_native_halo(rom,6336,i)} for i in range(3)],
        'streaming_intermediates': [probe_streaming_intermediates(rom),
                                  probe_streaming_intermediates(rom, 0x64000000, 0x60000000),
                                  probe_streaming_intermediates(rom, 0x60000000, 0x64000000)],
        'stock': stock, 'expanded_geometry_only': expanded,
        'disjoint_tail_canvas': {'canvas_bytes': canvas_bytes,
            'canvas_start': tail_canvas_start, 'required_capacity': required_capacity,
            'additional_capacity': max(0, required_capacity - stock['native_capacity']),
            'fits_stock_capacity': required_capacity <= stock['native_capacity']},
        'activation_ready': False,
        'unproved': ['pool capacity and bank lifetime', 'all Develop branches and hardware output pitch',
                     'independent YUV geometry from common RAW status',
                     'live source/destination exclusivity', 'DMA pixels/cache']}


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
