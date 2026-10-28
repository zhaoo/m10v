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


class StorageHoles(C.Structure):
    _fields_ = [('first', Rect), ('dx', C.c_int32), ('dy', C.c_int32), ('count', C.c_uint32)]


class Storage(C.Structure):
    _fields_ = [('style', C.c_uint32), ('format', C.c_uint32), ('outer', Rect), ('inner', Rect),
                ('holes', StorageHoles * 2)] + [(n, C.c_uint32) for n in
                ('stride', 'allocated_height', 'y_bytes', 'chroma_bytes', 'total_bytes')]


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

    def test_border_margins_preserve_native_jpeg_eight_byte_start_alignment(self):
        for width,height in ((6000,1656),(6000,2248),(4672,4000),(1488,1280)):
            for style in (1,2):
                r=self.make(style,width,height)
                for margin in (r.inner.x,r.inner.y,r.outer.width-width-r.inner.x,
                               r.outer.height-height-r.inner.y):
                    self.assertEqual(margin%8,0)
        r=self.make(1,6000,1656)
        self.assertEqual((r.inner.x,r.inner.y),(72,72))

    def test_film_holes_are_symmetric_bounded_and_never_touch_photo(self):
        for width, height in ((6000, 4000), (4000, 6000), (6000, 1656), (1656, 6000), (2, 2), (2, 65534)):
            result = self.make(2, width, height)
            top, bottom = result.holes
            self.assertEqual(top.count, bottom.count)
            self.assertGreaterEqual(top.count, 1)
            self.assertLessEqual(top.count, 60)
            self.assertEqual(bottom.first.x, top.first.x)
            self.assertEqual(bottom.first.y, result.outer.height - top.first.y - top.first.height)
            for side, band in enumerate(result.holes):
                hole = band.first
                self.assertEqual((hole.x | hole.y | hole.width | hole.height | band.pitch) & 1, 0)
                self.assertGreaterEqual(hole.width, 2)
                self.assertGreaterEqual(hole.height, 2)
                self.assertGreaterEqual(band.pitch, hole.width + 2)
                self.assertLessEqual(hole.x + (band.count - 1) * band.pitch + hole.width, result.outer.width)
                if side == 0:
                    self.assertLessEqual(hole.y + hole.height, result.inner.y)
                else:
                    self.assertGreaterEqual(hole.y, result.inner.y + height)

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

    def storage(self, style, width, height, orientation, fmt=1):
        fn = self.lib.m10v_border_storage_layout
        fn.argtypes = [C.c_uint32] * 5 + [C.POINTER(Storage)]
        fn.restype = C.c_int
        result = Storage()
        self.assertEqual(fn(style, width, height, orientation, fmt, C.byref(result)), 0)
        return result

    def test_storage_plan_all_eight_exif_orientations_preserve_inner_pixels(self):
        # The larger Polaroid margin follows DISPLAY bottom. Source pixels
        # retain their storage order and source EXIF; no CPU rotation is used.
        for orientation in range(1, 9):
            r = self.storage(1, 6000, 4000, orientation)
            self.assertEqual((r.inner.width, r.inner.height), (6000, 4000))
            margins = (r.inner.x, r.inner.y, r.outer.width - r.inner.x - 6000,
                       r.outer.height - r.inner.y - 4000)
            bottom_side = {1: 3, 2: 3, 3: 1, 4: 1, 5: 2, 6: 2, 7: 0, 8: 0}[orientation]
            self.assertEqual(margins[bottom_side], 480)
            self.assertEqual(sorted(margins), [160, 160, 160, 480])

    def test_storage_plan_covers_aligned_full_canvas_and_padding_without_scaling(self):
        for width, height in ((6000, 4000), (6000, 1656), (4672, 4000), (1488, 1280)):
            for orientation in range(1, 9):
                for fmt in (1, 2):
                    r = self.storage(2, width, height, orientation, fmt)
                    self.assertEqual((r.inner.width, r.inner.height), (width, height))
                    self.assertGreaterEqual(r.stride, r.outer.width)
                    self.assertEqual(r.stride % 64, 0)
                    self.assertLess(r.stride - r.outer.width, 64)
                    self.assertGreaterEqual(r.allocated_height, r.outer.height)
                    self.assertEqual(r.allocated_height % 8, 0)
                    self.assertEqual(r.y_bytes, r.stride * r.allocated_height)
                    self.assertEqual(r.chroma_bytes, r.y_bytes // (2 if fmt == 2 else 1))
                    self.assertEqual(r.total_bytes, r.y_bytes + r.chroma_bytes)
                    for band in r.holes:
                        for i in range(band.count):
                            x, y = band.first.x + i * band.dx, band.first.y + i * band.dy
                            self.assertGreaterEqual(min(x, y), 0)
                            self.assertLessEqual(x + band.first.width, r.outer.width)
                            self.assertLessEqual(y + band.first.height, r.outer.height)
                            self.assertTrue(x + band.first.width <= r.inner.x or x >= r.inner.x + width or
                                            y + band.first.height <= r.inner.y or y >= r.inner.y + height)

    def test_storage_off_needs_no_canvas_and_rejects_unrepresentable_outputs(self):
        r = self.storage(0, 6000, 4000, 6)
        self.assertEqual((r.outer.width, r.outer.height), (6000, 4000))
        self.assertEqual((r.stride, r.allocated_height, r.total_bytes), (0, 0, 0))
        fn = self.lib.m10v_border_storage_layout
        for args in ((1, 6000, 4000, 0, 1), (1, 6000, 4000, 9, 1),
                     (1, 6000, 4000, 1, 3), (1, 16384, 16384, 1, 1)):
            r = Storage()
            C.memset(C.byref(r), 0xa5, C.sizeof(r))
            before = bytes(r)
            self.assertEqual(fn(*args, C.byref(r)), -1)
            self.assertEqual(bytes(r), before)

    def test_preview_fits_existing_native_box_for_all_crop_and_orientation_shapes(self):
        fit=self.lib.m10v_border_preview_fit
        fit.argtypes=[C.c_uint32]*4+[C.POINTER(Rect)];fit.restype=C.c_int
        for w,h in ((6000,4000),(6000,1656),(4672,4000),(1488,1280)):
            for style in (1,2):
                for orientation in range(1,9):
                    canvas=self.storage(style,w,h,orientation).outer
                    for bw,bh in ((720,480),(720,198),(160,120),(160,44)):
                        r=Rect()
                        self.assertEqual(fit(canvas.width,canvas.height,bw,bh,C.byref(r)),0)
                        self.assertEqual((r.x,r.y),(0,0))
                        self.assertLessEqual(r.width,bw);self.assertLessEqual(r.height,bh)
                        self.assertEqual((r.width|r.height)&1,0)
                        # Ratio error is strictly less than one2-pixel step;
                        # the scaler receives the WHOLE canvas, no crop ROI.
                        error=abs(r.width*canvas.height-r.height*canvas.width)
                        self.assertLess(error,2*max(canvas.width,canvas.height))
                        self.assertTrue(r.width>=bw-8 or r.height>=bh-8)
        r=Rect();self.assertEqual(fit(6320,4640,720,480,C.byref(r)),0)
        self.assertEqual((r.width,r.height),(652,480))
        self.assertEqual(fit(6320,4640,160,120,C.byref(r)),0)
        self.assertEqual((r.width,r.height),(158,116))
        self.assertEqual(fit(6480,4480,160,120,C.byref(r)),0)
        self.assertEqual((r.width,r.height),(156,108))

    def test_preview_rejects_impossible_chroma_box_without_mutating_output(self):
        fit=self.lib.m10v_border_preview_fit
        fit.argtypes=[C.c_uint32]*4+[C.POINTER(Rect)];fit.restype=C.c_int
        for args in ((0,4000,720,480),(6001,4000,720,480),(6000,4000,719,480),
                     (16386,4000,720,480),(16384,2,2,2)):
            r=Rect();C.memset(C.byref(r),0xa5,C.sizeof(r));before=bytes(r)
            self.assertEqual(fit(*args,C.byref(r)),-1)
            self.assertEqual(bytes(r),before)


if __name__ == '__main__':
    unittest.main()
