"""The capture and replay formats must agree without consulting active slots."""
import ctypes as c
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Film(c.Structure):
    _fields_ = [('id', c.c_uint32), ('bank', c.c_uint32)]


class RecordedFilmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(folder.cleanup)
        path = Path(folder.name)
        src = path / 'film.c'
        src.write_text('''
#include "m10v_recorded_film.h"
unsigned encode(unsigned id,unsigned bank){return m10v_recorded_film_code(id,bank);}
unsigned decode(unsigned code,m10v_recorded_film *out){return m10v_recorded_film_read(code,out);}
''')
        dll = path / 'film.dylib'
        subprocess.run(['clang', '-O2', '-dynamiclib', '-I', str(ROOT / 'native/gr3'),
                        str(src), '-o', str(dll)], check=True, capture_output=True)
        cls.lib = c.CDLL(str(dll))
        cls.lib.encode.argtypes = [c.c_uint32, c.c_uint32]
        cls.lib.decode.argtypes = [c.c_uint32, c.POINTER(Film)]

    def test_builtin_identity_ignores_slot_and_bank(self):
        for film in (1, 33, 67, 78, 289, 290, 300, 314, 321, 326):
            for unrelated_bank in (0, 21, 255, 256):
                code = self.lib.encode(film, unrelated_bank)
                self.assertEqual(code, 0x1000 + film)
                record = Film()
                self.assertEqual(self.lib.decode(code, c.byref(record)), 1)
                self.assertEqual((record.id, record.bank), (film, 0))

    def test_all_custom_ids_and_immutable_banks_round_trip(self):
        for film in range(79, 289):
            for bank in range(21, 256):
                code = self.lib.encode(film, bank)
                self.assertEqual(code, 0x2000 + (film - 79) * 235 + bank - 21)
                record = Film()
                self.assertEqual(self.lib.decode(code, c.byref(record)), 1)
                self.assertEqual((record.id, record.bank), (film, bank))

    def test_legacy_slots_and_unknown_values_cannot_select_a_film(self):
        for code in (0, 0x100, 0x10c, 0x115, 0x1000, 0x104f, 0x1147,
                     0x1fff, 0xe0c6, 0xffff, 0x10000):
            record = Film(0xdead, 0xbeef)
            self.assertEqual(self.lib.decode(code, c.byref(record)), 0)
            self.assertEqual((record.id, record.bank), (0xdead, 0xbeef))
        for bank in (0, 20, 256, 0xffffffff):
            self.assertEqual(self.lib.encode(79, bank), 0)
        self.assertEqual(self.lib.encode(0, 0), 0)
        self.assertEqual(self.lib.encode(327, 255), 0)
