"""Exercise the RAW-only chooser and both request markers in the delivered RTOS."""
import json
import os
from pathlib import Path
import struct
import unittest

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm_const as arm

from scripts.probe_gr3_raw_guides_adj import RAM, ROM, SP, call, decode, sha
from tests import test_gr3_raw_development_stock as stock

INPUT, MODEL, PROPERTY, WORKING = stock.INPUT, stock.MODEL, stock.PROPERTY, stock.WORKING

STOCK_MODEL = 0x550666e0
PREVIEW, SAVE = 0x55051000, 0x55052000


class RawFilmMenu(unittest.TestCase):
    def test_native_chooser_and_request_markers(self):
        folders = [os.environ.get('M10V_RAW_MENU_' + model.upper()) for model in ('gr3', 'gr3x')]
        if not all(folders):
            self.skipTest('set both final RAW menu candidate directories')
        for model, folder in zip(('gr3', 'gr3x'), folders):
            with self.subTest(model=model):
                self.verify_candidate(model, Path(folder))

    def verify_candidate(self, model, folder):
        manifest = json.loads((folder / 'M10V-runtime-manifest.json').read_text())
        receipt = json.loads((folder / 'M10V-build-receipt.json').read_text())
        path = folder / receipt['filename']
        self.assertEqual(manifest['camera_model'], model)
        self.assertEqual(sha(path.read_bytes()), receipt['candidate_sha256'])
        rom = decode(path)
        at = manifest['base'] - ROM
        self.assertEqual(sha(rom[at:at + manifest['code_bytes']]), manifest['code_sha256'])
        symbols = manifest['symbols']
        raw_symbols = {k: symbols['m10v_raw_menu_' + k] for k in (
            'init', 'model', 'destroy', 'count', 'capacity', 'row', 'current',
        )}
        u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        u.ctl_set_cpu_model(arm.UC_CPU_ARM_CORTEX_A9)
        u.reg_write(arm.UC_ARM_REG_C1_C0_2, 0xf00000)
        u.reg_write(arm.UC_ARM_REG_FPEXC, 0x40000000)
        u.mem_map(ROM, (len(rom) + 4095) & ~4095)
        u.mem_write(ROM, rom)
        u.mem_map(RAM, 0x100000)
        u.mem_write(0x55063d80, struct.pack('<I', 1))
        u.mem_write(0x550662d0, struct.pack('<I', 1))
        u.mem_map(0x5536d000, 0x1000)
        u.mem_write(0x5536d078, struct.pack('<2I', 0x53d624d8, 1))
        allocated, freed, posted = [], [], []
        allow_alloc = True
        heap = 0x55080000

        def platform(cpu, address, _size, _data):
            nonlocal heap
            r0, r1, r2, r3 = [cpu.reg_read(register) for register in (
                arm.UC_ARM_REG_R0, arm.UC_ARM_REG_R1, arm.UC_ARM_REG_R2, arm.UC_ARM_REG_R3)]
            if address in (0x536af2a8, 0x536af31c):
                allocated.append(r0)
                if r0 == 0x3cc and not allow_alloc:
                    result = 0
                elif len(allocated) == 1:
                    result = MODEL
                else:
                    result = heap
                    heap += (r0 + 7) & ~7
            elif address in (0x536af2e4, 0x536af358):
                freed.append(r0)
                result = 0
            elif address == 0x53553ad4:
                result = 1
            elif address == 0x5355198c:
                result = 0
            elif address == 0x5322b6e4:
                sp = cpu.reg_read(arm.UC_ARM_REG_SP)
                posted.append((r0, r1, r2, r3, sp, bytes(cpu.mem_read(sp, 4))))
                result = 0
            else:
                return
            cpu.reg_write(arm.UC_ARM_REG_R0, result)
            cpu.reg_write(arm.UC_ARM_REG_PC, cpu.reg_read(arm.UC_ARM_REG_LR))

        u.hook_add(UC_HOOK_CODE, platform)

        # The real singleton constructor initializes an independent stock model
        # prefix. Keep the standard selection/property fixtures after init.
        call(u, 0x5320b3c0, STOCK_MODEL, stop=0x5320b3c4)
        self.assertEqual(call(u, 0x5320b37c), MODEL)
        self.assertEqual(allocated, [0x3cc])
        for offset, address in ((0x18, PROPERTY), (0x24, INPUT)):
            u.mem_write(MODEL + offset, struct.pack('<I', address))
        u.mem_write(MODEL + 4, b'\x01\x01')
        u.mem_write(MODEL + 0x83, b'\x00\x03\x07')
        u.mem_write(PROPERTY + 4, struct.pack('<I', WORKING))
        u.mem_write(INPUT + 0x77c, b'\x11')

        def marker(site, request, offset):
            u.reg_write(arm.UC_ARM_REG_R3, 0)
            u.mem_write(SP, struct.pack('<I', 0x55123456))
            u.mem_write(request + offset - 4, b'\x5a' * 8)
            call(u, site, 0x55054000, 0x44411017, request, stop=site + 4)
            self.assertEqual(u.mem_read(request + offset - 4, 4), b'\x5a' * 4)
            self.assertEqual(posted[-1], (0x55054000, 0x44411017, request, 0,
                                          SP, struct.pack('<I', 0x55123456)))
            return struct.unpack('<I', u.mem_read(request + offset, 4))[0]

        # Mode zero keeps all original rows. Its new As Shot row returns
        # the original DNG's tone after choosing either stock or a film.
        u.mem_write(MODEL + 5, b'\0')
        u.mem_write(MODEL + 0x83, b'\1')
        self.assertEqual(call(u, 0x53283358, MODEL), 69 if model == 'gr3' else 65)
        self.assertEqual([call(u, 0x532834f0, MODEL, i) for i in range(14)],
                         list(range(1, 13)) + [3, 7])
        self.assertEqual(call(u, 0x532834f0, MODEL, 14), 0x10000)
        self.assertEqual(call(u, 0x532834d0, MODEL, 14), 0)
        self.assertEqual(call(u, raw_symbols['current'], MODEL), 0x10000)
        self.assertEqual(call(u, 0x5318a10c, MODEL, 0, 0x10000, stop=0x5318a110), 0xf8)
        self.assertEqual(call(u, 0x5318b460, MODEL, 0, 0x10000, stop=0x5318b464), 0x2e5)
        self.assertEqual(marker(0x53281978, PREVIEW, 0x83c), 0x4d520000)
        call(u, 0x531860a4, MODEL, stop=0x531860a8)
        call(u, 0x5318a6d0, 0, 0, stop=0x5328926c)
        self.assertEqual(marker(0x532831e8, SAVE, 0x82c), 0x4d52ffff)
        call(u, 0x5318add4, MODEL, stop=0x5328926c)
        self.assertEqual(marker(0x532831e8, SAVE, 0x82c), 0x4d520000)
        call(u, 0x5318a6d0, 0, 15, stop=0x5328926c)
        self.assertEqual(marker(0x53281978, PREVIEW, 0x83c), 0x4d520021)
        call(u, 0x5318a6d0, 0, 14, stop=0x5328926c)
        self.assertEqual(u.mem_read(MODEL + 0x82, 2), b'\x00\x00')
        self.assertEqual(u.mem_read(WORKING + 0x77c, 1), b'\x11')
        u.mem_write(INPUT + 0x77d, b'\x03')
        call(u, 0x53286e94, MODEL, stop=0x5355840c)
        self.assertEqual(u.reg_read(arm.UC_ARM_REG_R1), 3)
        self.assertEqual(call(u, raw_symbols['current'], MODEL), 0x10000)
        self.assertEqual(marker(0x53281978, PREVIEW, 0x83c), 0x4d520000)
        self.assertEqual(marker(0x532831e8, SAVE, 0x82c), 0x4d520000)

        u.mem_write(MODEL + 5, b'\1')
        u.mem_write(MODEL + 0x83, b'\0')
        self.assertEqual(marker(0x53281978, PREVIEW, 0x83c), 0x4d520000)
        self.assertEqual(marker(0x532831e8, SAVE, 0x82c), 0x4d520000)
        count = call(u, 0x53283358, MODEL)
        self.assertEqual(count, 69 if model == 'gr3' else 65)
        self.assertEqual(call(u, 0x53189b38), count)
        # Native list constructor and row-vector grower consume all rows.
        widget = call(u, 0x533ad7f0, 0x53b33c00 + 4 * 24)
        descriptors = 0x55068000
        u.mem_write(descriptors, bytes([26]) * count)
        u.reg_write(arm.UC_ARM_REG_R3, 58)
        call(u, 0x53394610, widget, descriptors, count)
        children = {call(u, 0x53394758, widget, i) for i in range(count)}
        self.assertEqual(len(children), count)
        self.assertNotIn(0, children)
        self.assertEqual([call(u, 0x532834f0, MODEL, i) for i in range(15)],
                         list(range(13)) + [3, 7])
        self.assertEqual(call(u, 0x532834f0, MODEL, 15), 0x10000 | 33)
        self.assertEqual(call(u, 0x532834d0, MODEL, 15), 0)
        self.assertEqual(call(u, 0x5318a10c, MODEL, 0, 0x10021, stop=0x5318a110), 703)
        self.assertEqual(call(u, 0x5318b460, MODEL, 0, 0x10021, stop=0x5318b464), 860)

        # As Shot checkpoint, tentative film, then cancel to this file.
        call(u, 0x531860a4, MODEL, stop=0x531860a8)
        call(u, 0x5318a6d0, 0, 15, stop=0x5328926c)
        self.assertEqual(u.mem_read(MODEL + 0x82, 2), b'\x00\x01')
        self.assertEqual(u.mem_read(WORKING + 0x77c, 1), b'\x0b')
        self.assertEqual(call(u, raw_symbols['current'], MODEL), 0x10000 | 33)
        self.assertEqual(marker(0x53281978, PREVIEW, 0x83c), 0x4d520021)
        self.assertEqual(marker(0x532831e8, SAVE, 0x82c), 0x4d520021)
        call(u, 0x5318add4, MODEL, stop=0x5328926c)
        self.assertEqual(marker(0x532831e8, SAVE, 0x82c), 0x4d520000)
        self.assertEqual(u.mem_read(INPUT + 0x77c, 1), b'\x11')

        # Another native row clears the private choice before applying.
        call(u, 0x5318a6d0, 0, 15, stop=0x5328926c)
        call(u, 0x5318a6d0, 0, 2, stop=0x5328926c)
        self.assertEqual(marker(0x532831e8, SAVE, 0x82c), 0x4d52ffff)
        for row, setting, value in ((13, 1, 3), (14, 2, 7)):
            call(u, 0x5318a6d0, 0, 15, stop=0x5328926c)
            call(u, 0x5318a6d0, 0, row, stop=0x5328926c)
            self.assertEqual(u.mem_read(MODEL + 0x82, 1), bytes([setting]))
            self.assertEqual(u.mem_read(MODEL + 0x83 + setting, 1), bytes([value]))
            self.assertEqual(marker(0x532831e8, SAVE, 0x82c), 0x4d52ffff)
        ids = {call(u, raw_symbols['row'], MODEL, i) for i in range(15, count)}
        self.assertNotIn(0x10000 | 289, ids)  # Charmera
        self.assertNotIn(0x10000 | 290, ids)  # Pixel
        self.assertEqual((0x10000 | 318) in ids, model == 'gr3')
        self.assertEqual(len(ids), count - 15)
        self.assertNotIn(0, ids)
        self.assertEqual(call(u, raw_symbols['row'], MODEL, count), 0)

        call(u, 0x5318a6d0, 0, 15, stop=0x5328926c)
        call(u, 0x5327ee7c, MODEL, stop=0x5327ee80)
        self.assertEqual(call(u, raw_symbols['current'], MODEL), 1)
        self.assertEqual(marker(0x532831e8, SAVE, 0x82c), 0x4d52ffff)
        call(u, 0x5320ac20)
        self.assertIn(MODEL, freed)
        allow_alloc = False
        call(u, 0x5320b3c0, STOCK_MODEL, stop=0x5320b3c4)
        self.assertEqual(call(u, raw_symbols['model']), STOCK_MODEL)
        self.assertEqual(call(u, 0x53283358, STOCK_MODEL), 14)
        self.assertEqual(call(u, 0x532833bc, STOCK_MODEL), 15)
