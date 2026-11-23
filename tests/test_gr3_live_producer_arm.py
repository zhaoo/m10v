"""Run both stock display callers through the production Live observer.

The pinned RTOS supplies the caller, descriptor setters and hook continuation.
Owner lookup, time/cache, display lookup/query and submission APIs are traps.
This proves ABI/guard behavior offline; it does not prove camera frame lifetime.
"""
import os
from pathlib import Path
import struct
import unittest

from scripts.build_gr3_roll_capture import build_observers, CAPTURE_API
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_READ
from unicorn.arm_const import *

ROOT = Path(__file__).resolve().parents[1]
CAMERA, ARENA = 0x56000000, 0x56010000
CONFIG, RECIPE, BACKING = 0x55010000, 0x55020000, 0x55030000
Y = 0x57000000
UV = Y + 1920 * 1088
STOP, STACK = 0x54e10000, 0x58f00000


class LiveProducerArmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stock = Path(os.environ.get('M10V_GR3_ORIGINAL_RTOS',
            ROOT / 'builds/gr3-pure-isp-feasibility-20261031/gr3-official-rtos.bin'))
        if not stock.is_file():
            raise unittest.SkipTest('pinned official GR III 2.10 RTOS required')
        cls.stock = stock.read_bytes()
        cls.imports = {name: 0x54e00000 + index * 4 for index, name in enumerate((
            *CAPTURE_API, 'm10v_roll_device_capture_channel', 'm10v_live_device_camera',
            'm10v_film_identity_owned', 'm10v_film_identity_read'))}
        cls.code, cls.manifest = build_observers(cls.stock, 0x54f00000, cls.imports, live=True)

    def machine(self):
        u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        u.mem_map(0x53000000, 0x02000000)
        u.mem_map(0x55000000, 0x04000000)
        u.mem_write(0x53000000, self.stock)
        u.mem_write(self.manifest['base'], self.code)
        for patch in self.manifest['patches']:
            u.mem_write(patch['address'], struct.pack('<I', patch['replacement']))
        u.reg_write(UC_ARM_REG_C1_C0_2, 0xf00000)
        u.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
        state = {'tick': 10000, 'clean': [], 'native': [], 'pixel_reads': 0}

        def put(a, *values):
            u.mem_write(a, struct.pack('<' + 'I' * len(values), *values))

        put(CAMERA, ARENA)
        put(CAMERA + 36, 10000)  # consumer_tick: original camera prefix is stable.
        put(ARENA, 0x31494c4d, 1, 111232, 7, 5)
        put(0x55040004, CONFIG)
        put(RECIPE + 4, 3)
        put(RECIPE + 0x60, Y - 0x1000)
        put(RECIPE + 0x9c, BACKING)
        put(RECIPE + 0x550, 0x1000)
        put(BACKING + 0x1c8, (1088 << 16) | 1920)
        u.mem_write(CONFIG, bytes([1, 0, 0, 0]))
        put(CONFIG + 4, (1920 << 16) | (2 << 8), (1008 << 16) | 1088,
            448, 0, 0x01010101, 0, 0, 0)
        u.mem_write(Y, bytes([42]) * (1920 * 1088))
        u.mem_write(ARENA + 128 + 128 + 128 + 24576, bytes([128]) * 12288)
        put(STACK, 0x55050000, 0)

        def trap(machine, a, size, _):
            result = None
            if a == self.imports['m10v_live_device_camera']:
                result = CAMERA
            elif a == self.imports['m10v_roll_device_capture_channel']:
                result = 0
            elif a == 0x53050b7c:
                put(machine.reg_read(UC_ARM_REG_R0), 0, state['tick'])
                result = 0
            elif a in (0x5383c834, 0x5383c870):
                state['clean'].append((a, machine.reg_read(UC_ARM_REG_R0),
                                       machine.reg_read(UC_ARM_REG_R1)))
                result = 0
            elif a == 0x536c3f9c:
                result = 0x55040000
            elif a == 0x536c4590:
                result = 1
            elif a == 0x536b93d0:
                result = 0
            elif a in (0x536c5ddc, 0x536c5d04):
                original_sp = machine.reg_read(UC_ARM_REG_SP)
                args = tuple(machine.reg_read(r) for r in (
                    UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3))
                state['native'].append((a, original_sp, args,
                    struct.unpack('<I', machine.mem_read(original_sp, 4))[0]))
                result = 1
            if result is not None:
                machine.reg_write(UC_ARM_REG_R0, result)
                machine.reg_write(UC_ARM_REG_PC, machine.reg_read(UC_ARM_REG_LR))

        def read(machine, access, a, size, value, _):
            if Y <= a < UV:
                state['pixel_reads'] += 1

        u.hook_add(UC_HOOK_CODE, trap)
        u.hook_add(UC_HOOK_MEM_READ, read)
        return u, state, put

    def display(self, u, configured=False):
        # Execute the actual stock caller from its prologue, not a synthetic
        # register tuple at the patched BL. r1=0 selects the configured branch.
        for reg, value in ((UC_ARM_REG_R0, RECIPE), (UC_ARM_REG_R1, int(not configured)),
                           (UC_ARM_REG_R2, 1), (UC_ARM_REG_R3, 0),
                           (UC_ARM_REG_SP, STACK), (UC_ARM_REG_LR, STOP)):
            u.reg_write(reg, value)
        u.emu_start(0x5345a21c, STOP, count=3000000)
        self.assertEqual(u.reg_read(UC_ARM_REG_PC), STOP)
        self.assertEqual(u.reg_read(UC_ARM_REG_SP), STACK)

    def diagnostic(self, u):
        return struct.unpack('<27I', u.mem_read(ARENA + 20, 108))

    def test_both_original_callers_keep_native_submit_and_publish_mono_frame(self):
        for configured in (False, True):
            with self.subTest(configured=configured):
                u, state, put = self.machine()
                self.display(u, configured)
                self.assertEqual(struct.unpack('<3I', u.mem_read(ARENA + 256, 12)), (2, 10000, 5))
                self.assertEqual(bytes(u.mem_read(ARENA + 384, 24576)), bytes([42]) * 24576)
                self.assertEqual(bytes(u.mem_read(ARENA + 384 + 24576, 12288)), bytes([128]) * 12288)
                self.assertEqual(state['native'][0][0], 0x536c5d04 if configured else 0x536c5ddc)
                self.assertEqual(state['native'][0][1], STACK - 56)
                self.assertEqual(state['native'][0][2],
                                 (CONFIG, 1, 0, 0 if configured else Y))
                if not configured:
                    self.assertEqual(state['native'][0][3], UV)
                d = self.diagnostic(u)
                self.assertEqual(d[1:3], (2, 1))
                self.assertEqual(d[8:19], (1, 10000, 10000, 5, 0, RECIPE,
                                          CONFIG, Y, UV, 3, 0))
                self.assertEqual(d[19:22], ((1920 << 16) | (2 << 8),
                                            (1008 << 16) | 1088, 448))

    def test_original_queue_marks_ready_frame_two_until_after_native_display(self):
        u, state, put = self.machine()
        queue, node, frames, controller = 0x55080000, 0x55080100, 0x55080200, 0x55090000
        put(queue, node)
        put(node, RECIPE, 0, 0)
        put(RECIPE + 4, 1)  # Ready producer node before stock extraction.
        for reg, value in ((UC_ARM_REG_R0, queue), (UC_ARM_REG_R1, frames),
                           (UC_ARM_REG_SP, STACK), (UC_ARM_REG_LR, STOP)):
            u.reg_write(reg, value)
        u.emu_start(0x5345a7ec, STOP, count=100000)
        self.assertEqual(u.reg_read(UC_ARM_REG_PC), STOP)
        self.assertEqual(bytes(u.mem_read(RECIPE + 4, 1)), b'\x02')
        self.assertEqual(struct.unpack('<I', u.mem_read(frames, 4))[0], RECIPE)
        put(controller + 0xaa4, queue)
        u.mem_write(0x55084f78, b'\x01')
        u.mem_write(controller + 0xac1, b'\x01\x01\x01')
        put(STACK - 0x44, 0)
        # The stock caller invokes display first, THEN publishes state3 at
        # 534495a4. Execute both; no fixture writes state2/3 around the hook.
        for reg, value in ((UC_ARM_REG_R1, RECIPE), (UC_ARM_REG_R9, controller),
                           (UC_ARM_REG_R10, frames), (UC_ARM_REG_R11, STACK),
                           (UC_ARM_REG_SP, STACK - 128), (UC_ARM_REG_LR, STOP)):
            u.reg_write(reg, value)
        u.emu_start(0x53449468, 0x534493d0, count=3000000)
        self.assertEqual(u.reg_read(UC_ARM_REG_PC), 0x534493d0)
        self.assertEqual(bytes(u.mem_read(RECIPE + 4, 1)), b'\x03')
        self.assertEqual(struct.unpack('<I', u.mem_read(ARENA + 256, 4))[0], 2,
                         'state2 native display was rejected before stock could publish state3')
        self.assertEqual(self.diagnostic(u)[17], 2)

    def test_live_observers_fit_fixed_texture_budget_with_identical_sampling(self):
        # The complete R12 renderer previously crossed its immutable texture
        # boundary by364 bytes with a6036-byte observer. This bound retains
        # every capture/Live export and the same nine preimage-checked hooks.
        self.assertLessEqual(len(self.code), 5596)
        self.assertEqual(len(self.manifest['patches']), 9)
        u, state, put = self.machine()
        for row in range(448):
            u.mem_write(Y + 1920 * row, bytes((row * 3 + col) & 255 for col in range(1008)))
        self.display(u)
        expected = bytes((((row * 7) >> 1) * 3 + ((col * 21) >> 2)) & 255
                         for row in range(128) for col in range(192))
        self.assertEqual(bytes(u.mem_read(ARENA + 384, 24576)), expected)

    def test_shared_exif_allocator_retains_distinct_roll_and_live_tags(self):
        u, state, put = self.machine()
        seen = []

        def exif(machine, a, size, _):
            regs = [machine.reg_read(r) for r in (
                UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)]
            if a == 0x535d0998:
                self.assertEqual(regs[0], 24)
                result = 0x55060000
            elif a == 0x535d0230:
                self.assertEqual(regs[0], 0x55060000)
                seen.append(tuple(regs[1:]))
                self.assertEqual(struct.unpack('<I', machine.mem_read(
                    machine.reg_read(UC_ARM_REG_SP), 4))[0], 0)
                result = 0
            elif a == 0x535cfaa0:
                self.assertEqual(tuple(regs[:2]), (0x55070000, 0x55060000))
                result = 0
            else:
                return
            machine.reg_write(UC_ARM_REG_R0, result)
            machine.reg_write(UC_ARM_REG_PC, machine.reg_read(UC_ARM_REG_LR))

        u.hook_add(UC_HOOK_CODE, exif)
        for name in ('m10v_live_camera_insert_tag', 'm10v_roll_camera_insert_tag'):
            u.reg_write(UC_ARM_REG_R0, 0x55070000)
            u.reg_write(UC_ARM_REG_SP, STACK)
            u.reg_write(UC_ARM_REG_LR, STOP)
            u.emu_start(self.manifest['exports'][name], STOP, count=100000)
            self.assertEqual(u.reg_read(UC_ARM_REG_PC), STOP)
            self.assertEqual(u.reg_read(UC_ARM_REG_SP), STACK)
        self.assertEqual(seen, [(0xc7f3, 7, 24), (0xc7f2, 7, 32)])

    def test_lease_and_source_rejection_are_distinct_and_never_read_pixels(self):
        for change, counter, reason in (('lease', 4, 0), ('recipe', 6, 2),
                                        ('free', 6, 2), ('retired', 6, 2),
                                        ('planes', 6, 12), ('geometry', 6, 7)):
            with self.subTest(change=change):
                u, state, put = self.machine()
                if change == 'lease':
                    put(CAMERA + 36, 1000)
                elif change == 'recipe':
                    put(RECIPE + 4, 1)  # Never borrow an unclassified/RAW source.
                elif change == 'free':
                    put(RECIPE + 4, 0)
                elif change == 'retired':
                    put(RECIPE + 4, 4)
                elif change == 'planes':
                    put(CONFIG + 4 + 20, Y + 64, UV + 64)
                else:
                    put(CONFIG + 4 + 4, (1007 << 16) | 1088)
                self.display(u)
                d = self.diagnostic(u)
                self.assertEqual((d[1], d[2], d[counter], d[12]), (2, 1, 1, reason))
                self.assertEqual(state['pixel_reads'], 0)
                self.assertEqual(struct.unpack('<I', u.mem_read(ARENA + 256, 4))[0], 0)
                self.assertEqual(len(state['native']), 1)

    def test_after_only_waits_for_matching_shutter_before_any_pixel_read(self):
        u, state, put = self.machine()
        put(ARENA + 16, 6)
        self.display(u)
        d = self.diagnostic(u)
        self.assertEqual((d[7], d[12], d[8], state['pixel_reads']), (1, 0, 0, 0))
        put(ARENA + 128, 2, 10000, 6)
        state['tick'] += 1000
        self.display(u)
        self.assertEqual(self.diagnostic(u)[8], 1)
        self.assertEqual(struct.unpack('<3I', u.mem_read(ARENA + 256, 12)), (2, 11000, 6))

    def test_after_only_capture_blackout_window_stops_after6500ms(self):
        for elapsed, expected in ((6500, 1), (6501, 0)):
            with self.subTest(elapsed=elapsed):
                u, state, put = self.machine()
                put(ARENA + 16, 6)
                put(ARENA + 128, 2, 10000, 6)
                state['tick'] = 10000 + elapsed
                put(CAMERA + 36, state['tick'])  # keep existing lease valid.
                self.display(u)
                self.assertEqual(self.diagnostic(u)[8], expected)
                self.assertEqual(self.diagnostic(u)[7], 1 - expected)
                self.assertEqual(bool(state['pixel_reads']), bool(expected))

    def test_unsafe_metadata_pointer_is_rejected_by_helper_without_pixel_access(self):
        u, state, put = self.machine()
        helper = self.manifest['exports']['m10v_live_camera_display']
        for reg, value in ((UC_ARM_REG_R0, 0x1234), (UC_ARM_REG_R1, CONFIG),
                           (UC_ARM_REG_R2, Y), (UC_ARM_REG_R3, UV),
                           (UC_ARM_REG_SP, STACK), (UC_ARM_REG_LR, STOP)):
            u.reg_write(reg, value)
        u.emu_start(helper, STOP, count=100000)
        self.assertEqual(u.reg_read(UC_ARM_REG_PC), STOP)
        d = self.diagnostic(u)
        self.assertEqual((d[6], d[12], d[17]), (1, 1, 0xffffffff))
        self.assertEqual(state['pixel_reads'], 0)

    def test_diagnostics_are_bounded_and_show_mode_off_entry(self):
        u, state, put = self.machine()
        put(ARENA + 16, 4)
        self.display(u)
        d = self.diagnostic(u)
        self.assertEqual((d[1], d[2], d[3]), (2, 1, 1))
        first = len([v for v in state['clean'] if v[1] == ARENA])
        for _ in range(10):
            self.display(u)
        self.assertEqual(len([v for v in state['clean'] if v[1] == ARENA]), first)
        state['tick'] += 1000
        self.display(u)
        self.assertEqual(self.diagnostic(u)[2:4], (12, 12))
        # Odd and committed snapshots each clean the existing control line.
        self.assertEqual(len([v for v in state['clean'] if v[1] == ARENA]), first + 2)

    def test_later_stale_lease_and_mode_off_retain_source_rejection_snapshot(self):
        u, state, put = self.machine()
        bad = (1007 << 16) | 1088
        put(CONFIG + 8, bad)
        self.display(u)
        source = self.diagnostic(u)[12:]
        self.assertEqual(source[0], 7)
        put(CONFIG + 8, (1008 << 16) | 1088)
        state['tick'] = 20000
        self.display(u)
        d = self.diagnostic(u)
        self.assertEqual(d[12:], source)
        self.assertEqual((d[4], d[6], d[9], d[10]), (1, 1, 20000, 10000))
        put(ARENA + 16, 8)
        state['tick'] += 1000
        self.display(u)
        self.assertEqual(self.diagnostic(u)[12:], source)
        self.assertEqual(state['pixel_reads'], 0)

    def test_r12_observed_upper_alias_planes_follow_same_native_contract(self):
        u, state, put = self.machine()
        y = 0xb47bfe40
        uv = 0xb49bde40
        u.mem_map(0xb4700000, 0x400000)
        u.mem_write(y, bytes([73]) * (1920 * 1088))
        put(RECIPE + 0x60, y - 0x1000)
        self.display(u)
        self.assertEqual(struct.unpack('<I', u.mem_read(ARENA + 256, 4))[0], 2)
        self.assertEqual(bytes(u.mem_read(ARENA + 384, 24576)), bytes([73]) * 24576)
        self.assertEqual(self.diagnostic(u)[15:17], (y, uv))

    def test_compact_diagnostic_branches_keep_every_profile_and_backing_guard(self):
        cases = (
            (CONFIG + 4, (1920 << 16) | (1 << 8), 7),
            (CONFIG + 8, (1007 << 16) | 1088, 7),
            (CONFIG + 12, 447, 7),
            (CONFIG + 16, 1, 7),
            (CONFIG + 32, 1, 7),
            (RECIPE + 0x9c, 0x1234, 13),
            (BACKING + 0x1c8, (1088 << 16) | 1919, 13),
            (RECIPE + 0x550, 0x1040, 13),
        )
        for at, value, reason in cases:
            with self.subTest(at=hex(at), value=hex(value)):
                u, state, put = self.machine()
                put(at, value)
                # Corrupt metadata must be tested at the guarded helper:
                # the stock caller itself dereferences/derives these fields
                # before the hook, and cannot be used as a corruption stub.
                for reg, value in ((UC_ARM_REG_R0, RECIPE), (UC_ARM_REG_R1, CONFIG),
                                   (UC_ARM_REG_R2, Y), (UC_ARM_REG_R3, UV),
                                   (UC_ARM_REG_SP, STACK), (UC_ARM_REG_LR, STOP)):
                    u.reg_write(reg, value)
                u.emu_start(self.manifest['exports']['m10v_live_camera_display'],
                            STOP, count=100000)
                self.assertEqual(u.reg_read(UC_ARM_REG_PC), STOP)
                self.assertEqual(self.diagnostic(u)[12], reason)
                self.assertEqual(self.diagnostic(u)[6], 1)
                self.assertEqual(state['pixel_reads'], 0)
                self.assertEqual(struct.unpack('<I', u.mem_read(ARENA + 256, 4))[0], 0)


if __name__ == '__main__':
    unittest.main()
