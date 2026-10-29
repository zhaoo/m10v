"""Execute half-frame camera adapters in ARM; no mapped image pixels."""
import struct
import json
import os
from pathlib import Path
import unittest
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE,arm_const as A
from tests import test_gr3_aspect as aspect
from tests import test_gr3_aspect_dng as dng


class HalfFrameTests(unittest.TestCase):
    setUpClass = classmethod(aspect.AspectTests.setUpClass.__func__)
    machine = aspect.AspectTests.machine
    call = aspect.AspectTests.call
    live_machine = aspect.AspectTests.live_machine

    def test_menu_appends_half_frame_preserving_old_order_and_invalid_reset(self):
        self.assertEqual(self.call(0x540b98c4).reg_read(A.UC_ARM_REG_R0), 6)
        for current, following in [(0,3),(3,1),(1,4),(4,5),(5,6),(6,0),(255,0)]:
            self.assertEqual(self.call(0x540b9300,current).reg_read(A.UC_ARM_REG_R0), following)

    def test_resolution_dispatch_uses_portrait_geometry_for_all_native_crops(self):
        for mag, sizes in [(0x3f800000,[(2992,4000),(2400,3200),(1680,2240),(960,1280)]),
                           (0x3fa00000,[(2400,3200),(2400,3200),(1680,2240),(960,1280)]),
                           (0x3fe49249,[(1680,2240),(1680,2240),(1680,2240),(960,1280)])]:
            for quality, expected in enumerate(sizes):
                with self.subTest(mag=hex(mag),quality=quality):
                    u=self.machine()
                    u.reg_write(A.UC_ARM_REG_C1_C0_2,0xf00000)
                    u.reg_write(A.UC_ARM_REG_FPEXC,0x40000000)
                    u.mem_write(aspect.RAM,b'\xa5'*4)
                    u.mem_write(aspect.RAM+0xf0000,struct.pack('<I',aspect.RAM+2))
                    for reg,v in [(A.UC_ARM_REG_S0,mag),(A.UC_ARM_REG_R1,quality),(A.UC_ARM_REG_R2,6),(A.UC_ARM_REG_R3,aspect.RAM)]:u.reg_write(reg,v)
                    u.emu_start(0x540b9450,aspect.STOP,count=10000)
                    self.assertEqual(struct.unpack('<HH',u.mem_read(aspect.RAM,4)),expected)

    def test_invalid_quality_or_magnification_never_modifies_dimensions(self):
        for mag,quality in [(0,0),(0x7fc00000,0),(0x3f800001,0),(0x3f800000,4),(0x3f800000,255)]:
            u=self.machine();u.mem_write(aspect.RAM,b'\xa5'*4)
            for reg,v in [(A.UC_ARM_REG_R0,mag),(A.UC_ARM_REG_R1,quality),(A.UC_ARM_REG_R2,aspect.RAM),(A.UC_ARM_REG_R3,aspect.RAM+2)]:u.reg_write(reg,v)
            u.emu_start(self.entries['m10v_aspect_half_resolution'],aspect.STOP,count=10000)
            self.assertEqual(bytes(u.mem_read(aspect.RAM,4)),b'\xa5'*4)

    def test_filter_normalization_matches_half_frame_output_diagonal(self):
        for mag,want in [(0x3f800000,0x3f315574),(0x3fa00000,0x3f0e00d5),(0x3fe49249,0x3ec6cdf7)]:
            self.assertEqual(self.call(self.entries['m10v_aspect_half_filter'],mag,0).reg_read(A.UC_ARM_REG_R0),want)

    def test_iiix_compile_gate_keeps_five_old_modes_and_no_half_entry(self):
        from scripts.gr3_aspect_overlay import build_module,MODULE
        code,symbols=build_module(half_frame=False)
        self.assertNotIn('m10v_aspect_half_resolution',symbols)
        for name,arg,want in [('count',0,5),('next',5,0),('next',6,0)]:
            u=self.machine();u.mem_protect(MODULE,8192,7);u.mem_write(MODULE,code)
            u.reg_write(A.UC_ARM_REG_R0,arg)
            u.emu_start(symbols['m10v_aspect_'+name],aspect.STOP,count=10000)
            self.assertEqual(u.reg_read(A.UC_ARM_REG_R0),want)

    def test_new_caption_routes_in_every_language_without_intercepting_legacy_ids(self):
        resource=self.call(0x540b9428,0,6).reg_read(A.UC_ARM_REG_R0)
        self.assertNotEqual(resource,self.caption_id)
        for language in range(21):
            for entry,leaf,reg in [(0x540b89f8,0x53396700,A.UC_ARM_REG_R7),(0x540b8bc4,0x5339710c,A.UC_ARM_REG_R3)]:
                u=self.machine();u.reg_write(A.UC_ARM_REG_R0,language);u.reg_write(A.UC_ARM_REG_R7,resource)
                u.reg_write(A.UC_ARM_REG_R11,aspect.RAM+0xe0000)
                seen=[]
                def stop(m,a,s,d):
                    if a==leaf:seen.append(a);m.emu_stop()
                u.hook_add(UC_HOOK_CODE,stop);u.emu_start(entry,aspect.STOP,count=1000)
                self.assertEqual(seen,[leaf]);ptr=u.reg_read(reg)
                header=bytes(u.mem_read(ptr,8));text=bytes(u.mem_read(struct.unpack_from('<I',header,4)[0],header[0]*2)).decode('utf-16le').rstrip('\0')
                self.assertEqual(text,'Half 3:4')

    def test_preview_draws_vertical_mask_matching_the_aligned_photo(self):
        for width,height,mask in [(720,480,181),(360,240,91)]:
            u=self.live_machine(6,0x3f800000);view=aspect.RAM+0x2000;surface=aspect.RAM+0x3000
            u.mem_write(view+0x9e,b'\x01')
            for offset in (0x30,0x64):u.mem_write(view+offset,struct.pack('<4I',0,0,width,height))
            rects=[];returns={0x5320804c:aspect.RAM+0x400,0x532081ec:aspect.RAM+0x500,0x53208298:0,0x540b88b4:0}
            def draw(m,a,s,d):
                if a not in returns:return
                if a==0x540b88b4:rects.append(struct.unpack('<5I',m.mem_read(m.reg_read(A.UC_ARM_REG_SP),20)))
                m.reg_write(A.UC_ARM_REG_R0,returns[a]);m.reg_write(A.UC_ARM_REG_PC,m.reg_read(A.UC_ARM_REG_LR))
            u.hook_add(UC_HOOK_CODE,draw);u.reg_write(A.UC_ARM_REG_R0,view);u.reg_write(A.UC_ARM_REG_R1,surface)
            u.emu_start(self.entries['m10v_aspect_draw'],aspect.STOP,count=5000)
            self.assertEqual(rects,[(0,0,mask,height,16),(width-mask,0,mask,height,16)])

    def test_half_frame_mask_and_af_are_centered_in_native_live_coordinates(self):
        for bits in (0x3f800000,0x3fa00000,0x3fe49249):
            u=self.live_machine(6,bits)
            u.emu_start(self.entries['m10v_aspect_mask_active'],aspect.STOP,count=10000)
            self.assertEqual(u.reg_read(A.UC_ARM_REG_R0),1)
            u=self.live_machine(6,bits)
            for reg,v in [(A.UC_ARM_REG_R0,6),(A.UC_ARM_REG_R1,{0x3f800000:0,0x3fa00000:1,0x3fe49249:2}[bits]),(A.UC_ARM_REG_R2,aspect.RAM+0x9000)]:u.reg_write(reg,v)
            u.emu_start(self.entries['m10v_aspect_af_bounds'],aspect.STOP,count=10000)
            self.assertEqual(u.reg_read(A.UC_ARM_REG_R0),1)
            l,t,r,b=struct.unpack('<4I',u.mem_read(aspect.RAM+0x9000,16))
            self.assertEqual((l+r,t+b),(720,480))
            self.assertGreaterEqual(l,181);self.assertGreaterEqual(t,60)
            self.assertGreater(r,l);self.assertGreater(b,t)

    def test_active_crop_is_native_and_published_once_after_geometry(self):
        for mag, expected in [(0x2000,(1470628,1966080,739246,0)),
                              (0x2800,(1179648,1572864,884736,196608)),
                              (0x38f6,(825754,1101005,1061683,432538))]:
            u=self.live_machine(6,0x3f800000);context=aspect.RAM+0x4000
            calls=[]
            def notification(m,a,s,d):
                if a==0x536ae870:
                    calls.append(struct.unpack('<4I',m.mem_read(context+0x64,16)))
            u.hook_add(UC_HOOK_CODE,notification)
            for reg,v in [(A.UC_ARM_REG_R0,context),(A.UC_ARM_REG_R1,6),(A.UC_ARM_REG_R2,mag)]:u.reg_write(reg,v)
            u.emu_start(self.entries['m10v_aspect_private_active'],aspect.STOP,count=10000)
            self.assertEqual(struct.unpack('<4I',u.mem_read(context+0x64,16)),expected)
            self.assertEqual(calls,[expected])


class HalfFrameDngTests(dng.AspectDngTests):
    def test_makernote_writer_preserves_half_frame_identity(self):
        u=self.overlay_machine();props=dng.RAM+0x100
        self.w32(u,dng.IMAGE+0x20,props);u.mem_write(props+0xf2,b'\x06')
        u.mem_map(0x535d0000,0x1000);observed=[]
        def writer(m,a,s,d):
            if a==0x535d02b4:
                observed.append(tuple(m.reg_read(r) for r in (A.UC_ARM_REG_R0,A.UC_ARM_REG_R1,A.UC_ARM_REG_R2)))
                m.reg_write(A.UC_ARM_REG_R0,1);m.reg_write(A.UC_ARM_REG_PC,m.reg_read(A.UC_ARM_REG_LR))
        u.hook_add(UC_HOOK_CODE,writer)
        self.assertEqual(self.call(u,self.overlay_entries['m10v_aspect_write']),1)
        self.assertEqual(observed,[(dng.OUT,0,6)])

    def test_custom_half_frame_dng_uses_frozen_dimensions(self):
        for mm,w,h in [(29,2880,3856),(41,2032,2720),(70,1184,1600),(100,832,1120)]:
            u=self.machine(raw=6,width=w,height=h,origin=(20,14))
            self.assertEqual(self.call(u),1,mm)
            self.assertEqual(struct.unpack('<4I',u.mem_read(dng.OUT,16)),(20,14,w,h))

    def test_half_frame_full_or_cropped_dng_retains_frozen_identity_and_guard_bytes(self):
        for index,(full_w,h,w) in enumerate([(6000,4000,2992),(4800,3200,2400),(3360,2240,1680),(1920,1280,960)]):
            for source_w in (full_w,w):
                u=self.machine(raw=6,width=source_w,height=h,origin=(20,14))
                self.assertEqual(self.call(u),1)
                x=20+(full_w-w)//2 if source_w==full_w else 20
                self.assertEqual(bytes(u.mem_read(dng.OUT,20)),struct.pack('<4I4B',x,14,w,h,6,index,1,0))
                self.assertEqual(bytes(u.mem_read(dng.OUT-4,4)),b'\xa5'*4)
                self.assertEqual(bytes(u.mem_read(dng.OUT+20,4)),b'\xa5'*4)


class FinalHalfFrameCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=os.environ.get('M10V_ZOOM_RTOS');manifest=os.environ.get('M10V_ZOOM_MANIFEST')
        if not path or not manifest:raise unittest.SkipTest('requires final RTOS and manifest')
        cls.rom=Path(path).read_bytes();cls.manifest=json.loads(Path(manifest).read_text())

    def machine(self):
        u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
        u.mem_map(aspect.BASE,(len(self.rom)+4095)&~4095);u.mem_write(aspect.BASE,self.rom)
        u.mem_map(aspect.RAM,0x100000);u.reg_write(A.UC_ARM_REG_SP,aspect.RAM+0xd0000)
        u.reg_write(A.UC_ARM_REG_LR,aspect.STOP)
        u.reg_write(A.UC_ARM_REG_C1_C0_2,0xf00000);u.reg_write(A.UC_ARM_REG_FPEXC,0x40000000)
        return u

    def test_native_image_map_produces_actual_centered_half_frame_sensor_window(self):
        for mm,expected in [(28,(2992,4000,1572,40)),(35,(2400,3200,1868,440)),
                            (41,(2032,2720,2052,680)),(50,(1680,2240,2228,920))]:
            u=self.machine();bits=struct.unpack('<I',struct.pack('<f',mm/28))[0]
            u.reg_write(A.UC_ARM_REG_S0,bits);u.mem_write(aspect.RAM+0xd0000,struct.pack('<I',6))
            for reg,v in zip((A.UC_ARM_REG_R0,A.UC_ARM_REG_R1,A.UC_ARM_REG_R2,A.UC_ARM_REG_R3),range(aspect.RAM+0x100,aspect.RAM+0x108,2)):u.reg_write(reg,v)
            u.emu_start(0x5365f0ec,aspect.STOP,count=200000)
            self.assertEqual(struct.unpack('<4H',u.mem_read(aspect.RAM+0x100,8)),expected)
            self.assertEqual(u.reg_read(A.UC_ARM_REG_SP),aspect.RAM+0xd0000)

    def test_installed_zoom_and_replay_use_half_frame_identity_for_every_custom_focal(self):
        z=self.manifest['zoom'];state=aspect.RAM+0x2000;ctx=aspect.RAM+0x100
        for mm in range(29,50):
            if mm==35:continue
            bits=struct.unpack('<I',struct.pack('<f',mm/28))[0]
            w=(2992*28//mm)//16*16;h=(4000*28//mm)//16*16
            for quality,(max_w,max_h) in enumerate([(2992,4000),(2400,3200),(1680,2240),(960,1280)]):
                u=self.machine();u.reg_write(A.UC_ARM_REG_S0,bits)
                u.mem_write(aspect.RAM+0xd0000,struct.pack('<I',aspect.RAM+0x102))
                for reg,v in [(A.UC_ARM_REG_R1,quality),(A.UC_ARM_REG_R2,6),(A.UC_ARM_REG_R3,aspect.RAM+0x100)]:u.reg_write(reg,v)
                u.emu_start(0x536a2a30,aspect.STOP,count=200000)
                self.assertEqual(struct.unpack('<2H',u.mem_read(aspect.RAM+0x100,4)),(min(w,max_w),min(h,max_h)))
            u=self.machine();u.mem_write(ctx+8,struct.pack('<I',state));u.mem_write(state+0x7b8,struct.pack('<I',bits));u.mem_write(state+0x7b6,b'\x06')
            u.reg_write(A.UC_ARM_REG_R0,ctx)
            u.emu_start(z['symbols']['m10v_zoom_capture_replay_rect'],aspect.STOP,count=200000)
            qw,qh,x,y=struct.unpack('<4I',u.mem_read(state+0x6a0,16))
            self.assertEqual((qw,qh),(w*73728//150,h*73728//150))
            self.assertLessEqual(abs(qw+2*x-2949120),1);self.assertLessEqual(abs(qh+2*y-1966080),1)


if __name__=='__main__':unittest.main()
