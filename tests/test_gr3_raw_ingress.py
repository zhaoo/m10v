"""Exercise RAW transport trampolines against both official instruction sets."""
import struct
import unittest

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm_const as A

from scripts.build_gr3_film_slot_extension import build_appended_slots
from scripts.build_gr3_m10v_library import capture_stock_rtos

ROM, RAM, CODE, IDENTITY = 0x53000000, 0x55000000, 0x54180000, 0x54160000
CALLBACK, CLEAR = 0x54170000, 0x54170004
TASK, FILE, REQUEST, ORIGINAL = 0x55010000, 0x55011000, 0x55012000, 0x55013000
SOURCE, DEST, RECIPE = 0x55100000, 0x55200000, 0x55300000
OTHER_FILE, OTHER_SOURCE = 0x55016000, 0x55180000
SP, SI_BYTES = 0x553f0000, 0x74270
REG = (A.UC_ARM_REG_R0, A.UC_ARM_REG_R1, A.UC_ARM_REG_R2, A.UC_ARM_REG_R3)


class RawIngress(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.images = {name: capture_stock_rtos(name) for name in ('gr3', 'gr3x')}

    def test_request_selection_stays_with_its_file_through_recipe_copy(self):
        for model, stock in self.images.items():
            with self.subTest(model=model):
                self.exercise(stock)

    def exercise(self, stock):
        from scripts.build_gr3_raw_ingress import build_raw_ingress
        # The test exercises the existing copy adapter too. Its one C callback
        # is a boundary stub so we can observe the exact invocation and order.
        symbols = dict.fromkeys((
            'm10v_camera_library_shooting_count', 'm10v_menu_recorded_icon',
            'm10v_isp_frame_identity_code',
            *(f'm10v_tone_menu_{name}' for name in (
                'index', 'menu_name', 'menu_icon', 'adj_name', 'adj_icon', 'menu_matches',
                'adj_matches', 'adj_select',
            )),
            *(f'm10v_menu_playback_name_{name}' for name in ('create', 'destroy', 'refresh')),
        ), CALLBACK)
        symbols.update(m10v_isp_frame_identity_clear=CLEAR, m10v_isp_frame_raw_snapshot=CALLBACK)
        identity, appended = build_appended_slots(IDENTITY, IDENTITY, stock, symbols)
        identity_copy = appended['playback']['identity_hooks']['copy']
        image, report = build_raw_ingress(
            CODE, stock, symbols, identity_copy)
        u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        u.ctl_set_cpu_model(A.UC_CPU_ARM_CORTEX_A9)
        u.reg_write(A.UC_ARM_REG_C1_C0_2, 0xf00000)
        u.reg_write(A.UC_ARM_REG_FPEXC, 0x40000000)
        u.mem_map(ROM, 0x1200000)
        u.mem_write(ROM, stock)
        u.mem_write(CODE, image)
        u.mem_write(IDENTITY, identity)
        for patch in report['patches']:
            u.mem_write(patch['address'], struct.pack('<I', patch['replacement']))
        u.mem_map(RAM, 0x400000)
        snapshots = []
        cleared = []
        copy_source = SOURCE
        original = {0x5355e87c, 0x534bffe4, 0x534d6ab8}

        def word(address):
            return struct.unpack('<I', u.mem_read(address, 4))[0]

        def write(address, value):
            u.mem_write(address, struct.pack('<I', value))

        def boundary(cpu, address, _size, _user):
            if address == CALLBACK:
                snapshots.append(tuple(cpu.reg_read(r) for r in REG[:3]))
                if copy_source:
                    self.assertEqual(u.mem_read(DEST, SI_BYTES), u.mem_read(copy_source, SI_BYTES))
                    self.assertEqual(word(DEST + SI_BYTES), 0)
            elif address == CLEAR:
                self.assertEqual(cpu.reg_read(REG[0]), DEST)
                self.assertEqual(word(DEST + SI_BYTES), 0xfacefeed)
                write(DEST + SI_BYTES, 0)
                cleared.append(address)
            elif address == 0x536af2a8:
                self.assertEqual(cpu.reg_read(REG[0]), SI_BYTES + 16)
                cpu.reg_write(REG[0], SOURCE)
            elif address not in original:
                return
            cpu.reg_write(A.UC_ARM_REG_PC, cpu.reg_read(A.UC_ARM_REG_LR))

        u.hook_add(UC_HOOK_CODE, boundary)

        def run(start, end, *, r0=0, r1=0, r2=0, r3=0, r4=0, r5=0, r7=0, fp=0,
                stock_frame=0):
            for reg, value in zip(REG, (r0, r1, r2, r3)):
                u.reg_write(reg, value)
            for reg, value in ((A.UC_ARM_REG_R4, r4), (A.UC_ARM_REG_R5, r5), (A.UC_ARM_REG_R7, r7),
                               (A.UC_ARM_REG_SP, SP), (A.UC_ARM_REG_R11, fp)):
                u.reg_write(reg, value)
            u.emu_start(start, end, count=400000)
            self.assertEqual(u.reg_read(A.UC_ARM_REG_PC), end)
            self.assertEqual(u.reg_read(A.UC_ARM_REG_SP), SP - stock_frame)
            return u.reg_read(REG[0])

        def copy(mode, source=SOURCE):
            nonlocal copy_source
            copy_source = source
            write(DEST + SI_BYTES, 0xfacefeed)
            previous = len(cleared)
            result = run(0x53510830, 0x53510834,
                         r0=DEST, r1=source, r2=SI_BYTES, r4=RECIPE, r5=mode)
            self.assertEqual(result, DEST)
            self.assertEqual(len(cleared), previous + 1)
            self.assertEqual(word(DEST + SI_BYTES), 0)

        def no_source(mode):
            nonlocal copy_source
            copy_source = 0
            write(DEST + SI_BYTES, 0xfacefeed)
            previous = len(cleared)
            result = run(0x53510800, 0x53510834, r0=RECIPE, r1=mode, stock_frame=32)
            self.assertEqual(result, RECIPE)
            self.assertEqual(len(cleared), previous)
            self.assertEqual(word(DEST + SI_BYTES), 0xfacefeed)

        write(0x55086f4c, 1)
        write(0x55086f28, TASK)
        write(TASK, 0x53c5bf08)
        write(TASK + 0x24, FILE)
        u.mem_write(TASK + 0x21, b'\x01')
        for item in (FILE, OTHER_FILE):
            u.mem_write(item + 0x12, b'\x01')
            u.mem_write(item + 0x25, b'\x01\x01')
            write(item + 0x5d0, 0x55014000)
        u.mem_write(SOURCE, b'\x5a' * SI_BYTES)
        u.mem_write(SOURCE + 0x77c, b'\x0b')
        u.mem_write(SOURCE + SI_BYTES, b'\xaa' * 16)
        run(0x534bf1d4, 0x534bf1ec, r4=TASK)
        self.assertEqual(word(TASK + 0x28), SOURCE)
        self.assertEqual(u.mem_read(SOURCE + SI_BYTES, 16), bytes(16))

        for mode, item, choice, tag, expected in (
            (9, FILE, 0x4d520000, 0x20f43, 0x1043),
            (12, FILE, 0x4d520000, 0x20f43, 0x1043),
            (12, OTHER_FILE, 0x4d520000, 0x20f21, 0x1021),
            (11, OTHER_FILE, 0x4d520043, 0x20f21, 0x1043),
            (10, OTHER_FILE, 0x4d520043, 1, 0x1043),
            (12, FILE, 0x4d52ffff, 0x20f43, 0),
            (12, FILE, 0, 0x20f43, 0),
            (12, FILE, 0x4d520000, 0x1000c, 0),
        ):
            with self.subTest(mode=mode, choice=choice, tag=tag):
                save = mode == 12
                offset = 0x82c if save else 0x83c
                clone = 0x534a5530 if save else 0x534a47ac
                emit = 0x534c17fc if save else 0x534c1128
                write(TASK + 0x24, item)
                write(item + 0x220, tag)
                write(ORIGINAL + offset, choice)
                write(REQUEST + offset, 0xa5a5a5a5)
                run(clone, clone + 4, r3=7, r4=REQUEST, r7=ORIGINAL)
                self.assertEqual(word(REQUEST + offset), choice)
                if save:
                    self.assertEqual(u.mem_read(REQUEST + 0x828, 1), b'\x07')
                frame = 0x55015000
                write(frame - (0x868 if save else 0x8c0), REQUEST)
                run(emit, emit + 4, r2=SOURCE, r7=TASK, fp=frame)
                copy(mode)
                self.assertEqual(snapshots[-1], (RECIPE, mode, expected))
                self.assertEqual(u.mem_read(SOURCE + 0x77c, 1), b'\x0b')
                if expected:
                    no_source(mode)
                    self.assertEqual(snapshots[-1], (RECIPE, mode, 0))
                    wrong_mode = 9 if save else 12
                    copy(wrong_mode)
                    self.assertEqual(snapshots[-1], (RECIPE, wrong_mode, 0))
                    copy(mode, OTHER_SOURCE)
                    self.assertEqual(snapshots[-1], (RECIPE, mode, 0))
                    write(TASK + 0x24, OTHER_FILE if item == FILE else FILE)
                    copy(mode)
                    self.assertEqual(snapshots[-1], (RECIPE, mode, 0))
                    write(TASK + 0x24, item)
                    u.mem_write(item + 0x25, b'\x00')
                    copy(mode)
                    self.assertEqual(snapshots[-1], (RECIPE, mode, 0))
                    u.mem_write(item + 0x25, b'\x01')
                run(emit + 4, emit + 8, r7=TASK)
                self.assertEqual(word(SOURCE + SI_BYTES), 0)
                copy(mode)
                self.assertEqual(snapshots[-1], (RECIPE, mode, 0))

        before = len(snapshots)
        copy(0)
        no_source(0)
        self.assertEqual(len(snapshots), before)
