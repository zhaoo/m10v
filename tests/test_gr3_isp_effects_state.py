"""Host contracts for the metadata-only ISP settings record and snapshot."""
import ctypes as C
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import zlib


ROOT = Path(__file__).resolve().parents[1]
FIELDS = ("leak_gain", "leak_position", "leak_spread", "grain_mode",
          "grain_size", "blur_gain", "blur_range", "reserved")


class Settings(C.Structure):
    _fields_ = [(name, C.c_uint32) for name in FIELDS]


class Snapshot(C.Structure):
    _fields_ = [("settings", Settings), ("effective_grain_strength", C.c_uint32)]


def wire(sequence=0, values=(0,) * 8, magic=0x31505349, version=1):
    body = struct.pack("<11I", magic, version, sequence, *values)
    return body + struct.pack("<I", zlib.crc32(body))


class EffectsStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = ROOT / "native/gr3/m10v_isp_effects_state.c"
        if not source.exists():
            raise AssertionError("ISP effects settings core is not implemented")
        cls.temp = tempfile.TemporaryDirectory()
        library = Path(cls.temp.name) / "effects.so"
        subprocess.run(["clang", "-std=c11", "-Wall", "-Wextra", "-Werror",
                        "-shared", "-fPIC", str(source), "-o", str(library)], check=True)
        cls.lib = C.CDLL(str(library))
        cls.lib.m10v_isp_effects_defaults.argtypes = [C.POINTER(Settings)]
        cls.lib.m10v_isp_effects_validate.argtypes = [C.POINTER(Settings)]
        cls.lib.m10v_isp_effects_encode.argtypes = [C.POINTER(Settings), C.c_uint32,
                                                   C.c_void_p, C.c_size_t]
        cls.lib.m10v_isp_effects_decode.argtypes = [C.c_void_p, C.c_size_t,
                                                   C.POINTER(Settings), C.POINTER(C.c_uint32)]
        cls.lib.m10v_isp_effects_select_newest.argtypes = [C.c_void_p, C.c_size_t,
            C.c_void_p, C.c_size_t, C.POINTER(Settings), C.POINTER(C.c_uint32)]
        cls.lib.m10v_isp_effects_resolve_snapshot.argtypes = [C.POINTER(Settings),
            C.c_uint32, C.POINTER(Snapshot)]

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "temp"):
            cls.temp.cleanup()

    def test_defaults_preserve_inherited_grain_and_disable_new_effects(self):
        settings = Settings(*([0xAAAAAAAA] * 8))
        self.lib.m10v_isp_effects_defaults(C.byref(settings))
        self.assertEqual(bytes(settings), bytes(32))
        self.assertEqual(self.lib.m10v_isp_effects_validate(C.byref(settings)), 1)

    def test_every_parameter_boundary_and_reserved_word_is_validated(self):
        maxima = (3, 2, 2, 4, 2, 3, 2, 0)
        for i, maximum in enumerate(maxima):
            for value, expected in ((0, 1), (maximum, 1), (maximum + 1, 0), (0xFFFFFFFF, 0)):
                settings = Settings()
                setattr(settings, FIELDS[i], value)
                self.assertEqual(self.lib.m10v_isp_effects_validate(C.byref(settings)), expected,
                                 (FIELDS[i], value))
        self.assertEqual(self.lib.m10v_isp_effects_validate(None), 0)

    def test_encoder_is_fixed_little_endian_and_crc_interoperable(self):
        settings = Settings(3, 2, 1, 4, 2, 3, 1, 0)
        out = C.create_string_buffer(48)
        self.assertEqual(self.lib.m10v_isp_effects_encode(C.byref(settings), 0xFEDCBA98, out, 48), 1)
        self.assertEqual(out.raw, wire(0xFEDCBA98, (3, 2, 1, 4, 2, 3, 1, 0)))

    def test_decoder_accepts_independent_record_and_rejects_corrupt_or_unknown_schema(self):
        fixtures = [wire(magic=0), wire(version=2), wire(values=(4, 0, 0, 0, 0, 0, 0, 0)),
                    wire(values=(0, 0, 0, 0, 0, 0, 0, 1))]
        original = wire(17, (1, 2, 0, 3, 2, 1, 2, 0))
        settings = Settings()
        seq = C.c_uint32()
        self.assertEqual(self.lib.m10v_isp_effects_decode(original, 48, C.byref(settings), C.byref(seq)), 1)
        self.assertEqual(tuple(getattr(settings, x) for x in FIELDS), (1, 2, 0, 3, 2, 1, 2, 0))
        self.assertEqual(seq.value, 17)
        for i in range(48):
            changed = bytearray(original)
            changed[i] ^= 1
            fixtures.append(bytes(changed))
        for record in fixtures:
            before = bytes(settings)
            self.assertEqual(self.lib.m10v_isp_effects_decode(record, len(record), C.byref(settings), C.byref(seq)), 0)
            self.assertEqual((bytes(settings), seq.value), (before, 17))

    def test_wrong_lengths_and_null_arguments_fail_without_mutation(self):
        settings = Settings(1)
        seq = C.c_uint32(123)
        out = C.create_string_buffer(b"X" * 49, 49)
        for size in (0, 47, 49):
            self.assertEqual(self.lib.m10v_isp_effects_encode(C.byref(settings), 0, out, size), 0)
            self.assertEqual(out.raw, b"X" * 49)
            self.assertEqual(self.lib.m10v_isp_effects_decode(wire(), size, C.byref(settings), C.byref(seq)), 0)
        self.assertEqual((settings.leak_gain, seq.value), (1, 123))
        self.assertEqual(self.lib.m10v_isp_effects_encode(None, 0, out, 48), 0)
        self.assertEqual(self.lib.m10v_isp_effects_encode(C.byref(settings), 0, None, 48), 0)
        settings.reserved = 1
        self.assertEqual(self.lib.m10v_isp_effects_encode(C.byref(settings), 0, out, 48), 0)
        self.assertEqual(out.raw, b"X" * 49)
        for record, target, sequence in ((None, C.byref(settings), C.byref(seq)),
                (wire(), None, C.byref(seq)), (wire(), C.byref(settings), None)):
            self.assertEqual(self.lib.m10v_isp_effects_decode(record, 48, target, sequence), 0)

    def test_newest_selection_wraps_and_fails_closed_on_ambiguous_history(self):
        cases = [(wire(4), wire(5), 1, 5), (wire(5), wire(4), 0, 5),
                 (wire(0xFFFFFFFF), wire(0), 1, 0), (wire(0), wire(0xFFFFFFFF), 0, 0),
                 (wire(8), wire(8), 0, 8),
                 (wire(8), wire(8, (1, 0, 0, 0, 0, 0, 0, 0)), -1, 99),
                 (wire(0), wire(0x80000000), -1, 99),
                 (wire(1), b"broken", 0, 1), (b"broken", wire(2), 1, 2),
                 (b"broken", b"broken", -1, 99), (None, wire(2), 1, 2)]
        for a, b, expected, sequence in cases:
            settings = Settings(2)
            seq = C.c_uint32(99)
            result = self.lib.m10v_isp_effects_select_newest(a, len(a) if a else 0,
                b, len(b) if b else 0, C.byref(settings), C.byref(seq))
            self.assertEqual((result, seq.value), (expected, sequence))
            self.assertEqual(settings.leak_gain, 2 if expected == -1 else 0)
        self.assertEqual(self.lib.m10v_isp_effects_select_newest(wire(), 48, wire(), 48, None, None), -1)

    def test_snapshot_resolves_inherit_and_override_exactly_once(self):
        for mode in range(5):
            for slot in range(4):
                settings = Settings(3, 2, 1, mode, 2, 1, 2, 0)
                snap = Snapshot()
                self.assertEqual(self.lib.m10v_isp_effects_resolve_snapshot(C.byref(settings), slot, C.byref(snap)), 1)
                self.assertEqual(bytes(snap.settings), bytes(settings))
                self.assertEqual(snap.effective_grain_strength, slot if mode == 0 else mode - 1)

    def test_snapshot_rejects_invalid_metadata_without_publishing_partial_state(self):
        settings = Settings()
        snap = Snapshot(Settings(3), 77)
        before = bytes(snap)
        for slot in (4, 0xFFFFFFFF):
            self.assertEqual(self.lib.m10v_isp_effects_resolve_snapshot(C.byref(settings), slot, C.byref(snap)), 0)
            self.assertEqual(bytes(snap), before)
        settings.grain_mode = 5
        self.assertEqual(self.lib.m10v_isp_effects_resolve_snapshot(C.byref(settings), 0, C.byref(snap)), 0)
        self.assertEqual(bytes(snap), before)
        self.assertEqual(self.lib.m10v_isp_effects_resolve_snapshot(None, 0, C.byref(snap)), 0)
        self.assertEqual(self.lib.m10v_isp_effects_resolve_snapshot(C.byref(settings), 0, None), 0)


if __name__ == "__main__":
    unittest.main()
