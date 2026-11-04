"""Run the installed playback-name hooks against each model's ARM firmware."""
import json
import os
from pathlib import Path
import struct
import unittest

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm_const as arm

from scripts.probe_gr3_raw_guides_adj import ENTRY, ROM, SP, call, decode, sha

OWNER = 0x55010000
ROOT_WIDGET = 0x55020000
METADATA = 0x55064dc8
WIDGET = 0x55050000


class DeliveredPlaybackNameTests(unittest.TestCase):
    def test_caption_on_both_models(self):
        folders = [os.environ.get('M10V_PLAYBACK_' + model.upper()) for model in ('gr3', 'gr3x')]
        if not all(folders):
            self.skipTest('set both final playback candidate directories')
        for model, folder in zip(('gr3', 'gr3x'), folders):
            with self.subTest(model=model):
                self.verify_caption(Path(folder), model)

    def verify_caption(self, folder, model):
        manifest = json.loads((folder / 'M10V-runtime-manifest.json').read_text())
        receipt = json.loads((folder / 'M10V-build-receipt.json').read_text())
        path = folder / receipt['filename']
        self.assertEqual(manifest['camera_model'], model)
        self.assertEqual(sha(path.read_bytes()), receipt['candidate_sha256'])
        rom = decode(path)
        start = manifest['base'] - ROM
        self.assertEqual(sha(rom[start:start + manifest['code_bytes']]), manifest['code_sha256'])
        name = manifest['appended_slots']['playback']['name']
        self.assertEqual(name['owner_offset'], 0x31c)
        self.assertEqual(name['owner_bytes'], 0x320)
        x, y, width, height = name['rect']
        # The label occupies the free strip between the still detail's
        # metadata row and native Image Control parameter grid.
        for slot in (0x21c, 0x224, 0x228, 0x27c, 0x280, 0x2c8, 0x2cc, 0x2d0):
            index = (slot - 0x15c) // 4
            left, top, w, h = struct.unpack_from('<4I', rom, 0xb30fa0 + 24 * index + 4)
            self.assertTrue(x + width <= left or left + w <= x or
                            y + height <= top or top + h <= y, hex(slot))

        u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        u.ctl_set_cpu_model(arm.UC_CPU_ARM_CORTEX_A9)
        u.reg_write(arm.UC_ARM_REG_C1_C0_2, 0xf00000)
        u.reg_write(arm.UC_ARM_REG_FPEXC, 0x40000000)
        u.mem_map(ROM, (len(rom) + 4095) & ~4095)
        u.mem_write(ROM, rom)
        u.mem_map(0x55000000, 0x100000)
        u.mem_map(0x5536d000, 0x1000)
        u.mem_write(0x5536d078, struct.pack('<2I', 0x53d624d8, 1))
        u.mem_write(0x55063d80, struct.pack('<I', 1))
        u.mem_write(0x550643b8, struct.pack('<I', 1))

        def word(address):
            return struct.unpack('<I', u.mem_read(address, 4))[0]

        heap, alloc_fail = WIDGET, False
        free = []
        allocations = []
        stock_calls = []

        def platform(machine, address, _size, _arg):
            nonlocal heap
            r0 = machine.reg_read(arm.UC_ARM_REG_R0)
            if address in (0x536af2a8, 0x536af31c):
                allocations.append(r0)
                if alloc_fail and address == 0x536af2a8:
                    result = 0
                else:
                    result = heap
                    heap += (r0 + 7) & ~7
            elif address in (0x536af2e4, 0x536af358):
                free.append(r0)
                result = 0
            elif address == 0x5316cd28:
                stock_calls.append(address)
                u.mem_write(OWNER + 0x15c, struct.pack('<I', ROOT_WIDGET))
                result = 0
            elif address in (0x53179ba0, 0x53177724):
                stock_calls.append(address)
                result = 0
            else:
                return
            machine.reg_write(arm.UC_ARM_REG_R0, result)
            machine.reg_write(arm.UC_ARM_REG_PC, machine.reg_read(arm.UC_ARM_REG_LR))

        u.hook_add(UC_HOOK_CODE, platform)
        call(u, 0x53170884, stop=0x5317088c)
        self.assertEqual(allocations, [name['owner_bytes']])
        heap = WIDGET
        u.reg_write(arm.UC_ARM_REG_R3, 720)
        u.mem_write(SP, struct.pack('<I', 480))
        call(u, 0x5339199c, ROOT_WIDGET, 0, 0)  # original canvas constructor
        call(u, 0x53178390, OWNER, stop=0x53178394)
        widget = word(OWNER + name['owner_offset'])
        self.assertEqual(widget, WIDGET)
        self.assertEqual(word(widget), 0x53c09e80)  # actual label vtable
        self.assertEqual(word(widget + 4), ROOT_WIDGET)
        self.assertEqual(list(struct.unpack('<4I', u.mem_read(widget + 0x20, 16))), name['rect'])
        self.assertEqual(u.mem_read(widget + 0x9e, 1), b'\0')

        def refresh(code, mode=2, route=0x04000001, out_of_line=False):
            u.mem_write(OWNER + 0x124, struct.pack('<I', route))
            u.mem_write(OWNER + 0x306, struct.pack('<H', mode))
            external = ENTRY + 0x100 if out_of_line else 0
            if external:
                u.mem_write(external, struct.pack('<H', code))
            u.mem_write(ENTRY + 12, struct.pack('<H2xI', 0 if external else code, external))
            call(u, 0x535c24ec, 0, METADATA + 0x18c, ENTRY)
            call(u, 0x5317cb94, OWNER, stop=0x5317cb98)
            if u.mem_read(widget + 0x9e, 1) == b'\0':
                return None
            n = u.mem_read(widget + 0xed, 1)[0]
            return bytes(u.mem_read(word(widget + 0xf0), n * 2)).decode('utf-16-le').rstrip('\0')

        for code, caption in ((0x1021, '800T'), (0x1043, 'Harman Phoenix II'),
                              (0x10c, 'Unknown film'), (0x115, 'Unknown film'),
                              (0x2000, 'Unknown film'), (0xe0c5, 'Unknown film'),
                              (0x100, None), (0x10b, None), (0x116, None),
                              (0xe0c6, None), (0x1021, '800T')):
            self.assertEqual(refresh(code), caption, hex(code))
        self.assertIsNone(refresh(0x1021, mode=1))
        self.assertIsNone(refresh(0x1021, mode=0x102))
        self.assertIsNone(refresh(0x1021, route=0x04000002))
        self.assertEqual(refresh(0x1021, out_of_line=True), '800T')
        call(u, 0x53177a8c, OWNER, stop=0x53177a90)
        self.assertEqual(word(OWNER + name['owner_offset']), 0)
        self.assertIn(widget, free)
        self.assertEqual(stock_calls[0], 0x5316cd28)
        self.assertEqual(stock_calls[-1], 0x53177724)

        alloc_fail = True
        call(u, 0x53178390, OWNER, stop=0x53178394)
        self.assertEqual(word(OWNER + name['owner_offset']), 0)
        call(u, 0x5317cb94, OWNER, stop=0x5317cb98)
        call(u, 0x53177a8c, OWNER, stop=0x53177a90)
