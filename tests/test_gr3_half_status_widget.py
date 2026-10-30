"""Actual MENU selection -> immediate properties -> native shooting status widget.

UI singleton getters and the property setter/getter execute original ARM. Only
screen type, final widget operations and event publication are OS/UI boundaries.
Capture SettingsModel is deliberately unavailable: selecting Half must repaint
its label before a half-press synchronizes capture settings.
"""
import hashlib
import os
from pathlib import Path
import struct
import unittest
from unicorn import UC_HOOK_CODE
from unicorn import arm_const as A
from scripts.gr3_aspect_overlay import branch
from tests.test_gr3_aspect_full_callers import FullAspectCallers as _Support
from tests.test_gr3_aspect import RAM, STOP, BASE


class HalfStatusWidgetTests(unittest.TestCase):
    setUpClass=classmethod(_Support.setUpClass.__func__)
    machine=_Support.machine
    run_entry=_Support.run_entry

    def fixture(self):
        code=bytearray(self.code)
        final=os.environ.get('M10V_HALF_STATUS_RTOS')
        if final:code=bytearray(Path(final).read_bytes())
        else:
            struct.pack_into('<I',code,0x531f920c-BASE,branch(0x531f920c,self.entries['m10v_aspect_status_icon']))
            struct.pack_into('<I',code,self.entries['m10v_aspect_half_record']-BASE+8,877)
        original=self.code;self.code=bytes(code)
        try:u=self.machine()
        finally:self.code=original
        props,owner,widget=RAM+0x10000,RAM+0x20000,RAM+0x30000
        for address,value in ((0x55063d80,1),(0x55063ed0,1),(0x55064488,1),
                              (0x55063f34,props),(owner+0x174,widget)):
            u.mem_write(address,struct.pack('<I',value))
        u.mem_write(props+0x44,b'\1') # active menu property; defer capture-model update
        calls=[]
        def boundary(m,address,size,data):
            if address in (0x53525d5c,0x5354a778):
                raise AssertionError('status read stale capture SettingsModel')
            elif address==0x5316d8d4:value=0x04000043
            elif address==0x5320aefc:value=RAM+0x40000
            elif address==0x532288b0:value=0
            elif address==0x5339b744:
                calls.append(('icon',m.reg_read(A.UC_ARM_REG_R0),m.reg_read(A.UC_ARM_REG_R1),m.reg_read(A.UC_ARM_REG_R2)));value=1
            elif address==0x533ad3c0:
                calls.append(('visible',m.reg_read(A.UC_ARM_REG_R0),m.reg_read(A.UC_ARM_REG_R1)));value=1
            elif address==0x536b93d0 or address==0x536b9f1c:
                if not m.reg_read(A.UC_ARM_REG_R0):raise AssertionError('native UI assertion')
                value=0
            else:return
            m.reg_write(A.UC_ARM_REG_R0,value);m.reg_write(A.UC_ARM_REG_PC,m.reg_read(A.UC_ARM_REG_LR))
        u.hook_add(UC_HOOK_CODE,boundary)
        return u,props,owner,widget,calls

    def test_all_seven_real_menu_selections_preserve_native_icons_except_literal_half(self):
        # Native status enums differ from the stored crop IDs. The previous
        # Half native fallback was enum3, which selected the stock 4:3 tile339.
        modes=((0,0,257),(3,2,256),(1,3,339),(2,1,337),(4,3,339),(5,3,339),(6,3,877))
        for row,(raw,native,icon) in enumerate(modes):
            with self.subTest(raw=raw):
                u,props,owner,widget,calls=self.fixture()
                self.run_entry(u,0x531b6bb8,0,row)
                self.assertEqual(bytes(u.mem_read(props+0x4c2,1)),bytes([raw]))
                u.mem_write(0x550645b8+0x14,bytes([native]))
                self.run_entry(u,0x531f9160,owner)
                self.assertEqual(calls,[('icon',widget,0x1cc,icon),('visible',widget,1)])

    def test_native_hidden_status_mode_stays_hidden_for_half(self):
        u,props,owner,widget,calls=self.fixture()
        self.run_entry(u,0x531b6bb8,0,6)
        u.mem_write(0x550645b8+0x14,b'\5')
        self.run_entry(u,0x531f9160,owner)
        self.assertEqual(calls,[('visible',widget,0)])

    def test_half_art_is_literal_half_reproducible_and_preserves_factory_frame(self):
        from scripts.generate_gr3_half_frame_icon import generate,ROOT
        from tests.test_gr3_zoom_icon_style_arm import IconStyle
        tile,payload,report=generate()
        self.assertEqual(report['label'],'Half')
        self.assertEqual(payload,(ROOT/'native/gr3/m10v_half_frame_icon.rgba').read_bytes())
        self.assertEqual(report['sha256'],hashlib.sha256(payload).hexdigest())
        IconStyle.setUpClass();stock=IconStyle().native(339)
        self.assertNotEqual(payload,stock)
        for y in range(40):
            for x in range(60):
                if 12<=x<48 and 7<=y<33:continue
                self.assertEqual(payload[(y*60+x)*4:(y*60+x+1)*4],stock[(y*60+x)*4:(y*60+x+1)*4])
