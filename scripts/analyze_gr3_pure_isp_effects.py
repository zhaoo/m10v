"""Read-only, hash-pinned spatial-effect evidence for GR III / IIIx.

Runs original ARM metadata paths with photo/noise planes UNMAPPED. Stops at
the stock CPU noise generator, before executing it. Does not install hooks,
emit firmware, execute DMA, or establish visual quality / device performance.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

from scripts.analyze_gr3_border_iip import OriginalArm, probe_rectangle, validate
from scripts.build_gr3_digital_hdf import ROWS
from scripts.border_resize_contract import probe as resize_probe

SPANS = {
    'grain': (0x5367ad3c, 0x5367b534),
    'cpu_noise': (0x5368a92c, 0x5368aa40),
    'loader': (0x536789f0, 0x53678b40),
    'blend_constructor': (0x53674f54, 0x5367509c),
    'store': (0x5368c3d8, 0x5368c5b4),
    'spatial_stage': (0x53680dc0, 0x53681260),
    'clarity': (0x5367c158, 0x5367c7e8),
    'clarity_rows': (0x538f1fd4, 0x538f209a),
    'spf_service_constructor': (0x53772888, 0x53772a38),
    'spf_driver_constructor': (0x53772a38, 0x53772b38),
}


def grain_probe(rom, width, height, execution=False, strength=1):
    """Query actual workspace or stop at the original CPU RNG call boundary."""
    if width < 1 or height < 1 or width > 65535 or height > 65535:
        raise ValueError('invalid image dimensions')
    if strength not in (1, 2, 3):
        raise ValueError('invalid native grain strength')
    p = OriginalArm(rom)
    A, u = p.A, p.u
    desc, needed, sp, stop = 0x55080000, 0x55081000, 0x55ffe000, 0x55fff000
    work = 0x70000000 if execution else 0
    size = ((width + 15) & ~15) * height
    u.mem_write(desc + 0x10, struct.pack('<HH', width, height))
    p.words(needed, size if execution else 0)
    result = {'width': width, 'height': height, 'strength': strength,
              'photo_pixels_mapped': False, 'noise_pixels_mapped': False}
    if not execution:
        result['return_value'] = p.call(0x5367ad3c, 0, desc, desc, strength, 0, needed)
        result['workspace_bytes'] = p.read_words(needed, 1)[0]
        if result['return_value'] != 1 or result['workspace_bytes'] != size:
            raise AssertionError('unexpected original grain workspace query')
    else:
        from unicorn import UC_HOOK_CODE

        def observe(uc, pc, _size, _data):
            if pc == 0x5368a92c:
                result['cpu_noise_request'] = {
                    'caller_return': uc.reg_read(A.UC_ARM_REG_LR),
                    'destination': uc.reg_read(A.UC_ARM_REG_R0),
                    'bytes': uc.reg_read(A.UC_ARM_REG_R1),
                }
                uc.emu_stop()

        u.hook_add(UC_HOOK_CODE, observe)
        p.words(sp, work, needed)
        for n, value in enumerate((0, desc, desc, strength)):
            u.reg_write(getattr(A, f'UC_ARM_REG_R{n}'), value)
        u.reg_write(A.UC_ARM_REG_SP, sp)
        u.reg_write(A.UC_ARM_REG_LR, stop)
        u.emu_start(0x5367ad3c, stop, count=10000)
        expected = {'caller_return': 0x5367ae18, 'destination': work, 'bytes': size}
        if result.get('cpu_noise_request') != expected:
            raise AssertionError('did not reach expected original CPU noise boundary')
        result['stopped_before_cpu_noise_execution'] = True
    if p.assertions:
        raise AssertionError(p.assertions)
    return result


def analyze(images):
    if set(images) != {'gr3', 'gr3x'}:
        raise ValueError('both exact official models required')
    reports = {}
    for model, rom in images.items():
        digest = validate(rom, model)
        rectangles = [probe_rectangle(rom, *rect) for rect in (
            (0, 0, 6000, 4000), (128, 64, 512, 512), (0, 0, 4000, 6000))]
        if any(r['assertions'] for r in rectangles):
            raise AssertionError('original Loader/Store assertion')
        reports[model] = {
            'rtos_sha256': digest,
            'span_sha256': {name: hashlib.sha256(rom[a-0x53000000:b-0x53000000]).hexdigest()
                            for name, (a, b) in SPANS.items()},
            'grain_workspace_queries': [grain_probe(rom, w, h) for w, h in (
                (2, 1), (6000, 4000), (4000, 6000), (6002, 4000))],
            'grain_execution_boundaries': [grain_probe(rom, 6000, 4000, True, v)
                                           for v in (1, 2, 3)],
            'loader_store_rectangles': rectangles,
            'texture_transfer': resize_probe(rom, 6000, 4000, fmt=0, source_format=0,
                source_size=(3072, 2048), source_stride=3072, source_plane=0x54600000,
                destination_stride=6016, texture_research=True),
            'rejected_native_terminal_phase': resize_probe(rom, 6000, 4000, fmt=0, source_format=0,
                source_size=(3072, 2048), source_stride=3072, source_plane=0x54600000,
                destination_stride=6016, native_phase=(1, 2), texture_research=True),
        }
    parity = {name: reports['gr3']['span_sha256'][name] == reports['gr3x']['span_sha256'][name]
              for name in SPANS}
    if not all(parity.values()):
        raise AssertionError('model-specific spatial instructions require separate research')
    return {
        'schema': 'm10v-pure-isp-effects-feasibility/v1',
        'models': reports, 'identical_original_spans': parity,
        'existing_hdf_detail_gain_rows_q10': ROWS,
        'stock_grain_satisfies_no_cpu_pixels': False,
        'firmware_emitted': False, 'hardware_pixels_executed': False,
        'camera_tested': False, 'activation_ready': False,
        'unproved': [
            'texture DMA addressability, tiling and per-shot phase without CPU expansion',
            'colored light-leak Blend/GPC arithmetic and chroma range',
            'SPF blur kernel, boundaries and full-frame response',
            'task admission, workspace ownership and failure quiescence for new graphs',
            'combined effects, capture latency and film-grain visual calibration',
        ],
        'blocked_shortcuts': [
            'tested public resize wrapper configures two components for fmt0; mono transfer is not established',
            'native terminal-phase flag records original line228 assertion; no submit/wait observed under intercepted boundaries',
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gr3-rtos', type=Path, required=True)
    parser.add_argument('--gr3x-rtos', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = analyze({'gr3': args.gr3_rtos.read_bytes(), 'gr3x': args.gr3x_rtos.read_bytes()})
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'models': sorted(report['models']),
                      'identical_spans': len(report['identical_original_spans']),
                      'activation_ready': report['activation_ready']}))


if __name__ == '__main__':
    main()
