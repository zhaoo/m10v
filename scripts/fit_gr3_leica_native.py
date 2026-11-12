"""Reconstruct Leica-look color candidates from paired public comparisons."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OFFICIAL = 'https://leica-camera.com/en-US/photography/leica-looks'
MEDIA = 'https://leica-camera.com/sites/default/files/styles/medium_content_media_desktop/public/'
PROFILE_REVIEW = 'https://www.robinschimko.com/blog/the-return-of-the-leica-looks'
CLASSIC_REVIEW = 'https://dc.watch.impress.co.jp/docs/review/newproduct/1511538.html'
REPORT = 'native/gr3/leica-reference.json'
HEADER = 'native/gr3/m10v_leica_native_profiles.h'
PREVIEW = 'web/gr3/leica-luts.json'
BASE = 'native/gr3/native-film-fit-targets.json'
TRAIN_SEED = 331334
HOLDOUT_SEED = 334331
PATCH_SEED = 342
ITERATIONS = 3500

SPECS = [
    (331, 'Chrome', 'CHR', '#58666c', '低饱和，保留细微反差的街拍色调。'),
    (332, 'Brass', 'BRS', '#ae7945', '中间调和高光偏暖金色，模拟日落光线。'),
    (333, 'Teal', 'TEL', '#367173', '青蓝偏冷的电影色调，适合城市与海边。'),
    (334, 'Classic', 'CLS', '#92634c', '较强反差，暖色略褪的复古电影色调。'),
]

# (Filename after the official media path, WebP cache token, expected SHA-256).
MEDIA_SOURCES = {
    'Chrome': [
        ('2024-09/Leica-Looks-Chrome-1-1920x1280.jpg', 'bWCPs-xG', '25f72b445432814e01da755b76e54e465307d49528482b55c40e10e46f351c90'),
        ('2024-09/Leica-Looks-Chrome-2-1920x1280.jpg', '9ZZK7MBB', 'c43d5b3d8a9d4ebb794b80441424d011b229d60f19ec419fc4041f4c37a6ba79'),
        ('2024-09/Leica-Looks-Chrome-3-1920x1280.jpg', 'hQ8FqeXT', '633f5b85d103a141f601e23ef9916d1d2d91b181330c0dc7955092a470e0a0df'),
        ('2024-09/Leica-Looks-Chrome-4-1920x1280.jpg', '01K1J2vD', '32275f1deddab557073f9087574e1978d3da9327e93c9b7f76ab503e645ba787'),
        ('2024-09/Leica-Looks-Chrome-5-1920x1280.jpg', 'alnvMQ_g', 'c71c8c2aeeba7c4eb5c027ca6521db5c288aa0e9ae3b71ee4b63773a57a2a70e'),
    ],
    'Brass': [
        ('2025-03/Leica-Looks_Brass_1_1920x1280.jpg', 'p6SUx9vO', '6ac85c523ee944474de15029a51d58b9bc55fdc8e754e9125d1b59e59a477889'),
        ('2025-03/Leica-Looks_Brass_2_1920x1280.jpg', 'W-ideygy', '638876cf8da7d621f1f67cf2c31a7c10e95b1131345b1fde5e46e940c4221f02'),
        ('2025-03/Leica-Looks_Brass_3_1920x1280.jpg', 'ibq9yve6', 'd16b8ab2853d13cb154650e9ac6d706e9015a00d2048340bf3b1cab1a04e4947'),
        ('2025-03/Leica-Looks_Brass_4_1920x1280.jpg', 'Sfyh1yyJ', '2ed76ddf62526a697448276075cd9299201f802fc98158d5a8215ce80feca5fe'),
        ('2025-03/Leica-Looks_Brass_5_1920x1280.jpg', 'Nv7NoJ_0', 'f056db06d4735c8f333ca403dde981839427a700e3744beac2101c5b35ddb59f'),
    ],
    'Teal': [
        ('2025-07/Leica-Looks_Teal_1920x12802.jpg', 'NgD92Q4v', 'e8b88d47d3e814ab99cd9b1c3ed02936a7596712cda5ce055cdfd33b6da279e0'),
        ('2025-07/Leica-Looks_Teal_1920x1280.jpg', 'zUTrZVqa', '0396b891c1928fce88aa7c108e35dd90abcd5a92c8ff4314da436515bafa517f'),
        ('2025-07/Leica-Looks_Teal_1920x12804.jpg', 'Jd6-G6lE', '08df63d52c742bba31c996b8d04803850abecf264ef6f33455d31c8b6e0d6156'),
        ('2025-07/Leica-Looks_Teal_1920x12803.jpg', 'i9bXtIuE', '2663e5d8747e083d04ee98f7184657b633eba4bf25c01a0bcccdf89b06dbb8d2'),
    ],
    'Classic': [
        ('2024-09/Leica-Looks-Classic-1-1920x1280_.jpg', '4jhEt8zB', 'e1ce78b0bb1614bdc3bd3e81111f09d9ffdb910edf2a6eefc1e17af6a17f2b95'),
        ('2024-09/Leica-Looks-Classic-2-1920x1280.jpg', 'KOpMR3Xb', '1d3c59e46368c1a93e1d0d794371f1f7f1f8e334032463fa6b5b7e7f1293ce35'),
        ('2024-09/Leica-Looks-Classic-3-1920x1280.jpg', '9t663QTQ', 'cafdc707595747987f6c6f63b2a30e8e0d3e050da6a54d232f63f6f41a5cd4e7'),
        ('2024-09/Leica-Looks-Classic-4-1920x1280.jpg', 'TgC4luZs', 'd96ba24c1e5e93e70439e06e123033563a9c4f28268d5e2501bc2d95b425b08c'),
        ('2024-09/Leica-Looks-Classic-5-1920x1280.jpg', 'lhQP8lv3', '39f25ecdfffff820aa68707ad4925f374746bda25cc891cb643ae19726bba768'),
    ],
}
# Scene indices (one-based) reserved in their entirety before fitting.
HOLDOUT_SCENE = {'Chrome': 2, 'Brass': 3, 'Teal': 4, 'Classic': 2}
CLASSIC_REVIEW_SOURCES = [
    ('q3standard', '37_s.jpg', 'e07334665a1318aed030e379b3b9aaeff7cf315397386a929606adc5a7e157e9'),
    ('q3classic', '39_s.jpg', '319cc59b863bd8aa2c54014559675736d37401ce924f00dbab80457bec1aa0cd'),
]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def native_header(report):
    from scripts.build_gr3_isp_native_look import decode_curve_deltas, encode_curve_deltas

    def array(values):
        return '{' + ','.join(map(str, values)) + '}'

    frames, hues, stream = [], [], bytearray()
    for q in report['native_profiles_full']:
        matrix = array(v for row in q['matrix_q13'] for v in row)
        post = array(v for row in q['post_q9'] for v in row)
        offsets = []
        for curve in q['curves']:
            deltas = [right-left for left, right in zip(curve, curve[1:])]
            if len(deltas) != 255 or any(not 0 <= value <= 255 for value in deltas):
                raise ValueError('Leica lossless curve delta overflow')
            encoded = encode_curve_deltas(deltas)
            if decode_curve_deltas(encoded) != deltas:
                raise ValueError('Leica lossless curve roundtrip differs')
            offsets.append(len(stream))
            stream.extend(encoded)
        frames.append('    {' + ','.join((matrix, post, array(c[0] for c in q['curves']), array(offsets))) + '}')
        hues.append('    ' + array(v for sector in q['hue_q10'] for row in sector for v in row))
    return (
        '/* Generated from leica-reference.json; losslessly packed native ISP color. */\n'
        'static const native_frame_packed native_leica_frame[4]={\n'
        + ',\n'.join(frames)
        + '\n};\nstatic const uint8_t native_leica_curve_stream[]=' + array(stream)
        + ';\nstatic const int16_t native_leica_hue[4][108]={\n'
        + ',\n'.join(hues) + '\n};\n'
    )


def verify(root=ROOT):
    from scripts.verify_gr3_anime_e6_reference import verify_profile

    root = Path(root)
    report = json.loads((root / REPORT).read_text())
    preview = json.loads((root / PREVIEW).read_text())
    if report['camera_validated'] or report['official_lut'] or not report['approximation']:
        raise ValueError('unsubstantiated Leica calibration claim')
    if (preview['size'], preview['bits'], preview['order']) != (15, 8, 'RGB, blue fastest'):
        raise ValueError('Leica preview geometry')
    ids = [spec[0] for spec in SPECS]
    if any([s[key] for s in rows] != ids for rows, key in [
        (preview['stocks'], 'id'), (report['stocks'], 'id'),
        (report['native_profiles_full'], 'film_id'),
    ]):
        raise ValueError('Leica identity mismatch')
    for path, expected in report['files'].items():
        if digest((root / path).read_bytes()) != expected:
            raise ValueError('Leica reference input differs: ' + path)
    hashes = set()
    for stock, spec, profile in zip(preview['stocks'], report['stocks'], report['native_profiles_full']):
        if stock['name'] != spec['name'] or stock['group'] != '影像':
            raise ValueError('Leica preview metadata differs')
        data = bytes(stock['native_values'])
        actual = digest(data)
        if len(data) != 15 ** 3 * 3 or actual != spec['native_preview_sha256'] or actual in hashes:
            raise ValueError('Leica preview data differs')
        hashes.add(actual)
        verify_profile(profile)
    if (root / HEADER).read_text() != native_header(report):
        raise ValueError('Leica native header readback differs')
    return report


def load_pinned(url, expected, cache, name):
    file = cache / name
    if not file.exists():
        with urlopen(url, timeout=30) as response:
            data = response.read(4 * 1024 * 1024 + 1)
        if digest(data) != expected:
            raise ValueError('Leica reference SHA-256 differs: ' + url)
        file.write_bytes(data)
    data = file.read_bytes()
    if digest(data) != expected:
        raise ValueError('Cached Leica reference SHA-256 differs: ' + str(file))
    return data


def pair_samples(data):
    import cv2
    import numpy as np
    from PIL import Image
    from scipy.optimize import minimize

    rgb = np.asarray(Image.open(io.BytesIO(data)).convert('RGB'))
    if rgb.shape != (480, 720, 3):
        raise ValueError('Official comparison dimensions differ')
    before = rgb[157:324, :250] / 255
    after = cv2.resize(rgb[30:450, 89:], (250, 167), interpolation=cv2.INTER_AREA) / 255
    y, x = np.mgrid[:167, :250]
    # White border, thumbnail overlay and both text areas are excluded.
    valid = ((x > 7) & (x < 243) & (y > 7) & (y < 159)
             & ~((x < 139) & (y > 113)) & ~((x < 69) & (y > 44) & (y < 121)))

    def luma(values):
        return values @ np.array([.299, .587, .114])

    def highpass(values):
        return values - cv2.GaussianBlur(values, (0, 0), 2.0)

    def warp(values, shift):
        return cv2.warpAffine(
            values, np.array([[1., 0., shift[0]], [0., 1., shift[1]]]),
            (250, 167), flags=cv2.INTER_LINEAR,
        )

    src_hi, dst_hi = highpass(luma(before)), highpass(luma(after))

    def cost(shift):
        return -np.corrcoef(src_hi[valid], warp(dst_hi, shift)[valid])[0, 1]

    shift = minimize(cost, (-1., -.25), bounds=[(-2.5, .5), (-1.5, 1.5)], method='Powell').x
    correlation = float(-cost(shift))
    if correlation < .32:
        raise ValueError('Insufficient registration confidence')
    after = warp(after, shift)
    # Average corresponding flat patches and sample a spatially spaced grid.
    patch = lambda a: cv2.GaussianBlur(a, (0, 0), 1.25)
    for rgb in [before, after]:
        y_channel = luma(rgb)
        variance = patch(y_channel ** 2) - patch(y_channel) ** 2
        valid &= variance < .055 ** 2
    valid &= (x % 3 == 0) & (y % 3 == 0)
    reference, look = patch(before)[valid], patch(after)[valid]
    if len(reference) < 600:
        raise ValueError('Insufficient valid comparison patches')
    return reference, look, dict(shift_xy=shift.tolist(), highpass_correlation=correlation, count=len(reference))


def independent_classic_samples(cache):
    import cv2
    import numpy as np
    from PIL import Image

    inputs, sources = [], []
    for name, filename, expected in CLASSIC_REVIEW_SOURCES:
        url = 'https://asset.watch.impress.co.jp/img/dcw/docs/1511/538/' + filename
        data = load_pinned(url, expected, cache, name)
        inputs.append(np.asarray(Image.open(io.BytesIO(data)).convert('RGB')) / 255)
        sources.append(dict(url=url, sha256=expected))
    if any(rgb.shape != (319, 480, 3) for rgb in inputs):
        raise ValueError('Classic review comparison dimensions differ')
    y, x = np.mgrid[:319, :480]
    mask = (x % 6 == 0) & (y % 6 == 0) & (x > 6) & (y > 6) & (x < 474) & (y < 313)
    patches, edges = [], []
    for rgb in inputs:
        lum = rgb @ np.array([.299, .587, .114])
        smooth = cv2.GaussianBlur(lum, (0, 0), 1.25)
        mask &= cv2.GaussianBlur(lum ** 2, (0, 0), 1.25) - smooth ** 2 < .05 ** 2
        patches.append(cv2.GaussianBlur(rgb, (0, 0), 1.25))
        edges.append(lum - cv2.GaussianBlur(lum, (0, 0), 2.0))
    correlation = float(np.corrcoef(edges[0].ravel(), edges[1].ravel())[0, 1])
    if correlation < .9:
        raise ValueError('Classic review photos do not align')
    return patches[0][mask], patches[1][mask], dict(
        source=CLASSIC_REVIEW, images=sources, highpass_correlation=correlation,
        scope='Independent Leica Q3 Standard and Classic JPEG comparison. Used only after fitting.',
    )


def features(rgb):
    import numpy as np
    from scripts.fit_gr3_native_film_targets import YCC

    y, cb, cr = (rgb @ YCC.T).T
    knots = np.array([0., .09, .2, .35, .5, .68, .83, .94, 1.])
    tone = np.column_stack([np.interp(y, knots, row) for row in np.eye(len(knots))])
    mid = 2 * y - 1
    return np.column_stack([
        tone, cb, cr, mid * cb, mid * cr, mid ** 2 * cb, mid ** 2 * cr,
        cb ** 2, cr ** 2, cb * cr,
    ])


def chroma_weights(rgb):
    import numpy as np

    # A sky or building façade must not drown out colors occupying fewer pixels.
    bins = np.minimum((rgb * 8).astype(int), 7)
    index = bins @ np.array([64, 8, 1])
    return 1 / np.sqrt(np.bincount(index, minlength=512)[index])


def learn_target(x, y, regularize_rgb):
    import numpy as np

    weight = chroma_weights(x)
    weight *= len(weight) / weight.sum()
    design, delta = features(x), y - x
    anchor = features(regularize_rgb)
    # Broad color-gamut prior keeps unsupported hues close to the baseline and
    # mild second differences avoid kinks in the reconstructed neutral curves.
    smooth = np.zeros((7, design.shape[1]))
    for i in range(len(smooth)):
        smooth[i, i:i + 3] = [1., -2., 1.]
    penalty = 0.012 * len(x) * (anchor.T @ anchor / len(anchor)) + 0.7 * smooth.T @ smooth
    penalty += 0.04 * np.eye(design.shape[1])
    weights = weight
    for _ in range(7):
        weighted = design.T * weights
        coef = np.linalg.solve(weighted @ design + penalty, weighted @ delta)
        residual = np.linalg.norm(design @ coef - delta, axis=1)
        weights = weight * np.minimum(1, .045 / np.maximum(residual, 1e-10))
    return coef


def generate(cache):
    import numpy as np
    from scripts.analyze_gr3_film_color_targets import metrics
    from scripts.build_gr3_harman_reference import sample_tetrahedral
    from scripts.fit_gr3_four_looks_native import seam_samples
    from scripts.fit_gr3_native_film_targets import fit, fit_gate, quantize, render_quantized
    from scripts.verify_gr3_anime_e6_reference import verify_profile

    cache.mkdir(parents=True, exist_ok=True)
    base = np.array(json.loads((ROOT / BASE).read_text())['base_gamma_q14']) / 16384
    grid = np.stack(np.meshgrid(*[np.linspace(0, 1, 15)] * 3, indexing='ij'), axis=-1).reshape(-1, 3)
    neutrals = np.repeat(np.linspace(0, 1, 257)[:, None], 3, axis=1)
    skin = np.array([[115, 82, 68], [194, 150, 130], [98, 62, 45], [220, 172, 143], [255, 210, 180]]) / 255
    train_rgb = np.random.default_rng(TRAIN_SEED).uniform(0, 1, (1536, 3))
    holdout = np.random.default_rng(HOLDOUT_SEED).uniform(0, 1, (16384, 3))
    report = dict(
        schema='m10v-leica-reference/v1', official_lut=False, approximation=True, camera_validated=False,
        official_source=OFFICIAL, third_party_profile_comparison=PROFILE_REVIEW,
        comparison_role='Third-party Lightroom and camera JPEG examples for visual cross-reference. No third-party LUT, Lightroom profile or photograph redistributed.',
        scope='Display-referred reconstruction from public comparison scenes. The source is a compressed Standard inset, not matched raw sensor data.',
        fit_domain='GR III Standard model inverse, native CCA, 12 hue sectors, gamma curves and native CSP',
        train_seed=TRAIN_SEED, patch_seed=PATCH_SEED, holdout_seed=HOLDOUT_SEED, iterations_limit=ITERATIONS,
        evaluation='The official held-out scene for each look is excluded from fitting and consulted when choosing patch weighting. The Q3 Classic review scene is an independent comparison.',
        native_profiles_full=[], stocks=[],
    )
    preview = dict(size=15, bits=8, order='RGB, blue fastest', stocks=[])
    for film, look, code, color, description in SPECS:
        observations, evidence = [], []
        for i, (path, token, expected) in enumerate(MEDIA_SOURCES[look], 1):
            name = look.lower() + ('' if look == 'Teal' and i == 1 else str(i))
            url = MEDIA + path + '.webp?itok=' + token
            src, dst, registration = pair_samples(load_pinned(url, expected, cache, name))
            held = i == HOLDOUT_SCENE[look]
            evidence.append(dict(url=url, sha256=expected, holdout=held, **registration))
            if held:
                scene_x, scene_y = src, dst
            else:
                observations.append((src, dst))
        source_x = np.concatenate([pair[0] for pair in observations])
        source_y = np.concatenate([pair[1] for pair in observations])
        coef = learn_target(source_x, source_y, grid)

        def target(rgb):
            return np.clip(rgb + features(rgb) @ coef, 0, 1)

        weights = chroma_weights(source_x)
        chosen = np.random.default_rng(PATCH_SEED).choice(len(source_x), 4096, p=weights / weights.sum())
        train = np.vstack([train_rgb, np.tile(neutrals, (5, 1)), source_x[chosen]])
        train_target = target(train)
        # Trim pointwise compression/alignment outliers around the smooth fit.
        patch_mix = 0.0 if look == 'Chrome' else 0.5
        patch_target = train_target[-len(chosen):]
        patch_target += np.clip(source_y[chosen] - patch_target, -.065, .065) * patch_mix
        params, optimization = fit(train, train_target, base, iterations=ITERATIONS, constrain_native=True)
        q = quantize(params)
        seams = seam_samples(q, base)
        native = np.rint(render_quantized(q, grid, base) * 255).astype('uint8')
        native_holdout = render_quantized(q, holdout, base)
        scores = {
            'isp_vs_reconstruction': metrics(target(holdout), native_holdout),
            'reconstruction_vs_official_scene': metrics(scene_y, target(scene_x)),
            'isp_vs_official_scene': metrics(scene_y, render_quantized(q, scene_x, base)),
            'isp_vs_reconstruction_neutral': metrics(target(neutrals), render_quantized(q, neutrals, base)),
            'isp_vs_reconstruction_skin': metrics(target(skin), render_quantized(q, skin, base)),
            'browser_vs_isp': metrics(native_holdout, sample_tetrahedral(native.reshape(15, 15, 15, 3) / 255, holdout)),
        }
        seam_output = render_quantized(q, seams, base).reshape(-1, 2, 3)
        q.update(
            film_id=film, holdout=scores['isp_vs_reconstruction'], validation=scores,
            seam_max_rgb_code_jump=float(np.max(np.abs(np.diff(seam_output, axis=1))) * 255),
            optimization=optimization, training_patch_mix=patch_mix,
            gate=fit_gate(scores['isp_vs_reconstruction'], False),
        )
        if look == 'Classic':
            review_x, review_y, evidence_review = independent_classic_samples(cache)
            q['independent_review'] = dict(
                **evidence_review, scores=metrics(review_y, render_quantized(q, review_x, base)),
            )
        verify_profile(q)
        stock = dict(
            id=film, name='Leica ' + look, key='leica-' + look.lower(), group='影像', title=look.upper(),
            code=code, color=color, description=description, approximation=True, camera_calibrated=False,
            official_lut=False, iso=0,
        )
        report['stocks'].append(dict(
            **stock, reference_scenes=evidence, target_coefficients=coef.tolist(),
            native_preview_sha256=digest(native.tobytes()),
        ))
        report['native_profiles_full'].append(q)
        preview['stocks'].append(dict(**stock, native_values=native.ravel().tolist()))
        print(f"{film} {look}: native vs reconstruction ΔE00 P95 {q['holdout']['de00_p95']:.2f}; "
              f"native vs held-out scene {scores['isp_vs_official_scene']['de00_p95']:.2f}", flush=True)
    (ROOT / PREVIEW).write_text(json.dumps(preview, ensure_ascii=False, separators=(',', ':')) + '\n')
    (ROOT / HEADER).write_text(native_header(report))
    paths = [
        str(Path(__file__).relative_to(ROOT)), BASE, PREVIEW, HEADER,
        'scripts/fit_gr3_native_film_targets.py', 'scripts/analyze_gr3_film_color_targets.py',
        'scripts/fit_gr3_four_looks_native.py', 'scripts/build_gr3_harman_reference.py',
        'scripts/verify_gr3_anime_e6_reference.py',
        'scripts/build_gr3_isp_native_look.py',
    ]
    report['files'] = {path: digest((ROOT / path).read_bytes()) for path in paths}
    (ROOT / REPORT).write_text(json.dumps(report, ensure_ascii=False, separators=(',', ':')) + '\n')
    return verify(ROOT)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='verify generated data without external inputs')
    parser.add_argument('--cache', type=Path, help='local directory for pinned public source images')
    args = parser.parse_args()
    if not args.check and args.cache is None:
        parser.error('--cache is required to generate')
    result = verify(ROOT) if args.check else generate(args.cache)
    print('Verified', len(result['stocks']), 'Leica native profiles')
