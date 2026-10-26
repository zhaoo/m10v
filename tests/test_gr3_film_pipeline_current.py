"""Current ten-slot ABI: real Still Make to encoder admission, no completion stub.

The ISP hardware and filesystem are not emulated. The tests deliberately fail
on pixel/cache/allocation access in an authenticated native-only capture.
"""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import zlib
from unicorn import UC_HOOK_CODE
from unicorn import arm_const as A
from tests.test_gr3_isp_base import StockISP, ROOT


class CurrentFilmPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        official = ROOT / 'builds/gr3-extension-validation/official-rtos.bin'
        cls.rom = official.read_bytes()
        assert hashlib.sha256(cls.rom).hexdigest() == '8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67'
        delivery = os.environ.get('M10V_CURRENT_PIPELINE_CANDIDATE')
        if delivery:
            folder = Path(delivery)
            cls.manifest = json.loads((folder / 'M10V-runtime-manifest.json').read_text())
            receipt = json.loads((folder / 'M10V-build-receipt.json').read_text())
            binary = folder / 'fwdc239b.bin'
            assert hashlib.sha256(binary.read_bytes()).hexdigest() == receipt['candidate_sha256']
            js = "import{readFileSync}from'node:fs';import{decodeFrameMap}from'./node/gr3-frames.mjs';const b=readFileSync(process.argv[1]),d=decodeFrameMap(b,b.readUInt32LE(b.length-8)).decoded;process.stdout.write(d.subarray(0x10870,0x10870+d.readUInt32LE(0x1086c)));"
            cls.image = subprocess.check_output(['node', '--input-type=module', '-e', js, str(binary)], cwd=ROOT)
        else:
            cls.temp = tempfile.TemporaryDirectory()
            cls.addClassCleanup(cls.temp.cleanup)
            folder = Path(cls.temp.name)
            subprocess.run(['node', 'scripts/export_gr3_m10v_native.mjs', str(folder)],
                cwd=ROOT, check=True, capture_output=True)
            cls.manifest = json.loads((folder / 'M10V-runtime-manifest.json').read_text())
            js = "import{readFileSync}from'node:fs';import{decodeFrameMap}from'./node/gr3-frames.mjs';const b=readFileSync(process.argv[1]),d=decodeFrameMap(b,b.readUInt32LE(b.length-8)).decoded;process.stdout.write(d.subarray(0x10870,0x10870+d.readUInt32LE(0x1086c)));"
            cls.image = subprocess.check_output(['node', '--input-type=module', '-e', js, str(folder / 'fwdc239b.bin')], cwd=ROOT)
        offset = cls.manifest['base'] - 0x53000000
        runtime = cls.image[offset:offset + cls.manifest['code_bytes']]
        assert hashlib.sha256(runtime).hexdigest() == cls.manifest['code_sha256']

    def call(self, e, name, *args):
        e.call(self.manifest['symbols'][name], *args)
        return e.u.reg_read(A.UC_ARM_REG_R0)

    def fixture(self, film=66, slot=0):
        e = StockISP(self.image)
        recipe = e.alloc(0x5140)
        e.w32(recipe, 0x53d0fc90)
        e.w32(recipe + 0x4778, 0x31545653)
        obj = e.cursor
        e.make(25 + slot, 1)
        frame = obj + 0x1400
        si = int.from_bytes(e.u.mem_read(frame + 0x82d0, 4), 'little')
        # Stage1 uses the embedded sub-shot; encoder identity remains base SI.
        e.u.mem_write(si + 0x77c, bytes([25 + slot]))
        request = e.alloc(0x40)
        e.w32(recipe + 0x44c8, si)
        e.w32(recipe + 0x5c, request)
        # Run the original setup writes, not a guessed context offset.
        e.u.reg_write(A.UC_ARM_REG_R0, recipe)
        e.u.reg_write(A.UC_ARM_REG_R4, recipe)
        e.u.emu_start(0x5350eb10, 0x5350eb38, count=100)
        state = bytearray(184)
        struct.pack_into('<IHHI', state, 0, 0x5630314d, 5, 184, 7)
        # Earlier slots are valid distinct enabled films; trailing slots empty.
        for index in range(slot + 1):
            struct.pack_into('<H6B', state, 12 + 8 * index,
                film if index == slot else 34 + index, 0, 0, 0, 3, 5, 2)
        struct.pack_into('<I', state, 180, zlib.crc32(state[:180]))
        data = e.alloc(184)
        e.u.mem_write(data, bytes(state))
        self.assertEqual(self.call(e, 'm10v_isp_frame_recipe_snapshot', recipe, data), 1)
        return e, recipe, obj, frame, si, request, data

    def make(self, e, recipe, obj, frame):
        for reg, value in ((0, obj), (1, frame), (3, 0x536dd8f0), (6, recipe + 0x96c)):
            e.u.reg_write(getattr(A, 'UC_ARM_REG_R' + str(reg)), value)
        e.u.reg_write(A.UC_ARM_REG_SP, 0x5effff00)
        e.u.reg_write(A.UC_ARM_REG_LR, 0x53501d6c)
        e.u.emu_start(0x53501d68, 0x53501d6c, count=5000000)
        self.assertEqual(e.u.reg_read(A.UC_ARM_REG_PC), 0x53501d6c)

    def capture(self, e, recipe, si, request):
        context = recipe + 0x9b8
        for offset, value in ((0, 0x53d0fbe0), (0x30, recipe + 0x1a8),
                (0x34, si), (0x38, request), (0x3c, recipe + 0xb0),
                (0x40, recipe + 0xd0), (0x44, recipe + 0xf0),
                (0x48, recipe + 0x110), (0x4c, recipe + 0x130)):
            e.w32(context + offset, value)
        e.w32(request, 0x53d0fe60)
        e.u.mem_write(request + 12, b'\1\1')
        e.u.mem_write(recipe + 0x140, b'\1')
        e.w32(recipe + 0x60, 0x70000000)
        dimensions = e.alloc(4)
        e.u.mem_write(dimensions, struct.pack('<HH', 6112, 4064))
        e.w32(recipe + 0x230, dimensions)
        # 24MP image planes intentionally unmapped: native-only must not access them.
        e.u.mem_write(recipe + 0xb0, struct.pack('<4I8H', 1, 0x65000000, 0x68000000, 0, 6000, 4000, 6000, 4000, 0, 0, 2, 0))
        e.u.mem_write(recipe + 0x110, struct.pack('<4I8H', 1, 0x6b000000, 0x6b100000, 0, 720, 480, 720, 480, 0, 0, 2, 0))
        forbidden = {0x536af2a8, 0x5383c8a8, 0x53828014,
            self.manifest['symbols']['m10v_camera_library_load']}
        def boundary(u, at, n, _):
            if at in forbidden:
                raise AssertionError(f'native-only capture reached pixel/allocation/filesystem boundary {at:#x}')
            if self.manifest['debug_mode'] and at == self.manifest['symbols']['m10v_debug_batch']:
                # SD transport is external. Timing and control still run real code.
                u.reg_write(A.UC_ARM_REG_R0, 0)
                u.reg_write(A.UC_ARM_REG_PC, u.reg_read(A.UC_ARM_REG_LR))
        e.u.hook_add(UC_HOOK_CODE, boundary)
        return self.call(e, 'm10v_capture_library', context)

    def test_5207_and_5219_actual_still_completion_reaches_24mp_zero_pixel_fast_path(self):
        for film in (62, 66):
            for slot in (0, 4, 9):
                with self.subTest(film=film, slot=slot):
                    e, recipe, obj, frame, si, request, data = self.fixture(film, slot)
                    self.make(e, recipe, obj, frame)
                    self.assertEqual(self.call(e, 'm10v_isp_frame_recipe_completed', recipe, si, 25 + slot, data), 1)
                    self.assertEqual(self.capture(e, recipe, si, request), 0)

    def test_repeated_still_make_does_not_accumulate_color_banks(self):
        for film in (62, 66):
            e, recipe, obj, frame, *_ = self.fixture(film)
            self.make(e, recipe, obj, frame)
            first = bytes(e.u.mem_read(frame, 0x9000))
            for _ in range(3):
                self.make(e, recipe, obj, frame)
                self.assertEqual(bytes(e.u.mem_read(frame, 0x9000)), first)

    def test_ordinary_builtin_profiles_complete_under_native_parameter_changes(self):
        for film in range(33, 79):
            for extra in ({}, {0x77d: 1, 0x77e: 7, 0x780: 2, 0x793: 6, 0x794: 2}):
                with self.subTest(film=film, extra=extra):
                    e, recipe, obj, frame, si, request, data = self.fixture(film)
                    for offset, value in extra.items():
                        e.u.mem_write(si + 0x71248 + offset, bytes([value]))
                    self.make(e, recipe, obj, frame)
                    self.assertEqual(self.call(e, 'm10v_isp_frame_recipe_completed', recipe, si, 25, data), 1)
                    self.assertEqual(self.capture(e, recipe, si, request), 0)

    def test_fitted_builtin_films_use_isp_for_stills_without_pixel_fallback(self):
        # User-approved ISP approximation: the same profiles already used by
        # live view must also own still color, including IDs beyond 78.
        for film in (77, 298, *range(291, 298), *range(299, 306)):
            with self.subTest(film=film):
                e, recipe, obj, frame, si, request, data = self.fixture(film)
                self.make(e, recipe, obj, frame)
                self.assertEqual(self.call(e, 'm10v_isp_frame_recipe_completed', recipe, si, 25, data), 1)
                self.assertEqual(self.capture(e, recipe, si, request), 0)

    def test_charmera_and_pixel_do_not_claim_native_color_completion(self):
        for film in (289, 290):
            e, recipe, obj, frame, si, request, data = self.fixture(film)
            self.make(e, recipe, obj, frame)
            self.assertEqual(self.call(e, 'm10v_isp_frame_recipe_completed', recipe, si, 25, data), 0)

    def test_wrong_frame_or_changed_configuration_cannot_skip_cpu_color(self):
        e, recipe, obj, frame, si, request, data = self.fixture()
        self.make(e, recipe, obj, frame)
        self.assertEqual(self.call(e, 'm10v_isp_frame_recipe_completed', recipe, si + 4, 25, data), 0)
        self.assertEqual(self.call(e, 'm10v_isp_frame_recipe_completed', recipe, si, 26, data), 0)
        changed = bytearray(e.u.mem_read(data, 184))
        struct.pack_into('<I', changed, 8, 8)
        struct.pack_into('<I', changed, 180, zlib.crc32(changed[:180]))
        e.u.mem_write(data, bytes(changed))
        self.assertEqual(self.call(e, 'm10v_isp_frame_recipe_completed', recipe, si, 25, data), 0)

if __name__ == '__main__':
    unittest.main()
