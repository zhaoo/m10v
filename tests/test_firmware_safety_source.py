import importlib.util
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('safety_source', ROOT / 'skills/m10v-firmware-safety/scripts/verify_source.py')
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)


class FirmwareSafetySourceTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('M10V_GR3X_170_FIXTURE'), 'requires official IIIx 1.70')
    def test_strictly_decoded_170_is_identified_but_remains_blocked(self):
        report = source.inspect(os.environ['M10V_GR3X_170_FIXTURE'], 'gr3x', ROOT)
        self.assertEqual(report['public_version'], '1.70')
        self.assertTrue(report['source_identity_verified'])
        self.assertTrue(report['full_decode_verified'])
        self.assertFalse(report['supported_build_source'])
        self.assertEqual(report['status'], 'blocked_new_version')


if __name__ == '__main__':
    unittest.main()
