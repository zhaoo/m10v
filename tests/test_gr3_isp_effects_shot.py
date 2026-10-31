"""ARM contracts for per-exposure metadata freeze/plan/completion ownership."""
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from scripts.build_gr3_m10v_library import FLAGS, link_object
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm_const as A

ROOT = Path(__file__).resolve().parents[1]
BASE, RECIPE, OFFSET, OUT, SI = 0x541D0000, 0x55010000, 0x5778, 0x55009000, 0x55030000
SHOT = RECIPE + OFFSET


class EffectsShotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = ROOT / 'native/gr3/m10v_isp_effects_shot.c'
        if not source.exists():
            raise AssertionError('ISP effects per-exposure shot owner is missing')
        cls.temp = tempfile.TemporaryDirectory()
        folder = Path(cls.temp.name)
        src, obj = folder / 'shot.c', folder / 'shot.o'
        src.write_text('\n'.join('#include "' + str(ROOT / 'native/gr3' / name) + '"'
            for name in ('m10v_isp_effects_state.c', 'm10v_isp_effects_shot.c')))
        subprocess.run([shutil.which('clang'), *FLAGS,
            '-DM10V_ISP_EFFECTS_SHOT_OFFSET=' + hex(OFFSET), '-c', str(src), '-o', str(obj)],
            check=True, capture_output=True)
        names = ('reserve', 'freeze', 'read', 'plan', 'complete', 'fail', 'stock_query')
        exports = tuple('m10v_isp_effects_shot_' + name for name in names)
        cls.code, cls.symbols = link_object(obj.read_bytes(), BASE,
            {'m10v_isp_effects_camera_snapshot': 0x53000100}, prefix='m10v_settings_',
            omitted_exports=('m10v_settings_open', 'm10v_settings_key'), additional_exports=exports)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'temp'):
            cls.temp.cleanup()

    def setUp(self):
        self.u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        self.u.mem_map(BASE, 0x10000)
        self.u.mem_write(BASE, self.code)
        self.u.mem_map(0x53000000, 0x1000)
        self.u.mem_map(0x55000000, 0x100000)
        self.put(RECIPE, 0x53D0FC90)
        self.put(RECIPE + 0x4778, 0x31545653)
        self.put(RECIPE + 0x44C8, SI)
        self.settings, self.sequence, self.available, self.calls = (0,) * 8, 7, True, 0
        self.u.hook_add(UC_HOOK_CODE, self.hook)
        self.call('reserve', RECIPE)

    def put(self, address, *values):
        self.u.mem_write(address, struct.pack('<' + 'I' * len(values), *values))

    def word(self, address):
        return struct.unpack('<I', self.u.mem_read(address, 4))[0]

    def hook(self, u, pc, size, data):
        if pc == 0x53000100:
            self.calls += 1
            if self.available:
                self.put(u.reg_read(A.UC_ARM_REG_R0), *self.settings)
                self.put(u.reg_read(A.UC_ARM_REG_R1), self.sequence)
            u.reg_write(A.UC_ARM_REG_R0, int(self.available))
            u.reg_write(A.UC_ARM_REG_PC, u.reg_read(A.UC_ARM_REG_LR))

    def call(self, name, *args):
        for i in range(4):
            self.u.reg_write(getattr(A, f'UC_ARM_REG_R{i}'), args[i] if i < len(args) else 0)
        self.u.reg_write(A.UC_ARM_REG_SP, 0x550FD000)
        for i, arg in enumerate(args[4:]):
            self.put(0x550FD000 + i * 4, arg)
        self.u.reg_write(A.UC_ARM_REG_LR, 0x550FF000)
        self.u.emu_start(self.symbols['m10v_isp_effects_shot_' + name], 0x550FF000, count=100000)
        self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC), 0x550FF000)
        return self.u.reg_read(A.UC_ARM_REG_R0)

    def shot(self):
        return bytes(self.u.mem_read(SHOT, 96))

    def test_reserve_owns_exact_tail_and_explicitly_starts_new_exposure(self):
        self.u.mem_write(SHOT - 4, b'\xA5' * 104)
        self.call('reserve', RECIPE)
        self.assertEqual(bytes(self.u.mem_read(SHOT - 4, 4)), b'\xA5' * 4)
        self.assertEqual(bytes(self.u.mem_read(SHOT + 96, 4)), b'\xA5' * 4)
        self.assertEqual(self.word(SHOT + 4), RECIPE)
        self.assertEqual(self.shot()[8:], bytes(88))
        self.assertEqual(self.calls, 0)

    def test_freeze_once_keeps_settings_and_sequence_across_ui_changes(self):
        self.settings = (3, 2, 1, 4, 2, 3, 1, 0)
        self.assertEqual(self.call('freeze', RECIPE), 1)
        frozen = self.shot()
        self.settings, self.sequence = (0,) * 8, 99
        self.assertEqual(self.call('freeze', RECIPE), 1)
        self.assertEqual(self.call('read', RECIPE, OUT), 1)
        self.assertEqual(bytes(self.u.mem_read(OUT, 96)), frozen)
        self.assertEqual(self.calls, 1)
        self.assertEqual(self.word(OUT + 12), 7)
        self.assertEqual(self.word(OUT + 8), 1)

    def test_unavailable_and_invalid_settings_are_frozen_until_explicit_reserve(self):
        for invalid in (False, True):
            self.call('reserve', RECIPE)
            self.available = invalid
            self.settings = (4, 0, 0, 0, 0, 0, 0, 0)
            self.assertEqual(self.call('freeze', RECIPE), 0)
            self.assertEqual(self.word(SHOT + 8), 2)
            self.available, self.settings = True, (0,) * 8
            count = self.calls
            self.assertEqual(self.call('freeze', RECIPE), 0)
            self.assertEqual(self.calls, count)
            self.u.mem_write(OUT, b'\xA5' * 96)
            self.assertEqual(self.call('read', RECIPE, OUT), 0)
            self.assertEqual(bytes(self.u.mem_read(OUT, 96)), b'\xA5' * 96)
        self.call('reserve', RECIPE)
        self.assertEqual(self.call('freeze', RECIPE), 1)

    def test_saved_orientation_and_si_override_freeze_once_at_producer(self):
        for raw,exif in ((0,1),(1,8),(2,3),(3,6),(4,1)):
            self.call('reserve',RECIPE)
            self.u.mem_write(SI+0xc8,bytes((raw,)));self.u.mem_write(SI+0x71e03,b'\0');self.call('freeze',RECIPE)
            self.assertEqual(self.word(SHOT+88),exif);self.assertEqual(self.word(SHOT+76),SI)
            self.u.mem_write(SI+0xc8,b'\x03')
            self.assertEqual(self.call('plan',RECIPE,SI,6000,4000,0),1)
            self.assertEqual(self.word(SHOT+88),exif)
            self.u.mem_write(SI+0xc8,b'\x03');self.assertEqual(self.call('plan',RECIPE,SI,6000,4000,0),1)
            self.assertEqual(self.word(SHOT+88),exif);self.assertEqual(self.call('read',RECIPE,OUT),1)
        self.call('reserve',RECIPE)
        self.u.mem_write(SI+0xc8,b'\0');self.u.mem_write(SI+0x71e03,b'\x01');self.u.mem_write(SI+0x71e04,b'\x03');self.call('freeze',RECIPE)
        self.assertEqual(self.call('plan',RECIPE,SI,6000,4000,0),1);self.assertEqual(self.word(SHOT+88),6)

    def test_frozen_orientation_cannot_rebind_to_a_later_saved_si(self):
        self.u.mem_write(SI+0xc8,b'\x01');self.call('freeze',RECIPE);before=self.shot()
        self.put(RECIPE+0x44c8,SI+4)
        self.assertEqual(self.call('plan',RECIPE,SI+4,6000,4000,0),0)
        self.assertEqual(self.call('freeze',RECIPE),0);self.assertEqual(self.shot(),before)
        self.put(RECIPE+0x44c8,SI);self.assertEqual(self.call('read',RECIPE,OUT),1)
        self.assertEqual(self.word(OUT+88),8)

    def test_original_exif_setter_confirms_saved_si_direction_and_override(self):
        from scripts import probe_gr3_border_exif as original
        from scripts.build_gr3_border_wait_guard import MODELS
        pinned=original.SHA
        try:
            for model in ('gr3','gr3x'):
                rom=(ROOT/f'builds/gr3-pure-isp-feasibility-20261031/{model}-official-rtos.bin').read_bytes()
                original.SHA=MODELS[model]['rtos_sha256'];r=original.probe(rom)
                self.assertEqual(r['capture_orientation_to_exif'],{0:1,1:8,2:3,3:6,4:1})
                self.assertTrue(r['checks']['si_orientation_override'])
        finally:original.SHA=pinned

    def test_plan_freezes_inherited_strength_geometry_si_and_workspace_without_completion(self):
        self.call('freeze', RECIPE)
        self.assertEqual(self.call('plan', RECIPE, SI, 6000, 4000, 2), 1)
        self.assertEqual(tuple(self.word(SHOT + off) for off in (48, 52, 56, 60, 64, 68, 72, 76)),
                         (6000, 4000, 36000000, 2, 1, 0, 0, SI))
        planned = self.shot()
        self.settings = (3, 0, 0, 4, 0, 3, 0, 0)
        self.assertEqual(self.call('freeze', RECIPE), 1)
        self.assertEqual(self.call('plan', RECIPE, SI, 6000, 4000, 2), 1)
        for args in ((SI, 6002, 4000, 2), (SI, 6000, 4000, 1), (SI + 4, 6000, 4000, 2)):
            self.assertEqual(self.call('plan', RECIPE, *args), 0)
            self.assertEqual(self.shot(), planned)
        self.assertEqual(self.calls, 1)

    def test_workspace_zero_for_all_off_or_blur_only_and_leak_uses_aligned_yuv420(self):
        for settings, slot, workspace in (((0,) * 8, 0, 0),
                ((0, 0, 0, 1, 0, 3, 0, 0), 3, 0),
                ((1, 0, 0, 1, 0, 0, 0, 0), 3, 8448),
                ((0, 0, 0, 2, 0, 0, 0, 0), 0, 6336)):
            self.call('reserve', RECIPE)
            self.settings = settings
            self.call('freeze', RECIPE)
            self.assertEqual(self.call('plan', RECIPE, SI, 162, 24, slot), 1)
            self.assertEqual(self.word(SHOT + 56), workspace)
            self.assertEqual(self.word(SHOT + 68), 0)

    def test_invalid_dimensions_slot_or_current_si_reject_without_planning(self):
        self.call('freeze', RECIPE)
        before = self.shot()
        for si, width, height, slot in ((SI, 0, 2, 0), (SI, 2, 0, 0), (SI, 3, 2, 0),
                (SI, 2, 3, 0), (SI, 6146, 2, 0), (SI, 2, 6146, 0),
                (SI, 2, 2, 4), (0, 2, 2, 0), (SI + 4, 2, 2, 0)):
            self.assertEqual(self.call('plan', RECIPE, si, width, height, slot), 0)
            self.assertEqual(self.shot(), before)
        self.assertEqual(self.call('plan', RECIPE, SI, 6144, 6144, 3), 1)
        self.assertEqual(self.word(SHOT + 56), 56623104)

    def test_completion_requires_plan_matching_si_enabled_flags_and_actual_caller_signal(self):
        self.settings = (1, 0, 0, 2, 0, 1, 0, 0)
        self.call('freeze', RECIPE)
        self.assertEqual(self.call('complete', RECIPE, SI, 1), 0)
        self.call('plan', RECIPE, SI, 6000, 4000, 0)
        before = self.shot()
        for si, flags in ((SI + 4, 1), (0, 1), (SI, 0), (SI, 8)):
            self.assertEqual(self.call('complete', RECIPE, si, flags), 0)
            self.assertEqual(self.shot(), before)
        for flags, expected in ((2, 2), (4, 6), (1, 7), (1, 7)):
            self.assertEqual(self.call('complete', RECIPE, SI, flags), 1)
            self.assertEqual(self.word(SHOT + 68), expected)
        self.call('freeze', RECIPE)
        self.assertEqual(self.word(SHOT + 68), 7)
        self.call('reserve', RECIPE)
        self.settings = (0, 0, 0, 1, 0, 0, 0, 0)
        self.call('freeze', RECIPE)
        self.call('plan', RECIPE, SI, 2, 2, 0)
        self.assertEqual(self.call('complete', RECIPE, SI, 1), 0)

    def test_failure_is_matching_sticky_and_never_fabricates_native_completion(self):
        self.settings = (1, 0, 0, 1, 0, 0, 0, 0)
        self.call('freeze', RECIPE)
        self.call('plan', RECIPE, SI, 2, 2, 0)
        before = self.shot()
        self.call('fail', RECIPE, SI + 4)
        self.assertEqual(self.shot(), before)
        self.call('fail', RECIPE, SI)
        self.assertEqual((self.word(SHOT + 68), self.word(SHOT + 72)), (0, 1))
        self.call('freeze', RECIPE)
        self.assertEqual(self.call('plan', RECIPE, SI, 2, 2, 0), 0)
        self.assertEqual(self.call('complete', RECIPE, SI, 2), 0)
        self.assertEqual((self.word(SHOT + 68), self.word(SHOT + 72)), (0, 1))

    def test_invalid_recipe_trace_token_and_snapshot_owner_reject_without_mutation(self):
        self.call('freeze', RECIPE)
        for address, invalid in ((RECIPE, 0), (RECIPE + 0x4778, 0),
                (RECIPE + 0x5110, 0x31574C52), (SHOT + 4, RECIPE + 4), (SHOT, 0)):
            old = self.word(address)
            self.put(address, invalid)
            before = self.shot()
            self.u.mem_write(OUT, b'\xA5' * 96)
            count = self.calls
            self.assertEqual(self.call('freeze', RECIPE), 0)
            self.assertEqual(self.call('read', RECIPE, OUT), 0)
            self.assertEqual(self.call('plan', RECIPE, SI, 2, 2, 0), 0)
            self.assertEqual(self.shot(), before)
            self.assertEqual(bytes(self.u.mem_read(OUT, 96)), b'\xA5' * 96)
            self.assertEqual(self.calls, count)
            if address in (RECIPE, RECIPE + 0x4778, RECIPE + 0x5110):
                self.call('reserve', RECIPE)
                self.assertEqual(self.shot(), before)
            self.put(address, old)
        self.put(RECIPE + 0x5110, 0x31574C52, RECIPE)
        self.assertEqual(self.call('read', RECIPE, OUT), 1)
        for recipe in (0, RECIPE + 1, 0x7FFFFFFC):
            self.assertEqual(self.call('read', recipe, OUT), 0)
        for out in (0, OUT + 1, 0x7FFFFFF0, SHOT):
            self.assertEqual(self.call('read', RECIPE, out), 0)

    def test_reserved_or_inconsistent_snapshot_metadata_is_never_published(self):
        self.call('freeze', RECIPE)
        for offset, invalid in ((8, 3), (16, 4), (64, 2), (68, 1), (72, 1), (80, 1)):
            original = self.word(SHOT + offset)
            self.put(SHOT + offset, invalid)
            self.u.mem_write(OUT, b'\xA5' * 96)
            self.assertEqual(self.call('read', RECIPE, OUT), 0)
            self.assertEqual(bytes(self.u.mem_read(OUT, 96)), b'\xA5' * 96)
            self.put(SHOT + offset, original)

    def test_stock_query_is_bound_once_to_planned_saved_si(self):
        self.call('freeze', RECIPE)
        self.assertEqual(self.call('stock_query', RECIPE, SI, 1234), 0)
        self.call('plan', RECIPE, SI, 6000, 4000, 1)
        self.assertEqual(self.call('stock_query', RECIPE, SI + 4, 1234), 0)
        self.assertEqual(self.call('stock_query', RECIPE, SI, 1234), 1)
        self.assertEqual((self.word(SHOT + 80), self.word(SHOT + 84)), (1234, 1))
        before = self.shot()
        self.assertEqual(self.call('stock_query', RECIPE, SI, 1234), 1)
        self.assertEqual(self.call('stock_query', RECIPE, SI, 1235), 0)
        self.assertEqual(self.shot(), before)
        self.call('plan', RECIPE, SI, 6000, 4000, 1)
        for offset, invalid in ((48, 3), (56, 1), (60, 4), (68, 8), (76, SI + 4)):
            original = self.word(SHOT + offset)
            self.put(SHOT + offset, invalid)
            self.u.mem_write(OUT, b'\xA5' * 96)
            self.assertEqual(self.call('read', RECIPE, OUT), 0)
            self.assertEqual(bytes(self.u.mem_read(OUT, 96)), b'\xA5' * 96)
            self.put(SHOT + offset, original)


if __name__ == '__main__':
    unittest.main()
