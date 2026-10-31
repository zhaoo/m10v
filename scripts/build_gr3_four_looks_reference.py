"""Traceable display-domain references, never a camera or film calibration.

Official Fujifilm LUTs are fetched and checked, not vendored. Purple uses sparse
paired patches from the official illustrative chart, not measured sensitometry.
"""
import hashlib
import io
import json
import os
import sys
import urllib.request
import zipfile
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'third_party/spectral-film-lut/src')]
os.environ.setdefault('NUMBA_NUM_THREADS', '4')
CACHE = Path(os.environ.get('M10V_FOUR_LOOKS_CACHE', '/private/tmp/m10v-four-looks-source-cache'))
FUJI_URL = 'https://dl.fujifilm-x.com/support/lut/gfx-eterna-55-3d-lut-v110.zip'
FUJI_SHA = 'febfc7050999620651ca0cf162bf8b499970ef270b4da632765b61b958cf7940'
PURPLE_URL = 'https://cdn.downloads.lomography.com/downloads/lomochrome-purple-film-guide.pdf'
PURPLE_SHA = '0fb98ef8d13ae7d289f0fc7a70553a281e533e987d6fe72d186d0389b3505ec9'
FUJI_MEMBERS = {
    319: ('FLog2_to_CLASSIC-Neg._33grid_V.1.00.cube', 'f3db5fe777c3a64e998b8ada64ff8cc2e61f9b44538fd7c550733d1c55c197c5'),
    320: ('FLog2_to_CLASSIC-CHROME_33grid_V.1.00.cube', 'b68c8f4b38da958388931c34ce9eb5c09a495e8c37e654537d534dfd8f023b75'),
}
SPECS = [
    dict(id=318, key='kodak-2383', name='2383', ascii_name='2383', title='KODAK', code='2383', color='#b08a48', group='ECN2', iso=0, reference='MIT spectral 2383 print model with declared ideal-negative display adaptation'),
    dict(id=319, key='classic-negative', name='Classic Negative', ascii_name='Classic Negative', title='CLASSIC', code='NEG', color='#6b7869', group='影像', iso=0, reference='Official GFX ETERNA 55 F-Log2 Classic Neg. v1.00; display adaptation'),
    dict(id=320, key='classic-chrome', name='Classic Chrome', ascii_name='Classic Chrome', title='CLASSIC', code='CHR', color='#607d88', group='影像', iso=0, reference='Official GFX ETERNA 55 F-Log2 Classic Chrome v1.00; display adaptation'),
    dict(id=321, key='lomochrome-purple', name='LomoChrome Purple', ascii_name='LomoChrome Purple', title='PURPLE', code='100-400', color='#985cb1', group='创意', iso=100, reference='Sparse official ISO100 illustrative paired-chart digitization with authored interpolation; not a measured film model'),
]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fetch_checked(name, url, sha):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / name
    if not path.exists():
        data = urllib.request.urlopen(url, timeout=120).read()
        if digest(data) != sha:
            raise ValueError('download source digest: ' + name)
        path.write_bytes(data)
    data = path.read_bytes()
    if digest(data) != sha:
        raise ValueError('cached source digest: ' + name)
    return data


def srgb_decode(rgb):
    import numpy as np
    x = np.asarray(rgb, float)
    return np.where(x <= .04045, x / 12.92, ((x + .055) / 1.055) ** 2.4)


def srgb_encode(rgb):
    import numpy as np
    x = np.maximum(rgb, 0)
    return np.where(x <= .0031308, 12.92 * x, 1.055 * x ** (1 / 2.4) - .055)


def flog2_encode(linear):
    import numpy as np
    x = np.asarray(linear, float)
    return np.where(x < .000889, 8.799461 * x + .092864,
                    .245281 * np.log10(np.maximum(5.555556 * x + .064829, 1e-20)) + .384316)


def fuji_input(rgb):
    import colour
    # Both spaces are D65; no chromatic adaptation. Exposure scale is exactly 1.
    linear = colour.RGB_to_RGB(srgb_decode(rgb), 'ITU-R BT.709', 'ITU-R BT.2020')
    return flog2_encode(linear)


def parse_cube(text):
    import numpy as np
    size = None
    rows = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or line.startswith('TITLE'):
            continue
        if line.startswith('LUT_3D_SIZE'):
            size = int(line.split()[1])
        elif line.startswith('DOMAIN_'):
            expected = 0 if line.startswith('DOMAIN_MIN') else 1
            if list(map(float, line.split()[1:])) != [expected] * 3:
                raise ValueError('unsupported cube domain')
        else:
            rows.append(list(map(float, line.split())))
    a = np.asarray(rows, float)
    if size is None or a.shape != (size ** 3, 3) or not np.isfinite(a).all():
        raise ValueError('cube dimensions or values')
    return a.reshape(size, size, size, 3).transpose(2, 1, 0, 3)


@cache
def fuji_table(film):
    archive = fetch_checked('fuji.zip', FUJI_URL, FUJI_SHA)
    filename, sha = FUJI_MEMBERS[film]
    member = 'gfx-eterna-55-3d-lut-v110/33Grid/F-Log2/' + filename
    data = zipfile.ZipFile(io.BytesIO(archive)).read(member)
    if digest(data) != sha:
        raise ValueError('Fujifilm member digest')
    return parse_cube(data.decode())


@cache
def print_model():
    from spectral_film_lut.film_spectral import FilmSpectral
    from spectral_film_lut.print_film.kodak_2383 import KODAK_2383
    return FilmSpectral(KODAK_2383)


def digitize_purple():
    """Retain numeric facts and rectangles, never the copyrighted photographs."""
    import numpy as np
    import pymupdf
    from PIL import Image
    pdf = pymupdf.open(stream=fetch_checked('purple.pdf', PURPLE_URL, PURPLE_SHA), filetype='pdf')
    # Physical page 2; embedded JPEG pixels, no PDF rescaling/color conversion.
    configurations = [('input', 88, [312, 370, 428, 486, 544, 602], [282, 339, 396, 453]),
                      ('output', 90, [326, 386, 446, 506, 566, 626], [279, 339, 399, 459])]
    result = dict(pdf_sha256=PURPLE_SHA, physical_page=2, half_rectangle=10,
                  holdout_indices=[2, 8, 14, 20], interpolation=dict(kernel='thin_plate_spline', degree=1, smoothing=.02),
                  limitations='Illustrative JPEG chart pair, different captures, unspecified scanner/white balance/exposure/ICC; encoded RGB treated as sRGB. Within-patch spread is not total uncertainty. Sparse extrapolation is authored, not film measurement.')
    for key, xref, columns, rows in configurations:
        image = pdf.extract_image(xref)
        pixels = np.asarray(Image.open(io.BytesIO(image['image'])).convert('RGB'))
        samples = []
        for r, y in enumerate(rows):
            for c, x in enumerate(columns):
                # Right chart slopes upward slightly toward the right.
                cy = y - round(c * 1.2) if key == 'input' else y
                rect = [x - 10, cy - 10, x + 10, cy + 10]
                patch = pixels[rect[1]:rect[3], rect[0]:rect[2]].reshape(-1, 3)
                samples.append(dict(rect=rect, median_rgb=np.median(patch, axis=0).tolist(),
                                    std_rgb=np.std(patch, axis=0).tolist(),
                                    p10_rgb=np.percentile(patch, 10, axis=0).tolist(),
                                    p90_rgb=np.percentile(patch, 90, axis=0).tolist()))
        result[key] = dict(xref=xref, dimensions=[image['width'], image['height']], image_sha256=digest(image['image']), samples=samples)
    return result


@cache
def purple_interpolator():
    import numpy as np
    from scipy.interpolate import RBFInterpolator
    data = json.loads((ROOT / 'third_party/four-looks/purple-chart.json').read_text())
    x = np.array([s['median_rgb'] for s in data['input']['samples']]) / 255
    y = np.array([s['median_rgb'] for s in data['output']['samples']]) / 255
    keep = np.array([i for i in range(24) if i not in data['holdout_indices']])
    return RBFInterpolator(x[keep], y[keep], **data['interpolation'])


def render(film, rgb):
    import numpy as np
    x = np.clip(np.asarray(rgb, float), 0, 1)
    if film == 318:
        from spectral_film_lut.film_spectral import LAD_NEGATIVE
        from spectral_film_lut.color_processing import output_transform
        # Declared ideal neutral negative: density slope .6, LAD at 18% linear.
        # This isolates print stock appearance; it is not a named camera negative.
        apd = LAD_NEGATIVE + .6 * np.log10(np.maximum(srgb_decode(x), 1e-6) / .18)
        model = print_model()
        xyz, _ = model.project(model.print_from_apd(apd), 6500, False, 0)
        out = output_transform(xyz, 'Rec. 709', gamma_func='sRGB')
    elif film in FUJI_MEMBERS:
        from scripts.build_gr3_harman_reference import sample_tetrahedral
        out = srgb_encode(np.clip(sample_tetrahedral(fuji_table(film), fuji_input(x)), 0, 1) ** 2.2)
    elif film == 321:
        out = purple_interpolator()(x)
    else:
        raise ValueError('unknown four-look identity')
    if not np.isfinite(out).all():
        raise ValueError('nonfinite source transform')
    return np.clip(out, 0, 1)


def generate():
    import numpy as np
    source_dir = ROOT / 'third_party/four-looks'
    source_dir.mkdir(parents=True, exist_ok=True)
    chart = digitize_purple()
    (source_dir / 'purple-chart.json').write_text(json.dumps(chart, indent=2) + '\n')
    purple_interpolator.cache_clear()
    grid = np.stack(np.meshgrid(*[np.linspace(0, 1, 15)] * 3, indexing='ij'), axis=-1).reshape(-1, 3)
    stocks, specs = [], []
    for spec in SPECS:
        values = np.rint(render(spec['id'], grid) * 255).astype('uint8').ravel().tolist()
        stock = spec | dict(values=values, approximation=True, official_lut=False, film_calibrated=False, camera_calibrated=False)
        stocks.append(stock)
        specs.append({k: v for k, v in stock.items() if k != 'values'} | dict(table_sha256=digest(bytes(values))))
    sources = json.loads((source_dir / 'sources.json').read_text())
    paths = ['scripts/build_gr3_four_looks_reference.py', 'third_party/four-looks/sources.json', 'third_party/four-looks/README.md', 'third_party/four-looks/purple-chart.json',
             'third_party/spectral-film-lut/LICENSE', 'third_party/spectral-film-lut/SOURCE.json']
    paths += [str(p.relative_to(ROOT)) for p in sorted((ROOT / 'third_party/spectral-film-lut/src').rglob('*.py'))]
    ref = dict(schema='m10v-four-looks-reference/v1', stocks=specs, sources=sources, camera_validated=False,
               default_camera_renderer='quantized native ISP; no CPU color LUT',
               files={p: digest((ROOT / p).read_bytes()) for p in paths},
               limits='Errors measure declared numerical display references only; not physical film/camera accuracy.')
    (ROOT / 'web/gr3/four-looks-luts.json').write_text(json.dumps(dict(size=15, bits=8, order='RGB, blue fastest', stocks=stocks), separators=(',', ':')) + '\n')
    (ROOT / 'native/gr3/four-looks-reference.json').write_text(json.dumps(ref, indent=2) + '\n')


if __name__ == '__main__':
    generate()
