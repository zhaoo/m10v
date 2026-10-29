"""Original encoded allocation policy and request bounds, without JPEG pixels."""
import unittest
from pathlib import Path

from scripts.probe_gr3_border_encoded_bank import probe

ROOT = Path(__file__).resolve().parents[1]


class EncodedBankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.roms = {model: (ROOT / f'builds/gr3-border-iip-20261027/{model}-official-rtos.bin').read_bytes()
                    for model in ('gr3', 'gr3x')}
        cls.reports = {model: probe(rom, model) for model, rom in cls.roms.items()}

    def test_hash_and_model_mismatch_are_rejected(self):
        for model, rom in self.roms.items():
            for label, data in ((None, rom), ('gr4', rom),
                                ('gr3x' if model == 'gr3' else 'gr3', rom), (model, rom[:-1])):
                with self.assertRaises(ValueError):
                    probe(data, label)
        self.assertEqual(self.reports['gr3']['spans'], self.reports['gr3x']['spans'])

    def test_real_encoded_query_and_id4_layout_bound_active_controls(self):
        for report in self.reports.values():
            off, on, expanded = report['cases']
            self.assertEqual(off['native_query_capacity'], 15159200)
            self.assertEqual(on['native_query_capacity'], 18516800)
            for case in (off, on, expanded):
                self.assertEqual(case['original_encoded_query_calls'], 2)
                self.assertEqual(case['recipe_bank_pointer'], 0x60000000)
                self.assertEqual(case['recipe_capacity_field'], case['native_query_capacity'])
                self.assertEqual(case['capture_codec_extra_enable'], int(case['extra_enabled_fixture']))
                self.assertEqual(case['assertions'], [])
                self.assertEqual([c['offset_in_bank'] for c in case['controls']],
                                 [128, 15086016, 15150656, 15158976])
                self.assertEqual([c['capacity'] for c in case['controls']],
                                 [15085728, 64512, 8192, 3300000])
                for control in case['controls']:
                    if control['active_fixture']:
                        self.assertTrue(control['fits_query'])
                        self.assertEqual(control['pointer'] % 64, 0)
                if case['extra_enabled_fixture']:
                    self.assertTrue(case['auxiliary_rgb_thumbnail']['fits_query'])
                    self.assertEqual(case['auxiliary_rgb_thumbnail']['capacity'], 57600)
            self.assertFalse(off['controls'][3]['fits_query'])
            self.assertFalse(off['controls'][3]['active_fixture'])
            self.assertIsNone(off['extra_request'])

    def test_setup6_and_native_driver_keep_per_channel_bounds_for_expanded_geometry(self):
        for report in self.reports.values():
            for case in report['cases']:
                self.assertEqual(case['setup6_bindings'],
                    [0x550800b0, 0x550800d0, 0x550800f0, 0x55080110,
                     0x55080130, 0x55080148, 0x55080160, 0x55080178])
                self.assertEqual(case['r110_geometry'][:2], case['dimensions_fixture'])
                for name, index in (('main', 0), ('extra', 3)):
                    request = case[name + '_request']
                    if request is None:
                        continue
                    control = case['controls'][index]
                    self.assertEqual(request['dimensions'], case['dimensions_fixture'])
                    self.assertEqual(request['output_pointer'], control['pointer'])
                    self.assertEqual(request['output_pointer_register'], control['pointer'])
                    self.assertEqual(request['output_capacity'], control['capacity'])
                    self.assertEqual(request['output_capacity_register_sectors'], control['capacity'] // 512)
                    self.assertEqual(request['serialized_capacity_bytes'], control['capacity'] // 512 * 512)

    def test_stock_si_does_not_enlarge_bank_when_yuv_canvas_grows(self):
        for report in self.reports.values():
            _, stock, expanded = report['cases']
            self.assertEqual(stock['native_query_capacity'], expanded['native_query_capacity'])
            self.assertEqual(stock['controls'], expanded['controls'])
            policy = report['explicit_dimension_native_policy']
            self.assertEqual(policy[0]['main'], {'target_bytes': 13714288, 'capacity': 15085728})
            self.assertEqual(policy[0]['extra'], {'target_bytes': 3000000, 'capacity': 3300000})
            self.assertEqual(policy[1]['main'], {'target_bytes': 16757040, 'capacity': 18432752})
            self.assertEqual(policy[1]['extra'], {'target_bytes': 3665600, 'capacity': 4032160})
            for p in policy:
                self.assertEqual(p['assertions'], [])
            for flag in ('hardware_executed', 'pixels_mapped', 'pool_allocation_executed', 'activation_ready'):
                self.assertFalse(report[flag])


if __name__ == '__main__':
    unittest.main()
