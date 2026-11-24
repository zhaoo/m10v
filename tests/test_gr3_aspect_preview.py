"""Native ADJ dispatch -> immediate selection -> installed LCD grid callback.

The capture model deliberately retains its earlier ratio until capture apply.
Native property availability queries run through the original accessor with a
read-only property-service boundary. Grid geometry is observed at the existing
native rectangle engine; no camera image pixels are accessed by the test.
"""
import os
import struct
from types import SimpleNamespace
from unicorn import UC_PROT_ALL
from scripts.analyze_gr3_border_iip import OriginalArm, BASE
import unittest
from tests import test_gr3_aspect_formal as support
from tests import test_gr3_aspect_adj as adj


class NativeAspectPreview(unittest.TestCase):
    setUpClass = classmethod(support.FormalAspectSelection.setUpClass.__func__)

    def device(self):
        rom = self.rom
        if os.environ.get('M10V_PREVIEW_SOURCE') == '1':
            source = adj.FinalAspectAdj()
            source.official = self.official
            rom = bytearray(source.source_fixture(True))
            # Retain the production component's two native LCD entry hooks;
            # the old source-only ADJ fixture loaded just its appended code.
            for address, expected in ((0x53668b04, bytes.fromhex('ab3e29ea')),
                                      (0x53668fb0, bytes.fromhex('943d29ea')),
                                      (0x53437228, struct.pack('<I', 0xea000000 | (((0x540b92d0-0x53437228-8)>>2)&0xffffff)))):
                offset=address-BASE
                self.assertEqual(self.rom[offset:offset+4], expected)
                rom[offset:offset+4]=expected
        camera = OriginalArm(self.official)
        old = (len(self.official) + 4095) & ~4095
        extent = (len(rom) + 4095) & ~4095
        camera.u.mem_protect(BASE, old, UC_PROT_ALL)
        if extent > old:
            camera.u.mem_map(BASE + old, extent - old)
        camera.u.mem_write(BASE, bytes(rom))
        model, properties = 0x55063f30, support.support.PROPERTIES
        for flag in (0x55063d80, 0x55063ed0, 0x55063e54):
            camera.words(flag, 1)
        camera.words(model + 4, properties)
        camera.words(adj.CONTROLLER + 0x1f0, adj.LIST)
        camera.u.mem_write(properties + 0x918, b'\4')
        camera.boundaries = {0x532288b0: lambda: 0, self.symbols['m10v_debug_log']: lambda: 0}
        fixture = SimpleNamespace(camera=camera, model=model,
            ratio=lambda: camera.call(0x53245260, model))
        capture, box, data = 0x550c0000, 0x550d0000, 0x550e0000
        camera.words(0x553458ac, 1)
        camera.words(0x553458b0, capture)
        camera.words(capture + 0x518, box)
        camera.words(box, data)
        camera.words(0x55362964, 1)  # Real native override manager singleton.
        for address in (0x536ae71c, 0x536ae870, 0x536a9dd4):
            camera.boundaries[address] = lambda: 1
        # Read-only generic native property query. It reports no synchronous
        # backend write admission, leaving the committed capture copy intact.
        camera.boundaries[0x536abd28] = lambda: 0
        properties = support.support.PROPERTIES
        camera.words(fixture.model + 4, *([properties] * 8))
        camera.u.mem_write(properties + 0x44, b'\0')
        return camera, fixture, capture, data

    def test_liveview_grid_uses_immediate_selection_before_capture_model_catches_up(self):
        camera, fixture, capture, data = self.device()
        camera.words(0x550645f0, 0x08000000)
        view, surface = 0x550a4000, 0x550a5000
        display, parent, native_vptr = 0x550a8000, 0x550a9000, 0x53c0aa68
        camera.words(display + 0x15c, parent, view)
        camera.u.mem_write(display + 0x2d1, b'\1')
        camera.words(view, native_vptr, parent)
        for widget in (view, parent):
            camera.u.mem_write(widget + 0x9e, b'\1')
            for offset in (0x30, 0x64):
                camera.words(widget + offset, 0, 0, 720, 480)
        camera.u.mem_write(view + 0xf4, b'\2\x10')
        visibility=[]
        def native_visibility():
            widget=camera.u.reg_read(camera.A.UC_ARM_REG_R0)
            enabled=camera.u.reg_read(camera.A.UC_ARM_REG_R1)
            camera.u.mem_write(widget+0x9e,bytes([enabled!=0]))
            visibility.append(enabled!=0)
            return 0
        camera.boundaries[0x533ad3c0]=native_visibility
        camera.boundaries[0x533ad308] = lambda: 0  # Native invalidation endpoint.
        # The original native setup runs with real stored grid-guide flags OFF.
        # It hides the grid first; the existing main-LiveView mask adapter may
        # then show its frame-only view. No visible-grid fixture is assumed.
        camera.u.mem_write(view+0x9e,b'\0')

        def repaint(private):
            setup = camera.read_words(0x53b2fa48, 1)[0]
            camera.call(setup, display, 1, 1)
            vptr = camera.read_words(view, 1)[0]
            self.assertEqual(vptr != native_vptr, private)
            # Resolve the installed native/custom draw slot after real setup.
            callback=0x5339c3b0
            if private:
                table=bytes(camera.u.mem_read(vptr,0x60))
                callbacks=[address for address in (0x540b90a4,0x540b91cc)
                           if struct.pack('<I',address) in table]
                self.assertEqual(len(callbacks),1)
                callback=callbacks[0]
            camera.call(callback, view, surface)
        camera.boundaries[0x5339c3b0] = lambda: 0  # Native base grid paint.
        camera.boundaries[0x533ab9bc] = lambda: 0
        camera.boundaries[0x5320804c] = lambda: 0x550a6000
        camera.boundaries[0x532081ec] = lambda: 0x550a7000
        camera.boundaries[0x53208298] = lambda: 0  # Isolate crop masks from labels.
        masks = []
        def rectangle():
            sp = camera.u.reg_read(camera.A.UC_ARM_REG_SP)
            masks.append(camera.read_words(sp, 5))
            return 0
        camera.boundaries[0x540b88b4] = rectangle
        # Native list selection, descriptor lookup, apply callback, post-apply
        # bookkeeping all run; this is the callsite seen at LR=0x531a3160.
        for row, raw, expected in ((4, 4, [[0,0,720,108,16],[0,372,720,108,16]]),
                                   (5, 5, [[0,0,80,480,16],[640,0,80,480,16]])):
            with self.subTest(raw=raw):
                camera.u.mem_write(adj.LIST + 0x110, struct.pack('<H', row))
                camera.call(0x531a3100, adj.CONTROLLER)
                self.assertEqual(fixture.ratio(), raw)
                self.assertEqual(camera.call(0x5354a778, capture), 0)
                masks.clear()
                visibility.clear()
                repaint(True)
                self.assertIn(False,visibility)
                self.assertIn(True,visibility)
                self.assertEqual(masks, expected)
        # The existing movie and native forced-aspect policy still owns LCD
        # rendering even when the still UI copy retains a private ratio.
        for condition in ('movie', 'override'):
            with self.subTest(condition=condition):
                camera.u.mem_write(data + 0x74e, bytes([condition == 'movie']))
                camera.u.mem_write(0x55362968 + 0x105 + 0x4a, bytes([condition == 'override']))
                masks.clear()
                repaint(False)
                self.assertEqual(masks, [])
        camera.u.mem_write(data + 0x74e, b'\0')
        camera.u.mem_write(0x55362968 + 0x105 + 0x4a, b'\0')
        camera.u.mem_write(adj.LIST + 0x110, struct.pack('<H', 0))
        camera.call(0x531a3100, adj.CONTROLLER)
        self.assertEqual(fixture.ratio(), 0)
        masks.clear()
        repaint(False)
        self.assertEqual(masks, [])
        self.assertFalse(camera.assertions)

    def test_adj_background_publishes_native_cropped_viewport_without_grid_layer(self):
        camera, fixture, capture, data = self.device()
        camera.words(0x550645f0, 0x02000000)  # Native still ADJ route.
        if os.environ.get('M10V_PREVIEW_SOURCE') != '1':
            owner_session=support.support.OWNER
            camera.words(0x55063910,1)
            camera.words(0x55063988,owner_session)
            camera.call(self.symbols['m10v_half_pair_init'],owner_session)
            self.assertEqual(camera.call(self.symbols['m10v_settings_half_set'],1),0)
        camera.words(data + 0x7b8, 0x3f800000)
        profile, owner = 0x550b0000, 0x550b1000
        camera.words(owner + 0xa0, profile)
        camera.u.mem_write(0x55362968 + 0x6c2, b'\1')
        native=(2949120,1966080,0,0)
        service, context=0x550b2000,0x550b3000
        camera.words(service+8,context)
        camera.words(context+4,*native)
        camera.words(context+0x24,*native)
        camera.boundaries[0x536659ac]=lambda:service
        camera.boundaries[0x53666200]=lambda:0
        camera.boundaries[0x5366632c]=lambda:0
        camera.boundaries[0x53665c2c]=lambda:0  # Native refreshed base rectangle supplied above.

        def publish():
            registers = camera.A
            for register, value in ((registers.UC_ARM_REG_R4, owner),
                                    (registers.UC_ARM_REG_R3, profile),
                                    (registers.UC_ARM_REG_R5, 0),
                                    (registers.UC_ARM_REG_SP, 0x55ffe000)):
                camera.u.reg_write(register, value)
            camera.u.emu_start(0x53456a7c, 0x53456b10, count=500000)
            self.assertEqual(camera.u.reg_read(registers.UC_ARM_REG_PC), 0x53456b10)
            return (struct.unpack('<2H', camera.u.mem_read(owner + 0x54a, 4)),
                    struct.unpack('<2H', camera.u.mem_read(owner + 0x558, 4)))

        # No display/GridView is constructed or forced visible in this test.
        # Native CLASS (not raw-ID) drives the viewport's width/height calls.
        for row, raw, expected in ((4, 4, (640, 234)), (5, 5, (498, 424)),
                                   (6, 6, (320, 424))):
            with self.subTest(raw=raw):
                camera.u.mem_write(adj.LIST + 0x110, struct.pack('<H', row))
                camera.call(0x531a3100, adj.CONTROLLER)
                self.assertEqual(fixture.ratio(), raw)
                self.assertEqual(camera.call(0x5354a778, capture), 0)
                selected_class=camera.call(0x53669424, profile, 1)
                viewport, backing = publish()
                self.assertEqual(viewport, expected)
                self.assertEqual(backing, (640, 424))
                self.assertEqual(selected_class,raw)
                self.assertEqual(camera.u.mem_read(profile + 4, 1)[0],raw)
                camera.call(0x53437170)
                width,height,left,top=camera.read_words(context+0x64,4)
                if raw==4:
                    self.assertEqual((width,height,left,top),(2949120,1085276,0,440402))
                elif raw==5:
                    self.assertEqual((width,height,left,top),(2296381,1966080,326369,0))
                else:
                    self.assertEqual((width,height,left,top),(1470628,1966080,739246,0))
                self.assertEqual(camera.call(0x5354a778,capture),0)
        # Native movie/forced-aspect owners retain their original full class.
        camera.u.mem_write(data + 0x74e, b'\1')
        self.assertEqual(camera.call(0x53669424, profile, 1), 0)
        camera.u.mem_write(data + 0x74e, b'\0')
        camera.words(0x550645f0, 0x08000000)
        self.assertEqual(camera.call(0x53669424, profile, 1), 0)
        self.assertFalse(camera.assertions)
