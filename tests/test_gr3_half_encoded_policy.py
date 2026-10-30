"""Execute the encoded-only adapter, preserving exposure metadata and ABI.

The larger policy is admitted ONLY at the two bank-capacity/quality callsites;
this test does not replace actual sensor-resolution or crop tests.
"""
import struct
import unittest
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm_const as A
from scripts.gr3_aspect_overlay import build_module, MODULE


class HalfEncodedPolicyTests(unittest.TestCase):
    def test_adapter_preserves_original_resolution_arguments_except_half_identity(self):
        for enabled in (False, True):
            code, symbols = build_module(enabled)
            for raw in range(8):
                with self.subTest(enabled=enabled, raw=raw):
                    u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
                    u.mem_map(MODULE, (len(code)+4095)&~4095)
                    u.mem_write(MODULE, code)
                    u.mem_map(0x536a2000, 4096)
                    u.mem_map(0x55000000, 4096)
                    args = [0x55000100, 2, raw, 0x55000200]
                    for i,v in enumerate(args):u.reg_write(getattr(A,f'UC_ARM_REG_R{i}'),v)
                    u.reg_write(A.UC_ARM_REG_SP,0x55000800)
                    u.mem_write(0x55000800, struct.pack('<I',0x55000202))
                    u.reg_write(A.UC_ARM_REG_LR,0x55000ff0)
                    seen=[]
                    def native(machine, address, size, _):
                        if address==0x536a2a30:
                            seen.append([machine.reg_read(getattr(A,f'UC_ARM_REG_R{i}')) for i in range(4)])
                            self.assertEqual(bytes(machine.mem_read(0x55000800,4)),struct.pack('<I',0x55000202))
                            machine.reg_write(A.UC_ARM_REG_R0,0x12345678)
                            machine.reg_write(A.UC_ARM_REG_PC,machine.reg_read(A.UC_ARM_REG_LR))
                    u.hook_add(UC_HOOK_CODE,native)
                    u.emu_start(symbols['m10v_aspect_encoded_resolution'],0x55000ff0,count=100)
                    self.assertEqual(seen, [[args[0],args[1],0 if enabled and raw==6 else raw,args[3]]])
                    self.assertEqual(u.reg_read(A.UC_ARM_REG_R0),0x12345678)
