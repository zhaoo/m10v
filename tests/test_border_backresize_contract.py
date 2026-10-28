import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import border_backresize_contract as contract


class BackResizeContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.roms = [(ROOT / name).read_bytes() for name in (
            'builds/gr3-extension-validation/official-rtos.bin',
            'builds/gr3-border-iip-20261027/gr3x-official-rtos.bin')]

    def test_crop_uses_new_low_descriptor_pitch(self):
        for rom in self.roms:
            for crop, offset in (((6000, 4000), 0), ((6000, 2248), 876 * 6336),
                                 ((4664, 4000), 668)):
                with self.subTest(crop=crop):
                    r = contract.probe_backresize(rom, crop)
                    self.assertEqual(r['assertions'], [])
                    expected = [0x60180000 + offset, 0x64180000 + offset, 0]
                    self.assertEqual(r['source_after']['planes'], expected)
                    self.assertEqual(r['main_after']['planes'], expected)
                    self.assertEqual(r['source_after']['geometry'], [*crop, 6336, 4000, 0, 0])
                    self.assertEqual(r['main_after']['geometry'], [*crop, 6336, 4000, 0, 0])
                    self.assertEqual(r['before']['source']['planes'][0] -
                                     r['before']['main']['planes'][0], 144 * 6336)
                    self.assertEqual(r['native_request']['opcode'], 0x708001)
                    self.assertEqual(r['events'][:2], ['submit_boundary', 'wait_boundary'])
                    self.assertFalse(r['pixels_mapped'])

    def test_nonzero_origin_and_wait_failure_are_not_normalized(self):
        for rom in self.roms:
            r = contract.probe_backresize(rom, (6000, 2248), origin=(12, 8))
            self.assertEqual(r['source_after']['geometry'][4:], [12, 8])
            self.assertEqual(r['main_after']['geometry'][4:], [0, 0])
            failed = contract.probe_backresize(rom, wait_result=0)
            self.assertEqual(failed['assertions'], [])
            self.assertEqual(failed['events'].count('cache_boundary'), 4)

    def test_setup6_original_metadata_is_repeatable(self):
        for rom in self.roms:
            r = contract.probe_setup6(rom)
            self.assertEqual(r['assertions'], [])
            self.assertTrue(r['setup5_leaves_jpeg_context_unchanged'])
            self.assertTrue(r['setup6_copies_source_to_110'])
            self.assertTrue(r['setup6_idempotent_same_source'])
            self.assertEqual(r['later_setup6_refreshes_110']['geometry'],
                             [6320, 4640, 6336, 4640, 0, 0])
            self.assertEqual(r['later_setup6_refreshes_110']['planes'],
                             [0x60000000, 0x64000000, 0])
            self.assertEqual(r['context_fields30_to58'],
                             [0x550801a8, 0x55210000, 0x55200000, 0x550800b0,
                              0x550800d0, 0x550800f0, 0x55080110, 0x55080130,
                              0x55080148, 0x55080160, 0x55080178])
            allowed = set(range(0x110, 0x12d)) | set(range(0x9e8, 0xa14))
            self.assertTrue(all(w['recipe_offset'] in allowed
                                for w in r['setup6_recipe_writes']))
            self.assertEqual(r['native_allocations'], 0)
            self.assertFalse(r['work_published'])

    def test_stripes_are_original_byte_columns_without_pitch_conversion(self):
        for rom in self.roms:
            r = contract.probe_stripe_offsets(rom)
            self.assertEqual(r['assertions'], [])
            self.assertEqual(r['writer_offsets'], [0, 1960, 3944])
            self.assertEqual(r['copied_offsets'], r['writer_offsets'])
            self.assertEqual(r['output_plane_bindings'],
                             [[0x60180000 + n, 0x64180000 + n]
                              for n in (0, 1960, 3944)])
            self.assertFalse(r['pitch_read_by_binding'])
            self.assertFalse(r['camera_initialization_selector_executed'])


if __name__ == '__main__':
    unittest.main()
