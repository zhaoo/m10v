#!/usr/bin/env python3
"""Build traceable SHD50/KOLOR/Pegasus host references and previews.

This module runs on the build host only. Its spatial fields are later consumed
as immutable native-ISP inputs; none of the Python/Pillow code runs on camera.
"""
import argparse
import colorsys
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FIELD_HEIGHT = 64
FIELD_WIDTH = 128
VARIANTS = 4
SHD_LUMA = np.array([0.09, 0.69, 0.22], dtype=np.float64)


def _sample_tetrahedral(table, rgb):
    """RGB axes with blue fastest, matching the native firmware LUT sampler."""
    table = np.asarray(table, dtype=float)
    rgb = np.asarray(rgb, dtype=float)
    position = np.clip(rgb, 0, 1) * (table.shape[0] - 1)
    cell = np.minimum(position.astype(int), table.shape[0] - 2)
    fraction = position - cell
    order = np.argsort(-fraction, axis=-1, kind='stable')
    result = table[tuple(cell.T)].copy()
    previous = result.copy()
    corner = cell.copy()
    rows = np.arange(len(cell))
    for index in range(3):
        axis = order[:, index]
        corner[rows, axis] += 1
        current = table[tuple(corner.T)]
        result += fraction[rows, axis, None] * (current - previous)
        previous = current
    return result


def _shd_curve_float():
    x = np.arange(256, dtype=np.float64) / 255.0
    normalized = np.clip((x - 0.06) / 0.80, 0.0, 1.0)
    contrast = np.clip(0.5 + 1.35 * (normalized - 0.5), 0.0, 1.0)
    return (contrast * contrast * (3.0 - 2.0 * contrast)) * 255.0


SHD_CURVE_FLOAT = _shd_curve_float()
SHD_CURVE = np.rint(SHD_CURVE_FLOAT).astype(np.uint8)


def _rgb(rgb):
    value = np.asarray(rgb)
    if value.ndim < 1 or value.shape[-1] != 3:
        raise ValueError('RGB input must end in three channels')
    return np.clip(value, 0, 255).astype(np.uint8, copy=False)


def render_shd50(rgb):
    source = _rgb(rgb).astype(np.float64)
    luminance = np.tensordot(source, SHD_LUMA, axes=([-1], [0]))
    lo = np.floor(luminance).astype(np.int16)
    hi = np.minimum(lo + 1, 255)
    fraction = luminance - lo
    mono = np.rint(SHD_CURVE[lo] * (1.0 - fraction) + SHD_CURVE[hi] * fraction)
    mono = np.clip(mono, 0, 255).astype(np.uint8)
    return np.repeat(mono[..., None], 3, axis=-1)


def _delta_ycbcr(delta_rgb):
    r, g, b = np.moveaxis(delta_rgb, -1, 0)
    return np.stack((
        .299 * r + .587 * g + .114 * b,
        -.168736 * r - .331264 * g + .5 * b,
        .5 * r - .418688 * g - .081312 * b,
    ), axis=-1)


def _kolor_float(variant):
    y, x = np.mgrid[0:FIELD_HEIGHT, 0:FIELD_WIDTH]
    x = (x + .5) / FIELD_WIDTH
    y = (y + .5) / FIELD_HEIGHT
    colors = np.array([
        [255, 42, 42], [42, 92, 255], [255, 132, 24],
        [35, 218, 112], [255, 74, 181], [25, 220, 211],
    ], dtype=np.float64)
    rng = np.random.Generator(np.random.PCG64(0x4b4f4c4f + variant * 0x9e37))
    weights = []
    for index in range(len(colors)):
        cx = (rng.uniform(-.10, 1.10) + .17 * index) % 1.15
        cy = rng.uniform(-.08, 1.08)
        sx = rng.uniform(.18, .38)
        sy = rng.uniform(.16, .34)
        distance = ((x - cx) / sx) ** 2 + ((y - cy) / sy) ** 2
        weights.append(np.exp(-1.65 * distance))
    weights = np.stack(weights, axis=-1)
    total = weights.sum(axis=-1, keepdims=True)
    mixture = (weights[..., None] * colors).sum(axis=-2) / np.maximum(total, 1e-6)
    alpha = np.clip(total[..., 0] * .42, 0, .72)
    ripple = 0.94 + 0.06 * np.sin((x * (2.1 + .2 * variant) + y * 1.7) * 2 * np.pi)
    delta_rgb = mixture * (alpha * ripple)[..., None] * .72
    return _delta_ycbcr(delta_rgb)


def _pegasus_float(variant):
    y, x = np.mgrid[0:FIELD_HEIGHT, 0:FIELD_WIDTH]
    xn = (x + .5) / FIELD_WIDTH
    yn = (y + .5) / FIELD_HEIGHT
    centers = (.30, .43, .57, .69)
    widths = (.115, .145, .105, .165)
    strengths = (.92, .80, 1.0, .84)
    t = (yn - centers[variant]) / widths[variant]
    alpha = np.exp(-.5 * (t / .92) ** 2) * strengths[variant]
    alpha[np.abs(t) > 2.35] = 0
    hue = np.mod(.01 + np.clip((t + 2.15) / 4.3, 0, 1) * .79, 1.0)
    flat = hue.ravel()
    color = np.array([colorsys.hsv_to_rgb(float(h), .88, 1.0) for h in flat], dtype=np.float64)
    color = color.reshape(FIELD_HEIGHT, FIELD_WIDTH, 3) * 255.0
    horizontal = .97 + .03 * np.sin((xn * 1.5 + variant * .13) * 2 * np.pi)
    delta_rgb = color * (alpha * horizontal)[..., None] * .46
    return _delta_ycbcr(delta_rgb)


def _float_fields(kind, variant):
    if type(variant) is not int or not 0 <= variant < VARIANTS:
        raise ValueError('variant must be 0..3')
    if kind == 'kolor':
        return _kolor_float(variant)
    if kind == 'pegasus':
        return _pegasus_float(variant)
    raise ValueError('kind must be kolor or pegasus')


def signed_fields(kind, variant):
    quantized = np.rint(np.clip(_float_fields(kind, variant), -127, 127)).astype(np.int16)
    fields = {}
    for index, component in enumerate(('y', 'cb', 'cr')):
        value = quantized[..., index]
        fields[component + '_pos'] = np.maximum(value, 0).astype(np.uint8)
        fields[component + '_neg'] = np.maximum(-value, 0).astype(np.uint8)
    return fields


def _colorplus(rgb):
    source = _rgb(rgb)
    stock = next(s for s in json.loads((ROOT / 'web/gr3/c41-luts.json').read_text())['stocks'] if s['id'] == 323)
    table = np.asarray(stock['values'], dtype=np.float64).reshape(15, 15, 15, 3) / 255.0
    flat = source.reshape(-1, 3).astype(np.float64) / 255.0
    out = np.empty_like(flat)
    for start in range(0, len(flat), 131072):
        out[start:start + 131072] = _sample_tetrahedral(table, flat[start:start + 131072])
    return np.rint(np.clip(out.reshape(source.shape), 0, 1) * 255).astype(np.uint8)


def _upsample(component, width, height):
    image = Image.fromarray(component.astype(np.float32))
    return np.asarray(image.resize((width, height), Image.Resampling.BICUBIC), dtype=np.float64)


def _apply_fields(rgb, kind, variant):
    source = rgb.astype(np.float64)
    height, width = source.shape[:2]
    fields = signed_fields(kind, variant)
    delta = []
    for component in ('y', 'cb', 'cr'):
        positive = _upsample(fields[component + '_pos'], width, height)
        negative = _upsample(fields[component + '_neg'], width, height)
        delta.append(positive - negative)
    dy, dcb, dcr = delta
    r, g, b = np.moveaxis(source, -1, 0)
    y = .299 * r + .587 * g + .114 * b + dy
    cb = -.168736 * r - .331264 * g + .5 * b + dcb
    cr = .5 * r - .418688 * g - .081312 * b + dcr
    out = np.stack((
        y + 1.402 * cr,
        y - .344136 * cb - .714136 * cr,
        y + 1.772 * cb,
    ), axis=-1)
    return np.rint(np.clip(out, 0, 255)).astype(np.uint8)


def render_preview(rgb, film, variant=0):
    source = _rgb(rgb)
    if film == 'shd50':
        return render_shd50(source)
    if film == 'revolog-kolor':
        return _apply_fields(_colorplus(source), 'kolor', variant)
    if film == 'pegasus':
        return _apply_fields(_colorplus(source), 'pegasus', variant)
    raise ValueError('unknown film preview')


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_reference():
    field_error = 0.0
    field_metrics = {}
    for kind in ('kolor', 'pegasus'):
        field_metrics[kind] = []
        for variant in range(VARIANTS):
            target = np.clip(_float_fields(kind, variant), -127, 127)
            quantized = np.rint(target)
            field_error = max(field_error, float(np.abs(target - quantized).max()))
            field_metrics[kind].append({
                'variant': variant,
                'coverage_over_8dn': float((np.abs(quantized).max(axis=-1) > 8).mean()),
                'peak_dn': int(np.abs(quantized).max()),
            })
    source = ROOT / 'web/gr3/film-street-source.png'
    return {
        'schema': 'm10v-three-film-reference/v1',
        'generated_on': '2026-11-06',
        'films': [
            {'id': 328, 'name': 'SHD50', 'group': 'D76', 'model': 'independent high-contrast monochrome ISP target'},
            {'id': 329, 'name': 'Revolog KOLOR', 'group': 'C41', 'model': 'ColorPlus ISP base plus organic spatial field'},
            {'id': 330, 'name': 'Pegasus', 'group': 'C41', 'model': 'ColorPlus ISP base plus horizontal rainbow beam'},
        ],
        'sources': [
            {'role': 'user reference', 'description': 'attached SHD50 description and night sample, 2026-11-06'},
            {'role': 'SHD50 community samples', 'url': 'https://www.reddit.com/r/AnalogCommunity/comments/1rok0tc/lucky_shd50_is_a_weird_film/'},
            {'role': 'SHD50 community exposure discussion', 'url': 'https://www.talkphotography.co.uk/threads/lucky-shd50-35mm-film.774288/'},
            {'role': 'KOLOR official', 'url': 'https://www.revolog.net/fr/products/kolor'},
            {'role': 'Yodica founder interview', 'url': 'https://kosmofoto.com/2018/07/new-film-maker-yodica-offers-saturated-special-films/'},
            {'role': 'Pegasus specification', 'url': 'https://stingphotography.com/film/yodica/pegasus/'},
            {'role': 'Yodica ColorPlus base report', 'url': 'https://www.revelab.es/comprar/yodica-pegasus/'},
        ],
        'shd50': {
            'luma_weights': SHD_LUMA.tolist(),
            'luma_weights_q13': np.rint(SHD_LUMA * 8192).astype(int).tolist(),
            'curve_u8': SHD_CURVE.astype(int).tolist(),
            'fit_scope': 'reference-informed artistic fit; no manufacturer sensitometry located',
        },
        'rainbow': {
            'variants_per_film': VARIANTS,
            'field_shape': [FIELD_HEIGHT, FIELD_WIDTH],
            'components': ['y_pos', 'y_neg', 'cb_pos', 'cb_neg', 'cr_pos', 'cr_neg'],
            'metrics': field_metrics,
            'coordinate_system': 'physical sensor/film frame; no EXIF rotation',
        },
        'preview_source': {'path': str(source.relative_to(ROOT)), 'sha256': _sha(source), 'dimensions': [1536, 1024]},
        'metrics': {
            'shd50_curve_quantization_max_dn': float(np.abs(SHD_CURVE_FLOAT - SHD_CURVE).max()),
            'rainbow_field_quantization_max_dn': field_error,
        },
        'camera_tested': False,
        'preview_is_camera_output': False,
    }


def native_header(reference):
    luma = reference['shd50']['luma_weights_q13']
    curve = [value * 64 for value in reference['shd50']['curve_u8']]
    return (
        '/* Generated from three-film-reference.json; SHD50 native ISP base. */\n'
        'static const int16_t native_shd50_luma[3]={' + ','.join(map(str, luma)) + '};\n'
        'static const uint16_t native_shd50_curve[256]={' + ','.join(map(str, curve)) + '};\n'
        '#define M10V_RAINBOW_COLORPLUS_INDEX 3u\n'
    )


def _label(image, text):
    result = image.copy()
    draw = ImageDraw.Draw(result, 'RGBA')
    font = ImageFont.load_default()
    box = (24, 24, 24 + max(176, len(text) * 9), 62)
    draw.rounded_rectangle(box, radius=7, fill=(0, 0, 0, 178))
    draw.text((36, 36), text, fill=(255, 255, 255, 255), font=font)
    return result


def generate_previews(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    source = np.asarray(Image.open(ROOT / 'web/gr3/film-street-source.png').convert('RGB'))
    images = {
        'shd50.png': render_preview(source, 'shd50', 0),
        'revolog-kolor.png': render_preview(source, 'revolog-kolor', 0),
        'pegasus.png': render_preview(source, 'pegasus', 0),
    }
    for name, pixels in images.items():
        Image.fromarray(pixels).save(output / name, optimize=True)
    panels = [
        _label(Image.fromarray(source), 'Original'),
        _label(Image.fromarray(images['shd50.png']), 'SHD50'),
        _label(Image.fromarray(images['revolog-kolor.png']), 'Revolog KOLOR'),
        _label(Image.fromarray(images['pegasus.png']), 'Pegasus'),
    ]
    comparison = Image.new('RGB', (source.shape[1] * 2, source.shape[0] * 2))
    for index, panel in enumerate(panels):
        comparison.paste(panel, ((index % 2) * source.shape[1], (index // 2) * source.shape[0]))
    comparison.save(output / 'comparison.png', optimize=True)
    reference = build_reference()
    (output / 'three-film-reference.json').write_text(json.dumps(reference, indent=2, sort_keys=True) + '\n')
    paths = [output / name for name in ('shd50.png', 'revolog-kolor.png', 'pegasus.png', 'comparison.png')]
    return {'reference': reference, 'sha256': {path.name: _sha(path) for path in paths}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/previews/three-film-r1')
    parser.add_argument('--reference', type=Path, default=ROOT / 'native/gr3/three-film-reference.json')
    args = parser.parse_args()
    report = generate_previews(args.output)
    args.reference.write_text(json.dumps(report['reference'], indent=2, sort_keys=True) + '\n')
    (ROOT / 'native/gr3/m10v_three_films_native_profile.h').write_text(native_header(report['reference']))
    print(json.dumps({'output': str(args.output), 'reference': str(args.reference), 'sha256': report['sha256']}, sort_keys=True))


if __name__ == '__main__':
    main()
