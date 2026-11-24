"""Execute ADJ highlight and stock Fn snapshot in the authenticated final BIN.

Only camera model/filesystem/graphics services are leaves. Highlight and Fn
snapshot instructions execute from the final firmware, not substituted helpers.
"""
import struct
import os
import json
from pathlib import Path
import unittest
from unicorn import UC_HOOK_CODE
from unicorn import arm_const as A
from tests import test_gr3_film_pipeline_current as pipeline
from tests.test_gr3_isp_base import StockISP


class DetailSelectionArmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pipeline.CurrentFilmPipelineTests.setUpClass.__func__(cls)
        # Developer-only linked-runtime check; release verification omits this
        # and executes the authenticated final BIN unchanged.
        overlay = os.environ.get('M10V_DETAIL_RUNTIME')
        if overlay:
            from scripts.build_gr3_native_detail import branch
            folder = Path(overlay)
            cls.manifest = json.loads((folder / 'm10v-library-arm.json').read_text())
            image = bytearray(cls.image)
            runtime = (folder / 'm10v-library-arm.bin').read_bytes()
            offset = cls.manifest['base'] - 0x53000000
            image[offset:offset + len(runtime)] = runtime
            for address, target in (
                (0x531a0ba0, cls.manifest['symbols']['m10v_tone_menu_adj_select']),
                *(([(0x531a4a80,cls.manifest['detail']['entries']['adj_fn'])]) if 'adj_fn' in cls.manifest['detail']['entries'] else []),
                (0x532c2c80, cls.manifest['appended_slots']['entries']['index']),
                (0x532c2a9c, cls.manifest['appended_slots']['entries']['count']),
                (0x531acc04, cls.manifest['detail']['entries']['tone_snapshot']),
                (0x531acc14, cls.manifest['detail']['entries']['tone_kind'])):
                struct.pack_into('<I', image, address - 0x53000000,
                    branch(address, target, address in (0x531acc04, 0x531acc14)))
            cls.image = bytes(image)
    call = pipeline.CurrentFilmPipelineTests.call
    publish_owner = pipeline.CurrentFilmPipelineTests.publish_owner

    def selection_machine(self):
        e = StockISP(self.image)
        state = bytearray.fromhex(self.manifest['initial_state_hex'])
        data = e.alloc(len(state))
        e.u.mem_write(data, bytes(state))
        self.publish_owner(e, data)
        controller, ui, event = [e.alloc(n) for n in (0x280, 0x1a0, 8)]
        e.w32(controller, 0x53b394e0)
        e.w32(controller + 0x124, 0x02000000)
        rows=e.alloc(0x80);e.w32(controller+0x1f0,rows)
        self.adj_row=[14];self.adj_function=[12];self.queued_routes=[]
        self.real_adj_events=False
        e.w32(event, 0x35)
        model = 0x55068200
        active, writes = [27], []
        self.film_trace = []
        fs, link, manager = [e.alloc(n) for n in (0x24, 4, 12)]
        e.w32(manager + 8, link); e.w32(link, fs)
        e.u.mem_write(fs + 0x20, b'\1')
        journal = {'fail': False, 'files': {}, 'rollback': [], 'state': state}

        def service(u, address, size, unused):
            if address == self.manifest['symbols'].get('m10v_debug_log'):
                args=[u.reg_read(getattr(A,f'UC_ARM_REG_R{i}')) for i in range(4)]
                last=struct.unpack('<I',u.mem_read(u.reg_read(A.UC_ARM_REG_SP),4))[0]
                self.film_trace.append((args[0],args[1],args[2],args[3],last));result=1
            elif address in (0x5320ad88, 0x5320b31c): result = 0x55006000
            elif address == 0x5320ba9c: result = model
            elif address == 0x5320b5bc: result = 0x55006000
            elif address == 0x531a2820: result = self.adj_function[0]
            elif address == 0x53394820: result = self.adj_row[0]
            elif address == 0x5316c9d8:
                self.queued_routes.append(tuple(u.reg_read(getattr(A,f'UC_ARM_REG_R{i}')) for i in range(3)));result=0
            elif address in (self.manifest['settings_menu']['exports'].get('m10v_ab_adj_exit_original'),
                             self.manifest['settings_menu']['exports'].get('m10v_ab_adj_refresh_original')): result=0
            elif address == 0x532bd6b4: result = active[0]
            elif address == 0x532bd6d4: result = 0
            elif address == 0x532c26c0:
                active[0] = u.reg_read(A.UC_ARM_REG_R1)
                writes.append(active[0]); result = 0
            elif address == 0x53828014: result = manager
            elif address == self.manifest['symbols'].get('m10v_companion_ui_storage_enter'): result = 1
            elif address in (self.manifest['symbols'].get('m10v_companion_ui_storage_current'),
                             self.manifest['symbols'].get('m10v_companion_ui_storage_leave')): result = 1
            elif address in (0x53825fa8, 0x53825648):
                name = bytes(u.mem_read(u.reg_read(A.UC_ARM_REG_R1), 12)).split(b'\0')[0]
                size, ptr = u.reg_read(A.UC_ARM_REG_R2), u.reg_read(A.UC_ARM_REG_R3)
                if address == 0x53825fa8:
                    result = int(not journal['fail'])
                    if result: journal['files'][name] = bytes(u.mem_read(ptr, size))
                else:
                    result = int(name in journal['files'])
                    if result:
                        saved = journal['files'][name]
                        u.mem_write(ptr, saved)
                        state[:] = saved
            elif address == 0x5339ee0c:
                journal['rollback'].append(u.reg_read(A.UC_ARM_REG_R1)); result = 0
            elif address == self.manifest['symbols']['m10v_camera_library_load']:

                u.mem_write(u.reg_read(A.UC_ARM_REG_R0), bytes(state)); result = 0
            elif address == self.manifest['settings_menu']['exports']['m10v_ab_adj_event_original']:
                if self.real_adj_events:return  # Execute the genuine native ADJ event body.
                result = 0
            else: return
            u.reg_write(A.UC_ARM_REG_R0, result)
            u.reg_write(A.UC_ARM_REG_PC, u.reg_read(A.UC_ARM_REG_LR))
        e.u.hook_add(UC_HOOK_CODE, service)
        self.journal = journal
        return e, controller, ui, event, active, writes

    def test_fn_snapshots_each_highlight_without_activating_it(self):
        e, controller, ui, event, active, writes = self.selection_machine()
        for row, tone in ((14, 25), (15, 26), (14, 25)):
            e.call(0x531a0ba0, controller, row)
            self.assertEqual(self.call(e, 'm10v_camera_library_adj_tone'), tone)
            e.call(0x531acbe4, ui)
            self.assertEqual(e.u.mem_read(ui + 0x198, 1)[0], tone,
                'Fn opened the active film instead of the highlighted film')
            self.assertEqual(active, [27])
            self.assertEqual(writes, [])
        self.assertEqual(e.assertions, [], 'Fn must not send appended tones to the stock 12-kind switch')

    def test_cancel_discards_candidate_and_next_fn_uses_active_tone(self):
        e, controller, ui, event, active, writes = self.selection_machine()
        e.call(0x531a0ba0, controller, 15)
        e.call(self.manifest['symbols']['m10v_hdf_adj_event'], controller, event)
        self.assertEqual(self.call(e, 'm10v_camera_library_adj_tone'), 0)
        e.call(0x531acbe4, ui)
        self.assertEqual(e.u.mem_read(ui + 0x198, 1)[0], 27)
        self.assertEqual(writes, [])

    def test_each_fn_edit_persists_its_frozen_slot_and_failed_save_restores_slider(self):
        e, controller, ui, event, active, writes = self.selection_machine()
        slider = e.alloc(4)
        e.w32(ui + 0x164, slider)
        for row, target, grain in ((14, 0, 3), (15, 1, 2)):
            e.call(0x531a0ba0, controller, row)
            e.call(0x531acbe4, ui)
            before = bytes(self.journal['state'])
            # A later live highlight cannot retarget an already open Fn rail.
            e.call(0x531a0ba0, controller, 16)
            self.assertEqual(self.call(e, 'm10v_detail_control', 2, ui, (3 << 8) | grain), 1)
            after = bytes(self.journal['state'])
            self.assertEqual(after[14 + target * 8], grain)
            for other in range(10):
                if other != target:
                    self.assertEqual(after[12 + other * 8:20 + other * 8], before[12 + other * 8:20 + other * 8])
            committed = dict(self.journal['files'])
            self.journal['fail'] = True
            self.assertEqual(self.call(e, 'm10v_detail_control', 2, ui, (3 << 8) | 1), 0)
            self.assertEqual(self.journal['files'], committed)
            self.assertEqual(bytes(self.journal['state']), after)
            self.assertEqual(self.journal['rollback'][-1], grain)
            self.journal['fail'] = False
        self.assertEqual(writes, [])
        self.assertEqual(active, [27])

    def test_factory_fn_and_raw_development_keep_the_stock_tone_snapshot(self):
        e, controller, ui, event, active, writes = self.selection_machine()
        active[0] = 16
        e.call(0x531a0ba0, controller, 0)
        e.call(0x531acbe4, ui)
        self.assertEqual(e.u.mem_read(ui + 0x198, 1)[0], 16)
        self.assertEqual(e.u.mem_read(ui + 0x19a, 1)[0], 5)
        e.call(0x531a0ba0, controller, 14)
        e.u.mem_write(0x55068200 + 0x1b, b'\1')
        e.call(0x531acbe4, ui)
        self.assertEqual(e.u.mem_read(ui + 0x198, 1)[0], 16)
        self.assertEqual(writes, [])
        self.assertEqual(e.assertions, [])

    def test_raw_detail_controller_ignores_candidate_even_when_shooting_model_is_live(self):
        e, controller, ui, event, active, writes = self.selection_machine()
        active[0] = 16
        e.call(0x531a0ba0, controller, 14)
        e.u.mem_write(ui + 0x19b, b'\1')
        e.call(0x531acbe4, ui)
        self.assertEqual(e.u.mem_read(ui + 0x198, 1)[0], 16)
        self.assertEqual(e.assertions, [])

    def test_diagnostic_records_match_the_executed_fn_target_and_journal_write(self):
        if not self.manifest.get('debug_mode'):
            self.skipTest('diagnostic-only trace is absent from formal builds')
        e,controller,ui,event,active,writes=self.selection_machine()
        e.call(0x531a0ba0,controller,14)
        e.call(0x531acbe4,ui)
        self.assertEqual(self.call(e,'m10v_detail_control',2,ui,(3<<8)|3),1)
        self.assertIn((360,ui,27,25,25),self.film_trace)
        self.assertIn((362,ui,2,(3<<8)|3,0),self.film_trace)
        identity=[r for r in self.film_trace if r[0]==363]
        self.assertEqual(identity[-1][2],struct.unpack_from('<H',bytes.fromhex(self.manifest['initial_state_hex']),12)[0])
        written=[r for r in self.film_trace if r[0]==364]
        self.assertEqual(written[-1][1:4],(ui,0,0))
        self.assertEqual(self.journal['state'][14],3)

    def construct_native_detail_fields(self,e,ui):
        # Execute the genuine constructor's complete byte-field initialization,
        # stopping before its graphical callback registration leaf.
        # Original BaseController ctor establishes sentinel routes and128=1.
        e.u.reg_write(A.UC_ARM_REG_R5,ui)
        e.u.reg_write(A.UC_ARM_REG_R6,0)
        e.u.emu_start(0x5316c92c,0x5316c980,count=100)
        e.u.emu_start(0x5316c984,0x5316c998,count=100)
        self.assertEqual(struct.unpack('<I',e.u.mem_read(ui+0x124,4))[0],0x10000000)
        self.assertEqual(e.u.mem_read(ui+0x128,1),b'\1')
        self.assertEqual(struct.unpack('<I',e.u.mem_read(ui+0x150,4))[0],0x10000000)
        e.u.reg_write(A.UC_ARM_REG_R4,ui)
        e.u.reg_write(A.UC_ARM_REG_R12,0)
        e.u.emu_start(0x531afdf4,0x531afe28,count=100)
        self.assertEqual(e.u.mem_read(ui+0x198,1),b'\x0b')

    def enter_native_detail_route(self,e,ui,route,parent):
        # Execute the actual BaseController route/parent stores before virtual enter.
        e.u.reg_write(A.UC_ARM_REG_R4,ui)
        e.u.reg_write(A.UC_ARM_REG_R5,route)
        e.u.reg_write(A.UC_ARM_REG_R2,parent)
        e.u.emu_start(0x5316dfe8,0x5316dff4,count=10)

    def test_real_native_fn_route_keeps_selected_row_across_adj_exit_and_repeated_snapshot(self):
        e,c,ui,event,active,writes=self.selection_machine()
        for row,tone,slot,grain in ((14,25,0,3),(15,26,1,2)):
            self.adj_row[0]=row
            e.call(0x531a0ba0,c,row)
            self.real_adj_events=True
            payload=e.alloc(8);e.u.mem_write(payload,b'\x02'+bytes(7))
            e.w32(event,0x1b);e.w32(event+4,payload)
            e.call(self.manifest['symbols']['m10v_hdf_adj_event'],c,event)
            # Genuine531a4db8 reads physical Fn1b/payload2, calls531a4a80,
            # switches the actual native function and queues the detail route.
            self.assertEqual(self.queued_routes[-1],(c,0x02000014,0x02000000))
            if self.manifest.get('debug_mode') and 'adj_fn' in self.manifest['detail']['entries']:
                self.assertIn((377,c,row,tone,slot),self.film_trace)
                self.assertIn((378,c,tone,tone,0),self.film_trace)
            e.call(self.manifest['symbols']['m10v_settings_controller_ab_adj_exit'],c)
            self.assertEqual(self.call(e,'m10v_camera_library_adj_tone'),0)
            self.construct_native_detail_fields(e,ui)
            e.call(0x531acbe4,ui)
            self.assertEqual(e.u.mem_read(ui+0x198,1)[0],tone)
            self.enter_native_detail_route(e,ui,0x02000014,0x02000000)
            e.call(0x531acbe4,ui)  # Native Ready snapshots a second time.
            self.assertEqual(e.u.mem_read(ui+0x198,1)[0],tone)
            self.assertEqual(self.call(e,'m10v_detail_control',2,ui,(3<<8)|grain),1)
            self.assertEqual(self.journal['state'][14+slot*8],grain)
        self.assertEqual(writes,[])
        self.assertEqual(active,[27])

    def test_previous_fn_handoff_is_not_inherited_by_reused_native_detail_allocation(self):
        e,c,ui,event,active,writes=self.selection_machine()
        self.adj_row[0]=14
        e.call(0x531a4a80,c,2)
        e.call(self.manifest['symbols']['m10v_settings_controller_ab_adj_exit'],c)
        e.call(0x531acbe4,ui)
        self.assertEqual(e.u.mem_read(ui+0x198,1)[0],25)
        self.construct_native_detail_fields(e,ui)
        e.call(0x531acbe4,ui)  # A newly constructed unrelated detail has no ADJ handoff.
        self.assertEqual(e.u.mem_read(ui+0x198,1)[0],27)

    def test_cached_detail_entered_from_menu_does_not_reuse_the_previous_adj_handoff(self):
        e,c,ui,event,active,writes=self.selection_machine()
        self.adj_row[0]=14
        e.call(0x531a4a80,c,2)
        e.call(self.manifest['symbols']['m10v_settings_controller_ab_adj_exit'],c)
        self.construct_native_detail_fields(e,ui)
        self.enter_native_detail_route(e,ui,0x02000014,0x02000000)
        e.call(0x531acbe4,ui)
        self.assertEqual(e.u.mem_read(ui+0x198,1)[0],25)
        # BaseController changes route/parent on cached-page reentry; no ctor.
        self.enter_native_detail_route(e,ui,0x02000014,0x02000012)
        e.call(0x531acbe4,ui)
        self.assertEqual(e.u.mem_read(ui+0x198,1)[0],27)
        self.assertEqual(writes,[])
