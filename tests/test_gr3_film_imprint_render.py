"""Native dispatch with unmapped pixels: no CPU image work is possible."""
import struct

from tests.test_gr3_isp_effects_render import RenderTests,bindings,BASE,EXT,build

def imprint_bindings():
    return [[dict(base=0x54c00000+(i*2+sign)*6144,bytes=6144,
                   width=64,height=64,stride=64) for sign in range(2)] for i in range(7)]

class ImprintRenderTests(RenderTests):
    @classmethod
    def setUpClass(cls):
        cls.code,cls.manifest=build.build(BASE,bindings(),EXT,enabled=True,imprints=imprint_bindings())
        cls.symbols=cls.manifest['symbols']
    def imprint(self,style=1,orientation=1):
        self.configure(grain=0,leak=0,orientation=orientation)
        self.capacity=240000
        self.put(self.shot+28,1)
        self.put(self.shot+44,0x46580000|(style<<7))
        self.put(self.shot+56,self.capacity)
        self.calls=[]
    def test_imprint_resizes_each_unsigned_chroma_field_then_finishes_y(self):
        self.imprint()
        self.assertEqual(self.invoke(),1)
        self.assertEqual([c[0] for c in self.calls],['plan','execute','granulation','plan','execute','granulation','granulation'])
        self.assertEqual([c[5] for c in self.calls if c[0]=='granulation'],[self.work+120000]*2+[self.work])
        self.assertEqual(self.manifest['imprint']['cpu_pixel_access'],False)
        self.assertEqual(self.manifest['imprint']['camera_tested'],False)
    def test_native_chroma_uses_zero_identity_and_monotone_weight_tables(self):
        self.imprint()
        self.assertEqual(self.invoke(),1)
        passes=[call for call in self.calls if call[0]=='granulation']
        positive,negative=(struct.unpack('<768h',self.u.mem_read(call[7],1536)) for call in passes[:2])
        identity=tuple(range(256))
        for table in (positive,negative):
            self.assertEqual(table[256:512],identity)
            self.assertEqual(table[512:768],identity)
        self.assertGreater(positive[128],128)
        self.assertLess(negative[128],128)
    def test_saved_orientation_preserves_sensor_field_and_does_not_distort_portrait(self):
        for style in range(1,8):
            for slot,orientation in enumerate((1,3,6,8)):
                self.imprint(style,orientation)
                self.assertEqual(self.invoke(),1)
                self.assertEqual([c[1][0] for c in self.calls if c[0]=='plan'],
                                 [t['base'] for t in imprint_bindings()[style-1]])
    def test_each_failed_native_stage_rejects_without_cpu_fallback(self):
        for failure in range(1,6):
            self.imprint();self.native_count=0;self.fail_at=failure
            self.assertEqual(self.invoke(),-4)
            self.assertEqual(self.native_count,failure)
    def test_imprint_only_insufficient_workspace_fails_before_submit(self):
        self.imprint()
        self.assertEqual(self.invoke(capacity=239999),-1)
        self.assertEqual(self.calls,[])

class ImprintDiagnosticTests(ImprintRenderTests):
    """Only the SD logger is doubled; native pixels remain unmapped."""
    TRACE = 0x54d00400
    @classmethod
    def setUpClass(cls):
        cls.code,cls.manifest=build.build(BASE,bindings(),EXT,enabled=True,
            imprints=imprint_bindings(),trace_batch=cls.TRACE)
        cls.symbols=cls.manifest['symbols']
    def setUp(self):
        super().setUp()
        self.checkpoints=[]
    def hook(self,u,pc,size,data):
        if pc==self.TRACE:
            self.checkpoints.extend(self.words(self.reg(0)+i*20,5) for i in range(self.reg(1)))
            # Failed logging must never affect photo processing.
            u.reg_write(self.A_R0,0)
            u.reg_write(self.A_PC,u.reg_read(self.A_LR))
            return
        return super().hook(u,pc,size,data)
    from unicorn.arm_const import UC_ARM_REG_R0 as A_R0, UC_ARM_REG_PC as A_PC, UC_ARM_REG_LR as A_LR
    def test_each_real_imprint_job_has_a_pre_submit_checkpoint_even_if_logger_fails(self):
        self.imprint()
        self.assertEqual(self.invoke(),1)
        stages=[r[3] for r in self.checkpoints if r[2]==0x46584900]
        self.assertEqual(stages,[1,2,3,4,5,6])
        self.assertTrue(all(r[0]==198 and r[1]==0x55004000 for r in self.checkpoints))
    def test_failed_job_is_identified_without_submitting_later_jobs(self):
        for job in range(1,6):
            self.imprint();self.checkpoints=[];self.native_count=0;self.fail_at=job
            self.assertEqual(self.invoke(),-4)
            stages=[r[3] for r in self.checkpoints if r[2]==0x46584900]
            self.assertEqual(stages,list(range(1,job+1))+[0x80|job])
    def test_off_has_no_diagnostic_filesystem_calls_or_native_jobs(self):
        self.configure(grain=0,leak=0)
        self.assertEqual(self.invoke(0,0),1)
        self.assertEqual(self.checkpoints,[])
        self.assertEqual(self.calls,[])
    def test_24mp_422_reports_full_workspace_and_both_photo_planes_without_cpu_pixels(self):
        self.w,self.h,self.stride=6000,4000,6016
        # Deliberately non-overlapping 24MP planes, none mapped for CPU use.
        self.y,self.uv,self.work=0x60000000,0x64000000,0x70000000
        self.imprint(style=7)
        self.capacity=48000000;self.put(self.shot+56,self.capacity)
        self.assertEqual(self.invoke(),1)
        facts={r[2]:r[3:] for r in self.checkpoints if r[2]!=0x46584900}
        self.assertEqual(facts[0x46584901],(7,48000000))
        self.assertEqual(facts[0x46584902],(6000|(4000<<16),6016|(4000<<16)))
        self.assertEqual(facts[0x46584903],(0x60000000,0x64000000))
