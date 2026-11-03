"""Keep register-prefix evidence separate from a successful physical decode."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.probe_gr3_anniversary_decompress_contract import probe

ROOT = Path(__file__).resolve().parents[1]


class DecompressContractTests(unittest.TestCase):
    def test_unknown_model_rejected_before_reading_files(self):
        with self.assertRaisesRegex(ValueError, 'unsupported model'):
            probe('missing.bin', 'missing.bin', 'gr4')

    def test_cli_never_writes_firmware_or_overwrites_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)/'not-firmware.bin'
            args = [sys.executable, '-m', 'scripts.probe_gr3_anniversary_decompress_contract',
                    '--new', 'missing.bin', '--old', 'missing.bin', '--model', 'gr3', '--report']
            result = subprocess.run(args+[str(target)], cwd=ROOT, text=True, capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('research output must be JSON', result.stdout)
            self.assertFalse(target.exists())
            target = Path(directory)/'existing.json'
            target.write_text('preserved')
            result = subprocess.run(args+[str(target)], cwd=ROOT, text=True, capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('already exists', result.stdout)
            self.assertEqual(target.read_text(), 'preserved')

    def check_profile(self, fixture, old, model):
        result = probe(fixture, ROOT/'bin'/old, model)
        for field in ('installation_allowed', 'camera_verified', 'stable', 'bin_emitted'):
            self.assertFalse(result[field])
        self.assertEqual(len(result['original_driver_blocks_identical']), 3)
        for name in ('official', 'proposed'):
            trace = result[name]
            self.assertEqual(trace['reached'], '0x53857fd8')
            self.assertEqual(trace['registers']['0x1b030004'], 1)
            self.assertEqual(trace['registers']['0x1b03002c'], 1)
            self.assertEqual(trace['registers']['0x1b030018'], 0x56000080)
            self.assertEqual(trace['registers']['0x1b030020'], 0x60000000)
            for field in ('wait_executed', 'interrupt_synthesized', 'hardware_decoded', 'completion_substituted'):
                self.assertFalse(trace[field])
        self.assertEqual(result['disabled_engine']['writes'], [])
        self.assertEqual(result['disabled_engine']['reached'], '0x550ffff0')
        self.assertEqual(result['differing_registers'], ['0x1b03001c'])
        self.assertGreater(result['in_memory_frames']['literal_count'], 0)

    @unittest.skipUnless(os.environ.get('M10V_GR3_220_FIXTURE'), 'requires exact official 2.20')
    def test_gr3_stops_at_real_hardware_wait(self):
        self.check_profile(os.environ['M10V_GR3_220_FIXTURE'], 'fwdc239b-gr3-official.bin', 'gr3')

    @unittest.skipUnless(os.environ.get('M10V_GR3X_170_FIXTURE'), 'requires exact official 1.70')
    def test_gr3x_stops_at_real_hardware_wait(self):
        self.check_profile(os.environ['M10V_GR3X_170_FIXTURE'], 'fwdc243b-gr3x-official.bin', 'gr3x')


if __name__ == '__main__':
    unittest.main()
