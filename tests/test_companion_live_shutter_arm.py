"""Production ARM consumer: shutter publication can race a frame read batch."""
import struct
import unittest

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_INTR, UC_HOOK_MEM_READ
from unicorn import arm_const as A
from tests import test_companion_live_attach_arm as attach


class LiveShutterArmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        attach.LiveAttachArmTests.setUpClass.__func__(cls)

    def machine(self, mode=1):
        u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        for address, size in ((0x10000, 0x100000), (0x1000000, 0x200000),
                              (0x56000000, 0x200000)):
            u.mem_map(address, size)
        offset = struct.unpack_from('<I', self.binary, 28)[0]
        size, count = struct.unpack_from('<HH', self.binary, 42)
        for index in range(count):
            segment = struct.unpack_from('<8I', self.binary, offset + index * size)
            if segment[0] == 1:
                u.mem_write(segment[2], self.binary[segment[1]:segment[1] + segment[4]])
        u.mem_write(0x90000, struct.pack('<8I', 1, 0x56000000, 111232,
                                       0x56020000, 3, 36992, 36864, 1))
        events, writes = [], []
        self.saved, self.file_bytes = {}, bytearray()

        def string(at):
            value = bytearray()
            while u.mem_read(at, 1) != b'\0':
                value += u.mem_read(at, 1)
                at += 1
            return value.decode()

        def syscall(machine, interrupt, unused):
            number = machine.reg_read(A.UC_ARM_REG_R7)
            args = [machine.reg_read(getattr(A, 'UC_ARM_REG_R' + str(i))) for i in range(6)]
            if number == 192:
                result = 0x1000000
            elif number == 5:
                result = 10
            elif number == 322:
                name = string(args[1])
                result = 11 if name == 'M10V' else 12 if args[2] & (1 << 14) else 13 if name.endswith('.TMP') else -2
            elif number == 323:
                result = -17
            elif number == 4:
                data = bytes(machine.mem_read(args[1], args[2]))
                if args[0] == 1:
                    writes.append(data)
                else:
                    self.assertEqual(args[0], 13)
                    self.file_bytes.extend(data)
                result = args[2]
            elif number == 0xfe00:
                events.append((string(args[0]), struct.unpack('<' + 'I' * args[2],
                    machine.mem_read(args[1], args[2] * 4))))
                result = 0
            elif number == 329:
                self.saved[string(args[3])] = bytes(self.file_bytes)
                result = 0
            elif number in (6, 118):
                result = 0
            else:
                self.fail(f'unexpected syscall {number}')
            machine.reg_write(A.UC_ARM_REG_R0, result & 0xffffffff)

        u.hook_add(UC_HOOK_INTR, syscall)

        def call(entry, *args):
            for index, value in enumerate(args):
                u.reg_write(getattr(A, 'UC_ARM_REG_R' + str(index)), value)
            u.reg_write(A.UC_ARM_REG_SP, 0xa0000)
            u.reg_write(A.UC_ARM_REG_LR, 0x80000)
            u.emu_start(entry, 0x80000, count=2000000)
            self.assertEqual(u.reg_read(A.UC_ARM_REG_PC), 0x80000)
            return u.reg_read(A.UC_ARM_REG_R0)

        self.assertEqual(call(self.entry, 0x90000, 0x56020000), 1)
        request = 4 | mode
        u.mem_write(0x56000000, struct.pack('<5I', 0x31494c4d, 1, 111232, 0x56020000, request))

        def frame(ordinal, tick):
            at = 0x56000100 + ((ordinal - 1) % 3) * 36992
            u.mem_write(at, struct.pack('<3I', ordinal * 2, tick & 0xffffffff, request))
            u.mem_write(at + 128, bytes([42]) * 24576 + bytes([128]) * 12288)

        def shot(tick):
            u.mem_write(0x56000080, struct.pack('<8I', 2, tick & 0xffffffff, request, 0, 1, 2, 3, 1))

        return u, lambda now: call(self.sample, now), frame, shot, events, writes

    def test_shutter_published_during_read_batch_keeps_owned_pre_and_post_frames(self):
        u, sample, frame, shot, events, writes = self.machine()
        # Publish the event after the consumer copied the old shutter packet,
        # before it reads the already-produced post-exposure frame headers.
        published, armed = [], []

        def publish(machine, access, address, size, value, unused):
            if address == 0x560000ff and armed and not published:
                published.append(True)
                shot(12000)
                frame(21, 12050)

        hook = u.hook_add(UC_HOOK_MEM_READ, publish)
        for ordinal, tick in enumerate(range(10000, 12000, 100), 1):
            frame(ordinal, tick)
            sample(tick)
        armed.append(True)
        sample(12050)
        u.hook_del(hook)
        self.assertEqual(published, [True], events)
        frame(22, 12150)
        sample(12150)
        self.assertIn(b'LIVE_SHUTTER\n', writes)
        self.assertNotIn(b'LIVE_SKIPPED_PREBUFFER_OR_BUSY\n', writes)
        for ordinal, tick in enumerate(range(12250, 13500, 100), 23):
            frame(ordinal, tick)
            sample(tick)
        sample(13680)
        self.assertIn(b'LIVE_SD_OK\n', writes)
        self.assertEqual(list(self.saved), ['01000000.M10'])
        data = next(iter(self.saved.values()))
        self.assertEqual(struct.unpack_from('<4sHHHHIII', data),
                         (b'M10L', 2, 31, 192, 128, 1600, 3151, 1))
        self.assertEqual(len(data), 24 + 31 * (36864 + 8))
        self.assertEqual(struct.unpack_from('<II', data, 24 + 16 * (36864 + 8)),
                         (1650, 36864))

    def test_timestamp_window_survives_batched_consumer_scheduling(self):
        # Circular-output references retain source PTS; consumer scheduling is
        # not a capture clock. Exercise one to three published slots per read.
        for batch in (1, 2, 3):
            with self.subTest(batch=batch):
                u, sample, frame, shot, events, writes = self.machine()
                for ordinal, tick in enumerate(range(10000, 12000, 100), 1):
                    frame(ordinal, tick)
                    if ordinal % batch == 0:
                        sample(50000 + tick)
                shot(12000)
                for ordinal, tick in enumerate(range(12050, 13500, 100), 21):
                    frame(ordinal, tick)
                    if ordinal % batch == 0:
                        sample(50000 + tick)
                sample(63500)
                sample(63700)
                self.assertIn(b'LIVE_SD_OK\n', writes)
                self.assertNotIn(b'LIVE_SKIPPED_PREBUFFER_OR_BUSY\n', writes)
                data = next(iter(self.saved.values()))
                magic, version, count, width, height, shutter, duration, fmt = \
                    struct.unpack_from('<4sHHHHIII', data)
                self.assertEqual((magic, version, width, height, fmt),
                                 (b'M10L', 2, 192, 128, 1))
                times = [struct.unpack_from('<I', data, 24 + i * 36872)[0]
                         for i in range(count)]
                self.assertEqual(times, sorted(set(times)))
                self.assertGreaterEqual(shutter, 1250)
                self.assertLessEqual(shutter, 1650)
                self.assertLessEqual(duration - times[-1], 251)

    def test_inflight_shutter_defers_post_frame_until_stable_publication(self):
        u, sample, frame, shot, events, writes = self.machine()
        for ordinal, tick in enumerate(range(10000, 12000, 100), 1):
            frame(ordinal, tick)
            sample(tick)
        shot(12000)
        u.mem_write(0x56000080, struct.pack('<I', 1))
        frame(21, 12050)
        sample(12050)
        self.assertEqual(writes, [])
        u.mem_write(0x56000080, struct.pack('<I', 2))
        frame(22, 12150)
        sample(12150)
        self.assertEqual(writes, [b'LIVE_SHUTTER\n'])

    def test_stable_shutter_arms_during_blackout_and_retains_real_preframes(self):
        u, sample, frame, shot, events, writes = self.machine()
        for ordinal, tick in enumerate(range(10000, 12000, 100), 1):
            frame(ordinal, tick)
            sample(tick)
        shot(12000)
        sample(12000)  # no post frame exists; event still freezes prehistory.
        self.assertIn(b'LIVE_SHUTTER\n', writes)
        sample(14000)  # old1800ms idle reset must not discard pending history.
        for ordinal, tick in enumerate(range(14644, 16145, 100), 21):
            frame(ordinal, tick)
            sample(tick)
        sample(16250)
        self.assertIn(b'LIVE_SD_OK\n', writes)
        data = next(iter(self.saved.values()))
        header = struct.unpack_from('<4sHHHHIII', data)
        self.assertEqual(header[5:7], (1600, 5745))
        times = [struct.unpack_from('<I', data, 24 + i * 36872)[0] for i in range(header[2])]
        self.assertEqual(times, list(range(0, 1501, 100)) + list(range(4244, 5745, 100)))
        starts = [v for n, v in events if n == 'LIVE_POST_START']
        self.assertEqual(starts[0][3], 14644)
        self.assertEqual(starts[0][6], 2644)

    def test_no_post_timeout_and_late_first_post_are_precise_failures(self):
        for first in (None, 15001):
            with self.subTest(first=first):
                u, sample, frame, shot, events, writes = self.machine(mode=2)
                shot(10000)
                sample(10000)
                self.assertIn(b'LIVE_SHUTTER\n', writes)
                sample(14000)
                if first is not None:
                    frame(1, first)
                    sample(first)
                else:
                    sample(15100)
                failures = [v for n, v in events if n == 'LIVE_WINDOW_FAILED']
                self.assertEqual(failures[-1][0], 6)
                self.assertNotIn(b'LIVE_SD_OK\n', writes)
                self.assertEqual(self.saved, {})

    def test_short_prebuffer_still_rejects_and_reports_actual_window(self):
        u, sample, frame, shot, events, writes = self.machine()
        for ordinal, tick in enumerate(range(10000, 10300, 100), 1):
            frame(ordinal, tick)
            sample(tick)
        shot(10300)
        frame(4, 10350)
        sample(10350)
        self.assertEqual(writes, [b'LIVE_SKIPPED_PREBUFFER_OR_BUSY\n'])
        windows = [values for name, values in events if name == 'LIVE_WINDOW_REJECT']
        self.assertEqual(windows, [(2, 5, 10300, 3, 10000, 10200, 0, 0)])
        self.assertEqual(self.saved, {})

    def test_after_only_saves_with_independent_linux_epoch_and_wrapping_native_clock(self):
        u, sample, frame, shot, events, writes = self.machine(mode=2)
        start = 0xffffff80
        shot(start)
        for ordinal, delta in enumerate(range(60, 1500, 100), 1):
            frame(ordinal, start + delta)
            sample(10000 + delta)
        sample(11680)
        self.assertEqual(writes, [b'LIVE_SHUTTER\n', b'LIVE_SD_OK\n'])
        data = next(iter(self.saved.values()))
        self.assertEqual(struct.unpack_from('<4sHHHHIII', data),
                         (b'M10L', 2, 15, 192, 128, 0, 1561, 1))


if __name__ == '__main__':
    unittest.main()
