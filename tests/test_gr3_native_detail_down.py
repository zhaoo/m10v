"""Run Fn Image Control's native list construction and Down-key redraw."""
import json
import os
from pathlib import Path
import struct
import unittest
import zlib

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm_const as arm

from scripts.probe_gr3_raw_guides_adj import RAM, ROM, call, decode, sha


class NativeDetailDown(unittest.TestCase):
    def test_down_redraws_agfa_vista_200(self):
        for model in ('gr3', 'gr3x'):
            with self.subTest(model=model):
                folder = os.environ.get('M10V_DETAIL_' + model.upper())
                if not folder:
                    self.skipTest('set final M10V_DETAIL_GR3 and M10V_DETAIL_GR3X candidate directories')
                self.verify_down(Path(folder), model)

    def verify_down(self, folder, model):
        manifest = json.loads((folder / 'M10V-runtime-manifest.json').read_text())
        receipt = json.loads((folder / 'M10V-build-receipt.json').read_text())
        path = folder / receipt['filename']
        self.assertEqual(manifest['camera_model'], model)
        self.assertEqual(sha(path.read_bytes()), receipt['candidate_sha256'])
        rom = decode(path)
        at = manifest['base'] - ROM
        self.assertEqual(sha(rom[at:at + manifest['code_bytes']]), manifest['code_sha256'])
        self.assertTrue(manifest['experimental_capture']['full_isp_effects'])

        u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        u.ctl_set_cpu_model(arm.UC_CPU_ARM_CORTEX_A15)
        u.reg_write(arm.UC_ARM_REG_C1_C0_2, 0xf00000)
        u.reg_write(arm.UC_ARM_REG_FPEXC, 0x40000000)
        u.mem_map(ROM, (len(rom) + 4095) & ~4095)
        u.mem_write(ROM, rom)
        u.mem_map(RAM, 0x100000)
        u.mem_map(0x5536d000, 0x1000)
        u.mem_write(0x5536d078, struct.pack('<2I', 0x53d624d8, 1))
        heap = RAM + 0x20000
        controller = RAM + 0x4000
        addresses = set()
        # Agfa Vista 200, grain level 1, halo gain/spread/threshold 3/4/5.
        state = bytearray.fromhex(manifest['initial_state_hex'])
        installed = [struct.unpack_from('<H6B', state, 12 + i*8) for i in range(10)]
        self.assertIn((33, 0, 0, 7, 7, 5, 4), installed)
        self.assertTrue(all(slot[1:4] == (0, 0, 0) for slot in installed if slot[0] not in (0, 33)))
        struct.pack_into('<H6B', state, 12, 326, 1, 0, 3, 4, 5, 2)
        struct.pack_into('<8B', state, 96, 0, 2, 4, 2, 0x83, 0, 0, 0)
        state[-4:] = struct.pack('<I', zlib.crc32(state[:-4]))

        def platform(cpu, address, _size, _data):
            nonlocal heap
            addresses.add(address)
            r0 = cpu.reg_read(arm.UC_ARM_REG_R0)
            if address in (0x536af2a8, 0x536af31c):
                result = heap
                heap += (r0 + 7) & ~7
            elif address in (0x536af2e4, 0x536af358, 0x533ad308):
                result = 0
            elif address == manifest['symbols']['m10v_camera_library_load']:
                cpu.mem_write(r0, bytes(state))
                result = 0
            else:
                return
            cpu.reg_write(arm.UC_ARM_REG_R0, result)
            cpu.reg_write(arm.UC_ARM_REG_PC, cpu.reg_read(arm.UC_ARM_REG_LR))

        u.hook_add(UC_HOOK_CODE, platform)
        vtable, = struct.unpack('<I', u.mem_read(0x531afe44, 4))
        u.mem_write(controller, struct.pack('<I', vtable))
        u.mem_write(controller + 0x198, bytes((25, 0, 0)))
        # Native Fn detail descriptor, type 13, and stock callback registration.
        native_list = call(u, 0x533ad7f0, 0x53b3bb50)
        u.mem_write(controller + 0x194, struct.pack('<I', native_list))
        # Appended M10V slots have the Standard carrier's stock kind.
        kind = call(u, 0x531aca98, controller, 11)
        u.mem_write(controller + 0x19a, bytes((kind,)))
        call(u, 0x531afbe0, controller)

        # Navigate from the first private halo row. The stock callback redraws
        # all rows including Grain, where the old type confusion corrupted
        # LabelView's UTF-16 pointer on the initial render.
        count = call(u, 0x531afab8, controller, 0, kind)
        private_fields = manifest['detail']['variant_ids']['common']
        first_private = count - len(private_fields)
        first_halo = first_private + private_fields.index(18)
        u.mem_write(native_list + 0x110, struct.pack('<H', first_halo))
        call(u, 0x531aff84, controller)
        addresses.clear()
        event_method, = struct.unpack('<I', u.mem_read(vtable + 0x28, 4))
        event = controller + 0x200
        u.mem_write(event, struct.pack('<H', 0xd1))  # Physical Down key.
        call(u, event_method, controller, event, stop=0x531b07d8)
        self.assertIn(0x531b08f4, addresses)
        self.assertIn(0x53394db4, addresses)
        self.assertIn(0x531b0834, addresses)
        self.assertIn(0x53390ef8, addresses)
        self.assertNotIn(0x53396f80, addresses)
        self.assertEqual(call(u, 0x53394820, native_list), first_halo + 1)

        for field, value in ((18, '3'), (19, '4'), (20, '5'), (21, '1'),
                             (23, '2'), (24, 'Rnd'), (25, '2'), (26, '3')):
            row = call(u, 0x53394758, native_list, first_private + private_fields.index(field))
            label, = struct.unpack('<I', u.mem_read(row + 0xf4, 4))
            pointer, = struct.unpack('<I', u.mem_read(label + 0xf0, 4))
            expected = (value + '\0').encode('utf-16le')
            self.assertEqual(u.mem_read(pointer, len(expected)), expected)

        direction_row = first_private + private_fields.index(24)
        control = manifest['symbols']['m10v_detail_control']
        addresses.clear()
        call(u, control, 8, controller, (24 << 16) | direction_row)
        self.assertNotIn(0x533ab548, addresses,
                         'the leak direction row already has the correct native bounds')
        for direction, name in enumerate(('L', 'U', 'R', 'D', 'Rnd')):
            state[98] = direction
            state[-4:] = struct.pack('<I', zlib.crc32(state[:-4]))
            self.assertEqual(call(u, control, 3, controller, (6 << 16) | direction_row), 1)
            row = call(u, 0x53394758, native_list, direction_row)
            label, = struct.unpack('<I', u.mem_read(row + 0xf4, 4))
            pointer, = struct.unpack('<I', u.mem_read(label + 0xf0, 4))
            expected = (name + '\0').encode('utf-16le')
            self.assertEqual(u.mem_read(pointer, len(expected)), expected)
