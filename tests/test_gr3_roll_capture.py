"""Test the single-reservation handoff between AppMain and the GR III writer."""

import ctypes
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
U32 = ctypes.c_uint32
I32 = ctypes.c_int32
Marker = ctypes.c_uint8 * 32


class Channel(ctypes.Structure):
    _fields_ = [(name, U32) for name in (
        "state", "ticket", "si", "generation", "group", "writer", "reached", "marked",
    )] + [("marker", Marker), ("result", I32), ("save", U32 * 8),
          ("settings", U32 * 3), ("diagnostic", U32 * 7)]


class CaptureChannelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = tempfile.TemporaryDirectory(prefix="m10v-roll-capture-")
        cls.addClassCleanup(scratch.cleanup)
        output = Path(scratch.name) / "roll_capture.so"
        lib = ROOT / "native/gr3/m10v_roll_capture.c"
        if not lib.is_file():
            return
        subprocess.run([
            os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
            "-shared", "-fPIC", str(lib), "-o", str(output),
        ], check=True)
        cls.lib = ctypes.CDLL(str(output))
        state = ctypes.POINTER(Channel)
        cls.lib.m10v_roll_capture_arm.argtypes = [state, U32, ctypes.POINTER(ctypes.c_uint8), U32, U32, U32]
        cls.lib.m10v_roll_capture_revoke.argtypes = [state, U32]
        cls.lib.m10v_roll_capture_reserve.argtypes = [state, U32, U32, U32, U32, U32]
        cls.lib.m10v_roll_capture_copy_marker.argtypes = [state, U32, U32, ctypes.POINTER(ctypes.c_uint8)]
        cls.lib.m10v_roll_capture_complete.argtypes = [state, U32, U32, I32]
        cls.lib.m10v_roll_capture_take_result.argtypes = [
            state, ctypes.POINTER(U32), ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(I32),
        ]

    def setUp(self):
        self.assertTrue(hasattr(self, "lib"), "capture bridge must exist")
        self.channel = Channel()
        self.at = ctypes.byref(self.channel)
        self.marker = Marker(*range(32))
        self.result = I32()
        self.ticket = U32()
        self.copied = Marker()

    def arm(self, ticket):
        return self.lib.m10v_roll_capture_arm(self.at, ticket, self.marker, 25, 4, 37)

    def reserve(self, si=0x55100000, generation=8, tone=25, aspect=4, film=37):
        return self.lib.m10v_roll_capture_reserve(self.at, si, generation, tone, aspect, film)

    def test_claim_prevents_revoke_and_preserves_exact_marker(self):
        self.assertTrue(self.arm(1))
        self.assertTrue(self.reserve())
        self.assertFalse(self.reserve(si=0x55200000, generation=9))
        self.assertFalse(self.lib.m10v_roll_capture_revoke(self.at, 1))
        self.assertFalse(self.lib.m10v_roll_capture_copy_marker(self.at, 0x55100000, 9, self.copied))
        self.assertTrue(self.lib.m10v_roll_capture_copy_marker(self.at, 0x55100000, 8, self.copied))
        self.assertEqual(bytes(self.copied), bytes(self.marker))

    def test_receipt_is_consumed_once_and_rejects_foreign_identity(self):
        self.assertTrue(self.arm(42))
        self.assertTrue(self.reserve())
        self.assertFalse(self.lib.m10v_roll_capture_complete(self.at, 0x55100000, 9, 1))
        self.assertTrue(self.lib.m10v_roll_capture_complete(self.at, 0x55100000, 8, 3))
        self.assertFalse(self.arm(43))
        take = self.lib.m10v_roll_capture_take_result
        self.assertTrue(take(self.at, ctypes.byref(self.ticket), self.copied, ctypes.byref(self.result)))
        self.assertEqual((self.ticket.value, self.result.value, bytes(self.copied)), (42, 3, bytes(self.marker)))
        self.assertFalse(take(self.at, ctypes.byref(self.ticket), self.copied, ctypes.byref(self.result)))

    def test_revoke_before_exposure_cannot_cancel_another_ticket(self):
        self.assertTrue(self.arm(8))
        self.assertFalse(self.lib.m10v_roll_capture_revoke(self.at, 9))
        self.assertTrue(self.lib.m10v_roll_capture_revoke(self.at, 8))
        self.assertFalse(self.reserve())
        self.assertTrue(self.arm(9))

    def test_late_setting_changes_leave_marker_armed_for_the_correct_photo(self):
        self.assertTrue(self.arm(7))
        self.assertFalse(self.reserve(tone=22))
        self.assertFalse(self.reserve(aspect=0))
        self.assertFalse(self.reserve(film=33))
        self.assertTrue(self.reserve())


if __name__ == "__main__":
    unittest.main()
