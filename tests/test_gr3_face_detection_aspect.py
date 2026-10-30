"""Face config classes through actual original FocusModel -> FaceDetectionService.

The r3 argument at 53450368 is the FocusModel class, not the stored ratio.
The unsupported private 4:3 service case is characterized, not hidden.
"""
from pathlib import Path
import struct
import unittest
from unicorn import UC_PROT_ALL
from scripts.analyze_gr3_border_iip import OriginalArm
from scripts.gr3_aspect_overlay import build_module, MODULE, branch

ROM=Path('builds/gr3-extension-validation/official-rtos.bin')
OWNER,PROFILE,VECTOR,SERVICE=0x55200000,0x55210000,0x55220000,0x55230000


def fixture(source=False):
    rom=ROM.read_bytes();p=OriginalArm(rom)
    if source:
        code,symbols=build_module()
        end=0x53000000+((len(rom)+4095)&~4095)
        need=MODULE+((len(code)+4095)&~4095)
        if need>end:p.u.mem_map(end,need-end)
        p.u.mem_write(MODULE,code)
        p.u.mem_protect(0x53000000,((len(rom)+4095)&~4095),UC_PROT_ALL)
        p.words(0x53450368,branch(0x53450368,symbols['m10v_aspect_face_config']))
        # The unchanged GRLife continuation publishes the native prologue.
        p.words(0x540b9144,0x03a03000,0xe1a0c00d,branch(0x540b914c,0x5345036c))
    p.words(OWNER+4,VECTOR,VECTOR,VECTOR,VECTOR,VECTOR,VECTOR)
    p.words(VECTOR+0x128,0x68000000)
    p.words(OWNER+0x9c8,720*4096,480*4096)
    p.words(OWNER+0x266c,4096)
    for off,val in ((0xa6,720),(0xa8,480),(0xaa,720),(0xc4,720),(0xc6,480),(0xcc,720),(0xce,480)):
        p.u.mem_write(PROFILE+off,struct.pack('<H',val))
    # Publish/face-history services are boundaries; config construction,
    # division, source descriptor and service output arithmetic run original.
    p.boundaries={0x53666a24:lambda:0,0x53648fbc:lambda:1}
    p.words(SERVICE+0x34,VECTOR)
    return p


def run(p,klass):
    p.call(0x53450368,OWNER,PROFILE,0,klass,0,8192,0,720,480)
    face=p.u.mem_read(OWNER+0x42f6,1)[0]
    p.call(0x5365761c,SERVICE,OWNER+0x42e8)
    return face


class FaceDetectionAspectTests(unittest.TestCase):
    def test_original_four_by_three_class_reproduces_exact_r4_device_assert(self):
        p=fixture()
        self.assertEqual(run(p,2),1)
        self.assertEqual(p.assertions,[{'caller':0x53657708,'line':1047}])

    def test_actual_wide_and_half_classes_use_supported_native_face_geometry(self):
        for klass,face in ((0,0),(1,2),(3,0)):
            with self.subTest(klass=klass):
                p=fixture(True)
                self.assertEqual(run(p,klass),face)
                self.assertFalse(p.assertions)

    def test_source_four_by_three_case_remains_visible_without_speculative_policy_change(self):
        p=fixture(True)
        self.assertEqual(run(p,2),1)
        self.assertEqual(p.assertions,[{'caller':0x53657708,'line':1047}])
