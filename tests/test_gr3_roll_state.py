"""Host tests for the camera roll journal and the M10R photo marker."""
import ctypes as c
import pathlib
import subprocess
import tempfile
import unittest
import zlib


ROOT = pathlib.Path(__file__).resolve().parents[1]


class Record(c.Structure):
    _fields_ = [
        ("magic", c.c_uint32), ("sequence", c.c_uint32),
        ("id", c.c_uint8 * 16), ("film", c.c_uint32),
        ("aspect", c.c_uint32), ("target", c.c_uint32),
        ("count", c.c_uint32), ("status", c.c_uint32),
        ("crc", c.c_uint32),
    ]


ReadRecord = c.CFUNCTYPE(c.c_int, c.c_void_p, c.c_uint32, c.POINTER(Record))
WriteRecord = c.CFUNCTYPE(c.c_int, c.c_void_p, c.c_uint32, c.POINTER(Record))


class Journal(c.Structure):
    _fields_ = [("context", c.c_void_p), ("read", ReadRecord), ("write", WriteRecord)]


ProbeSaved = c.CFUNCTYPE(c.c_int, c.c_void_p, c.POINTER(c.c_uint8))


class SavedProbe(c.Structure):
    _fields_ = [("context", c.c_void_p), ("find", ProbeSaved)]


class Owner(c.Structure):
    _fields_ = [
        ("journal", Journal), ("probe", SavedProbe), ("current", Record),
        ("marker", c.c_uint8 * 32), ("loaded", c.c_int), ("armed", c.c_int),
        ("reservation", c.c_uint32),
    ]


class FilmRollTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = tempfile.TemporaryDirectory(prefix="m10v-roll-test-")
        cls.addClassCleanup(cls.scratch.cleanup)
        output = pathlib.Path(cls.scratch.name) / "roll.so"
        native = ROOT / "native/gr3"
        subprocess.run([
            "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
            str(native / "m10v_roll.c"), str(native / "m10v_roll_owner.c"), "-o", str(output),
        ], check=True)
        cls.lib = c.CDLL(str(output))
        cls.lib.m10v_roll_open.argtypes = [
            c.POINTER(Record), c.POINTER(Record), c.POINTER(c.c_uint8),
            c.c_uint32, c.c_uint32, c.c_uint32,
        ]
        cls.lib.m10v_roll_change.argtypes = [c.POINTER(Record), c.POINTER(Record), c.c_uint32]
        cls.lib.m10v_roll_complete.argtypes = [c.POINTER(Record), c.POINTER(Record), c.c_uint32]
        cls.lib.m10v_roll_latest.argtypes = [c.POINTER(Record), c.POINTER(Record)]
        cls.lib.m10v_roll_marker.argtypes = [c.POINTER(Record), c.c_uint32, c.POINTER(c.c_uint8)]
        cls.lib.m10v_roll_load.argtypes = [c.POINTER(Journal), c.POINTER(Record)]
        cls.lib.m10v_roll_store.argtypes = [c.POINTER(Journal), c.POINTER(Record), c.POINTER(Record)]
        cls.lib.m10v_roll_apply_saved.argtypes = [
            c.POINTER(Journal), c.POINTER(c.c_uint8), c.c_uint32,
        ]
        cls.lib.m10v_roll_reconcile.argtypes = [
            c.POINTER(Journal), c.POINTER(SavedProbe), c.POINTER(Record),
        ]
        cls.lib.m10v_roll_owner_init.argtypes = [
            c.POINTER(Owner), c.POINTER(Journal), c.POINTER(SavedProbe),
        ]
        cls.lib.m10v_roll_owner_init.restype = None
        cls.lib.m10v_roll_owner_recover.argtypes = [c.POINTER(Owner)]
        cls.lib.m10v_roll_owner_snapshot.argtypes = [c.POINTER(Owner), c.POINTER(Record)]
        cls.lib.m10v_roll_owner_change.argtypes = [c.POINTER(Owner), c.c_uint32]
        cls.lib.m10v_roll_owner_arm.argtypes = [c.POINTER(Owner), c.POINTER(c.c_uint8)]
        cls.lib.m10v_roll_owner_arm.restype = c.c_uint32
        cls.lib.m10v_roll_owner_finish.argtypes = [
            c.POINTER(Owner), c.c_uint32, c.POINTER(c.c_uint8), c.c_int32,
        ]

    @staticmethod
    def journal():
        pages = {}
        writes = []
        write_ok = [True]

        @ReadRecord
        def read(_context, page, out):
            if page not in pages:
                return 0
            c.memmove(out, pages[page], c.sizeof(Record))
            return 1

        @WriteRecord
        def write(_context, page, record):
            writes.append(record.contents.sequence)
            if not write_ok[0]:
                return 0
            pages[page] = bytes(record.contents)
            return 1

        return Journal(None, read, write), writes, write_ok

    def marker(self, rec):
        marker = (c.c_uint8 * 32)()
        self.assertTrue(
            self.lib.m10v_roll_marker(c.byref(rec), rec.count + 1, marker)
        )
        return marker

    def test_successful_original_advances_once_even_if_the_pair_arrives_late(self):
        io, writes, _ = self.journal()
        first = self.open()
        marker = self.marker(first)
        self.assertEqual(self.lib.m10v_roll_store(c.byref(io), None, c.byref(first)), 1)
        self.assertEqual(self.lib.m10v_roll_apply_saved(c.byref(io), marker, 0), 0)
        self.assertEqual(self.lib.m10v_roll_apply_saved(c.byref(io), marker, 4), 0)
        wrong = self.marker(self.open(number=2))
        self.assertEqual(self.lib.m10v_roll_apply_saved(c.byref(io), wrong, 1), 0)
        bad_crc = (c.c_uint8 * 32).from_buffer_copy(bytes(marker))
        bad_crc[28] ^= 0xff
        self.assertEqual(self.lib.m10v_roll_apply_saved(c.byref(io), bad_crc, 1), 0)
        self.assertEqual(self.lib.m10v_roll_apply_saved(c.byref(io), marker, 1), 1)
        self.assertEqual(self.lib.m10v_roll_apply_saved(c.byref(io), marker, 2), 1)
        current = Record()
        self.assertEqual(self.lib.m10v_roll_load(c.byref(io), c.byref(current)), 1)
        self.assertEqual(current.count, 1)
        self.assertEqual(writes, [1, 2])

    def test_reopen_recovers_only_verified_originals_after_an_interrupted_commit(self):
        io, writes, write_ok = self.journal()
        first, current = self.open(), Record()
        wanted = bytes(self.marker(first))
        self.assertEqual(self.lib.m10v_roll_store(c.byref(io), None, c.byref(first)), 1)
        write_ok[0] = False
        marker = (c.c_uint8 * 32).from_buffer_copy(wanted)
        self.assertEqual(self.lib.m10v_roll_apply_saved(c.byref(io), marker, 3), -1)
        write_ok[0] = True
        observed = []

        @ProbeSaved
        def find(_context, candidate):
            marker = c.string_at(candidate, 32)
            observed.append(marker)
            return int(marker == wanted)

        probe = SavedProbe(None, find)
        self.assertEqual(self.lib.m10v_roll_reconcile(
            c.byref(io), c.byref(probe), c.byref(current)), 1)
        self.assertEqual(current.count, 1)
        self.assertEqual(bytes(current.id), bytes(first.id))
        self.assertEqual([int.from_bytes(v[20:24], "little") for v in observed], [1, 2])
        self.assertEqual(writes, [1, 2, 2])

    def test_unverifiable_original_does_not_authorize_reusing_its_frame(self):
        io, writes, _ = self.journal()
        first, result = self.open(), Record()
        self.assertEqual(self.lib.m10v_roll_store(c.byref(io), None, c.byref(first)), 1)

        @ProbeSaved
        def unavailable(_context, _marker):
            return -1

        probe = SavedProbe(None, unavailable)
        self.assertEqual(self.lib.m10v_roll_reconcile(
            c.byref(io), c.byref(probe), c.byref(result)), -1)
        self.assertEqual(result.sequence, 0)
        self.assertEqual(writes, [1])

    def test_owner_keeps_frame_frozen_and_blocks_rearm_until_save_outcome_resolved(self):
        io, writes, write_ok = self.journal()
        first, current, owner = self.open(), Record(), Owner()
        present = set()

        @ProbeSaved
        def find(_context, candidate):
            return int(c.string_at(candidate, 32) in present)

        probe = SavedProbe(None, find)
        self.assertEqual(self.lib.m10v_roll_store(c.byref(io), None, c.byref(first)), 1)
        self.lib.m10v_roll_owner_init(c.byref(owner), c.byref(io), c.byref(probe))
        self.assertEqual(self.lib.m10v_roll_owner_recover(c.byref(owner)), 1)
        marker, following = (c.c_uint8 * 32)(), (c.c_uint8 * 32)()
        ticket = self.lib.m10v_roll_owner_arm(c.byref(owner), marker)
        self.assertEqual(ticket, 1)
        self.assertEqual(self.lib.m10v_roll_owner_arm(c.byref(owner), following), 0)
        self.assertEqual(self.lib.m10v_roll_owner_change(c.byref(owner), 2), 0)
        self.assertEqual(self.lib.m10v_roll_owner_recover(c.byref(owner)), -1)
        self.assertEqual(self.lib.m10v_roll_owner_finish(c.byref(owner), ticket, marker, 0), 1)
        retry = self.lib.m10v_roll_owner_arm(c.byref(owner), following)
        self.assertEqual(retry, 2)
        self.assertEqual(bytes(marker), bytes(following))
        self.assertEqual(self.lib.m10v_roll_owner_finish(c.byref(owner), ticket, marker, 1), 0)

        write_ok[0] = False
        present.add(bytes(following))
        self.assertEqual(self.lib.m10v_roll_owner_finish(c.byref(owner), retry, following, 2), -1)
        self.assertEqual(self.lib.m10v_roll_owner_arm(c.byref(owner), following), 0)
        self.assertEqual(self.lib.m10v_roll_owner_snapshot(c.byref(owner), c.byref(current)), -1)
        write_ok[0] = True
        self.assertEqual(self.lib.m10v_roll_owner_recover(c.byref(owner)), 1)
        self.assertEqual(self.lib.m10v_roll_owner_snapshot(c.byref(owner), c.byref(current)), 1)
        self.assertEqual(current.count, 1)
        self.assertEqual(self.lib.m10v_roll_owner_arm(c.byref(owner), following), 3)
        self.assertEqual(int.from_bytes(bytes(following[20:24]), "little"), 2)
        self.assertEqual(writes, [1, 2, 2])

    def open(self, old=None, number=1, target=24):
        rec = Record()
        uuid = (c.c_uint8 * 16)(number, *range(1, 16))
        self.assertTrue(self.lib.m10v_roll_open(old, c.byref(rec), uuid, 33, 0, target))
        return rec

    def test_pause_resume_and_journal_fallback(self):
        active = self.open()
        paused, resumed = Record(), Record()
        self.assertTrue(self.lib.m10v_roll_complete(c.byref(active), c.byref(paused), 1))
        self.assertTrue(self.lib.m10v_roll_change(c.byref(paused), c.byref(paused), 2))
        marker = (c.c_uint8 * 32)()
        self.assertFalse(self.lib.m10v_roll_marker(c.byref(paused), 2, marker))
        self.assertTrue(self.lib.m10v_roll_change(c.byref(paused), c.byref(resumed), 1))
        self.assertEqual(resumed.count, 1)
        self.assertEqual(bytes(resumed.id), bytes(active.id))
        self.assertEqual(self.lib.m10v_roll_latest(c.byref(paused), c.byref(resumed)), 1)
        resumed.crc ^= 1
        self.assertEqual(self.lib.m10v_roll_latest(c.byref(paused), c.byref(resumed)), 0)

    def test_marker_is_byte_exact_and_capacity_closes_roll(self):
        rec = self.open()
        marker = (c.c_uint8 * 32)()
        self.assertFalse(self.lib.m10v_roll_marker(c.byref(rec), 2, marker))
        for frame in range(1, 25):
            self.assertTrue(self.lib.m10v_roll_marker(c.byref(rec), frame, marker))
            self.assertEqual(bytes(marker[:4]), b"M10R")
            self.assertEqual(bytes(marker[4:20]), bytes(rec.id))
            self.assertEqual(int.from_bytes(bytes(marker[20:24]), "little"), frame)
            self.assertEqual(int.from_bytes(bytes(marker[24:28]), "little"), 24)
            self.assertEqual(int.from_bytes(bytes(marker[28:32]), "little"), zlib.crc32(bytes(marker[:28])))
            self.assertTrue(self.lib.m10v_roll_complete(c.byref(rec), c.byref(rec), frame))
        self.assertEqual(rec.status, 3)
        self.assertFalse(self.lib.m10v_roll_complete(c.byref(rec), c.byref(rec), 25))
        following = self.open(c.byref(rec), number=2, target=36)
        self.assertEqual(following.sequence, rec.sequence + 1)
        self.assertNotEqual(bytes(following.id), bytes(rec.id))

    def test_no_reopen_of_an_active_or_closed_identity(self):
        first = self.open()
        next_roll = Record()
        self.assertFalse(self.lib.m10v_roll_open(c.byref(first), c.byref(next_roll), first.id, 33, 0, 36))
        self.assertTrue(self.lib.m10v_roll_change(c.byref(first), c.byref(next_roll), 3))
        self.assertFalse(self.lib.m10v_roll_open(c.byref(next_roll), c.byref(next_roll), next_roll.id, 33, 0, 36))
        self.assertFalse(self.lib.m10v_roll_change(c.byref(next_roll), c.byref(next_roll), 1))


    def test_journal_survives_torn_write_and_rejects_stale_progress(self):
        pages = {}
        unavailable = set()
        corrupt_next_write = False

        @ReadRecord
        def read(_context, page, out):
            if page in unavailable:
                return -1
            if page not in pages:
                return 0
            c.memmove(out, pages[page], c.sizeof(Record))
            return 1

        @WriteRecord
        def write(_context, page, record):
            blob = bytes(record.contents)
            pages[page] = blob[:32] + bytes(16) if corrupt_next_write else blob
            return 1

        io = Journal(None, read, write)
        live, next_state, loaded = self.open(), Record(), Record()
        self.assertEqual(self.lib.m10v_roll_load(c.byref(io), c.byref(loaded)), 0)
        self.assertTrue(self.lib.m10v_roll_store(c.byref(io), None, c.byref(live)))
        self.assertTrue(self.lib.m10v_roll_complete(c.byref(live), c.byref(next_state), 1))
        corrupt_next_write = True
        self.assertFalse(self.lib.m10v_roll_store(c.byref(io), c.byref(live), c.byref(next_state)))
        self.assertEqual(self.lib.m10v_roll_load(c.byref(io), c.byref(loaded)), 1)
        self.assertEqual(loaded.count, 0)
        corrupt_next_write = False
        self.assertTrue(self.lib.m10v_roll_store(c.byref(io), c.byref(live), c.byref(next_state)))
        self.assertFalse(self.lib.m10v_roll_store(c.byref(io), c.byref(live), c.byref(next_state)))
        self.assertEqual(self.lib.m10v_roll_load(c.byref(io), c.byref(loaded)), 1)
        self.assertEqual(loaded.count, 1)
        unavailable.add(0)
        self.assertEqual(self.lib.m10v_roll_load(c.byref(io), c.byref(loaded)), -1)
