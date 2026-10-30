"""Original class mapper -> real viewport/backend dimension publisher.

The fifth width/height argument is native CLASS, not the stored ratio. This
executes the installed candidate's helper hooks rather than inventing raw6
as a geometry argument. These are metadata checks, not display hardware proof.
"""
import os
from pathlib import Path
import struct
import unittest
from unicorn import UC_PROT_ALL
from scripts.analyze_gr3_border_iip import OriginalArm

ORIGINAL=Path('builds/gr3-extension-validation/official-rtos.bin')
CANDIDATE=Path(os.environ.get('M10V_VIEWPORT_RTOS','builds/gr3-half-frame-r5-debug-final-20261030/final-rtos.bin'))
OWNER,PROFILE,ROOT,MODEL=0x55200000,0x55210000,0x55220000,0x55230000


def fixture(candidate=False,raw=0,scanmode=0,kind=0,override=0):
    rom=ORIGINAL.read_bytes();p=OriginalArm(rom)
    if candidate:
        installed=CANDIDATE.read_bytes()
        old=(len(rom)+4095)&~4095;new=(len(installed)+4095)&~4095
        if new>old:p.u.mem_map(0x53000000+old,new-old)
        p.u.mem_protect(0x53000000,old,UC_PROT_ALL)
        p.u.mem_write(0x53000000,installed)
    p.words(OWNER+0xa0,PROFILE);p.words(ROOT,MODEL)
    p.u.mem_write(PROFILE+5,bytes([scanmode,0]))
    p.u.mem_write(MODEL+0x6c2,b'\1')
    p.boundaries={0x53525d5c:lambda:ROOT,0x5354a778:lambda:raw,
                  0x53549958:lambda:kind,0x53654150:lambda:MODEL,0x53654220:lambda:override}
    return p


def publish(p):
    A=p.A
    for reg,value in ((A.UC_ARM_REG_R4,OWNER),(A.UC_ARM_REG_R3,PROFILE),
                      (A.UC_ARM_REG_R5,0),(A.UC_ARM_REG_SP,0x55ffe000)):
        p.u.reg_write(reg,value)
    p.u.emu_start(0x53456a7c,0x53456b10,count=500000)
    if p.u.reg_read(A.UC_ARM_REG_PC)!=0x53456b10:raise AssertionError('publisher did not reach rejoin')
    viewport=struct.unpack('<2H',p.u.mem_read(OWNER+0x54a,4))
    backend=struct.unpack('<2H',p.u.mem_read(OWNER+0x558,4))
    return viewport,backend


class LiveViewportCallers(unittest.TestCase):
    def test_real_mapper_and_publisher_use_full_backing_for_masked_wide_and_half(self):
        for raw,klass in ((0,0),(2,0),(6,0)):
            for scanmode in range(4):
                with self.subTest(raw=raw,scanmode=scanmode):
                    p=fixture(True,raw,scanmode)
                    # Execute actual installed class mapper; byte4 is what the
                    # actual publisher later loads as its fifth argument.
                    self.assertEqual(p.call(0x53669424,PROFILE,1),klass)
                    self.assertEqual(bytes(p.u.mem_read(PROFILE+4,1)),bytes([klass]))
                    actual=publish(p)
                    reference=fixture(False,0,scanmode)
                    reference.u.mem_write(PROFILE+4,bytes([klass]))
                    self.assertEqual(actual,publish(reference))
                    for shape in actual:
                        self.assertTrue(all(0<value<=4096 and not(value&1) for value in shape))
                    if raw in(2,6):self.assertEqual(actual[0],actual[1])
                    if raw==2:self.assertEqual(actual[0][0],actual[1][0])
                    self.assertFalse(p.assertions)
                    self.assertFalse(reference.assertions)

    def test_normal_live_wide_compatibility_publisher_uses_full_native_backing(self):
        p=fixture(True,2,0);p.call(0x53669424,PROFILE,1)
        self.assertEqual(publish(p),((640,424),(640,424)))

    def test_movie_and_forced_aspect_keep_native_wide_class_and_storage(self):
        for kind,override in ((1,0),(0,1),(1,1)):
            for scanmode in range(4):
                with self.subTest(kind=kind,override=override,scanmode=scanmode):
                    p=fixture(True,2,scanmode,kind,override)
                    r=fixture(False,2,scanmode,kind,override)
                    self.assertEqual(p.call(0x53669424,PROFILE,1),1)
                    self.assertEqual(r.call(0x53669424,PROFILE,1),1)
                    self.assertEqual(publish(p),publish(r))
                    self.assertFalse(p.assertions);self.assertFalse(r.assertions)
