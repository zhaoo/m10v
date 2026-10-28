"""Original encoded-bank metadata, never JPEG pixels or a pool allocation.

The original encoded-size query is executed, not replaced with a zero result.
SI/configuration and initialized extra-channel size metadata are explicit fixtures.
"""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path
from unicorn import UC_HOOK_CODE

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.analyze_gr3_border_iip import OriginalArm, validate

BASE, RECIPE, SI, BANK = 0x53000000, 0x55080000, 0x55100000, 0x60000000
SPANS = {'query': (0x53510cec, 0x53510fa0),
         'layout': (0x53510fa0, 0x53511270),
         'native_size_policy': (0x53664720, 0x53664c94),
         'native_si_dimensions': (0x536a2a30, 0x536a2efc),
         'setup6': (0x5350ea50, 0x5350eab8),
         'capture_enable': (0x5350480c, 0x53504890),
         'codec_channels': (0x53663f68, 0x53664430),
         'jpeg_request': (0x53663a8c, 0x53663ba4),
         'jpeg_driver': (0x53791044, 0x537913e4),
         'output_bound_register': (0x53792394, 0x537923a4)}


def setup(rom, extra, width, height):
    p = OriginalArm(rom)
    p.words(RECIPE, 0x53d0fc90)
    p.words(RECIPE + 0x23c, RECIPE + 0x5000)
    p.u.mem_write(RECIPE + 0x5004, struct.pack('<H', 4000))
    p.words(RECIPE + 0x5c, RECIPE + 0x6000)
    p.words(RECIPE + 0x44c8, SI)
    p.u.mem_write(RECIPE + 0x600d, bytes([extra]))
    stride = (width + 63) & ~63
    p.u.mem_write(RECIPE + 0x252, struct.pack('<8H', stride, 0, width, height, 0, 720, 480, 720))
    # Original size policy consumes frozen SI enum0/aspect0/crop1.0, not
    # the YUV descriptor dimensions. Do not forge a new native size enum.
    p.u.mem_write(SI + 0x7b8, struct.pack('<f', 1.0))
    # Explicit initialized private size-helper metadata: skip lazy singleton
    # construction, but execute its original dimension/capacity arithmetic.
    p.words(0x55363bb4, 1)
    p.u.mem_write(0x55363bc0, struct.pack('<f', 1.0))

    def thumbnail():
        p.u.mem_write(p.u.reg_read(p.A.UC_ARM_REG_R1), struct.pack('<H', 160))
        p.u.mem_write(p.u.reg_read(p.A.UC_ARM_REG_R2), struct.pack('<H', 120))

    p.boundaries = {0x536a2f10: thumbnail}
    p.original_query_visits = 0
    def observe_query(u, address, size, data):
        if address == 0x53664c0c:
            p.original_query_visits += 1
    p.u.hook_add(UC_HOOK_CODE, observe_query)
    return p


def request_bound(p, descriptor, output):
    context, packet = 0x55200000, 0x55210000
    observed = {}

    def record():
        at = p.u.reg_read(p.A.UC_ARM_REG_R2)
        raw = bytes(p.u.mem_read(at, 0x24))
        p.u.mem_write(packet, raw)
        observed.update(output_pointer=struct.unpack_from('<I', raw, 8)[0],
                        output_capacity=struct.unpack_from('<I', raw, 0x14)[0],
                        dimensions=list(struct.unpack_from('<2H', raw, 0xe)))

    p.boundaries = {0x536a9dd4: lambda: 0, 0x53791044: record,
                    0x536a9e8c: lambda: 0, 0x53790f88: lambda: 0}
    p.call(0x53663a8c, context, descriptor, output, 0x3b6, 0, 0)
    # Execute the actual original driver -> capacity register setter as well.
    # This RAM image has no busy response; hardware start/control are replaced.
    p.u.mem_map(0x298c0000, 0x10000)
    p.words(context + 0x24, 0x55230000)
    p.boundaries = {address: (lambda: 0) for address in
                    (0x5356284c, 0x5377c450, 0x5378fecc, 0x53790e8c,
                     0x53790b30, 0x53784de0, 0x53783820, 0x53791ec4,
                     0x53791c20, 0x53791f44)}
    p.call(0x53791044, context, 0, packet)
    observed['output_capacity_register_sectors'] = p.read_words(0x298c0458, 1)[0]
    observed['serialized_capacity_bytes'] = observed['output_capacity_register_sectors'] * 512
    observed['output_pointer_register'] = p.read_words(0x298c0440, 1)[0]
    return observed


def case(rom, extra, width=6000, height=4000):
    p = setup(rom, extra, width, height)
    # Execute full query including 53664c0c, then public id4 setter and its
    # original virtual encoded-layout method. Neither query nor layout is stubbed.
    p.call(0x53510cec, RECIPE)
    capacity = p.call(0x5350d47c, RECIPE, 4)
    p.call(0x5350d7e8, RECIPE, 4, BANK)
    controls = []
    for offset, name, active in ((0x130, 'main', True), (0x148, 'preview', True),
                                 (0x160, 'thumbnail', True), (0x178, 'extra', bool(extra))):
        pointer, target, bound, actual, flags, state = p.read_words(RECIPE + offset, 6)
        controls.append({'name': name, 'recipe_offset': offset, 'pointer': pointer,
                         'offset_in_bank': pointer - BANK, 'target_bytes': target,
                         'capacity': bound, 'active_fixture': active,
                         'end_offset': pointer - BANK + bound,
                         'fits_query': BANK <= pointer and pointer - BANK + bound <= capacity})
    # Original Setup6 semantic-copy and binding fragment, stopping at its
    # original tail rejoin. Photo-plane pointer tokens remain unmapped.
    source = bytearray(32)
    source[0], source[28] = 1, 2
    struct.pack_into('<3I', source, 4, 0x68000000, 0x6a000000, 0)
    struct.pack_into('<6H', source, 0x10, width, height, (width + 63) & ~63, height, 0, 0)
    p.u.mem_write(RECIPE + 0x70, bytes(source))
    p.u.mem_write(RECIPE + 0xb0, bytes(source))
    for register in (p.A.UC_ARM_REG_R0, p.A.UC_ARM_REG_R4):
        p.u.reg_write(register, RECIPE)
    p.u.reg_write(p.A.UC_ARM_REG_SP, 0x55ffe000)
    p.u.emu_start(0x5350ea50, 0x5350e6f0, count=10000)
    if p.u.reg_read(p.A.UC_ARM_REG_PC) != 0x5350e6f0 or p.u.reg_read(p.A.UC_ARM_REG_SP) != 0x55ffe000:
        raise AssertionError('original Setup6 fragment did not reach balanced rejoin')
    copied = bytes(p.u.mem_read(RECIPE + 0x110, 32))
    bindings = p.read_words(RECIPE + 0x9f4, 8)
    # Execute the actual capture caller's packet-enable construction, stopping
    # before its event-clear call. The byte at packet+23 comes from R5c+d.
    frame, factory = 0x55ffdffc, 0x55240000
    p.words(factory + 4, 0x55250000)
    for register, value in ((0, factory), (4, RECIPE + 0x9b8), (5, 0), (8, 2)):
        p.u.reg_write(getattr(p.A, f'UC_ARM_REG_R{register}'), value)
    p.u.reg_write(p.A.UC_ARM_REG_R11, frame)
    p.u.reg_write(p.A.UC_ARM_REG_SP, 0x55ffdf80)
    p.u.emu_start(0x5350480c, 0x53504890, count=10000)
    if p.u.reg_read(p.A.UC_ARM_REG_PC) != 0x53504890:
        raise AssertionError('capture enable fragment did not reach boundary')
    capture_extra = p.u.mem_read(frame - 0x39, 1)[0]
    rgb_pointer, rgb_capacity = p.read_words(RECIPE + 0x194, 1)[0], p.read_words(RECIPE + 0x1a4, 1)[0]
    # Request and register bound for main; fresh fixture for extra avoids
    # reusing the ordinary-RAM MMIO mapping as mutable engine state.
    main_request = request_bound(p, RECIPE + 0xb0, RECIPE + 0x130)
    q = setup(rom, extra, width, height)
    q.call(0x53510cec, RECIPE)
    q.call(0x5350d7e8, RECIPE, 4, BANK)
    q.u.mem_write(RECIPE + 0x110, copied)
    extra_request = request_bound(q, RECIPE + 0x110, RECIPE + 0x178) if extra else None
    return {'dimensions_fixture': [width, height], 'extra_enabled_fixture': bool(extra),
            'native_query_capacity': capacity, 'recipe_bank_pointer': p.read_words(RECIPE + 0x300, 1)[0],
            'recipe_capacity_field': p.read_words(RECIPE + 0x360, 1)[0], 'controls': controls,
            'setup6_bindings': bindings, 'r110_geometry': list(struct.unpack_from('<6H', copied, 0x10)),
            'capture_codec_extra_enable': capture_extra,
            'original_encoded_query_calls': p.original_query_visits,
            'auxiliary_rgb_thumbnail': {'pointer': rgb_pointer, 'capacity': rgb_capacity,
                'active_fixture': bool(extra), 'end_offset': rgb_pointer - BANK + rgb_capacity,
                'fits_query': BANK <= rgb_pointer and rgb_pointer - BANK + rgb_capacity <= capacity},
            'main_request': main_request, 'extra_request': extra_request,
            'assertions': p.assertions + q.assertions}


def probe(rom, model):
    if model not in ('gr3', 'gr3x'):
        raise ValueError('explicit official model required')
    digest = validate(rom, model)
    # Direct native policy for explicit dimensions, independent of SI enums.
    # This is the original target/capacity policy, NOT a worst-case JPEG bound.
    policies = []
    for width, height in ((6000, 4000), (6320, 4640), (6480, 4480)):
        p = OriginalArm(rom)
        policy = {'dimensions': [width, height]}
        for quality, name in ((0, 'main'), (2, 'extra')):
            target = p.call(0x53664954, 0x55080000, quality, width, height)
            bound = p.call(0x53664b88, 0x55080000, quality, width, height)
            policy[name] = {'target_bytes': target, 'capacity': bound}
        policy['assertions'] = p.assertions
        policies.append(policy)
    return {'schema': 'm10v-encoded-bank-research/v1', 'model': model, 'rtos_sha256': digest,
            'probe_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'spans': {name: {'start': start, 'end': end,
                            'sha256': hashlib.sha256(rom[start-BASE:end-BASE]).hexdigest()}
                      for name, (start, end) in SPANS.items()},
            'cases': [case(rom, 0), case(rom, 1), case(rom, 1, 6320, 4640)],
            'explicit_dimension_native_policy': policies,
            'hardware_executed': False, 'pixels_mapped': False, 'pool_allocation_executed': False,
            'activation_ready': False,
            'limits': ['Frozen SI remains stock enum0/aspect0/crop1.0; changing YUV geometry does not enlarge encoded query.',
                       'Initialized extra-size singleton and 160x120 thumbnail geometry are explicit fixture metadata.',
                       'Native target/capacity policy is not a worst-case encoded-length guarantee.',
                       'Capacity register serialization does not prove silicon overflow handling or safe completion.',
                       'Queried capacity does not prove actual cached pool allocation or ownership.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rtos', type=Path, required=True)
    parser.add_argument('--model', choices=('gr3', 'gr3x'), required=True)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    report = json.dumps(probe(args.rtos.read_bytes(), args.model), indent=2) + '\n'
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report)
    else:
        print(report, end='')


if __name__ == '__main__':
    main()
