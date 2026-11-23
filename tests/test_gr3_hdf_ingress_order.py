"""Run stock task order with final candidate HDF or a current-source overlay.

An explicit M10V_CURRENT_PIPELINE_CANDIDATE executes its final HDF bytes directly.
Without it, current HDF calls are rebound into a separate test RX mapping for
source validation against the generated candidate's surrounding stock pipeline.
"""
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from unicorn import UC_HOOK_CODE
from unicorn import arm_const as A
from scripts.build_gr3_m10v_library import link_object
from tests import test_gr3_hdf_task_pipeline as hdf_pipeline
from tests import test_gr3_film_pipeline_current as pipeline

ROOT = Path(__file__).resolve().parents[1]
CURRENT = 0x56000000


class HdfIngressOrderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pipeline.CurrentFilmPipelineTests.setUpClass.__func__(cls)
        cls.code, cls.current = b'', {}
        if os.environ.get('M10V_CURRENT_PIPELINE_CANDIDATE'):
            return
        with tempfile.TemporaryDirectory() as temporary:
            obj = Path(temporary) / 'hdf.o'
            flags = cls.manifest['flags'] + [
                '-DM10V_PHOTO_RECIPE=1', '-DM10V_HDF_SHARED_RECIPE=1',
                '-DM10V_HDF_UI_CACHE=1', '-DM10V_HDF_DEFAULT=0',
                '-DM10V_HDF_OWNER_OFFSET=' + hex(cls.manifest['hdf_menu']['owner_offset']),
            ]
            subprocess.run(['/opt/homebrew/opt/llvm/bin/clang', *flags, '-c',
                str(ROOT / 'native/gr3/m10v_digital_hdf.c'), '-o', str(obj)],
                check=True, capture_output=True)
            cls.code, cls.current = link_object(obj.read_bytes(), CURRENT,
                cls.manifest['symbols'], 'm10v_hdf_',
                additional_exports=('m10v_hdf_remote_snapshot', 'm10v_hdf_copy_box'),
                omitted_exports=('m10v_hdf_alloc',))

    genuine_recipe_allocation = hdf_pipeline.HdfTaskPipelineTests.genuine_recipe_allocation
    warm_ui = hdf_pipeline.HdfTaskPipelineTests.warm_ui
    reserve = hdf_pipeline.HdfTaskPipelineTests.reserve
    trap_storage = hdf_pipeline.HdfTaskPipelineTests.trap_storage
    enqueue = pipeline.CurrentFilmPipelineTests.enqueue
    make = pipeline.CurrentFilmPipelineTests.make
    capture = pipeline.CurrentFilmPipelineTests.capture

    def call(self, e, name, *args):
        e.call(self.current.get(name, self.manifest['symbols'][name]), *args)
        return e.u.reg_read(A.UC_ARM_REG_R0)

    def fixture(self):
        # Stage0 populates the saved base SI through stock Make. Stage1's
        # synthetic sub-shot leaves base-SI Clarity uninitialized in the
        # generic fixture, so it cannot establish the HDF-off parameter.
        values = pipeline.CurrentFilmPipelineTests.fixture(self, 62, stage=0)
        e = values[0]
        if not self.code:
            return values
        e.u.mem_map(CURRENT, 0x10000)
        e.u.mem_write(CURRENT, self.code)
        routes = {self.manifest['symbols'][name]: address
                  for name, address in self.current.items()}

        def current_hdf(u, at, size, unused):
            if at in routes:
                u.reg_write(A.UC_ARM_REG_PC, routes[at])

        e.u.hook_add(UC_HOOK_CODE, current_hdf)
        return values

    def initialize_request(self, e, recipe):
        # Original saved-SI/request fields feed the original constructor at
        #5351084c. This runs BEFORE first5351ea9c task submission on camera.
        e.services.add(0x53654220)  # Native property bits are an OS boundary.
        for reg, value in ((A.UC_ARM_REG_R0, recipe), (A.UC_ARM_REG_R1, 9),
                           (A.UC_ARM_REG_R2, struct.unpack('<I', e.u.mem_read(recipe + 0x44c8, 4))[0]),
                           (A.UC_ARM_REG_SP, 0x5effff00)):
            e.u.reg_write(reg, value)
        e.u.emu_start(0x53510800, 0x53510850, count=3000000)
        self.assertEqual(e.u.reg_read(A.UC_ARM_REG_PC), 0x53510850)

    def settings(self, e, recipe, si, execution):
        params, values = e.alloc(0x34), e.alloc(12)
        context = recipe + 0x4320
        if struct.unpack('<I', e.u.mem_read(context, 4))[0] != 0x53d0fc60:
            # Original recipe constructor writes the Develop vptr/empty fields.
            # Then original module setup copies this recipe's saved SI/source;
            # never inject the HDF token's SI or ready bits in this regression.
            e.u.reg_write(A.UC_ARM_REG_R7, recipe + 0x4000)
            e.u.reg_write(A.UC_ARM_REG_R5, 0)
            e.u.emu_start(0x5350f940, 0x5350f9c8, count=1000)
            e.w32(context + 0x3c, e.alloc(0x80))  # External module descriptor.
            e.u.reg_write(A.UC_ARM_REG_R4, recipe)
            e.u.reg_write(A.UC_ARM_REG_R5, recipe + 0x4000)
            e.u.emu_start(0x5350ed8c, 0x5350edbc, count=1000)
            self.assertEqual(struct.unpack('<II', e.u.mem_read(context + 0x30, 8)),
                             (recipe + 0x1a8, si))
        e.w32(params + 0x10, values)
        site = 0x53503aa0 if execution else 0x535033d8
        entry = next(p['entry'] for p in self.manifest['capture_lifecycle']['native_grain']['patches']
                     if p['address'] == site)
        e.u.reg_write(A.UC_ARM_REG_R0, params)
        e.u.reg_write(A.UC_ARM_REG_R1, si)
        e.u.reg_write(A.UC_ARM_REG_R2, 1)
        e.u.reg_write(A.UC_ARM_REG_R4, context)
        e.u.reg_write(A.UC_ARM_REG_R12, context)
        e.u.reg_write(A.UC_ARM_REG_SP, 0x5effff00)
        e.u.reg_write(A.UC_ARM_REG_LR, 0x5e000000)
        e.u.emu_start(entry, 0x5e000000, count=200000)
        self.assertEqual(e.u.reg_read(A.UC_ARM_REG_PC), 0x5e000000)
        return params, struct.unpack('<4hf', e.u.mem_read(values, 12))

    def test_request_initialization_before_task_snapshot_arms_native_hdf(self):
        e, recipe, obj, frame, si, request, data = self.fixture()
        self.genuine_recipe_allocation(e, recipe)
        self.warm_ui(e, data, 3)
        trap = self.trap_storage(e)
        self.reserve(e, recipe)
        self.initialize_request(e, recipe)
        self.assertEqual(struct.unpack('<3I', e.u.mem_read(recipe + 0x5134, 12)), (0, 0, 0))
        self.enqueue(e, recipe, 19)
        self.assertEqual(bytes(e.u.mem_read(request + 0x24, 1)), b'\1',
                         'first real task must arm HDF after native request initialization')
        self.assertEqual(struct.unpack('<3I', e.u.mem_read(recipe + 0x5134, 12)), (3, 3, si))
        self.make(e, recipe, obj, frame)
        self.assertEqual(self.call(e, 'm10v_isp_frame_recipe_completed', recipe, si, 25, data), 1)
        plan, p = self.settings(e, recipe, si, False)
        execution, x = self.settings(e, recipe, si, True)
        self.assertEqual(p, x)
        self.assertEqual(x[1], 7)
        # The real DSP/Clarity execution is a device boundary. Do not inject
        # a success result or fabricate its completion bit to pass this test.
        e.u.hook_del(trap)

    def test_off_and_cold_hdf_cache_keep_native_parameters_and_zero_pixel_encoder(self):
        for cold in (False, True):
            with self.subTest(cold=cold):
                e, recipe, obj, frame, si, request, data = self.fixture()
                self.genuine_recipe_allocation(e, recipe)
                owner = self.warm_ui(e, data, 0)
                if cold:
                    self.call(e, 'm10v_hdf_menu_cache_init', owner)
                trap = self.trap_storage(e)
                self.reserve(e, recipe)
                self.initialize_request(e, recipe)
                before = bytes(e.u.mem_read(request, 64))
                self.enqueue(e, recipe, 19)
                self.assertEqual(bytes(e.u.mem_read(request, 64)), before)
                expected = (128, 0, 0) if cold else (1, 0, 0)
                self.assertEqual(struct.unpack('<3I', e.u.mem_read(recipe + 0x5134, 12)), expected)
                self.make(e, recipe, obj, frame)
                _, plan = self.settings(e, recipe, si, False)
                _, execution = self.settings(e, recipe, si, True)
                self.assertEqual(plan, execution)
                self.assertEqual(execution[1], 0)
                self.assertEqual(self.capture(e, recipe, si, request), 0)
                e.u.hook_del(trap)

    def test_queued_strength_is_frozen_and_reused_recipe_adopts_next_commit(self):
        e, recipe, obj, frame, si, request, data = self.fixture()
        self.genuine_recipe_allocation(e, recipe)
        self.warm_ui(e, data, 3)
        trap = self.trap_storage(e)
        self.reserve(e, recipe)
        self.initialize_request(e, recipe)
        self.enqueue(e, recipe, 19)
        e.u.hook_del(trap)
        ui = e.u.hook_add(UC_HOOK_CODE, self.storage)
        self.assertEqual(self.call(e, 'm10v_hdf_save', 1), 0)
        e.u.hook_del(ui)
        trap = self.trap_storage(e)
        self.enqueue(e, recipe, 0)
        self.assertEqual(struct.unpack('<3I', e.u.mem_read(recipe + 0x5134, 12)), (3, 3, si))
        self.assertEqual(self.settings(e, recipe, si, False)[1][1], 7)
        self.genuine_recipe_allocation(e, recipe)
        self.reserve(e, recipe)
        self.initialize_request(e, recipe)
        self.enqueue(e, recipe, 19)
        self.assertEqual(struct.unpack('<3I', e.u.mem_read(recipe + 0x5134, 12)), (3, 1, si))
        self.assertEqual(self.settings(e, recipe, si, False)[1][1], 5)
        e.u.hook_del(trap)

    def test_hdf_native_parameters_remain_independent_of_cold_or_busy_color_cache(self):
        for busy in (False, True):
            with self.subTest(busy=busy):
                e, recipe, obj, frame, si, request, data = self.fixture()
                self.genuine_recipe_allocation(e, recipe)
                owner = self.warm_ui(e, data, 2)
                if busy:
                    self.assertEqual(self.call(e, 'm10v_camera_library_mutation_begin'), 1)
                else:
                    self.call(e, 'm10v_camera_library_preview_init', owner)
                trap = self.trap_storage(e)
                self.reserve(e, recipe)
                self.initialize_request(e, recipe)
                self.enqueue(e, recipe, 19)
                self.assertEqual(struct.unpack('<3I', e.u.mem_read(recipe + 0x5134, 12)),
                                 (3, 2, si))
                self.assertEqual(self.settings(e, recipe, si, False)[1][1], 6)
                self.assertEqual(self.settings(e, recipe, si, True)[1][1], 6)
                e.u.hook_del(trap)


if __name__ == '__main__':
    unittest.main()
