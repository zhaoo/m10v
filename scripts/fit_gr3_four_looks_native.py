"""Fit original floating source transforms directly, then quantize and evaluate."""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def native_header(ref):
    from scripts.fit_gr3_d76_native import native_header as full_header
    return full_header(ref).replace('d76-reference.json', 'four-looks-reference.json').replace('native_d76', 'native_four_looks').replace('[7]', '[4]').replace('live approximation, never still completion', 'quantized native ISP; no CPU color LUT')


def seam_samples(q, base):
    import numpy as np
    from scripts.fit_gr3_native_film_targets import BOUNDS, YCC, AXIS
    rays = []
    for quadrant in range(4):
        rays.append(quadrant * 90.)
        rays.extend((quadrant * 90 + np.degrees(np.arctan2(2048 - v, v))) % 360 for v in BOUNDS[quadrant])
    # Sectors operate after the fitted relative pre-matrix; map both sides back
    # into model input RGB so the test crosses actual native partition planes.
    samples = []
    inverse = np.linalg.inv(np.asarray(q['effective_relative_matrix']))
    for angle in sorted(set(rays)):
        for y in [.2, .5, .8]:
            for amplitude in [.03, .08]:
                theta = np.radians([angle - 1e-5, angle + 1e-5])
                z = np.column_stack([np.full(2, y), amplitude * np.cos(theta), amplitude * np.sin(theta)]) @ np.linalg.inv(YCC).T
                x = z @ inverse.T
                if np.all((x >= 0) & (x <= 1)):
                    samples.append(np.interp(x, AXIS, base))
    if not samples:
        raise ValueError('no reachable seam samples')
    return np.vstack(samples)


def generate():
    import numpy as np
    from scripts.build_gr3_four_looks_reference import render, digest, purple_interpolator
    from scripts.fit_gr3_native_film_targets import fit, quantize, render_quantized, fit_gate
    from scripts.build_gr3_harman_reference import sample_tetrahedral
    from scripts.analyze_gr3_film_color_targets import metrics
    from scripts.verify_gr3_anime_e6_reference import verify_profile

    ref = json.loads((ROOT / 'native/gr3/four-looks-reference.json').read_text())
    web = json.loads((ROOT / 'web/gr3/four-looks-luts.json').read_text())
    base = np.array(json.loads((ROOT / 'native/gr3/native-film-fit-targets.json').read_text())['base_gamma_q14']) / 16384
    neutral = np.repeat(np.linspace(0, 1, 257)[:, None], 3, axis=1)
    train = np.vstack([np.random.default_rng(318321).uniform(0, 1, (4096, 3)), neutral, neutral, neutral])
    # New final holdout is not used for solver/candidate selection.
    hold = np.random.default_rng(20261031322).uniform(0, 1, (32768, 3))
    tune = np.random.default_rng(2383318).uniform(0, 1, (8192, 3))
    skin = np.array([[115, 82, 68], [194, 150, 130], [98, 62, 45], [220, 172, 143], [255, 210, 180]]) / 255
    # All six cube faces, including corners and edges, independent of training.
    face = np.stack(np.meshgrid(np.linspace(0, 1, 23), np.linspace(0, 1, 23), indexing='ij'), axis=-1).reshape(-1, 2)
    saturated = np.vstack([np.insert(face, axis, value, axis=1) for axis in range(3) for value in [0, 1]])
    grid = np.stack(np.meshgrid(*[np.linspace(0, 1, 15)] * 3, indexing='ij'), axis=-1).reshape(-1, 3)
    profiles = []
    for stock, spec in zip(web['stocks'], ref['stocks']):
        film = stock['id']
        print('fitting original float source', film, flush=True)
        target = render(film, train)
        params, opt = fit(train, target, base, iterations=8000, constrain_native=True)
        q = quantize(params)
        verify_profile(q)
        candidates = []
        if film == 318:
            expected_tune = render(film, tune)
            def evaluate(candidate, optimization, seed, iterations):
                quantized = quantize(candidate)
                verify_profile(quantized)
                score = metrics(expected_tune, render_quantized(quantized, tune, base))
                candidates.append(dict(train_seed=seed, iterations_limit=iterations, optimization=optimization, tuning=score))
                return score['de00_mean'] + score['de00_p95'] / 4
            best = evaluate(params, opt, 318321, 8000)
            for seed in [319318, 321318]:
                alternate = np.vstack([np.random.default_rng(seed).uniform(0, 1, (4096, 3)), neutral, neutral, neutral])
                trial, optimization = fit(alternate, render(film, alternate), base, iterations=6000, constrain_native=True)
                selection = evaluate(trial, optimization, seed, 6000)
                print('2383 candidate', seed, candidates[-1]['tuning'], flush=True)
                if selection < best:
                    best, params, opt = selection, trial, optimization
            q = quantize(params)
        seams = seam_samples(q, base)
        sets = dict(random_holdout=hold, neutral=neutral, skin=skin, saturated=saturated, seam=seams)
        scores = {key: metrics(render(film, samples), render_quantized(q, samples, base)) for key, samples in sets.items()}
        native = np.rint(render_quantized(q, grid, base) * 255).astype('uint8')
        scores['preview_interpolation'] = metrics(render_quantized(q, hold, base), sample_tetrahedral(native.reshape(15, 15, 15, 3) / 255, hold))
        seam_output = render_quantized(q, seams, base).reshape(-1, 2, 3)
        scores['seam']['max_pair_rgb_code_jump'] = float(np.max(np.abs(np.diff(seam_output, axis=1))) * 255)
        scores['neutral']['max_channel_spread_codes'] = float(np.max(np.ptp(render_quantized(q, neutral, base), axis=1)) * 255)
        q.update(film_id=film, holdout=scores['random_holdout'], validation=scores,
                 optimization=opt, float_parameters=params.tolist(), candidates=candidates,
                 gate=fit_gate(scores['random_holdout'], False))
        profiles.append(q)
        stock['native_values'] = native.ravel().tolist()
        spec['native_preview_sha256'] = digest(bytes(stock['native_values']))
        print(film, json.dumps(scores), flush=True)

    chart = json.loads((ROOT / 'third_party/four-looks/purple-chart.json').read_text())
    indices = chart['holdout_indices']
    x = np.array([chart['input']['samples'][i]['median_rgb'] for i in indices]) / 255
    y = np.array([chart['output']['samples'][i]['median_rgb'] for i in indices]) / 255
    ref['purple_chart_holdout'] = dict(indices=indices, count=len(indices), source_interpolation=metrics(y, np.clip(purple_interpolator()(x), 0, 1)), native_vs_observed=metrics(y, render_quantized(profiles[3], x, base)), uncertainty='Four illustrative JPEG patches only, not independent film measurement; excludes reference construction and ISP training')
    ref.update(native_profiles_full=profiles,
               fitting_validation=dict(original_float_reference=True, constrain_native=True,
                                       train_seed=318321, holdout_seed=20261031322, train_random_count=4096,
                                       kodak_alternate_train_seeds=[319318, 321318], tuning_seed=2383318,
                                       tuning_count=8192, selection='2383 only: minimum quantized tuning DE00 mean + P95/4; final holdout unused for selection',
                                       holdout_count=32768, iterations_limit=8000, solver='L-BFGS-B existing analytic constrained fitter',
                                       metric='CIEDE2000 display sRGB, not physical film', camera_validated=False))
    (ROOT / 'web/gr3/four-looks-luts.json').write_text(json.dumps(web, separators=(',', ':')) + '\n')
    for path in ['scripts/fit_gr3_four_looks_native.py', 'scripts/verify_gr3_four_looks_reference.py', 'scripts/fit_gr3_native_film_targets.py', 'scripts/analyze_gr3_film_color_targets.py', 'scripts/build_gr3_harman_reference.py', 'native/gr3/native-film-fit-targets.json', 'web/gr3/four-looks-luts.json']:
        ref['files'][path] = digest((ROOT / path).read_bytes())
    (ROOT / 'native/gr3/four-looks-reference.json').write_text(json.dumps(ref, indent=2) + '\n')
    (ROOT / 'native/gr3/m10v_four_looks_native_profiles.h').write_text(native_header(ref))


if __name__ == '__main__':
    generate()
