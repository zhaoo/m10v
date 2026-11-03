"""Mixed-version lab evidence must never open the production download gate."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.probe_gr3_anniversary_preserved_cpu import probe

ROOT = Path(__file__).resolve().parents[1]


class PreservedCpuProbeTests(unittest.TestCase):
    def test_unsupported_model_rejected_before_file_access(self):
        with self.assertRaisesRegex(ValueError, 'unsupported model'):
            probe('missing.bin', 'missing.bin', 'gr4')

    def test_firmware_output_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'not-a-package.bin'
            result = subprocess.run([sys.executable, '-m', 'scripts.probe_gr3_anniversary_preserved_cpu',
                '--new', 'missing.bin', '--old', 'missing.bin', '--model', 'gr3', '--report', str(output)],
                cwd=ROOT, text=True, capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('research output must be JSON', result.stdout)
            self.assertFalse(output.exists())

    def check_profile(self, fixture, old, model):
        result = probe(fixture, ROOT/'bin'/old, model)
        for flag in ('installation_allowed', 'camera_verified', 'stable', 'bin_emitted'):
            self.assertFalse(result[flag])
        self.assertTrue(result['cpu_entirely_preserved'])
        self.assertEqual(result['cpu_getter_third_component'], 20)
        self.assertEqual(result['combined_footer_kind'], 2)
        self.assertEqual(len(result['unchanged_sections']), 13)
        self.assertFalse(result['production_import']['accepted'])
        self.assertEqual(result['production_import']['reason'], 'version: component copies differ')
        self.assertFalse(result['prior_all_fields_raised_model']['internally_consistent'])
        self.assertEqual(result['decompressor_driver_prefix']['reached'], '0x53857fd8')
        self.assertFalse(result['decompressor_driver_prefix']['hardware_decoded'])
        self.assertEqual(result['memory_variant_frames']['literal_lengths'], [24576])
        self.assertTrue(result['original_compressed_trailer_preserved']['flags_references_and_frame_length_preserved'])
        self.assertEqual(result['second_stage_version_cases'], [
            {'kind': 2, 'patched': False, 'accepted': False},
            {'kind': 2, 'patched': True, 'accepted': True},
        ])
        # Combined type must retain the original CPU-version boundary.
        self.assertEqual([row['accepted'] for row in result['first_stage_version_cases'] if row['kind'] == 2],
                         [True, True, False, False])

    @unittest.skipUnless(os.environ.get('M10V_GR3_220_FIXTURE'), 'requires exact official 2.20')
    def test_gr3_preserves_official_cpu_and_web_rejects_lab_container(self):
        self.check_profile(os.environ['M10V_GR3_220_FIXTURE'], 'fwdc239b-gr3-official.bin', 'gr3')

    @unittest.skipUnless(os.environ.get('M10V_GR3X_170_FIXTURE'), 'requires exact official 1.70')
    def test_gr3x_preserves_official_cpu_and_web_rejects_lab_container(self):
        self.check_profile(os.environ['M10V_GR3X_170_FIXTURE'], 'fwdc243b-gr3x-official.bin', 'gr3x')


if __name__ == '__main__':
    unittest.main()
