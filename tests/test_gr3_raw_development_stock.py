"""Execute the native RAW Image Control chooser and apply/cancel on both models."""
import os
from pathlib import Path
import struct
import unittest

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm_const as arm

from scripts.probe_gr3_raw_guides_adj import ROM, RAM, SP, call, decode

ROOT = Path(__file__).resolve().parents[1]
MODEL, INPUT, WORKING, PROPERTY = (RAM + offset for offset in (0x10000, 0x20000, 0x30000, 0x40000))
AS_SHOT_TONE = 17
CONTROL_COUNT, CONTROL_CAPACITY = 0x53283358, 0x532833BC
CONTROL_CATEGORY, CONTROL_VALUE = 0x532834D0, 0x532834F0
CONTROL_SELECT, CONTROL_RESTORE = 0x5318A6D0, 0x53289314
APPLIED_TONE = 0x5328926C
# Only allocator and message-queue boundaries are substituted. The two packet
# builders, owner transfer and mode mapping are firmware instructions.
EVENT_OWNER, GEOMETRY, PACKET, PARAMS = (RAM + n for n in (0x50000, 0x52000, 0x53000, 0x54000))
PROCESSING_OWNER, DEVICE = RAM + 0x55000, RAM + 0x57000
ENQUEUE = 0x534D6260


class StockRawDevelopment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.images = {}
        for model, filename in (('gr3', 'fwdc239b-gr3-official.bin'), ('gr3x', 'fwdc243b-gr3x-official.bin')):
            candidate = os.environ.get('M10V_RAW_STOCK_PROBE_' + model.upper())
            path = Path(candidate) if candidate else ROOT / 'bin' / filename
            cls.images[model] = decode(path)

    def machine(self, rom, extra_returns=None):
        cpu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        cpu.ctl_set_cpu_model(arm.UC_CPU_ARM_CORTEX_A9)
        cpu.reg_write(arm.UC_ARM_REG_C1_C0_2, 0xf00000)
        cpu.reg_write(arm.UC_ARM_REG_FPEXC, 0x40000000)
        cpu.mem_map(ROM, (len(rom) + 4095) & ~4095)
        cpu.mem_write(ROM, rom)
        cpu.mem_map(RAM, 0x100000)
        for address, value in ((MODEL + 0x18, PROPERTY), (MODEL + 0x24, INPUT), (PROPERTY + 4, WORKING)):
            cpu.mem_write(address, struct.pack('<I', value))
        cpu.mem_write(INPUT + 0x77c, bytes([AS_SHOT_TONE]))
        cpu.mem_write(MODEL + 0x83, bytes([1, 3, 7]))

        returns = {0x5320AD88: 0, 0x5320B37C: MODEL, 0x53553AD4: 1, 0x5355198C: 0}
        if extra_returns:
            returns.update(extra_returns)

        def boundary(u, address, size, _):
            if address in returns:
                u.reg_write(arm.UC_ARM_REG_R0, returns[address])
                u.reg_write(arm.UC_ARM_REG_PC, u.reg_read(arm.UC_ARM_REG_LR))
        cpu.hook_add(UC_HOOK_CODE, boundary)
        return cpu

    def test_native_image_control_row_categories_and_values(self):
        for model, rom in self.images.items():
            with self.subTest(model=model):
                cpu = self.machine(rom)
                self.assertEqual(call(cpu, CONTROL_CAPACITY, MODEL), 15)
                for with_as_shot in (0, 1):
                    cpu.mem_write(MODEL + 5, bytes([with_as_shot]))
                    count = call(cpu, CONTROL_COUNT, MODEL)
                    categories = [call(cpu, CONTROL_CATEGORY, MODEL, row) for row in range(count)]
                    values = [call(cpu, CONTROL_VALUE, MODEL, row) for row in range(count)]
                    self.assertEqual(categories, [0] * (12 + with_as_shot) + [1, 2])
                    self.assertEqual(values, [0] * with_as_shot + list(range(1, 13)) + [3, 7])

    def test_native_select_and_restore_keep_input_separate(self):
        for model, rom in self.images.items():
            with self.subTest(model=model):
                cpu = self.machine(rom)
                cpu.mem_write(MODEL + 5, b'\x01')
                cpu.mem_write(MODEL + 0x39f, b'\x00\x00')
                call(cpu, CONTROL_SELECT, 0, 2, stop=APPLIED_TONE)
                self.assertEqual(bytes(cpu.mem_read(MODEL + 0x82, 2)), b'\x00\x02')
                self.assertEqual(bytes(cpu.mem_read(WORKING + 0x77c, 1)), b'\x0c')
                call(cpu, CONTROL_RESTORE, MODEL, stop=APPLIED_TONE)
                self.assertEqual(bytes(cpu.mem_read(MODEL + 0x82, 2)), b'\x00\x00')
                self.assertEqual(bytes(cpu.mem_read(WORKING + 0x77c, 1)), bytes([AS_SHOT_TONE]))
                self.assertEqual(bytes(cpu.mem_read(INPUT + 0x77c, 1)), bytes([AS_SHOT_TONE]))

    def test_as_shot_reuses_each_input_when_the_model_reopens(self):
        for model, rom in self.images.items():
            with self.subTest(model=model):
                cpu = self.machine(rom)
                cpu.mem_write(MODEL + 5, b'\x01')
                for index, tone in enumerate((17, 21, 11)):
                    source = INPUT + index * 0x1000
                    cpu.mem_write(source + 0x77c, bytes([tone]))
                    cpu.mem_write(MODEL + 0x24, struct.pack('<I', source))
                    call(cpu, CONTROL_SELECT, 0, 0, stop=APPLIED_TONE)
                    self.assertEqual(bytes(cpu.mem_read(MODEL + 0x82, 2)), b'\x00\x00')
                    self.assertEqual(bytes(cpu.mem_read(WORKING + 0x77c, 1)), bytes([tone]))


    def test_preview_and_save_pass_their_own_si_to_processing(self):
        for model, rom in self.images.items():
            with self.subTest(model=model):
                cpu = self.machine(rom, {
                    0x536AF2A8: PACKET + 0x100,  # callback allocation
                    0x5382CAE4: DEVICE,         # queue service
                    0x5382D074: PACKET,         # event packet allocation
                    0x534DFF80: 1,              # source device
                    0x53522688: 0,              # processing notification
                    0x53520BDC: 0,              # optional processing flag
                })
                cpu.mem_write(GEOMETRY, struct.pack('<B x H H', 0, 1280, 854))
                cpu.mem_write(PROCESSING_OWNER + 0x9b0, struct.pack('<I', DEVICE))
                for expected in (9, 12, 10, 11, 9):
                    with self.subTest(mode=expected):
                        save = expected == 12
                        source = INPUT if save else WORKING
                        event = 0x72c8100e if save else 0x72c8100d
                        entry = 0x534d6ab8 if save else 0x534d65c0
                        cpu.mem_write(PACKET, bytes(0x18))
                        same_size = expected in (10, 11)
                        cpu.mem_write(PROCESSING_OWNER + 0x998,
                                      struct.pack('<HH', 1280 * same_size, 854 * same_size))
                        cpu.mem_write(SP, struct.pack('<II', int(save or expected == 10), 0))
                        cpu.reg_write(arm.UC_ARM_REG_R3, 0 if save else source)
                        call(cpu, entry, EVENT_OWNER, GEOMETRY, source if save else 0, stop=ENQUEUE)
                        self.assertEqual(cpu.reg_read(arm.UC_ARM_REG_R1), event)
                        self.assertEqual(cpu.reg_read(arm.UC_ARM_REG_R2), PACKET)
                        si_offset = 0x10 if save else 0x14
                        self.assertEqual(struct.unpack('<I', cpu.mem_read(PACKET + si_offset, 4))[0], source)
                        receive = 0x53516bfc if save else 0x53516b40
                        call(cpu, receive, PROCESSING_OWNER, PACKET)
                        self.assertEqual(struct.unpack('<I', cpu.mem_read(PROCESSING_OWNER + 0x9a8, 4))[0], source)
                        self.assertEqual(cpu.mem_read(PROCESSING_OWNER + 0x9ad, 1)[0], int(save))
                        call(cpu, 0x53516c78, PROCESSING_OWNER, PARAMS)
                        self.assertEqual(call(cpu, 0x5350e000, PROCESSING_OWNER, 1, PARAMS), expected)

    def test_batch_success_requests_the_next_index_before_saving_again(self):
        result, indices = RAM + 0x58000, RAM + 0x59000
        for model, rom in self.images.items():
            with self.subTest(model=model):
                cpu = self.machine(rom, {
                    0x536b93d0: 0,  # logging
                    0x5327f93c: 0,  # display progress
                    0x5313d850: 0,  # progress percentage is outside the reload path
                    0x5327f3e8: 0,  # prepare notification
                    0x5320b07c: DEVICE,
                })
                cpu.mem_write(MODEL + 4, bytes((1, 1)))
                cpu.mem_write(MODEL + 8, struct.pack('<III', 3, indices, 0))
                cpu.mem_write(indices, struct.pack('<III', 0xa3, 0xb4, 0x37))
                cpu.mem_write(PACKET + 8, struct.pack('<I', result))
                cpu.mem_write(result, b'\x01')
                for sequence, next_file in ((1, 0xb4), (2, 0x37)):
                    call(cpu, 0x5327fc14, MODEL, PACKET, stop=0x5322b6e4)
                    self.assertEqual(cpu.reg_read(arm.UC_ARM_REG_R1), 0x44411019)
                    self.assertEqual(cpu.reg_read(arm.UC_ARM_REG_R2), next_file)
                    self.assertEqual(struct.unpack('<I', cpu.mem_read(MODEL + 0x10, 4))[0], sequence)

    def test_dng_makernote_dispatch_copies_identity_to_each_file_item(self):
        dng, extractor, entry, file_item = (RAM + n for n in (0x60000, 0x61000, 0x62000, 0x63000))
        for model, rom in self.images.items():
            with self.subTest(model=model):
                cpu = self.machine(rom, {0x534dfb40: 1})  # RAW-format query
                # An official reader has the original "unknown tone" move at
                # this site. An M10V candidate runs the recorded-tone decoder.
                private_codes = rom[0x5c251c:0x5c2520] != struct.pack('<I', 0x83a02000)
                for index, (code, external) in enumerate(((0x1021, False), (0x1043, True), (0xe0c6, False))):
                    item = file_item + index * 0x1000
                    cpu.mem_write(dng, bytes(0x4ac))
                    cpu.mem_write(extractor + 4, struct.pack('<I', dng))
                    call(cpu, 0x535f1414, extractor)
                    cpu.mem_write(entry + 4, struct.pack('<H', 0x4f))
                    cpu.mem_write(entry + 12, struct.pack('<H2xI', code, entry + 0x100 if external else 0))
                    if external:
                        cpu.mem_write(entry + 0x100, struct.pack('<H', code))
                    self.assertEqual(call(cpu, 0x535f2394, extractor, entry, 4), 1)
                    call(cpu, 0x534eae74, dng, item, stop=0x534eafcc)
                    expected = 0x20000 | (code - 0x100) if private_codes and index < 2 else 0
                    self.assertEqual(struct.unpack('<I', cpu.mem_read(item + 0x220, 4))[0], expected)
                    self.assertEqual(bytes(cpu.mem_read(item + 0x25, 2)), b'\x01\x01')


if __name__ == '__main__':
    unittest.main()
