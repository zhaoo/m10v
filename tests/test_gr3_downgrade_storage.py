"""Schema identity guards do not authorize writing or downgrading a camera."""
import os
from pathlib import Path
import unittest

from scripts.analyze_gr3_downgrade_storage import load, schema, schema_guard


class StorageSchemaGuardTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('M10V_GR3_220_FIXTURE'), 'requires exact official 2.20')
    def test_old_and_new_schema_input_passes_real_loop_but_changed_edge_words_do_not(self):
        old, new = load('gr3_old')['sections']['RTOS'], load('gr3_new')['sections']['RTOS']
        for receiver, origin in ((old, new), (new, old)):
            description = schema(origin)
            start = int(description['actual_compared_start'], 16)-0x53000000
            table = origin[start:start+4172]
            match = schema_guard(receiver, table)
            self.assertTrue(match['accepted'])
            self.assertEqual(match['compared_words'], 1043)
            for index in (0, 521, 1042):
                mismatch = schema_guard(receiver, table, index)
                self.assertFalse(mismatch['accepted'])
                self.assertEqual(mismatch['compared_words'], index+1)
                self.assertFalse(mismatch['persistent_write_executed'])
                self.assertFalse(mismatch['default_or_error_path_executed'])

    @unittest.skipUnless(os.environ.get('M10V_GR3X_170_FIXTURE'), 'requires exact official 1.70')
    def test_iiix_schema_length_or_unknown_mutation_index_is_rejected(self):
        rom = load('gr3x_new')['sections']['RTOS']
        description = schema(rom)
        start = int(description['actual_compared_start'], 16)-0x53000000
        table = rom[start:start+4172]
        with self.assertRaisesRegex(ValueError, 'length differs'):
            schema_guard(rom, table[:-4])
        with self.assertRaisesRegex(ValueError, 'invalid changed word'):
            schema_guard(rom, table, 1043)


if __name__ == '__main__':
    unittest.main()
