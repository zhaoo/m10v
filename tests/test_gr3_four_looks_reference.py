"""Numerical source contracts; these are not physical camera acceptance."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class FourLooksReference(unittest.TestCase):
    def test_source_builder_exists(self):
        self.assertTrue((ROOT / 'scripts/build_gr3_four_looks_reference.py').is_file())

    def builder(self):
        import scripts.build_gr3_four_looks_reference as source
        return source

    def test_flog2_reflection_code_values(self):
        import numpy as np
        source = self.builder()
        np.testing.assert_allclose(source.flog2_encode(np.array([0, .18, .9])) * 1023,
                                   [95, 400, 570], atol=1)
        encoded = source.fuji_input(np.full((1, 3), .5))
        self.assertLess(float(encoded.max()), .5)
        np.testing.assert_allclose(encoded[0], encoded[0, 0], atol=1e-5)

    def test_cube_axis_is_red_fastest_on_disk(self):
        import numpy as np
        source = self.builder()
        rows = ['LUT_3D_SIZE 2']
        rows += [f'{r} {g} {b}' for b in [0, 1] for g in [0, 1] for r in [0, 1]]
        table = source.parse_cube('\n'.join(rows))
        from scripts.build_gr3_harman_reference import sample_tetrahedral
        rgb = np.array([[.12, .36, .91], [.9, .2, .1]])
        np.testing.assert_allclose(sample_tetrahedral(table, rgb), rgb, atol=1e-12)
        with self.assertRaises(ValueError):
            source.parse_cube('LUT_3D_SIZE 2\n0 0 0')

    def test_generated_integrity_and_exact_readback(self):
        from scripts.verify_gr3_four_looks_reference import verify
        ref = verify(ROOT)
        self.assertEqual([s['id'] for s in ref['stocks']], [318, 319, 320, 321])
        self.assertFalse(ref['camera_validated'])
        self.assertTrue(ref['fitting_validation']['original_float_reference'])
        for profile in ref['native_profiles_full']:
            self.assertEqual(set(profile['validation']),
                             {'random_holdout', 'neutral', 'skin', 'saturated', 'seam', 'preview_interpolation'})

    def test_bounds_and_readback_reject_corruption(self):
        import copy
        from scripts.verify_gr3_four_looks_reference import verify_profile, verify_header
        ref = json.loads((ROOT / 'native/gr3/four-looks-reference.json').read_text())
        profile = copy.deepcopy(ref['native_profiles_full'][0])
        profile['native_csp_signed9'][0][0] = 256
        with self.assertRaises(ValueError):
            verify_profile(profile)
        profile = copy.deepcopy(ref['native_profiles_full'][0])
        profile['native_cca_signed12'][0][0] += 1
        with self.assertRaisesRegex(ValueError, 'composition readback'):
            verify_profile(profile)
        text = (ROOT / 'native/gr3/m10v_four_looks_native_profiles.h').read_text()
        with self.assertRaises(ValueError):
            verify_header(ref, text.replace('native_four_looks_frame', 'wrong_frame', 1))

    def test_pinned_fetch_rejects_corrupt_cached_bytes(self):
        import tempfile
        from unittest.mock import patch
        source = self.builder()
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'input').write_bytes(b'corrupt')
            with patch.object(source, 'CACHE', Path(folder)):
                with self.assertRaisesRegex(ValueError, 'cached source digest'):
                    source.fetch_checked('input', 'https://invalid.example', '0' * 64)

    def test_purple_preserves_observed_color_shift_without_channel_swap(self):
        import numpy as np
        source = self.builder()
        # The photographed green chart patch is violet in the official guide.
        chart = json.loads((ROOT / 'third_party/four-looks/purple-chart.json').read_text())
        x = np.array([chart['input']['samples'][13]['median_rgb']]) / 255
        result = source.render(321, x)[0]
        self.assertGreater(result[2], result[1])
        # The four declared validation patches must not be RBF training knots.
        self.assertEqual(chart['holdout_indices'], [2, 8, 14, 20])
        self.assertEqual(len(chart['input']['samples']), 24)


if __name__ == '__main__':
    unittest.main()
