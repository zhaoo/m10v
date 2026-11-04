"""Compile the camera's guide renderer and inspect its RGBA writes."""
import ctypes as C
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from unicorn import UC_ARCH_ARM, UC_MODE_ARM, Uc
from unicorn import arm_const as A

from scripts.build_gr3_m10v_library import FLAGS

ROOT = Path(__file__).resolve().parents[1]
EMPTY = 0x13050709
GUIDE = 0x80000000


class Rect(C.Structure):
    _fields_ = [(name, C.c_uint32) for name in ("left", "top", "right", "bottom")]


class Surface(C.Structure):
    _fields_ = [
        ("pixels", C.POINTER(C.c_uint32)),
        ("capacity_pixels", C.c_uint32),
        ("stride_pixels", C.c_uint32),
        ("width", C.c_uint32),
        ("height", C.c_uint32),
        ("photo", Rect),
        ("clip", Rect),
    ]


class GuidesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(folder.cleanup)
        library = Path(folder.name) / "guides.so"
        result = subprocess.run(
            ["clang", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
             "-shared", "-fPIC", str(ROOT / "native/gr3/m10v_guides.c"), "-o", str(library)],
            capture_output=True, text=True,
        )
        if result.returncode:
            raise AssertionError(result.stderr)
        cls.library = C.CDLL(str(library))
        cls.draw = cls.library.m10v_guides_draw
        cls.draw.argtypes = [C.POINTER(Surface), C.c_uint32, C.c_uint32]
        cls.draw.restype = None

    def surface(self, width, height, photo, clip=None):
        stride = width + 13
        size = stride * height
        pixels = (C.c_uint32 * (size + 2))(*([EMPTY] * (size + 2)))
        address = C.cast(C.byref(pixels, C.sizeof(C.c_uint32)), C.POINTER(C.c_uint32))
        surface = Surface(address, size, stride, width, height,
                          Rect(*photo), Rect(*(clip or (0, 0, width, height))))
        return surface, pixels

    def painted(self, surface, pixels):
        self.assertEqual(pixels[0], EMPTY)
        self.assertEqual(pixels[-1], EMPTY)
        stride = surface.stride_pixels
        result = set()
        for y in range(surface.height):
            row = 1 + y * stride
            self.assertEqual(pixels[row + surface.width:row + stride],
                             [EMPTY] * (stride - surface.width))
            for x in range(surface.width):
                color = pixels[row + x]
                if color != EMPTY:
                    self.assertEqual(color, GUIDE)
                    result.add((x, y))
        return result

    def test_golden_grid_matches_known_photo_boxes(self):
        cases = [
            (720, 480, (0, 0, 720, 480), (275, 445, 183, 297)),  # 3:2
            (720, 480, (120, 0, 600, 480), (303, 417, 183, 297)),  # 1:1
            (720, 480, (40, 0, 680, 480), (284, 436, 183, 297)),  # 4:3
            (720, 480, (0, 38, 720, 442), (275, 445, 192, 288)),  # GR III 16:9
            (720, 480, (0, 37, 720, 442), (275, 445, 192, 287)),  # 405-row 16:9
            (720, 480, (0, 108, 720, 372), (275, 445, 209, 271)),  # XPan
            (720, 480, (80, 0, 640, 480), (294, 426, 183, 297)),  # 6x7
            (720, 480, (181, 0, 539, 480), (318, 402, 183, 297)),  # Half
            (360, 240, (0, 0, 360, 240), (138, 222, 92, 148)),  # 3:2
            (360, 240, (60, 0, 300, 240), (152, 208, 92, 148)),  # 1:1
            (360, 240, (20, 0, 340, 240), (142, 218, 92, 148)),  # 4:3
            (360, 240, (0, 19, 360, 221), (138, 222, 96, 144)),  # 16:9
            (360, 240, (0, 54, 360, 186), (138, 222, 104, 136)),  # XPan
            (360, 240, (40, 0, 320, 240), (147, 213, 92, 148)),  # 6x7
            (360, 240, (91, 0, 269, 240), (159, 201, 92, 148)),  # Half
        ]
        for width, height, photo, (x1, x2, y1, y2) in cases:
            with self.subTest(photo=photo):
                surface, pixels = self.surface(width, height, photo)
                self.draw(C.byref(surface), 1, GUIDE)
                left, top, right, bottom = photo
                expected = {
                    (x, y) for y in range(top, bottom) for x in range(left, right)
                    if x in (x1 - 1, x1, x2 - 1, x2) or y in (y1 - 1, y1, y2 - 1, y2)
                }
                self.assertEqual(self.painted(surface, pixels), expected)

    def test_four_spirals_are_connected_and_reflect_in_the_photo_box(self):
        for width, height, photo in (
            (360, 240, (40, 10, 320, 230)), (720, 480, (0, 108, 720, 372)),
            (720, 480, (181, 0, 539, 480)),
        ):
            left, top, right, bottom = photo
            patterns = []
            for mode in range(2, 6):
                surface, pixels = self.surface(width, height, photo)
                self.draw(C.byref(surface), mode, GUIDE)
                pattern = self.painted(surface, pixels)
                self.assertGreater(len(pattern), 2 * (right - left))
                self.assertTrue(all(left <= x < right and top <= y < bottom for x, y in pattern))
                patterns.append(pattern)

            normal, rightward, downward, reversed_both = patterns
            self.assertEqual(rightward, {(left + right - 1 - x, y) for x, y in normal})
            self.assertEqual(downward, {(x, top + bottom - 1 - y) for x, y in normal})
            self.assertEqual(reversed_both, {(left + right - 1 - x, top + bottom - 1 - y)
                                             for x, y in normal})
            self.assertEqual(len({frozenset(pattern) for pattern in patterns}), 4)

            # Connected raster path, including diagonal steps in narrow parts of the spiral.
            seen = {next(iter(normal))}
            frontier = list(seen)
            while frontier:
                x, y = frontier.pop()
                for dx, dy in ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1),
                               (1, -1), (1, 0), (1, 1)):
                    point = (x + dx, y + dy)
                    if point in normal and point not in seen:
                        seen.add(point)
                        frontier.append(point)
            self.assertEqual(seen, normal)

    def test_spiral_passes_successive_golden_quarter_turns(self):
        surface, pixels = self.surface(360, 240, (0, 0, 360, 240))
        self.draw(C.byref(surface), 2, GUIDE)
        painted = self.painted(surface, pixels)
        # At each quarter turn the distance from the pole shrinks by phi.
        # Landmark pixels from the analytic curve fitted to this photo box.
        landmarks = [(358, 66), (102, 231), (4, 66), (102, 3), (139, 66),
                     (102, 90), (88, 66), (102, 57), (107, 66), (102, 69)]
        for x, y in landmarks:
            with self.subTest(landmark=(x, y)):
                self.assertIn((x, y), painted)
                self.assertIn((x + 1, y + 1), painted)
        self.assertNotIn((180, 120), painted)

    def test_clip_is_the_intersection_of_visible_canvas_and_photo(self):
        photo = (16, 5, 84, 61)
        clip = (35, 10, 111, 28)
        for mode in range(1, 6):
            full, full_pixels = self.surface(100, 70, photo)
            clipped, pixels = self.surface(100, 70, photo, clip)
            self.draw(C.byref(full), mode, GUIDE)
            self.draw(C.byref(clipped), mode, GUIDE)
            expected = {(x, y) for x, y in self.painted(full, full_pixels)
                        if 35 <= x < 111 and 10 <= y < 28}
            self.assertTrue(expected)
            self.assertEqual(self.painted(clipped, pixels), expected)

    def test_split_dirty_clips_match_one_full_draw(self):
        photo = (40, 10, 320, 230)
        for mode in range(1, 6):
            full, full_pixels = self.surface(360, 240, photo)
            split, pixels = self.surface(360, 240, photo, (0, 0, 167, 240))
            self.draw(C.byref(full), mode, GUIDE)
            self.draw(C.byref(split), mode, GUIDE)
            split.clip = Rect(167, 0, 360, 240)
            self.draw(C.byref(split), mode, GUIDE)
            self.assertEqual(bytes(pixels), bytes(full_pixels))

    def test_arm_and_host_draw_identically_with_no_runtime_dependencies(self):
        base, stop = 0x54160000, 0x5416fff0
        state, pixels_address = 0x55000000, 0x55002004
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            obj, elf, script = path / "guides.o", path / "guides.elf", path / "guides.ld"
            script.write_text(
                f"SECTIONS {{ . = {base}; .text : {{ *(.text*) }} "
                ".rodata : { *(.rodata*) } "
                "/DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) } }"
            )
            subprocess.run(
                ["clang", *FLAGS, "-c", str(ROOT / "native/gr3/m10v_guides.c"), "-o", str(obj)],
                check=True, capture_output=True,
            )
            lld = os.environ.get("M10V_LLVM_LD") or shutil.which("ld.lld")
            if not lld and Path("/opt/homebrew/opt/lld/bin/ld.lld").exists():
                lld = "/opt/homebrew/opt/lld/bin/ld.lld"
            self.assertIsNotNone(lld, "set M10V_LLVM_LD to the ARM linker")
            subprocess.run([lld, "-T", str(script), "--entry=m10v_guides_draw",
                            str(obj), "-o", str(elf)], check=True, capture_output=True)
            image = elf.read_bytes()

        entry, = struct.unpack_from("<I", image, 24)
        section_offset, = struct.unpack_from("<I", image, 32)
        section_count, = struct.unpack_from("<H", image, 48)
        machine = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        machine.ctl_set_cpu_model(A.UC_CPU_ARM_CORTEX_A9)
        machine.mem_map(base, 0x10000)
        machine.mem_map(state, 0x180000)
        for i in range(section_count):
            _, kind, flags, address, offset, size, *_ = struct.unpack_from(
                "<10I", image, section_offset + i * 40)
            if flags & 2 and size:
                self.assertEqual(kind, 1)
                self.assertFalse(flags & 1)
                machine.mem_write(address, image[offset:offset + size])

        for width, height, photo, clip in (
            (720, 480, (0, 108, 720, 372), (66, 27, 719, 344)),
            (360, 240, (91, 0, 269, 240), (10, 20, 347, 240)),
        ):
            for mode in range(7):
                with self.subTest(width=width, mode=mode):
                    surface, pixels = self.surface(width, height, photo, clip)
                    machine.mem_write(pixels_address - 4, bytes(pixels))
                    self.draw(C.byref(surface), mode, GUIDE)
                    machine.mem_write(state, struct.pack(
                        "<13I", pixels_address, surface.capacity_pixels,
                        surface.stride_pixels, width, height, *photo, *clip,
                    ))
                    for reg, value in ((A.UC_ARM_REG_R0, state), (A.UC_ARM_REG_R1, mode),
                                       (A.UC_ARM_REG_R2, GUIDE), (A.UC_ARM_REG_LR, stop),
                                       (A.UC_ARM_REG_SP, state + 0x1000)):
                        machine.reg_write(reg, value)
                    machine.emu_start(entry, stop, count=500000)
                    self.assertEqual(machine.reg_read(A.UC_ARM_REG_PC), stop)
                    self.assertEqual(machine.mem_read(pixels_address - 4, C.sizeof(pixels)),
                                     bytes(pixels))

    def test_invalid_layout_and_disabled_modes_do_not_write(self):
        def draw_with(change, mode=1):
            surface, pixels = self.surface(80, 64, (10, 6, 68, 62))
            change(surface)
            self.draw(C.byref(surface), mode, GUIDE)
            self.assertTrue(all(pixel == EMPTY for pixel in pixels))

        for mode in (0, 6, 0xffffffff):
            draw_with(lambda surface: None, mode)
        for name, value in (
            ("capacity_pixels", 93 * 63 + 79),
            ("stride_pixels", 79),
            ("stride_pixels", 0xffffffff),
            ("width", 0xffffffff),
            ("height", 0),
            ("pixels", None),
            ("photo", Rect(10, 6, 81, 62)),
            ("photo", Rect(68, 6, 10, 62)),
            ("clip", Rect(50, 32, 15, 32)),
        ):
            with self.subTest(field=name, value=value):
                draw_with(lambda surface: setattr(surface, name, value))
        self.draw(None, 1, GUIDE)
