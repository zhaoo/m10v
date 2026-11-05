"""Approved artistic reference and bounded ISP fit; not a hardware pixel test."""
import importlib
import unittest
import numpy as np


class MarlboroReferenceTests(unittest.TestCase):
    def test_approved_target_is_neutral_high_contrast_and_has_no_baked_halo(self):
        module = importlib.import_module('scripts.build_gr3_marlboro_reference')
        ramp = np.repeat(np.linspace(0, 1, 256)[:, None], 3, axis=1)
        result = module.render(ramp)
        np.testing.assert_array_equal(result[:, 0], result[:, 1])
        np.testing.assert_array_equal(result[:, 1], result[:, 2])
        self.assertEqual(result[0, 0], 0)
        self.assertEqual(result[-1, 0], 1)
        self.assertLess(result[64, 0], ramp[64, 0])
        self.assertGreater(result[192, 0], ramp[192, 0])
        self.assertTrue(np.all(np.diff(result[:, 0]) >= 0))
        colors = module.render(np.random.default_rng(327).uniform(0, 1, (1000, 3)))
        np.testing.assert_array_equal(colors[:, 0], colors[:, 1])

    def test_quantized_profile_and_preview_are_traceable_and_achromatic(self):
        module = importlib.import_module('scripts.build_gr3_marlboro_reference')
        ref = module.verify()
        q = ref['native_profiles_full'][0]
        self.assertEqual(q['film_id'], 327)
        self.assertFalse(ref['camera_validated'])
        self.assertEqual(q['native_csp_signed9'][1:], [[0, 0, 0], [0, 0, 0]])
        self.assertLessEqual(q['holdout']['de00_p95'], 2)
        self.assertLessEqual(q['holdout']['de00_max'], 6)


if __name__ == '__main__':
    unittest.main()
