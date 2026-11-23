"""Execute the delivery service's direct process lifetime, network startup and independent fault log.

The Linux kernel calls and native replies are fixtures. All worker, network,
CRC and signal-handler instructions come from M10V_TEST_SERVICE_ELF.
"""
import os
from pathlib import Path
import struct
import unittest
import zlib

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_INTR
from unicorn.arm_const import (
    UC_CPU_ARM_CORTEX_A9, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
    UC_ARM_REG_R3, UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R7,
    UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC,
)

REGISTERS = (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
             UC_ARM_REG_R3, UC_ARM_REG_R4, UC_ARM_REG_R5)


def words(*values):
    return struct.pack('<' + 'I' * len(values), *values)


class WorkerArmTests(unittest.TestCase):
    def setUp(self):
        path = os.environ.get('M10V_TEST_SERVICE_ELF')
        if not path:
            self.skipTest('requires the actual compiled delivery service')
        binary = Path(path).read_bytes()
        self.machine = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        self.machine.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_A9)
        self.machine.mem_map(0x10000, 0x100000)
        self.machine.mem_map(0x10000000, 0x20000)
        self.machine.mem_map(0x20000000, 0x4000)
        self.machine.mem_map(0x21000000, 0x400000)
        offset = struct.unpack_from('<I', binary, 28)[0]
        size, count = struct.unpack_from('<HH', binary, 42)
        for index in range(count):
            segment = struct.unpack_from('<8I', binary, offset + index * size)
            if segment[0] == 1:
                self.machine.mem_write(segment[2], binary[segment[1]:segment[1] + segment[4]])
        offset = struct.unpack_from('<I', binary, 32)[0]
        size, count = struct.unpack_from('<HH', binary, 46)
        sections = [struct.unpack_from('<10I', binary, offset + index * size)
                    for index in range(count)]
        self.symbols = {}
        for section in sections:
            if section[1] != 2:
                continue
            strings = sections[section[6]]
            names = binary[strings[4]:strings[4] + strings[5]]
            for position in range(section[4], section[4] + section[5], 16):
                name, value, _, _, _, defined = struct.unpack_from('<IIIBBH', binary, position)
                if defined:
                    self.symbols[names[name:].split(b'\0', 1)[0].decode()] = value
        self.calls, self.logs, self.actions = [], [], {}
        self.open_paths = []
        self.open_files, self.pending_files, self.published_files = {}, {}, {}
        self.stdout_error = False
        self.exit_code = None
        self.handling_sigpipe = False
        self.clock = 7000
        self.physical, self.mappings, self.commands = {}, {}, []
        self.wire = 0x56010080
        self.replied = 0
        self.live_offer_failure = False
        self.run_until_heartbeat = False
        self.wifi_up = False
        self.socket_failure = False
        self.ioctl_failure = False
        self.stop_on_listen = False
        self.machine.hook_add(UC_HOOK_INTR, self.syscall)

    def text(self, address):
        return bytes(self.machine.mem_read(address, 256)).split(b'\0', 1)[0].decode()

    def put(self, address, data):
        for index, value in enumerate(data):
            self.physical[address + index] = value

    def physical_bytes(self, address, size):
        return bytes(self.physical.get(address + index, 0) for index in range(size))

    def respond(self):
        request = self.wire + 128
        sequence, command, size, crc, _, _ = struct.unpack('<6I', self.physical_bytes(request, 24))
        if not sequence or sequence & 1 or sequence == self.replied:
            return
        self.replied = sequence
        self.commands.append(command)
        reply_code = 0
        if command == 1:
            payload = self.physical_bytes(request + 128, size) + self.config[:32]
        elif command == 11 and self.live_offer_failure:
            payload, reply_code = b'', 10
        elif command == 11:
            arena, context = 0x56200000, 0x56010000
            self.put(arena, words(0x31494c4d, 1, 111232, context, 0) + bytes(108))
            payload = words(1, arena, 111232, context, 3, 36992, 36864, 1)
        elif command == 12:
            payload = b''
        elif command == 9:
            payload = bytes(5)
        else:
            self.fail(f'unexpected native command {command}')
        checksum = zlib.crc32(words(sequence, command, len(payload), crc, reply_code) + payload)
        self.put(request + 1152,
                 words(sequence, command, len(payload), checksum, crc, reply_code) + bytes(104) + payload)
        if self.run_until_heartbeat and (
                self.commands.count(12) >= 2 or
                self.live_offer_failure and self.commands.count(11) >= 2):
            self.machine.emu_stop()

    def syscall(self, machine, interrupt, unused):
        args = [machine.reg_read(register) for register in REGISTERS]
        number = machine.reg_read(UC_ARM_REG_R7)
        self.calls.append((number, args))
        result = 0
        if number in (2, 42, 66, 114):
            self.fail(f'direct worker must not fork, create pipes, setsid or wait: {number}')
        elif number in (20, 64, 147):
            result = {20: 103, 64: 102, 147: 102}[number]
        elif number == 174:
            self.assertEqual(args[2:4], [0, 8])
            action = struct.unpack('<5I', machine.mem_read(args[1], 20))
            expected_flags = 0 if args[0] == 13 and action[0] == 1 else 4
            self.assertEqual(action[1:], (expected_flags, 0, 0xffffffff, 0xffffffff))
            self.actions[args[0]] = action[0]
        elif number == 5:
            path = self.text(args[0])
            if path.endswith(('/R9WORK.TXT', '/R10WORK.TXT', '/R16WORK.TXT', '/R16FAULT.TXT')) or path == '/tmp/m10v-worker-1101.log':
                expected = 0x441 if path.startswith('/tmp/') else 0x101441
                self.assertEqual(args[1:3], [expected, 0o600])
                result = 57 if path.startswith('/tmp/') else 56 if 'FAULT' in path else 55
                self.open_paths.append(path)
                self.open_files[result] = path
                self.pending_files[result] = bytearray()
            elif path == '/dev/urandom':
                result = 30
            elif path == '/dev/mem':
                result = 31 + (args[1] & 3)
            elif path == '/media/storage1':
                result = 40
            else:
                self.fail(f'unexpected open {path}')
        elif number == 3:
            machine.mem_write(args[1], bytes(range(1, args[2] + 1)))
            result = args[2]
        elif number == 4:
            data = bytes(machine.mem_read(args[1], args[2]))
            self.logs.append((args[0], data))
            if args[0] in self.open_files:
                self.pending_files[args[0]].extend(data)
            if args[0] == 1 and self.stdout_error:
                result = -32
                disposition = self.actions.get(13, 0)
                if disposition != 1 and not self.handling_sigpipe:
                    self.handling_sigpipe = True
                    if not disposition:
                        self.exit_code = 141
                        machine.emu_stop()
                    else:
                        info, context = 0x10001000, 0x10001100
                        machine.mem_write(info, words(13, 0, 0x80, 0))
                        machine.mem_write(context + 92, words(machine.reg_read(UC_ARM_REG_PC)))
                        machine.reg_write(UC_ARM_REG_R0, 13)
                        machine.reg_write(UC_ARM_REG_R1, info)
                        machine.reg_write(UC_ARM_REG_R2, context)
                        machine.reg_write(UC_ARM_REG_PC, disposition)
                        return
            else:
                result = args[2]
        elif number == 192:
            if args[3] == 0x22:
                result = 0x21000000
                self.assertLess(args[1], 0x400000)
            else:
                result = 0x20000000
                physical = args[5] << 12
                self.mappings[result] = (physical, args[1], args[2])
                machine.mem_write(result, self.physical_bytes(physical, args[1]))
        elif number == 91:
            physical, length, protection = self.mappings.pop(args[0])
            if protection == 3:
                self.put(physical, bytes(machine.mem_read(args[0], length)))
                self.respond()
        elif number == 263:
            machine.mem_write(args[1], words(self.clock // 1000, self.clock % 1000 * 1000000))
        elif number == 162:
            seconds, nanos = struct.unpack('<2I', machine.mem_read(args[0], 8))
            self.clock += seconds * 1000 + nanos // 1000000
        elif number == 281:
            if self.run_until_heartbeat:
                expected = [1, 11, 9] if self.live_offer_failure else [1, 11, 12, 9]
                self.assertEqual(self.commands[:len(expected)], expected,
                                 'network startup follows HELLO and attempted offline tick')
            result = -97 if self.socket_failure else 50
        elif number == 54:
            if self.ioctl_failure:
                result = -19
            elif args[1] == 0x8912:
                capacity, output = struct.unpack('<2I', machine.mem_read(args[2], 8))
                self.assertEqual(capacity, 512)
                if self.wifi_up:
                    entry = bytearray(32)
                    entry[:6] = b'wlan0\0'
                    entry[16:18] = b'\x02\0'
                    entry[20:24] = bytes([192, 168, 0, 1])
                    machine.mem_write(output, bytes(entry))
                machine.mem_write(args[2], words(32 if self.wifi_up else 0))
            elif args[1] in (0x8913, 0x8b01, 0x8b07):
                self.assertEqual(self.text(args[2]), 'wlan0')
                machine.mem_write(args[2] + 16, words(3 if args[1] == 0x8b07 else 1))
            else:
                self.fail(f'unexpected network ioctl {args[1]:x}')
        elif number == 294:
            self.assertEqual(args[1:3], [1, 25])
            self.assertEqual(self.text(args[3]), 'wlan0')
        elif number == 282:
            self.assertEqual(bytes(machine.mem_read(args[1], 8)),
                             b'\x02\0' + (18743).to_bytes(2, 'big') + bytes([192, 168, 0, 1]))
        elif number == 284:
            self.assertEqual(args[:2], [50, 1])
            if self.stop_on_listen:
                machine.emu_stop()
        elif number == 322:
            result = 41 if self.text(args[1]) == 'M10V' else 42
        elif number == 323:
            result = -17
        elif number == 6:
            if args[0] in self.open_files:
                path = self.open_files.pop(args[0])
                self.published_files.setdefault(path, bytearray()).extend(self.pending_files.pop(args[0]))
        elif number == 1:
            self.exit_code = args[0]
            machine.emu_stop()
        else:
            self.fail(f'unexpected syscall {number} {args}')
        machine.reg_write(UC_ARM_REG_R0, result & 0xffffffff)

    def execute(self, name, *args):
        self.assertIn(name, self.symbols, f'compiled service lacks {name}')
        self.machine.reg_write(UC_ARM_REG_SP, 0x10010000)
        self.machine.reg_write(UC_ARM_REG_LR, 0x10000)
        for register, value in zip(REGISTERS, args):
            self.machine.reg_write(register, value)
        self.machine.emu_start(self.symbols[name], 0x10000, count=3000000)
        return self.machine.reg_read(UC_ARM_REG_R0)

    def diagnostics(self):
        self.execute('m10v_linux_diagnostics_start')
        self.assertEqual(set(self.actions), {1, 4, 6, 7, 11, 13, 15})
        self.assertIn((55, b'PROCESS_START 00000067 00000066 00000066\n'), self.logs)

    def test_sd_trace_is_published_on_close_before_return(self):
        self.diagnostics()
        published = self.published_files.get('/media/storage1/M10V/R16WORK.TXT', b'')
        self.assertIn(b'PROCESS_START ', published,
                      'a completed trace must close its SD descriptor so readers see its size')

    def test_ram_entry_precedes_any_sd_open(self):
        self.diagnostics()
        self.assertEqual(self.open_paths[0], '/tmp/m10v-worker-1101.log')
        self.assertIn(b'R16_ENTRY_BEFORE_SD',
                      self.published_files.get('/tmp/m10v-worker-1101.log', b''))

    def test_fault_logs_pc_and_address_when_inherited_stdout_fails(self):
        self.diagnostics()
        self.stdout_error = True
        info, context = 0x10001000, 0x10001100
        self.machine.mem_write(info, words(11, 0, 1, 0xdeadbeef))
        self.machine.mem_write(context + 92, words(0x3ebe0))
        self.symbols['installed_fault_handler'] = self.actions[11]
        before = sum(number == 5 for number, _ in self.calls)
        self.execute('installed_fault_handler', 11, info, context)
        self.assertEqual(self.exit_code, 139)
        self.assertIn((56, b'WORKER_SIGNAL 0000000b 00000001 deadbeef 0003ebe0\n'), self.logs)
        self.assertEqual(sum(number == 5 for number, _ in self.calls), before)
        self.assertIn(b'WORKER_SIGNAL ', self.published_files['/media/storage1/M10V/R16FAULT.TXT'])

    def run_actual_worker(self):
        config_address = self.symbols['target_config']
        self.config = bytes(self.machine.mem_read(config_address, 180))
        owner, context = 0x56000000, 0x56010000
        self.put(0x55063910, words(1))
        self.put(0x55063988, words(owner))
        self.put(owner + 0x6400,
                 words(0x3244494d, 2, 64, context, self.wire, 2432, context) + bytes(36))
        self.put(self.wire, words(0x32434d4d, 2, 2432, 1, owner, context) + self.config[:32] + bytes(72))
        for index, address in enumerate((0x5316fcf8, 0x5319667c, 0x5383c834, 0x5383c870)):
            self.put(address, self.config[112 + index * 16:128 + index * 16])
        self.run_until_heartbeat = True
        self.execute('_start')
        self.assertIn((55, b'OFFLINE_TICKED\n'), self.logs)
        for event in ('HELLO_CLEAR_BEGIN', 'HELLO_CLEAR_OK', 'HELLO_COPY_BEGIN',
                      'HELLO_COPY_OK', 'HELLO_CRC_BEGIN', 'HELLO_CRC_OK'):
            self.assertTrue(any(fd == 55 and data.startswith(event.encode()) for fd, data in self.logs), event)

    def test_direct_start_has_no_fork_and_keeps_offline_heartbeats(self):
        self.run_actual_worker()
        self.assertGreaterEqual(self.commands.count(12), 2)

    def test_live_offer_failure_keeps_direct_worker_running(self):
        self.live_offer_failure = True
        self.run_actual_worker()
        self.assertNotIn(12, self.commands)
        self.assertGreaterEqual(self.commands.count(11), 2)
        self.assertFalse(any(b'LIVE_ARENA_OK' in data for _, data in self.logs))

    def test_broken_lcmd_stdout_ignores_sigpipe_and_keeps_offline_worker_alive(self):
        self.stdout_error = True
        self.run_actual_worker()
        self.assertEqual(self.actions[13], 1, 'SIGPIPE must be SIG_IGN')
        self.assertIsNone(self.exit_code)
        self.assertGreaterEqual(self.commands.count(12), 2)

    def test_socket_failure_does_not_starve_offline_heartbeats(self):
        self.socket_failure = True
        self.run_actual_worker()
        self.assertGreaterEqual(self.commands.count(12), 2)
        self.assertIn((55, b'WIFI_SOCKET_END ffffff9f\n'), self.logs)

    def test_ioctl_failure_closes_socket_and_keeps_heartbeats(self):
        self.ioctl_failure = True
        self.run_actual_worker()
        self.assertGreaterEqual(self.commands.count(12), 2)
        self.assertIn((55, b'WIFI_IOCTL_END 00008912 ffffffed 00000200\n'), self.logs)
        self.assertTrue(any(n == 6 and a[0] == 50 for n, a in self.calls))

    def test_network_diagnostics_stop_after_four_attempts(self):
        self.diagnostics()
        for _ in range(6):
            self.assertEqual(self.execute('m10v_linux_prepare_wifi', self.symbols['config']), 0)
        self.assertEqual(self.logs.count((55, b'WIFI_SOCKET_BEGIN\n')), 4)
        self.assertEqual(self.logs.count((55, b'WIFI_CLOSE_END\n')), 4)

    def test_direct_worker_reaches_real_listener_when_hotspot_is_available(self):
        self.wifi_up = True
        self.stop_on_listen = True
        self.run_actual_worker()
        self.assertIn((55, b'WIFI_OK\n'), self.logs)
        self.assertTrue(any(number == 284 for number, _ in self.calls))


if __name__ == '__main__':
    unittest.main()
