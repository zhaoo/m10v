import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import border_resize_contract as contract


class BorderResizeContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.roms = {model: (ROOT / path).read_bytes() for model, path in (
            ('gr3', 'builds/gr3-extension-validation/official-rtos.bin'),
            ('gr3x', 'builds/gr3-border-iip-20261027/gr3x-official-rtos.bin'))}

    def test_official_identity_fail_closed(self):
        for model, rom in self.roms.items():
            self.assertEqual(contract.validate(rom, model), contract.HASHES[model])
            with self.assertRaises(ValueError):
                contract.probe(bytes([rom[0] ^ 1]) + rom[1:])

    def test_public_route_and_original_resize_requests(self):
        for model, rom in self.roms.items():
            for width, height, stride in ((654, 480, 720), (160, 116, 160)):
                for fmt in (1, 2):
                    with self.subTest(model=model, width=width, fmt=fmt):
                        r = contract.probe(rom, width, height, fmt)
                        self.assertEqual(r['assertions'], [])
                        self.assertEqual(r['public_request']['opcode'], 0x00708002)
                        self.assertEqual(r['public_request']['mask'], 0x40)
                        self.assertEqual(len(r['scaler_requests']), 2)
                        y, c = r['scaler_requests']
                        self.assertEqual(y['source']['size'], [6320, 4640])
                        self.assertEqual(y['destination']['size'], [width, height])
                        self.assertEqual(c['source']['size'], [3160, 4640])
                        self.assertEqual(c['destination']['size'], [width // 2, height if fmt == 1 else height // 2])
                        for request in (y, c):
                            self.assertEqual(request['source']['stride'], 6336)
                            self.assertEqual(request['destination']['stride'], stride)
                            self.assertEqual(request['roi_fields'], [0, 0, 0, 0])
                        self.assertFalse(r['pixels_mapped'])
                        self.assertFalse(r['hardware_pixels_executed'])
                        self.assertTrue(r['scaler_configuration_executed'])
                        self.assertFalse(r['unit_uploads_executed'])
                        self.assertTrue(all(v['computed_configuration'] for v in r['scaler_requests']))
                        self.assertEqual(r['events'].count('submit_boundary'), 2)
                        self.assertEqual(r['events'][-1], 'release_boundary')
                        self.assertTrue(all(w['mask'] == 4 for w in r['waits']))

    def test_failed_wait_is_not_success_or_quiescence(self):
        for rom in self.roms.values():
            r = contract.probe(rom, wait_result=0)
            self.assertEqual(len(r['scaler_requests']), 2)
            self.assertEqual(r['events'][-1], 'release_boundary')
            self.assertFalse(r['failure_quiescence_proven'])
            self.assertFalse(r['ownership_proven'])

    def test_odd_or_outside_capacity_rejected(self):
        rom = next(iter(self.roms.values()))
        for size in ((655, 480), (654, 481), (722, 480), (0, 480)):
            with self.assertRaises(ValueError):
                contract.probe(rom, *size)


if __name__ == '__main__':
    unittest.main()
