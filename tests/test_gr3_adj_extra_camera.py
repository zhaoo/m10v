"""Run the real A32 nine-tile adapter against stock service boundaries."""
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import *

ROOT = Path(__file__).resolve().parents[1]
BASE = 0x54160000
OWNER = 0x55010000
ADJ = 0x55020000
PARENT = 0x55021000
FRAME = 0x55022000
VECTOR = 0x55023000
RETURN = 0x5500fe00
REGS = (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)
KEYBOARD = 0x55029200
KEY_SERVICE = 0x55029c00
KEY_QUEUE = 0x55029d00
KEY_NAVIGATION = 0x55029e00
KEY_STUB = 0x55029f00


class CameraAdjTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        artifact = os.environ.get("M10V_TEST_ADJ_FIRMWARE_DIR")
        cls.final = bool(artifact)
        if artifact:
            directory = Path(artifact).resolve()
            manifests = list(directory.rglob("M10V-runtime-manifest.json"))
            if len(manifests) != 1:
                raise AssertionError(f"expected one runtime manifest in {directory}")
            manifest = json.loads(manifests[0].read_text())
            model = manifest["camera_model"]
            filename = "fwdc243b.bin" if model == "gr3x" else "fwdc239b.bin"
            candidates = list(directory.rglob(filename))
            if len(candidates) != 1:
                raise AssertionError(f"expected one {filename} in {directory}")
            script = """
import {readFileSync} from 'node:fs';
import {decodeFrameMap} from './node/gr3-frames.mjs';
const bytes=readFileSync(process.argv[1]), decoded=decodeFrameMap(bytes).decoded;
let at=0;
while(decoded.toString('ascii',at,at+4)!=='RTOS')at+=16+decoded.readUInt32LE(at+12);
process.stdout.write(decoded.subarray(at+16,at+16+decoded.readUInt32LE(at+12)));
"""
            cls.rom = subprocess.check_output(
                ["node", "--input-type=module", "-e", script, candidates[0]], cwd=ROOT)
            cls.symbols = manifest["symbols"]
            cls.stock_refresh = manifest["settings_menu"]["exports"]["m10v_ab_adj_refresh_original"]
            cls.stock_dispatch = manifest["settings_menu"]["exports"]["m10v_ab_dispatch_original"]
            cls.stock_destroy = manifest["settings_menu"]["exports"]["m10v_ab_adj_destroy_original"]
            cls.hdf_cache = OWNER + manifest["hdf_menu"]["owner_offset"] + manifest["hdf_adj"]["cache"]["offset"]
            cls.code = None
            patches = manifest["adj_extra"]["patches"]
            if len(patches) != (28 if (manifest.get("debug_log") or {}).get("adj_exit_trace") else 9):
                raise AssertionError("final ADJ patch inventory differs")
            for patch in patches:
                word = struct.unpack_from("<I", cls.rom, patch["address"] - 0x53000000)[0]
                if word != patch["replacement"]:
                    raise AssertionError(f"final ADJ patch differs at {patch['address']:#x}")
            return
        compiler = shutil.which(os.environ.get("M10V_LLVM_CLANG", "clang"))
        if not compiler or not shutil.which("ld.lld"):
            raise unittest.SkipTest("ARM compiler/linker required")
        from scripts.build_gr3_digital_hdf import official_rtos
        cls.rom = official_rtos()
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for name in ("m10v_adj_extra", "m10v_adj_extra_camera"):
                subprocess.run([compiler, "-target", "armv7a-none-eabi", "-marm",
                    "-mcpu=cortex-a9", "-ffreestanding", "-fno-builtin", "-Oz",
                    "-DM10V_ADJ_EXTRA_OWNER_OFFSET=0x6500", "-DM10V_ADJ_EXTRA_HDF=1",
                    "-DM10V_APPENDED_SLOTS=1", "-DM10V_BORDER_ENABLED=1",
                    "-c", ROOT / f"native/gr3/{name}.c", "-o", folder / f"{name}.o"],
                    check=True, capture_output=True)
            stub = folder / "stub.S"
            stub.write_text(".text\n.global m10v_adj_extra_camera_stock_slot_type\n"
                "m10v_adj_extra_camera_stock_slot_type:\nmov r0,#12\nbx lr\n"
                ".global m10v_camera_library_shooting_count\nm10v_camera_library_shooting_count:\nmov r0,#22\nbx lr\n")
            subprocess.run([compiler, "-target", "armv7a-none-eabi", "-c",
                stub, "-o", folder / "stub.o"], check=True)
            elf = folder / "image.elf"
            subprocess.run(["ld.lld", "-Ttext", hex(BASE), "-e", "m10v_adj_extra_camera_refresh",
                "-o", elf, *folder.glob("*.o")], check=True)
            objcopy = shutil.which("llvm-objcopy") or "/opt/homebrew/opt/llvm/bin/llvm-objcopy"
            nm = shutil.which("llvm-nm") or "/opt/homebrew/opt/llvm/bin/llvm-nm"
            subprocess.run([objcopy, "-O", "binary", elf, folder / "image.bin"], check=True)
            cls.code = (folder / "image.bin").read_bytes()
            cls.symbols = {name: int(addr, 16) for addr, _, name in (
                line.split() for line in subprocess.check_output([nm, elf], text=True).splitlines()
                if len(line.split()) == 3)}

    def setUp(self):
        self.u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        self.u.mem_map(0x53000000, max(0x1500000, (len(self.rom) + 0xfff) & ~0xfff))
        self.u.mem_write(0x53000000, self.rom)
        if not self.final:
            self.u.mem_write(BASE, self.code)
            hook = 0x531a2820
            target = self.symbols["m10v_adj_extra_camera_slot_type"]
            self.put(hook, 0xea000000 | (((target - hook - 8) >> 2) & 0xffffff))
        self.u.mem_map(0x55000000, 0x100000)
        self.put(0x55063910, 1)
        self.put(0x55063988, OWNER)
        self.put(ADJ, 0x53b394e0)
        self.put(ADJ + 0x180, FRAME)
        self.put(ADJ + 0x1f0, 0x55024000)
        for i in range(3):
            self.put(ADJ + 0x160 + i * 4, 0x55024100 + i * 0x100)
        self.cells = [0x55030000 + i * 0x200 for i in range(5)]
        self.icons = [0x55034000 + i * 0x200 for i in range(5)]
        for i, (cell, icon) in enumerate(zip(self.cells, self.icons)):
            self.put(ADJ + 0x16c + 4 * i, cell)
            self.put(ADJ + 0x184 + 4 * i, icon)
            self.put(icon + 4, PARENT)
        self.children = self.cells + [FRAME] + self.icons
        self.sync_children()
        self.files = {}
        self.writes = []
        self.geometry = {}
        self.geometry_writes = []
        self.labels = {}
        self.icon_values = {}
        self.allocations = []
        self.destroyed = []
        self.native_destroy_children = []
        self.visible = {}
        self.bindings = {}
        self.fail_insert = self.insertions = 0
        self.fail_write = False
        self.selected = []
        self.routes = []
        self.native_dispatch = False
        self.physical_switch = False
        self.real_caption = False
        self.run_native_setter = 0
        self.native_setters = []
        self.native_counts = []
        self.queued = []
        self.cursor = 0
        self.native_ids = self.rom[0xb4eba1:0xb4ebb3]
        self.setting_banks = [0x55028000 + i * 0x1000 for i in range(8)]
        self.native_records = {
            function: struct.unpack_from('<17I', self.rom, 0xb39a14 + function * 0x44)
            for function in self.native_ids
        }
        self.initial = 0
        self.route_enter_canvases = None
        self.entry_trace = []
        self.physical_trace = []
        self.trace_canvas_body = False
        self.trace_refresh_body = False
        self.native_transition_done = False
        self.put(0x55025008, 0x55025100)
        self.put(0x55025100, 0x55025200)
        self.u.mem_write(0x55025220, b"\1")
        self.put(0x55026004, 0x55028000)
        for i in range(5):
            self.u.mem_write(0x55028000 + 0x918 + 2 * i, b"\x0c")
        self.u.hook_add(UC_HOOK_CODE, self.service)
        self.call("init", OWNER)

    def put(self, addr, value):
        self.u.mem_write(addr, struct.pack("<I", value))

    def get(self, addr):
        return int.from_bytes(self.u.mem_read(addr, 4), "little")

    def sync_children(self):
        self.put(PARENT + 0xc, VECTOR)
        self.put(PARENT + 0x10, VECTOR + len(self.children) * 4)
        for i, value in enumerate(self.children):
            self.put(VECTOR + i * 4, value)

    def service(self, u, address, _size, _data):
        a, b, c, d = [u.reg_read(r) for r in REGS]
        result = 0
        if self.trace_refresh_body and address == 0x531a4168:
            u.reg_write(UC_ARM_REG_PC, 0x531a4114)
            return  # Keep the original Enter call frame, isolate the refresh.
        elif self.trace_refresh_body and address in (
            0x531a405c, 0x531a2fa8, 0x531a2be4, 0x531a2c28, 0x531a2cf0,
        ):
            pass
        elif self.trace_canvas_body and address == 0x5316d354:
            return  # Execute the final BIN's native canvas binder.
        elif self.trace_canvas_body and address == 0x5320b13c:
            result = 0x55026000
        elif self.trace_canvas_body and address in (0x53233874, 0x532338bc):
            pass  # Display service returns fallback and no alternate plane.
        elif self.trace_canvas_body and address == 0x532336c4:
            u.mem_write(a, struct.pack("<IIII", 0, 0, 720, 480))
        elif self.trace_canvas_body and address in (0x533ad308, 0x536b5604, 0x536b5d1c, KEY_STUB):
            pass
        elif self.final and self.native_transition_done and address == self.stock_dispatch:
            self.assertEqual(len(self.destroyed), 0)
            self.put(a + 4, 0)  # Canvas detach in the native transition.
            result = 1
        elif self.route_enter_canvases is not None and address in (
            0x5316dec0, 0x531a2a7c, 0x531a4408, 0x531a18dc, 0x531a1970,
            0x531a2934, 0x531a1898, 0x5326c1b4,
        ):
            pass  # Stock model/timer/keyboard and list services.
        elif self.route_enter_canvases is not None and address in (0x5316d354, 0x5316cb94):
            self.route_enter_canvases.append((address, tuple(self.children)))
            if address == 0x5316d354:
                self.put(a + 4, c)
        elif self.physical_switch and address in (
            0x5320b19c, 0x5320b73c, 0x5320b13c, 0x5320b3dc, 0x5320ae3c,
            0x5320bcdc, 0x5320c03c, 0x5320c120, 0x5320addc, 0x5320af5c,
            0x5320afbc, 0x5320b8bc, 0x5320b07c,
        ):
            result = KEY_SERVICE
        elif self.physical_switch and address == 0x5320b79c:
            result = KEY_NAVIGATION
        elif self.physical_switch and address == 0x5320aefc:
            result = KEY_QUEUE
        elif self.physical_switch and address == 0x5320b1fc:
            result = KEYBOARD
        elif self.physical_switch and address == 0x53228a90:
            result = ADJ
        elif self.physical_switch and address in (
            0x53229464, 0x5322ae44, 0x532b2618, 0x5322ce9c, KEY_STUB,
        ):
            pass
        elif self.final and address in (self.symbols.get("m10v_debug_log"), self.symbols.get("m10v_debug_batch")):
            if address == self.symbols.get("m10v_debug_log"):
                if 286 <= a <= 311:
                    self.entry_trace.append((a, b, c, d))
                elif a in (251, 252):
                    self.physical_trace.append((a, b, c, d))
        elif address == 0x53828014:
            result = 0x55025000
        elif address in (0x53825648, 0x53825fa8):
            name = bytes(u.mem_read(b, 12)).split(b"\0")[0]
            assert c == (24 if name.startswith(b"M10VHD") else 20)
            if address == 0x53825648:
                if name in self.files:
                    u.mem_write(d, self.files[name])
                    result = 1
            elif not self.fail_write:
                self.files[name] = bytes(u.mem_read(d, c))
                self.writes.append(name)
                result = 1
        elif address in (0x5320ad88, 0x5320b31c, 0x5320b67c, 0x5320ba9c):
            result = 0x55026000
        elif address == 0x532bd6b4:
            result = 25
        elif address == 0x532bd6d4:
            pass
        elif address in (0x5320aefc, 0x5320c03c):
            result = 0x55026000
        elif address == 0x53525d5c:
            result = 0x55026080
        elif address in (0x535493ac, 0x5354999c, 0x532dbda0):
            result = 1
        elif address == 0x532288b0:
            self.queued.append(b)
        elif address == 0x53293a30:
            if self.native_dispatch:
                return
            result = 200 + b
        elif address == 0x536af2a8:
            result = 0x55040000 + len(self.allocations) * 0x200
            self.allocations.append(result)
        elif address == 0x536b6de4 and a == PARENT + 8:
            self.insertions += 1
            if self.insertions != self.fail_insert:
                self.children.insert((b - VECTOR) // 4, self.get(c))
                self.sync_children()
                result = 1
        elif address == 0x536b6f68 and a == PARENT + 8:
            self.children.pop((b - VECTOR) // 4)
            self.sync_children()
        elif address == 0x533ac120:
            self.put(a + 4, b)
        elif address in (0x53393d84, 0x5339a908, 0x533ac568):
            self.geometry[a] = b
            self.geometry_writes.append(a)
        elif address in (0x53393d54, 0x5339a874):
            assert a not in self.children
            self.destroyed.append(a)
        elif address == 0x533ab548:
            self.labels[a] = struct.unpack("<4I", bytes(u.mem_read(b, 16)))
        elif address == 0x533ad3c0:
            self.visible[a] = b
        elif address == 0x533abeb0:
            self.bindings[a] = bytes(u.mem_read(self.get(b), 12))
        elif address == 0x5339a9a0:
            self.icon_values[a] = b
        elif self.real_caption and address in (0x53396f80, 0x53390ef8):
            return
        elif self.real_caption and address in (0x533abb68, 0x536b5d04, 0x533968e8, 0x533ad308):
            pass
        elif self.real_caption and address == 0x536af31c:
            result = 0x55027900
        elif address in (0x533ac1b4, 0x53393e00,
                0x53396f80, 0x53394e8c, 0x53390ef8, 0x533ab5d8):
            pass
        elif address == 0x533947f0:
            self.put(b, 0x11)
            self.u.mem_write(c, b"\x01\0")
            result = 1
        elif address == 0x531a4168:
            self.initial += 1
        elif (self.real_caption or self.trace_refresh_body) and address == 0x531a4114:
            return
        elif self.real_caption and address == self.stock_refresh:
            pass
        elif self.final and address == self.stock_destroy:
            self.native_destroy_children.append(tuple(self.children))
        elif address in (0x531a4480, 0x531a4114, 0x531a0150):
            pass
        elif address == 0x531a3100 and not self.native_dispatch:
            pass
        elif address == 0x53394820:
            result = self.cursor
        elif self.native_dispatch and any(address == r[10] for r in self.native_records.values()):
            self.native_setters.append((address, a, b))
            if address == self.run_native_setter:
                return
        elif self.native_dispatch and any(address == r[12] for r in self.native_records.values()):
            self.native_counts.append((address, a))
            result = 3
        elif address == 0x5316c9d8:
            self.routes.append((a, b, c))
        elif address == 0x531a4a80:
            self.routes.append((a, b, 0))
        elif self.final and address == self.symbols["m10v_camera_library_shooting_count"]:
            result = 22
        elif address == 0x531a4670:
            self.selected.append(u.reg_read(UC_ARM_REG_R5))
            return
        else:
            return
        u.reg_write(UC_ARM_REG_R0, result)
        u.reg_write(UC_ARM_REG_PC, u.reg_read(UC_ARM_REG_LR))

    def call(self, name, *args):
        if self.final and name == "initial_render":
            return self.execute(0x531a45d0, 0x531a45d4, *args)
        if self.final and name.startswith("touch"):
            return self.execute(0x531a48f0 + int(name[-1]) * 0x14, RETURN, *args)
        return self.execute(self.symbols["m10v_adj_extra_camera_" + name], RETURN, *args)

    def execute(self, entry, end, *args):
        for reg, value in zip(REGS, (*args, 0, 0, 0, 0)):
            self.u.reg_write(reg, value)
        self.u.reg_write(UC_ARM_REG_SP, 0x550ff000)
        self.u.reg_write(UC_ARM_REG_LR, RETURN)
        try:
            self.u.emu_start(entry, end, count=120000)
        except Exception as e:
            raise AssertionError(f"{entry:#x} at {self.u.reg_read(UC_ARM_REG_PC):#x}") from e
        self.assertEqual(self.u.reg_read(UC_ARM_REG_PC), end)
        self.assertEqual(self.u.reg_read(UC_ARM_REG_SP), 0x550ff000)
        return self.u.reg_read(UC_ARM_REG_R0)

    def assignments(self):
        for slot, function in enumerate((24, 25, 26, 27), 6):
            self.assertEqual(self.call("assign", slot, function), 1)

    def test_nine_simultaneous_positions_publish_only_after_all_insertions(self):
        self.assignments()
        self.call("initial_render", ADJ)
        self.assertEqual(self.initial, 1)
        self.assertEqual([self.geometry[c] for c in self.cells], [265, 315, 365, 415, 465])
        self.assertEqual([self.geometry[c] for c in self.allocations], [515, 565, 615, 665])
        self.assertTrue(all(self.visible[c] for c in self.allocations))
        self.assertEqual(self.labels[0x55024100], (0, 0, 255, 40))
        self.assertEqual(self.u.mem_read(ADJ + 0x1f4, 1), b"\0")
        self.call("retire", ADJ, 0)
        self.assertEqual(len(self.destroyed), 8)
        self.assertEqual(self.labels[0x55024100], (0, 0, 400, 40))
        self.assertEqual(len(self.children), 11)
        self.assertEqual([self.geometry[c] for c in self.cells], [425, 485, 545, 605, 665])

    def test_failed_extra_icon_insertion_keeps_the_stock_strip(self):
        self.assignments()
        self.fail_insert = 6
        self.call("refresh", ADJ)
        self.assertEqual(len(self.children), 11)
        self.assertTrue(all(c not in self.geometry for c in self.cells))
        self.assertEqual(len(self.destroyed), 6)
        self.call("retire", ADJ, 0)
        self.assertEqual(len(self.destroyed), 6)

    def test_journal_write_failure_keeps_previous_assignment(self):
        self.assignments()
        self.fail_write = True
        self.assertEqual(self.call("assign", 7, 27), 0)
        self.assertEqual(self.call("load", 0x55025300), 1)
        self.assertEqual(self.u.mem_read(0x55025300, 4), bytes((24, 25, 26, 27)))
        self.assertEqual(self.call("assign", 5, 27), 0)
        self.assertEqual(self.call("assign", 7, 31), 0)
        self.assertEqual(self.call("assign", 7, 15), 0)

    def test_native_functions_dispatch_without_persisting_virtual_slot(self):
        if not self.final:
            self.skipTest('requires the installed ADJ dispatch hooks')
        for i, bank in enumerate(self.setting_banks, 1):
            self.put(0x55026000 + i * 4, bank)
            self.u.mem_write(bank + 0x914, bytes([i % 5]))
        self.put(0x55026080, 0x55026000)
        self.native_dispatch = True
        for start in range(0, len(self.native_ids), 4):
            choices = self.native_ids[start:start + 4]
            for i, function in enumerate(choices):
                self.assertEqual(self.call("assign", 6 + i, function), 1)
            self.u.mem_write(ADJ + 0x1f4, b"\4")
            self.call("initial_render", ADJ)
            if not start:
                self.assertEqual(len(self.allocations), 4)
                self.assertTrue(all(self.visible[view] for view in self.allocations))
                for view, function in zip(self.allocations, choices):
                    self.assertEqual(self.icon_values[view + 0xf0],
                                     self.execute(0x53293a30, RETURN, 0, function))
            for i, function in enumerate(choices):
                with self.subTest(function=function):
                    self.cursor = i + 1
                    self.assertEqual(self.event(0xcf), 1)
                    self.assertEqual(self.call("slot_type", ADJ, i), function)
                    self.assertEqual(self.native_setters[-1], (self.native_records[function][10], ADJ, i + 1))
                    self.assertEqual(self.execute(0x531a31ac, RETURN, ADJ), 3)
                    self.assertEqual(self.native_counts[-1], (self.native_records[function][12], ADJ))
                    self.assertEqual([self.u.mem_read(bank + 0x914, 1)[0] for bank in self.setting_banks],
                                     [i % 5 for i in range(1, 9)])
                    self.assertEqual(self.event(0xd8), 0)
                    self.execute(0x531a4dbc, RETURN, ADJ, 0, 0, 0xd8)
                    self.assertEqual(self.queued[-1], 0x86)
            self.call("retire", ADJ, 0)
            self.assertEqual(self.u.mem_read(ADJ + 0x1f4, 1), b"\4")

        # Function 2's stock row mapping and property store both run in ROM.
        self.assertEqual(self.call("assign", 6, 2), 1)
        self.run_native_setter = self.native_records[2][10]
        self.cursor = 1
        self.call("initial_render", ADJ)
        self.assertEqual(self.event(0xcf), 1)
        setting = self.setting_banks[0] + 0x130
        self.assertEqual(self.get(setting), self.get(0x53b591e4))
        self.cursor = 2
        self.execute(0x531a3100, RETURN, ADJ)
        self.assertEqual(self.get(setting), self.get(0x53b591e8))
        self.call("retire", ADJ, 0)
        self.assertEqual(self.u.mem_read(ADJ + 0x1f4, 1), b"\4")
        self.execute(0x531a3100, RETURN, ADJ)
        self.assertEqual([self.u.mem_read(bank + 0x914, 1)[0] for bank in self.setting_banks], [4] * 8)

    def event(self, key):
        self.u.mem_write(0x55027000, struct.pack("<H", key))
        return self.call("event", ADJ, 0x55027000)

    def test_extra_focus_never_enters_stock_physical_index_or_movie_bank(self):
        self.assignments()
        self.u.mem_write(ADJ + 0x1f4, b"\4")
        movie = bytes(range(60))
        stock = bytes(range(60, 120))
        self.u.mem_write(ADJ + 0x1f8, stock + movie)
        self.call("refresh", ADJ)
        self.assertEqual(self.event(0xcf), 1)
        self.assertEqual(self.u.mem_read(ADJ + 0x1f4, 1), b"\0")
        self.assertEqual(self.call("slot_type", ADJ, 0), 0)
        self.assertEqual(self.event(0xd8), 1)
        self.assertEqual(self.event(0xcf), 1)
        self.assertEqual(self.event(0xd8), 1)
        self.assertEqual(self.event(0xcf), 1)
        self.assertEqual(self.event(0xd8), 1)
        self.assertEqual(self.event(0xcf), 1)
        self.assertEqual(self.event(0xd8), 1)
        self.assertEqual(self.routes, [
            (ADJ, 0x020000a0, 0x08000000), (ADJ, 0x0200f100, 0x08000000),
            (ADJ, 2, 0), (ADJ, 0x02000073, 0x08000000),
        ])
        self.assertEqual(self.selected, [0, 1, 2, 3])
        self.call("touch3", ADJ)
        self.assertEqual(self.call("slot_type", ADJ, 3), 12)
        self.assertEqual(self.selected, [0, 1, 2, 3, 3])
        self.assertEqual(self.u.mem_read(ADJ + 0x1f4, 1), b"\3")
        saved = stock[:52] + b"\x11\0\0\0\1\0" + stock[58:]
        self.assertEqual(self.u.mem_read(ADJ + 0x1f8, 120), saved + movie)

    def test_all_off_movie_and_queued_close_never_rebuild_extra_strip(self):
        self.call("refresh", ADJ)
        self.assertFalse(self.allocations)
        self.assertFalse(self.geometry)
        self.call("retire", ADJ, 0)
        self.assignments()
        self.u.mem_write(ADJ + 0x270, b"\1")
        self.call("refresh", ADJ)
        self.assertFalse(self.allocations)
        self.u.mem_write(ADJ + 0x270, b"\0")
        self.call("initial_render", ADJ)
        self.assertEqual(self.event(0x35), 0)
        geometry = dict(self.geometry)
        self.call("refresh", ADJ)
        self.assertEqual(self.event(0xcf), 0)
        self.call("retire", ADJ, 0)
        self.assertEqual(self.geometry, geometry)
        self.call("refresh", ADJ)
        self.assertEqual(self.geometry, geometry)
        self.assertEqual(len(self.allocations), 4)
        self.assertEqual(len(self.children), 11)
        self.assertEqual(len(self.destroyed), 8)

        self.files.clear()
        self.call("initial_render", ADJ)
        self.assertEqual([self.geometry[c] for c in self.cells], [425, 485, 545, 605, 665])
        self.assertEqual(len(self.allocations), 4)

    def test_native_touch_binding_carries_lifetime_and_yields_to_ab(self):
        self.assignments()
        self.call("initial_render", ADJ)
        binding = self.bindings[self.allocations[1] + 0xf0]
        self.u.mem_write(0x55027504, binding)
        self.put(0x55027500, 0x55027504)
        self.call("suspend", ADJ, 1)
        self.execute(0x531a1874, RETURN, 0x55027500)
        self.assertEqual(self.selected, [])
        self.call("suspend", ADJ, 0)
        self.execute(0x531a1874, RETURN, 0x55027500)
        self.assertEqual(self.selected, [1])
        self.call("retire", ADJ, 0)
        self.call("initial_render", ADJ)
        self.execute(0x531a1874, RETURN, 0x55027500)
        self.assertEqual(self.selected, [1])

    def native_event(self, key):
        self.u.mem_write(0x55027000, struct.pack("<H", key))
        return self.execute(0x531a4db8, RETURN, ADJ, 0x55027000)

    def test_physical_adj_exits_private_shortcut_instead_of_opening_child(self):
        if not self.final:
            self.skipTest("requires the installed HDF/A-B event chain")
        self.assertEqual(self.call("assign", 6, 27), 1)
        self.u.mem_write(ADJ + 0x1f4, b"\4")
        self.call("initial_render", ADJ)
        self.assertEqual(self.native_event(0xcf), 1)
        self.assertEqual(self.native_event(0x1e), 0)
        self.assertEqual(self.native_event(0xd8), 0)
        self.assertEqual(self.queued, [0x86])
        self.assertEqual(self.routes, [])
        geometry, children = dict(self.geometry), list(self.children)
        self.execute(0x531a3e88, RETURN, ADJ)
        self.assertEqual(self.geometry, geometry)
        self.assertEqual(self.children, children)
        self.assertEqual(self.destroyed, [])
        self.call("refresh", ADJ)
        self.assertEqual(len(self.allocations), 1)

    def test_private_navigation_sets_real_native_caption_without_reinterpreting_its_flags(self):
        if not self.final:
            self.skipTest("requires the installed ADJ event chain")
        self.real_caption = True
        # Decode the type17 title descriptor through the genuine native factory.
        title = self.execute(0x533ad7f0, RETURN, 0x53b39574)
        self.assertEqual(self.get(title), 0x53c0a378)
        self.assertEqual(self.get(title + 0xf0), 0x01000000)
        self.put(ADJ + 0x160, title)
        self.assertEqual(self.call("assign", 6, 27), 1)
        self.assertEqual(self.call("assign", 9, 24), 1)
        self.u.mem_write(ADJ + 0x1f4, b"\4")
        self.call("initial_render", ADJ)
        self.assertEqual(self.native_event(0xcf), 1)
        self.assertEqual(int.from_bytes(self.u.mem_read(title + 0xea, 2), "little"), 1199)
        self.assertEqual(self.get(title + 0xf0), 0x01000000)
        self.call("touch0", ADJ)
        self.assertEqual(self.native_event(0xce), 1)
        self.assertEqual(int.from_bytes(self.u.mem_read(title + 0xea, 2), "little"), 1196)
        self.assertEqual(self.get(title + 0xf0), 0x01000000)

    def test_physical_adj_exits_hdf_without_saving_highlighted_value(self):
        if not self.final:
            self.skipTest("requires the installed HDF/A-B event chain")
        self.assertEqual(self.call("assign", 6, 20), 1)
        self.u.mem_write(ADJ + 0x1f4, b"\4")
        self.put(self.hdf_cache, 0x100)
        self.put(self.hdf_cache + 4, 0x43464448)
        self.call("initial_render", ADJ)
        self.assertEqual(self.native_event(0xcf), 1)
        self.assertEqual(self.get(self.hdf_cache + 8), ADJ)
        self.cursor = 2
        self.assertEqual(self.native_event(0x1e), 0)
        self.assertEqual(self.native_event(0xd8), 0)
        self.assertEqual(self.queued, [0x86])
        self.assertFalse(any(name.startswith(b"M10VHD") for name in self.writes))
        self.assertEqual(self.get(self.hdf_cache + 8), 0)

    def test_logged_native_exit_defers_widget_mutation_until_next_open(self):
        if not self.final:
            self.skipTest("requires the installed HDF/A-B exit chain")
        self.assignments()
        self.call("initial_render", ADJ)
        geometry, labels = dict(self.geometry), dict(self.labels)
        children = list(self.children)
        binding = self.bindings[self.allocations[0] + 0xf0]
        self.u.mem_write(0x55027504, binding)
        self.put(0x55027500, 0x55027504)

        # Captured on device (build 85f8c5f5, sequence 936–948).
        self.assertEqual(self.native_event(0x2), 0)
        self.assertEqual(self.native_event(0x88), 0)
        self.execute(0x531a3e88, RETURN, ADJ)
        self.assertEqual(self.geometry, geometry)
        self.assertEqual(self.labels, labels)
        self.assertEqual(self.children, children)
        self.assertEqual(self.destroyed, [])

        # A queued touch/refresh may still arrive during native LiveView entry.
        self.execute(0x531a1874, RETURN, 0x55027500)
        self.call("touch1", ADJ)
        self.call("refresh", ADJ)
        self.assertEqual(self.selected, [])
        self.assertEqual(len(self.allocations), 4)

        self.call("initial_render", ADJ)
        self.assertEqual(len(self.destroyed), 8)
        self.assertEqual(len(self.allocations), 8)
        self.assertEqual(len(self.children), len(children))
        self.assertEqual([self.geometry[c] for c in self.cells], [265, 315, 365, 415, 465])

        # The other safe endpoint is native destruction with the parent still
        # valid. The original destructor must receive only its stock views.
        self.execute(0x531a3e88, RETURN, ADJ)
        self.assertEqual(len(self.destroyed), 8)
        self.execute(0x5319ff24, RETURN, ADJ)
        self.assertEqual(len(self.destroyed), 16)
        self.assertEqual(self.native_destroy_children, [tuple(self.cells + [FRAME] + self.icons)])
        self.call("retire", ADJ, 1)
        self.assertEqual(len(self.destroyed), 16)

    def test_border_assignment_opens_only_existing_border_child(self):
        self.assertEqual(self.call("assign", 6, 28), 1)
        self.assertEqual(self.call("load", 0x55025300), 1)
        self.assertEqual(bytes(self.u.mem_read(0x55025300, 4)), bytes((28, 0, 0, 0)))
        self.u.mem_write(ADJ + 0x1f4, b"\4")
        self.call("initial_render", ADJ)
        self.assertEqual(self.event(0xcf), 1)
        self.assertEqual(self.call("slot_type", ADJ, 0), 0)
        self.assertEqual(self.event(0xd8), 1)
        self.assertEqual(self.routes, [(ADJ, 0x0200f108, 0x08000000)])
        self.assertFalse(any(name.startswith(b"BORDER") for name in self.writes))


    def enable_physical_switch(self):
        self.physical_switch = True
        self.put(KEYBOARD, KEYBOARD + 0x800)
        self.put(KEYBOARD + 0x810, 0x532231e4)
        self.put(KEY_SERVICE, KEY_SERVICE + 0x30)
        self.put(KEY_SERVICE + 0x38, KEY_STUB)
        self.put(KEY_QUEUE, 0x02000000)
        self.execute(0x53225a4c, RETURN, KEY_NAVIGATION)
        self.u.mem_write(KEYBOARD + 0xbf + 0x1e, b"\2")
        self.put(ADJ + 0x124, 0x02000000)

    def dispatch(self, key, payload=0):
        self.u.mem_write(0x55027000, struct.pack("<III", key, payload, 0))
        return self.execute(0x5316d5dc, RETURN, ADJ, 0x55027000)

    def press_physical_lever(self):
        for phase, value in ((1, 1), (2, 0)):
            self.u.mem_write(0x55027010, struct.pack("<II", phase, value))
            self.dispatch(0x1e, 0x55027010)

    def test_physical_lever_confirm_survives_queued_property_notification(self):
        if not self.final:
            self.skipTest("requires installed BaseController and native keyboard chain")
        self.enable_physical_switch()
        self.assertEqual(self.call("assign", 6, 24), 1)
        self.u.mem_write(ADJ + 0x1f4, b"\4")
        self.call("initial_render", ADJ)
        self.assertEqual(self.native_event(0xcf), 1)

        self.press_physical_lever()
        self.assertEqual(self.queued, [0xd8])
        # The native keyboard queues the confirmation. A previously queued
        # property notification can run before that newly appended event.
        self.dispatch(0x18d)
        self.dispatch(self.queued[0])
        self.assertEqual(self.queued, [0xd8, 0x86])
        self.assertEqual(self.routes, [])
        self.dispatch(self.queued[1])
        self.assertEqual(self.routes, [(ADJ, 0x08000000, 0x10000000)])

    def test_physical_lever_uses_stock_exit_with_stock_focus(self):
        if not self.final:
            self.skipTest("requires installed BaseController and native keyboard chain")
        self.enable_physical_switch()
        self.assertEqual(self.call("assign", 6, 24), 1)
        self.call("initial_render", ADJ)

        self.press_physical_lever()
        self.assertEqual(self.queued, [0xd8])
        self.dispatch(0x18d)
        self.dispatch(self.queued[0])
        self.assertEqual(self.queued, [0xd8, 0x86])
        self.assertEqual(self.routes, [])
        self.dispatch(self.queued[1])
        self.assertEqual(self.routes, [(ADJ, 0x08000000, 0x10000000)])

    def test_private_menu_close_routes_to_liveview_then_adj_reopens(self):
        if not self.final:
            self.skipTest("requires the installed native ADJ vtable and enter callback")
        self.put(ADJ + 0x124, 0x02000000)
        for slot, function in enumerate((28, 24, 27, 25), 6):
            self.assertEqual(self.call("assign", slot, function), 1)
        self.u.mem_write(ADJ + 0x1f4, b"\4")
        self.call("initial_render", ADJ)
        stock = tuple(self.cells + [FRAME] + self.icons)
        self.put(ADJ + 0x15c, PARENT)
        for i, destination in enumerate((0x0200f108, 0x020000a0, 0x02000073, 0x0200f100)):
            with self.subTest(destination=hex(destination)):
                self.route_enter_canvases = None
                icon = self.allocations[-4 + i] + 0xf0
                self.u.mem_write(0x55027504, self.bindings[icon])
                self.put(0x55027500, 0x55027504)
                self.execute(0x531a1874, RETURN, 0x55027500)
                self.assertEqual(self.event(0xd8), 1)
                self.assertEqual(self.routes[-1][:2], (ADJ, destination))
                parent = self.routes[-1][2]
                self.execute(0x531a3e88, RETURN, ADJ)  # Stock ADJ exit callback.
                self.put(ADJ + 4, 0)  # Native exit detaches the old canvas.
                child, vtable = 0x5502b000, 0x5502b800
                self.put(child, vtable)
                self.put(vtable + 0x18, 0x5316c74c)
                self.put(vtable + 0x1c, 0x5316c750)
                self.u.mem_write(child + 0x14c, b"\0")
                self.route_enter_canvases = []
                # Native base Enter stores the parent from the opening event.
                self.execute(0x5316dfa8, RETURN, child, destination, parent, 0)
                # The native helper used by each child on close consumes it.
                self.assertEqual(self.execute(0x5316ca28, RETURN, child), 1)
                close_route = self.routes[-1]
                self.assertEqual(self.u.mem_read(child + 0x154, 1), b"\1")
                self.route_enter_canvases.clear()
                # The next user ADJ press comes from LiveView, as on initial open.
                self.execute(self.get(0x53b394e0 + 0x14), RETURN,
                    ADJ, 0x02000000, 0x08000000, 0)
                self.assertEqual(self.route_enter_canvases, [(0x5316d354, stock), (0x5316cb94, stock)])
                self.assertEqual(len(self.children), len(stock) + 8)
                self.assertEqual(len(self.destroyed), 8 * (i + 1))
                self.assertEqual(close_route, (child, 0x08000000, 0x10000000))

    def test_selection_refresh_does_not_move_the_fixed_strip(self):
        self.assignments()
        self.call("initial_render", ADJ)
        self.geometry_writes.clear()
        self.call("touch1", ADJ)
        self.call("refresh", ADJ)
        self.assertIn(FRAME, self.geometry_writes)
        self.assertFalse(set(self.cells + self.icons).intersection(self.geometry_writes))

    def test_adj_widgets_are_released_after_native_close_before_next_enter(self):
        if not self.final:
            self.skipTest("requires installed route and exit hooks")
        self.put(ADJ + 0x124, 0x02000000)
        self.put(ADJ + 4, PARENT)
        self.assignments()
        self.call("initial_render", ADJ)
        stock_children = self.cells + [FRAME] + self.icons
        geometry = dict(self.geometry)
        self.execute(0x531a3e88, RETURN, ADJ)
        self.assertEqual(len(self.destroyed), 0)
        self.native_transition_done = True
        self.put(0x55027010, 0x08000000)
        self.assertEqual(self.dispatch(0x193, 0x55027010), 1)
        self.assertEqual(self.children, stock_children)
        self.assertEqual(len(self.destroyed), 8)
        self.assertEqual(self.geometry, geometry)
        self.call("refresh", ADJ)  # A retired controller still rejects late refresh.
        self.assertEqual(len(self.allocations), 4)


    def test_installed_diagnostic_entry_probes_preserve_native_canvas_arguments(self):
        if "m10v_adj_extra_camera_trace_canvas" not in self.symbols:
            self.skipTest("requires installed ADJ diagnostic call sites")
        self.put(ADJ + 0x15c, PARENT)
        self.route_enter_canvases = []
        self.execute(self.get(0x53b394e0 + 0x14), RETURN,
                     ADJ, 0x02000000, 0x08000000, 0)
        self.assertEqual([row[0] for row in self.entry_trace], list(range(286, 296)))
        self.assertTrue(all(row[1] == ADJ for row in self.entry_trace))
        self.assertEqual(self.entry_trace[6:8], [(292, ADJ, 0, PARENT), (293, ADJ, 0, PARENT)])
        self.assertEqual(self.get(ADJ + 4), PARENT)


    def test_installed_diagnostic_records_physical_adj_release_from_liveview(self):
        if "m10v_adj_extra_camera_trace_canvas" not in self.symbols:
            self.skipTest("requires installed ADJ diagnostic call sites")
        self.native_transition_done = True  # Isolate stock event forwarding.
        self.put(ADJ + 0x124, 0x08000000)
        self.u.mem_write(0x55027010, struct.pack("<II", 2, 0))
        self.assertEqual(self.dispatch(0x1e, 0x55027010), 1)
        self.assertEqual(self.physical_trace, [(251, ADJ, 0x1e, 2), (252, ADJ, 0x1e, 1)])


    def test_installed_diagnostic_canvas_walk_forwards_to_native_callbacks(self):
        if "m10v_adj_extra_camera_trace_area" not in self.symbols:
            self.skipTest("requires installed canvas diagnostics")
        self.trace_canvas_body = True
        self.route_enter_canvases = []
        self.put(ADJ + 0x15c, PARENT)
        vtable = 0x5502b800
        self.put(PARENT, vtable)
        for offset in (0x18, 0x28, 0x34):
            self.put(vtable + offset, KEY_STUB)
        self.execute(self.get(0x53b394e0 + 0x14), RETURN,
                     ADJ, 0x02000000, 0x08000000, 0)
        self.assertEqual([row[0] for row in self.entry_trace],
                         [*range(286, 293), 304, 305, *range(298, 304), 293, 294, 295])
        self.assertEqual(self.get(ADJ + 4), PARENT)
        self.entry_trace.clear()
        self.put(ADJ + 4, 0)
        self.execute(0x5316d354, RETURN, ADJ, 0, PARENT)
        self.assertEqual(self.entry_trace, [])
        self.assertEqual(self.get(ADJ + 4), PARENT)


    def test_installed_diagnostic_refresh_walk_records_stock_calls_in_order(self):
        if "m10v_adj_extra_camera_trace_list" not in self.symbols:
            self.skipTest("requires installed refresh diagnostics")
        self.trace_refresh_body = True
        self.route_enter_canvases = []
        self.put(ADJ + 0x15c, PARENT)
        self.execute(self.get(0x53b394e0 + 0x14), RETURN,
                     ADJ, 0x02000000, 0x08000000, 0)
        self.assertEqual([row[0] for row in self.entry_trace],
                         [*range(306, 312), *range(286, 296)])
        self.assertEqual(self.get(ADJ + 4), PARENT)


    def test_native_invalidation_cannot_visit_retired_extra_views(self):
        if not self.final:
            self.skipTest("requires installed native ADJ exit and route callbacks")
        self.put(ADJ + 0x124, 0x02000000)
        self.put(ADJ + 4, PARENT)
        self.assignments()
        self.call("initial_render", ADJ)
        tile, icon = self.allocations[0], self.allocations[0] + 0xf0
        # Model two real overlap registrations. Both directions are entered
        # by the camera's own View overlap callback and vector insert.
        stock_peer = self.icons[0]
        # Skip the platform paint notification while preserving the native
        # invalidation traversal and its bidirectional stock dependency.
        self.put(PARENT, 0x5502b800)
        self.put(0x5502b800 + 0x44, KEY_STUB)
        self.put(KEY_STUB, 0xe12fff1e)  # bx lr
        for i, view in enumerate((PARENT, FRAME, tile, icon, stock_peer)):
            storage = 0x5502c000 + 0x20 * i
            self.put(view + 0x88, storage)
            self.put(view + 0x8c, storage)
            self.put(view + 0x90, storage + 0x20)
            self.u.mem_write(view + 0x64, struct.pack("<4I", 265, 5, 50, 50))
            self.u.mem_write(view + 0x9e, b"\1")
        self.execute(0x533ace44, RETURN, PARENT, tile)
        self.execute(0x533ace44, RETURN, FRAME, icon)
        self.execute(0x533ace44, RETURN, PARENT, stock_peer)
        self.assertEqual(self.get(self.get(PARENT + 0x88)), tile)
        self.assertEqual(self.get(self.get(FRAME + 0x88)), icon)

        self.execute(0x531a3e88, RETURN, ADJ)
        self.native_transition_done = True
        self.put(0x55027010, 0x08000000)
        self.assertEqual(self.dispatch(0x193, 0x55027010), 1)
        self.assertEqual(len(self.destroyed), 8)
        # Freed heap is intentionally unmapped. Run the original invalidate
        # path that device logs reach, rather than just inspecting the vector.
        self.u.mem_unmap(0x55040000, 0x1000)
        self.execute(0x533ad308, RETURN, PARENT)
        self.execute(0x533ad308, RETURN, FRAME)
        self.assertEqual(self.get(PARENT + 0x88) + 4, self.get(PARENT + 0x8c))
        self.assertEqual(self.get(self.get(PARENT + 0x88)), stock_peer)
        self.assertEqual(self.get(FRAME + 0x88), self.get(FRAME + 0x8c))
