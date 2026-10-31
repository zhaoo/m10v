"""Execute genuine producer/settings/query/execution ingress with pure helpers.

Only camera cache, native shade/Clarity endpoints, queue and render are service
doubles. CPU RNG and photo pixels remain unavailable; no hardware claim.
"""
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest

from scripts.build_gr3_isp_recipe_color import build as build_recipe
from scripts.build_gr3_native_grain_hooks import build as build_grain, HELPERS
from tests.test_gr3_isp_base import StockISP, BASE
from tests import test_gr3_isp_effects_pipeline as pipeline_case
from unicorn import UC_HOOK_CODE
from unicorn import arm_const as A

ROOT = Path(__file__).resolve().parents[1]


class PureCaptureHooksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = (ROOT / 'builds/gr3-extension-validation/official-rtos.bin').read_bytes()
        pipeline_case.EffectsPipelineTests.setUpClass.__func__(cls)
        cls.addClassCleanup(cls.temp.cleanup)
        cls.pipeline_code, cls.pipeline_exports = cls.code, cls.symbols
        names = ('m10v_library_valid', 'm10v_library_tables', 'm10v_camera_library_preview',
            'm10v_camera_library_custom_profile', 'm10v_camera_library_mutation_busy',
            'm10v_hdf_reserve', 'm10v_hdf_task_snapshot', 'm10v_hdf_settings', 'm10v_hdf_done')
        cls.external = {name: 0x541F0000 + i * 4 for i, name in enumerate(names)}
        cls.external.update(cls.pipeline_exports)
        cls.owner = {'storage': {'color_offset': 0x4A08, 'color_bytes': 1796,
            'extended_recipe_bytes': 0x57D8, 'stamp_offset': 0x5140, 'stamp_bytes': 16},
            'patches': [{'address': 0x53523E0C}]}
        with tempfile.TemporaryDirectory() as folder:
            cls.recipe_code, cls.recipe_manifest = build_recipe(folder, cls.rom, cls.external,
                cls.owner, observer=False, producer_snapshot=True, native_color=True,
                native_grain=True, shared_hdf=True, pure_isp_effects=True)
            cls.grain_code, cls.grain_manifest = build_grain(folder, 0x541A0000,
                {**cls.recipe_manifest['exports'], **cls.pipeline_exports}, cls.rom,
                pure_isp_effects=True)

    def fixture(self, available=True):
        image = bytearray(self.rom)
        blocks = ((0x54180000, self.recipe_code), (0x541A0000, self.grain_code),
                  (pipeline_case.shot_case.BASE, self.pipeline_code), (0x541F0000, bytes(128)))
        for address, code in blocks:
            end = address - BASE + len(code)
            if end > len(image):
                image.extend(bytes(end - len(image)))
            image[address - BASE:end] = code
        patches = self.recipe_manifest['patches'] + self.grain_manifest['patches']
        patches += [self.grain_manifest['pure_isp_query_patch']]
        for patch in patches:
            image[patch['address'] - BASE:patch['address'] - BASE + 4] = bytes.fromhex(patch['replacement_hex'])
        e = StockISP(image)
        recipe = e.alloc(0x57D8)
        si = e.alloc(0x80000)
        owner, plan = e.alloc(0xB00), e.alloc(0x300)
        e.w32(recipe, 0x53D0FC90)
        e.w32(recipe + 0x4778, 0x31545653)
        e.w32(recipe + 0x44C8, si)
        context = recipe + 0x4320
        e.w32(context, 0x53D0FC60)
        e.w32(context + 0x30, recipe + 0x1A8)
        e.w32(context + 0x34, si)
        e.w32(recipe + 0x1C, plan)
        e.u.mem_write(plan + 0x204, struct.pack('<H', 19))
        e.w32(owner + 0x9B4 + 19 * 4, 0x60030000)
        e.u.mem_write(si + 0x77C, b'\x0B')  # stock Standard, no film cache
        e.u.mem_write(si + 0x794, b'\x04')
        e.u.mem_write(si + 0x795, b'\x03')
        e.events, e.rendered, e.cache_available = [], [], available
        e.hold_reached = False
        e.frozen = (0, 0, 0, 0, 0, 0, 0, 0)
        addresses = {address: name for name, address in self.external.items() if name.startswith(('m10v_hdf_', 'm10v_camera_library_', 'm10v_library_'))}
        def services(u, pc, size, data):
            if pc == 0x5368A92C:
                self.fail('original CPU RNG was reached')
            if pc == 0x536B0A74:
                e.hold_reached = True
                u.emu_stop()
                return
            if pc == 0x53000100:
                e.events.append('cache')
                if e.cache_available:
                    u.mem_write(u.reg_read(A.UC_ARM_REG_R0), struct.pack('<8I', *e.frozen))
                    e.w32(u.reg_read(A.UC_ARM_REG_R1), 7)
                result = int(e.cache_available)
            elif pc == 0x53000200:
                e.rendered.append(tuple(u.reg_read(getattr(A, f'UC_ARM_REG_R{i}')) for i in range(4)))
                result = getattr(e, 'render_result', 1)
            elif pc == 0x53000300:
                result = 1  # Bounded diagnostic service, no completion/state writes.
            elif pc in addresses:
                e.events.append(addresses[pc])
                result = 1 if addresses[pc] == 'm10v_library_valid' else 0
            elif pc in (0x5351E888, 0x5350E624):
                result = 0
            elif pc == 0x536ABD28:
                e.events.append('enqueue')
                result = 0
            elif pc in (0x5367B540, 0x5367C158):
                result = 1
            else:
                return
            u.reg_write(A.UC_ARM_REG_R0, result & 0xFFFFFFFF)
            u.reg_write(A.UC_ARM_REG_PC, u.reg_read(A.UC_ARM_REG_LR))
        e.u.hook_add(UC_HOOK_CODE, services)
        e.call(self.pipeline_exports['m10v_isp_effects_shot_reserve'], recipe)
        return e, recipe, si, context, owner

    def at(self, e, site, args, context):
        for i in range(13):
            e.u.reg_write(getattr(A, f'UC_ARM_REG_R{i}'), 0x12340000 + i)
        for i, value in enumerate(args):
            e.u.reg_write(getattr(A, f'UC_ARM_REG_R{i}'), value)
        e.u.reg_write(A.UC_ARM_REG_R4, context)
        e.u.reg_write(A.UC_ARM_REG_R12, context)
        e.u.reg_write(A.UC_ARM_REG_SP, 0x5EFFF000)
        e.u.reg_write(A.UC_ARM_REG_LR, 0x5E000000)
        e.u.emu_start(site, site + 4, count=1000000)
        if e.hold_reached:
            self.assertEqual(e.u.reg_read(A.UC_ARM_REG_PC), 0x536B0A74)
            return 0
        self.assertEqual(e.u.reg_read(A.UC_ARM_REG_PC), site + 4)
        return e.u.reg_read(A.UC_ARM_REG_R0)

    def params(self, e):
        params, a, b, values = e.alloc(64), e.alloc(32), e.alloc(32), e.alloc(16)
        for descriptor, y, uv in ((a, 0x70000000, 0x71000000), (b, 0x72000000, 0x73000000)):
            e.u.mem_write(descriptor, struct.pack('<4I6HI', 1, y, uv, 0, 640, 480, 640, 480, 0, 0, 2))
        e.w32(params + 4, a)
        e.w32(params + 8, b)
        e.w32(params + 0x10, values)
        e.w32(params + 0x2C, 0x74000000)
        return params, values

    def test_real_producer_freezes_before_enqueue_even_when_color_preview_unavailable(self):
        e, recipe, si, context, owner = self.fixture()
        e.call(0x5351EA9C, owner, recipe)
        self.assertLess(e.events.index('cache'), e.events.index('enqueue'))
        self.assertEqual(int.from_bytes(e.u.mem_read(recipe + 0x5778 + 8, 4), 'little'), 1)
        e.frozen = (3, 2, 2, 4, 2, 3, 2, 0)
        e.call(0x5351EA9C, owner, recipe)
        self.assertEqual(e.events.count('cache'), 1)

    def test_real_cold_producer_is_untouched_and_can_reach_jpeg_admission(self):
        e, recipe, si, context, owner = self.fixture(available=False)
        e.call(0x5351EA9C, owner, recipe)
        self.assertEqual(int.from_bytes(e.u.mem_read(recipe + 0x5778 + 8, 4), 'little'), 2)
        e.call(self.pipeline_exports['m10v_isp_effects_pipeline_encoder_admit'], recipe, si)
        self.assertEqual(e.u.reg_read(A.UC_ARM_REG_R0), 1)
        self.assertFalse(e.hold_reached)

    def test_original_query_and_execution_use_frozen_stock_grain_without_cpu_rng(self):
        e, recipe, si, context, owner = self.fixture()
        e.call(0x5351EA9C, owner, recipe)
        p0, values0 = self.params(e)
        self.at(e, 0x535033D8, (p0, si, 1), context)
        self.assertEqual(struct.unpack('<h', e.u.mem_read(values0 + 4, 2))[0], 0)
        queried, native = e.alloc(4), e.alloc(0x100)
        self.at(e, 0x535033E8, (native, p0, queried), context)
        capacity = int.from_bytes(e.u.mem_read(queried, 4), 'little')
        self.assertEqual(capacity, 460800)
        p1, values1 = self.params(e)
        self.at(e, 0x53503AA0, (p1, si, 1), context)
        e.w32(p1 + 0x30, capacity)
        self.assertEqual(self.at(e, 0x53503AB4, (native, p1, 0), context), 1)
        self.assertEqual(e.rendered[0][0], native)
        self.assertEqual(int.from_bytes(e.u.mem_read(recipe + 0x5778 + 68, 4), 'little'), 1)

    def test_original_stock_grain_menu_argument_is_reversed_into_ui_strength(self):
        for native_menu, effective in ((1, 3), (2, 2), (3, 1)):
            e, recipe, si, context, owner = self.fixture()
            e.call(0x5351EA9C, owner, recipe)
            e.u.mem_write(si + 0x795, bytes([native_menu]))
            params, values = self.params(e)
            self.at(e, 0x535033D8, (params, si, 1), context)
            self.assertEqual(struct.unpack('<h', e.u.mem_read(values + 4, 2))[0], 0)
            self.assertEqual(int.from_bytes(e.u.mem_read(recipe + 0x5778 + 60, 4), 'little'), effective)

    def test_render_failure_returns_zero_and_never_fabricates_completion(self):
        e, recipe, si, context, owner = self.fixture()
        e.call(0x5351EA9C, owner, recipe)
        params, _ = self.params(e)
        self.at(e, 0x535033D8, (params, si, 1), context)
        queried, native = e.alloc(4), e.alloc(0x100)
        self.at(e, 0x535033E8, (native, params, queried), context)
        e.w32(params + 0x30, int.from_bytes(e.u.mem_read(queried, 4), 'little'))
        e.render_result = -4
        self.assertEqual(self.at(e, 0x53503AB4, (native, params, 0), context), 0)
        self.assertTrue(e.hold_reached, 'admitted failure must retain the frame instead of reaching ignored caller r0')
        self.assertEqual(int.from_bytes(e.u.mem_read(recipe + 0x5778 + 68, 4), 'little'), 0)

    def test_unadmitted_pixel_char_and_hdr_keep_original_execution_result(self):
        for kind in ('pixel', 'char', 'hdr', 'cold'):
            for stock_result in (0, 1):
                e, recipe, si, context, owner = self.fixture(available=kind != 'cold')
                e.call(0x5351EA9C, owner, recipe)
                if kind in ('pixel', 'char'):
                    state = e.alloc(184)
                    e.u.mem_write(state, bytes(184))
                    e.u.mem_write(state + 12, struct.pack('<H', 290 if kind == 'pixel' else 289))
                    e.call(self.recipe_manifest['exports']['m10v_isp_frame_recipe_snapshot'], recipe, state)
                    e.u.mem_write(si + 0x77C, b'\x0C')
                if kind == 'hdr':
                    e.u.mem_write(si + 0x77C, b'\x0E')
                    e.u.mem_write(si + 0x796, b'\x01')
                params, _ = self.params(e)
                self.at(e, 0x53503AA0, (params, si, 1), context)
                self.assertEqual(int.from_bytes(e.u.mem_read(params + 0x20, 4), 'little'), 0)
                executed = []
                def original(u, pc, size, data):
                    if pc == 0x53680DBC:
                        u.reg_write(A.UC_ARM_REG_R0, stock_result)
                        u.reg_write(A.UC_ARM_REG_PC, u.reg_read(A.UC_ARM_REG_LR))
                    elif pc == self.pipeline_exports['m10v_isp_effects_pipeline_execute']:
                        executed.append(pc)
                e.u.hook_add(UC_HOOK_CODE, original)
                self.assertEqual(self.at(e, 0x53503AB4, (e.alloc(0x100), params, 0), context), stock_result, kind)
                self.assertEqual(executed, [])

    def test_default_build_still_has_four_patches_and_separate_query_is_pure_only(self):
        exports = dict(zip(HELPERS, (0x541B0000, 0x541B0200)))
        with tempfile.TemporaryDirectory() as folder:
            code, manifest = build_grain(folder, 0x541A0000, exports, self.rom)
        self.assertEqual(hashlib.sha256(code).hexdigest(), 'ef8a567f0f58166a1bacfb8b4d769bbcc310bcde474a0e125b8c5aa9bf71b761')
        self.assertEqual(len(manifest['patches']), 4)
        self.assertNotIn('pure_isp_query_patch', manifest)
        self.assertEqual(len(self.grain_manifest['patches']), 4)
        self.assertEqual(self.grain_manifest['pure_isp_query_patch']['address'], 0x535033E8)

    def test_query_and_execution_preserve_native_postcall_abi_and_capture_actual_r0_context(self):
        for site, helper_name in ((0x535033E8, 'm10v_isp_effects_pipeline_workspace'),
                                  (0x53503AB4, 'm10v_isp_effects_pipeline_execute')):
            for original_result, helper_result in ((1, 1), (1, 0), (0, 1)):
                e, recipe, si, context, owner = self.fixture()
                params, _ = self.params(e)
                native, queried = e.alloc(0x100), e.alloc(4)
                e.w32(params + 0x20, recipe)  # admitted wrapper ABI fixture
                seen = []
                final_fp = [0x1122334400000000 + n for n in range(32)]
                def adversarial(u, pc, size, data):
                    if pc == 0x53680DBC:
                        self.assertEqual((u.reg_read(A.UC_ARM_REG_R0), u.reg_read(A.UC_ARM_REG_R1)), (native, params))
                        for reg, value in ((0, original_result), (1, 0x11111111), (2, 0x22222222),
                                           (3, 0x33333333), (12, 0xCCCCCCCC)):
                            u.reg_write(getattr(A, f'UC_ARM_REG_R{reg}'), value)
                        for n in range(32):
                            u.reg_write(getattr(A, f'UC_ARM_REG_D{n}'), final_fp[n])
                        u.reg_write(A.UC_ARM_REG_FPSCR, 0x01000000)
                        u.reg_write(A.UC_ARM_REG_CPSR, 0xA0000013)
                        u.reg_write(A.UC_ARM_REG_PC, u.reg_read(A.UC_ARM_REG_LR))
                    elif pc == self.pipeline_exports[helper_name]:
                        seen.append(tuple(u.reg_read(getattr(A, f'UC_ARM_REG_R{i}')) for i in range(4)))
                        target = u.reg_read(A.UC_ARM_REG_LR)
                        for i in range(13):
                            u.reg_write(getattr(A, f'UC_ARM_REG_R{i}'), 0xDEAD0000 + i)
                        for i in range(32):
                            u.reg_write(getattr(A, f'UC_ARM_REG_D{i}'), 0xDEAD000000000000 + i)
                        u.reg_write(A.UC_ARM_REG_FPSCR, 0)
                        u.reg_write(A.UC_ARM_REG_CPSR, 0x60000013)
                        u.reg_write(A.UC_ARM_REG_R0, helper_result)
                        u.reg_write(A.UC_ARM_REG_PC, target)
                e.u.hook_add(UC_HOOK_CODE, adversarial)
                result = self.at(e, site, (native, params, queried if site == 0x535033E8 else 0), context)
                self.assertEqual(result, original_result if site == 0x535033E8 or helper_result else 0)
                expected_args = (params, queried, original_result) if site == 0x535033E8 else (recipe, native, params, original_result)
                self.assertEqual(seen[0][:len(expected_args)], expected_args)
                self.assertEqual([e.u.reg_read(getattr(A, f'UC_ARM_REG_R{i}')) for i in (1, 2, 3, 12)],
                                 [0x11111111, 0x22222222, 0x33333333, 0xCCCCCCCC])
                self.assertEqual(e.u.reg_read(A.UC_ARM_REG_R4), context)
                self.assertEqual(e.u.reg_read(A.UC_ARM_REG_SP), 0x5EFFF000)
                self.assertEqual(e.u.reg_read(A.UC_ARM_REG_LR), site + 4)
                self.assertEqual(e.u.reg_read(A.UC_ARM_REG_CPSR) & 0xF0000000, 0xA0000000)
                self.assertEqual(e.u.reg_read(A.UC_ARM_REG_FPSCR), 0x01000000)
                self.assertEqual([e.u.reg_read(getattr(A, f'UC_ARM_REG_D{i}')) for i in range(32)], final_fp)


if __name__ == '__main__':
    unittest.main()
