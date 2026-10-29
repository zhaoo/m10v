"""The camera diagnostic must reach the separately built trace modules."""
import tempfile
import unittest
import struct
from pathlib import Path
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM
from unicorn import arm_const as A

from scripts.build_gr3_save_trace import build as build_save
from scripts.build_gr3_module_dispatch_trace import build as build_module

ROOT = Path(__file__).resolve().parents[1]


class BorderDebugCompileTests(unittest.TestCase):
    def test_both_trace_components_compile_border_diagnostics(self):
        rom = ROOT / 'builds/gr3-extension-validation/official-rtos.bin'
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            plain, plain_manifest = build_save(root / 'plain-save', 0x540e0000, rtos=rom)
            active, active_manifest = build_save(root / 'border-save', 0x540e0000,
                                                 rtos=rom, border_debug=True)
            self.assertFalse(plain_manifest['border_debug'])
            self.assertTrue(active_manifest['border_debug'])
            self.assertNotEqual(plain, active)
            u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
            u.mem_map(0x540e0000, 0x2000)
            u.mem_write(0x540e0000, active)
            u.mem_map(0x55000000, 0x20000)
            u.mem_map(0x60000000, 0x1000)
            trace = 0x55001000
            u.mem_write(trace, struct.pack('<I', 0x31545653))
            for tag, stage, reason in ((0x4d313030, 1, 0x11801950),
                                       (0x424f5244, 3, 6),
                                       (0x4d313030, 2, 0x0fa01770)):
                stack = 0x5501f000
                u.mem_write(stack, struct.pack('<2I', stage, reason))
                for register, value in zip((A.UC_ARM_REG_R0, A.UC_ARM_REG_R1,
                                            A.UC_ARM_REG_R2, A.UC_ARM_REG_R3),
                                           (trace, 197, 0x55002000, tag)):
                    u.reg_write(register, value)
                u.reg_write(A.UC_ARM_REG_SP, stack)
                u.reg_write(A.UC_ARM_REG_LR, 0x60000000)
                u.emu_start(active_manifest['exports']['m10v_save_trace_append'],
                            0x60000000, count=10000)
                self.assertEqual(u.reg_read(A.UC_ARM_REG_PC), 0x60000000)
            self.assertEqual(struct.unpack('<5I', u.mem_read(trace + 16 + 31 * 20, 20)),
                             (197, 0x55002000, 0x424f5244, 3, 6))

            kwargs = dict(rtos=rom, take=active_manifest['exports']['m10v_save_trace_recipe_take'],
                          batch=0x540c0000)
            plain, plain_manifest = build_module(root / 'plain-module', 0x540f0000,
                                                 active_manifest['exports']['m10v_save_trace_recipe_mark'],
                                                 **kwargs)
            active, active_manifest = build_module(root / 'border-module', 0x540f0000,
                                                   active_manifest['exports']['m10v_save_trace_recipe_mark'],
                                                   border_debug=True, **kwargs)
            self.assertFalse(plain_manifest['border_debug'])
            self.assertTrue(active_manifest['border_debug'])
            self.assertNotEqual(plain, active)


if __name__ == '__main__':
    unittest.main()
