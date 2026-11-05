"""Throwaway visual study: native 800T color data + unchanged main halo kernel.

This is a host software simulation on a downloaded JPEG, not camera output or
an ISP halo implementation. No film IDs, firmware, ADJ/Fn, or catalog are changed.
"""
import argparse
import ctypes as C
import hashlib
import json
import re
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]


def native_800t():
    from scripts.build_gr3_isp_native_look import decode_curve_deltas
    text = (ROOT / 'native/gr3/m10v_isp_native_look_profiles.h').read_text()
    fields = re.search(r'native_800t_frame = \{\{([^}]+)\},\{([^}]+)\},\{([^}]+)\},\{([^}]+)\}\}', text).groups()
    matrix, post, first, offsets = [list(map(int, f.split(','))) for f in fields]
    stream = bytes(map(int, re.search(r'native_curve_stream\[\d+\] = \{([^}]+)\}', text).group(1).split(',')))
    curves = []
    for value, offset in zip(first, offsets):
        curves.append(np.r_[value, value + np.cumsum(decode_curve_deltas(stream[offset:]))])
    return np.array(matrix).reshape(3, 3), np.array(post).reshape(3, 3), np.array(curves)


def yuv422(rgb):
    ycc = np.asarray(Image.fromarray(rgb).convert('YCbCr'))
    y = ycc[:, :, 0].copy()
    uv = np.empty(y.shape, np.uint8)
    for c in range(2):
        uv[:, c::2] = ((ycc[:, 0::2, c + 1].astype(np.uint16) + ycc[:, 1::2, c + 1] + 1) >> 1).astype(np.uint8)
    return y, uv


def rgb422(y, uv):
    ycc = np.stack([y, np.repeat(uv[:, 0::2], 2, axis=1), np.repeat(uv[:, 1::2], 2, axis=1)], axis=2)
    return Image.frombytes('YCbCr', (y.shape[1], y.shape[0]), ycc.tobytes()).convert('RGB')


def run(source, out):
    out.mkdir(parents=True, exist_ok=True)
    original = Image.open(source).convert('RGB')
    if original.width % 2:
        original = original.crop((0, 0, original.width - 1, original.height))
    rgb = np.asarray(original, dtype=np.float64) / 255
    matrix, post, curves = native_800t()
    # Main's 800T relative matrix is identity, so no assumed Standard inverse
    # is necessary for this display-domain reference. Reuse all 256 knots.
    assert np.array_equal(matrix, np.eye(3, dtype=int) * 8192)
    color = np.empty_like(rgb)
    for c in range(3):
        color[:, :, c] = np.interp(rgb[:, :, c] * 255, np.arange(256), curves[c] / 16383)
    color = np.uint8(np.clip(np.rint((color @ (post / 512).T) * 255), 0, 255))

    # Proposed ISP-expressible base: replicated Q13 luminance matrix, identical
    # monotonic Q14 curves, identity post. sRGB linearization is ONLY the host
    # reference model; actual stock gamma/matrix composition needs calibration.
    luma_q13 = [2449, 4809, 934]
    linear = np.where(rgb <= .04045, rgb / 12.92, ((rgb + .055) / 1.055) ** 2.4)
    luma = linear @ (np.array(luma_q13) / 8192)
    gray = np.where(luma <= .0031308, 12.92 * luma, 1.055 * luma ** (1 / 2.4) - .055)
    axis = np.arange(256) / 255
    x = np.clip((axis - .035) / .93, 0, 1)
    contrast = np.rint(np.clip(.55 * x + .45 * (x * x * (3 - 2 * x)), 0, 1) * 16383).astype(int)
    mono = np.interp(gray * 255, np.arange(256), contrast / 16383)
    mono = np.repeat(np.uint8(np.rint(mono * 255))[:, :, None], 3, axis=2)

    lib = C.CDLL(str(out / 'halo.dylib'))
    pointer = C.POINTER(C.c_uint8)
    lib.preview_halo.argtypes = [pointer, pointer, C.c_uint32, C.c_uint32, C.c_uint32, pointer, C.c_uint32]
    lib.preview_halo.restype = C.c_int
    w, h = original.size
    shift = 0
    while (w + (1 << shift) - 1) >> shift > 384 or (h + (1 << shift) - 1) >> shift > 256:
        shift += 1
    gw, gh = (w + (1 << shift) - 1) >> shift, (h + (1 << shift) - 1) >> shift
    ptr = lambda a: a.ctypes.data_as(pointer)
    outputs = [original]
    halo_stats = {}
    for name, base in [('800t', color), ('marlboro', mono)]:
        y, uv = yuv422(base)
        yy, cc = y.copy(), uv.copy()
        scratch = np.zeros(6 * gw * gh, dtype=np.uint8)
        assert lib.preview_halo(ptr(yy), ptr(cc), w, h, shift, ptr(scratch), scratch.size) == 0
        outputs.append(rgb422(yy, cc))
        halo_stats[name] = {'changed_luma_pixels': int(np.count_nonzero(yy != y)), 'changed_chroma_bytes': int(np.count_nonzero(cc != uv))}
    names = ['original', '800t', 'marlboro']
    labels = ['Original', '800T / simulation', 'Marlboro / simulation']
    for name, im in zip(names, outputs):
        im.save(out / (name + '.jpg'), quality=97, subsampling=0)
    font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf', 30)
    small = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf', 18)
    tw, th = 720, round(h * 720 / w)
    sheet = Image.new('RGB', (3 * tw, th + 106), '#101012')
    draw = ImageDraw.Draw(sheet)
    for i, (label, im) in enumerate(zip(labels, outputs)):
        draw.text((i * tw + 22, 16), label, font=font, fill='#eeeeef')
        draw.text((i * tw + 22, 57), 'Same scene | halo 7 / 7 / 5' if i else 'Atul Vinayak / Unsplash', font=small, fill='#ababaf')
        sheet.paste(im.resize((tw, th), Image.Resampling.LANCZOS), (i * tw, 106))
    sheet.save(out / 'comparison.jpg', quality=95, subsampling=0)
    # Matched detail around lamps, signs and umbrellas. Crop after processing
    # so the halo's source integration/grid geometry stays identical.
    box = (int(w * .18), int(h * .09), int(w * .69), int(h * .60))
    cw, ch = 720, round((box[3] - box[1]) * 720 / (box[2] - box[0]))
    detail = Image.new('RGB', (3 * cw, ch + 60), '#101012')
    draw = ImageDraw.Draw(detail)
    for i, (label, im) in enumerate(zip(labels, outputs)):
        draw.text((i * cw + 22, 12), label, font=font, fill='white')
        detail.paste(im.crop(box).resize((cw, ch), Image.Resampling.LANCZOS), (i * cw, 60))
    detail.save(out / 'highlight-detail.jpg', quality=96, subsampling=0)
    profile = {'matrix_q13': luma_q13 * 3, 'post_q9': [512, 0, 0, 0, 512, 0, 0, 0, 512], 'curves': [contrast.tolist()] * 3}
    (out / 'marlboro-isp-base-concept.json').write_text(json.dumps(profile, indent=2) + '\n')
    files = ['native/gr3/halation_energy.h', 'native/gr3/m10v_library.h', 'native/gr3/m10v_isp_native_look_profiles.h']
    evidence = {
        'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'source_page': 'https://unsplash.com/photos/people-walking-on-sidewalk-near-building-during-night-time-kSwMHdHrFqc',
        'photographer': 'Atul Vinayak', 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'dimensions': [w, h], 'grid_shift': shift, 'grain': 0, 'soft': 0,
        'halation': {'gain': 7, 'spread': 7, 'threshold': 5, 'profile': 4, 'kernel': 'unchanged m10v_800t_effects'},
        'same_algorithm_and_controls': True, 'same_pixel_halo_mask': False,
        'note': 'The same kernel derives its energy from each differently graded base; seed masks naturally differ. ADJ/Fn parity is intended, not implemented by this simulation.',
        'camera_output': False, 'camera_performance_tested': False, 'pure_isp_halo_implemented': False,
        'color_model': 'Display JPEG reference with main 800T decoded profile. Marlboro uses a proposed linear-light luma / monotonic contrast model, requiring actual ISP calibration.',
        'halo_stats': halo_stats, 'native_sha256': {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in files},
    }
    (out / 'simulation.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(evidence, indent=2))


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(ROOT))
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('out', type=Path)
    args = p.parse_args()
    run(args.source, args.out)
