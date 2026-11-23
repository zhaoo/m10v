"""Check the GR III still-file result adapter without camera, storage, or a firmware build."""

import ctypes
import itertools
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
U32 = ctypes.c_uint32
GROUP = 0x55100000
SI = 0x55200000
JPEG = GROUP + 0x14
DNG = GROUP + 0x1178
GROUP_DONE = 0x00800001


class Save(ctypes.Structure):
    _fields_ = [(name, U32) for name in (
        "ticket", "group", "si", "stream", "expected", "seen", "succeeded", "conflicts",
    )]


class RollSaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = tempfile.TemporaryDirectory(prefix="m10v-roll-save-")
        cls.addClassCleanup(cls.scratch.cleanup)
        output = pathlib.Path(cls.scratch.name) / "roll_save.so"
        source = ROOT / "native/gr3/m10v_roll_save.c"
        if not source.is_file():
            raise AssertionError("The roll save bridge is missing")
        subprocess.run([
            "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
            str(source), "-o", str(output),
        ], check=True)
        cls.lib = ctypes.CDLL(str(output))
        state = ctypes.POINTER(Save)
        cls.lib.m10v_roll_save_begin.argtypes = [state, U32, U32, U32, U32, U32]
        cls.lib.m10v_roll_save_output.argtypes = [state, U32, U32, U32, U32, U32, U32]
        cls.lib.m10v_roll_save_end.argtypes = [state, U32, U32, U32]

    def begin(self, expected=3, stream=0, ticket=7):
        state = Save()
        self.assertEqual(self.lib.m10v_roll_save_begin(
            ctypes.byref(state), ticket, GROUP, SI, stream, expected,
        ), 1)
        return state

    def output(self, state, descriptor, phases=1, ok=1, ticket=7, group=GROUP, si=SI):
        return self.lib.m10v_roll_save_output(
            ctypes.byref(state), ticket, group, descriptor, si, phases, ok,
        )

    def end(self, state, ticket=7, group=GROUP, event=GROUP_DONE):
        return self.lib.m10v_roll_save_end(ctypes.byref(state), ticket, group, event)

    def test_either_completion_order_reports_each_confirmed_original(self):
        for jpg, dng, reversed_order in itertools.product((0, 1), repeat=3):
            with self.subTest(jpg=jpg, dng=dng, reversed_order=reversed_order):
                state = self.begin()
                outputs = [(JPEG, jpg), (DNG, dng)]
                for descriptor, ok in reversed(outputs) if reversed_order else outputs:
                    self.assertEqual(self.output(state, descriptor, ok=ok), 1)
                self.assertEqual(self.end(state), jpg | (dng << 1))
                self.assertEqual(self.end(state), -2)

    def test_stock_true_return_before_data_and_close_does_not_count(self):
        state = self.begin(expected=1)
        self.assertEqual(self.output(state, JPEG, phases=0), 1)
        self.assertEqual(self.end(state), 0)

    def test_missing_result_and_conflicting_duplicate_require_reconciliation(self):
        state = self.begin()
        self.assertEqual(self.output(state, JPEG, ok=0), 1)
        self.assertEqual(self.end(state), -1)
        state = self.begin(expected=1)
        self.assertEqual(self.output(state, JPEG), 1)
        self.assertEqual(self.output(state, JPEG, ok=0), 1)
        self.assertEqual(self.end(state), -1)

    def test_unrelated_callbacks_do_not_change_the_active_capture(self):
        state = self.begin(expected=2, stream=2)
        self.assertEqual(self.lib.m10v_roll_save_begin(
            ctypes.byref(state), 8, GROUP, SI, 2, 2,
        ), 0)
        self.assertEqual(self.end(state, event=0x00800007), -2)
        self.assertEqual(self.end(state, ticket=6), -2)
        self.assertEqual(self.end(state, group=GROUP + 4), -2)
        self.assertEqual(self.output(state, DNG, ok=0), 0)
        self.assertEqual(self.output(state, GROUP + 0x1D10, ticket=6, ok=0), 0)
        self.assertEqual(self.output(state, GROUP + 0x1D10, group=GROUP + 4), 0)
        self.assertEqual(self.output(state, GROUP + 0x1D10, si=SI + 4, ok=0), 0)
        self.assertEqual(self.output(state, GROUP + 0xBAC, ok=0), 0)
        self.assertEqual(self.output(state, GROUP + 0x1D10, phases=2), 0)
        self.assertEqual(self.output(state, GROUP + 0x1D10), 1)
        self.assertEqual(self.end(state), 2)

    def test_reusing_a_group_does_not_inherit_the_previous_output(self):
        state = self.begin(expected=1)
        self.assertEqual(self.output(state, JPEG), 1)
        self.assertEqual(self.end(state), 1)
        self.assertEqual(self.lib.m10v_roll_save_begin(
            ctypes.byref(state), 8, GROUP, SI, 0, 1,
        ), 1)
        self.assertEqual(self.output(state, JPEG), 0)
        self.assertEqual(self.end(state, ticket=8), -1)


if __name__ == "__main__":
    unittest.main()
