#!/usr/bin/env python3
"""Offline original-ARM target-offset copy contract; no DMA or photo simulation."""
import argparse
import hashlib
import json
import struct
from pathlib import Path

from analyze_gr3_border_iip import BASE, HASHES, OriginalArm, validate

SPANS = {
    'descriptor_flags_and_constructor': (0x5376bb08, 0x5376bc48),
    'copy_graph': (0x53681260, 0x536814b8),
    'granulation_byte_descriptors': (0x5367af34, 0x5367afdc),
    'descriptor_bindings': (0x5376bdcc, 0x5376c044),
    'format_register_writer': (0x53870da4, 0x5387110c),
    'destination_cache': (0x5376bd18, 0x5376bdcc),
    'transfer_worker': (0x5369a948, 0x5369ad08),
    'transfer_plane_wait': (0x5369a40c, 0x5369a4b4),
    'transfer_packet': (0x537e2814, 0x537e2920),
    'transfer_start': (0x537e25fc, 0x537e27d4),
    'public_dispatch_wait': (0x534aad6c, 0x534aae9c),
    'public_copy_client': (0x534ab7a0, 0x534aba04),
    'public_other_client': (0x534aba38, 0x534abc18),
    'public_copy_worker': (0x53658cfc, 0x53658e68),
    'public_convert_worker': (0x53658e68, 0x5365900c),
}


def geometry(width=6000, height=4000, stride=6336, left=160, top=160,
             canvas_height=4320, base=0x74000000):
    values = (width, height, stride, left, top, canvas_height, base)
    if not all(type(v) is int for v in values):
        raise ValueError('integer byte-plane geometry required')
    if not (0 < width <= 65535 and 0 < height <= 65535 and
            width + left <= stride <= 65535 and min(left, top) >= 0 and
            top + height <= canvas_height <= 65535 and base > 0):
        raise ValueError('crop outside canvas or unsupported dimensions')
    offset = top * stride + left
    # Native cache routine covers stride*height bytes FROM the shifted pointer,
    # rather than just the visible last row. Prove that full span is in canvas.
    allocation = stride * canvas_height
    if offset + stride * height > allocation or base + allocation > 0x80000000:
        raise ValueError('native cache span exceeds canvas allocation')
    if (base + offset) & 3:
        raise ValueError('unaligned destination token')
    return dict(width=width, height=height, stride=stride, left=left, top=top,
                canvas_height=canvas_height, canvas_base=base, byte_offset=offset,
                destination=base + offset, allocation_bytes=allocation,
                cache_end=base + offset + stride * height)


def probe(rom, *, wait_result=1, **kwargs):
    """Execute copy0x53681260 until real scheduler boundary; OS returns are doubles.

    Original descriptors, constructors, graph registration/linking and cache
    span computation execute. Heap, handle allocator, submit, wait, graph release
    and cache backend are bounded ABI doubles; no camera completion is produced.
    """
    validate(rom)
    if wait_result not in (0, 1):
        raise ValueError('wait_result must be0 or1')
    g = geometry(**kwargs)
    p = OriginalArm(rom)
    # MMIO register addresses are ordinary zeroed RAM in this offline fixture.
    # Mode2 bypasses hardware handshake; it cannot execute DMA.
    p.u.mem_map(0x28880000, 0x10000)
    p.words(0x28880004, 2)
    ctx, owner, src, dst = 0x55080000, 0x55081000, 0x55082000, 0x55082100
    p.words(ctx + 8, owner)
    p.words(owner + 4, 0x55084000)
    p.words(owner + 12, 0x55083000)
    events, allocations, cache = [], [], []
    record = {'geometry': g, 'events': events, 'cache': cache,
              'pixels_mapped': False, 'hardware_pixels_executed': False,
              'camera_tested': False, 'ownership_proven': False,
              'failure_quiescence_proven': False}
    handles = []

    def reg(n):
        return p.u.reg_read(getattr(p.A, f'UC_ARM_REG_R{n}'))

    def allocate():
        size = reg(0)
        address = 0x55100000 + len(allocations) * 0x1000
        allocations.append({'address': address, 'bytes': size})
        return address

    def handle():
        value = len(handles)
        handles.append(value)
        return value

    def submit():
        graph, loader = reg(1), reg(3)
        store = p.read_words(p.u.reg_read(p.A.UC_ARM_REG_SP), 1)[0]
        record['graph'] = {'descriptor_count': p.read_words(graph + 0x34, 1)[0],
                           'descriptors': p.read_words(graph + 4, 2),
                           'node_count': reg(2), 'loader': loader, 'store': store,
                           'completion_cookie': p.read_words(graph + 0x38, 1)[0]}
        record['loader_image'] = bytes(p.u.mem_read(loader, 0xc0)).hex()
        record['store_image'] = bytes(p.u.mem_read(store, 0x1c0)).hex()
        events.append('submit_boundary')
        return 0

    def wait():
        record['wait'] = {'context': reg(0), 'mask': reg(1), 'test_double_result': wait_result}
        events.append('wait_boundary')
        return wait_result

    def cache_backend():
        cache.append({'address': reg(1), 'bytes': reg(2)})
        events.append('cache_backend')

    p.boundaries = {0x536af2a8: allocate, 0x53779dd4: handle,
                    0x5368a510: wait,
                    0x5376ebd0: lambda: 1,
                    0x53870cc8: lambda: 0, 0x53870d38: lambda: 0,
                    0x5387110c: lambda: record.setdefault('unit_uploads', []).append(
                        {'unit': reg(0), 'packet': bytes(p.u.mem_read(reg(1), 16)).hex()}),
                    0x5376e55c: lambda: events.append('scheduler_submit_boundary'),
                    0x5376c044: lambda: events.append('release_boundary'),
                    0x536bbc30: lambda: 0, 0x536bbcac: cache_backend,
                    0x536bbc3c: cache_backend,
                    0x536af2e4: lambda: events.append('free_boundary')}
    # Original submit's resource bitsets use two NEON u64 shifts which Unicorn
    # 2.1.4 SIGILLs on this host. Step only their ARM-defined bitset semantics;
    # record the substitution explicitly. No pixel arithmetic is emulated.
    from unicorn import UC_HOOK_CODE
    def observe(u, pc, size, data):
        if pc == 0x5376cd10:
            submit()  # observation only; continue executing original submit
        elif pc in (0x5376c434, 0x5376c45c):
            shift = u.reg_read(p.A.UC_ARM_REG_D17) & 255
            if shift & 128:
                shift -= 256
            value = u.reg_read(p.A.UC_ARM_REG_D8)
            result = ((value << shift) if shift >= 0 else (value >> -shift)) & 0xffffffffffffffff if abs(shift) < 64 else 0
            u.reg_write(p.A.UC_ARM_REG_D16, result)
            u.reg_write(p.A.UC_ARM_REG_PC, pc + 4)
            record.setdefault('resource_bitset_instruction_substitutions', []).append(pc)
    p.u.hook_add(UC_HOOK_CODE, observe)
    # Stock Granulation demonstrates format6 + byte stride. Match its source
    # flags0x100100 and destination0x100000; do not borrow SPF flags0x100002.
    for desc, flags, plane, stride in ((src, 0x100100, 0x70000000, g['width']),
                                      (dst, 0x100000, g['destination'], g['stride'])):
        p.call(0x5376bba0, desc, g['width'], g['height'], 6, flags)
        p.call(0x5376bc08, desc, plane, stride, 0)
    before = [bytes(p.u.mem_read(d, 0x50)) for d in (src, dst)]
    record['native_return_from_wait_double'] = p.call(0x53681260, ctx, 0, dst, src)
    record['format_register_fixture'] = [dict(
        handle=n, control=p.read_words(0x28880300 + n * 64, 1)[0],
        size=p.read_words(0x28880320 + n * 64, 1)[0],
        stride=p.read_words(0x28880310 + n * 64, 1)[0],
        plane=p.read_words(0x28880324 + n * 64, 1)[0]) for n in handles]
    record['allocations'] = allocations
    record['assertions'] = p.assertions
    record['descriptors'] = []
    for desc, initial in zip((src, dst), before):
        raw = bytes(p.u.mem_read(desc, 0x50))
        record['descriptors'].append({'address': desc, 'format': raw[9],
            'flag_field4': struct.unpack_from('<I', raw, 4)[0],
            'size': list(struct.unpack_from('<2H', raw, 0x28)),
            'stride_bytes': struct.unpack_from('<I', raw, 0x2c)[0],
            'plane': struct.unpack_from('<I', raw, 0x3c)[0],
            'handle': struct.unpack_from('<I', raw, 0x4c)[0],
            'unchanged_except_handle': initial[:0x4c] == raw[:0x4c]})
    return record


def probe_public_same_format(rom):
    """Observe equal-format public route; dispatcher is NOT executed."""
    p = OriginalArm(rom)
    context, src, dst, service = 0x55080000, 0x55081000, 0x55082000, 0x55083000
    for desc, plane, stride in ((src, 0x70000000, 6000),
                                (dst, 0x740f78a0, 6336)):
        p.u.mem_write(desc, b'\x01')
        p.words(desc + 4, plane, 0, 0)
        p.u.mem_write(desc + 0x10, struct.pack('<6H', 6000, 4000, stride, 4000, 0, 0))
    p.words(service + 4, 0x55084000)
    result = {'dispatcher_executed': False, 'ownership_proven': False,
              'pixels_mapped': False, 'cache_suppressed_argument': 1}
    def factory():
        result['factory'] = 0x5369a0e8
        return service
    def dispatch():
        A = p.A
        request = p.u.reg_read(A.UC_ARM_REG_R3)
        params = p.read_words(request + 8, 1)[0]
        result.update(mask=p.u.reg_read(A.UC_ARM_REG_R1),
                      opcode=p.read_words(request + 12, 1)[0],
                      parameter_descriptors=p.read_words(params, 2),
                      service_dispatch_argument=p.u.reg_read(A.UC_ARM_REG_R2))
        return 1
    p.boundaries = {0x5369a0e8: factory, 0x534aad6c: dispatch}
    p.call(0x534ab7a0, context, 0, src, dst, 1)
    result['assertions'] = p.assertions
    return result


def probe_transfer_worker(rom, wait_result=1, fmt=1, layout=2, left=160, top=160):
    """Execute original TransferRect same-format worker; stop before DMA start."""
    if fmt not in (1, 2) or layout not in (1, 2) or min(left, top) < 0:
        raise ValueError('unsupported public transfer format or offset')
    p = OriginalArm(rom)
    worker, service, packet, args, src, dst = (0x55080000 + i * 0x1000 for i in range(6))
    p.words(worker + 0x34, service)
    p.words(service + 0x54, packet)
    p.words(args, src, dst)
    for desc, planes, stride in ((src, (0x70000000, 0x72000000), 6000),
                                (dst, (0x74000000 + top * 6336 + left,
                                       0x78000000 + (top if fmt == 1 else top // 2) * 6336 + left), 6336)):
        p.u.mem_write(desc, bytes([fmt]))
        p.words(desc + 4, *planes, 0x7c000000 if desc == dst else 0x73000000)
        p.u.mem_write(desc + 0x10, struct.pack('<6H', 6000, 4000, stride, 4000, 0, 0))
        p.u.mem_write(desc + 0x1c, bytes([layout]))
    result = {'transfers': [], 'events': [], 'pixels_mapped': False,
              'dma_executed': False, 'failure_quiescence_proven': False}
    def reg(n):
        return p.u.reg_read(getattr(p.A, f'UC_ARM_REG_R{n}'))
    def transfer():
        raw = bytes(p.u.mem_read(reg(2), 0x2d))
        result['transfers'].append(dict(mode=raw[0],
            planes=list(struct.unpack_from('<2I', raw, 4)),
            geometry=list(struct.unpack_from('<8H', raw, 0xc))))
        result['events'].append('dma_start_boundary')
    def wait():
        result['events'].append('wait_boundary')
        result.setdefault('waits', []).append({'event': reg(0), 'mask': reg(1),
                                             'timeout': reg(3), 'test_double_result': wait_result})
        return wait_result
    p.boundaries = {0x5356284c: lambda: 0, 0x537e25fc: transfer,
                    0x536a9dd4: lambda: result['events'].append('clear_boundary'),
                    0x536a9e8c: wait,
                    0x537e29e4: lambda: result['events'].append('driver_handoff_boundary')}
    p.call(0x5369a948, worker, args)
    result['assertions'] = p.assertions
    return result


def probe_public_cache(rom, fmt=1):
    p = OriginalArm(rom)
    desc = 0x55081000
    p.u.mem_write(desc, bytes([fmt]))
    p.words(desc + 4, 0x740f78a0, 0x780f78a0, 0)
    p.u.mem_write(desc + 0x10, struct.pack('<6H', 6000, 4000, 6336, 4000, 0, 0))
    events = []
    def record(kind):
        events.append({'kind': kind,
            'plane': p.u.reg_read(p.A.UC_ARM_REG_R1),
            'bytes': p.u.reg_read(p.A.UC_ARM_REG_R2)})
    p.boundaries = {0x536bbc30: lambda: 0,
                    0x536bbc3c: lambda: record('pre'),
                    0x536bbcc0: lambda: record('post')}
    p.call(0x534ab1a4, 0x55080000, desc)
    p.call(0x534ab60c, 0x55080000, desc)
    return {'events': events, 'assertions': p.assertions, 'pixels_mapped': False}


def analyze(rom, model):
    digest = validate(rom, model)
    return {'schema': 'm10v-border-copy-contract/v1', 'model': model,
            'rtos_sha256': digest,
            'analyzer_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'spans': {name: {'start': a, 'end': b,
                'sha256': hashlib.sha256(rom[a-BASE:b-BASE]).hexdigest()}
                for name, (a, b) in SPANS.items()},
            'public_same_format_route': probe_public_same_format(rom),
            'public_transfer_worker': probe_transfer_worker(rom),
            'public_transfer_failed_wait': probe_transfer_worker(rom, 0),
            'public_transfer_unaligned': probe_transfer_worker(rom, left=68),
            'public_transfer_format2': probe_transfer_worker(rom, fmt=2),
            'public_cache_format1': probe_public_cache(rom, 1),
            'public_cache_format2': probe_public_cache(rom, 2),
            'target_offset_copy': probe(rom), 'failed_wait': probe(rom, wait_result=0),
            'activation_ready': False,
            'unproved': ['unit register upload and DMA byte identity',
                'JPEG-worker public service ownership and lifetime',
                'failure reset/quiescence', 'canvas allocation and cache-line ownership',
                'capture/JPEG integration and camera latency']}


def main():
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


if __name__ == '__main__':
    main()
