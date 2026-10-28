"""Original JPEG pointer checks; MMIO is ordinary fixture RAM, never hardware.

The assertion service records and returns so invalid serialization is visible.
A register write following that substituted assertion is NOT native acceptance.
"""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.analyze_gr3_border_iip import OriginalArm, validate

BASE = 0x53000000
SETTERS = ((0x5379228c, 0x298c0430, 0x70000000),
           (0x537922e4, 0x298c0434, 0x74000000),
           (0x5379233c, 0x298c0440, 0x78000000))
OFFSETS = (0, 2, 4, 6, 8)
SPAN = (0x5379228c, 0x53792394)
SPAN_SHA256 = 'c26321cb8eb388a62cd9160782de60064db6beaa1fa064c06059bf41a2d28887'


def driver(rom, offset):
    p = OriginalArm(rom)
    p.u.mem_map(0x298c0000, 0x10000)
    context, packet = 0x55080000, 0x55081000
    p.words(context + 0x24, 0x55082000)
    raw = bytearray(0x24)
    struct.pack_into('<3I', raw, 0, 0x70000000 + offset,
                     0x74000000 + offset, 0x78000000)
    struct.pack_into('<4H', raw, 0xc, 6336, 6320, 4640, 1)
    struct.pack_into('<I', raw, 0x14, 32 * 1024 * 1024)
    raw[0x22] = 1
    p.u.mem_write(packet, bytes(raw))
    # Same declared control/start boundaries as the original size probe.
    p.boundaries = {address: (lambda: 0) for address in
                    (0x5356284c, 0x5377c450, 0x5378fecc, 0x53790e8c,
                     0x53790b30, 0x53784de0, 0x53783820, 0x53791ec4,
                     0x53791c20, 0x53791f44)}
    p.call(0x53791044, context, 0, packet)
    return {'offset': offset,
            'register_values': [p.read_words(reg, 1)[0] for _, reg, _ in SETTERS],
            'assertions': p.assertions,
            'native_alignment_checks_passed': not p.assertions}


def setter(rom, address, register, token, offset):
    p = OriginalArm(rom)
    p.u.mem_map(0x298c0000, 0x10000)
    p.call(address, 0x55082000, token + offset)
    return {'setter': address, 'register': register, 'offset': offset,
            'pointer': token + offset, 'register_value': p.read_words(register, 1)[0],
            'assertions': p.assertions,
            'native_alignment_checks_passed': not p.assertions}


def probe(rom, model):
    if model not in ('gr3', 'gr3x'):
        raise ValueError('explicit GR III/IIIx model identity required')
    digest = validate(rom, model)
    start, end = SPAN
    span_hash = hashlib.sha256(rom[start - BASE:end - BASE]).hexdigest()
    if span_hash != SPAN_SHA256:
        raise ValueError('original JPEG pointer setter span differs')
    return {
        'schema': 'm10v-jpeg-pointer-alignment/v1', 'model': model,
        'rtos_sha256': digest, 'setter_span': {'start': start, 'end': end,
                                            'sha256': span_hash},
        'probe_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'driver': [driver(rom, offset) for offset in OFFSETS],
        'setters': [setter(rom, address, register, token, offset)
                    for address, register, token in SETTERS for offset in OFFSETS],
        'hardware_executed': False, 'pixels_mapped': False,
        'firmware_emitted': False, 'activation_ready': False,
        'assertion_boundary': 'Records and returns; subsequent RAM writes do not admit an invalid pointer.',
        'conclusion': 'Original setters assert unless pointer is 8-byte aligned; the full pointer is serialized without masking low bits.',
        'limits': ['Ordinary RAM backs MMIO addresses; control/start services are substituted.',
                   'Aligned serialization does not prove silicon acceptance, DMA safety or performance.',
                   'Other producers and consumers require separate pointer-alignment contracts.'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rtos', type=Path, required=True)
    parser.add_argument('--model', choices=('gr3', 'gr3x'), required=True)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    report = probe(args.rtos.read_bytes(), args.model)
    result = json.dumps(report, indent=2) + '\n'
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(result)
    else:
        print(result, end='')


if __name__ == '__main__':
    main()
