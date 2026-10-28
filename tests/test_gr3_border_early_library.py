"""Real producer/tuner -> early native Setup6 -> existing residual bridge.

No image hardware is emulated and no border-complete state is fabricated.
Unmapped photo planes ensure the authenticated native-only bridge touches no
pixels. BackResize hardware/owner scheduling remains a separate integration.
"""
import struct
import tempfile
import unittest
from pathlib import Path
from unicorn import arm_const as A
from scripts.build_gr3_m10v_library import build
from tests import test_gr3_film_pipeline_current as current

ROOT=Path(__file__).resolve().parents[1]
class EarlyBorderLibraryTests(unittest.TestCase):
    call=current.CurrentFilmPipelineTests.call
    fixture=current.CurrentFilmPipelineTests.fixture
    enqueue=current.CurrentFilmPipelineTests.enqueue
    make=current.CurrentFilmPipelineTests.make
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
        cls.manifest=build(cls.tmp.name,sd_library=True,lifecycle_trace=True,recipe_snapshot=True,
            native_color=True,native_grain=True,appended_slots=True,border_enabled=True,hdf_enabled=False)
        cls.rom=(ROOT/'builds/gr3-extension-validation/official-rtos.bin').read_bytes()
        image=bytearray(cls.rom);m=cls.manifest
        code=(Path(cls.tmp.name)/'m10v-library-arm.bin').read_bytes();at=m['base']-0x53000000
        if len(image)<at+len(code):image.extend(bytes(at+len(code)-len(image)))
        image[at:at+len(code)]=code
        for p in m['capture_lifecycle']['snapshot']['patches']:
            at=p['address']-0x53000000
            assert image[at:at+4]==bytes.fromhex(p['expected_hex'])
            image[at:at+4]=bytes.fromhex(p['replacement_hex'])
        cls.image=bytes(image)
    def test_real_ingress_and_tuner_allow_clean_library_before_original_jpeg_stage(self):
        e,recipe,obj,frame,si,request,data=self.fixture(film=66)
        # Remove fixture's direct scalar snapshot: this test admits the state
        # only through the actual original5351ea9c producer/trampoline.
        e.u.mem_write(recipe+0x4a08,bytes(1796))
        owner=e.alloc(self.manifest['hdf_menu']['owner_bytes'])
        e.w32(0x55063910,1);e.w32(0x55063988,owner)
        e.w32(owner+0x213c,0x3856504d);e.w32(owner+0x2140,2)
        e.u.mem_write(owner+0x2144,bytes(e.u.mem_read(data,184)))
        cache=owner+self.manifest['border']['cache_owner_offset']
        for offset,value in ((0,0x3143424d),(4,2),(8,1),(12,1)):e.w32(cache+offset,value)
        for kind in (19,0,16,1,8,9,2,4):self.enqueue(e,recipe,kind)
        self.make(e,recipe,obj,frame)
        self.assertEqual(self.call(e,'m10v_isp_frame_recipe_completed',recipe,si,25,data)&1,1)
        # Authentic post-crop low descriptors; photos intentionally unmapped.
        low=struct.pack('<4I8H',1,0x65000000,0x68000000,0,6000,4000,6336,4000,0,0,2,0)
        e.u.mem_write(recipe+0x70,low);e.u.mem_write(recipe+0xb0,low)
        e.w32(recipe+0x9b8,0x53d0fbe0)
        e.w32(request,0x53d0fe60);e.u.mem_write(request+12,b'\x01\x01')
        e.u.mem_write(recipe+0x140,b'\x01');e.w32(recipe+0x60,0x70000000)
        dims=e.alloc(4);e.u.mem_write(dims,struct.pack('<2H',6112,4064));e.w32(recipe+0x230,dims)
        e.call(0x5350e624,recipe,6)
        self.assertEqual(bytes(e.u.mem_read(recipe+0x110,32)),low)
        self.assertEqual(self.call(e,'m10v_border_shot_transition',recipe,0,1),1)
        self.assertEqual(self.call(e,'m10v_capture_library',recipe+0x9b8),0)
        self.assertEqual(self.call(e,'m10v_border_shot_transition',recipe,1,2),1)
        e.call(0x5350e624,recipe,6) # normal later metadata setup remains legal
        self.assertEqual(self.call(e,'m10v_capture_library',recipe+0x9b8),0)
        self.assertEqual(self.call(e,'m10v_border_shot_phase',recipe),2,
                         'only existing processing attempted; no hardware-border completion claim')

if __name__=='__main__':unittest.main()
