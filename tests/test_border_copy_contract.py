"""Offline contract only: original ARM never reads/writes photo-plane bytes."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import border_copy_contract as contract


class BorderCopyContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.roms = {model: (ROOT / path).read_bytes() for model, path in (
            ('gr3', 'builds/gr3-extension-validation/official-rtos.bin'),
            ('gr3x', 'builds/gr3-border-iip-20261027/gr3x-official-rtos.bin'))}

    def test_identity_and_model_fail_closed(self):
        for model, rom in self.roms.items():
            self.assertEqual(contract.validate(rom, model), contract.HASHES[model])
            changed = bytearray(rom)
            changed[-1] ^= 1
            with self.assertRaises(ValueError):
                contract.probe(changed)
            with self.assertRaises(ValueError):
                contract.validate(rom, 'gr3x' if model == 'gr3' else 'gr3')

    def test_target_offset_binding_and_native_registers(self):
        for model, rom in self.roms.items():
            with self.subTest(model=model):
                r = contract.probe(rom)
                self.assertEqual(r['assertions'], [])
                s, d = r['descriptors']
                self.assertEqual([s['size'], d['size']], [[6000, 4000]] * 2)
                self.assertEqual([s['flag_field4'], d['flag_field4']], [1, 0])
                self.assertEqual([s['stride_bytes'], d['stride_bytes']], [6000, 6336])
                self.assertEqual(d['plane'], 0x74000000 + 160 * 6336 + 160)
                self.assertTrue(all(v['unchanged_except_handle'] for v in (s, d)))
                self.assertEqual(r['graph']['descriptors'], [s['address'], d['address']])
                self.assertEqual(r['graph']['node_count'], 2)
                self.assertEqual([v['unit'] for v in r['unit_uploads']], [2, 31])
                for desc, regs in zip((s, d), r['format_register_fixture']):
                    self.assertEqual(regs['size'], 6000 | 4000 << 16)
                    self.assertEqual(regs['stride'], desc['stride_bytes'])
                    self.assertEqual(regs['plane'], desc['plane'])
                    self.assertEqual(regs['control'] >> 8 & 15, 6)
                    self.assertEqual(regs['control'] >> 12 & 1, desc['flag_field4'])
                self.assertEqual(r['cache'][-1], {'address': d['plane'], 'bytes': 6336 * 4000})
                self.assertEqual(r['native_return_from_wait_double'], 1)
                self.assertEqual(r['wait']['mask'], 0x400)
                self.assertFalse(r['pixels_mapped'])
                self.assertFalse(r['hardware_pixels_executed'])
                self.assertFalse(r['ownership_proven'])
                self.assertFalse(r['failure_quiescence_proven'])
                self.assertTrue(r['resource_bitset_instruction_substitutions'])
                events = r['events']
                self.assertLess(events.index('scheduler_submit_boundary'), events.index('wait_boundary'))
                self.assertLess(events.index('wait_boundary'), events.index('release_boundary'))

    def test_public_same_format_uses_its_own_service_route(self):
        for rom in self.roms.values():
            r = contract.probe_public_same_format(rom)
            self.assertEqual(r['assertions'], [])
            self.assertEqual(r['factory'], 0x5369a0e8)
            self.assertEqual(r['opcode'], 0x010e8006)
            self.assertEqual(r['mask'], 0x400)
            self.assertEqual(r['parameter_descriptors'], [0x55081000, 0x55082000])
            self.assertEqual(r['service_dispatch_argument'], 0x55084008)
            self.assertFalse(r['dispatcher_executed'])
            self.assertFalse(r['ownership_proven'])

    def test_public_worker_formats_offsets_and_failed_wait(self):
        for rom in self.roms.values():
            for fmt in (1, 2):
                for left, mode in ((160, 6), (68, 1)):
                    r = contract.probe_transfer_worker(rom, fmt=fmt, left=left)
                    self.assertEqual(r['assertions'], [])
                    self.assertEqual(len(r['transfers']), 2)
                    y, c = r['transfers']
                    self.assertEqual(y['mode'], mode)
                    self.assertEqual(y['geometry'], [6000, 4000, 6000, 6336, 0, 0, 0, 0])
                    self.assertEqual(c['geometry'], [6000, 4000 if fmt == 1 else 2000,
                                                    6000, 6336, 0, 0, 0, 0])
                    self.assertEqual(y['planes'][1], 0x74000000 + 160 * 6336 + left)
                    self.assertFalse(r['dma_executed'])
                    self.assertFalse(r['pixels_mapped'])
                    self.assertTrue(all(w['mask'] == 0x03050001 for w in r['waits']))
                caches = contract.probe_public_cache(rom, fmt)
                self.assertEqual(caches['assertions'], [])
                self.assertEqual([e['bytes'] for e in caches['events']],
                                 [25344000, 25344000 if fmt == 1 else 12672000] * 2)
            failed = contract.probe_transfer_worker(rom, 0)
            self.assertEqual(len(failed['transfers']), 2)
            self.assertEqual(failed['events'].count('driver_handoff_boundary'), 2)
            self.assertFalse(failed['failure_quiescence_proven'])

    def test_failed_wait_still_releases_and_invalidates(self):
        for rom in self.roms.values():
            r = contract.probe(rom, wait_result=0)
            self.assertEqual(r['native_return_from_wait_double'], 0)
            self.assertIn('release_boundary', r['events'])
            self.assertEqual(r['cache'][-1]['bytes'], 25344000)
            self.assertFalse(r['failure_quiescence_proven'])

    def test_bad_geometry_and_full_native_cache_span(self):
        for kwargs in ({'left': -1}, {'width': 6337}, {'height': 0},
                       {'top': 321}, {'left': 161}, {'width': True},
                       {'canvas_height': 4160}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                contract.geometry(**kwargs)
        g = contract.geometry()
        self.assertLessEqual(g['cache_end'], g['canvas_base'] + g['allocation_bytes'])
        self.assertEqual(g['byte_offset'], 1013920)


if __name__ == '__main__':
    unittest.main()
