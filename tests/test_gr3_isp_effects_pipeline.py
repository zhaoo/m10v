"""ARM metadata adapter tests; render endpoint is explicitly a service double.

Original final-descriptor evidence is executed separately below. Pixel planes
and workspace remain unmapped in adapter tests; no hardware success is proved.
"""
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib

from scripts.build_gr3_m10v_library import FLAGS, link_object
from tests import test_gr3_isp_effects_shot as shot_case
from unicorn import arm_const as A

ROOT = Path(__file__).resolve().parents[1]
RECIPE, SI, SHOT = shot_case.RECIPE, shot_case.SI, shot_case.SHOT
PARAMS, PHOTO_A, PHOTO_B, VALUES, QUERIED, CONTEXT = (0x55070000 + i * 0x100 for i in range(6))


class EffectsPipelineTests(unittest.TestCase):
    put, word, shot = shot_case.EffectsShotTests.put, shot_case.EffectsShotTests.word, shot_case.EffectsShotTests.shot

    @classmethod
    def setUpClass(cls):
        source = ROOT / 'native/gr3/m10v_isp_effects_pipeline.c'
        if not source.exists():
            raise AssertionError('ISP effects pipeline metadata adapter is missing')
        cls.temp = tempfile.TemporaryDirectory()
        folder = Path(cls.temp.name)
        src, obj = folder / 'pipeline.c', folder / 'pipeline.o'
        src.write_text('\n'.join('#include "' + str(ROOT / 'native/gr3' / name) + '"'
            for name in ('m10v_isp_effects_state.c', 'm10v_isp_effects_shot.c', 'm10v_isp_effects_pipeline.c')))
        subprocess.run([shutil.which('clang'), *FLAGS,
            '-DM10V_DEBUG_MODE=1',
            '-DM10V_ISP_EFFECTS_SHOT_OFFSET=' + hex(shot_case.OFFSET), '-c', str(src), '-o', str(obj)],
            check=True, capture_output=True)
        exports = tuple('m10v_isp_effects_shot_' + name for name in
            ('reserve', 'freeze', 'read', 'plan', 'complete', 'fail', 'stock_query', 'unavailable'))
        exports += tuple('m10v_isp_effects_pipeline_' + name for name in ('settings', 'workspace', 'execute', 'encoder_admit'))
        cls.code, cls.symbols = link_object(obj.read_bytes(), shot_case.BASE,
            {'m10v_isp_effects_camera_snapshot': 0x53000100, 'm10v_isp_effects_render': 0x53000200,
             'm10v_debug_batch': 0x53000300},
            prefix='m10v_settings_', omitted_exports=('m10v_settings_open', 'm10v_settings_key'),
            additional_exports=exports)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'temp'):
            cls.temp.cleanup()

    def setUp(self):
        shot_case.EffectsShotTests.setUp(self)
        self.u.mem_map(0x536B0000, 0x1000)
        self.holds = 0
        self.diagnostics = []
        self.render_calls, self.render_result = [], 1
        self.put(PARAMS, 0xA5A5A5A5, PHOTO_A, PHOTO_B, 0x11223344, VALUES, 0, 0, 0, 0, 0, 0, 0x70000000, 0)
        self.photo(PHOTO_A, 1, 0x60000000, 0x64000000)
        self.photo(PHOTO_B, 1, 0x62000000, 0x66000000)
        self.u.mem_write(VALUES, struct.pack('<4hf', 0, 0, 3, 0, 1.0))

    def hook(self, u, pc, size, data):
        if pc == 0x53000300:
            pointer, count = u.reg_read(A.UC_ARM_REG_R0), u.reg_read(A.UC_ARM_REG_R1)
            self.diagnostics.extend(struct.unpack('<5I', u.mem_read(pointer + i * 20, 20)) for i in range(count))
            u.reg_write(A.UC_ARM_REG_R0, 1)
            u.reg_write(A.UC_ARM_REG_PC, u.reg_read(A.UC_ARM_REG_LR))
            return
        if pc == 0x536B0A74:
            self.holds += 1
            u.emu_stop()
            return
        if pc == 0x53000200:
            pointer = u.reg_read(A.UC_ARM_REG_R1)
            snapshot = self.word(u.reg_read(A.UC_ARM_REG_SP))
            self.render_calls.append((u.reg_read(A.UC_ARM_REG_R0),
                bytes(u.mem_read(pointer, 32)), u.reg_read(A.UC_ARM_REG_R2),
                u.reg_read(A.UC_ARM_REG_R3), bytes(u.mem_read(snapshot, 96))))
            u.reg_write(A.UC_ARM_REG_R0, self.render_result & 0xFFFFFFFF)
            u.reg_write(A.UC_ARM_REG_PC, u.reg_read(A.UC_ARM_REG_LR))
            return
        return shot_case.EffectsShotTests.hook(self, u, pc, size, data)

    def call(self, name, *args):
        prefix = 'pipeline_' if name in ('settings', 'workspace', 'execute', 'encoder_admit') else 'shot_'
        for i in range(4):
            self.u.reg_write(getattr(A, f'UC_ARM_REG_R{i}'), args[i] if i < len(args) else 0)
        self.u.reg_write(A.UC_ARM_REG_SP, 0x550FD000)
        for i, arg in enumerate(args[4:]):
            self.put(0x550FD000 + i * 4, arg)
        self.u.reg_write(A.UC_ARM_REG_LR, 0x550FF000)
        self.u.emu_start(self.symbols['m10v_isp_effects_' + prefix + name], 0x550FF000, count=100000)
        if self.u.reg_read(A.UC_ARM_REG_PC) == 0x536B0A74:
            return 0  # Explicitly observed nonreturning native yield boundary.
        self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC), 0x550FF000)
        return self.u.reg_read(A.UC_ARM_REG_R0)

    def photo(self, address, fmt, y, uv):
        self.u.mem_write(address, struct.pack('<4I6H I', fmt, y, uv, 0, 640, 480, 640, 480, 0, 0, 2))

    def arm(self, settings=(0, 0, 0, 2, 0, 0, 0, 0), stock_bytes=0, fmt=1):
        self.settings = settings
        self.call('freeze', RECIPE)
        self.photo(PHOTO_A, fmt, 0x60000000, 0x64000000)
        self.photo(PHOTO_B, fmt, 0x62000000, 0x66000000)
        enabled = self.call('settings', RECIPE, SI, PARAMS, 0)
        self.put(QUERIED, stock_bytes)
        self.assertEqual(self.call('workspace', PARAMS, QUERIED, 1), 1)
        self.put(PARAMS + 0x30, self.word(QUERIED))
        return enabled

    def test_settings_clear_cpu_grain_and_preserve_other_original_fields(self):
        self.settings = (0,) * 8
        self.call('freeze', RECIPE)
        before = bytes(self.u.mem_read(PARAMS, 0x34))
        original = bytes(self.u.mem_read(VALUES, 12))
        self.assertEqual(self.call('settings', RECIPE, SI, PARAMS, 0), 0)
        after = bytearray(before)
        struct.pack_into('<I', after, 0x20, RECIPE)
        self.assertEqual(bytes(self.u.mem_read(PARAMS, 0x34)), after)
        expected = bytearray(original)
        expected[4:6] = b'\0\0'
        self.assertEqual(bytes(self.u.mem_read(VALUES, 12)), expected)

    def test_active_worker_reports_planning_before_native_execution(self):
        self.arm(settings=(1, 0, 0, 1, 0, 0, 0, 0))
        checkpoints = [r for r in self.diagnostics if r[2] == 0x46584800]
        self.assertEqual([r[3] for r in checkpoints], [1, 2])
        self.assertEqual(self.holds, 0)
        self.assertEqual(self.render_calls, [])

    def test_native_byte_format_ignores_uninitialized_descriptor_padding(self):
        self.settings = (1, 0, 0, 1, 0, 0, 0, 0)
        self.call('freeze', RECIPE)
        for descriptor in (PHOTO_A, PHOTO_B):
            self.put(descriptor, 0xA5A5A501)
        self.assertEqual(self.call('settings', RECIPE, SI, PARAMS, 0), 1)
        self.put(QUERIED, 0)
        self.assertEqual(self.call('workspace', PARAMS, QUERIED, 1), 1)
        self.put(PARAMS + 0x30, self.word(QUERIED))
        self.assertEqual(self.call('execute', RECIPE, CONTEXT, PARAMS, 1), 1)
        self.assertEqual(self.word(SHOT + 68), 2)
        self.assertEqual(self.holds, 0)
        self.assertEqual(self.word(PHOTO_A), 0xA5A5A501)

    def test_byte_format_keeps_full_422_chroma_allocation_protected(self):
        self.arm(settings=(1, 0, 0, 1, 0, 0, 0, 0))
        for descriptor in (PHOTO_A, PHOTO_B):
            self.put(descriptor, 0xA5A5A501)
        # Inside the second half of the real 422 chroma plane. Treating the
        # padded word as !=1 would incorrectly use the smaller 420 span.
        self.put(PARAMS + 0x2C, 0x64000000 + 200000)
        self.assertEqual(self.call('execute', RECIPE, CONTEXT, PARAMS, 1), 0)
        self.assertEqual(self.holds, 1)
        self.assertEqual(self.render_calls, [])

    def test_native_workspace_margin_aligns_owned_view_without_mutating_parameters(self):
        self.arm(settings=(1, 0, 0, 1, 0, 0, 0, 0))
        needed = self.word(QUERIED)
        self.put(PARAMS + 0x2C, 0x74000008, needed + 16)
        before = bytes(self.u.mem_read(PARAMS, 0x34))
        self.assertEqual(self.call('execute', RECIPE, CONTEXT, PARAMS, 1), 1)
        self.assertEqual(self.render_calls[0][2:4], (0x74000010, needed + 8))
        self.assertEqual(bytes(self.u.mem_read(PARAMS, 0x34)), before)

    def test_upper_mapped_native_workspace_is_not_rejected_as_metadata(self):
        self.arm(settings=(1, 0, 0, 1, 0, 0, 0, 0))
        self.put(PARAMS + 0x2C, 0xA4000000)
        self.assertEqual(self.call('execute', RECIPE, CONTEXT, PARAMS, 1), 1)
        self.assertEqual(self.render_calls[0][2], 0xA4000000)

    def test_alignment_never_borrows_past_native_capacity(self):
        self.arm(settings=(1, 0, 0, 1, 0, 0, 0, 0))
        self.put(PARAMS + 0x2C, 0x74000008)
        self.assertEqual(self.call('execute', RECIPE, CONTEXT, PARAMS, 1), 0)
        self.assertEqual(self.render_calls, [])

    def test_workspace_diagnostic_distinguishes_capacity_from_bank_or_overlap(self):
        self.arm(settings=(1, 0, 0, 1, 0, 0, 0, 0))
        self.put(PARAMS + 0x30, self.word(QUERIED) - 1)
        self.assertEqual(self.call('execute', RECIPE, CONTEXT, PARAMS, 1), 0)
        reasons = [r for r in self.diagnostics if r[2] == 0x46584800 and r[3] == 12]
        self.assertEqual(reasons[-1][4], 2)

    def test_blur_only_keeps_original_workspace_without_new_alignment_requirement(self):
        self.arm(settings=(0, 0, 0, 1, 0, 1, 0, 0), stock_bytes=4096)
        self.put(PARAMS + 0x2C, 0xA4000008)
        before=bytes(self.u.mem_read(PARAMS,0x34))
        self.assertEqual(self.call('execute', RECIPE, CONTEXT, PARAMS, 1), 1)
        self.assertEqual(self.word(SHOT + 68), 4)
        self.assertEqual(self.render_calls, [])
        self.assertEqual(bytes(self.u.mem_read(PARAMS,0x34)), before)

    def test_missing_completion_reports_exact_hold_before_yield(self):
        self.u.mem_write(SI + 0x77C, b'\x0B')
        self.arm(settings=(0, 0, 0, 2, 0, 0, 0, 0))
        self.diagnostics.clear()
        self.assertEqual(self.call('encoder_admit', RECIPE, SI), 0)
        checkpoints = [r for r in self.diagnostics if r[2] == 0x46584800]
        self.assertEqual([r[3] for r in checkpoints], [24])
        facts = {r[2]: r for r in self.diagnostics}
        self.assertEqual(facts[0x46583033][3:], (1, 0))
        self.assertEqual(self.holds, 1)

    def test_blur_hdf_combination_mapping_and_frozen_queue_settings(self):
        for hdf in range(4):
            for gain in (1, 2, 3):
                for radius in range(3):
                    self.call('reserve', RECIPE)
                    self.settings = (0, 0, 0, 1, 0, gain, radius, 0)
                    self.call('freeze', RECIPE)
                    self.settings = (3, 2, 2, 4, 2, 0, 0, 0)
                    self.u.mem_write(VALUES + 2, struct.pack('<h', 4 + hdf if hdf else -2))
                    self.assertEqual(self.call('settings', RECIPE, SI, PARAMS, 0), 1)
                    value = struct.unpack('<h', self.u.mem_read(VALUES + 2, 2))[0]
                    self.assertEqual(value, 8 + hdf * 9 + (gain - 1) * 3 + radius)
                    self.assertEqual(self.word(SHOT + 68), 0)

    def test_unavailable_stays_cold_and_never_reenables_cpu_rng(self):
        self.available = False
        self.call('freeze', RECIPE)
        self.available = True
        self.assertEqual(self.call('settings', RECIPE, SI, PARAMS, 3), 0)
        self.assertEqual(struct.unpack('<h', self.u.mem_read(VALUES + 4, 2))[0], 0)
        self.assertEqual(self.render_calls, [])

    def test_workspace_retains_original_query_and_raises_max_only_on_success(self):
        self.assertEqual(self.arm(stock_bytes=1024), 1)
        self.assertEqual((self.word(SHOT + 80), self.word(SHOT + 84), self.word(QUERIED)), (1024, 1, 460800))
        self.put(QUERIED, 999)
        before = self.shot()
        self.assertEqual(self.call('workspace', PARAMS, QUERIED, 0), 0)
        self.assertEqual((self.word(QUERIED), self.shot()), (999, before))
        self.assertEqual(self.call('workspace', PARAMS, QUERIED, 1), 0)
        self.assertEqual(self.word(QUERIED), 999)

    def test_actual_final_photo_comes_from_original_stock_query_not_raised_texture_size(self):
        for stock, expected in ((0, PHOTO_A), (128, PHOTO_B)):
            self.call('reserve', RECIPE)
            self.arm(stock_bytes=stock)
            self.assertEqual(self.call('execute', RECIPE, CONTEXT, PARAMS, 1), 1)
            self.assertEqual(self.render_calls[-1][1], bytes(self.u.mem_read(expected, 32)))
            self.assertEqual(self.word(SHOT + 68), 1)
        self.assertEqual(len(self.render_calls), 2)

    def test_accepts_original_422_and_420_photos_and_leak_worst_case_capacity(self):
        for fmt in (1, 2):
            self.call('reserve', RECIPE)
            self.arm((1, 0, 0, 1, 0, 0, 0, 0), fmt=fmt)
            self.assertEqual(self.word(QUERIED), 614400)
            self.assertEqual(self.call('execute', RECIPE, CONTEXT, PARAMS, 1), 1)
            self.assertEqual(self.word(SHOT + 68), 2)

    def test_actual_render_success_marks_once_and_duplicate_does_not_rerender(self):
        self.arm((1, 0, 0, 2, 0, 1, 2, 0))
        self.assertEqual(self.call('execute', RECIPE, CONTEXT, PARAMS, 1), 1)
        self.assertEqual((self.word(SHOT + 68), self.word(SHOT + 72)), (7, 0))
        self.assertEqual(self.call('execute', RECIPE, CONTEXT, PARAMS, 1), 1)
        self.assertEqual(len(self.render_calls), 1)
        self.assertEqual(self.render_calls[0][0], CONTEXT)

    def test_blur_only_completion_uses_original_success_without_texture_render(self):
        self.arm((0, 0, 0, 1, 0, 2, 2, 0), stock_bytes=1024)
        self.assertEqual(self.word(QUERIED), 1024)
        self.assertEqual(self.call('execute', RECIPE, CONTEXT, PARAMS, 1), 1)
        self.assertEqual(self.word(SHOT + 68), 4)
        self.assertEqual(self.render_calls, [])

    def test_wrong_settings_si_clears_stale_ingress_and_never_keeps_cpu_grain(self):
        self.arm()
        self.u.mem_write(VALUES + 4, struct.pack('<h', 3))
        self.assertEqual(self.call('settings', RECIPE, SI + 4, PARAMS, 0), 0)
        self.assertEqual(self.word(PARAMS + 0x20), 0)
        self.assertEqual(struct.unpack('<h', self.u.mem_read(VALUES + 4, 2))[0], 0)
        self.assertEqual(self.call('execute', RECIPE, CONTEXT, PARAMS, 1), 0)
        self.assertEqual(self.render_calls, [])

    def test_stock_failure_render_failure_and_blur_mismatch_never_fabricate_completion(self):
        for failure in ('stock', 'render', 'clarity'):
            self.call('reserve', RECIPE)
            self.arm((1, 0, 0, 2, 0, 1, 0, 0))
            self.render_result = -4 if failure == 'render' else 1
            if failure == 'clarity':
                self.u.mem_write(VALUES + 2, b'\0\0')
            self.assertEqual(self.call('execute', RECIPE, CONTEXT, PARAMS, 0 if failure == 'stock' else 1), 0)
            self.assertEqual(self.holds, ('stock', 'render', 'clarity').index(failure) + 1)
            self.assertEqual((self.word(SHOT + 68), self.word(SHOT + 72)), (0, 1))

    def test_wrong_si_capacity_and_workspace_overlap_fail_before_render(self):
        changes = [(PARAMS + 0x30, 1), (PARAMS + 0x2C, 0x60000000),
                   (PARAMS + 0x2C, 0x64000000), (PARAMS + 0x2C, PARAMS),
                   (PARAMS + 0x2C, RECIPE), (PARAMS + 0x2C, CONTEXT),
                   (PARAMS + 0x20, RECIPE + 4), (RECIPE + 0x44C8, SI + 4)]
        for address, invalid in changes:
            self.call('reserve', RECIPE)
            self.arm()
            old = self.word(address)
            self.put(address, invalid)
            count = len(self.render_calls)
            self.assertEqual(self.call('execute', RECIPE, CONTEXT, PARAMS, 1), 0)
            self.assertEqual(len(self.render_calls), count)
            self.assertEqual(self.word(SHOT + 68), 0)
            self.put(address, old)

    def test_encoder_gate_holds_active_unplanned_failed_query_or_missing_completion(self):
        self.u.mem_write(SI + 0x77C, b'\x0B')
        self.settings = (0, 0, 0, 2, 0, 0, 0, 0)
        self.call('freeze', RECIPE)
        self.assertEqual(self.call('encoder_admit', RECIPE, SI), 0)
        self.assertEqual(self.holds, 1)
        self.call('settings', RECIPE, SI, PARAMS, 0)
        self.put(QUERIED, 0)
        self.assertEqual(self.call('workspace', PARAMS, QUERIED, 0), 0)
        self.assertEqual(self.call('encoder_admit', RECIPE, SI), 0)
        self.assertEqual(self.holds, 2)
        self.assertEqual(self.call('workspace', PARAMS, QUERIED, 1), 1)
        self.assertEqual(self.call('encoder_admit', RECIPE, SI), 0)
        self.assertEqual(self.holds, 3)
        self.put(PARAMS + 0x30, self.word(QUERIED))
        self.assertEqual(self.call('execute', RECIPE, CONTEXT, PARAMS, 1), 1)
        self.assertEqual(self.call('encoder_admit', RECIPE, SI), 1)
        self.assertEqual(self.call('encoder_admit', RECIPE, SI + 4), 0)
        self.assertEqual(self.holds, 4)

    def test_encoder_gate_allows_only_authenticated_untouched_cold_snapshot(self):
        self.u.mem_write(SI + 0x77C, b'\x0B')
        self.available = False
        self.call('freeze', RECIPE)
        self.assertEqual(self.call('encoder_admit', RECIPE, SI), 1)
        for offset, bad in ((16, 1), (64, 1), (68, 1), (80, 1), (88, 1), (92, 1)):
            self.put(SHOT + offset, bad)
            self.assertEqual(self.call('encoder_admit', RECIPE, SI), 0)
            self.put(SHOT + offset, 0)
        self.assertEqual(self.holds, 6)

    def test_all_off_preserves_original_stage_failure_without_new_failure_or_hold(self):
        self.u.mem_write(SI + 0x77C, b'\x0B')
        self.arm((0, 0, 0, 1, 0, 0, 0, 0))
        self.assertEqual(self.call('execute', RECIPE, CONTEXT, PARAMS, 0), 0)
        self.assertEqual(self.word(SHOT + 72), 0)
        self.assertEqual(self.call('encoder_admit', RECIPE, SI), 1)
        self.assertEqual(self.holds, 0)

    def color_snapshot(self, film=66, grain=2, selected=12):
        base = RECIPE + 0x4A08
        self.put(base, 0x31435349, 1, 1796, 1, 7)
        self.u.mem_write(base + 22, struct.pack('<H', selected))
        state = bytearray(184)
        struct.pack_into('<IHHI', state, 0, 0x5630314D, 5, 184, 7)
        struct.pack_into('<HB', state, 12, film, grain)
        struct.pack_into('<I', state, 180, zlib.crc32(state[:180]))
        self.u.mem_write(base + 1612, bytes(state))

    def test_encoder_gate_resolves_owned_selected_tone_and_preserves_special_native_routes(self):
        self.u.mem_write(SI + 0x77C, b'\x0B')
        self.u.mem_write(SI + 0x795, b'\0')
        self.color_snapshot()
        self.call('freeze', RECIPE)
        self.assertEqual(self.call('settings', RECIPE, SI, PARAMS, 2), 1)
        self.put(QUERIED, 0)
        self.call('workspace', PARAMS, QUERIED, 1)
        self.put(PARAMS + 0x30, self.word(QUERIED))
        self.assertEqual(self.call('execute', RECIPE, CONTEXT, PARAMS, 1), 1)
        self.assertEqual(self.call('encoder_admit', RECIPE, SI), 1)
        for film in (289, 290):
            self.color_snapshot(film)
            self.call('reserve', RECIPE)  # no ready snapshot: unsupported stays native
            self.assertEqual(self.call('encoder_admit', RECIPE, SI), 1)
        self.u.mem_write(SI + 0x77C, b'\x0E')
        self.assertEqual(self.call('encoder_admit', RECIPE, SI), 1)
        self.assertEqual(self.holds, 0)


class OriginalFinalDescriptorTests(unittest.TestCase):
    def test_hash_pinned_original_stage_selects_r6_and_real_hdr_zero_keeps_it(self):
        from scripts.analyze_gr3_border_iip import OriginalArm
        from unicorn import UC_HOOK_CODE
        fixtures = ROOT / 'builds/gr3-pure-isp-feasibility-20261031'
        for model in ('gr3', 'gr3x'):
            rom_path = fixtures / (model + '-official-rtos.bin')
            if not rom_path.exists():
                self.skipTest('exact local original RTOS fixture unavailable')
            for stock_bytes, expected in ((0, PHOTO_A), (128, PHOTO_B)):
                p = OriginalArm(rom_path.read_bytes())
                p.words(PARAMS, 0, PHOTO_A, PHOTO_B, 0, VALUES, 0, 0, 0, 0, 0, 0, 0x70000000, 4096)
                p.u.mem_write(VALUES, struct.pack('<4hf', 0, 0, 0, 0, 1.0))
                for address, y, uv in ((PHOTO_A, 0x60000000, 0x64000000), (PHOTO_B, 0x62000000, 0x66000000)):
                    p.u.mem_write(address, struct.pack('<4I6HI', 1, y, uv, 0, 640, 480, 640, 480, 0, 0, 2))
                calls, hdr_destinations, real_hdr_zero = [], [], []
                def processing(kind):
                    def endpoint():
                        r1, r2 = p.u.reg_read(A.UC_ARM_REG_R1), p.u.reg_read(A.UC_ARM_REG_R2)
                        if r2 == 0:
                            offset = 8 if kind == 'shade' else 4
                            output = p.read_words(p.u.reg_read(A.UC_ARM_REG_SP) + offset, 1)[0]
                            p.words(output, stock_bytes)
                        else:
                            calls.append((kind, r1, r2))
                        return 1
                    return endpoint
                p.boundaries.update({0x5367B540: processing('shade'), 0x5367C158: processing('clarity')})
                def observe(u, pc, size, data):
                    if pc == 0x53680088 and u.reg_read(A.UC_ARM_REG_R2):
                        hdr_destinations.append(u.reg_read(A.UC_ARM_REG_R1))
                    if pc == 0x5368039C:
                        real_hdr_zero.append(pc)
                p.u.hook_add(UC_HOOK_CODE, observe)
                p.call(0x53680DBC, CONTEXT, PARAMS, 0)
                self.assertEqual(p.u.reg_read(A.UC_ARM_REG_R0), 1)
                self.assertEqual(calls[-1][0], 'clarity')
                self.assertEqual(calls[-1][2], expected)
                self.assertEqual(hdr_destinations, [expected])
                self.assertEqual(len(real_hdr_zero), 2)  # original sizing + execution
                self.assertEqual(p.assertions, [])


if __name__ == '__main__':
    unittest.main()
