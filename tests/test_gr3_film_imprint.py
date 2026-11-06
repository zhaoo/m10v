"""Imprint journal contracts execute the real codec with its unchanged ABI."""
import ctypes as C
import struct
import subprocess
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAG = 0x46580000
class Settings(C.Structure):
    _fields_ = [(n, C.c_uint32) for n in ('leak_gain','leak_position','leak_spread',
        'grain_mode','grain_size','blur_gain','blur_range','reserved')]
class Snapshot(C.Structure):
    _fields_ = [('settings', Settings), ('grain', C.c_uint32)]

class ImprintCodecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        so = Path(cls.tmp.name)/'codec.dylib'
        subprocess.run(['clang','-shared','-fPIC','-DM10V_PURE_ISP_EFFECTS=1',
            str(ROOT/'native/gr3/m10v_isp_effects_state.c'),'-o',str(so)],check=True)
        cls.lib=C.CDLL(str(so))
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()
    def encode(self,s):
        b=C.create_string_buffer(48)
        self.assertEqual(self.lib.m10v_isp_effects_encode(C.byref(s),7,b,48),1)
        return b.raw
    def test_all_five_styles_roundtrip_in_v3_without_abi_growth(self):
        self.assertEqual(C.sizeof(Settings),32)
        for style in range(1,8):
            s=Settings(1,0,1,2,0,2,1,TAG|(style<<7)|66)
            b=self.encode(s)
            self.assertEqual(struct.unpack_from('<I',b,4)[0],3)
            out=Settings();seq=C.c_uint32()
            self.assertEqual(self.lib.m10v_isp_effects_decode(b,48,C.byref(out),C.byref(seq)),1)
            self.assertEqual((bytes(out),seq.value),(bytes(s),7))
    def test_v1_v2_bytes_unchanged_and_old_versions_reject_imprint_bits(self):
        for prefs,version in ((0,1),(TAG|66,2)):
            s=Settings(1,0,1,2,0,2,1,prefs)
            raw=struct.pack('<11I',0x31505349,version,7,1,0,1,2,0,2,1,prefs)
            self.assertEqual(self.encode(s),raw+struct.pack('<I',zlib.crc32(raw)))
        raw=struct.pack('<11I',0x31505349,2,7,0,0,0,0,0,0,0,TAG|128)
        out=Settings();seq=C.c_uint32(9)
        self.assertEqual(self.lib.m10v_isp_effects_decode(raw+struct.pack('<I',zlib.crc32(raw)),48,C.byref(out),C.byref(seq)),0)
        self.assertEqual(seq.value,9)
    def test_invalid_styles_and_unused_bits_reject(self):
        for word in (TAG|1024,TAG|2048,128,TAG|0x80000000):
            self.assertEqual(self.lib.m10v_isp_effects_validate(C.byref(Settings(reserved=word))),0)
    def test_strength_changes_and_toggles_preserve_selected_imprint(self):
        s=Settings(reserved=TAG|(5<<7)|66)
        for kind in range(3):
            self.assertEqual(self.lib.m10v_isp_effects_set_strength(C.byref(s),kind,3),1)
            self.assertEqual((s.reserved>>7)&7,5)
            for enabled in (0,1):
                self.assertEqual(self.lib.m10v_isp_effects_set_enabled(C.byref(s),kind,enabled),1)
                self.assertEqual((s.reserved>>7)&7,5)
    def test_snapshot_retains_imprint_and_strips_only_ui_strength_memory(self):
        for style in range(1,8):
            s=Settings(reserved=TAG|(style<<7)|66);out=Snapshot()
            self.assertEqual(self.lib.m10v_isp_effects_resolve_snapshot(C.byref(s),0,C.byref(out)),1)
            self.assertEqual(out.settings.reserved,TAG|(style<<7))
    def test_v3_without_imprint_is_noncanonical_and_rejected(self):
        raw=struct.pack('<11I',0x31505349,3,7,0,0,0,0,0,0,0,TAG|66)
        out=Settings();seq=C.c_uint32()
        self.assertEqual(self.lib.m10v_isp_effects_decode(raw+struct.pack('<I',zlib.crc32(raw)),48,C.byref(out),C.byref(seq)),0)

if __name__=='__main__':unittest.main()
