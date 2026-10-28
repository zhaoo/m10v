"""Bounded border rectangles: full padding initialized, inner photo untouched."""
import ctypes as C
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from tests import test_gr3_border_bank as bank
from tests import test_gr3_border_canvas as canvas

ROOT=Path(__file__).resolve().parents[1]
MAX=132
class Rectangle(C.Structure):
    _fields_=[('destination',C.c_uint32)]+[(n,C.c_uint16) for n in ('y','cb','cr','reserved')]
class FillPlan(C.Structure):
    _fields_=[(n,C.c_uint32) for n in ('tag','count','bytes')]+[
              ('rectangles',Rectangle*MAX),('descriptors',bank.Descriptor*MAX)]

class BorderFillPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
        cls.sources=[ROOT/'native/gr3'/f'{name}.c' for name in
            ('m10v_border','m10v_border_bank','m10v_border_canvas','m10v_border_fill_plan')]
        lib=Path(cls.tmp.name)/'fill.dylib'
        subprocess.run([shutil.which('clang'),'-shared','-fPIC','-O2','-Wall','-Wextra','-Werror',
                        *map(str,cls.sources),'-o',str(lib)],check=True,capture_output=True)
        cls.lib=C.CDLL(str(lib));cls.plan=cls.lib.m10v_border_fill_plan
        cls.plan.argtypes=[C.POINTER(canvas.Canvas),C.c_uint32,C.POINTER(FillPlan)];cls.plan.restype=C.c_int
        cls.bank_plan=cls.lib.m10v_border_bank_plan
        cls.bank_plan.argtypes=[C.c_uint32]*4+[C.POINTER(bank.Descriptors),C.POINTER(bank.BankPlan)]
        cls.canvas_plan=cls.lib.m10v_border_canvas_plan
        cls.canvas_plan.argtypes=[C.c_uint32,C.c_uint32,C.POINTER(bank.Descriptor)]+[C.c_uint32]*3+[C.POINTER(canvas.Canvas)]
    def make(self,style=1,orientation=1,w=6000,h=4000):
        b=bank.BankPlan();images=bank.BorderBankTests().images()
        self.assertEqual(self.bank_plan(style,orientation,0x60000000,72192000,C.byref(images),C.byref(b)),0)
        d=bank.Descriptor.from_buffer_copy(b.images[0]);stride=d[5]&65535
        offset=((4000-h)//2)*stride+(6000-w)//2
        d[1]+=offset;d[2]+=offset;d[4]=w|(h<<16)
        result=canvas.Canvas()
        self.assertEqual(self.canvas_plan(style,orientation,C.byref(d),b.bank,b.bank+b.plane_bytes,
                         b.plane_bytes,C.byref(result)),0)
        return result
    def test_single_bundle_covers_borders_and_padding_without_touching_inner(self):
        for style in (1,2):
            for orientation in range(1,9):
                for w,h in ((6000,4000),(6000,1656),(4672,4000)):
                    c=self.make(style,orientation,w,h);before=bytes(c);out=FillPlan();base=0x55020000
                    self.assertEqual(self.plan(C.byref(c),base,C.byref(out)),1)
                    self.assertEqual(bytes(c),before)
                    self.assertEqual(out.tag,0x42464231);self.assertEqual(out.bytes,12+12*out.count)
                    holes=sum(b.count for b in c.layout.holes)
                    bars=out.count-holes
                    self.assertGreaterEqual(bars,4)
                    self.assertLessEqual(out.count,MAX)
                    area=0;inner=c.layout.inner
                    for i in range(out.count):
                        r=out.rectangles[i];d=out.descriptors[i]
                        self.assertEqual(r.destination,base+FillPlan.descriptors.offset+i*32)
                        self.assertEqual((r.cb,r.cr,r.reserved),(128,128,0))
                        self.assertEqual(r.y,(255 if style==1 else 0) if i<bars else 224)
                        self.assertEqual((d[1],d[2]),(c.canvas[1],c.canvas[2]))
                        self.assertEqual(d[5],c.canvas[5])
                        x,y=d[6]&65535,d[6]>>16;rw,rh=d[4]&65535,d[4]>>16
                        self.assertGreater(min(rw,rh),0)
                        self.assertLess(rw*rh,0x100000,'avoid native split/assert branch')
                        self.assertLessEqual(x+rw,c.layout.stride)
                        self.assertLessEqual(y+rh,c.layout.allocated_height)
                        self.assertTrue(x+rw<=inner.x or x>=inner.x+inner.width or
                                        y+rh<=inner.y or y>=inner.y+inner.height)
                        if i<bars:area+=rw*rh
                    self.assertEqual(area,c.layout.stride*c.layout.allocated_height-inner.width*inner.height)
    def test_invalid_geometry_cannot_clobber_metadata_or_photo_owner(self):
        for fail in ('inner','hole','count','alias','alignment','format','rows'):
            c=self.make(2);base=0x55020000
            if fail=='inner':c.inner[1]+=8
            elif fail=='hole':
                c.layout.holes[0].first.x=c.layout.inner.x;c.layout.holes[0].first.y=c.layout.inner.y
            elif fail=='count':c.layout.holes[0].count=65
            elif fail=='alias':base=c.canvas[1]
            elif fail=='alignment':base+=2
            elif fail=='format':c.canvas[0]=2
            else:c.canvas[5]+=1<<16
            out=FillPlan();C.memset(C.byref(out),0xa5,C.sizeof(out));before=bytes(out)
            self.assertEqual(self.plan(C.byref(c),base,C.byref(out)),-1,fail)
            self.assertEqual(bytes(out),before)
    def test_off_has_no_bundle_and_needs_no_output_or_pixel_geometry(self):
        c=canvas.Canvas();c.layout.style=0
        self.assertEqual(self.plan(C.byref(c),0,None),0)
    def test_freestanding_arm_has_no_pixel_or_runtime_helpers(self):
        objects=[]
        for source in self.sources:
            obj=Path(self.tmp.name)/(source.stem+'.o');objects.append(str(obj))
            subprocess.run([shutil.which('clang'),'--target=armv7-none-eabi','-mcpu=cortex-a9','-marm',
                '-mfloat-abi=soft','-Os','-ffreestanding','-fno-builtin','-fno-stack-protector',
                '-fno-unwind-tables','-fno-asynchronous-unwind-tables','-c',str(source),'-o',str(obj)],
                check=True,capture_output=True)
        p=subprocess.run([shutil.which('ld.lld'),'-Ttext=0x54160000','--entry=m10v_border_fill_plan',
                          *objects,'-o',str(Path(self.tmp.name)/'fill.elf')],text=True,capture_output=True)
        self.assertEqual(p.returncode,0,p.stderr)

if __name__=='__main__':unittest.main()
