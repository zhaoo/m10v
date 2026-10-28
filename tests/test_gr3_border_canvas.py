"""Pure post-BackResize descriptor transaction; never maps image storage."""
import ctypes as C
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import struct
import sys
from tests.test_gr3_border import Storage
from tests import test_gr3_border_bank as bank

ROOT=Path(__file__).resolve().parents[1]
class Canvas(C.Structure):
    _fields_=[('inner',bank.Descriptor),('canvas',bank.Descriptor),('layout',Storage)]

class BorderCanvasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
        lib=Path(cls.tmp.name)/'canvas.dylib'
        cls.sources=[ROOT/'native/gr3'/f'{name}.c' for name in
                     ('m10v_border','m10v_border_bank','m10v_border_canvas')]
        subprocess.run([shutil.which('clang'),'-shared','-fPIC','-O2','-Wall','-Wextra','-Werror',
                        *map(str,cls.sources),'-o',str(lib)],check=True,capture_output=True)
        cls.lib=C.CDLL(str(lib));cls.plan=cls.lib.m10v_border_canvas_plan
        cls.plan.argtypes=[C.c_uint32,C.c_uint32,C.POINTER(bank.Descriptor)]+[C.c_uint32]*3+[C.POINTER(Canvas)]
        cls.plan.restype=C.c_int
        cls.bank_plan=cls.lib.m10v_border_bank_plan
        cls.bank_plan.argtypes=[C.c_uint32]*4+[C.POINTER(bank.Descriptors),C.POINTER(bank.BankPlan)]
    def full_bank(self,style=1,orientation=1):
        source=bank.BorderBankTests().images();out=bank.BankPlan()
        self.assertEqual(self.bank_plan(style,orientation,0x60000000,72192000,C.byref(source),C.byref(out)),0)
        return out
    def cropped(self,b,w=6000,h=1656):
        d=bank.Descriptor.from_buffer_copy(b.images[0]);stride=d[5]&65535
        offset=((4000-h)//2)*stride+(6000-w)//2
        d[1]+=offset;d[2]+=offset;d[4]=w|(h<<16)
        return d
    def test_actual_crop_geometry_wraps_inside_original_admitted_planes(self):
        for style in (1,2):
            for orientation in range(1,9):
                b=self.full_bank(style,orientation)
                for w,h in ((6000,4000),(6000,1656),(6000,1104),(4672,4000)):
                    d=self.cropped(b,w,h);before=bytes(d);out=Canvas()
                    self.assertEqual(self.plan(style,orientation,C.byref(d),b.bank,
                        b.bank+b.plane_bytes,b.plane_bytes,C.byref(out)),0,(style,orientation,w,h))
                    self.assertEqual(bytes(d),before)
                    self.assertEqual(out.inner[4],d[4])
                    self.assertEqual(out.inner[5]>>16,h)
                    self.assertEqual(out.canvas[4]&65535,out.layout.outer.width)
                    self.assertEqual(out.canvas[4]>>16,out.layout.outer.height)
                    self.assertEqual(out.canvas[5]>>16,out.layout.allocated_height)
                    offset=out.layout.inner.y*out.layout.stride+out.layout.inner.x
                    for plane in (1,2):
                        self.assertEqual(out.canvas[plane]+offset,d[plane])
                        self.assertEqual(out.canvas[plane]%8,0)
                        start=b.bank+(plane-1)*b.plane_bytes
                        self.assertGreaterEqual(out.canvas[plane],start)
                        self.assertLessEqual(out.canvas[plane]+out.layout.y_bytes,start+b.plane_bytes)
    def test_off_is_exact_and_does_not_require_canvas_capacity(self):
        b=self.full_bank();d=self.cropped(b);out=Canvas()
        self.assertEqual(self.plan(0,1,C.byref(d),0,0,0,C.byref(out)),0)
        self.assertEqual(bytes(out.inner),bytes(d));self.assertEqual(bytes(out.canvas),bytes(d))
        self.assertEqual(out.layout.total_bytes,0)
    def test_original_backresize_result_fits_padded_bank_on_both_models(self):
        sys.path.insert(0,str(ROOT/'scripts'))
        from border_backresize_contract import probe_backresize
        from analyze_gr3_border_iip import validate
        for model in ('gr3','gr3x'):
            rom=(ROOT/f'builds/gr3-border-iip-20261027/{model}-official-rtos.bin').read_bytes()
            validate(rom,model)
            for style,orientation in ((1,1),(1,8),(2,1),(2,6)):
                b=self.full_bank(style,orientation)
                for crop in ((6000,4000),(6000,1656),(4672,4000)):
                    native=probe_backresize(rom,crop,stride=b.canvas.stride,
                              source_planes=(b.source_y,b.source_c))
                    self.assertFalse(native['assertions'])
                    image=native['main_after'];raw=bytearray(32);raw[0]=image['format'];raw[28]=image['layout']
                    struct.pack_into('<3I',raw,4,*image['planes'])
                    struct.pack_into('<6H',raw,16,*image['geometry'])
                    d=bank.Descriptor.from_buffer_copy(raw);out=Canvas()
                    self.assertEqual(self.plan(style,orientation,C.byref(d),b.bank,
                         b.bank+b.plane_bytes,b.plane_bytes,C.byref(out)),0,(model,style,orientation,crop))
                    self.assertEqual(out.inner[5]>>16,crop[1])
                    self.assertEqual(out.canvas[1]%8,0)
    def test_alignment_roi_cache_span_and_bank_fail_without_output_mutation(self):
        b=self.full_bank()
        for failure in ('alignment','roi','short','upper_bank','stride','third','format'):
            d=self.cropped(b);y,c,n=b.bank,b.bank+b.plane_bytes,b.plane_bytes
            if failure=='alignment':d[1]+=4
            elif failure=='roi':d[6]=8
            elif failure=='short':n=1000000
            elif failure=='upper_bank':c=0x90000000
            elif failure=='stride':d[5]=(4000<<16)|6000
            elif failure=='third':d[3]=0x70000000
            else:d[0]=2
            out=Canvas();C.memset(C.byref(out),0xa5,C.sizeof(out));before=bytes(out)
            self.assertEqual(self.plan(1,1,C.byref(d),y,c,n,C.byref(out)),-1)
            self.assertEqual(bytes(out),before)
    def test_arm_module_links_without_cpu_pixel_or_runtime_helpers(self):
        objects=[]
        for source in self.sources:
            obj=Path(self.tmp.name)/(source.stem+'.o');objects.append(str(obj))
            subprocess.run([shutil.which('clang'),'--target=armv7-none-eabi','-mcpu=cortex-a9',
                '-marm','-mfloat-abi=soft','-Os','-ffreestanding','-fno-builtin','-fno-stack-protector',
                '-fno-unwind-tables','-fno-asynchronous-unwind-tables','-c',str(source),'-o',str(obj)],
                check=True,capture_output=True)
        result=subprocess.run([shutil.which('ld.lld'),'-Ttext=0x54160000',
            '--entry=m10v_border_canvas_plan',*objects,'-o',str(Path(self.tmp.name)/'canvas.elf')],
            text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__':unittest.main()
