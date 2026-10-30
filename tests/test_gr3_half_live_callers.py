"""Half live geometry through original mapper/common/FocusModel callers.

Only singleton lookup and publication are doubles. The class mapper and both
rectangle selection paths execute installed r3 ARM plus current source overlay.
"""
import struct
import unittest
from unicorn import UC_HOOK_CODE
from unicorn import arm_const as A
from tests.test_gr3_aspect_full_callers import FullAspectCallers as Support
from tests.test_gr3_aspect_full_callers import RAM, STOP

class HalfLiveCallers(unittest.TestCase):
    setUpClass=classmethod(Support.setUpClass.__func__)
    machine=Support.machine
    device=Support.device
    run_entry=Support.run_entry

    def test_half_mapper_and_both_live_refresh_paths_use_same_native_focal_rectangle(self):
        for mag,q13 in ((0x3f800000,0x2000),(0x3fa00000,0x2800),(0x3fe49249,0x38f6)):
            results=[]
            for path in ('common','focus'):
                with self.subTest(mag=hex(mag),path=path):
                    u,events=self.device(6,mag)
                    u.reg_write(A.UC_ARM_REG_C1_C0_2,0xf00000)
                    u.reg_write(A.UC_ARM_REG_FPEXC,0x40000000)
                    context,owner,root=RAM+0x4000,RAM+0x10000,RAM+0x11000
                    u.mem_write(owner+8,struct.pack('<I',context))
                    u.mem_write(root,struct.pack('<I',RAM+0x300))
                    native=(2949120,1966080,0,0)
                    focal=(1800000,1200000,574560,383040)
                    wide=(2949120,1105920,0,430080)
                    for offset,rect in ((4,native),(0x24,focal),(0x54,wide)):
                        u.mem_write(context+offset,struct.pack('<4I',*rect))
                    returns={0x536659ac:owner,0x53666200:0,0x5366632c:0,
                             0x53525d5c:root,0x5354a778:6,0x53549958:0,
                             0x53654150:RAM+0x12000,0x53654220:0,
                             0x536ae71c:0,0x536ae870:1}
                    def boundary(m,address,size,data):
                        if address==0x5354a7bc:
                            m.reg_write(A.UC_ARM_REG_S0,mag)
                            m.reg_write(A.UC_ARM_REG_PC,m.reg_read(A.UC_ARM_REG_LR))
                        elif address in returns:
                            m.reg_write(A.UC_ARM_REG_R0,returns[address])
                            m.reg_write(A.UC_ARM_REG_PC,m.reg_read(A.UC_ARM_REG_LR))
                    u.hook_add(UC_HOOK_CODE,boundary)
                    # Use the actual original mapper, which stores its result
                    # at destination+4 exactly as FocusModel does before+751.
                    self.run_entry(u,0x53669424,owner+0x74d,1)
                    self.assertEqual(u.reg_read(A.UC_ARM_REG_R0),0)
                    self.assertEqual(bytes(u.mem_read(owner+0x751,1)),b'\0')
                    if path=='common':self.run_entry(u,0x53437170)
                    else:
                        u.mem_write(owner+0x756,b'\0')
                        u.mem_write(owner+0x758,struct.pack('<I',q13))
                        u.mem_write(owner+0xa94,struct.pack('<I',context))
                        u.reg_write(A.UC_ARM_REG_R4,owner)
                        u.emu_start(0x53445054,0x53445088,count=50000)
                        self.assertEqual(u.reg_read(A.UC_ARM_REG_PC),0x53445088)
                    self.assertFalse(events)
                    result=struct.unpack('<4I',u.mem_read(context+0x64,16))
                    self.assertEqual(result,native if q13==0x2000 else focal)
                    results.append(result)
            self.assertEqual(results[0],results[1])
