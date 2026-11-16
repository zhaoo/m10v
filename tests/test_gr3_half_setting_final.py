"""Run the Half gate and native aspect selection from a standalone-menu BIN."""
import json
import os
from pathlib import Path
import struct
import subprocess
import unittest

from unicorn import UC_PROT_ALL, UC_PROT_EXEC, UC_PROT_READ

from scripts.analyze_gr3_border_iip import BASE, OriginalArm
from scripts.build_gr3_m10v_library import capture_stock_rtos
from tests import test_gr3_aspect_adj as adj

ROOT = Path(__file__).resolve().parents[1]
OWNER, BOX_STATE, BOX_TWO = 0x55070000, 0x55078000, 0x55094000
MODEL, PROPERTIES = adj.MODEL, adj.PROPERTIES
RATIO = PROPERTIES + 0x4c2


class FinalHalfSetting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.environ.get("M10V_MENU_HUB_CANDIDATE")
        if not path:
            raise unittest.SkipTest("M10V_MENU_HUB_CANDIDATE is required")
        candidate = Path(path).resolve()
        manifest = json.loads((candidate / "M10V-runtime-manifest.json").read_text())
        cls.symbols = manifest["symbols"]
        cls.official = capture_stock_rtos()
        cls.rom = subprocess.check_output(["node", "--input-type=module", "-e", """
            import {readFileSync} from 'node:fs';
            import {decodeFrameMap} from './node/gr3-frames.mjs';
            const data=decodeFrameMap(readFileSync(process.argv[1])).decoded;
            let at=0;
            while(data.toString('ascii',at,at+4)!=='RTOS')at+=16+data.readUInt32LE(at+12);
            process.stdout.write(data.subarray(at+16,at+16+data.readUInt32LE(at+12)));
            """, candidate / "fwdc239b.bin"], cwd=ROOT)

    def setUp(self):
        self.camera = camera = OriginalArm(self.official)
        old = (len(self.official) + 4095) & ~4095
        extent = (len(self.rom) + 4095) & ~4095
        camera.u.mem_protect(BASE, old, UC_PROT_ALL)
        camera.u.mem_map(BASE + old, extent - old)
        camera.u.mem_write(BASE, self.rom)
        camera.u.mem_protect(BASE, extent, UC_PROT_READ | UC_PROT_EXEC)
        camera.words(0x55063910, 1)
        camera.words(0x55063988, OWNER)
        camera.words(MODEL + 4, PROPERTIES)
        camera.words(adj.CONTROLLER + 0x1f0, adj.LIST)
        camera.u.mem_write(PROPERTIES + 0x918, b"\4")  # Native still ADJ Aspect Ratio
        camera.u.mem_write(PROPERTIES + 0x44, b"\1")  # Active shooting properties
        self.events = []
        camera.boundaries = {
            0x5320ad88: lambda: MODEL,
            0x5320b31c: lambda: MODEL,
            0x5320b67c: lambda: MODEL,
            0x5320aefc: lambda: MODEL,
            0x532288b0: lambda: self.events.append(camera.u.reg_read(camera.A.UC_ARM_REG_R1)),
            self.symbols["m10v_debug_log"]: lambda: 0,
        }
        camera.call(self.symbols["m10v_half_pair_init"], OWNER)
        self.menu = camera.read_words(0x53b3cf00, 10)

    def change(self, enabled):
        return self.camera.call(self.symbols["m10v_settings_half_set"], enabled)

    def enabled(self):
        return self.camera.call(self.symbols["m10v_settings_half_enabled"])

    def ratio(self):
        return self.camera.u.mem_read(RATIO, 1)[0]

    def test_default_hides_half_but_keeps_xpan_and_6x7_in_menu_adj_and_cycle(self):
        call = self.camera.call
        self.assertEqual(call(self.menu[2]), 6)
        self.assertEqual(call(0x531a31ac, adj.CONTROLLER), 6)
        for row, raw in enumerate((0, 3, 1, 2, 4, 5)):
            call(self.menu[6], 0, row)
            self.assertEqual(self.ratio(), raw)
        call(self.menu[6], 0, 6)  # A stale menu index cannot select hidden Half.
        self.assertEqual(self.ratio(), 5)
        self.assertEqual(call(0x540b9300, 4), 5)
        self.assertEqual(call(0x540b9300, 5), 0)
        self.assertEqual(call(0x540b9300, 6), 0)

    def test_toggle_shows_half_then_restores_live_3_2_via_native_setter(self):
        call = self.camera.call
        self.assertEqual(self.change(1), 0)
        self.assertEqual(self.enabled(), 1)
        self.assertEqual(call(self.menu[2]), 7)
        self.assertEqual(call(0x531a31ac, adj.CONTROLLER), 7)
        self.assertEqual(call(0x540b9300, 5), 6)
        call(self.menu[6], 0, 6)
        self.assertEqual(self.ratio(), 6)
        cleanups = []
        camera, registers = self.camera, self.camera.A

        def record_cleanup():
            if camera.u.reg_read(registers.UC_ARM_REG_R0) == 221:
                owner = camera.u.reg_read(registers.UC_ARM_REG_R1)
                sp = camera.u.reg_read(registers.UC_ARM_REG_SP)
                cleanups.append((owner, camera.read_words(sp, 1)[0]))
            return 0

        camera.boundaries[self.symbols["m10v_debug_log"]] = record_cleanup
        self.events.clear()
        self.assertEqual(self.change(0), 0)
        self.assertEqual(self.enabled(), 0)
        self.assertEqual(self.ratio(), 0)
        self.assertEqual(self.events, [0x183])
        self.assertEqual(cleanups, [(OWNER, 2)])  # Explicit pair cancellation.
        self.assertEqual(call(self.menu[2]), 6)

    def test_assignable_aspect_cycle_skips_half_until_enabled(self):
        camera = self.camera
        camera.boundaries.update({0x5320b7fc: lambda: 0, 0x53243e40: lambda: 0})
        camera.u.mem_write(RATIO, b"\5")
        camera.call(0x53227114)
        self.assertEqual(self.ratio(), 0)
        self.assertEqual(self.change(1), 0)
        camera.u.mem_write(RATIO, b"\5")
        camera.call(0x53227114)
        self.assertEqual(self.ratio(), 6)
        camera.call(0x53227114)
        self.assertEqual(self.ratio(), 0)
        self.assertFalse(camera.assertions)

    def test_disabling_without_live_model_leaves_half_enabled(self):
        self.assertEqual(self.change(1), 0)
        self.camera.call(self.menu[6], 0, 6)
        self.camera.boundaries[0x5320b31c] = lambda: 0
        self.assertNotEqual(self.change(0), 0)
        self.assertEqual(self.enabled(), 1)
        self.assertEqual(self.ratio(), 6)

    def test_saved_half_in_native_user_box_recalls_3_2_until_enabled(self):
        camera = self.camera
        camera.words(MODEL, BOX_STATE, PROPERTIES, 0, 0, BOX_TWO)
        camera.u.mem_write(BOX_STATE, b"\1")
        camera.u.mem_write(BOX_TWO + 0x44, b"\1")
        camera.u.mem_write(BOX_TWO + 0x4c2, b"\6")
        # Observe after live activation has passed through the policy gate.
        # The native memcpy and ratio setter run; leave sensor apply-all to
        # the camera. The untouched source buffer represents the saved box.
        camera.boundaries[0x532750fc] = lambda: 0
        camera.call(0x53279fa0, MODEL, 2)
        self.assertEqual(self.ratio(), 0)
        self.assertEqual(camera.u.mem_read(BOX_TWO + 0x4c2, 1)[0], 6)
        self.assertEqual(self.change(1), 0)
        camera.u.mem_write(BOX_STATE, b"\1")
        camera.call(0x53279fa0, MODEL, 2)
        self.assertEqual(self.ratio(), 6)

    def test_companion_explicit_half_write_enables_the_same_camera_gate(self):
        address = self.symbols.get("m10v_settings_controller_remote_aspect_write")
        if address is None:
            self.skipTest("candidate has no companion")
        busy = self.symbols["m10v_settings_controller_remote_busy"]
        self.camera.boundaries[busy] = lambda: 0
        self.assertEqual(self.camera.call(self.menu[2]), 6)
        self.assertEqual(self.camera.call(address, 6), 0)
        self.assertEqual(self.ratio(), 6)
        self.assertEqual(self.camera.call(self.menu[2]), 7)
        self.assertEqual(self.camera.call(address, 0), 0)
        self.assertEqual(self.ratio(), 0)
        self.assertEqual(self.camera.call(self.menu[2]), 7)

    def test_failed_companion_half_write_does_not_enable_the_camera_gate(self):
        address = self.symbols.get("m10v_settings_controller_remote_aspect_write")
        if address is None:
            self.skipTest("candidate has no companion")
        busy = self.symbols["m10v_settings_controller_remote_busy"]
        self.camera.boundaries[busy] = lambda: 0
        self.camera.boundaries[0x532525a4] = lambda: 1  # The native write did not stick.
        self.assertNotEqual(self.camera.call(address, 6), 0)
        self.assertEqual(self.ratio(), 0)
        self.assertEqual(self.camera.call(self.menu[2]), 6)
