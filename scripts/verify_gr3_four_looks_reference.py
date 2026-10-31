"""Offline stdlib-only checks for native build/export hosts."""
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.verify_gr3_anime_e6_reference import verify_profile as check_bounds


def verify_profile(q):
    check_bounds(q)
    # Independently read back the integer composition used by the native frame
    # helper, not just the serialized coefficient bounds.
    standard_cca = [[436, -184, 4], [-48, 400, -96], [1, -104, 359]]
    standard_csp = [[77, 150, 29], [-43, -85, 128], [128, -107, -21]]
    def multiply(a, b, rounding, divisor):
        return [[(sum(a[i][k] * b[k][j] for k in range(3)) + rounding) // divisor
                 for j in range(3)] for i in range(3)]
    if q['native_cca_signed12'] != multiply(q['matrix_q13'], standard_cca, 4096, 8192):
        raise ValueError('native CCA composition readback')
    if q['native_csp_signed9'] != multiply(standard_csp, q['post_q9'], 256, 512):
        raise ValueError('native CSP composition readback')


def verify_header(ref, text):
    from scripts.fit_gr3_four_looks_native import native_header
    if text != native_header(ref):
        raise ValueError('four looks native header readback')


def verify(root=ROOT):
    root = Path(root)
    ref = json.loads((root / 'native/gr3/four-looks-reference.json').read_text())
    web = json.loads((root / 'web/gr3/four-looks-luts.json').read_text())
    if (web['size'], web['bits'], web['order']) != (15, 8, 'RGB, blue fastest'):
        raise ValueError('four looks domain')
    if ref['camera_validated'] or ref['default_camera_renderer'] != 'quantized native ISP; no CPU color LUT':
        raise ValueError('unsupported camera claim')
    if [s['id'] for s in ref['stocks']] != list(range(318, 322)) or [s['id'] for s in web['stocks']] != list(range(318, 322)) or [q['film_id'] for q in ref['native_profiles_full']] != list(range(318, 322)):
        raise ValueError('four looks inventory')
    for path, sha in ref['files'].items():
        if hashlib.sha256((root / path).read_bytes()).hexdigest() != sha:
            raise ValueError('four looks source changed: ' + path)
    if ref['sources'] != json.loads((root / 'third_party/four-looks/sources.json').read_text()):
        raise ValueError('four looks sources divergence')
    for stock, spec, profile in zip(web['stocks'], ref['stocks'], ref['native_profiles_full']):
        verify_profile(profile)
        for entry in [stock, spec]:
            if not entry['approximation'] or entry['official_lut'] or entry['camera_calibrated'] or entry['film_calibrated']:
                raise ValueError('unsupported fidelity claim')
        for key, hashkey in [('values', 'table_sha256'), ('native_values', 'native_preview_sha256')]:
            values = stock[key]
            if len(values) != 10125 or any(type(v) is not int or not 0 <= v <= 255 for v in values) or hashlib.sha256(bytes(values)).hexdigest() != spec[hashkey]:
                raise ValueError('four looks table digest/bounds')
        for scores in profile['validation'].values():
            if any(not math.isfinite(v) for v in scores.values()):
                raise ValueError('four looks nonfinite validation')
    if len({bytes(s['values']) for s in web['stocks']}) != 4:
        raise ValueError('aliased four look references')
    verify_header(ref, (root / 'native/gr3/m10v_four_looks_native_profiles.h').read_text())
    return ref


if __name__ == '__main__':
    verify()
    print('four looks reference verified')
