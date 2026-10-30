"""Installed grid setup/callback -> native clipped RGBA rectangle renderer.

Only native grid-content drawing/setup, UI invalidation endpoints, graphics
singleton/FB-handle services and OS locks are boundaries. Mask clipping, palette
lookup and NEON RGBA writes execute real ARM. This does not emulate LCD DMA.
"""
import os
from pathlib import Path
import struct
import unittest
from unicorn import UC_HOOK_CODE, UC_PROT_ALL
from scripts.analyze_gr3_border_iip import OriginalArm
from tests.test_gr3_aspect_full_callers import FullAspectCallers as _Support
from scripts.gr3_aspect_overlay import build_module

BASE=0x53000000
DISPLAY,GRID,PARENT=0x55200000,0x55201000,0x55202000
SETTINGS,WRAPPER,SI=0x55210000,0x55220000,0x55230000
MANAGER,GRAPHICS,SURFACE,FB=0x55240000,0x55241000,0x55250000,0x55600000
NATIVE_VPTR=0x53c0aa68


class GridMaskTransitions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _Support.setUpClass()
        cls.code=_Support.code
        _,cls.entries=build_module()
        path=os.environ.get('M10V_GRID_MASK_RTOS')
        cls.final=bool(path)
        if path:cls.code=Path(path).read_bytes()

    def fixture(self,width=720,height=480):
        rom=Path('builds/gr3-extension-validation/official-rtos.bin').read_bytes()
        p=OriginalArm(rom);old=(len(rom)+4095)&~4095;new=(len(self.code)+4095)&~4095
        if new>old:p.u.mem_map(BASE+old,new-old)
        p.u.mem_protect(BASE,old,UC_PROT_ALL);p.u.mem_write(BASE,self.code)
        if not self.final:p.words(0x53b2fa48,self.entries['m10v_aspect_grid_setup'])
        # This test isolates mask pixels. Status/icon payload rendering is
        # covered separately by the actual native icon blitter artifact gate.
        p.words(0x553458ac,1);p.words(0x553458b0,SETTINGS)
        p.words(SETTINGS+0x518,WRAPPER);p.words(WRAPPER,SI)
        p.words(DISPLAY+0x15c,PARENT,GRID)
        p.u.mem_write(DISPLAY+0x2d1,b'\1')
        p.words(GRID,NATIVE_VPTR,PARENT)
        for target in (GRID,PARENT):
            p.u.mem_write(target+0x9e,b'\1')
            p.words(target+0x30,0,0,width,height)
            p.words(target+0x64,0,0,width,height)
        p.u.mem_write(GRID+0xf4,b'\2\x10')
        p.u.mem_write(SURFACE+2,b'\5')
        p.u.mem_write(SURFACE+0x18,struct.pack('<H',width))
        p.words(GRAPHICS,0x57000000)
        events=[]
        def record(name):
            def call():events.append((name,p.u.reg_read(p.A.UC_ARM_REG_R0)));return 0
            return call
        p.boundaries={0x5317750c:record('native-setup'),0x5339c3b0:record('native-grid'),
                      0x533ad308:record('invalidate'),0x536ae71c:lambda:1,0x536ae870:lambda:1,
                      0x53654150:lambda:MANAGER,0x53654220:lambda:0,
                      0x5320804c:lambda:MANAGER,0x532081ec:lambda:GRAPHICS,
                      0x53208298:lambda:0, # icon service excluded; real blitter has its own final gate
                      0x536c7520:lambda:FB}
        fills=[]
        def observe(u,address,size,data):
            if address==0x53208a2c:
                packet=u.reg_read(p.A.UC_ARM_REG_R1)
                fills.append((struct.unpack('<5I',u.mem_read(packet,20)),u.mem_read(packet+20,1)[0]))
        p.u.hook_add(UC_HOOK_CODE,observe)
        return p,events,fills

    def setup(self,p,ratio):
        p.u.mem_write(SI+0x7b6,bytes([ratio]))
        callback=p.read_words(0x53b2fa48,1)[0]
        self.assertEqual(callback,self.entries['m10v_aspect_grid_setup'])
        p.call(callback,DISPLAY,1,1)

    def draw(self,p):
        vptr=p.read_words(GRID,1)[0]
        # Resolve the actual native/custom vtable draw slot, rather than
        # calling m10v_aspect_draw directly with fabricated raw arguments.
        table=bytes(p.u.mem_read(vptr,0x60))
        custom=(0x540b90a4).to_bytes(4,'little')
        if custom in table:callback=0x540b90a4
        else:
            self.assertEqual(vptr,NATIVE_VPTR)
            callback=0x5339c3b0
        p.call(callback,GRID,SURFACE)

    def test_real_grid_setup_draw_and_restore_invalidate_both_native_owners(self):
        for width,height in ((720,480),(360,240)):
            with self.subTest(dimensions=(width,height)):
                p,events,fills=self.fixture(width,height)
                self.setup(p,0);self.assertEqual(p.read_words(GRID,1),[NATIVE_VPTR])
                events.clear();self.setup(p,2)
                self.assertNotEqual(p.read_words(GRID,1),[NATIVE_VPTR])
                self.assertIn(('invalidate',GRID),events);self.assertIn(('invalidate',PARENT),events)
                p.u.mem_write(FB,b'\xff'*width*height*4)
                self.draw(p)
                margin=38 if width==720 else 19
                self.assertEqual(fills,[((SURFACE,0,0,width,margin),1),((SURFACE,0,height-margin,width,margin),1)])
                self.assertEqual(bytes(p.u.mem_read(FB,4)),b'\0\0\0\xff')
                self.assertEqual(bytes(p.u.mem_read(FB+((height//2)*width+width//2)*4,4)),b'\xff'*4)
                events.clear();fills.clear();self.setup(p,0)
                self.assertEqual(p.read_words(GRID,1),[NATIVE_VPTR])
                self.assertIn(('invalidate',GRID),events);self.assertIn(('invalidate',PARENT),events)
                self.draw(p);self.assertFalse(fills);self.assertFalse(p.assertions)

    def test_movie_or_native_override_restores_original_grid_without_wide_mask(self):
        for condition in ('movie','override'):
            with self.subTest(condition=condition):
                p,events,fills=self.fixture()
                self.setup(p,2)
                self.assertNotEqual(p.read_words(GRID,1),[NATIVE_VPTR])
                if condition=='movie':p.u.mem_write(SI+0x74e,b"\1")
                else:p.boundaries[0x53654220]=lambda:1
                events.clear();self.setup(p,2)
                self.assertEqual(p.read_words(GRID,1),[NATIVE_VPTR])
                self.assertIn(('invalidate',GRID),events);self.assertIn(('invalidate',PARENT),events)
                p.u.mem_write(FB,b"\xff"*(720*480*4))
                self.draw(p)
                self.assertFalse(fills)
                self.assertEqual(bytes(p.u.mem_read(FB,720*480*4)),b"\xff"*(720*480*4))
                self.assertFalse(p.assertions)

    def test_active_wide_to_half_property_setup_invalidates_both_owners_without_draw_loop(self):
        p,events,fills=self.fixture()
        for ratio in (2,6,2,4,5,6):
            events.clear();self.setup(p,ratio)
            # The explicit post-setup publication also covers active->active
            # transitions with identical class, vtable and canvas geometry.
            self.assertIn(('invalidate',GRID),events)
            self.assertIn(('invalidate',PARENT),events)
            self.assertEqual(sum(name=='native-setup' for name,_ in events),1)
            p.u.mem_write(FB,b"\xff"*(720*480*4))
            events.clear();self.draw(p)
            self.assertFalse(any(name=='invalidate' for name,_ in events),'OnDraw invalidated itself')
        self.assertFalse(p.assertions)

    def test_post_setup_wrapper_preserves_legacy_registers_flags_and_stack(self):
        for ratio in (0,2,6):
            for warm in (False,True):
                snapshots=[]
                for wrapped in (False,True):
                    p,events,_=self.fixture()
                    p.u.mem_write(SI+0x7b6,bytes([ratio]))
                    if warm:p.call(0x540b7bf4,DISPLAY,1,1,0x12345678)
                    target=p.read_words(0x53b2fa48,1)[0] if wrapped else 0x540b7bf4
                    p.call(target,DISPLAY,1,1,0x12345678)
                    A=p.A
                    snapshots.append(([p.u.reg_read(getattr(A,f'UC_ARM_REG_R{i}')) for i in range(13)],
                                      p.u.reg_read(A.UC_ARM_REG_SP),p.u.reg_read(A.UC_ARM_REG_CPSR)&0xf8000000))
                self.assertEqual(snapshots[0],snapshots[1],(ratio,warm))

    def test_each_callback_preserves_current_frame_center_including_transparency(self):
        p,events,fills=self.fixture()
        for ratio in (2,6,2,0,2):
            self.setup(p,ratio)
            for pixel in (b'\xff\xff\xff\xff',b'\x31\xa2\x67\0'):
                # Explicit current input surface, not an emulated DMA refresh.
                p.u.mem_write(FB,pixel*(720*480));fills.clear()
                self.draw(p)
                at=FB+((480//2)*720+720//2)*4
                self.assertEqual(bytes(p.u.mem_read(at,4)),pixel)
                if ratio==2:
                    self.assertEqual(bytes(p.u.mem_read(FB+38*720*4,404*720*4)),pixel*(404*720))
                elif ratio==6:
                    margin=(720-480*2992//4000+1)//2
                    for row in range(480):
                        self.assertEqual(bytes(p.u.mem_read(FB+(row*720+margin)*4,(720-2*margin)*4)),pixel*(720-2*margin))
                else:
                    self.assertEqual(bytes(p.u.mem_read(FB,720*480*4)),pixel*(720*480))
                if ratio==2:
                    self.assertEqual([v[1] for v in fills],[1,1])
                    self.assertEqual(bytes(p.u.mem_read(FB,4)),b'\0\0\0\xff')
                elif ratio==6:
                    self.assertEqual([v[1] for v in fills],[16,16])
                    self.assertEqual(bytes(p.u.mem_read(FB,4)),b'\0\0\0\x80')
                else:self.assertFalse(fills)
        self.assertFalse(p.assertions)
