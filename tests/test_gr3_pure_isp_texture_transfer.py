"""Execute stock texture-transfer metadata with pixel addresses unmapped."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from scripts.border_resize_contract import probe


class PureIspTextureTransferTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures = ROOT / 'builds/gr3-pure-isp-feasibility-20261031'
        cls.roms = {m: (fixtures / f'{m}-official-rtos.bin').read_bytes()
                    for m in ('gr3', 'gr3x')}

    def test_public_route_is_not_a_safe_single_plane_texture_transfer(self):
        for model, rom in self.roms.items():
            with self.subTest(model=model):
                result = probe(rom, 6000, 4000, fmt=0, source_format=0,
                               source_size=(3072, 2048), source_stride=3072,
                               source_plane=0x54600000, destination_stride=6016, texture_research=True)
                self.assertEqual(result['assertions'], [])
                self.assertFalse(result['pixels_mapped'])
                request = result['scaler_requests'][0]
                self.assertEqual(request['source']['size'], [3072, 2048])
                self.assertEqual(request['destination']['size'], [6000, 4000])
                self.assertEqual(request['source']['planes'][0], 0x54600000)
                self.assertEqual(request['destination']['stride'], 6016)
                self.assertEqual(result['events'][-1], 'release_boundary')
                self.assertEqual([x['component'] for x in result['loader_inputs']], [0, 1])
                self.assertEqual([x['selected_plane'] for x in result['loader_inputs']], [0x54600000, 0])
                self.assertFalse(result['single_plane_transfer_proven'])

    def test_failed_wait_remains_failure_evidence(self):
        for rom in self.roms.values():
            result = probe(rom, 6000, 4000, fmt=0, wait_result=0,
                           source_format=0, source_size=(3072, 2048),
                           source_stride=3072, source_plane=0x54600000,
                           destination_stride=6016, texture_research=True)
            self.assertEqual(result['waits'][0]['test_double_result'], 0)
            self.assertFalse(result['failure_quiescence_proven'])
            self.assertFalse(result['hardware_pixels_executed'])

    def test_native_terminal_phase_is_rejected_by_original_assertion(self):
        for rom in self.roms.values():
            result = probe(rom, 6000, 4000, fmt=0, source_format=0,
                           source_size=(3072, 2048), source_stride=3072,
                           source_plane=0x54600000, destination_stride=6016,
                           native_phase=(1, 2), texture_research=True)
            self.assertEqual(result['assertions'], [{'caller': 0x53771170, 'line': 228}])
            self.assertEqual(len(result['loader_inputs']), 1)
            self.assertEqual(result['events'][-1], 'release_boundary')
            self.assertNotIn('submit_boundary', result['events'])
            self.assertNotIn('wait_boundary', result['events'])
            self.assertFalse(result['single_plane_transfer_proven'])

    def test_invalid_source_span_rejected_before_execution(self):
        for stride in (0, 3000, 65536):
            with self.assertRaises(ValueError):
                probe(self.roms['gr3'], source_size=(3072, 2048), source_stride=stride)

    def test_cannot_claim_unmapped_pixels_for_a_mapped_source(self):
        for plane in (0x53000000, 0x55090000, 0x54fff000):
            with self.subTest(plane=hex(plane)), self.assertRaises(ValueError):
                probe(self.roms['gr3'], 6000, 4000, fmt=0, source_format=0,
                      source_size=(3072, 2048), source_stride=3072,
                      source_plane=plane, destination_stride=6016, texture_research=True)

    def test_secondary_plane_overflow_is_rejected_before_descriptor_write(self):
        with self.assertRaises(ValueError):
            probe(self.roms['gr3'], source_plane=0xfe100000, source_format=1)

    def test_oriented_runtime_masks_reach_full_photo_scaler_without_native_assertion(self):
        # Native configuration evidence only: unit upload/events remain explicit
        # boundaries. This does not prove physical scaling quality or DMA.
        for model, rom in self.roms.items():
            for width, height in ((256, 128), (128, 256)):
                for fmt in (1, 2):
                    with self.subTest(model=model, source=(width, height), destination_format=fmt):
                        result = probe(rom, 6000, 4000, fmt=fmt, source_format=2,
                            source_size=(width, height), source_stride=width,
                            source_plane=0x54400000,
                            source_chroma_plane=0x54400000 + width * height,
                            destination_stride=6000, texture_research=True)
                        self.assertEqual(result['assertions'], [])
                        self.assertEqual(len(result['scaler_requests']), 2)
                        self.assertEqual(len(result['loader_inputs']), 2)
                        self.assertEqual(result['events'].count('submit_boundary'), 2)
                        self.assertEqual(result['events'].count('wait_boundary'), 2)
                        self.assertEqual(result['events'][-1], 'release_boundary')
                        self.assertFalse(result['hardware_pixels_executed'])
