"""Execute the crop menu and geometry, rather than inspecting patch text."""
import importlib.util
import json
import os
import struct
import subprocess
import unittest
from pathlib import Path

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_PROT_READ, UC_PROT_EXEC, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_SP, UC_ARM_REG_LR

ROOT = Path(__file__).resolve().parents[1]
BASE, STOP, RAM = 0x53000000, 0x550ff000, 0x55000000


class AspectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        template = json.loads((ROOT/'.runtime/grlife-current/reconstruction/firmware_store/templates/urban160-native.json').read_text())
        script = "import{readFileSync}from'node:fs';import{officialResources}from'./node/gr3-stock-presets.mjs';const{decoded:d,sections:s}=officialResources(readFileSync('bin/fwdc239b-gr3-official.bin'));process.stdout.write(d.subarray(s.RTOS.offset,s.RTOS.offset+s.RTOS.size));"
        cls.code = bytearray(subprocess.check_output(['node','--input-type=module','-e',script],cwd=ROOT))
        cls.code.extend(bytes(0x10ba000-len(cls.code)))
        blob = bytes.fromhex(template['program_hex'])
        cls.code[template['base_va']-BASE:template['base_va']-BASE+len(blob)] = blob
        script = ROOT/'scripts/gr3_aspect_overlay.py'
        cls.entries = {}
        if script.exists():
            spec = importlib.util.spec_from_file_location('aspect_overlay', script)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            cls.code, cls.entries = module.apply_overlay(cls.code)
        candidate=os.environ.get('M10V_ASPECT_BIN')
        if candidate:
            script="import{readFileSync}from'node:fs';import{decodeFrameMap}from'./node/gr3-frames.mjs';const b=readFileSync(process.argv[1]),d=decodeFrameMap(b,b.readUInt32LE(b.length-8)).decoded;process.stdout.write(d.subarray(0x10870,0x10870+d.readUInt32LE(0x1086c)));"
            cls.code=subprocess.check_output(['node','--input-type=module','-e',script,candidate],cwd=ROOT)
        cls.caption_id=struct.unpack_from('<I',cls.code,cls.entries['m10v_aspect_id_record']-BASE+4)[0]

    def machine(self):
        u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        extent = (len(self.code)+4095)&~4095
        u.mem_map(BASE, extent)
        u.mem_write(BASE, bytes(self.code))
        u.mem_protect(BASE, extent, UC_PROT_READ|UC_PROT_EXEC)
        u.mem_map(RAM, 0x100000)
        u.reg_write(UC_ARM_REG_SP, RAM+0xf0000)
        u.reg_write(UC_ARM_REG_LR, STOP)
        return u

    def call(self, address, *args):
        u = self.machine()
        for reg, value in zip([UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3], args):
            u.reg_write(reg, value)
        u.emu_start(address, STOP, count=10000)
        return u

    def live_machine(self, ratio, mag):
        from unicorn import arm_const as A
        u=self.machine()
        u.mem_write(RAM+0x100,struct.pack('<I',RAM+0x200))
        u.mem_write(RAM+0x304,struct.pack('<I',RAM+0x400))
        u.mem_write(RAM+0x400+0x4c2,bytes([ratio]))
        u.mem_write(RAM+0x400+0x4c4,struct.pack('<I',mag))
        returns={0x5320ad88:RAM+0x80,0x5320b31c:RAM+0x300,
                 0x53525d5c:RAM+0x100,0x5354a778:ratio,0x53549958:0,
                 0x53654150:RAM+0x500,0x53654220:0,
                 0x53665c2c:0,0x536ae870:1}
        def native(uc,address,size,data):
            if address in returns:
                uc.reg_write(A.UC_ARM_REG_R0,returns[address])
                uc.reg_write(A.UC_ARM_REG_PC,uc.reg_read(A.UC_ARM_REG_LR))
        u.hook_add(UC_HOOK_CODE,native)
        return u

    def test_mask_remains_active_with_every_native_focal_crop(self):
        from unicorn import arm_const as A
        for ratio in (4,5):
            for mag in (0x3f800000,0x3fa00000,0x3fe3d70a,0x3fe49249):
                with self.subTest(ratio=ratio,mag=hex(mag)):
                    u=self.live_machine(ratio,mag)
                    u.emu_start(self.entries['m10v_aspect_mask_active'],STOP,count=10000)
                    self.assertEqual(u.reg_read(A.UC_ARM_REG_R0),1)

    def test_focus_and_common_live_paths_use_same_native_focal_crop_rectangle(self):
        from unicorn import arm_const as A
        for ratio in (4,5):
            for mag,q13 in ((0x3f800000,0x2000),(0x3fa00000,0x2800),(0x3fe49249,0x38f6)):
                expected=(2949120,1966080,0,0) if q13==0x2000 else (1800000,1200000,574560,383040)
                for entry in (0x540b9168,0x540b92d0):
                    with self.subTest(ratio=ratio,mag=hex(mag),entry=hex(entry)):
                        u=self.live_machine(ratio,mag);context=RAM+0x4000
                        u.mem_write(context+4,struct.pack('<4I',2949120,1966080,0,0))
                        u.mem_write(context+0x24,struct.pack('<4I',1800000,1200000,574560,383040))
                        u.reg_write(A.UC_ARM_REG_R0,context);u.reg_write(A.UC_ARM_REG_R1,0)
                        u.reg_write(A.UC_ARM_REG_R2,ratio);u.reg_write(A.UC_ARM_REG_R3,q13)
                        if entry==0x540b92d0:
                            # Native caller's saved-register epilogue, rather than a fake C return.
                            sp=RAM+0xe0000;u.reg_write(A.UC_ARM_REG_R11,sp+0x1c)
                            u.mem_write(sp,struct.pack('<7I',0,0,0,0,0,RAM+0xf0000,STOP))
                            u.reg_write(A.UC_ARM_REG_R4,q13);u.reg_write(A.UC_ARM_REG_R5,ratio)
                        u.emu_start(entry,STOP,count=10000)
                        self.assertEqual(struct.unpack('<4I',u.mem_read(context+0x64,16)),expected)

    def test_masked_width_and_height_stay_in_native_three_by_two_coordinates(self):
        from unicorn import arm_const as A
        for ratio in (4,5):
            for mag in (0x3f800000,0x3fa00000,0x3fe49249):
                for entry,leaf,value in ((0x540b85b8,0x540b8678,720),(0x540b8608,0x540b8680,480)):
                    with self.subTest(ratio=ratio,mag=hex(mag),entry=hex(entry)):
                        u=self.live_machine(ratio,mag)
                        def size_boundary(uc,address,size,data):
                            if address==leaf:
                                self.assertEqual(struct.unpack('<I',uc.mem_read(uc.reg_read(A.UC_ARM_REG_SP),4))[0],0)
                                uc.reg_write(A.UC_ARM_REG_R0,value)
                                uc.reg_write(A.UC_ARM_REG_PC,uc.reg_read(A.UC_ARM_REG_LR))
                        u.hook_add(UC_HOOK_CODE,size_boundary)
                        u.mem_write(RAM+0xf0000,struct.pack('<I',ratio))
                        u.emu_start(entry,STOP,count=10000)
                        self.assertEqual(u.reg_read(A.UC_ARM_REG_R0),value)

    def test_menu_adds_six_by_seven_without_changing_existing_identities(self):
        self.assertEqual(self.call(0x540b98c4).reg_read(UC_ARM_REG_R0), 6)
        for current, following in [(0,3),(3,1),(1,4),(4,5),(5,6),(6,0),(255,0)]:
            with self.subTest(current=current):
                self.assertEqual(self.call(0x540b9300,current).reg_read(UC_ARM_REG_R0), following)

    def test_xpan_caption_preserves_case_and_old_crop_identity(self):
        descriptor = 0x540b97ec-BASE
        size = self.code[descriptor]
        ptr = struct.unpack_from('<I', self.code, descriptor+4)[0]-BASE
        self.assertEqual(bytes(self.code[ptr:ptr+size*2]).decode('utf-16le').rstrip('\0'), 'XPan')

    def test_new_ratio_has_its_own_label(self):
        self.assertEqual(self.call(0x540b9428,0,5).reg_read(UC_ARM_REG_R0), self.caption_id)

    def test_six_by_seven_resolution_for_all_quality_and_crop_combinations(self):
        for mag, sizes in [(0x3f800000,[(4672,4000),(3728,3200),(2608,2240),(1488,1280)]),
                           (0x3fa00000,[(3728,3200),(3728,3200),(2608,2240),(1488,1280)]),
                           (0x3fe3d70a,[(2608,2240),(2608,2240),(2608,2240),(1488,1280)]),
                           (0x3fe49249,[(2608,2240),(2608,2240),(2608,2240),(1488,1280)])]:
            for quality, expected in enumerate(sizes):
                with self.subTest(mag=hex(mag),quality=quality):
                    u=self.call(self.entries['m10v_aspect_resolution'],mag,quality,RAM,RAM+2)
                    self.assertEqual(struct.unpack('<HH',u.mem_read(RAM,4)),expected)

    def test_custom_active_geometry_projects_native_rectangle_under_lock(self):
        from unicorn import arm_const as A
        for mm in range(29,101):
            if mm in (35,50): continue
            bits=struct.unpack('<I',struct.pack('<f',mm/28))[0]
            q=int(mm/28*8192+0.5)
            nw=(2949120*8192+q//2)//q;nh=(1966080*8192+q//2)//q
            for ratio in (2,4,5):
                u=self.live_machine(ratio,bits);context=RAM+0x4000
                u.mem_write(context+0x24,struct.pack('<4I',nw,nh,(2949120-nw+1)//2,(1966080-nh+1)//2))
                u.reg_write(A.UC_ARM_REG_R0,context);u.reg_write(A.UC_ARM_REG_R1,ratio)
                u.reg_write(A.UC_ARM_REG_R2,q)
                name='m10v_aspect_write_active' if ratio==5 else 'm10v_aspect_private_active'
                u.emu_start(self.entries[name],STOP,count=10000)
                w=nw*7//9 if ratio==5 else nw*8//9 if ratio==2 else nw
                h=nh*69//250 if ratio==4 else nh
                self.assertEqual(struct.unpack('<4I',u.mem_read(context+0x64,16)),(w,h,(2949120-w+1)//2,(1966080-h+1)//2))

    def test_custom_float_validation_and_af_bounds_every_mm(self):
        from unicorn import arm_const as A
        for mm in range(28,101):
            bits=struct.unpack('<I',struct.pack('<f',mm/28))[0]
            self.assertEqual(self.call(self.entries['m10v_aspect_mm'],bits).reg_read(A.UC_ARM_REG_R0),mm)
            for ratio in (1,4,5):
                u=self.live_machine(ratio,bits)
                for reg,value in ((A.UC_ARM_REG_R0,ratio),(A.UC_ARM_REG_R1,0 if mm==28 else 1 if mm==35 else 2 if mm==50 else 0),(A.UC_ARM_REG_R2,RAM+0x9000)):
                    u.reg_write(reg,value)
                u.emu_start(self.entries['m10v_aspect_af_bounds'],STOP,count=10000)
                self.assertEqual(u.reg_read(A.UC_ARM_REG_R0),1)
                l,t,r,b=struct.unpack('<4I',u.mem_read(RAM+0x9000,16))
                self.assertEqual((l+r,t+b),(720,480))
                self.assertGreater(r,l);self.assertGreater(b,t)
                self.assertGreaterEqual(l,120 if ratio==5 else 80)
                self.assertGreaterEqual(t,60)
        for bits in (0,0x7fc00000,0x3f000000,0x40800000,0x3f800001):
            self.assertEqual(self.call(self.entries['m10v_aspect_mm'],bits).reg_read(A.UC_ARM_REG_R0),0)

    def test_custom_six_by_seven_resolution_uses_continuous_crop(self):
        for mm in (29, 41, 70, 100):
            bits=struct.unpack('<I',struct.pack('<f',mm/28))[0]
            for quality, maximum in enumerate((4000,3200,2240,1280)):
                h=min(maximum,(4000*28//mm)//16*16)
                w=min((4672,3728,2608,1488)[quality],(4672*28//mm)//16*16)
                u=self.call(self.entries['m10v_aspect_resolution'],bits,quality,RAM,RAM+2)
                self.assertEqual(struct.unpack('<HH',u.mem_read(RAM,4)),(w,h))

    def test_text_routes_both_new_names_in_every_native_language(self):
        from unicorn import arm_const as A
        for language in range(21):
            for resource, label in [(self.caption_id-1,'XPan'),(self.caption_id,'6x7')]:
                for entry,leaf,register in [(0x540b89f8,0x53396700,A.UC_ARM_REG_R7),
                                            (0x540b8bc4,0x5339710c,A.UC_ARM_REG_R3)]:
                    with self.subTest(language=language,resource=resource,entry=hex(entry)):
                        u=self.machine();u.reg_write(A.UC_ARM_REG_R0,language)
                        u.reg_write(A.UC_ARM_REG_R7,resource);u.reg_write(A.UC_ARM_REG_R11,RAM+0xe0000)
                        seen=[]
                        def stop(uc,address,size,data):
                            if address==leaf: seen.append(address);uc.emu_stop()
                        u.hook_add(UC_HOOK_CODE,stop)
                        u.emu_start(entry,STOP,count=1000)
                        self.assertEqual(seen,[leaf])
                        ptr=u.reg_read(register)
                        header=bytes(u.mem_read(ptr,8));count=header[0]
                        text=bytes(u.mem_read(struct.unpack_from('<I',header,4)[0],count*2)).decode('utf-16le').rstrip('\0')
                        self.assertEqual(text,label)

    def test_new_crop_has_centered_screen_and_thumbnail_origins(self):
        for entry,expected in [(0x540b94e8,(80,0)),(0x540b950c,(10,0))]:
            u=self.call(entry,0,5,RAM,RAM+2)
            self.assertEqual(struct.unpack('<HH',u.mem_read(RAM,4)),expected)
        # The XPan geometry is unchanged while its caption is renamed.
        u=self.call(0x540b94e8,0,4,RAM,RAM+2)
        self.assertEqual(struct.unpack('<HH',u.mem_read(RAM,4)),(0,108))

    def test_native_grid_draw_uses_vertical_six_by_seven_mask(self):
        from unicorn import arm_const as A
        for entry,ratio,width in [(e,r,w) for e in (0x540b90a4,0x540b91cc) for r in (4,5) for w in (720,360)]:
            with self.subTest(entry=hex(entry),ratio=ratio,width=width):
                u=self.machine();view=RAM+0x2000;surface=RAM+0x3000
                u.mem_write(RAM+0x100,struct.pack('<I',RAM+0x200))
                u.mem_write(view+0x9e,b'\x01')
                for offset in [0x30,0x64]: u.mem_write(view+offset,struct.pack('<4I',0,0,width,width*2//3))
                returns={0x53525d5c:RAM+0x100,0x5354a778:ratio,0x53549958:0,
                         0x53654150:RAM+0x300,0x53654220:0,0x5339c3b0:0,
                         0x533ab9bc:0,0x5320804c:RAM+0x400,0x532081ec:RAM+0x500,
                         0x53208298:0} # Isolate mask drawing; final indicator test executes the icon renderer.
                rectangles=[]
                def native(uc,address,size,data):
                    if address==0x540b88b4:
                        sp=uc.reg_read(A.UC_ARM_REG_SP)
                        rectangles.append(struct.unpack('<5I',uc.mem_read(sp,20)))
                    elif address not in returns: return
                    uc.reg_write(A.UC_ARM_REG_R0,returns.get(address,0))
                    uc.reg_write(A.UC_ARM_REG_PC,uc.reg_read(A.UC_ARM_REG_LR))
                u.hook_add(UC_HOOK_CODE,native)
                u.reg_write(A.UC_ARM_REG_R0,view);u.reg_write(A.UC_ARM_REG_R1,surface)
                u.emu_start(entry,STOP,count=2000)
                scale=width//360
                expected=[(0,0,40*scale,240*scale,16),(320*scale,0,40*scale,240*scale,16)] if ratio==5 else [(0,0,width,54*scale,16),(0,186*scale,width,54*scale,16)]
                self.assertEqual(rectangles,expected)


if __name__ == '__main__':
    unittest.main()
