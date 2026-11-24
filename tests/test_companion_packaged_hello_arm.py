"""Execute the actual delivery ELF through discovery and first HELLO publication.

Set M10V_TEST_SERVICE_ELF to the extracted, shipped executable. Kernel syscalls
and physical pages are fixtures. Production ARM instructions, pointers, mapping
permissions and request CRC execute unchanged. This cannot verify camera caches.
"""
import os
from pathlib import Path
import re
import struct
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]


def words(*values):
    return struct.pack('<' + 'I' * len(values), *values)


class PackagedHelloArmTests(unittest.TestCase):
    def test_exact_elf_readonly_discovery_clock_and_bounded_publication(self):
        path = os.environ.get('M10V_TEST_SERVICE_ELF')
        if not path:
            self.skipTest('requires the exact extracted delivery ELF')
        from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_INTR
        from unicorn.arm_const import (
            UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
            UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R7, UC_ARM_REG_SP,
            UC_ARM_REG_LR, UC_ARM_REG_PC,
        )
        binary = Path(path).read_bytes()
        self.assertEqual(binary[:7], b'\x7fELF\x01\x01\x01')
        emulator = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        emulator.mem_map(0x10000, 0x100000)
        emulator.mem_map(0x10000000, 0x20000)
        emulator.mem_map(0x20000000, 0x4000)
        offset = struct.unpack_from('<I', binary, 28)[0]
        size, count = struct.unpack_from('<HH', binary, 42)
        for index in range(count):
            segment = struct.unpack_from('<8I', binary, offset + index * size)
            if segment[0] == 1:
                emulator.mem_write(segment[2], binary[segment[1]:segment[1] + segment[4]])
        offset = struct.unpack_from('<I', binary, 32)[0]
        size, count = struct.unpack_from('<HH', binary, 46)
        sections = [struct.unpack_from('<10I', binary, offset + index * size)
                    for index in range(count)]
        symbols = {}
        for section in sections:
            if section[1] != 2:
                continue
            table = sections[section[6]]
            names = binary[table[4]:table[4] + table[5]]
            for position in range(section[4], section[4] + section[5], 16):
                name, value, _, _, _, defined = struct.unpack_from('<IIIBBH', binary, position)
                if defined:
                    symbols[names[name:].split(b'\0', 1)[0].decode()] = value
        # Main seeds this field from /dev/urandom before invoking the adapter.
        emulator.mem_write(symbols['target_config'] + 96, bytes(range(1, 17)))
        config = bytes(emulator.mem_read(symbols['target_config'], 180))
        owner, context = 0x56000000, 0x56010000
        wire = context + 128
        physical = {}

        def put(address, data):
            for index, value in enumerate(data):
                physical[address + index] = value

        header = (ROOT / 'native/companion/resident_bridge.h').read_text()
        magic = int(re.search(r'M10V_RESIDENT_MAGIC\s+(0x[0-9a-fA-F]+)', header)[1], 16)
        put(0x55063910, words(1))
        put(0x55063988, words(owner))
        put(owner + 0x6400, words(0x3244494d, 2, 64, context, wire, 2432, context) + bytes(36))
        put(wire, words(magic, 2, 2432, 1, owner, context) + config[:32] + bytes(72))
        for index, address in enumerate((0x5316fcf8, 0x5319667c, 0x5383c834, 0x5383c870)):
            put(address, config[112 + index * 16:128 + index * 16])
        calls, logs, mappings = [], [], {}
        log_descriptors = {}
        registers = (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
                     UC_ARM_REG_R3, UC_ARM_REG_R4, UC_ARM_REG_R5)

        def syscall(machine, interrupt, unused):
            args = [machine.reg_read(register) for register in registers]
            number = machine.reg_read(UC_ARM_REG_R7)
            calls.append((number, args))
            if number == 5:
                result = 10 + sum(item[0] == 5 for item in calls)
                path = bytes(machine.mem_read(args[0], 128)).split(b'\0', 1)[0].decode()
                if path in ('/tmp/m10v-worker-1101.log', '/media/storage1/M10V/R16WORK.TXT', '/media/storage1/M10V/R17WORK.TXT', '/media/storage1/M10V/R18WORK.TXT', '/media/storage1/M10V/R19WORK.TXT'):
                    self.assertEqual(args[1], 0x441 if path.startswith('/tmp/') else 0x101441)
                    log_descriptors[result] = path
                else:
                    self.assertEqual(path, '/dev/mem')
            elif number == 192:
                self.assertFalse(mappings, 'previous physical mapping was released')
                result = 0x20000000
                address = args[5] << 12
                mappings[result] = address, args[1], args[2]
                self.assertEqual(args[3], 1, 'MAP_SHARED')
                self.assertIn(args[2], (1, 3))
                machine.mem_write(result, bytes(physical.get(address + index, 0)
                                                for index in range(args[1])))
            elif number == 91:
                address, length, protection = mappings.pop(args[0])
                self.assertEqual(length, args[1])
                if protection == 3:
                    put(address, bytes(machine.mem_read(args[0], length)))
                result = 0
            elif number == 263:
                self.assertEqual(args[0], 1, 'CLOCK_MONOTONIC')
                machine.mem_write(args[1], words(7, 123000000))
                result = 0
            elif number == 4:
                if args[0] == 1:
                    logs.append(bytes(machine.mem_read(args[1], args[2])).decode())
                else:
                    self.assertIn(args[0], log_descriptors)
                result = args[2]
            elif number == 6:
                log_descriptors.pop(args[0], None)
                result = 0
            else:
                self.fail(f'unexpected syscall {number} with {args}')
            machine.reg_write(UC_ARM_REG_R0, result)

        emulator.hook_add(UC_HOOK_INTR, syscall)

        def run(function, *args):
            emulator.reg_write(UC_ARM_REG_SP, 0x10010000)
            emulator.reg_write(UC_ARM_REG_LR, 0x10000)
            for register, value in zip(registers, args):
                emulator.reg_write(register, value)
            emulator.emu_start(symbols[function], 0x10000, count=1000000)
            self.assertEqual(emulator.reg_read(UC_ARM_REG_PC), 0x10000)
            return emulator.reg_read(UC_ARM_REG_R0)

        self.assertEqual(run('m10v_linux_devmem_open', symbols['memory'],
                             symbols['transport'], symbols['m10v_linux_now_ms']), 1)
        self.assertEqual(run('m10v_linux_target_init', symbols['target'],
                             symbols['target_config'], symbols['transport']), 0)
        self.assertTrue(all(args[2] == 1 for number, args in calls if number == 192))
        self.assertEqual(run('m10v_linux_target_hello', symbols['target']), 6)
        writes = [args for number, args in calls if number == 192 and args[2] == 3]
        self.assertEqual(len(writes), 3)
        request = wire + 128
        self.assertTrue(all(args[5] == request >> 12 and args[1] == 4096 for args in writes))
        self.assertEqual([number for number, _ in calls].count(263), 1)
        if 'm10v_linux_diagnostics_start' in symbols:
            self.assertIn('OWNER_REQUEST_BEGIN 00000001 00000002\n', logs)
        else:
            self.assertEqual(logs, [], 'formal HELLO must perform no diagnostic writes')
        request_bytes = bytes(physical.get(request + index, 0) for index in range(1152))
        sequence, command, length = struct.unpack_from('<III', request_bytes)
        self.assertEqual((sequence, command, length), (2, 1, 16))
        self.assertEqual(request_bytes[128:144], config[96:112])
        expected_crc = zlib.crc32(request_bytes[:12] + request_bytes[16:24] + request_bytes[128:144])
        self.assertEqual(struct.unpack_from('<I', request_bytes, 12)[0], expected_crc)
        self.assertEqual(struct.unpack_from('<Q', emulator.mem_read(symbols['target'] + 232, 8))[0], 7123)
        self.assertFalse(mappings)


if __name__ == '__main__':
    unittest.main()
