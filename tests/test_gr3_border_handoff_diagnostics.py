"""Run final ARM metadata checkpoints; no image buffers or storage emulation."""
import struct
import os
import unittest
from unicorn import UC_HOOK_CODE
from unicorn import arm_const as A
from tests import test_gr3_film_pipeline_current as pipeline


@unittest.skipUnless(os.environ.get('M10V_CURRENT_PIPELINE_CANDIDATE'),
                     'requires a final border-enabled candidate')
class BorderHandoffDiagnosticsTests(unittest.TestCase):
    setUpClass = classmethod(pipeline.CurrentFilmPipelineTests.setUpClass.__func__)
    fixture = pipeline.CurrentFilmPipelineTests.fixture
    call = pipeline.CurrentFilmPipelineTests.call

    def test_final_bin_restores_camera_4403_center_crop_metadata_without_pixel_work(self):
        e, recipe, *_ = self.fixture(35)
        # Isolated completed-stage metadata from the physical r1 failure.
        # Residual library is a boundary; no ISP completion claim is made here.
        def residual(u, at, size, unused):
            if at != self.manifest['symbols']['m10v_capture_library']: return
            u.reg_write(A.UC_ARM_REG_R0, 0);u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
        e.u.hook_add(UC_HOOK_CODE, residual)
        e.w32(recipe+0x510c,0x42524461)
        e.u.mem_write(recipe+0x256,struct.pack('<HH',6000,4000))
        e.w32(recipe+0x304,0x6211a940);e.w32(recipe+0x364,74907648)
        d=(1,0x624c71e0,0x6429a7e0,0,6000|(4000<<16),6336|(4640<<16),0,2)
        for offset in (0x70,0xb0,0x110):e.u.mem_write(recipe+offset,struct.pack('<8I',*d))
        e.services.discard(0x536af2a8)
        forbidden=[]
        def observe(u, at, size, unused):
            if at in (0x536af2a8,0x536af31c,0x5383c8a8,0x53828014,0x535847d8):forbidden.append(at)
        e.u.hook_add(UC_HOOK_CODE,observe)
        self.assertEqual(self.call(e,'m10v_border_runtime_jpeg',recipe+0x9b8),0)
        expected=(1,0x622d8140,0x640ab740,0,6320|(4640<<16),6336|(4640<<16),0,2)
        for offset in (0x70,0xb0,0x110):self.assertEqual(struct.unpack('<8I',e.u.mem_read(recipe+offset,32)),expected)
        self.assertEqual(forbidden,[])

    def test_debug_checkpoints_capture_main_and_preview_descriptors_on_both_sides(self):
        self.assertTrue(self.manifest['border']['pixel_pipeline_enabled'])
        e, recipe, *_ = self.fixture(35)
        e.w32(recipe + 0x510c, 0x42524461)
        e.u.mem_write(recipe + 0x256, struct.pack('<HH', 6000, 4000))
        e.w32(recipe + 0x304, 0x68000000); e.w32(recipe + 0x364, 72192000)
        batches = []
        def boundary(u, at, size, unused):
            if at == self.manifest['symbols']['m10v_debug_batch']:
                count = u.reg_read(A.UC_ARM_REG_R1); ptr = u.reg_read(A.UC_ARM_REG_R0)
                batches.append([struct.unpack('<5I', u.mem_read(ptr + 20*i, 20)) for i in range(count)])
            elif at == self.manifest['symbols']['m10v_debug_log']: pass
            elif at == 0x53050b7c: e.w32(u.reg_read(A.UC_ARM_REG_R0), 0)
            else: return
            u.reg_write(A.UC_ARM_REG_R0, 0); u.reg_write(A.UC_ARM_REG_PC, u.reg_read(A.UC_ARM_REG_LR))
        e.u.hook_add(UC_HOOK_CODE, boundary)
        for event, prefix, w, h in ((193, 0x4a000000, 6000, 4000), (190, 0x4a100000, 6320, 4640)):
            for offset in (0x70, 0xb0, 0xd0, 0xf0, 0x110):
                e.w32(recipe+offset+4, 0x68000000+offset)
                e.w32(recipe+offset+8, 0x6a000000+offset)
                e.w32(recipe+offset+16, w|(h<<16)); e.w32(recipe+offset+20, 6336|(h<<16))
            batches.clear(); self.call(e, 'm10v_lifecycle_phase', recipe+0x9b8, event, 0)
            snapshot = next((b for b in batches if len(b)==12), [])
            self.assertEqual(len(snapshot), 12)
            for index, offset in enumerate((0x70, 0xb0, 0xd0, 0xf0, 0x110)):
                self.assertEqual(snapshot[2*index], (197, recipe, prefix|(offset<<8), 0x68000000+offset, 0x6a000000+offset))
                self.assertEqual(snapshot[2*index+1], (197, recipe, prefix|(offset<<8)|1, w|(h<<16), 6336|(h<<16)))
            self.assertEqual(snapshot[-2], (197, recipe, prefix|2, 0x42524461, 6000|(4000<<16)))
            self.assertEqual(snapshot[-1], (197, recipe, prefix|3, 0x68000000, 72192000))
        e.w32(recipe+0x510c, 0x42524400); batches.clear()
        self.call(e, 'm10v_lifecycle_phase', recipe+0x9b8, 190, 0)
        self.assertFalse(any(len(b)==12 for b in batches))


if __name__ == '__main__': unittest.main()
