"""Execute the still Aspect Ratio ADJ descriptor from a decoded final BIN."""
import json
import os
from pathlib import Path
import struct
import unittest

from unicorn import UC_PROT_ALL, UC_PROT_EXEC, UC_PROT_READ

from scripts.analyze_gr3_border_iip import OriginalArm
from scripts.build_gr3_m10v_library import capture_stock_rtos
from scripts.gr3_aspect_overlay import apply_overlay

ROOT = Path(__file__).resolve().parents[1]
BASE = 0x53000000
CONTROLLER, MODEL, PROPERTIES = 0x55080000, 0x55090000, 0x55091000
LIST, ROW_VIEW = 0x550a0000, 0x550a1000
RAW_RATIOS = (0, 3, 1, 2, 4, 5, 6)


def descriptor_address(rom):
    low = struct.unpack_from("<I", rom, 0x531a31c4 - BASE)[0]
    high = struct.unpack_from("<I", rom, 0x531a31cc - BASE)[0]
    immediate = lambda w: ((w >> 4) & 0xf000) | (w & 0xfff)
    return immediate(low) | immediate(high) << 16


def icon_ids(rom, half):
    start = rom.index(b"A7AI", 0x540bc000 - BASE, 0x540be000 - BASE)
    xpan, six_by_seven = struct.unpack_from("<2I", rom, start + 4)
    icons = [257, 256, 339, 337, xpan, six_by_seven]
    if half:
        start = rom.index(b"A7FH", 0x540bc000 - BASE, 0x540be000 - BASE)
        icons.append(struct.unpack_from("<I", rom, start + 8)[0])
    return icons


class FinalAspectAdj(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.official = capture_stock_rtos()

    def source_fixture(self, half):
        # Use the pinned retained crop template, as the ordinary aspect ARM
        # suite does, and exercise this branch's production overlay builder.
        template = json.loads((ROOT / ".runtime/grlife-current/reconstruction/firmware_store"
                               / "templates/urban160-native.json").read_text())
        stock = self.official if half else capture_stock_rtos("gr3x")
        retained = bytearray(stock)
        retained.extend(bytes(0x540ba000 - BASE - len(retained)))
        code = bytes.fromhex(template["program_hex"])
        at = template["base_va"] - BASE
        retained[at:at + len(code)] = code
        struct.pack_into("<I", retained, 0x53b2fa48 - BASE, 0x540b7bf4)
        image, symbols = apply_overlay(retained, half_frame=half)
        image = bytearray(image)
        struct.pack_into("<2I", image, symbols["m10v_aspect_icon_record"] - BASE + 4, 855, 856)
        if half:
            struct.pack_into("<I", image, symbols["m10v_aspect_half_record"] - BASE + 8, 877)
        return bytes(image)

    def fixture(self, rom):
        official = self.official
        camera = OriginalArm(official)
        old = (len(official) + 4095) & ~4095
        extent = (len(rom) + 4095) & ~4095
        camera.u.mem_protect(BASE, old, UC_PROT_ALL)
        if extent > old:
            camera.u.mem_map(BASE + old, extent - old)
        camera.u.mem_write(BASE, rom)
        camera.u.mem_protect(BASE, extent, UC_PROT_READ | UC_PROT_EXEC)
        camera.words(MODEL + 4, PROPERTIES)
        camera.words(CONTROLLER + 0x1f0, LIST)
        camera.u.mem_write(PROPERTIES + 0x918, b"\4")  # Native still ADJ Aspect Ratio
        camera.u.mem_write(PROPERTIES + 0x44, b"\1")  # Native active property path
        draws = []
        A = camera.A

        def draw():
            draws.append((camera.u.reg_read(A.UC_ARM_REG_R0), camera.u.reg_read(A.UC_ARM_REG_R1)))
            return 0

        camera.boundaries = {
            0x5320ad88: lambda: MODEL,
            0x5320b31c: lambda: MODEL,
            0x5320b67c: lambda: MODEL,
            0x5320aefc: lambda: MODEL,
            0x532288b0: lambda: 0,
            0x53394758: lambda: ROW_VIEW,
            0x533a1734: draw,
        }
        return camera, draws

    def test_installed_native_adj_lists_checks_draws_and_applies_menu_aspects(self):
        fixtures = [(True, os.environ.get("M10V_ADJ_ASPECT_GR3_RTOS")),
                    (False, os.environ.get("M10V_ADJ_ASPECT_GR3X_RTOS"))]
        for half, path in fixtures:
            with self.subTest(half=half):
                rom = Path(path).read_bytes() if path else self.source_fixture(half)
                camera, draws = self.fixture(rom)
                descriptor = descriptor_address(rom) + 4 * 0x44
                draw = camera.read_words(descriptor + 0x18, 1)[0]
                checked = camera.read_words(descriptor + 0x20, 1)[0]
                apply = camera.read_words(descriptor + 0x28, 1)[0]
                count = camera.read_words(descriptor + 0x30, 1)[0]
                expected = RAW_RATIOS if half else RAW_RATIOS[:-1]
                self.assertEqual(camera.call(0x531a31ac, CONTROLLER), len(expected))
                for row, (raw, icon) in enumerate(zip(expected, icon_ids(rom, half))):
                    with self.subTest(row=row):
                        self.assertNotEqual(icon, 0)
                        camera.call(draw, CONTROLLER, row)
                        self.assertEqual(draws[-1], (ROW_VIEW, icon))
                        self.assertEqual(camera.call(apply, CONTROLLER, row), 1)
                        self.assertEqual(bytes(camera.u.mem_read(PROPERTIES + 0x4c2, 1)), bytes([raw]))
                        self.assertEqual(camera.call(checked, CONTROLLER, row), 1)
                        self.assertEqual(camera.call(checked, CONTROLLER, (row + 1) % len(expected)), 0)
                self.assertFalse(camera.assertions)
                self.assertEqual(camera.call(apply, CONTROLLER, len(expected)), 0)
                self.assertEqual(camera.call(checked, CONTROLLER, len(expected)), 0)
                self.assertEqual(bytes(camera.u.mem_read(PROPERTIES + 0x4c2, 1)), bytes([expected[-1]]))
                camera.u.mem_write(CONTROLLER + 0x270, b"\1")
                self.assertEqual(camera.call(count, CONTROLLER), 2)
                self.assertEqual(camera.call(apply, CONTROLLER, 2), 0)

                unbound = bytearray(rom)
                record = unbound.index(b"A7AI", 0x540bc000 - BASE, 0x540be000 - BASE)
                struct.pack_into("<2I", unbound, record + 4, 0, 0)
                unbound_camera, _ = self.fixture(bytes(unbound))
                self.assertEqual(unbound_camera.call(0x531a31ac, CONTROLLER), 2)
                self.assertEqual(unbound_camera.call(apply, CONTROLLER, 2), 0)
