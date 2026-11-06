import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from scripts import build_gr3_three_film_preview as fit
from scripts import build_gr3_isp_effect_textures as textures


ROOT = Path(__file__).resolve().parents[1]


class ThreeFilmModelTests(unittest.TestCase):
    def test_shd50_is_high_contrast_monochrome_with_weak_red_response(self):
        colors = np.array([
            [255, 0, 0],
            [0, 255, 0],
            [0, 0, 255],
            [32, 32, 32],
            [64, 64, 64],
            [192, 192, 192],
            [230, 230, 230],
        ], dtype=np.uint8).reshape(1, 7, 3)
        out = fit.render_shd50(colors)[0]
        self.assertTrue(np.array_equal(out[:, 0], out[:, 1]))
        self.assertTrue(np.array_equal(out[:, 1], out[:, 2]))
        self.assertLess(int(out[0, 0]), int(out[2, 0]))
        self.assertLess(int(out[2, 0]), int(out[1, 0]))
        self.assertLess(int(out[3, 0]), 20)
        self.assertGreater(int(out[5, 0]) - int(out[4, 0]), 150)
        self.assertGreaterEqual(int(out[6, 0]), 248)

    def test_rainbow_fields_have_four_deterministic_nonaliased_variants(self):
        keys = {'y_pos', 'y_neg', 'cb_pos', 'cb_neg', 'cr_pos', 'cr_neg'}
        for kind in ('kolor', 'pegasus'):
            variants = [fit.signed_fields(kind, i) for i in range(4)]
            for index, fields in enumerate(variants):
                self.assertEqual(set(fields), keys)
                for component in ('y', 'cb', 'cr'):
                    positive = fields[component + '_pos']
                    negative = fields[component + '_neg']
                    self.assertEqual(positive.shape, (64, 128))
                    self.assertEqual(positive.dtype, np.uint8)
                    self.assertTrue(np.array_equal(positive, fit.signed_fields(kind, index)[component + '_pos']))
                    self.assertFalse(np.any((positive > 0) & (negative > 0)))
                    signed = positive.astype(np.int16) - negative.astype(np.int16)
                    self.assertGreater(int(np.abs(signed).max()), 12)
            digests = {
                hashlib.sha256(b''.join(v[k].tobytes() for k in sorted(keys))).hexdigest()
                for v in variants
            }
            self.assertEqual(len(digests), 4)

    def test_pegasus_is_a_horizontal_band_and_kolor_varies_in_two_dimensions(self):
        pegasus = fit.signed_fields('pegasus', 0)
        p_energy = sum(pegasus[k].astype(np.float32) for k in pegasus)
        row_profile = p_energy.mean(axis=1)
        col_profile = p_energy.mean(axis=0)
        self.assertGreater(float(row_profile.std()), 3 * float(col_profile.std()))
        self.assertGreater(float(row_profile.max()), 30)
        self.assertLess(float(np.percentile(row_profile, 20)), 4)

        kolor = fit.signed_fields('kolor', 0)
        kolor_signed = np.stack([
            kolor[component + '_pos'].astype(np.float32) - kolor[component + '_neg']
            for component in ('y', 'cb', 'cr')
        ], axis=-1)
        self.assertGreater(float(np.max(np.abs(kolor_signed))), 60.0)
        self.assertGreater(float(np.mean(np.abs(kolor_signed))), 10.0)
        k_energy = sum(kolor[k].astype(np.float32) for k in kolor)
        self.assertGreater(float(k_energy.mean(axis=0).std()), 4)
        self.assertGreater(float(k_energy.mean(axis=1).std()), 4)

    def test_reference_records_sources_metrics_and_quantized_bounds(self):
        reference = fit.build_reference()
        self.assertEqual(reference['schema'], 'm10v-three-film-reference/v1')
        self.assertEqual([film['id'] for film in reference['films']], [328, 329, 330])
        self.assertEqual([film['name'] for film in reference['films']], ['SHD50', 'Revolog KOLOR', 'Pegasus'])
        urls = {source['url'] for source in reference['sources'] if source.get('url')}
        self.assertIn('https://www.revolog.net/fr/products/kolor', urls)
        self.assertIn('https://kosmofoto.com/2018/07/new-film-maker-yodica-offers-saturated-special-films/', urls)
        self.assertIn('https://www.reddit.com/r/AnalogCommunity/comments/1rok0tc/lucky_shd50_is_a_weird_film/', urls)
        self.assertLessEqual(reference['metrics']['shd50_curve_quantization_max_dn'], 1)
        self.assertLessEqual(reference['metrics']['rainbow_field_quantization_max_dn'], 1)
        self.assertEqual(reference['rainbow']['variants_per_film'], 4)
        self.assertEqual(reference['rainbow']['field_shape'], [64, 128])

    def test_runtime_asset_inventory_names_every_signed_component(self):
        names = textures._runtime_names()
        for kind in ('kolor', 'pegasus'):
            for variant in range(4):
                for component in ('y', 'cb', 'cr'):
                    for sign in ('pos', 'neg'):
                        self.assertIn(f'rainbow_{kind}_{variant}_{component}_{sign}_nv12', names)
        self.assertEqual(len(names), 85)


class ThreeFilmPreviewTests(unittest.TestCase):
    def test_preview_renderer_is_deterministic_and_preserves_geometry(self):
        source = np.asarray(Image.open(ROOT / 'web/gr3/film-street-source.png').convert('RGB'))
        rendered = {}
        for film in ('shd50', 'revolog-kolor', 'pegasus'):
            first = fit.render_preview(source, film, 0)
            second = fit.render_preview(source, film, 0)
            self.assertEqual(first.shape, source.shape)
            self.assertEqual(first.dtype, np.uint8)
            self.assertTrue(np.array_equal(first, second))
            self.assertFalse(np.array_equal(first, source))
            rendered[film] = first
        self.assertTrue(np.array_equal(rendered['shd50'][..., 0], rendered['shd50'][..., 1]))
        self.assertFalse(np.array_equal(rendered['revolog-kolor'], rendered['pegasus']))

    def test_preview_files_have_stable_layout_and_reference_readback(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            report = fit.generate_previews(output)
            expected = {'shd50.png', 'revolog-kolor.png', 'pegasus.png', 'comparison.png'}
            self.assertEqual({p.name for p in output.glob('*.png')}, expected)
            for name in expected - {'comparison.png'}:
                with Image.open(output / name) as image:
                    self.assertEqual(image.size, (1536, 1024))
            with Image.open(output / 'comparison.png') as image:
                self.assertEqual(image.size, (3072, 2048))
            self.assertEqual(set(report['sha256']), expected)
            for name, digest in report['sha256'].items():
                self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), digest)
            persisted = json.loads((output / 'three-film-reference.json').read_text())
            self.assertEqual(persisted, report['reference'])


if __name__ == '__main__':
    unittest.main()
