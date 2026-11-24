"""Extended ADJ bank -> genuine physical Fn -> frozen native detail target.

Assign and focus slots 6..9 through the installed adapter. The real slot-type
resolver and native list-cursor getter run; model/filesystem/graphics are leaves.
"""
import json
import os
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest
from unicorn.arm_const import *
from tests.test_gr3_adj_extra_camera import CameraAdjTests, OWNER, ADJ, RETURN, REGS
from tests.test_gr3_detail_selection_arm import DetailSelectionArmTests


class _FnCamera(CameraAdjTests):
    def setUp(self):
        self.fn_mode = False
        super().setUp()
        self.fn_mode = True
        folder = Path(os.environ['M10V_TEST_ADJ_FIRMWARE_DIR'])
        self.manifest = json.loads((folder/'M10V-runtime-manifest.json').read_text())
        self.state_bytes = bytearray.fromhex(self.manifest['initial_state_hex'])
        self.active_tone = 29
        self.tone_writes = []
        self.film_trace = []
        self.save_fail = False
        self.put(ADJ+0x124,0x02000000)
        # The authenticated UI journal cache is already published on entry;
        # this test isolates navigation and Fn, not initial SD cache loading.
        self.put(OWNER+0x213c,0x3856504d)
        self.put(OWNER+0x2140,2)
        self.u.mem_write(OWNER+0x2144,bytes(self.state_bytes))
        self.u.mem_write(0x55068200+0x1b,b'\0')

    def service(self,u,address,size,data):
        if not self.fn_mode:
            return super().service(u,address,size,data)
        a,b,c,d=[u.reg_read(r)for r in REGS]
        result=None
        if address==0x5320ba9c:result=0x55068200
        elif address==0x5320b5bc:result=0x55026000
        elif address==0x532bd6b4:result=self.active_tone
        elif address==0x532bd6d4:result=0
        elif address==0x532c26c0:
            self.tone_writes.append(b);self.active_tone=b;result=0
        elif address in (0x531a4a80,0x53394820):
            return  # Execute installed Fn adapter and genuine native cursor getter.
        elif address==self.symbols['m10v_camera_library_shooting_count']:
            return  # Use the actual configured film count, not the old strip fixture's 22.
        elif address==self.symbols['m10v_camera_library_load']:
            u.mem_write(a,bytes(self.state_bytes));result=0
        elif address in (self.symbols.get('m10v_companion_ui_storage_enter'),
                         self.symbols.get('m10v_companion_ui_storage_current'),
                         self.symbols.get('m10v_companion_ui_storage_leave')):result=1
        elif address in (0x53825648,0x53825fa8) and c==len(self.state_bytes):
            name=bytes(u.mem_read(b,12)).split(b'\0')[0]
            if address==0x53825fa8:
                result=int(not self.save_fail)
                if result:self.files[name]=bytes(u.mem_read(d,c))
            else:
                result=int(name in self.files)
                if result:
                    u.mem_write(d,self.files[name]);self.state_bytes[:]=self.files[name]
        elif address==self.symbols.get('m10v_debug_log'):
            fifth=int.from_bytes(u.mem_read(u.reg_read(UC_ARM_REG_SP),4),'little')
            self.film_trace.append((a,b,c,d,fifth));result=1
        elif address in (0x5339ee0c,0x53396f80):result=0
        if result is None:return super().service(u,address,size,data)
        u.reg_write(UC_ARM_REG_R0,result)
        u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))


class ExtendedAdjFnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.environ.get('M10V_TEST_ADJ_FIRMWARE_DIR'):
            raise unittest.SkipTest('final firmware directory required')
        _FnCamera.setUpClass()

    def camera(self,logical_slot=9,function=12):
        cam=_FnCamera();cam.setUp()
        self.assertEqual(cam.call('assign',logical_slot,function),1)
        cam.u.mem_write(ADJ+0x1f4,b'\4')
        cam.call('initial_render',ADJ)
        # Real installed extra icon callback switches the saved cursor bank.
        icon=cam.allocations[-1]+0xf0
        cam.u.mem_write(0x55027504,cam.bindings[icon])
        cam.put(0x55027500,0x55027504)
        cam.execute(0x531a1874,RETURN,0x55027500)
        self.assertEqual(cam.call('virtual_focus',ADJ),1)
        self.assertEqual(cam.execute(0x531a2820,RETURN,ADJ,logical_slot-6),function if function<=20 else 0)
        return cam

    def open_fn(self,cam,row):
        # Native OptionListView's highlighted cursor, distinct from active look.
        # Do not stub the getter used by the production Fn route.
        cam.u.mem_write(0x55024000+0x110,struct.pack('<H',row))
        self.assertEqual(cam.execute(0x53394820,RETURN,0x55024000),row)
        payload=0x55079000;cam.u.mem_write(payload,b'\x02'+bytes(7))
        event=payload+16;cam.u.mem_write(event,struct.pack('<II',0x1b,payload))
        cam.execute(cam.symbols['m10v_hdf_adj_event'],RETURN,ADJ,event)
        self.assertEqual(cam.routes[-1],(ADJ,0x02000014,0x02000000))
        cam.execute(cam.symbols['m10v_settings_controller_ab_adj_exit'],RETURN,ADJ)
        return self.snapshot_detail(cam)

    def snapshot_detail(self,cam):
        ui=0x55070000
        DetailSelectionArmTests.construct_native_detail_fields(self,SimpleNamespace(u=cam.u),ui)
        cam.execute(0x531acbe4,RETURN,ui)
        return ui

    def test_extended_image_control_fn_edits_hovered_film_without_activation(self):
        for logical_slot in (6,7,8,9):
            for slot in range(5):
                row,tone,grain=14+slot,25+slot,1+slot%3
                with self.subTest(logical_slot=logical_slot,row=row):
                    cam=self.camera(logical_slot)
                    ui=self.open_fn(cam,row)
                    self.assertEqual(cam.u.mem_read(ui+0x198,1)[0],tone,
                        'extended ADJ Fn incorrectly opened the confirmed active film')
                    previous=bytes(cam.state_bytes)
                    result=cam.execute(cam.symbols['m10v_detail_control'],RETURN,2,ui,(3<<8)|grain)
                    self.assertEqual(result,1)
                    self.assertEqual(cam.state_bytes[14+slot*8],grain)
                    for other in range(10):
                        if other!=slot:self.assertEqual(cam.state_bytes[12+other*8:20+other*8],previous[12+other*8:20+other*8])
                    self.assertEqual(cam.active_tone,29)
                    self.assertEqual(cam.tone_writes,[])

    def test_effects_shortcut_keeps_current_film_and_ignores_unrelated_cursor(self):
        cam=self.camera(function=26)
        cam.u.mem_write(0x55024000+0x110,struct.pack('<H',14))
        event=0x55079000;cam.u.mem_write(event,struct.pack('<II',0xd8,0))
        self.assertEqual(cam.execute(cam.symbols['m10v_adj_extra_camera_event'],RETURN,ADJ,event),1)
        self.assertEqual(cam.routes[-1],(ADJ,0x02000014,0x02000000))
        cam.execute(cam.symbols['m10v_settings_controller_ab_adj_exit'],RETURN,ADJ)
        ui=self.snapshot_detail(cam)
        self.assertEqual(cam.u.mem_read(ui+0x198,1)[0],29)
        self.assertEqual(cam.active_tone,29)
        self.assertEqual(cam.tone_writes,[])


def load_tests(loader,tests,pattern):
    return loader.loadTestsFromTestCase(ExtendedAdjFnTests)
