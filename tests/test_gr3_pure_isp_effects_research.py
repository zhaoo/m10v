"""Evidence checks for the read-only research probe, not hardware validation."""
import unittest
from pathlib import Path

from scripts.analyze_gr3_pure_isp_effects import analyze, grain_probe

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'builds/gr3-pure-isp-feasibility-20261031'


class PureIspResearchIdentityTests(unittest.TestCase):
    def test_requires_both_models(self):
        with self.assertRaises(ValueError):
            analyze({})

    def test_rejects_fabricated_firmware(self):
        with self.assertRaises(ValueError):
            analyze({'gr3': bytes(256), 'gr3x': bytes(256)})

    def test_rejects_invalid_probe_dimensions_and_strength(self):
        for width, height, strength in ((0, 1, 1), (1, 65536, 1), (2, 1, 0)):
            with self.assertRaises(ValueError):
                grain_probe(b'', width, height, strength=strength)


class PureIspResearchOfficialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not all((FIXTURES / f'{m}-official-rtos.bin').exists() for m in ('gr3', 'gr3x')):
            raise unittest.SkipTest('exact local official RTOS fixtures not available')
        cls.images = {m: (FIXTURES / f'{m}-official-rtos.bin').read_bytes()
                      for m in ('gr3', 'gr3x')}

    def test_original_metadata_and_cpu_noise_boundary_for_both_models(self):
        report = analyze(self.images)
        self.assertTrue(all(report['identical_original_spans'].values()))
        for model in report['models'].values():
            self.assertEqual(model['grain_workspace_queries'][1]['workspace_bytes'], 24000000)
            self.assertEqual(model['grain_workspace_queries'][3]['workspace_bytes'], 24064000)
            for probe in model['grain_execution_boundaries']:
                self.assertEqual(probe['cpu_noise_request']['bytes'], 24000000)
                self.assertTrue(probe['stopped_before_cpu_noise_execution'])
                self.assertFalse(probe['photo_pixels_mapped'])
                self.assertFalse(probe['noise_pixels_mapped'])
            transfer = model['texture_transfer']
            self.assertFalse(transfer['single_plane_transfer_proven'])
            self.assertEqual(len(transfer['loader_inputs']), 2)
            self.assertEqual(transfer['loader_inputs'][1]['selected_plane'], 0)
            phase = model['rejected_native_terminal_phase']
            self.assertEqual(phase['assertions'], [{'caller': 0x53771170, 'line': 228}])
            self.assertNotIn('submit_boundary', phase['events'])
        for key in ('stock_grain_satisfies_no_cpu_pixels', 'firmware_emitted',
                    'hardware_pixels_executed', 'camera_tested', 'activation_ready'):
            self.assertFalse(report[key])

    def test_rejects_swapped_or_modified_official_images(self):
        with self.assertRaises(ValueError):
            analyze({'gr3': self.images['gr3x'], 'gr3x': self.images['gr3']})
        corrupt = bytearray(self.images['gr3'])
        corrupt[0x67ae14] ^= 1
        with self.assertRaises(ValueError):
            analyze({**self.images, 'gr3': bytes(corrupt)})
