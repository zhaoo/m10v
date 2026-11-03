"""Container research must preserve negative evidence and hardware boundaries."""
import os
from pathlib import Path
import subprocess
import sys
import unittest

from scripts.probe_gr3_anniversary_container import probe

ROOT = Path(__file__).resolve().parents[1]


class AnniversaryContainerProbeTests(unittest.TestCase):
    def test_unknown_model_rejected_before_io(self):
        with self.assertRaisesRegex(ValueError, 'unsupported model'):
            probe('missing.bin', 'gr4')

    def test_cli_refuses_firmware_report_path_before_reading_source(self):
        result = subprocess.run([sys.executable, 'scripts/probe_gr3_anniversary_container.py',
            '--new', 'missing.bin', '--model', 'gr3', '--report', '/tmp/research-must-never-write.bin'],
            cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('research output must be JSON', result.stdout)
        self.assertFalse(Path('/tmp/research-must-never-write.bin').exists())

    def check_probe(self, fixture, model, version):
        result = probe(fixture, model)
        self.assertEqual(result['status'], 'offline_partial_evidence')
        self.assertEqual(result['preservation']['version'], version)
        for flag in ('installation_allowed', 'camera_verified', 'stable', 'bin_emitted'):
            self.assertFalse(result[flag])
        self.assertFalse(result['full_parser_boundary']['completed'])
        self.assertEqual(result['full_parser_boundary']['hardware_mmio_base'], '0x1b030000')
        self.assertEqual(result['strict_host_candidate']['source_authenticity'], 'unverified')
        self.assertEqual(len(result['preservation']['unchanged_sections']), 12)
        self.assertGreater(result['preservation']['original_frames_reused'], 0)
        self.assertEqual(result['strict_host_candidate']['decoded_sha256'], result['preservation']['decoded_sha256'])
        rows = {row['case']: row for row in result['cases']}
        # Preserve this negative finding: outer admission alone is insufficient.
        self.assertTrue(rows['truncated_repaired']['arm_outer_accepted'])
        self.assertFalse(rows['truncated_repaired']['strict_host']['accepted'])
        for case in ('wrong_model_repaired', 'wrong_type_repaired', 'bad_sum'):
            self.assertFalse(rows[case]['arm_outer_accepted'])
            self.assertFalse(rows[case]['strict_host']['accepted'])
        self.assertFalse(rows['cpu_wrong_model_repaired']['arm_cpu_accepted'])
        self.assertFalse(rows['cpu_bad_sum']['arm_cpu_accepted'])
        self.assertTrue(rows['cpu_proposed']['arm_cpu_accepted'])
        self.assertTrue(rows['cpu_section_lookup']['arm_found'])
        self.assertEqual(rows['cpu_section_lookup']['payload_bytes'], 131072)
        dispatch = [row for row in result['cases'] if row['case'] == 'unsupported_dispatch_type']
        self.assertEqual([row['kind'] for row in dispatch], [5, 7])
        self.assertTrue(all(not row['arm_dispatch_accepted'] for row in dispatch))

    @unittest.skipUnless(os.environ.get('M10V_GR3_220_FIXTURE'), 'requires exact official 2.20')
    def test_gr3_memory_bridge_and_original_validators(self):
        self.check_probe(os.environ['M10V_GR3_220_FIXTURE'], 'gr3', '2.20.21.28')

    @unittest.skipUnless(os.environ.get('M10V_GR3X_170_FIXTURE'), 'requires exact official 1.70')
    def test_gr3x_memory_bridge_and_original_validators(self):
        self.check_probe(os.environ['M10V_GR3X_170_FIXTURE'], 'gr3x', '1.70.21.18')


if __name__ == '__main__':
    unittest.main()
