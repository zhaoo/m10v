"""Typed references must never reinterpret pixel/data words as ARM branches."""
import struct
import unittest
from scripts.gr3_target_relocations import Relocations


class TargetRelocationTests(unittest.TestCase):
    def test_data_words_do_not_become_branch_relocations(self):
        r = Relocations()
        # This is data with the bit pattern of a BL to stock firmware.
        raw = struct.pack('<II', 0xeb000000, 0x55068200)
        r.data(0x540c0000, raw)
        self.assertEqual(r.finish(0x540c0000, raw), [
            {'kind': 'pointer', 'sites': [0x540c0004], 'words': [0x55068200], 'target': 0x55068200},
        ])

    def test_code_records_branch_and_movw_movt_pair(self):
        r = Relocations()
        base = 0x540c0000
        delta = (0x5351ea9c-base-8)//4
        raw = struct.pack('<4I', 0xeb000000 | (delta & 0xffffff),
                          0xe3082200, 0xe1a00000, 0xe3452506)
        r.code(base, raw)
        self.assertEqual([(x['kind'],x['target']) for x in r.finish(base, raw)],
                         [('branch',0x5351ea9c),('mov_pair',0x55068200)])

    def test_overwritten_or_out_of_runtime_records_are_discarded(self):
        r = Relocations()
        r.data(0x540c0000,struct.pack('<I',0x55068200))
        r.data(0x540d0000,struct.pack('<I',0x55068200))
        self.assertEqual(r.finish(0x540c0000,bytes(4)),[])


if __name__ == '__main__': unittest.main()
