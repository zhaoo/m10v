"""Run the guides selector and paint veneer against exact stock ARM code."""
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib

from unicorn import Uc, UC_ARCH_ARM, UC_HOOK_CODE, UC_MODE_ARM
from unicorn import arm_const as A

from scripts.build_gr3_m10v_library import FLAGS, capture_stock_rtos

ROOT = Path(__file__).resolve().parents[1]
ROM = 0x53000000
MODULE = 0x54200000
RETURN = 0x543ff000
RAM = 0x55000000
OWNER, LIVE, CANVAS, GRID, BITMAP = (RAM + i * 0x10000 for i in range(1, 6))
PIXELS = RAM + 0x200000
SETTINGS, SI_ROOT, SI = RAM + 0x1c0000, RAM + 0x1c2000, RAM + 0x1c3000
STACK = RAM + 0x3ff000
STRIDE = 736


def word(value):
    return struct.pack("<I", value)


class GuidesCameraTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from scripts.build_gr3_guides_hooks import build_guides_hooks
        cls.models = {}
        ld = os.environ.get("M10V_LLVM_LD") or shutil.which("ld.lld")
        ld = ld or "/opt/homebrew/opt/lld/bin/ld.lld"
        for model in ("gr3", "gr3x"):
            with tempfile.TemporaryDirectory() as folder:
                directory = Path(folder)
                objects = []
                for filename in ("m10v_guides.c", "m10v_guides_camera.c", "m10v_guides_hooks.S"):
                    obj = directory / (filename + ".o")
                    result = subprocess.run(
                        ["clang", *FLAGS, "-DM10V_GUIDES_OWNER_OFFSET=0x6600",
                         "-DM10V_GUIDES_ASPECT=1", "-DM10V_DEBUG_MODE=1", "-DM10V_ADJ_EXIT_TRACE=1",
                         f"-DM10V_CAMERA_GR3X={int(model == 'gr3x')}",
                         "-c", str(ROOT / "native/gr3" / filename), "-o", str(obj)],
                        capture_output=True, text=True,
                    )
                    if result.returncode:
                        raise AssertionError(result.stderr)
                    objects.append(str(obj))
                link = directory / "layout.ld"
                link.write_text(
                    f"SECTIONS {{ . = {MODULE}; .text : {{ *(.text*) }} "
                    ".rodata : { *(.rodata*) } "
                    "/DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) } }")
                elf = directory / "guides.elf"
                result = subprocess.run([ld, "-T", str(link), "--entry=m10v_guides_camera_init",
                                         "--defsym=m10v_debug_log=0x543fe000",
                                         *objects, "-o", str(elf)], capture_output=True, text=True)
                if result.returncode:
                    raise AssertionError(result.stderr)
                data = elf.read_bytes()
            off, = struct.unpack_from("<I", data, 32)
            count, = struct.unpack_from("<H", data, 48)
            sections = [struct.unpack_from("<10I", data, off + i * 40) for i in range(count)]
            code, symbols = [], {}
            for _, kind, flags, address, offset, size, strings_index, _, _, _ in sections:
                if flags & 2 and size:
                    assert kind == 1 and not flags & 1
                    code.append((address, data[offset:offset + size]))
                if kind == 2:
                    start, length = sections[strings_index][4:6]
                    strings = data[start:start + length]
                    for at in range(offset, offset + size, 16):
                        name, value, _, _, _, _ = struct.unpack_from("<IIIBBH", data, at)
                        symbols[strings[name:].split(b"\0", 1)[0].decode()] = value
            stock = capture_stock_rtos(model)
            report = build_guides_hooks(MODULE, stock, symbols)
            patched = bytearray(stock)
            for patch in report["patches"]:
                at = patch["address"] - ROM
                patched[at:at + 4] = word(patch["replacement"])
            cls.models[model] = (patched, code, symbols)

    def machine(self, model, ratio=0, display=0):
        self.u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        self.u.ctl_set_cpu_model(A.UC_CPU_ARM_CORTEX_A9)
        rom, sections, self.symbols = self.models[model]
        self.u.mem_map(ROM, max(0x1400000, (len(rom) + 4095) & ~4095))
        self.u.mem_write(ROM, bytes(rom))
        self.u.mem_map(RAM, 0x400000)
        for address, data in sections:
            self.u.mem_write(address, data)
        self.put(0x55063910, 1)
        self.put(0x55063988, OWNER)
        self.put(0x55063f34, SETTINGS)
        self.put(SETTINGS + 4, SETTINGS)
        self.put(SI_ROOT, SI)
        self.put(LIVE + 4, CANVAS)
        self.put(LIVE + 0x15c, CANVAS)
        self.put(LIVE + 0x160, GRID)
        self.put(CANVAS + 0x28, 720)
        self.put(CANVAS + 0x2c, 480)
        self.put(CANVAS + 0xec, BITMAP)
        children = RAM + 0x1c4100
        self.put(CANVAS + 0xc, children)
        self.put(CANVAS + 0x10, children + 4)
        self.put(children, GRID)
        grid_vtable = RAM + 0x1c4200
        self.put(GRID, grid_vtable)
        self.put(grid_vtable + 0x4c, 0x5339c3b0)
        # Canvas::Draw first dispatches a native vtable method. Keep its
        # argument and original method in the fixture, stub its other service.
        vtable = RAM + 0x1c4000
        self.put(CANVAS, vtable)
        self.put(vtable + 0x48, ROM + 0x100)
        self.u.mem_write(CANVAS + 0x9e, b"\1")
        self.u.mem_write(LIVE + 0x2d1, bytes([display]))
        self.u.mem_write(SETTINGS + 0x912, bytes([display]))
        for offset in (0x8e2, 0x8e4, 0x8e6):
            self.u.mem_write(SETTINGS + offset, b"\1")
        self.u.mem_write(BITMAP + 2, b"\5")
        self.put(BITMAP + 4, STRIDE * 480 * 4)
        self.put(BITMAP + 8, PIXELS)
        self.u.mem_write(BITMAP + 0x18, struct.pack("<4H", STRIDE, 480, 720, 480))
        self.ratio = ratio
        self.children, self.clears, self.invalidations, self.rows = [], [], [], []
        self.grid_draws, self.trace = [], []
        self.ports = {ROM + 0x100: 0, 0x5320ad88: SETTINGS, 0x5320b31c: SETTINGS,
                      0x53525d5c: SI_ROOT, 0x5354a778: lambda: self.ratio,
                      0x53549958: 0, 0x53654150: SETTINGS, 0x53654220: 0,
                      0x53828014: 0, 0x5320804c: 0, 0x532081ec: 0,
                      0x53176820: 0,
                      0x53208a2c: self.clear, 0x533ad308: self.invalidate,
                      0x536b5604: 0, 0x5339e8b0: self.row}
        if "m10v_debug_log" in self.symbols:
            self.ports[self.symbols["m10v_debug_log"]] = self.log
        self.u.hook_add(UC_HOOK_CODE, self.boundary)
        self.u.hook_add(UC_HOOK_CODE, lambda *_: self.children.append(self.args()[:2]),
                        begin=0x53393d28, end=0x53393d28)
        self.u.hook_add(UC_HOOK_CODE, lambda *_: self.grid_draws.append(self.args()[:2]),
                        begin=0x5339c3b4, end=0x5339c3b4)
        self.call("m10v_guides_camera_init", OWNER)
        self.call("m10v_guides_camera_restore", LIVE)
        return self

    def put(self, addr, value):
        self.u.mem_write(addr, word(value))

    def get(self, addr):
        return int.from_bytes(self.u.mem_read(addr, 4), "little")

    def args(self):
        return tuple(self.u.reg_read(reg) for reg in
                     (A.UC_ARM_REG_R0, A.UC_ARM_REG_R1, A.UC_ARM_REG_R2))

    def clear(self):
        self.clears.append(1)
        self.u.mem_write(PIXELS, bytes(STRIDE * 480 * 4))
        return 0

    def invalidate(self):
        self.invalidations.append(self.args()[0])
        return 0

    def row(self):
        self.rows.append(self.args())
        return 0

    def log(self):
        self.trace.append(self.args()[0])
        return 1

    def boundary(self, _, address, size, data):
        if address in self.ports:
            value = self.ports[address]
            self.u.reg_write(A.UC_ARM_REG_R0, value() if callable(value) else value)
            self.u.reg_write(A.UC_ARM_REG_PC, self.u.reg_read(A.UC_ARM_REG_LR))

    def call(self, target, *args):
        if isinstance(target, str):
            target = self.symbols[target]
        for reg, value in zip((A.UC_ARM_REG_R0, A.UC_ARM_REG_R1, A.UC_ARM_REG_R2), args):
            self.u.reg_write(reg, value)
        self.u.reg_write(A.UC_ARM_REG_SP, STACK)
        self.u.reg_write(A.UC_ARM_REG_LR, RETURN)
        self.u.emu_start(target, RETURN, count=700000)
        self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC), RETURN)
        self.assertEqual(self.u.reg_read(A.UC_ARM_REG_SP), STACK)
        return self.u.reg_read(A.UC_ARM_REG_R0)

    def paint(self):
        self.call(0x53391b14, CANVAS)

    def pixel(self, x, y):
        return self.get(PIXELS + 4 * (y * STRIDE + x))

    def test_installed_native_selector_preserves_stock_values_and_private_choices(self):
        for model in ("gr3", "gr3x"):
            self.machine(model)
            count, draw, apply, checked = (
                self.get(address) for address in (0x53b3dcc8, 0x53b3dcd0, 0x53b3dcd8, 0x53b3dce0))
            self.assertEqual(self.call(count), 7)
            for index in range(2, 7):
                self.call(draw, 0, GRID, index)
                self.assertEqual(self.rows[-1][0], GRID)
                self.assertEqual(self.rows[-1][2], 1179 + index)
                self.assertEqual(self.call(apply, 0, index), 1)
                self.assertEqual(self.call(checked, 0, index), 1)
                self.assertEqual(self.call(checked, 0, 0), 0)
                self.assertEqual(self.u.mem_read(SETTINGS + 0x8be, 1), b"\0")
            self.assertEqual(self.call(apply, 0, 1), 1)
            self.assertEqual(self.u.mem_read(SETTINGS + 0x8be, 1), b"\1")
            self.assertEqual(self.call(checked, 0, 1), 1)
            self.assertEqual(self.call(apply, 0, 7), 0)

    def apply_native_grid_style(self, row):
        selector = SETTINGS + 0x6000
        self.put(selector + 0x124, 0x020000a0)
        self.call(0x531b9640, selector, 0x020000a0)
        self.assertEqual(bytes(self.u.mem_read(selector + 0x198, 1)), b"\x58")
        self.ports[0x53394820] = row  # Native option list's selected row
        self.assertEqual(self.call(0x531ba21c, selector), 1)

    def load_factory_grid_settings(self):
        # Execute the native factory initialization, including the default
        # DISP and Grid Guide fields, then use the native settings wrapper.
        def copy():
            dest, source, length = self.args()
            self.u.mem_write(dest, bytes(self.u.mem_read(source, length)))
            return dest

        self.u.reg_write(A.UC_ARM_REG_C1_C0_2, 0xf00000)
        self.u.reg_write(A.UC_ARM_REG_FPEXC, 0x40000000)
        self.ports.update({0x5313fd80: copy, 0x5323f328: 0,
                           0x536b53e0: 0, 0x536b53e8: 0})
        self.call(0x5323f424, SETTINGS, SETTINGS)
        self.assertEqual(self.grid_flags(), [0, 0, 0])
        self.assertEqual(self.u.mem_read(SETTINGS + 0x912, 1), b"\0")
        self.put(0x55063ed0, 1)
        for i in range(1, 9):
            self.put(0x55063f30 + i * 4, SETTINGS + (i - 1) * 0x1000)
        del self.ports[0x5320b31c]

    def grid_flags(self):
        return [self.u.mem_read(SETTINGS + offset, 1)[0] for offset in (0x8e2, 0x8e4, 0x8e6)]

    def test_native_grid_choice_enables_current_disp_profile_from_factory_defaults(self):
        for model in ("gr3", "gr3x"):
            self.machine(model)
            self.load_factory_grid_settings()
            self.apply_native_grid_style(2)
            self.assertEqual(self.call("m10v_guides_camera_mode"), 1)
            self.call(0x5317681c, LIVE)
            self.assertEqual(self.grid_flags(), [1, 0, 0])
            self.assertEqual(self.invalidations, [CANVAS])
            self.paint()
            self.assertEqual(self.pixel(275, 100), 0x80000000)
            self.call(0x5324325c, 0x55063f30, 0)
            self.call(0x5317681c, LIVE)
            self.paint()
            self.assertEqual(self.pixel(275, 100), 0)

    def test_stock_grid_choice_enables_only_current_supported_disp_profile(self):
        for model in ("gr3", "gr3x"):
            self.machine(model)
            self.load_factory_grid_settings()
            self.u.mem_write(SETTINGS + 0x912, b"\3")
            self.apply_native_grid_style(1)
            self.assertEqual(self.grid_flags(), [0, 0, 0])
            self.assertEqual(self.invalidations, [])

            self.u.mem_write(SETTINGS + 0x912, b"\1")
            self.u.mem_write(LIVE + 0x2d1, b"\1")
            self.apply_native_grid_style(1)
            self.assertEqual(self.grid_flags(), [0, 1, 0])
            self.assertEqual(self.invalidations, [])
            self.assertEqual(self.call("m10v_guides_camera_mode"), 0)

            shown = []
            self.ports.update({0x53177484: 0, 0x5339c1e0: 0,
                               0x533ad3c0: lambda: shown.append(self.args()[:2]) or 0})
            self.call(0x5317750c, LIVE, 1, 1)
            self.assertEqual(shown, [(GRID, 1)])
            self.assertEqual(self.u.mem_read(GRID + 0xf4, 2), b"\1\x10")

    def test_native_grid_style_apply_defers_redraw_until_live_update(self):
        for model in ("gr3", "gr3x"):
            self.machine(model)
            self.apply_native_grid_style(2)
            self.assertEqual(self.call("m10v_guides_camera_mode"), 1)
            self.assertEqual(self.invalidations, [], "Apply invalidated from the menu stack")
            self.call(0x5317681c, LIVE)
            self.assertEqual(self.invalidations, [CANVAS])
            self.paint()
            self.assertEqual(self.pixel(275, 100), 0x80000000)

    def test_live_enter_defers_redraw_until_first_native_update(self):
        for model in ("gr3", "gr3x"):
            self.machine(model)
            self.call("m10v_guides_camera_leave", LIVE)
            self.apply_native_grid_style(2)
            self.assertEqual(self.invalidations, [])
            self.call("m10v_guides_camera_restore", LIVE)
            self.assertEqual(self.invalidations, [], "Enter invalidated before live update")
            self.call(0x5317681c, LIVE)
            self.assertEqual(self.invalidations, [CANVAS])
            self.paint()
            self.assertEqual(self.pixel(275, 100), 0x80000000)

    def test_debug_trace_logs_only_first_update_per_setting_change(self):
        for model in ("gr3", "gr3x"):
            self.machine(model)
            self.assertEqual(self.trace, [276, 277])
            self.apply_native_grid_style(2)
            self.assertEqual(self.trace[-2:], [274, 275])
            for _ in range(3):
                self.call(0x5317681c, LIVE)
                self.paint()
            self.assertEqual(self.trace, [276, 277, 274, 275, 278, 279])
            self.call("m10v_guides_camera_leave", LIVE)
            self.call("m10v_guides_camera_restore", LIVE)
            self.call(0x5317681c, LIVE)
            self.assertEqual(self.trace, [276, 277, 274, 275, 278, 279])
            self.apply_native_grid_style(0)
            self.call(0x5317681c, LIVE)
            self.assertEqual(self.trace[-4:], [274, 275, 278, 279])

    def test_native_canvas_clear_then_paint_and_children_once_for_each_model(self):
        for model, rows in (("gr3", (192, 288)), ("gr3x", (192, 287))):
            self.machine(model, ratio=2)
            self.assertEqual(self.call("m10v_guides_camera_set_mode", 1), 1)
            self.call(0x5317681c, LIVE)
            self.assertEqual(self.invalidations, [CANVAS])
            self.paint()
            self.assertEqual(self.clears, [1])
            self.assertEqual(self.children, [(CANVAS, BITMAP)])
            for y in rows:
                self.assertEqual(self.pixel(200, y), 0x80000000)
            self.assertEqual(self.pixel(200, 250), 0)
            self.assertEqual(self.pixel(720, rows[0]), 0)
            self.assertEqual(self.grid_draws, [])
            # A draw outside the original child dispatch must reach stock,
            # even when the native bitmap pointer still matches.
            self.call(0x5339c3b0, GRID, BITMAP)
            self.assertEqual(self.grid_draws, [(GRID, BITMAP)])
            self.assertEqual(self.call("m10v_guides_camera_suppress_grid", GRID + 4, BITMAP), 0)

    def test_gr3x_native_wide_fit_matches_guide_viewport(self):
        self.machine("gr3x", ratio=2)
        self.u.reg_write(A.UC_ARM_REG_C1_C0_2, 0xf00000)
        self.u.reg_write(A.UC_ARM_REG_FPEXC, 0x40000000)
        native_size, canvas_fit = SETTINGS + 0x4000, SETTINGS + 0x4010
        self.u.mem_write(native_size, struct.pack("<2I", 6000, 3376))
        for width, height, top, fitted in ((720, 480, 37, 405), (360, 240, 19, 202)):
            self.u.mem_write(canvas_fit, struct.pack("<4I", width, height, 0, 0))
            self.assertEqual(self.call(0x532b1230, 0, native_size, canvas_fit), 1)
            self.assertEqual(struct.unpack("<4I", self.u.mem_read(canvas_fit, 16)),
                             (width, fitted, 0, top))

    def test_disp_movie_bad_bitmap_and_retired_live_view_do_not_draw(self):
        self.machine("gr3")
        self.call("m10v_guides_camera_set_mode", 1)
        self.call(0x5317681c, LIVE)
        self.paint()
        self.assertEqual(self.pixel(275, 100), 0x80000000)
        self.u.mem_write(LIVE + 0x2d1, b"\3")
        self.u.mem_write(SETTINGS + 0x912, b"\3")
        self.call(0x5317681c, LIVE)
        self.paint()
        self.assertEqual(self.pixel(275, 100), 0)
        self.u.mem_write(LIVE + 0x2d1, b"\0")
        self.u.mem_write(SETTINGS + 0x912, b"\0")
        self.u.mem_write(LIVE + 0x2d2, b"\1")
        self.call(0x5317681c, LIVE)
        self.paint()
        self.assertEqual(self.pixel(275, 100), 0)
        self.u.mem_write(LIVE + 0x2d2, b"\0")
        self.put(BITMAP + 4, 8)
        self.call(0x5317681c, LIVE)
        self.paint()
        self.assertEqual(self.pixel(275, 100), 0)
        self.assertEqual(self.call("m10v_guides_camera_suppress_grid", GRID, BITMAP), 0)
        self.call("m10v_guides_camera_leave", LIVE)
        self.put(BITMAP + 4, STRIDE * 480 * 4)
        self.call(0x5317681c, LIVE)
        self.paint()
        self.assertEqual(self.pixel(275, 100), 0)

        self.put(LIVE + 0x15c, 0)
        self.call("m10v_guides_camera_restore", LIVE)
        self.put(LIVE + 0x15c, CANVAS)
        self.call(0x5317681c, LIVE)
        self.paint()
        self.assertEqual(self.pixel(275, 100), 0x80000000)

    def test_mounted_journal_restore_corruption_and_card_replacement(self):
        self.machine("gr3")
        manager, slot, fs = SETTINGS + 0x5000, SETTINGS + 0x5100, SETTINGS + 0x5200
        self.put(manager + 8, slot)
        self.put(slot, fs)
        self.u.mem_write(fs + 0x20, b"\1")
        self.ports[0x53828014] = manager
        records = {}
        writes = []

        def request():
            _, name, count = self.args()
            self.assertEqual(count, 20)
            return bytes(self.u.mem_read(name, 12)).split(b"\0")[0], self.u.reg_read(A.UC_ARM_REG_R3)

        def read():
            name, address = request()
            if name not in records:
                return 0
            self.u.mem_write(address, records[name])
            return 1

        def write():
            name, address = request()
            records[name] = bytes(self.u.mem_read(address, 20))
            writes.append(name)
            return 1

        self.ports[0x53825648] = read
        self.ports[0x53825fa8] = write
        self.assertEqual(self.call("m10v_guides_camera_set_mode", 2), 1)
        self.assertEqual(self.call("m10v_guides_camera_set_mode", 5), 1)
        self.assertEqual(writes, [b"M10VGD1.BIN", b"M10VGD0.BIN"])

        self.call("m10v_guides_camera_dispose", OWNER)
        self.assertEqual(self.call("m10v_guides_camera_mode"), 0)
        self.call("m10v_guides_camera_init", OWNER)
        self.call("m10v_guides_camera_restore", LIVE)
        self.assertEqual(self.call("m10v_guides_camera_mode"), 5)

        records[b"M10VGD0.BIN"] = bytes(20)
        self.call("m10v_guides_camera_init", OWNER)
        self.call("m10v_guides_camera_restore", LIVE)
        self.assertEqual(self.call("m10v_guides_camera_mode"), 2)
        self.ports[0x53825fa8] = 0
        self.assertEqual(self.call("m10v_guides_camera_set_mode", 4), 0)
        self.assertEqual(self.call("m10v_guides_camera_mode"), 2)
        self.ports[0x53825fa8] = write

        replacement_card = struct.pack("<4I", 0x5344474d, 1, 77, 1)
        records.clear()
        records[b"M10VGD1.BIN"] = replacement_card + word(zlib.crc32(replacement_card))
        self.assertEqual(self.call("m10v_guides_camera_set_mode", 3), 1)
        self.assertEqual(struct.unpack_from("<I", records[b"M10VGD0.BIN"], 8)[0], 78)

    def test_final_firmware_uses_installed_menu_canvas_and_crop_grid(self):
        candidates = [(model, os.environ.get("M10V_GUIDES_" + model.upper() + "_BIN"))
                      for model in ("gr3", "gr3x")]
        if not all(path for _, path in candidates):
            self.skipTest("set M10V_GUIDES_GR3_BIN and M10V_GUIDES_GR3X_BIN to final test candidates")
        for model, path in candidates:
            firmware = Path(path)
            manifest = json.loads((firmware.parent / "M10V-runtime-manifest.json").read_text())
            script = (
                "import {readFileSync} from 'node:fs';"
                "import {decodeFrameMap} from './node/gr3-frames.mjs';"
                "const {decoded:d}=decodeFrameMap(readFileSync(process.argv[1]));"
                "let o=0;while(d.toString('ascii',o,o+4)!=='RTOS'){"
                "o+=16+d.readUInt32LE(o+12);if(o>=d.length)throw Error('RTOS missing');}"
                "process.stdout.write(d.subarray(o+16,o+16+d.readUInt32LE(o+12)));"
            )
            rtos = subprocess.check_output(["node", "--input-type=module", "-e", script,
                                            str(firmware.resolve())], cwd=ROOT)
            previous = self.models[model]
            try:
                self.models[model] = (rtos, [], manifest["symbols"])
                self.machine(model, ratio=4, display=1)
                self.load_factory_grid_settings()
                self.u.mem_write(SETTINGS + 0x912, b"\1")
                self.put(GRID, 0x53c0aa68)
                self.put(GRID + 4, CANVAS)
                for view in (GRID, CANVAS):
                    self.u.mem_write(view + 0x30, struct.pack("<4I", 0, 0, 720, 480))
                    self.u.mem_write(view + 0x64, struct.pack("<4I", 0, 0, 720, 480))
                    self.u.mem_write(view + 0x9e, b"\1")
                self.u.mem_write(GRID + 0xf4, b"\2\x10")
                manager, graphics = SETTINGS + 0x5000, SETTINGS + 0x5100
                self.ports.update({0x5317750c: 0, 0x5320804c: manager,
                                   0x532081ec: graphics, 0x53208298: 0})
                fills = []

                def fill():
                    _, packet, _ = self.args()
                    surface, x, y, width, height, color = struct.unpack(
                        "<5IB", bytes(self.u.mem_read(packet, 21)))
                    self.assertEqual(surface, BITMAP)
                    if (x, y, width, height, color) == (0, 0, 720, 480, 0):
                        return self.clear()
                    fills.append((x, y, width, height, color))
                    return 0

                self.ports[0x53208a2c] = fill
                callback = self.get(0x53b2fa48)
                self.call(callback, LIVE, 1, 1)
                self.assertEqual(self.get(self.get(GRID) + 0x4c), 0x540b90a4)
                count = self.get(0x53b3dcc8)
                self.assertEqual(self.call(count), 7)
                self.invalidations.clear()  # The crop callback also schedules its own repaint.
                self.apply_native_grid_style(2)
                self.assertEqual(self.grid_flags(), [0, 1, 0])
                self.assertEqual(self.invalidations, [], "Apply invalidated from the menu stack")
                self.call(0x5317681c, LIVE)
                self.assertEqual(self.invalidations, [CANVAS])
                self.paint()
                exit_trace = (manifest.get("debug_log") or {}).get("adj_exit_trace")
                self.assertEqual([event for event in self.trace if 274 <= event <= 279],
                                 [276, 277, 274, 275, 278, 279] if exit_trace else [])
                self.assertEqual(self.children, [(CANVAS, BITMAP)])
                self.assertEqual(fills, [(0, 0, 720, 108, 16), (0, 372, 720, 108, 16)])
                self.assertEqual(self.grid_draws, [])
                self.assertEqual(self.pixel(100, 209), 0x80000000)
                self.assertEqual(self.pixel(100, 20), 0)
                self.call("m10v_guides_camera_leave", LIVE)
                self.u.mem_write(GRID + 0x9e, b"\0")
                self.call(0x5317681c, LIVE)
                self.paint()
                self.assertEqual(self.pixel(100, 209), 0)
            finally:
                self.models[model] = previous
