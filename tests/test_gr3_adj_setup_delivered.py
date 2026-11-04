"""Exercise the installed Setup page and Grid Style in the same camera owner."""
import json
import os
from pathlib import Path
import struct
import unittest
import zlib

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm_const as arm

from scripts.probe_gr3_raw_guides_adj import ROM, call, decode, sha


class DeliveredAdjSetupTests(unittest.TestCase):
    def test_setup_route_and_commit_on_each_model(self):
        folders = [os.environ.get('M10V_CONTROLS_' + model.upper()) for model in ('gr3', 'gr3x')]
        if not all(folders):
            self.skipTest('set both final controls candidate directories')
        for model, folder in zip(('gr3', 'gr3x'), folders):
            with self.subTest(model=model):
                self.verify_setup(Path(folder), model)

    def verify_setup(self, folder, model):
        manifest = json.loads((folder / 'M10V-runtime-manifest.json').read_text())
        receipt = json.loads((folder / 'M10V-build-receipt.json').read_text())
        path = folder / receipt['filename']
        self.assertEqual(manifest['camera_model'], model)
        self.assertEqual(sha(path.read_bytes()), receipt['candidate_sha256'])
        rom = decode(path)
        at = manifest['base'] - ROM
        self.assertEqual(sha(rom[at:at + manifest['code_bytes']]), manifest['code_sha256'])
        u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        u.ctl_set_cpu_model(arm.UC_CPU_ARM_CORTEX_A9)
        u.mem_map(ROM, (len(rom) + 4095) & ~4095)
        u.mem_write(ROM, rom)
        u.mem_map(0x55000000, 0x100000)
        sym = manifest['symbols']
        owner, fs, event = 0x55010000, 0x55020000, 0x55030000
        route = 0x0200f107
        page = owner + 0x13bc + 0x6c0
        u.mem_write(0x55063910, struct.pack('<I', 1))
        u.mem_write(0x55063988, struct.pack('<I', owner))
        u.mem_write(fs + 8, struct.pack('<I', fs + 0x100))
        u.mem_write(fs + 0x100, struct.pack('<I', fs + 0x200))
        u.mem_write(fs + 0x220, b'\x01')
        u.mem_write(page + 0x158, struct.pack('<I', 0x55040000))
        u.mem_write(page + 0x158 + 56*4, struct.pack('<I', 53))
        records = {}
        writes = []
        captions = {}
        for i in range(53):
            u.mem_write(page + 0x158 + 4 * i, struct.pack('<I', 0x55040000 + 0x200 * i))

        def native(machine, address, _size, _arg):
            r0, r1, r2, r3 = [machine.reg_read(reg) for reg in (
                arm.UC_ARM_REG_R0, arm.UC_ARM_REG_R1, arm.UC_ARM_REG_R2, arm.UC_ARM_REG_R3)]
            if address == manifest['settings_menu']['exports']['m10v_settings_factory_original']:
                self.assertEqual(r1, 0x0200004a)
                result = owner
            elif address == 0x53828014:
                result = fs
            elif address in (0x53825648, 0x53825fa8):
                name = bytes(machine.mem_read(r1, 12)).split(b'\0')[0]
                self.assertEqual(r2, 20)
                result = 0
                if address == 0x53825648 and name in records:
                    machine.mem_write(r3, records[name])
                    result = 1
                elif address == 0x53825fa8:
                    data = bytes(machine.mem_read(r3, r2))
                    records[name] = data
                    writes.append(data)
                    result = 1
            elif address == sym.get('m10v_debug_log'):
                # This setup fixture models 20-byte settings journals. The
                # diagnostic ring has its own final guide and logger fixtures.
                result = 0
            elif address == 0x53396f80:
                captions[r0] = r1
                result = 0
            elif address in (0x5316ca28, 0x533ad3c0, 0x53393e00, 0x5339658c,
                             0x5320ad88, 0x5320b67c):
                result = 0
            else:
                return
            machine.reg_write(arm.UC_ARM_REG_R0, result)
            machine.reg_write(arm.UC_ARM_REG_PC, machine.reg_read(arm.UC_ARM_REG_LR))
        u.hook_add(UC_HOOK_CODE, native)
        call(u, sym['m10v_adj_extra_camera_init'], owner)
        call(u, sym['m10v_guides_camera_init'], owner)
        self.assertEqual(call(u, sym['m10v_hdf_menu_factory'], 0, route), page)
        self.assertEqual(call(u, sym['m10v_settings_controller_ready'], page, route), 1)
        def press(key):
            u.mem_write(event, struct.pack('<H', key))
            self.assertEqual(call(u, sym['m10v_settings_controller_key'], page, event), 1)

        native_ids = rom[0xb4eba0:0xb4eba0 + 19]
        value_widget = 0x55040000 + 0x200 * 48
        for function in native_ids[1:]:
            press(0xcf)
            self.assertEqual(captions[value_widget], call(u, 0x53292810, 0, function))
        self.assertEqual(writes, [], 'browsing the native list writes to the card')
        press(0xcf)  # Guides immediately after the original choices.
        press(0xd8)
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0][12:16], b'\x18\x00\x00\x00')
        self.assertEqual(struct.unpack_from('<I', writes[0], 16)[0], zlib.crc32(writes[0][:16]))
        self.assertEqual(call(u, sym['m10v_settings_controller_ready'], page, route), 1)
        u.mem_write(event, struct.pack('<H', 0xd8))
        self.assertEqual(call(u, sym['m10v_settings_controller_key'], page, event), 1)
        self.assertEqual(len(writes), 1, 'committing an unchanged value rewrites the card')

        apply_guide, = struct.unpack('<I', u.mem_read(0x53b3dcd8, 4))
        self.assertEqual(apply_guide, sym['m10v_guides_camera_apply'])
        self.assertEqual(call(u, apply_guide, page, 2), 1)
        self.assertEqual(call(u, sym['m10v_guides_camera_mode']), 1)
        self.assertEqual(set(records), {b'M10VAD0.BIN', b'M10VGD1.BIN'})
        self.assertEqual(records[b'M10VAD0.BIN'][12:16], b'\x18\x00\x00\x00')
        self.assertEqual(records[b'M10VGD1.BIN'][12:16], b'\x01\x00\x00\x00')
        self.assertEqual(call(u, sym['m10v_adj_extra_camera_load'], event), 1)
        self.assertEqual(u.mem_read(event, 4), b'\x18\x00\x00\x00')
        self.assertEqual(call(u, sym['m10v_menu_recorded_icon'], 0x20f21), 703)
        self.assertEqual(call(u, sym['m10v_menu_recorded_icon'], 0x20f43), 737)

        press(0xd1)  # Slot 7 starts empty. Select and save the first stock function.
        press(0xcf)
        press(0xd8)
        self.assertEqual(writes[-1][12:16], b'\x18\x01\x00\x00')
        press(0xcf)
        press(0x86)  # Cancel the next native option.
        self.assertEqual(len(writes), 3, 'cancel must keep the previous ADJ journal')
        self.assertEqual(call(u, sym['m10v_adj_extra_camera_load'], event), 1)
        self.assertEqual(u.mem_read(event, 4), b'\x18\x01\x00\x00')

        press(0xd1)  # Slot 8 is off. One step left wraps to Border.
        press(0xce)
        self.assertEqual(captions[value_widget + 0x400], 1155)
        press(0xd8)
        self.assertEqual(writes[-1][12:16], b'\x18\x01\x1c\x00')
        self.assertEqual(call(u, sym['m10v_hdf_menu_factory'], 0, 0x0200f108),
                         owner + manifest['hdf_menu']['owner_offset'])
