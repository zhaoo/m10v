"""Shared display-oriented border geometry; no image memory or hardware."""
import ctypes as C
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Rect(C.Structure):
    _fields_ = [(n, C.c_uint32) for n in ('x', 'y', 'width', 'height')]


class Holes(C.Structure):
    _fields_ = [('first', Rect), ('pitch', C.c_uint32), ('count', C.c_uint32)]


class Layout(C.Structure):
    _fields_ = [('style', C.c_uint32), ('outer', Rect), ('inner', Rect), ('holes', Holes * 2)]


class BorderGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        lib = Path(cls.tmp.name) / 'border.dylib'
        subprocess.run([shutil.which('clang'), '-shared', '-fPIC', '-O2', '-Wall', '-Wextra', '-Werror',
                        str(ROOT / 'native/gr3/m10v_border.c'), '-o', str(lib)], check=True, capture_output=True)
        cls.lib = C.CDLL(str(lib))
        cls.layout = cls.lib.m10v_border_layout
        cls.layout.argtypes = [C.c_uint32] * 3 + [C.POINTER(Layout)]
        cls.layout.restype = C.c_int

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def make(self, style, width, height):
        result = Layout()
        self.assertEqual(self.layout(style, width, height, C.byref(result)), 0)
        self.assertEqual((result.inner.width, result.inner.height), (width, height))
        self.assertEqual((result.outer.x, result.outer.y), (0, 0))
        return result

    def test_off_preserves_exact_full_crop_and_has_no_border_work(self):
        for width, height in ((6000, 4000), (6000, 1656), (4672, 4000), (2, 2)):
            result = self.make(0, width, height)
            self.assertEqual((result.outer.width, result.outer.height), (width, height))
            self.assertEqual((result.inner.x, result.inner.y), (0, 0))
            self.assertEqual([band.count for band in result.holes], [0, 0])

    def test_polaroid_preserves_pixels_with_three_times_bottom_margin(self):
        for width, height, expected in ((6000, 4000, (6320, 4640)),
                                        (4000, 6000, (4320, 6640))):
            result = self.make(1, width, height)
            self.assertEqual((result.outer.width, result.outer.height), expected)
            self.assertEqual((result.inner.x, result.inner.y), (160, 160))
            self.assertEqual(result.outer.height - result.inner.y - height, 480)
            self.assertEqual([band.count for band in result.holes], [0, 0])

    def test_all_existing_crop_shapes_and_sizes_stay_intact(self):
        for width, height in ((6000, 4000), (4000, 4000), (5328, 4000), (6000, 1656),
                              (4672, 4000), (3728, 3200), (2608, 2240), (1488, 1280),
                              (4800, 3200), (3360, 2240), (1920, 1280), (160, 120), (2, 2)):
            for w, h in ((width, height), (height, width)):
                for style in (1, 2):
                    with self.subTest(size=(w, h), style=style):
                        result = self.make(style, w, h)
                        self.assertGreater(result.outer.width, w)
                        self.assertGreater(result.outer.height, h)
                        self.assertEqual((result.inner.x | result.inner.y | result.outer.width | result.outer.height) & 1, 0)

    def test_film_holes_are_symmetric_bounded_and_never_touch_photo(self):
        for width, height in ((6000, 4000), (4000, 6000), (6000, 1656), (1656, 6000), (2, 2), (2, 65534)):
            result = self.make(2, width, height)
            left, right = result.holes
            self.assertEqual(left.count, right.count)
            self.assertGreaterEqual(left.count, 1)
            self.assertLessEqual(left.count, 64)
            self.assertEqual(right.first.x, result.outer.width - left.first.x - left.first.width)
            for side, band in enumerate(result.holes):
                hole = band.first
                self.assertEqual((hole.x | hole.y | hole.width | hole.height | band.pitch) & 1, 0)
                self.assertGreaterEqual(hole.width, 2)
                self.assertGreaterEqual(hole.height, 2)
                self.assertGreaterEqual(band.pitch, hole.height + 2)
                self.assertLessEqual(hole.y + (band.count - 1) * band.pitch + hole.height, result.outer.height)
                if side == 0:
                    self.assertLessEqual(hole.x + hole.width, result.inner.x)
                else:
                    self.assertGreaterEqual(hole.x, result.inner.x + width)

    def test_invalid_inputs_and_null_output_reject_without_mutation(self):
        for style, width, height in ((3, 6000, 4000), (1, 0, 4000), (1, 6001, 4000),
                                    (1, 6000, 4001), (1, 65536, 4000), (1, 2**32 - 1, 2)):
            result = Layout()
            C.memset(C.byref(result), 0xa5, C.sizeof(result))
            before = bytes(result)
            self.assertEqual(self.layout(style, width, height, C.byref(result)), -1)
            self.assertEqual(bytes(result), before)
        self.assertEqual(self.layout(1, 6000, 4000, None), -1)

    def test_arm_module_links_without_runtime_helpers(self):
        obj = Path(self.tmp.name) / 'border-arm.o'
        elf = Path(self.tmp.name) / 'border-arm.elf'
        subprocess.run([shutil.which('clang'), '--target=armv7-none-eabi', '-mcpu=cortex-a9',
                        '-marm', '-mfloat-abi=soft', '-O2', '-ffreestanding', '-fno-builtin',
                        '-fno-stack-protector', '-fno-unwind-tables', '-fno-asynchronous-unwind-tables',
                        '-Wall', '-Wextra', '-Werror', '-c', str(ROOT / 'native/gr3/m10v_border.c'),
                        '-o', str(obj)], check=True, capture_output=True)
        result = subprocess.run([shutil.which('ld.lld'), '-Ttext=0x54160000',
                                 '--entry=m10v_border_layout', str(obj), '-o', str(elf)],
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
