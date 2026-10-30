"""Host-executed spatial YC422 pairing; this does not establish camera acceptance."""
import ctypes as C
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FIELDS=('width','height','stride','rows','plane_bytes','used_bytes','first_x','first_y','second_x','second_y')
class Plan(C.Structure):
    _fields_=[(name,C.c_uint32) for name in FIELDS]

def aligned_buffer(size,fill=0xa5):
    owner=(C.c_uint8*(size+64))()
    address=(C.addressof(owner)+63)&~63
    C.memset(address,fill,size)
    return owner,address

class HalfPairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source=ROOT/'native/gr3/m10v_half_pair.c'
        assert source.exists(),'spatial pair implementation is missing'
        cls.temp=tempfile.TemporaryDirectory(prefix='m10v-half-pair-')
        library=Path(cls.temp.name)/'pair.so'
        subprocess.run([shutil.which('clang') or 'cc','-std=c99','-Wall','-Wextra','-Werror','-O2','-shared','-fPIC',str(source),'-o',str(library)],check=True)
        cls.lib=C.CDLL(str(library))
        cls.lib.m10v_half_pair_plan.argtypes=[C.c_uint32]*4+[C.POINTER(Plan)]
        cls.lib.m10v_half_pair_plan.restype=C.c_int
        cls.lib.m10v_half_pair_compose.argtypes=[C.POINTER(Plan),C.c_void_p,C.c_void_p,C.c_void_p,C.c_uint32]
        cls.lib.m10v_half_pair_compose.restype=C.c_int
    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()
    def plan(self,w,h,orientation,capacity=73728000):
        p=Plan()
        self.assertEqual(self.lib.m10v_half_pair_plan(w,h,orientation,capacity,C.byref(p)),1)
        return p
    def test_literal_colored_frames_and_black_padding_all_orientations(self):
        # Two 2x2 planes, with distinguishable per-row Y and paired C samples.
        first=(C.c_uint8*8)(20,21,22,23,70,180,71,181)
        second=(C.c_uint8*8)(90,91,92,93,100,130,101,131)
        expectations={1:([20,21,90,91],[22,23,92,93],[70,180,100,130],[71,181,101,131]),
                      3:([90,91,20,21],[92,93,22,23],[100,130,70,180],[101,131,71,181]),
                      6:([90,91],[92,93],[20,21],[22,23]),
                      8:([20,21],[22,23],[90,91],[92,93])}
        for orientation in (1,3,6,8):
            with self.subTest(orientation=orientation):
                p=self.plan(2,2,orientation)
                owner,dest=aligned_buffer(p.used_bytes+64)
                self.assertEqual(self.lib.m10v_half_pair_compose(C.byref(p),first,second,dest,p.used_bytes),1)
                y=C.string_at(dest,p.plane_bytes);c=C.string_at(dest+p.plane_bytes,p.plane_bytes)
                if orientation in (1,3):
                    yr=expectations[orientation][:2];cr=expectations[orientation][2:]
                elif orientation==6:
                    yr=expectations[6];cr=([100,130],[101,131],[70,180],[71,181])
                else:
                    yr=expectations[8];cr=([70,180],[71,181],[100,130],[101,131])
                expected_y=bytearray([16])*p.plane_bytes;expected_c=bytearray([128])*p.plane_bytes
                for row,values in enumerate(yr):expected_y[row*p.stride:row*p.stride+p.width]=bytes(values)
                for row,values in enumerate(cr):expected_c[row*p.stride:row*p.stride+p.width]=bytes(values)
                self.assertEqual(y,expected_y);self.assertEqual(c,expected_c)
                self.assertEqual(C.string_at(dest+p.used_bytes,64),bytes([0xa5])*64)
    def test_default_24mp_plan_fits_bank_and_exact_geometry(self):
        for orientation in (1,3,6,8):
            p=self.plan(2992,4000,orientation)
            self.assertEqual((p.width,p.height),(5984,4000) if orientation in (1,3) else (2992,8000))
            self.assertEqual((p.stride%64,p.rows%16),(0,0))
            self.assertLessEqual(p.used_bytes,73728000)
            self.assertEqual(p.plane_bytes,p.stride*p.rows)
            self.assertEqual(p.used_bytes,p.plane_bytes*2)
    def test_full_camera_frame_copies_both_halves_without_color_change(self):
        w,h=2992,4000;pixels=w*h
        first=(C.c_uint8*(2*pixels))();second=(C.c_uint8*(2*pixels))()
        C.memset(C.addressof(first),20,pixels);C.memset(C.addressof(first)+pixels,80,pixels)
        C.memset(C.addressof(second),90,pixels);C.memset(C.addressof(second)+pixels,140,pixels)
        p=self.plan(w,h,1,74907648);owner,dest=aligned_buffer(p.used_bytes+64)
        self.assertEqual(self.lib.m10v_half_pair_compose(C.byref(p),first,second,dest,74907648),1)
        for row in (0,1,1999,3999):
            at=dest+row*p.stride
            self.assertEqual(C.string_at(at,w),bytes([20])*w)
            self.assertEqual(C.string_at(at+w,w),bytes([90])*w)
            self.assertEqual(C.string_at(at+p.plane_bytes,w),bytes([80])*w)
            self.assertEqual(C.string_at(at+p.plane_bytes+w,w),bytes([140])*w)
            self.assertEqual(C.string_at(at+2*w,p.stride-2*w),bytes([16])*(p.stride-2*w))
        self.assertEqual(C.string_at(dest+p.used_bytes,64),bytes([0xa5])*64)
    def test_invalid_plans_leave_output_unchanged(self):
        for w,h,o,cap in ((0,2,1,9999),(2,0,1,9999),(3,2,1,9999),(2,3,1,9999),(2994,2,1,73728000),(2,4002,1,73728000),(0xfffffffe,2,1,0xffffffff),(2,0xfffffffe,6,0xffffffff),(2,2,2,9999),(2,2,0,9999),(2,2,1,2047)):
            p=Plan(*([0x12345678]*10));before=bytes(p)
            self.assertEqual(self.lib.m10v_half_pair_plan(w,h,o,cap,C.byref(p)),0)
            self.assertEqual(bytes(p),before)
        self.assertEqual(self.lib.m10v_half_pair_plan(2,2,1,9999,None),0)
    def test_invalid_compose_never_writes_destination(self):
        p=self.plan(2,2,1);a=(C.c_uint8*8)(*range(8));b=(C.c_uint8*8)(*range(8,16))
        owner,d=aligned_buffer(4096);before=C.string_at(d,4096)
        for first,second,dest,cap,plan in ((None,b,d,4096,C.byref(p)),(a,None,d,4096,C.byref(p)),(a,b,None,4096,C.byref(p)),(a,b,d,p.used_bytes-1,C.byref(p)),(a,b,d+1,4095,C.byref(p)),(a,b,d,4096,None),(d,b,d,4096,C.byref(p)),(a,d+64,d,4096,C.byref(p)),(a,a,d,4096,C.byref(p)),(C.addressof(a),C.addressof(a)+4,d,4096,C.byref(p)),(C.c_void_p(-4),b,d,4096,C.byref(p))):
            self.assertEqual(self.lib.m10v_half_pair_compose(plan,first,second,dest,cap),0)
            self.assertEqual(C.string_at(d,4096),before)
        for name in FIELDS:
            broken=Plan.from_buffer_copy(p)
            setattr(broken,name,getattr(broken,name)+1)
            self.assertEqual(self.lib.m10v_half_pair_compose(C.byref(broken),a,b,d,4096),0,name)
            self.assertEqual(C.string_at(d,4096),before)

if __name__=='__main__':unittest.main()
