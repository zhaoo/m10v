import tempfile
import unittest

from scripts.build_gr3_m10v_library import build
from scripts.build_gr3_save_trace import build as build_trace


class PureIspBuildAdmissionTests(unittest.TestCase):
    def test_requires_complete_native_owned_chain_before_compiling(self):
        with tempfile.TemporaryDirectory() as out:
            with self.assertRaisesRegex(ValueError, 'pure ISP'):
                build(out, pure_isp_effects=True)

    def test_rejects_nonboolean_effect_flag(self):
        with tempfile.TemporaryDirectory() as out:
            with self.assertRaisesRegex(ValueError, 'pure ISP'):
                build(out, pure_isp_effects='yes')

    def test_effects_factory_reserves_exact_96_byte_tail(self):
        with tempfile.TemporaryDirectory() as out:
            _, report = build_trace(out, pure_isp_effects=True)
            self.assertEqual(report['storage']['extended_recipe_bytes'], 0x57d8)
            self.assertEqual(report['storage']['effects_offset'], 0x5778)
            self.assertEqual(report['storage']['effects_bytes'], 96)
