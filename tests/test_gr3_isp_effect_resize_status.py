"""Execute Resize error observation and its optional hook as real ARM code.

The original RTOS is hash-pinned; no pixels or hardware are emulated.
"""
import importlib
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import border_recovery_wait_guard as native_guard
from scripts import build_gr3_border_wait_guard as guard
from unicorn import UC_PROT_READ, UC_PROT_WRITE, UC_PROT_EXEC

HELPER = 'm10v_border_effect_resize_status'
SITE = 0x53771620
BASE, A = native_guard.BASE, native_guard.A


class ResizeStatusTests(unittest.TestCase):
    reg = native_guard.WaitGuard.reg
    put = native_guard.WaitGuard.put
    word = native_guard.WaitGuard.word
    call = native_guard.WaitGuard.call
    invoke = native_guard.WaitGuard.invoke
    configure_other_owner = native_guard.WaitGuard.configure_other_owner

    @classmethod
    def setUpClass(cls):
        builder = ROOT / 'scripts/build_gr3_isp_effect_resize_status.py'
        if not builder.exists():
            raise AssertionError('optional Resize status hook builder is missing')
        cls.builder = importlib.import_module('scripts.build_gr3_isp_effect_resize_status')
        cls.code, cls.symbols, _, _ = guard._compile(BASE)
        if HELPER not in cls.symbols:
            raise AssertionError('private Resize status propagation is not implemented')
        cls.rom = (ROOT / 'builds/gr3-extension-validation/official-rtos.bin').read_bytes()
        _, cls.guard_manifest = guard.build(BASE, cls.rom, border_enabled=True,
                                            internal_guard_research=True)
        cls.shim, cls.manifest = cls.builder.build(0x54170000, cls.rom,
            cls.guard_manifest, enabled=True)

    def setUp(self):
        native_guard.WaitGuard.setUp(self)
        self.u.mem_map(0x54170000, 0x10000)
        self.u.mem_write(0x54170000, self.shim)
        self.configure_other_owner('resize')
        self.context, self.params = 0x55007000, 0x55008000
        self.put(self.worker + 0x34, self.context)
        self.put(self.client + 68, 0x31584645, 0)
        self.frame = self.original_frame()

    def hook(self, u, pc, size, data):
        if pc == self.symbols[HELPER] and getattr(self, 'clobber_helper', False):
            self.helper_args = (self.reg(0), self.reg(1))
            target = u.reg_read(A.UC_ARM_REG_LR)
            for i in range(13):
                u.reg_write(getattr(A, f'UC_ARM_REG_R{i}'), 0xA0000000 + i)
            for i in range(32):
                u.reg_write(getattr(A, f'UC_ARM_REG_D{i}'), 0xF000000000000000 + i)
            u.reg_write(A.UC_ARM_REG_FPSCR, 0)
            u.reg_write(A.UC_ARM_REG_CPSR, (u.reg_read(A.UC_ARM_REG_CPSR) & 0x0FFFFFFF) | 0xF0000000)
            u.reg_write(A.UC_ARM_REG_LR, 0xDEADBEE0)
            u.reg_write(A.UC_ARM_REG_PC, target)
            return
        return native_guard.WaitGuard.hook(self, u, pc, size, data)

    def original_frame(self):
        self.u.reg_write(A.UC_ARM_REG_C1_C0_2, 0xF00000)
        self.u.reg_write(A.UC_ARM_REG_FPEXC, 0x40000000)
        for i, value in enumerate((self.context, self.params, 2)):
            self.u.reg_write(getattr(A, f'UC_ARM_REG_R{i}'), value)
        self.u.reg_write(A.UC_ARM_REG_R7, self.worker)
        self.u.reg_write(A.UC_ARM_REG_SP, 0x550ED000)
        self.u.reg_write(A.UC_ARM_REG_LR, 0x536733E4)
        self.u.emu_start(0x53770BF0, 0x53770C28, count=1000)
        frame = self.u.reg_read(A.UC_ARM_REG_FP)
        self.assertEqual((self.word(frame - 4), self.word(frame - 28),
                          self.word(frame - 0x2D0)),
                         (0x536733E4, self.worker, self.context))
        return frame

    def install_hook(self):
        patches = self.manifest['patches']
        self.assertEqual(len(patches), 1)
        patch = patches[0]
        self.assertEqual(self.word(SITE), patch['expected'])
        self.u.mem_protect(SITE & ~4095, 4096, UC_PROT_READ | UC_PROT_WRITE | UC_PROT_EXEC)
        self.put(SITE, patch['replacement'])
        self.u.mem_protect(SITE & ~4095, 4096, UC_PROT_READ | UC_PROT_EXEC)

    def test_private_effect_error_becomes_sticky_and_success_never_clears_it(self):
        for native_error, before, expected in ((1, 0, 1), (255, 0, 1), (0, 0, 0), (0, 1, 1), (1, 7, 1)):
            self.u.mem_write(self.context + 0x54, bytes([native_error]))
            self.put(self.client + 72, before)
            self.invoke(self.symbols[HELPER], (self.context, self.frame))
            self.assertEqual(self.word(self.client + 72), expected)
            self.assertEqual(bytes(self.u.mem_read(self.context + 0x54, 1)), bytes([native_error]))

    def test_rejects_every_mismatched_native_scope_and_leaves_stock_clients_untouched(self):
        cases = [(self.frame - 4, 0xDEADBEEF), (self.frame - 0x2D0, self.context + 4),
                 (self.frame - 28, 0), (self.worker + 0x34, self.context + 4),
                 (self.worker + 0x48, 0), (self.worker + 0x54, 0),
                 (self.worker + 0x4C, 0), (self.worker + 0x50, 0),
                 (self.client, 0x53C5B680), (self.client + 32, 0),
                 (self.client + 36, 0), (self.client + 52, 0x03070004),
                 (self.client + 56, 0x10), (self.client + 60, self.worker + 4),
                 (self.client + 64, self.job + 4), (self.job + 4, self.client + 4),
                 (self.client + 68, 0), (self.client + 68, 0x55009000)]
        self.u.mem_write(self.context + 0x54, b'\x01')
        for address, invalid in cases:
            before = self.word(address)
            self.put(address, invalid)
            self.put(self.client + 72, 0)
            self.invoke(self.symbols[HELPER], (self.context, self.frame))
            self.assertEqual(self.word(self.client + 72), 0, hex(address))
            self.put(address, before)
        self.invoke(self.symbols[HELPER], (self.context + 4, self.frame))
        self.assertEqual(self.word(self.client + 72), 0)
        self.invoke(self.symbols[HELPER], (0, self.frame))
        self.invoke(self.symbols[HELPER], (self.context, 0))
        self.assertEqual(self.word(self.client + 72), 0)
        self.put(self.frame - 4, 0xDEADBEEF)
        self.put(self.frame - 28, 0x70000000)  # Must not dereference rejected parent.
        self.invoke(self.symbols[HELPER], (self.context, self.frame))
        self.assertEqual(self.word(self.client + 72), 0)

    def test_inline_hook_observes_before_original_status_copy_and_clear(self):
        self.install_hook()
        self.u.mem_write(self.context + 0x54, b'\x07')
        self.put(self.frame - 0x2D4, 0)
        self.u.reg_write(A.UC_ARM_REG_FP, self.frame)
        self.u.reg_write(A.UC_ARM_REG_R2, self.context)
        self.u.reg_write(A.UC_ARM_REG_R5, self.params)
        self.u.emu_start(SITE, SITE + 0x18, count=10000)
        self.assertEqual(self.word(self.client + 72), 1)
        self.assertEqual(bytes(self.u.mem_read(self.params + 0x3A, 1)), b'\x07')
        self.assertEqual(bytes(self.u.mem_read(self.context + 0x54, 1)), b'\x00')

    def test_inline_preserves_gprs_nzcv_all_vfp_and_fpscr_except_displaced_r1(self):
        self.install_hook()
        self.clobber_helper = True
        for i in range(13):
            if i != 11:
                self.u.reg_write(getattr(A, f'UC_ARM_REG_R{i}'), 0x12340000 + i)
        self.u.reg_write(A.UC_ARM_REG_FP, self.frame)
        self.put(self.frame - 0x2D4, 0xCAFEBABE)
        self.u.reg_write(A.UC_ARM_REG_LR, 0x550AB000)
        self.u.reg_write(A.UC_ARM_REG_SP, 0x550EC000)
        self.u.reg_write(A.UC_ARM_REG_CPSR, (self.u.reg_read(A.UC_ARM_REG_CPSR) & 0x0FFFFFFF) | 0xA0000000)
        self.u.reg_write(A.UC_ARM_REG_FPSCR, 0x01000000)
        for i in range(32):
            self.u.reg_write(getattr(A, f'UC_ARM_REG_D{i}'), 0x1234567800000000 + i)
        before = [self.reg(i) for i in range(15)]
        self.u.emu_start(SITE, SITE + 4, count=10000)
        self.assertEqual(self.helper_args, (self.context, self.frame))
        before[1] = 0xCAFEBABE
        self.assertEqual([self.reg(i) for i in range(15)], before)
        self.assertEqual(self.u.reg_read(A.UC_ARM_REG_CPSR) & 0xF0000000, 0xA0000000)
        self.assertEqual(self.u.reg_read(A.UC_ARM_REG_FPSCR), 0x01000000)
        self.assertEqual([self.u.reg_read(getattr(A, f'UC_ARM_REG_D{i}')) for i in range(32)],
                         [0x1234567800000000 + i for i in range(32)])

    def test_builder_is_opt_in_and_default_guard_remains_eighteen_patches(self):
        code, manifest = self.builder.build()
        self.assertEqual((code, manifest['patches']), (b'', []))
        self.assertFalse(manifest['enabled'])
        self.assertEqual(len(self.guard_manifest['patches']), 18)
        self.assertEqual(self.manifest['patches'][0]['expected'], 0xE51B12D4)
        self.assertFalse(self.manifest['hardware_completion_proven'])
        self.assertFalse(self.manifest['failure_quiescence_proven'])

    def test_builder_rejects_unpinned_rom_bad_address_and_partial_guard(self):
        for kwargs in ({'stock': bytes(256)}, {'camera_model': 'gr2'}, {'base': 0x54170001},
                       {'guard_manifest': {}}, {'enabled': 1}):
            options = dict(base=0x54170000, stock=self.rom, guard_manifest=self.guard_manifest, enabled=True)
            options.update(kwargs)
            with self.assertRaises(ValueError):
                self.builder.build(**options)
        changed = bytearray(self.rom)
        changed[SITE - 0x53000000] ^= 1
        with self.assertRaises(ValueError):
            self.builder.build(0x54170000, bytes(changed), self.guard_manifest, enabled=True)

    def test_builder_admits_both_independently_hash_pinned_models(self):
        fixtures = ROOT / 'builds/gr3-pure-isp-feasibility-20261031'
        if not (fixtures / 'gr3x-official-rtos.bin').exists():
            self.skipTest('exact local GR IIIx RTOS fixture unavailable')
        for model in ('gr3', 'gr3x'):
            rom = (fixtures / (model + '-official-rtos.bin')).read_bytes()
            _, private = guard.build(BASE, rom, border_enabled=True,
                internal_guard_research=True, camera_model=model)
            code, manifest = self.builder.build(0x54170000, rom, private,
                enabled=True, camera_model=model)
            self.assertEqual(manifest['camera_model'], model)
            self.assertEqual(manifest['patches'][0]['expected'], 0xE51B12D4)
            self.assertEqual(code, self.shim)


if __name__ == '__main__':
    unittest.main()
