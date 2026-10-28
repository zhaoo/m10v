import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import border_cache_contract as contract


class CacheContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.roms=[(ROOT/p).read_bytes() for p in (
            'builds/gr3-extension-validation/official-rtos.bin',
            'builds/gr3-border-iip-20261027/gr3x-official-rtos.bin')]

    def test_native_context_selects_clean_invalidate_or_invalidate(self):
        for rom in self.roms:
            for eligible,mode in ((True,'clean_invalidate'),(False,'invalidate')):
                r=contract.probe_cache(rom,length=128,eligible=eligible)
                self.assertEqual(r['assertions'],[])
                operations=[e for e in r['events'] if e['kind']=='maintenance']
                self.assertEqual([e['mode'] for e in operations],[mode]*3)
                self.assertEqual([e['scope'] for e in operations],['mva']*3)
                self.assertEqual([e['operand'] for e in operations],[0x60000000,0x60000040,0x60000080])
                self.assertEqual(r['events'][-1]['kind'],'dsb')
            rejected=contract.probe_cache(rom,entry=0x536bbc3c,length=128,eligible=False)
            self.assertFalse(any(e['kind']=='maintenance' for e in rejected['events']))
            self.assertTrue(any(e['kind']=='native_warning' for e in rejected['events']))

    def test_stillmake_whole_bank_uses_cross_core_setway_not_plane_line_walk(self):
        for rom in self.roms:
            r=contract.probe_stillmake(rom)
            self.assertEqual(r['assertions'],[])
            self.assertEqual(r['threshold'],262144)
            calls=[e for e in r['events'] if e['kind']=='adapter']
            self.assertEqual([(e['address'],e['bytes']) for e in calls],[(0x60000000,72192000)])
            self.assertEqual([e['targets'] for e in r['events'] if e['kind']=='sgi_request'],[1,2])
            operations=[e for e in r['events'] if e['kind']=='maintenance']
            self.assertEqual([e['mode'] for e in operations],['clean_invalidate']*8)
            self.assertEqual([e['scope'] for e in operations],['setway']*8)
            self.assertEqual([e['level'] for e in operations],[0]*4+[1]*4)
            self.assertTrue(r['remote_ack_is_double'])
            self.assertFalse(r['pixels_mapped'])

    def test_real_remote_handler_finishes_l1_before_ack_barrier(self):
        for rom in self.roms:
            for core in (0,1):
                r=contract.probe_remote(rom,2,core)
                events=r['events'];self.assertEqual(r['assertions'],[])
                self.assertEqual(len([e for e in events if e['kind']=='maintenance']),4)
                self.assertEqual([e['level'] for e in events if e['kind']=='maintenance'],[0]*4)
                ack=next(i for i,e in enumerate(events) if e['kind']=='ack_store' and e['value']==1)
                self.assertEqual(events[ack]['core'],core)
                self.assertEqual(events[ack-1]['kind'],'dsb')
                self.assertEqual(events[ack+1]['kind'],'dsb')
                self.assertFalse(r['remote_ack_is_double'])

    def test_backresize_cleanup_preserves_native_calls_and_visible_cache_height(self):
        for rom in self.roms:
            r=contract.probe_backresize_cleanup(rom);self.assertEqual(r['assertions'],[])
            calls=[e for e in r['events'] if e['kind']=='adapter']
            self.assertEqual([(e['address'],e['bytes']) for e in calls],
                [(0x72000000,57600),(0x73000000,76032000),
                 (0x60180000,14243328),(0x64180000,14243328)])
            self.assertEqual(len([e for e in r['events'] if e['kind']=='maintenance']),924)

    def test_original_debug_limit_switch_can_disable_fast_global_path(self):
        for rom in self.roms:
            r=contract.probe_limit_controls(rom)
            self.assertEqual(r['assertions'],[])
            self.assertEqual(r['disabled'],[0xffffffff,0xffffffff])
            self.assertEqual(r['restored'],[16384,262144])
            operations=[e for e in r['disabled_events'] if e['kind']=='maintenance']
            self.assertEqual(len(operations),4096)
            self.assertTrue(all(e['scope']=='mva' and e['mode']=='clean_invalidate' for e in operations))
            self.assertFalse(any(e['kind']=='sgi_request' for e in r['disabled_events']))

    def test_original_prepared_one_caller_skips_both_public_cache_methods(self):
        for rom in self.roms:
            r=contract.probe_prepared_one(rom)
            self.assertEqual(r['assertions'],[])
            self.assertEqual(r['original_prepared_one_events'],['native_dispatch_boundary'])
            self.assertEqual(r['unprepared_events'],
                             ['pre_cache_method','native_dispatch_boundary','post_cache_method'])


if __name__=='__main__':unittest.main()
