import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import border_yuv_bank_contract as contract


class YuvBankContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.roms = {model: (ROOT / path).read_bytes() for model, path in (
            ('gr3', 'builds/gr3-extension-validation/official-rtos.bin'),
            ('gr3x', 'builds/gr3-border-iip-20261027/gr3x-official-rtos.bin'))}

    def test_native_query_setter_and_stock_footprint(self):
        for model, rom in self.roms.items():
            with self.subTest(model=model):
                r = contract.probe(rom)
                self.assertEqual(r['assertions'], [])
                self.assertEqual(r['native_capacity'], 72192000)
                self.assertEqual(r['native_capacity'], 3 * 6016 * 4000)
                self.assertEqual(r['covered_bytes'], 51168064)
                self.assertEqual(r['tail_bytes'], 21023936)
                self.assertTrue(r['raw_pointer_unchanged'])
                self.assertEqual([d['size'] for d in r['descriptors']],
                    [[6000, 4000], [720, 480], [6000, 4000], [720, 480], [160, 120]])
                self.assertEqual(r['descriptors'][0]['planes'][0] - contract.BANK_BASE,
                                 9 * 16 * 6016)
                self.assertFalse(r['pixels_mapped'])

    def test_expanded_fixture_fits_budget_but_tail_append_does_not(self):
        for model, rom in self.roms.items():
            r = contract.analyze(rom, model)
            expanded = r['expanded_geometry_only']
            self.assertEqual(expanded['assertions'], [])
            self.assertEqual(expanded['covered_bytes'], 61961024)
            self.assertLess(expanded['covered_bytes'], r['stock']['native_capacity'])
            self.assertFalse(r['disjoint_tail_canvas']['fits_stock_capacity'])
            self.assertEqual(r['disjoint_tail_canvas']['additional_capacity'], 37774144)
            self.assertFalse(r['activation_ready'])

    def test_typed_develop_output_to_original_r2y_registers(self):
        for rom in self.roms.values():
            old = contract.probe_develop_geometry(rom)
            new = contract.probe_develop_geometry(rom, 6336)
            self.assertEqual(old['assertions'], [])
            self.assertEqual(new['assertions'], [])
            self.assertEqual(old['native_initial_geometry'], [6000, 4000, 6016, 4000, 0, 0])
            self.assertEqual(new['output_geometry'], [6000, 4000, 6336, 4000, 0, 0])
            self.assertEqual(new['r2y_native_output']['stride'], 6336)
            self.assertEqual(new['output_stride_register_low17'], 6336)
            self.assertTrue(new['status_stride_unchanged'])
            self.assertTrue(new['original_r2y_packer_executed'])
            self.assertTrue(new['original_r2y_output_config_executed'])
            self.assertFalse(new['hardware_registers_written'])

    def test_normal_stream_path_has_no_bank_rgb_intermediates(self):
        for rom in self.roms.values():
            baseline = contract.probe_streaming_intermediates(rom)
            bank_changed = contract.probe_streaming_intermediates(rom, 0x64000000, 0x60000000)
            output_changed = contract.probe_streaming_intermediates(rom, 0x60000000, 0x64000000)
            for r in (baseline, bank_changed, output_changed):
                self.assertEqual(r['assertions'], [])
                self.assertEqual(r['b2r_request_flags'], [1, 1, 1, 1, 0, 0, 0, 0])
                self.assertEqual(r['b2r_memory_output_flag'], 0)
                self.assertEqual(r['b2r_native_rgb_planes'], [0, 0, 0])
                self.assertTrue(all(d['format'] == 8 and d['planes'] == [0, 0, 0]
                                    for d in r['rgb_descriptors']))
                self.assertEqual(r['r2y_native_input_selector'], 1)
                self.assertEqual(r['r2y_native_rgb_input_planes'], [0, 0, 0])
                self.assertEqual(r['r2y_input_descriptor_pointer'], 0)
                self.assertEqual(r['native_heap_allocations'], 0)
                self.assertFalse(r['pixels_mapped'])
            self.assertEqual(baseline['r2y_yuv_output_planes'], bank_changed['r2y_yuv_output_planes'])
            self.assertNotEqual(baseline['r2y_yuv_output_planes'], output_changed['r2y_yuv_output_planes'])
            self.assertEqual(output_changed['r2y_yuv_output_planes'], [0x64100000, 0x65900000, 0])

    def test_native_halo_crop_registers_survive_independent_output_pitch(self):
        for rom in self.roms.values():
            for index, (column, roi_x, width) in enumerate(((0,68,1972),(1960,12,1996),(3944,12,2068))):
                old = contract.probe_native_halo(rom,6144,index)
                new = contract.probe_native_halo(rom,6336,index)
                for result in (old,new):
                    self.assertEqual(result['assertions'],[])
                    self.assertEqual(result['crop_registers'],[(width<<16)|roi_x,(4012<<16)|40])
                    self.assertEqual(result['native_planes'],[0x60180000+column,0x64180000+column,0])
                    self.assertEqual(result['native_crop'],[roi_x,width,40,4012])
                    self.assertFalse(result['pixels_mapped'])
                self.assertEqual([i*4 for i,(a,b) in enumerate(zip(old['registers'],new['registers'])) if a!=b],
                                 [0x140,0x144])


if __name__ == '__main__':
    unittest.main()
