"""Stateless custom-crop contracts; no firmware install or device claims."""
import struct
import ctypes as C
import subprocess
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class Geometry(C.Structure):
    _fields_=[(n,C.c_uint32) for n in ('x','y','width','height','output_width','output_height')]
class ZoomCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        lib=Path(cls.tmp.name)/'zoom.dylib'
        stub=Path(cls.tmp.name)/'stubs.c'
        stub.write_text('''#include <stdint.h>
uint32_t m10v_zoom_mm(uint32_t b) { for(unsigned mm=28;mm<=100;mm++){union {float f;uint32_t u;} v;v.f=(float)mm/28.0f;if(v.u==b)return mm;}return 0; }
uint32_t m10v_zoom_caption(uint32_t b) {return 900+m10v_zoom_mm(b);}
void m10v_zoom_capture_native_resolution(uint32_t b,uint32_t q,uint32_t r,uint16_t *w,uint16_t *h) {
 (void)b;(void)q;*w=r==6?2992:6000;*h=4000;
}
'''+'\n'.join('uint32_t '+n+'(void){return 0;}' for n in [
'm10v_zoom_bits','m10v_zoom_original_marker_write','m10v_zoom_original_marker_read','m10v_zoom_original_marker_summary','m10v_zoom_original_raw_count','m10v_zoom_original_raw_value','m10v_zoom_capture_raw_bits','m10v_zoom_native_ifd_byte','m10v_zoom_native_ifd_write_byte','m10v_zoom_native_summary_write','m10v_zoom_original_replay_rect']))
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-std=c99',str(ROOT/'native/gr3/m10v_zoom_capture.c'),str(ROOT/'native/gr3/m10v_zoom_capture_adapters.c'),str(stub),'-o',str(lib)],check=True,capture_output=True)
        cls.lib=C.CDLL(str(lib))
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_display_delegate_sentinel_and_invalid_float_rejection(self):
        self.lib.m10v_zoom_capture_caption.restype=C.c_uint32
        for mm in (28,35,50):
            bits=struct.unpack('<I',struct.pack('<f',mm/28))[0]
            self.assertEqual(self.lib.m10v_zoom_capture_caption(bits),0xffffffff)
            self.assertEqual(self.lib.m10v_zoom_capture_custom(bits),0)
        for mm in (30,36,41,49,100):
            bits=struct.unpack('<I',struct.pack('<f',mm/28))[0]
            self.assertEqual(self.lib.m10v_zoom_capture_caption(bits),900+mm)
        for bits in (0,0x3fbae148,0x7fc00000,0x7f800000,0xbf800000):
            self.assertEqual(self.lib.m10v_zoom_capture_caption(bits),0)
            self.assertEqual(self.lib.m10v_zoom_capture_custom(bits),1)
    def test_custom_marker_roundtrip_all_integer_focals_and_no_global_settings(self):
        for mm in range(28,101):
            marker=(C.c_uint8*3)(9,9,9)
            rc=self.lib.m10v_zoom_capture_marker_encode(mm,marker)
            self.assertEqual(rc,0 if mm in (28,35,50) else 1)
            if rc:
                self.assertEqual(list(marker),[0,0x80|(mm-28),1])
                self.assertEqual(self.lib.m10v_zoom_capture_marker_decode(marker),mm)
            else:self.assertEqual(list(marker),[9,9,9])
    def test_old_unknown_and_corrupt_markers_fall_through(self):
        for b in ([0,0,0],[0,5,0],[0,6,0],[0,128,1],[0,135,1],[0,150,1],[0,201,1],[0,130,0],[1,130,1],[0,130,2]):
            self.assertEqual(self.lib.m10v_zoom_capture_marker_decode((C.c_uint8*3)(*b)),0)
    def test_source_crop_and_downsampled_output_are_separate(self):
        g=Geometry()
        self.assertEqual(self.lib.m10v_zoom_capture_geometry(30,6000,4000,1920,1280,C.byref(g)),1)
        self.assertEqual((g.width,g.height),(5600,3728))
        self.assertEqual((g.x,g.y),(200,136))
        self.assertEqual((g.output_width,g.output_height),(1920,1280))
    def test_half_frame_custom_crop_accepts_identity_six_and_rejects_unknown(self):
        bits=struct.unpack('<I',struct.pack('<f',41/28))[0]
        w,h=C.c_uint16(0xa5a5),C.c_uint16(0xa5a5)
        self.assertEqual(self.lib.m10v_zoom_capture_resolution(bits,0,6,C.byref(w),C.byref(h)),1)
        self.assertEqual((w.value,h.value),(2032,2720))
        self.assertEqual(self.lib.m10v_zoom_capture_resolution(bits,0,7,C.byref(w),C.byref(h)),0)
        self.assertEqual((w.value,h.value),(2032,2720))
    def test_all_custom_focals_and_supported_aspect_baselines_stay_centered_and_bounded(self):
        for mm in range(29,101):
            if mm in (35,50):continue
            for w,h in ((6000,4000),(4000,4000),(5328,4000),(6000,2208),(4672,4000)):
                g=Geometry()
                self.assertEqual(self.lib.m10v_zoom_capture_geometry(mm,w,h,w,h,C.byref(g)),1)
                self.assertEqual((2*g.x+g.width,2*g.y+g.height),(6000,4000))
                self.assertEqual((g.width%16,g.height%16),(0,0))
                self.assertLessEqual(g.width*mm,w*28)
                self.assertLessEqual(g.height*mm,h*28)
                self.assertEqual((g.output_width,g.output_height),(g.width,g.height))
    def test_invalid_and_defaults_leave_geometry_untouched(self):
        for mm in (0,27,28,35,50,101,0xffffffff):
            g=Geometry(*([0xaabbccdd]*6))
            self.assertEqual(self.lib.m10v_zoom_capture_geometry(mm,6000,4000,6000,4000,C.byref(g)),0)
            self.assertEqual(list(bytes(g)),list(bytes(Geometry(*([0xaabbccdd]*6)))))
    def test_raw_development_quality_values_are_monotonic_and_bounded(self):
        for mm in (30,36,49,51,100):
            first=0 if mm<35 else 1 if mm<50 else 2
            self.assertEqual(self.lib.m10v_zoom_capture_quality_count(mm),4-first)
            for i in range(4-first):self.assertEqual(self.lib.m10v_zoom_capture_quality_value(mm,i),first+i)
            self.assertEqual(self.lib.m10v_zoom_capture_quality_value(mm,4-first),-1)
        for mm in (28,35,50,101):self.assertEqual(self.lib.m10v_zoom_capture_quality_count(mm),0)
if __name__=='__main__':unittest.main()
