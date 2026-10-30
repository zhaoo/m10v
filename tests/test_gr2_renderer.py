"""GR II big-endian scalar rendering must match the shared host algorithms."""
import ctypes as C
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib
from tests.test_unity_update import ROOT,component

class Gr2RendererTests(unittest.TestCase):
    def test_big_endian_catalog_render_matches_host_reference_pixels(self):
        from scripts.build_gr2_runtime import build_gr2_runtime
        from tests.gr2_compat_types import State,Image
        from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_MODE_BIG_ENDIAN,arm_const as r
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)
            report=build_gr2_runtime(component('gr2','b01firm8'),{},path)
            self.assertIn('m10v_library_render',report['symbols'],'GR II runtime lacks the shared scalar renderer')
            library=path/'host.dylib';sources=['m10v_library','halation_core','film_5207','film_harman','film_curated','film_newstocks']
            subprocess.run([shutil.which('clang'),'-O2','-dynamiclib',*[str(ROOT/f'compat/gr2-v1/native/gr3/{name}.c') for name in sources],'-o',str(library)],check=True,capture_output=True)
            host=C.CDLL(str(library));host.m10v_library_init.argtypes=[C.POINTER(State)]
            host.m10v_library_render.argtypes=[C.POINTER(Image),C.POINTER(State),C.c_uint32,C.c_void_p,C.c_uint32,C.c_void_p,C.c_uint32]
            u=Uc(UC_ARCH_ARM,UC_MODE_ARM|UC_MODE_BIG_ENDIAN);u.mem_map(report['base'],0x68000);u.mem_write(report['base'],bytes.fromhex(report['runtime_hex']));u.mem_map(0x50000000,0x20000)
            def call(name,args):
                for reg,value in zip((r.UC_ARM_REG_R0,r.UC_ARM_REG_R1,r.UC_ARM_REG_R2,r.UC_ARM_REG_R3),args):u.reg_write(reg,value)
                for i,value in enumerate(args[4:]):u.mem_write(0x50018000+4*i,struct.pack('>I',value))
                u.reg_write(r.UC_ARM_REG_SP,0x50018000);u.reg_write(r.UC_ARM_REG_LR,0x5001f000)
                u.emu_start(report['symbols'][name],0x5001f000,count=10000000)
                self.assertEqual(u.reg_read(r.UC_ARM_REG_PC),0x5001f000)
                return u.reg_read(r.UC_ARM_REG_R0)
            width,height=8,4;n=width*height
            initial_y=bytes((i*37+13)%256 for i in range(n));initial_uv=bytes((i*11+93)%256 for i in range(n))
            for film,grain,leak,exposure in [(film,0,0,0) for film in range(1,79)]+[(66,2,0,0),(67,3,4,1),(68,2,0,2),(70,1,8,0)]:
                with self.subTest(film=film,grain=grain,leak=leak,exposure=exposure):
                    state=State();host.m10v_library_init(C.byref(state));state.slots[0].film=film;state.slots[0].grain=grain;state.effects[0][1]=leak;state.effects[0][5]=exposure
                    state.crc=zlib.crc32(bytes(state)[:100])
                    y=(C.c_uint8*n).from_buffer_copy(initial_y);uv=(C.c_uint8*n).from_buffer_copy(initial_uv);scratch=(C.c_uint8*4096)()
                    image=Image(y,uv,n,n,width,height,width)
                    self.assertEqual(host.m10v_library_render(C.byref(image),C.byref(state),0,None,123,scratch,4096),0)
                    call('m10v_library_init',[0x50001000]);be=bytearray(u.mem_read(0x50001000,104));struct.pack_into('>H',be,12,film);be[14]=grain;be[57]=leak;be[61]=exposure;struct.pack_into('>I',be,100,zlib.crc32(be[:100]));u.mem_write(0x50001000,bytes(be))
                    u.mem_write(0x50002000,initial_y);u.mem_write(0x50003000,initial_uv);u.mem_write(0x50004000,bytes(4096))
                    u.mem_write(0x50005000,struct.pack('>7I',0x50002000,0x50003000,n,n,width,height,width))
                    self.assertEqual(call('m10v_library_render',[0x50005000,0x50001000,0,0,123,0x50004000,4096]),0)
                    self.assertEqual(bytes(u.mem_read(0x50002000,n)),bytes(y));self.assertEqual(bytes(u.mem_read(0x50003000,n)),bytes(uv))
                    self.assertIn('gr2_render_planar',report['symbols'])
                    u.mem_write(0x50002000,initial_y);u.mem_write(0x50003000,initial_uv[::2]+initial_uv[1::2])
                    u.mem_write(0x50006000,struct.pack('>11I',0x50002000,0x50003000,0x50003000+n//2,n,n//2,n//2,width,height,width,width//2,0x422))
                    self.assertEqual(call('gr2_render_planar',[0x50006000,0x50001000,0,0,123,0x50004000,4096]),0)
                    self.assertEqual(bytes(u.mem_read(0x50002000,n)),bytes(y))
                    self.assertEqual(bytes(u.mem_read(0x50003000,n)),bytes(uv)[::2]+bytes(uv)[1::2])

    def test_constant_scratch_shuffle_matches_independent_reference_at_full_sensor_size(self):
        with tempfile.TemporaryDirectory() as folder:
            library=Path(folder)/'planar.dylib'
            subprocess.run([shutil.which('clang'),'-O2','-dynamiclib',str(ROOT/'native/gr2/m10v_planar.c'),'-o',str(library)],check=True,capture_output=True)
            host=C.CDLL(str(library));host.gr2_chroma_shuffle.argtypes=[C.POINTER(C.c_uint8),C.c_uint32,C.c_int]
            for n in (*range(1,513),4928*3264//2):
                with self.subTest(samples=n):
                    original=bytes(range(251))*(2*n//251)+bytes(range(2*n%251))
                    pixels=(C.c_uint8*(2*n+8)).from_buffer_copy(b'\xa5'*4+original+b'\xa5'*4)
                    pointer=C.cast(C.byref(pixels,4),C.POINTER(C.c_uint8))
                    self.assertEqual(host.gr2_chroma_shuffle(pointer,n,0),1)
                    expected=bytearray(2*n);expected[::2]=original[:n];expected[1::2]=original[n:]
                    self.assertEqual(bytes(pixels)[4:-4],bytes(expected))
                    self.assertEqual(host.gr2_chroma_shuffle(pointer,n,1),1)
                    self.assertEqual(bytes(pixels),b'\xa5'*4+original+b'\xa5'*4)

    def test_big_endian_film_cards_emit_current_square_artwork_without_touching_guards(self):
        from scripts.build_gr2_runtime import build_gr2_runtime
        from tests import test_gr2_runtime_build as runtime_tests
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder);report=build_gr2_runtime(component('gr2','b01firm8'),{},path)
            self.assertTrue('gr2_film_card_rgba' in report['symbols'])
            library=path/'cards.dylib'
            subprocess.run([shutil.which('clang'),'-O2','-dynamiclib',str(ROOT/'native/gr3/m10v_film_card.c'),'-o',str(library)],check=True,capture_output=True)
            host=C.CDLL(str(library));host.m10v_film_card_render.argtypes=[C.POINTER(C.c_uint32),C.c_uint32,C.c_uint32,C.c_uint32]
            u=runtime_tests.Gr2RuntimeBuildTests.machine(self,report);u.mem_map(0x60000000,0x20000);size=128*128*4;address=0x60000004
            for film,slot,selected in ((1,0,0),(33,4,1),(66,2,0),(67,1,1),(68,3,1),(78,4,0)):
                with self.subTest(film=film,slot=slot,selected=selected):
                    expected=(C.c_uint32*(128*128))();self.assertEqual(host.m10v_film_card_render(expected,film,slot,selected),0)
                    u.mem_write(address-4,b'\xa5'*(size+8));u.mem_write(0x50018000,struct.pack('>I',selected))
                    result=runtime_tests.Gr2RuntimeBuildTests.call(self,u,report['symbols']['gr2_film_card_rgba'],[address,size,film,slot])
                    self.assertEqual(result,1);self.assertEqual(bytes(u.mem_read(address,size)),bytes(expected))
                    self.assertEqual(bytes(u.mem_read(address-4,4))+bytes(u.mem_read(address+size,4)),b'\xa5'*8)
            u.mem_write(address,b'\xa5'*size)
            self.assertEqual(runtime_tests.Gr2RuntimeBuildTests.call(self,u,report['symbols']['gr2_film_card_rgba'],[address,size-1,33,0]),0)
            self.assertEqual(bytes(u.mem_read(address,size)),b'\xa5'*size)
