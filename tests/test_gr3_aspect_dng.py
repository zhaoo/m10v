"""Execute the new DNG tag adapter and frozen legacy handler in ARM emulation."""
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_PROT_EXEC, UC_PROT_READ
from unicorn import UC_HOOK_CODE
from unicorn import arm_const as A

from scripts.build_gr3_save_trace import FLAGS, sections

ROOT = Path(__file__).resolve().parents[1]
BASE, LEGACY = 0x54150000, 0x540b7308
RAM, STOP = 0x55000000, 0x550ff000
IMAGE, PROPS, GEOMETRY, OUT = RAM, RAM + 0x1000, RAM + 0x80000, RAM + 0x81000


class AspectDngTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        template = json.loads((ROOT / '.runtime/grlife-current/reconstruction/firmware_store/templates/urban160-native.json').read_text())
        cls.old_base = template['base_va']
        cls.old_code = bytes.fromhex(template['program_hex'])
        clang = os.environ.get('M10V_LLVM_CLANG') or '/opt/homebrew/opt/llvm/bin/clang'
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            obj, elf, ld = p / 'dng.o', p / 'dng.elf', p / 'dng.ld'
            ld.write_text('SECTIONS { . = ' + hex(BASE) + '; .text : { *(.text*) *(.rodata*) } /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) } }')
            subprocess.run([clang, *FLAGS, '-c', str(ROOT / 'native/gr3/m10v_aspect_dng.c'), '-o', str(obj)], check=True, capture_output=True)
            subprocess.run([shutil.which('ld.lld') or 'ld.lld', '-m', 'armelf', '-T', str(ld), str(obj), '-o', str(elf)], check=True, capture_output=True)
            data = elf.read_bytes()
            rows = sections(data)
            for name, row in rows:
                if name == '.text':
                    cls.code = data[row[4]:row[4] + row[5]]
                if row[1] == 2:
                    sr = rows[row[6]][1]
                    strings = data[sr[4]:sr[4] + sr[5]]
                    for pos in range(row[4], row[4] + row[5], 16):
                        n, value, _, _, _, _ = struct.unpack_from('<IIIBBH', data, pos)
                        if strings[n:].split(b'\0')[0] == b'm10v_aspect_dng_tags':
                            cls.entry = value
        from scripts.gr3_aspect_overlay import build_module, MODULE
        cls.overlay_base = MODULE
        cls.overlay_code, cls.overlay_entries = build_module()

    def machine(self, raw=5, width=6000, height=4000, origin=(0, 0), sensor=None):
        u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        for address, code in [(self.old_base, self.old_code), (BASE, self.code)]:
            u.mem_map(address, (len(code) + 4095) & ~4095)
            u.mem_write(address, code)
            u.mem_protect(address, (len(code) + 4095) & ~4095, UC_PROT_READ | UC_PROT_EXEC)
        u.mem_map(RAM, 0x100000)
        self.w32(u, IMAGE + 0x7c, GEOMETRY)
        self.w32(u, IMAGE + 0x84, PROPS)
        u.mem_write(PROPS + 0x719fe, bytes([raw]))
        sensor = sensor or (width + origin[0], height + origin[1])
        # Distinguish sensor origin from crop-relative coordinates.
        for offset, value in [(8, 18), (12, 12), (0x10, sensor[0]), (0x14, sensor[1]),
                              (0x18, 18 + origin[0]), (0x1c, 12 + origin[1]),
                              (0x20, width), (0x24, height)]:
            self.w32(u, GEOMETRY + offset, value)
        u.mem_write(OUT - 4, b'\xa5' * 28)
        return u

    def overlay_machine(self):
        u = self.machine()
        u.mem_map(self.overlay_base, (len(self.overlay_code) + 4095) & ~4095)
        u.mem_write(self.overlay_base, self.overlay_code)
        return u

    @staticmethod
    def w32(u, address, value):
        u.mem_write(address, struct.pack('<I', value))

    def call(self, u, entry=None, image=IMAGE, out=OUT):
        u.reg_write(A.UC_ARM_REG_SP, RAM + 0xf0000)
        u.reg_write(A.UC_ARM_REG_LR, STOP)
        u.reg_write(A.UC_ARM_REG_R0, image)
        u.reg_write(A.UC_ARM_REG_R1, out)
        u.emu_start(entry or self.entry, STOP, count=100000)
        result = u.reg_read(A.UC_ARM_REG_R0)
        return result - 0x100000000 if result & 0x80000000 else result

    def test_full_and_already_cropped_geometry_for_every_size(self):
        for index, (full_w, h, crop_w) in enumerate([(6000, 4000, 4672), (4800, 3200, 3728),
                                                   (3360, 2240, 2608), (1920, 1280, 1488)]):
            for width in [full_w, crop_w]:
                with self.subTest(size=index, width=width):
                    u = self.machine(width=width, height=h, origin=(20, 14))
                    self.assertEqual(self.call(u), 1)
                    x = 20 + ((full_w - crop_w) // 2 if width == full_w else 0)
                    self.assertEqual(bytes(u.mem_read(OUT, 20)), struct.pack('<4I4B', x, 14, crop_w, h, 5, index, 1, 0))
                    self.assertEqual(bytes(u.mem_read(OUT - 4, 4)), b'\xa5' * 4)
                    self.assertEqual(bytes(u.mem_read(OUT + 20, 4)), b'\xa5' * 4)

    def test_custom_already_cropped_geometry_is_immutable_and_recognized(self):
        for mm in (29,41,70,100):
            w=(4672*28//mm)//16*16
            h=(4000*28//mm)//16*16
            u=self.machine(width=w,height=h,origin=(20,14))
            self.assertEqual(self.call(u),1)
            self.assertEqual(struct.unpack('<4I',u.mem_read(OUT,16)),(20,14,w,h))

    def test_unknown_size_keeps_original_crop_and_returns_unrecognized(self):
        u = self.machine(width=1000, height=700, origin=(2, 4))
        self.assertEqual(self.call(u), 0)
        self.assertEqual(bytes(u.mem_read(OUT, 20)), struct.pack('<4I4B', 2, 4, 1000, 700, 5, 255, 0, 0))

    def test_legacy_identities_are_byte_exact(self):
        for raw in [0, 1, 2, 3, 4, 255]:
            for width, height in [(6000, 4000), (5328, 4000), (6000, 2208), (1000, 700)]:
                with self.subTest(raw=raw, size=(width, height)):
                    old = self.machine(raw=raw, width=width, height=height)
                    new = self.machine(raw=raw, width=width, height=height)
                    self.assertEqual(self.call(new), self.call(old, LEGACY))
                    self.assertEqual(bytes(new.mem_read(OUT, 20)), bytes(old.mem_read(OUT, 20)))

    def test_invalid_descriptors_leave_output_untouched(self):
        edits = [(IMAGE + 0x7c, 0), (GEOMETRY + 0x10, 0), (GEOMETRY + 0x14, 0),
                 (GEOMETRY + 0x20, 0), (GEOMETRY + 0x24, 0),
                 (GEOMETRY + 0x18, 17), (GEOMETRY + 0x1c, 11),
                 (GEOMETRY + 0x18, 6019), (GEOMETRY + 0x1c, 4013),
                 (GEOMETRY + 0x20, 6001), (GEOMETRY + 0x24, 4001)]
        for address, value in edits:
            with self.subTest(address=hex(address), value=value):
                u = self.machine()
                self.w32(u, address, value)
                self.assertEqual(self.call(u), -1)
                self.assertEqual(bytes(u.mem_read(OUT, 20)), b'\xa5' * 20)
        for image, out in [(0, OUT), (IMAGE, 0)]:
            self.assertEqual(self.call(self.machine(), image=image, out=out), -1)

    def test_makernote_write_preserves_private_identity(self):
        u = self.overlay_machine()
        props = RAM + 0x100
        self.w32(u, IMAGE + 0x20, props)
        u.mem_write(props + 0xf2, b'\x05')
        u.mem_map(0x535d0000, 0x1000)
        observed = []

        def writer(machine, address, size, user):
            if address == 0x535d02b4:
                observed.append(tuple(machine.reg_read(r) for r in [A.UC_ARM_REG_R0, A.UC_ARM_REG_R1, A.UC_ARM_REG_R2]))
                machine.reg_write(A.UC_ARM_REG_R0, 1)
                machine.reg_write(A.UC_ARM_REG_PC, machine.reg_read(A.UC_ARM_REG_LR))

        u.hook_add(UC_HOOK_CODE, writer)
        self.assertEqual(self.call(u, self.overlay_entries['m10v_aspect_write']), 1)
        self.assertEqual(observed, [(OUT, 0, 5)])

    def test_makernote_read_and_binary_class_retain_identity(self):
        for raw in [4, 5, 6]:
            with self.subTest(raw=raw):
                u = self.overlay_machine()
                target = RAM + 0x82000
                self.w32(u, IMAGE + 12, target)
                u.mem_map(0x535d0000, 0x1000)

                def reader(machine, address, size, user):
                    if address == 0x535d04bc:
                        machine.reg_write(A.UC_ARM_REG_R0, raw)
                        machine.reg_write(A.UC_ARM_REG_PC, machine.reg_read(A.UC_ARM_REG_LR))

                u.hook_add(UC_HOOK_CODE, reader)
                self.call(u, self.overlay_entries['m10v_aspect_extract'])
                self.assertEqual(bytes(u.mem_read(target + 0x7b6, 1)), bytes([raw]))
        for raw in (5,6):
            u = self.overlay_machine()
            self.assertEqual(self.call(u, self.overlay_entries['m10v_aspect_binary_class'], image=raw), 0)

    def test_active_geometry_is_written_before_one_notification_even_on_zero(self):
        fixtures = [(0x2000, (2296381, 1966080, 326369, 0)),
                    (0x2800, (1832387, 1572864, 558367, 196608)),
                    (0x38f6, (1281884, 1101005, 833618, 432538))]
        for mag, geometry in fixtures:
            for notified in [0, 1, 0x12345678]:
                with self.subTest(mag=hex(mag), notified=notified):
                    u = self.overlay_machine()
                    u.mem_map(0x53665000, 0x1000)
                    u.mem_map(0x536ae000, 0x1000)
                    u.mem_write(IMAGE + 0x64, b'\xa5' * 16)
                    calls = []

                    def native(machine, address, size, user):
                        if address not in [0x53665c2c, 0x536ae870]:
                            return
                        calls.append(address)
                        if address == 0x53665c2c:
                            self.assertEqual(machine.reg_read(A.UC_ARM_REG_R0), IMAGE)
                            self.assertEqual(bytes(machine.mem_read(IMAGE + 0x64, 16)), b'\xa5' * 16)
                        else:
                            self.assertEqual(machine.reg_read(A.UC_ARM_REG_R0), IMAGE + 0x24bc)
                            self.assertEqual(struct.unpack('<4I', machine.mem_read(IMAGE + 0x64, 16)), geometry)
                        machine.reg_write(A.UC_ARM_REG_R0, notified if address == 0x536ae870 else 0)
                        machine.reg_write(A.UC_ARM_REG_PC, machine.reg_read(A.UC_ARM_REG_LR))

                    u.hook_add(UC_HOOK_CODE, native)
                    u.reg_write(A.UC_ARM_REG_R2, mag)
                    result = self.call(u, self.overlay_entries['m10v_aspect_write_active'])
                    self.assertEqual(result, notified)
                    self.assertEqual(calls, [0x53665c2c, 0x536ae870])
                    self.assertEqual(struct.unpack('<4I', u.mem_read(IMAGE + 0x64, 16)), geometry)

    def test_filter_matches_quantized_photo_diagonal(self):
        for mag, crop_enabled, expected in [(0x3f800000, 0, 0x3f5a583c),
                                           (0x3fa00000, 0, 0x3f2e6ac0),
                                           (0x3fe3d70a, 0, 0x3ef418fc),
                                           (0x3fe49249, 0, 0x3ef418fc),
                                           (0x3fe49249, 1, 0x3f5a583c)]:
            with self.subTest(mag=hex(mag), crop_enabled=crop_enabled):
                u = self.overlay_machine()
                self.assertEqual(self.call(u, self.overlay_entries['m10v_aspect_filter'], image=mag, out=crop_enabled), expected)

    def test_merge_restores_extended_identities_after_native_copy(self):
        for raw in [0, 1, 2, 3, 4, 5, 6, 255]:
            with self.subTest(raw=raw):
                u = self.overlay_machine()
                u.mem_write(OUT + 0x4c2, bytes([raw]))
                calls = []

                def native(machine, address, size, user):
                    if address == 0x540b9498:
                        calls.append(address)
                        self.assertEqual(machine.reg_read(A.UC_ARM_REG_R1), OUT)
                        machine.mem_write(OUT + 0x4c2, b'\0')
                        machine.reg_write(A.UC_ARM_REG_R0, 0x55)
                        machine.reg_write(A.UC_ARM_REG_PC, machine.reg_read(A.UC_ARM_REG_LR))

                u.hook_add(UC_HOOK_CODE, native)
                self.assertEqual(self.call(u, self.overlay_entries['m10v_aspect_merge']), 0x55)
                self.assertEqual(bytes(u.mem_read(OUT + 0x4c2, 1)), bytes([raw if raw in [1, 4, 5, 6] else 0]))
                self.assertEqual(calls, [0x540b9498])

    def test_ubox_restores_extended_identities_only_for_slots_one_to_six(self):
        for slot in [0, 1, 2, 3, 4, 5, 6, 7, 255]:
            for raw in [0, 1, 2, 3, 4, 5, 6, 255]:
                with self.subTest(slot=slot, raw=raw):
                    u = self.overlay_machine()
                    source, target = RAM + 0x83000, RAM + 0x84000
                    self.w32(u, IMAGE + 4, source)
                    self.w32(u, IMAGE + 8 + slot * 4, target)
                    u.mem_write(source + 0x4c2, bytes([raw]))
                    u.mem_write(target + 0x4c2, b'\xa5')
                    calls = []

                    def native(machine, address, size, user):
                        if address == 0x540b9248:
                            calls.append(address)
                            self.assertEqual(machine.reg_read(A.UC_ARM_REG_R1), slot)
                            machine.mem_write(target + 0x4c2, b'\0')
                            machine.reg_write(A.UC_ARM_REG_R0, 0x66)
                            machine.reg_write(A.UC_ARM_REG_PC, machine.reg_read(A.UC_ARM_REG_LR))

                    u.hook_add(UC_HOOK_CODE, native)
                    self.assertEqual(self.call(u, self.overlay_entries['m10v_aspect_ubox'], out=slot), 0x66)
                    expected = raw if 1 <= slot <= 6 and raw in [1, 4, 5, 6] else 0
                    self.assertEqual(bytes(u.mem_read(target + 0x4c2, 1)), bytes([expected]))
                    self.assertEqual(bytes(u.mem_read(source + 0x4c2, 1)), bytes([raw]))
                    self.assertEqual(calls, [0x540b9248])


if __name__ == '__main__':
    unittest.main()
