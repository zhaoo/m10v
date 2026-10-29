"""Plan only: preserve native bank ownership without allocating pixel planes."""
import ctypes as C
import shutil
import struct
import subprocess
import tempfile
import unittest
import sys
from pathlib import Path
from tests.test_gr3_border import Storage

ROOT=Path(__file__).resolve().parents[1]
Descriptor=C.c_uint32*8
Descriptors=Descriptor*5


class BankPlan(C.Structure):
    _fields_=[('images',Descriptors),('canvas',Storage)]+[(n,C.c_uint32) for n in
                ('bank','capacity','source_y','source_c','plane_bytes','preview_base','used_bytes')]


class BorderBankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
        lib=Path(cls.tmp.name)/'bank.dylib'
        subprocess.run([shutil.which('clang'),'-shared','-fPIC','-O2','-Wall','-Wextra','-Werror',
                        str(ROOT/'native/gr3/m10v_border.c'),str(ROOT/'native/gr3/m10v_border_bank.c'),
                        '-o',str(lib)],check=True,capture_output=True)
        cls.lib=C.CDLL(str(lib));cls.plan=cls.lib.m10v_border_bank_plan
        cls.plan.argtypes=[C.c_uint32]*4+[C.POINTER(Descriptors),C.POINTER(BankPlan)]
        cls.plan.restype=C.c_int

    def images(self,width=6000,height=4000,stride=6016):
        # Independent shape fixture, no image storage is mapped/allocated.
        images=Descriptors()
        def desc(i,w,h,s,y,c):
            raw=bytearray(32);raw[0]=1;raw[28]=2
            struct.pack_into('<3I',raw,4,y,c,0);struct.pack_into('<6H',raw,16,w,h,s,h,0,0)
            C.memmove(C.byref(images[i]),bytes(raw),32)
        bank=0x60000000
        desc(0,width,height,stride,bank+144*stride,bank+(height+288)*stride)
        desc(2,width,height,stride,bank,bank+(height+144)*stride)
        small=bank+(2*height+432)*stride
        desc(1,720,480,720,small+48*stride,small+48*stride+720*480+48*stride)
        desc(3,720,480,720,small,small+720*480+48*stride)
        thumb=small+2*(720*480+96*stride)
        desc(4,160,120,160,thumb,thumb+160*120)
        return images

    def test_full_resolution_padding_and_previews_fit_unchanged_native_capacity(self):
        for style in (1,2):
            for exif in range(1,9):
                images=self.images();before=bytes(images);out=BankPlan()
                self.assertEqual(self.plan(style,exif,0x60000000,72192000,C.byref(images),C.byref(out)),0)
                self.assertEqual(bytes(images),before)
                self.assertEqual(out.capacity,72192000)
                self.assertLessEqual(out.used_bytes,out.capacity)
                for i in (0,2):
                    self.assertEqual((out.images[i][4]&65535,out.images[i][4]>>16),(6000,4000))
                self.assertEqual(out.images[0][1],out.source_y)
                self.assertEqual(out.images[0][2],out.source_c)
                for plane in (1,2):
                    self.assertEqual(out.images[0][plane]-out.images[2][plane],144*out.canvas.stride)
                self.assertGreaterEqual(out.source_y-out.bank,144*out.canvas.stride)
                self.assertGreaterEqual(out.source_c-out.source_y,out.plane_bytes)
                for i in (1,3,4):
                    self.assertEqual(bytes(out.images[i])[16:],bytes(images[i])[16:])
                for i,j in ((1,3),(3,4)):
                    self.assertEqual(out.images[i][1]-out.images[j][1],images[i][1]-images[j][1])
                repeated=BankPlan()
                self.assertEqual(self.plan(style,exif,out.bank,out.capacity,C.byref(out.images),C.byref(repeated)),0)
                self.assertEqual(bytes(repeated),bytes(out),'metadata plan must be idempotent across native iterations')

    def test_off_preserves_all_original_descriptor_bytes(self):
        images=self.images();out=BankPlan()
        self.assertEqual(self.plan(0,1,0x60000000,72192000,C.byref(images),C.byref(out)),0)
        self.assertEqual(bytes(out.images),bytes(images))
        self.assertEqual(out.used_bytes,0)

    def test_original_constructor_and_bank_setter_feed_both_models(self):
        sys.path.insert(0,str(ROOT/'scripts'))
        from border_yuv_bank_contract import setup, RECIPE, BANK_BASE
        from analyze_gr3_border_iip import validate
        for model in ('gr3','gr3x'):
            rom=(ROOT/f'builds/gr3-border-iip-20261027/{model}-official-rtos.bin').read_bytes()
            validate(rom,model)
            p=setup(rom);a=p.A
            for reg,value in ((4,RECIPE),(5,0),(6,RECIPE+0x104),(7,RECIPE+0x100),
                              (0,RECIPE+0x108),(9,0x106),(10,0x102)):
                p.u.reg_write(getattr(a,f'UC_ARM_REG_R{reg}'),value)
            p.u.emu_start(0x5350f210,0x5350f31c,count=1000)
            self.assertEqual(p.u.reg_read(a.UC_ARM_REG_PC),0x5350f31c)
            # Restore only independent owner/geometry inputs overwritten by
            # the constructor fragment; its five descriptor bytes stay native.
            for offset,value in ((0,0x53d0fc90),(0x23c,RECIPE+0x5000),
                                 (0x44c8,RECIPE+0x7000),(0x5c,RECIPE+0x6000)):
                p.words(RECIPE+offset,value)
            p.call(0x53510cec,RECIPE)
            capacity=p.call(0x5350d47c,RECIPE,5)
            p.call(0x5350d7e8,RECIPE,5,BANK_BASE)
            images=Descriptors.from_buffer_copy(b''.join(bytes(p.u.mem_read(RECIPE+off,32))
                                     for off in (0x70,0x90,0xb0,0xd0,0xf0)))
            self.assertEqual(images[4][7]&255,0) # native thumbnail layout
            self.assertEqual(capacity,72192000)
            for style in (1,2):
                for orientation in range(1,9):
                    out=BankPlan()
                    self.assertEqual(self.plan(style,orientation,BANK_BASE,capacity,C.byref(images),C.byref(out)),0)
                    self.assertLessEqual(out.used_bytes,capacity)
                    self.assertEqual(out.images[4][7],images[4][7])
            self.assertFalse(p.assertions)

    def test_capacity_alias_and_invalid_geometry_fail_without_output_mutation(self):
        for mode in ('short','outside','third','odd','unaligned_source'):
            images=self.images();capacity=72192000
            if mode=='short':capacity=50000000
            elif mode=='outside':images[4][2]=0x70000000
            elif mode=='third':images[0][3]=0x60001000
            elif mode=='odd':images[0][4]+=1
            else:images[0][1]+=1
            out=BankPlan();C.memset(C.byref(out),0xa5,C.sizeof(out));before=bytes(out)
            self.assertEqual(self.plan(1,1,0x60000000,capacity,C.byref(images),C.byref(out)),-1)
            self.assertEqual(bytes(out),before)

    def test_unproved_source_cache_rows_are_rejected_before_relocation(self):
        images=self.images()
        for i,guard in ((0,144),(2,0)):
            images[i][5]=(8000<<16)|6016
            images[i][2]=0x60000000+(9000+guard)*6016
        out=BankPlan();C.memset(C.byref(out),0xa5,C.sizeof(out));before=bytes(out)
        self.assertEqual(self.plan(1,1,0x60000000,200000000,C.byref(images),C.byref(out)),-1)
        self.assertEqual(bytes(out),before)

    def shape_api(self):
        self.assertTrue(hasattr(self.lib,'m10v_border_bank_shape'),
                        'full-source shape API has not been implemented')
        shape=self.lib.m10v_border_bank_shape
        shape.argtypes=[C.c_uint32]*6+[C.POINTER(BankPlan)]
        shape.restype=C.c_int
        return shape

    def test_shape_reconstructs_same_slots_without_current_cropped_descriptors(self):
        shape=self.shape_api()
        for style in (1,2):
            for orientation in range(1,9):
                images=self.images();plan=BankPlan();slots=BankPlan()
                self.assertEqual(self.plan(style,orientation,0x60000000,72192000,C.byref(images),C.byref(plan)),0)
                self.assertEqual(shape(style,orientation,6000,4000,0x60000000,72192000,C.byref(slots)),0)
                self.assertEqual(bytes(slots.canvas),bytes(plan.canvas))
                for field in ('bank','capacity','source_y','source_c','plane_bytes','preview_base'):
                    self.assertEqual(getattr(slots,field),getattr(plan,field))
                self.assertEqual(bytes(slots.images),bytes(C.sizeof(Descriptors)))
                self.assertEqual(slots.used_bytes,slots.preview_base-slots.bank)
                # BackResize may crop/alias source and main; rebuilding slots
                # still uses unchanged common full-source dimensions.
                images[0][4]=(2248<<16)|6000;images[0][1]+=876*6336
                again=BankPlan()
                self.assertEqual(shape(style,orientation,6000,4000,0x60000000,72192000,C.byref(again)),0)
                self.assertEqual(bytes(again),bytes(slots))

    def test_shape_capacity_does_not_admit_preview_footprint(self):
        shape=self.shape_api();slots=BankPlan()
        self.assertEqual(shape(1,1,6000,4000,0x60000000,72192000,C.byref(slots)),0)
        bare_capacity=slots.used_bytes
        self.assertEqual(shape(1,1,6000,4000,0x60000000,bare_capacity,C.byref(slots)),0)
        out=BankPlan();C.memset(C.byref(out),0xa5,C.sizeof(out));before=bytes(out)
        images=self.images()
        self.assertEqual(self.plan(1,1,0x60000000,bare_capacity,C.byref(images),C.byref(out)),-1)
        self.assertEqual(bytes(out),before)
        unaligned=BankPlan()
        self.assertEqual(shape(1,1,6000,4000,0x60000004,72192000,C.byref(unaligned)),0)
        self.assertEqual(unaligned.used_bytes,2*unaligned.plane_bytes+60)

    def test_shape_off_and_invalid_input_do_not_invent_image_ownership(self):
        shape=self.shape_api();out=BankPlan()
        self.assertEqual(shape(0,1,6000,4000,0x60000000,72192000,C.byref(out)),0)
        self.assertEqual(out.used_bytes,0)
        self.assertEqual(out.source_y|out.source_c|out.plane_bytes|out.preview_base,0)
        self.assertEqual(bytes(out.images),bytes(C.sizeof(Descriptors)))
        for args in ((3,1,6000,4000,0x60000000,72192000),
                     (1,0,6000,4000,0x60000000,72192000),
                     (1,1,5999,4000,0x60000000,72192000),
                     (1,1,6000,4000,0x60000000,100)):
            C.memset(C.byref(out),0xa5,C.sizeof(out));before=bytes(out)
            self.assertEqual(shape(*args,C.byref(out)),-1)
            self.assertEqual(bytes(out),before)

    def test_arm_bank_plan_links_without_libc_or_runtime_helpers(self):
        objects=[]
        for name in ('m10v_border','m10v_border_bank'):
            obj=Path(self.tmp.name)/(name+'.o');objects.append(str(obj))
            subprocess.run([shutil.which('clang'),'--target=armv7-none-eabi','-mcpu=cortex-a9',
                            '-marm','-mfloat-abi=soft','-Os','-ffreestanding','-fno-builtin',
                            '-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables',
                            '-c',str(ROOT/'native/gr3'/(name+'.c')),'-o',str(obj)],check=True,capture_output=True)
        result=subprocess.run([shutil.which('ld.lld'),'-Ttext=0x54160000','--entry=m10v_border_bank_plan',
                               *objects,'-o',str(Path(self.tmp.name)/'bank.elf')],text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':unittest.main()
