"""Approved monochrome artistic target, fitted offline to the existing ISP.

The spatial halo is deliberately absent: camera code shares 800T's kernel.
No physical film, hardware pixel or performance calibration is claimed.
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SPEC = dict(id=327, key='marlboro', name='Marlboro', ascii_name='Marlboro',
            title='MARLBORO', code='B&W RED', color='#b51c2b', group='创意', iso=0,
            approximation=True, official_lut=False, film_calibrated=False,
            camera_calibrated=False,
            reference='User-approved high-contrast monochrome artistic target; independent 800T spatial halo')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def render(rgb):
    import numpy as np
    rgb = np.clip(np.asarray(rgb, float), 0, 1)
    linear = np.where(rgb <= .04045, rgb / 12.92, ((rgb + .055) / 1.055) ** 2.4)
    luma = linear @ (np.array([2449, 4809, 934]) / 8192)
    gray = np.where(luma <= .0031308, 12.92 * luma, 1.055 * luma ** (1 / 2.4) - .055)
    axis = np.arange(256) / 255
    x = np.clip((axis - .035) / .93, 0, 1)
    curve = np.rint((.55 * x + .45 * x * x * (3 - 2 * x)) * 16383) / 16383
    result = np.interp(gray * 255, np.arange(256), curve)
    return np.repeat(result[..., None], 3, axis=-1)


def native_header(ref):
    from scripts.build_gr3_isp_native_look import encode_curve_deltas, decode_curve_deltas
    q = ref['native_profiles_full'][0]
    arr = lambda x: '{' + ','.join(map(str, x)) + '}'
    stream = bytearray()
    offsets = []
    for curve in q['curves']:
        delta = [b-a for a,b in zip(curve,curve[1:])]
        if min(delta)<0 or max(delta)>255:
            raise ValueError('Marlboro packed delta bounds')
        encoded = encode_curve_deltas(delta)
        if decode_curve_deltas(encoded) != delta:
            raise ValueError('Marlboro packed curve readback')
        offsets.append(len(stream));stream.extend(encoded)
    packed = '{' + ','.join([arr([v for row in q['matrix_q13'] for v in row]),
                            arr([v for row in q['post_q9'] for v in row]),
                            arr([c[0] for c in q['curves']]),arr(offsets)]) + '}'
    return ('/* Generated lossless native ISP profile from marlboro-reference.json. */\n'
            'static const native_frame_packed native_marlboro_frame=' + packed + ';\n'
            'static const uint8_t native_marlboro_curve_stream[]=' + arr(stream) + ';\n'
            'static const int16_t native_marlboro_hue[108]=' + arr([v for sector in q['hue_q10'] for row in sector for v in row]) + ';\n')


def generate():
    import numpy as np
    from scripts.fit_gr3_native_film_targets import fit, quantize, render_quantized, fit_gate, STD_CSP
    from scripts.verify_gr3_anime_e6_reference import verify_profile
    from scripts.analyze_gr3_film_color_targets import metrics
    base = np.array(json.loads((ROOT / 'native/gr3/native-film-fit-targets.json').read_text())['base_gamma_q14']) / 16384
    neutral = np.repeat(np.linspace(0, 1, 256)[:, None], 3, axis=1)
    train = np.vstack([np.random.default_rng(32720261105).uniform(0, 1, (4096, 3)), neutral, neutral, neutral])
    params, optimization = fit(train, render(train), base, iterations=3000, constrain_native=True, monochrome=True)
    q = quantize(params)
    # Force exact hardware-neutral chroma, rather than merely low RGB error.
    post = np.repeat(np.rint(np.mean(q['post_q9'], axis=0)).astype(int)[None, :], 3, axis=0)
    native = (STD_CSP.astype(int) @ post + 256) // 512
    q.update(post_q9=post.tolist(), native_csp_signed9=native.tolist(),
             effective_relative_post=(np.linalg.inv(STD_CSP) @ native).tolist())
    verify_profile(q)
    hold = np.random.default_rng(20261105327).uniform(0, 1, (32768, 3))
    score = metrics(render(hold), render_quantized(q, hold, base))
    q.update(film_id=327, holdout=score, optimization=optimization, gate=fit_gate(score, False))
    if score['de00_p95'] > 2 or score['de00_max'] > 6:
        raise ValueError('Marlboro native fit quality: ' + json.dumps(score))
    grid = np.stack(np.meshgrid(*[np.linspace(0, 1, 15)] * 3, indexing='ij'), axis=-1).reshape(-1, 3)
    values = np.rint(render(grid) * 255).astype('uint8').ravel().tolist()
    native_values = np.rint(render_quantized(q, grid, base) * 255).astype('uint8').ravel().tolist()
    stock = SPEC | dict(values=values, native_values=native_values)
    (ROOT / 'web/gr3/marlboro-luts.json').write_text(json.dumps(dict(size=15, bits=8, order='RGB, blue fastest', stocks=[stock]), separators=(',', ':')) + '\n')
    paths = ['scripts/build_gr3_marlboro_reference.py', 'scripts/preview_gr3_marlboro.py',
             'scripts/fit_gr3_native_film_targets.py', 'scripts/fit_gr3_d76_native.py',
             'native/gr3/native-film-fit-targets.json', 'web/gr3/marlboro-luts.json']
    ref = dict(schema='m10v-marlboro-reference/v1', camera_validated=False,
               default_camera_renderer='quantized native ISP; no CPU color LUT',
               stocks=[SPEC | dict(table_sha256=digest(bytes(values)), native_preview_sha256=digest(bytes(native_values)))],
               native_profiles_full=[q],
               approved_target=dict(luma_q13=[2449, 4809, 934], black=.035, span=.93, smoothstep_weight=.45, curve_bits=14),
               fitting_validation=dict(train_seed=32720261105, holdout_seed=20261105327, holdout_count=32768,
                                       iterations_limit=3000, metric='CIEDE2000 display model, not camera output'),
               halo=dict(kernel='m10v_800t_effects', gain=7, spread=7, threshold=5, cpu_neon_authorized=True),
               files={p: digest((ROOT / p).read_bytes()) for p in paths})
    (ROOT / 'native/gr3/marlboro-reference.json').write_text(json.dumps(ref, ensure_ascii=False, indent=2) + '\n')
    (ROOT / 'native/gr3/m10v_marlboro_native_profile.h').write_text(native_header(ref))
    print(json.dumps(score), flush=True)


def verify(root=ROOT):
    from scripts.verify_gr3_anime_e6_reference import verify_profile
    root = Path(root)
    ref = json.loads((root / 'native/gr3/marlboro-reference.json').read_text())
    web = json.loads((root / 'web/gr3/marlboro-luts.json').read_text())
    if ref['camera_validated'] or ref['default_camera_renderer'] != 'quantized native ISP; no CPU color LUT':
        raise ValueError('Marlboro unsupported hardware claim')
    if [s['id'] for s in web['stocks']] != [327] or [q['film_id'] for q in ref['native_profiles_full']] != [327]:
        raise ValueError('Marlboro inventory')
    for path, sha in ref['files'].items():
        if digest((root / path).read_bytes()) != sha:
            raise ValueError('Marlboro source changed: ' + path)
    q = ref['native_profiles_full'][0]
    verify_profile(q)
    if q['native_csp_signed9'][1:] != [[0, 0, 0], [0, 0, 0]]:
        raise ValueError('Marlboro must have exactly neutral ISP chroma')
    stock, spec = web['stocks'][0], ref['stocks'][0]
    for key, field in [('values', 'table_sha256'), ('native_values', 'native_preview_sha256')]:
        v = stock[key]
        if len(v) != 10125 or any(type(n) is not int or not 0 <= n <= 255 for n in v) or digest(bytes(v)) != spec[field]:
            raise ValueError('Marlboro preview digest/bounds')
    if (root / 'native/gr3/m10v_marlboro_native_profile.h').read_text() != native_header(ref):
        raise ValueError('Marlboro native profile readback')
    return ref


if __name__ == '__main__':
    if '--verify' in sys.argv:
        verify()
        print('Marlboro reference verified')
    else:
        generate()
