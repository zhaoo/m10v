"""Original ARM request evidence; no hardware pixel or timing simulation."""
import hashlib
import unittest
from pathlib import Path

from scripts.analyze_gr3_border_iip import analyze, probe_fill, probe_rectangle

ROOT = Path(__file__).resolve().parents[1]


class BorderIipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.roms = {m: (ROOT / f'builds/gr3-border-iip-20261027/{m}-official-rtos.bin').read_bytes()
                    for m in ('gr3', 'gr3x')}

    def test_rejects_unrecognized_image_and_model_mismatch(self):
        for model, rom in self.roms.items():
            with self.assertRaises(ValueError):
                analyze(rom, 'gr4')
            with self.assertRaises(ValueError):
                analyze(rom, 'gr3x' if model == 'gr3' else 'gr3')
            with self.assertRaises(ValueError):
                analyze(rom[:-1], model)

    def test_both_official_images_have_identical_border_contract_instructions(self):
        reports = [analyze(rom, model) for model, rom in self.roms.items()]
        self.assertEqual(reports[0]['contract_sha256'], reports[1]['contract_sha256'])
        for report, rom in zip(reports, self.roms.values()):
            self.assertEqual(report['rtos_sha256'], hashlib.sha256(rom).hexdigest())
            self.assertFalse(report['firmware_emitted'])
            self.assertFalse(report['hardware_pixels_executed'])
            self.assertFalse(report['camera_tested'])
            self.assertFalse(report['activation_ready'])
            self.assertIn('failure_quiescence', report['unproved'])

    def test_original_loader_store_preserve_expanded_rectangle(self):
        for model, rom in self.roms.items():
            for x, y, width, height in ((0, 0, 6320, 4640), (160, 160, 6000, 4000),
                                       (0, 0, 4640, 6320), (0, 0, 16384, 16384)):
                with self.subTest(model=model, size=(width, height)):
                    result = probe_rectangle(rom, x, y, width, height)
                    self.assertEqual(result['loader'], [x, x + width - 1, y, y + height - 1])
                    self.assertEqual(result['store'], [x, x + width - 1, y, y + height - 1])
                    self.assertEqual(result['assertions'], [])

    def test_original_fill_driver_builds_constant_gpc_inputs_and_store_size(self):
        from scripts.analyze_gr3_border_iip import probe_fill_driver
        for model, rom in self.roms.items():
            with self.subTest(model=model):
                result = probe_fill_driver(rom, 6320, 4640, (77, 88, 99))
                self.assertEqual(result['constants'], [77, 88, 99])
                self.assertEqual(result['store_size'], [6320, 4640])
                self.assertEqual(result['store_origin'], [0, 0])
                self.assertEqual(result['events'], ['submit', 'wait', 'release'])
                self.assertFalse(result['pixels_mapped'])

    def test_original_fill_driver_also_releases_after_failed_event_wait(self):
        from scripts.analyze_gr3_border_iip import probe_fill_driver
        for rom in self.roms.values():
            result = probe_fill_driver(rom, 160, 120, (255, 128, 128), wait_result=0)
            self.assertEqual(result['events'], ['submit', 'wait', 'release'])
            self.assertFalse(result['failure_quiescence_proven'])

    def test_original_jpeg_request_preserves_expanded_dimensions(self):
        from scripts.analyze_gr3_border_iip import probe_jpeg_request
        for rom in self.roms.values():
            for width, height in ((6320, 4640), (4480, 6640), (6480, 4480)):
                result = probe_jpeg_request(rom, width, height)
                self.assertEqual(result['width'], width)
                self.assertEqual(result['height'], height)
                self.assertEqual(result['stride'], width)
                self.assertEqual(result['source_planes'], [0x70000000, 0x74000000])
                self.assertFalse(result['encoding_executed'])

    def test_original_jpeg_driver_serializes_expanded_dimensions_to_ram_register_fixture(self):
        from scripts.analyze_gr3_border_iip import probe_jpeg_registers
        for rom in self.roms.values():
            for width, height in ((6320, 4640), (4320, 6640), (6480, 4480)):
                result = probe_jpeg_registers(rom, width, height)
                self.assertEqual(result['image_size'], [width, height])
                self.assertEqual(result['dma_size'], [width, height])
                self.assertFalse(result['hardware_executed'])

    def test_original_fill_expanded_canvas_never_accesses_unmapped_planes(self):
        for model, rom in self.roms.items():
            for width, height in ((6320, 4640), (4480, 6640), (6480, 4480), (160, 120)):
                for fmt in (1, 2):
                    with self.subTest(model=model, size=(width, height), fmt=fmt):
                        result = probe_fill(rom, width, height, fmt, (77, 88, 99))
                        self.assertEqual(result['assertions'], [])
                        self.assertEqual(sum(r['height'] for r in result['requests']), height)
                        self.assertEqual(result['locks'], ['acquire', 'release'])
                        covered = 0
                        for request in result['requests']:
                            self.assertGreater(request['height'], 0)
                            self.assertEqual(request['visible_height'], request['height'])
                            self.assertEqual((request['left'], request['top']), (0, 0))
                            y_offset = width * covered
                            c_offset = y_offset // (2 if fmt == 2 else 1)
                            self.assertEqual(request['planes'],
                                             [0x70000000 + y_offset, 0x74000000 + c_offset, c_offset])
                            self.assertEqual(request['width'], width)
                            self.assertEqual(request['stride'], width)
                            self.assertEqual(request['constants'], [77, 88, 99])
                            self.assertEqual(request['format'], 0)
                            self.assertEqual(request['layout_code'], 2 if fmt == 2 else 0)
                            covered += request['height']
                        self.assertEqual(covered, height)
                        self.assertFalse(result['pixels_mapped'])


if __name__ == '__main__':
    unittest.main()
