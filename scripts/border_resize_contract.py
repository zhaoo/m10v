#!/usr/bin/env python3
"""Hash-pinned original public resize request proof, without pixel hardware."""
import argparse
import hashlib
import json
import struct
from pathlib import Path
from analyze_gr3_border_iip import BASE, HASHES, OriginalArm, validate

SPANS = {'public_resize': (0x534ab6b8, 0x534ab7a0),
         'resize_worker': (0x53673098, 0x5367357c),
         'resize_factory': (0x53672c48, 0x53672cbc),
         'scaler_configuration': (0x53765a5c, 0x53766910),
         'resolution_convert': (0x53770bf0, 0x53771bc0),
         'rotation_worker': (0x5368cb7c, 0x5368ccb4)}


def probe(rom, width=654, height=480, fmt=1, wait_result=1, source_roi=(0, 0), destination_roi=(0, 0)):
    validate(rom)
    if fmt not in (1, 2) or not (0 < width <= 720 and 0 < height <= 480) or width % 2 or height % 2:
        raise ValueError('unsupported even output size/format')
    if wait_result not in (0, 1):
        raise ValueError('invalid wait double')
    p = OriginalArm(rom)
    client, src, dst, factory, worker, service = (0x55080000 + i * 0x1000 for i in range(6))
    p.words(factory + 12, worker)
    p.words(worker + 0x34, service)
    for desc, format_code, w, h, stride, plane in (
        (src, 1, 6320, 4640, 6336, 0x70000000),
        (dst, fmt, width, height, 720 if width > 160 else 160, 0x74000000)):
        p.u.mem_write(desc, bytes([format_code]))
        p.words(desc + 4, plane, plane + 0x2000000, 0)
        roi = source_roi if desc == src else destination_roi
        p.u.mem_write(desc + 0x10, struct.pack('<6H', w, h, stride, h, *roi))
        p.u.mem_write(desc + 0x1c, b'\x02')
    r = {'scaler_requests': [], 'events': [], 'pixels_mapped': False,
         'hardware_pixels_executed': False, 'camera_tested': False,
         'ownership_proven': False, 'failure_quiescence_proven': False,
         'scaler_configuration_executed': True, 'unit_uploads_executed': False}
    def reg(n):
        return p.u.reg_read(getattr(p.A, f'UC_ARM_REG_R{n}'))
    def dispatch():
        request = reg(3)
        r['public_request'] = {'opcode': p.read_words(request + 12, 1)[0],
                               'mask': reg(1), 'queue': reg(2)}
        # Dispatch OS boundary is intercepted; execute the actual worker body
        # in a separate call after the public function returns.
        r['parameters'] = bytes(p.u.mem_read(p.read_words(request + 8, 1)[0], 0x16)).hex()
    def image(address):
        raw = bytes(p.u.mem_read(address, 0x3c))
        return {'size': list(struct.unpack_from('<2H', raw, 0x20)),
                'stride': struct.unpack_from('<I', raw, 0x1c)[0],
                'planes': list(struct.unpack_from('<3I', raw, 0x24))}
    def scale():
        config = reg(1)
        a, b = p.read_words(config + 0x30, 2)
        r['scaler_requests'].append({'source': image(a), 'destination': image(b),
            'roi_fields': list(struct.unpack('<4H', p.u.mem_read(config + 0x28, 8))),
            'config': bytes(p.u.mem_read(config, 0x38)).hex()})
    def wait():
        r['events'].append('wait_boundary')
        r.setdefault('waits', []).append({'event': reg(0), 'mask': reg(1),
            'timeout': reg(3), 'test_double_result': wait_result})
        return wait_result
    p.boundaries = {0x53672c48: lambda: factory, 0x534aad6c: dispatch,
        0x5376ebd0: lambda: 0, 0x5376eb14: lambda: 0,
        0x53765a24: lambda: r['events'].append('loader_boundary'),
        0x5377448c: lambda: r['events'].append('store_boundary'),
        0x5376eafc: lambda: 0, 0x536a9dd4: lambda: r['events'].append('clear_boundary'),
        0x5376e55c: lambda: r['events'].append('submit_boundary'),
        0x536a9e8c: wait,
        0x5376d86c: lambda: r['events'].append('release_boundary'),
        0x5376ed74: lambda: r['events'].append('release_boundary')}
    from unicorn import UC_HOOK_CODE
    pending = {}
    def observe(u, pc, size, data):
        if pc == 0x53765a5c:
            scale()
            pending['return'] = u.reg_read(p.A.UC_ARM_REG_LR)
            pending['output'] = reg(2)
        elif pc == pending.get('return'):
            r['scaler_requests'][-1]['computed_configuration'] = bytes(
                u.mem_read(pending['output'], 0x74)).hex()
            pending.clear()
    p.u.hook_add(UC_HOOK_CODE, observe)
    p.call(0x534ab6b8, client, src, dst, 1)
    params = 0x55087000
    p.u.mem_write(params, bytes.fromhex(r['parameters']))
    p.call(0x53673098, worker, params)
    r['assertions'] = p.assertions
    return r


def analyze(rom, model):
    digest = validate(rom, model)
    return {'schema': 'm10v-border-resize-contract/v1', 'model': model,
        'rtos_sha256': digest,
        'analyzer_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'spans': {n: {'start': a, 'end': b, 'sha256': hashlib.sha256(rom[a-BASE:b-BASE]).hexdigest()}
                  for n, (a, b) in SPANS.items()},
        'preview422': probe(rom), 'preview420': probe(rom, fmt=2),
        'thumbnail422': probe(rom, 160, 116),
        'thumbnail420': probe(rom, 160, 116, 2),
        'failed_wait': probe(rom, wait_result=0), 'activation_ready': False}


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
