"""Run the r3 ROM's menu descriptor and FocusModel callers with source adapters.

Only singleton/model ownership and message publication cross the emulated boundary;
menu routing, selection setter, native rectangle/size writers and AF dispatch run.
"""
import importlib.util
import json
import os
import struct
import unittest
from pathlib import Path
from unicorn import UC_HOOK_CODE
from unicorn import arm_const as A
from tests import test_gr3_aspect as support
BASE, RAM, STOP, ROOT = support.BASE, support.RAM, support.STOP, support.ROOT


class FullAspectCallers(unittest.TestCase):
    machine = support.AspectTests.machine

    @classmethod
    def setUpClass(cls):
        cls.r3 = (ROOT/'builds/gr3-half-frame-r3-debug-20261029/final-rtos.bin').read_bytes()
        spec = importlib.util.spec_from_file_location('aspect_full_overlay', ROOT/'scripts/gr3_aspect_overlay.py')
        overlay = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(overlay)
        module, cls.entries = overlay.build_module()
        # Rebind source over the actual r3 ROM, preserving all native caller patches.
        code = bytearray(cls.r3)
        code[overlay.MODULE-BASE:overlay.END-BASE] = bytes(overlay.END-overlay.MODULE)
        code[overlay.MODULE-BASE:overlay.MODULE-BASE+len(module)] = module
        def word(address, value):
            struct.pack_into('<I', code, address-BASE, value)
        for site, name in overlay.HOOKS.items():
            word(site, overlay.branch(site, cls.entries['m10v_aspect_'+name]))
        for site,(name,preimage) in overlay.NATIVE_CLASS_HOOKS.items():
            self_word=struct.unpack_from('<I',code,site-BASE)[0]
            if self_word!=preimage:raise AssertionError('native class-load preimage differs')
            word(site,overlay.branch(site,cls.entries['m10v_aspect_'+name]))
        report = json.loads((ROOT/'.runtime/grlife-current/reconstruction/firmware_store/templates/urban160-link-report.json').read_text())
        redirects = {'gr_dng_default_crop_tags':'dng_tags','open_gate_mask_is_active':'mask_active',
                     'draw_overlay':'draw','gr3_sro_af_bounds_test02':'af_bounds',
                     'gr3_sro_write_active_locked':'private_active'}
        for row in report['relocations']:
            if row['type'] in ('R_ARM_CALL','R_ARM_JUMP24') and row['symbol'] in redirects:
                word(row['place'], overlay.branch(row['place'],cls.entries['m10v_aspect_'+redirects[row['symbol']]],row['type']=='R_ARM_CALL'))
        # The live descriptor's three callbacks share this source-owned values table.
        for site in (0x531b4e08,0x531b6bd0,0x531b82f8):
            target = cls.entries['m10v_aspect_values']
            for at, half, opcode in ((site,target&65535,0xe3003000),(site+4,target>>16,0xe3403000)):
                word(at,opcode|((half&0xf000)<<4)|(half&0xfff))
        target=cls.entries['m10v_aspect_classes']
        for site,register,condition in ((0x534371dc,2,14),(0x53669450,3,9)):
            for at,half,opcode in ((site,target&65535,0x03000000),(site+8,target>>16,0x03400000)):
                word(at,(condition<<28)|opcode|(register<<12)|((half&0xf000)<<4)|(half&0xfff))
        final=os.environ.get('M10V_FULL_CALLER_RTOS')
        cls.code = Path(final).read_bytes() if final else bytes(code)

    def device(self, ratio=0, mag=0x3f800000):
        u=self.machine()
        u.mem_write(RAM+0x304,struct.pack('<I',RAM+0x400))
        u.mem_write(RAM+0x444,b'\1') # active properties avoid unrelated import validation
        u.mem_write(RAM+0x8c2,bytes([ratio]))
        u.mem_write(RAM+0x8c4,struct.pack('<I',mag))
        events=[]
        returns={0x5320ad88:RAM+0x80,0x5320b31c:RAM+0x300,0x5320b67c:RAM+0x300,
                 0x53243e40:0,0x5320aefc:RAM+0x100,0x532288b0:0}
        def boundary(m,address,size,data):
            if address==0x536b93d0:
                events.append(('assert',m.reg_read(A.UC_ARM_REG_R3),m.reg_read(A.UC_ARM_REG_LR)))
                m.emu_stop()
            elif address==0x5339e7a0:
                events.append(('caption',m.reg_read(A.UC_ARM_REG_R1)))
                m.reg_write(A.UC_ARM_REG_PC,m.reg_read(A.UC_ARM_REG_LR))
            elif address in returns:
                m.reg_write(A.UC_ARM_REG_R0,returns[address])
                m.reg_write(A.UC_ARM_REG_PC,m.reg_read(A.UC_ARM_REG_LR))
        u.hook_add(UC_HOOK_CODE,boundary)
        return u,events

    def run_entry(self,u,entry,*args):
        u.reg_write(A.UC_ARM_REG_LR,STOP)
        for reg,value in zip((A.UC_ARM_REG_R0,A.UC_ARM_REG_R1,A.UC_ARM_REG_R2,A.UC_ARM_REG_R3),args):
            u.reg_write(reg,value)
        u.emu_start(entry,STOP,count=50000)
        self.assertEqual(u.reg_read(A.UC_ARM_REG_PC),STOP,'caller did not return')

    def test_live_menu_descriptor_exposes_all_seven_rows_and_selection(self):
        descriptor=0x53b3cf00
        count,caption,select,checked=[struct.unpack_from('<I',self.code,descriptor-BASE+off)[0] for off in (8,16,24,32)]
        u,events=self.device()
        self.run_entry(u,count)
        self.assertEqual(u.reg_read(A.UC_ARM_REG_R0),7)
        for row,raw in enumerate((0,3,1,2,4,5,6)):
            with self.subTest(row=row,raw=raw):
                u,events=self.device()
                self.run_entry(u,caption,0,RAM+0x9000,row)
                self.assertEqual(events[0][0],'caption')
                self.assertNotEqual(events[0][1],0,'blank menu row')
                if raw==6:
                    half_record=self.code.index(struct.pack('<I',0x48463741))
                    self.assertEqual(events[0][1],struct.unpack_from('<I',self.code,half_record+4)[0])
                self.run_entry(u,select,0,row)
                self.assertEqual(u.mem_read(RAM+0x8c2,1),bytes([raw]))
                self.run_entry(u,checked,0,row)
                self.assertEqual(u.reg_read(A.UC_ARM_REG_R0),1)

    def test_menu_selected_raw_two_reaches_binary_model_converter(self):
        for historical in (False,True):
            with self.subTest(historical=historical):
                if historical:self.code=self.r3
                u,events=self.device()
                select=struct.unpack_from('<I',self.code,0x53b3cf18-BASE)[0]
                self.run_entry(u,select,0,3)
                self.run_entry(u,0x53245260,RAM+0x300)
                self.assertEqual(u.reg_read(A.UC_ARM_REG_R0),2)
                u.reg_write(A.UC_ARM_REG_LR,STOP)
                u.emu_start(0x536a3200,STOP,count=50000)
                if historical:
                    self.assertEqual(events,[('assert',115,0x536a3250)])
                else:
                    self.assertFalse(events)
                    self.assertEqual(u.reg_read(A.UC_ARM_REG_R0),0)
                    self.assertEqual(u.reg_read(A.UC_ARM_REG_PC),STOP)

    def test_full_focusmodel_callers_accept_all_ratios(self):
        for ratio in range(7):
            for mode in (0,14,15):
                for mag in (0x3f800000,0x3fa00000,0x3fe49249):
                    with self.subTest(ratio=ratio,mode=mode,mag=hex(mag)):
                        u,events=self.device(ratio,mag)
                        out=RAM+0x9000
                        self.run_entry(u,0x532afd48,out,0,mode)
                        self.assertFalse(events)
                        w,h=struct.unpack('<2I',u.mem_read(out,8))
                        self.assertGreater(w,0);self.assertGreater(h,0)
                        self.assertLessEqual(w,720);self.assertLessEqual(h,480)
                        self.run_entry(u,0x532afbb4,0,out)
                        self.assertFalse(events)
                        x,y,w,h=struct.unpack('<4I',u.mem_read(out,16))
                        self.assertGreater(w,0);self.assertGreater(h,0)
                        self.assertLessEqual(x+w,720);self.assertLessEqual(y+h,480)

    def test_full_live_refresh_raw_two_uses_same_full_backing_in_common_and_focus(self):
        # This is the actual common caller; its r5 is CLASS, not raw ratio.
        # raw2 -> class0 now shares the verified nativefull backing with Half.
        # The16:9 crop is a displaymask; no mode2 source recrop is permitted.
        for mag,q13 in ((0x3f800000,0x2000),(0x3fa00000,0x2800),(0x3fe49249,0x38f6)):
            for path,kind,override in __import__('itertools').product(('common','focus'),(0,1),(0,1)):
                with self.subTest(mag=hex(mag),path=path,kind=kind,override=override):
                    u,events=self.device(2,mag)
                    u.reg_write(A.UC_ARM_REG_C1_C0_2,0xf00000)
                    u.reg_write(A.UC_ARM_REG_FPEXC,0x40000000)
                    context=RAM+0x4000
                    owner=RAM+0x10000
                    root=RAM+0x11000
                    u.mem_write(owner+8,struct.pack('<I',context))
                    u.mem_write(root,struct.pack('<I',RAM+0x300))
                    native=(2949120,1966080,0,0)
                    focal=(1800000,1200000,574560,383040)
                    wide=(2949120,1105920,0,430080)
                    u.mem_write(context+4,struct.pack('<4I',*native))
                    u.mem_write(context+0x24,struct.pack('<4I',*focal))
                    u.mem_write(context+0x54,struct.pack('<4I',*wide))
                    returns={0x536659ac:owner,0x53666200:0,0x5366632c:0,
                             0x53525d5c:root,0x5354a778:2,0x53549958:kind,
                             0x53654150:RAM+0x12000,0x53654220:override,
                             0x536ae71c:0,0x536ae870:1}
                    def boundary(m,address,size,data):
                        if address==0x5354a7bc:
                            m.reg_write(A.UC_ARM_REG_S0,mag)
                            m.reg_write(A.UC_ARM_REG_PC,m.reg_read(A.UC_ARM_REG_LR))
                        elif address in returns:
                            m.reg_write(A.UC_ARM_REG_R0,returns[address])
                            m.reg_write(A.UC_ARM_REG_PC,m.reg_read(A.UC_ARM_REG_LR))
                    u.mem_write(RAM+0x12000+0x6c2,b'\1') # Original forcedwide class.
                    u.hook_add(UC_HOOK_CODE,boundary)
                    if path=='common':
                        self.run_entry(u,0x53437170)
                    else:
                        self.run_entry(u,0x53669424,owner+0x74d,1) # Actual source class mapper.
                        u.mem_write(owner+0x756,b'\0')
                        u.mem_write(owner+0x758,struct.pack('<I',q13))
                        u.mem_write(owner+0xa94,struct.pack('<I',context))
                        u.reg_write(A.UC_ARM_REG_R4,owner)
                        u.emu_start(0x53445054,0x53445088,count=50000)
                        self.assertEqual(u.reg_read(A.UC_ARM_REG_PC),0x53445088)
                    self.assertFalse(events)
                    expected=wide if kind==1 or override else native if q13==0x2000 else focal
                    self.assertEqual(struct.unpack('<4I',u.mem_read(context+0x64,16)),expected)


    def test_original_r3_menu_has_half_row_after_blank_raw_two_row(self):
        self.code=self.r3
        descriptor=0x53b3cf00
        count=struct.unpack_from('<I',self.code,descriptor-BASE+8)[0]
        caption=struct.unpack_from('<I',self.code,descriptor-BASE+16)[0]
        u,events=self.device()
        self.run_entry(u,count)
        self.assertEqual(u.reg_read(A.UC_ARM_REG_R0),7)
        half_record=self.code.index(struct.pack('<I',0x48463741))
        half_id=struct.unpack_from('<I',self.code,half_record+4)[0]
        for row,expected in ((3,0),(6,half_id)):
            u,events=self.device()
            self.run_entry(u,caption,0,RAM+0x9000,row)
            self.assertEqual(events,[('caption',expected)])

    def test_original_r3_full_small_af_caller_reproduces_reported_assertion(self):
        self.code=self.r3
        u,events=self.device(2)
        # Deliberately expect the historic failure without letting emulation abort.
        for reg,value in ((A.UC_ARM_REG_R0,RAM+0x9000),(A.UC_ARM_REG_R2,14)):
            u.reg_write(reg,value)
        u.emu_start(0x532afd48,STOP,count=50000)
        self.assertEqual(events,[('assert',1461,0x532afec0)])


if __name__=='__main__':
    unittest.main()
