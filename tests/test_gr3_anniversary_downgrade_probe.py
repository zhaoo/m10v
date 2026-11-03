"""Research probes must distinguish version admission from actual installation."""
import os
import unittest
from scripts.probe_gr3_anniversary_downgrade import probe


class AnniversaryDowngradeProbeTests(unittest.TestCase):
    def test_unknown_model_is_rejected_without_reading_any_file(self):
        with self.assertRaisesRegex(ValueError, 'model'):
            probe('missing.bin', 'missing.bin', 'gr4')

    @unittest.skipUnless(os.environ.get('M10V_GR3_220_FIXTURE'), 'requires official 2.20')
    def test_220_original_updater_rejects_old_bridge_and_patched_new_updater_admits_old_official(self):
        result = probe(os.environ['M10V_GR3_220_FIXTURE'], 'bin/fwdc239b-gr3-official.bin', 'gr3')
        self.assertEqual(result['stage_one_package_version'], '2.20.21.28')
        self.assertFalse(result['bin_emitted'])
        self.assertFalse(result['installation_allowed'])
        self.assertEqual(len(result['historical_bridge_rejection']), 6)
        self.assertTrue(all(row['accepted'] is False for row in result['historical_bridge_rejection']))
        self.assertTrue(all(row['accepted'] is True for row in result['second_stage'] if row['patched']))
        self.assertTrue(all(row['accepted'] is False for row in result['second_stage'] if not row['patched']))
        self.assertEqual(result['patch']['address'], '0x536286cc')
        self.assertEqual(result['patch']['destination'], '0x5362866c')

    @unittest.skipUnless(os.environ.get('M10V_GR3X_170_FIXTURE'), 'requires official 1.70')
    def test_170_uses_its_own_identity_and_keeps_hardware_gate_closed(self):
        result = probe(os.environ['M10V_GR3X_170_FIXTURE'], 'bin/fwdc243b-gr3x-official.bin', 'gr3x')
        self.assertEqual(result['stage_one_package_version'], '1.70.21.18')
        self.assertFalse(result['camera_verified'])
        self.assertFalse(result['installation_allowed'])
        self.assertTrue(result['remaining_blockers'])
        self.assertTrue(any(row['mode'] == 'wrong_model' and not row['accepted'] for row in result['cpu_validation']))


if __name__ == '__main__':
    unittest.main()
