"""Real ARM execution of metadata journal/cache with native file-service doubles."""
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib

from scripts.build_gr3_m10v_library import FLAGS, link_object
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_READ
from unicorn import arm_const as A

ROOT = Path(__file__).resolve().parents[1]
BASE, OWNER, OFFSET = 0x541C0000, 0x55010000, 0x62FC
CACHE, OUT, SEQ, INPUT = OWNER + OFFSET, 0x55030000, 0x55030040, 0x55030100
NAMES = ('ISPFXA.BIN', 'ISPFXB.BIN')


def record(sequence, values=(0,) * 8):
    body = struct.pack('<11I', 0x31505349, 1, sequence, *values)
    return body + struct.pack('<I', zlib.crc32(body))


class EffectsCameraTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = ROOT / 'native/gr3/m10v_isp_effects_camera.c'
        if not source.exists():
            raise AssertionError('ISP effects camera journal/cache adapter is missing')
        cls.temp = tempfile.TemporaryDirectory()
        folder = Path(cls.temp.name)
        src, obj = folder / 'camera.c', folder / 'camera.o'
        src.write_text('\n'.join('#include "' + str(ROOT / 'native/gr3' / name) + '"'
            for name in ('m10v_isp_effects_state.c', 'm10v_isp_effects_camera.c')))
        subprocess.run([shutil.which('clang'), *FLAGS,
            '-DM10V_ISP_EFFECT_CACHE_OWNER_OFFSET=' + hex(OFFSET), '-c', str(src), '-o', str(obj)],
            check=True, capture_output=True)
        exports = tuple('m10v_isp_effects_camera_' + name for name in ('init', 'refresh', 'save', 'snapshot'))
        cls.code, cls.symbols = link_object(obj.read_bytes(), BASE, prefix='m10v_settings_',
            omitted_exports=('m10v_settings_open', 'm10v_settings_key'), additional_exports=exports)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'temp'):
            cls.temp.cleanup()

    def setUp(self):
        self.u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        self.u.ctl_set_cpu_model(A.UC_CPU_ARM_CORTEX_A9)
        self.u.mem_map(BASE, 0x10000)
        self.u.mem_write(BASE, self.code)
        self.u.mem_map(0x53800000, 0x30000)
        self.u.mem_map(0x55000000, 0x100000)
        self.files, self.calls = {}, []
        self.read_count = self.write_count = 0
        self.on_read = self.on_write = None
        self.write_fail = self.corrupt_write = self.forbid_services = False
        self.put(0x55063910, 1)
        self.put(0x55063988, OWNER)
        self.put(0x55000108, 0x55000120)
        self.put(0x55000120, 0x55000140)
        self.u.mem_write(0x55000160, b'\x01')
        self.u.hook_add(UC_HOOK_CODE, self.hook)

    def put(self, address, *values):
        self.u.mem_write(address, struct.pack('<' + 'I' * len(values), *values))

    def word(self, address):
        return struct.unpack('<I', self.u.mem_read(address, 4))[0]

    def hook(self, u, pc, size, _):
        if pc not in (0x53828014, 0x53825648, 0x53825FA8):
            return
        self.assertFalse(self.forbid_services, 'capture snapshot called filesystem')
        self.calls.append(pc)
        result = 0
        if pc == 0x53828014:
            result = 0x55000100
        else:
            name = bytes(u.mem_read(u.reg_read(A.UC_ARM_REG_R1), 12)).split(b'\0')[0].decode()
            length, buffer = u.reg_read(A.UC_ARM_REG_R2), u.reg_read(A.UC_ARM_REG_R3)
            self.assertEqual(length, 48)
            self.assertIn(name, NAMES)
            if pc == 0x53825648:
                self.read_count += 1
                if self.on_read:
                    override = self.on_read(self.read_count, name)
                else:
                    override = None
                data = self.files.get(name) if override is None else override
                if data is not None:
                    u.mem_write(buffer, data[:length])
                    result = int(len(data) == length)
            else:
                self.write_count += 1
                if self.on_write:
                    self.on_write(self.write_count, name)
                if not self.write_fail:
                    data = bytes(u.mem_read(buffer, length))
                    self.files[name] = data[:-1] + bytes([data[-1] ^ 1]) if self.corrupt_write else data
                    result = 1
        u.reg_write(A.UC_ARM_REG_R0, result)
        u.reg_write(A.UC_ARM_REG_PC, u.reg_read(A.UC_ARM_REG_LR))

    def call(self, name, *args):
        for i, value in enumerate(args):
            self.u.reg_write(getattr(A, 'UC_ARM_REG_R' + str(i)), value)
        self.u.reg_write(A.UC_ARM_REG_SP, 0x550FD000)
        self.u.reg_write(A.UC_ARM_REG_LR, 0x550FF000)
        self.u.emu_start(self.symbols['m10v_isp_effects_camera_' + name], 0x550FF000, count=100000)
        self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC), 0x550FF000)
        value = self.u.reg_read(A.UC_ARM_REG_R0)
        return value if value < 0x80000000 else value - 0x100000000

    def cache_bytes(self):
        return bytes(self.u.mem_read(CACHE, 44))

    def snapshot(self):
        self.forbid_services = True
        try:
            result = self.call('snapshot', OUT, SEQ)
        finally:
            self.forbid_services = False
        return result, bytes(self.u.mem_read(OUT, 32)), self.word(SEQ)

    def test_init_owns_only_cache_and_defaults_without_writing_files(self):
        self.u.mem_write(CACHE - 4, b'\xA5' * 52)
        self.call('init', OWNER)
        self.assertEqual(bytes(self.u.mem_read(CACHE - 4, 4)), b'\xA5' * 4)
        self.assertEqual(bytes(self.u.mem_read(CACHE + 44, 4)), b'\xA5' * 4)
        self.assertEqual(self.snapshot(), (1, bytes(32), 0))
        self.assertEqual(self.write_count, 0)

    def test_cold_invalid_records_use_bounded_defaults_but_unavailable_filesystem_does_not(self):
        self.files = {NAMES[0]: record(7)[:20], NAMES[1]: record(7)[:-1] + b'X'}
        self.call('init', OWNER)
        self.assertEqual(self.snapshot(), (1, bytes(32), 0))
        self.u.mem_write(0x55000160, b'\x00')
        self.call('init', OWNER)
        self.assertEqual(self.cache_bytes(), bytes(44))
        self.assertEqual(self.snapshot()[0], 0)
        self.assertEqual(self.write_count, 0)

    def test_first_menu_refresh_accepts_unchanged_unsaved_defaults(self):
        self.call('init', OWNER)
        before = self.cache_bytes()
        self.assertEqual(self.snapshot(), (1, bytes(32), 0))
        self.assertEqual(self.call('refresh', OWNER), 0)
        self.assertEqual(self.snapshot(), (1, bytes(32), 0))
        self.assertEqual(self.write_count, 0)


    def test_refresh_selects_wrap_safe_valid_record_and_rejects_crc_short_reads(self):
        self.files = {NAMES[0]: record(0xFFFFFFFF, (1, 0, 0, 0, 0, 0, 0, 0)),
                      NAMES[1]: record(0, (2, 1, 2, 4, 2, 3, 2, 0))}
        self.call('init', OWNER)
        self.assertEqual(self.snapshot(), (1, struct.pack('<8I', 2, 1, 2, 4, 2, 3, 2, 0), 0))
        before = self.cache_bytes()
        self.files = {NAMES[0]: record(7)[:20], NAMES[1]: record(7)[:-1] + b'X'}
        self.assertLess(self.call('refresh', OWNER), 0)
        self.assertEqual(self.cache_bytes(), before)

    def test_ambiguous_journals_never_publish_defaults_or_replace_warm_cache(self):
        for records in ((record(0), record(0x80000000)),
                        (record(9), record(9, (1, 0, 0, 0, 0, 0, 0, 0)))):
            self.u.mem_write(CACHE, bytes(44))
            self.files = dict(zip(NAMES, records))
            self.assertLess(self.call('refresh', OWNER), 0)
            self.assertEqual(self.cache_bytes(), bytes(44))
            self.assertEqual(self.snapshot()[0], 0)

    def test_successful_save_requires_exact_readback_and_winning_generation(self):
        self.call('init', OWNER)
        values = (3, 2, 1, 4, 2, 3, 1, 0)
        self.put(INPUT, *values)
        self.assertEqual(self.call('save', OWNER, INPUT), 0)
        self.assertEqual(self.files[NAMES[1]], record(1, values))
        self.assertEqual(self.snapshot(), (1, struct.pack('<8I', *values), 1))
        self.assertEqual(self.read_count, 7)  # init2, latest2, readback1, winner2

    def test_failed_write_readback_and_winner_validation_never_publish(self):
        for failure in ('write', 'corrupt', 'readback', 'hidden_newer', 'cache_changed'):
            self.files = {}
            self.u.mem_write(CACHE, bytes(44))
            self.call('init', OWNER)
            self.put(INPUT, 3, 0, 0, 0, 0, 0, 0, 0)
            before = self.cache_bytes()
            start = self.read_count
            self.write_fail = failure == 'write'
            self.corrupt_write = failure == 'corrupt'
            def on_read(count, name):
                if failure == 'readback' and count == start + 3:
                    return b''
                if failure == 'hidden_newer' and count == start + 4:
                    return record(99)
                return None
            self.on_read = on_read
            self.on_write = (lambda *_: self.put(CACHE + 4, self.word(CACHE + 4) + 2)) if failure == 'cache_changed' else None
            self.assertLess(self.call('save', OWNER, INPUT), 0, failure)
            if failure == 'cache_changed':
                self.assertEqual(self.cache_bytes()[8:], before[8:])
            else:
                self.assertEqual(self.cache_bytes(), before)
        self.on_read = self.on_write = None

    def test_save_uses_authenticated_cache_floor_despite_failed_initial_reads(self):
        self.files[NAMES[0]] = record(8)
        self.call('init', OWNER)
        self.put(INPUT, 1, 0, 0, 0, 0, 0, 0, 0)
        start = self.read_count
        self.on_read = lambda count, name: b'' if count <= start + 2 else None
        self.assertEqual(self.call('save', OWNER, INPUT), 0)
        self.assertEqual(self.files[NAMES[1]], record(9, (1, 0, 0, 0, 0, 0, 0, 0)))
        self.assertEqual(self.snapshot()[2], 9)

    def test_save_wraps_sequence_and_rejects_ambiguous_cache_floor(self):
        self.files[NAMES[1]] = record(0xFFFFFFFF)
        self.call('init', OWNER)
        self.put(INPUT, 2, 0, 0, 0, 0, 0, 0, 0)
        self.assertEqual(self.call('save', OWNER, INPUT), 0)
        self.assertEqual(self.snapshot()[2], 0)
        self.files = {NAMES[0]: record(0x80000000)}
        before = self.cache_bytes()
        self.assertLess(self.call('save', OWNER, INPUT), 0)
        self.assertEqual(self.cache_bytes(), before)

    def test_snapshot_rejects_unavailable_mutating_invalid_cache_and_pointer_ranges(self):
        self.call('init', OWNER)
        before = self.cache_bytes()
        for address, invalid in ((0x55063910, 0), (0x55063988, 0),
                (CACHE, 0), (CACHE + 4, 3), (CACHE + 4, 0), (CACHE + 12, 4), (CACHE + 40, 1)):
            original = self.word(address)
            self.put(OUT, *([0xA5A5A5A5] * 8))
            self.put(SEQ, 99)
            self.put(address, invalid)
            self.assertEqual(self.snapshot(), (0, b'\xA5' * 32, 99))
            self.put(address, original)
        for out, sequence in ((0, SEQ), (OUT + 1, SEQ), (0x7FFFFFF0, SEQ),
                              (OUT, 0), (OUT, SEQ + 1), (OUT, OUT + 4),
                              (CACHE + 12, SEQ), (OUT, CACHE + 8)):
            self.assertEqual(self.call('snapshot', out, sequence), 0)
        self.assertEqual(self.cache_bytes(), before)

    def test_snapshot_rechecks_version_before_publishing_outputs(self):
        self.call('init', OWNER)
        self.put(OUT, *([0xA5A5A5A5] * 8))
        self.put(SEQ, 99)
        fired = []
        def mutate(u, access, address, size, value, data):
            if not fired:
                fired.append(True)
                self.put(CACHE + 4, self.word(CACHE + 4) + 2)
        handle = self.u.hook_add(UC_HOOK_MEM_READ, mutate, begin=CACHE + 12, end=CACHE + 43)
        self.assertEqual(self.snapshot(), (0, b'\xA5' * 32, 99))
        self.u.hook_del(handle)
        self.assertTrue(fired)

    def test_invalid_save_and_owner_fail_before_any_native_service(self):
        self.call('init', OWNER)
        self.calls.clear()
        self.put(INPUT, 4, 0, 0, 0, 0, 0, 0, 0)
        for owner, settings in ((0, INPUT), (OWNER + 1, INPUT), (0x7FFFFFFC, INPUT),
                                (OWNER, 0), (OWNER, INPUT + 1), (OWNER, INPUT)):
            self.assertLess(self.call('save', owner, settings), 0)
        self.assertEqual(self.calls, [])
        self.put(INPUT, *([0] * 8))
        self.u.mem_write(CACHE, bytes(44))
        self.assertLess(self.call('save', OWNER, INPUT), 0)
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
