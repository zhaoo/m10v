"""Exact final BIN: real MENU/ADJ models, selectors, and still frame sizing.

Singleton getters, InputPropertyModel setters/readback, installed MENU/ADJ
callbacks, native event enqueue, and frame sizing execute from final firmware.
The hub test bounds unrelated feature services, final painting, and OS route
transitions. The roll test uses the existing SD/RTOS service fixture while
executing journal recovery and the actual AppMain roll worker. This is offline
ABI/state/geometry evidence, not camera event delivery, output, or performance.
"""
import struct
import json
import os
from pathlib import Path
import unittest

from tests import test_gr3_half_setting_final as support
from tests import test_gr3_aspect_adj as adj


class FormalAspectSelection(unittest.TestCase):
    setUpClass = classmethod(support.FinalHalfSetting.setUpClass.__func__)

    def setUp(self):
        support.FinalHalfSetting.setUp(self)
        camera = self.camera
        # Use the real initialized singleton getters instead of replacing all
        # model owners with one synthetic model. The selected property copy is
        # the native InputPropertyModel at 0x55063f30.
        for address in (0x5320ad88, 0x5320b31c, 0x5320b67c, 0x5320aefc):
            del camera.boundaries[address]
        for flag in (0x55063d80, 0x55063ed0, 0x55063e54, 0x550643ac):
            camera.words(flag, 1)
        camera.words(0x55063f34, support.PROPERTIES)
        self.model = 0x55063f30
        descriptor = adj.descriptor_address(self.rom) + 4 * 0x44
        self.adj_apply = camera.read_words(descriptor + 0x28, 1)[0]
        self.adj_checked = camera.read_words(descriptor + 0x20, 1)[0]

    def ratio(self):
        return self.camera.call(0x53245260, self.model)

    def dimensions(self):
        camera = self.camera
        output = 0x550a8000
        camera.u.reg_write(camera.A.UC_ARM_REG_S0, 0x3f800000)
        camera.call(0x536a2a30, 0, 0, self.ratio(), output, output + 2)
        return struct.unpack('<HH', camera.u.mem_read(output, 4))

    def test_installed_hub_opt_in_survives_reopening_and_native_aspect_route(self):
        camera, symbols = self.camera, self.symbols
        for address in (0x5319aa68, 0x5316c8d4, 0x5316d354):
            camera.boundaries[address] = lambda: 0
        # Other feature services and final painting are unrelated boundaries;
        # the real owner constructor and Half init/set/read remain installed.
        for name in ('m10v_camera_library_preview_init', 'm10v_companion_ui_init',
                     'm10v_adj_extra_camera_init', 'm10v_guides_camera_init',
                     'm10v_torn_init', 'm10v_settings_view_hub_create',
                     'm10v_camera_library_load', 'm10v_isp_effects_camera_snapshot',
                     'm10v_border_camera_snapshot', 'm10v_hdf_cached',
                     'm10v_torn_state', 'm10v_guides_camera_mode'):
            if name in symbols:
                camera.boundaries[symbols[name]] = lambda: 0
        camera.boundaries[symbols['m10v_settings_view_hub_artwork']] = lambda: 8
        camera.boundaries[symbols['m10v_settings_view_hub']] = lambda: 1
        camera.boundaries[symbols['m10v_zoom_camera_snapshot']] = lambda: 0xffffffff
        routes = []
        camera.boundaries[0x5316c9d8] = lambda: routes.append(
            camera.u.reg_read(camera.A.UC_ARM_REG_R1))
        camera.boundaries[0x5316ca28] = lambda: 0
        page, event, route = support.OWNER + 0x6e00, 0x550a9000, 0x0200f10a
        camera.call(symbols['m10v_settings_controller_top_ctor'], support.OWNER)

        def reopen():
            self.assertEqual(camera.call(symbols['m10v_settings_controller_ready'], page, route), 1)
            camera.call(symbols['m10v_settings_controller_enter'], page, route, 0)

        def key(code):
            camera.words(event, code)
            self.assertEqual(camera.call(symbols['m10v_settings_controller_key'], page, event), 1)

        reopen()
        # Effects card -> Half row -> On -> confirm, entirely through installed
        # physical key routing. No synthetic Half-setting invocation here.
        for code in (0xcf, 0xd8) + (0xd1,) * 5 + (0xd8, 0xd1, 0xd8):
            key(code)
        self.assertEqual(camera.call(symbols['m10v_settings_half_enabled']), 1)
        reopen()
        self.assertEqual(camera.call(symbols['m10v_settings_half_enabled']), 1)
        self.assertEqual(camera.call(self.menu[2]), 7)
        # Return through hub entry and open its installed stock Aspect Ratio
        # route (the OS controller transition itself is the UI boundary).
        for code in (0x89, 0x89, 0xce, 0xd8, 0xd1, 0xd1, 0xd8):
            key(code)
        self.assertEqual(routes, [0x02000073])
        for row, raw, dimensions in ((4, 4, (6000, 2208)), (6, 6, (2992, 4000))):
            camera.call(self.menu[6], 0, row)
            self.assertEqual(self.ratio(), raw)
            self.assertEqual(self.dimensions(), dimensions)
        self.assertFalse(camera.assertions)

    def test_persisted_active_roll_restores_ratio_but_pause_and_close_allow_changes(self):
        from tests import test_gr3_roll_device_arm as roll
        from tests.test_gr3_companion_timer_arm import TimerMachine
        from unicorn import UC_HOOK_CODE
        from unicorn import arm_const as registers
        final_rom, symbols = self.rom, self.symbols

        class FinalCard(roll.RollDevice):
            def machine(inner):
                machine = TimerMachine(final_rom, b'')
                machine.instruction_budget = 1000000
                machine.set(0x55063910, 1)
                machine.set(0x55063988, roll.OWNER)
                return machine

        card = FinalCard('runTest')
        card.symbols = symbols
        candidate = Path(os.environ['M10V_MENU_HUB_CANDIDATE'])
        card.manifest = json.loads((candidate / 'M10V-runtime-manifest.json').read_text())

        def boot(files):
            machine = card.card_machine(files, original_aspect=True)
            if card.manifest.get('debug_mode'):
                # This fixture owns roll-journal I/O, not the separate GUI SD
                # logging facade. Capture that diagnostic filesystem boundary;
                # diagnostic producer and CRC logger instructions have separate
                # exact-ARM coverage, while all roll/control code stays real.
                machine.diagnostic_events=[]
                def diagnostic_sink(u,address,_size,_context):
                    if address==symbols['m10v_debug_log']:
                        machine.diagnostic_events.append(u.reg_read(registers.UC_ARM_REG_R0))
                        u.reg_write(registers.UC_ARM_REG_R0,0)
                        u.reg_write(registers.UC_ARM_REG_PC,u.reg_read(registers.UC_ARM_REG_LR))
                machine.u.hook_add(UC_HOOK_CODE,diagnostic_sink)
            machine.set(0x55063ed0, 1)
            machine.set(0x55063f34, support.PROPERTIES)
            machine.u.mem_write(support.PROPERTIES + 0x44, b'\1')
            machine.run(symbols['m10v_half_pair_init'], roll.OWNER)
            self.assertEqual(machine.run(symbols['m10v_settings_half_set'], 1), 0)
            if card.manifest.get('debug_mode'):self.assertIn(415,machine.diagnostic_events)

            def publication(u, address, _size, _context):
                if address == 0x532288b0:
                    u.reg_write(registers.UC_ARM_REG_R0, 0)
                    u.reg_write(registers.UC_ARM_REG_PC, u.reg_read(registers.UC_ARM_REG_LR))

            machine.u.hook_add(UC_HOOK_CODE, publication)
            card.prepare(machine)
            return machine

        def ratio(machine):
            return machine.u.mem_read(support.RATIO, 1)[0]

        files = {}
        machine = boot(files)
        # Use the existing stock-negative roll, whose native film choice does
        # not require synthetic catalog entries. Journal persistence and the
        # AppMain roll worker execute from the final firmware.
        self.assertEqual(machine.run(symbols['m10v_roll_device_open'], 0x10016, 0, 24), 1)
        active_files = files.copy()
        # Open the installed hub against this same live persistent roll owner.
        # Bound only unrelated feature initialization, painting and route OS.
        paint_codes, routes = [], []
        ignored = {0x5319aa68, 0x5316c8d4, 0x5316d354, 0x5316ca28}
        for name in ('m10v_camera_library_preview_init', 'm10v_companion_ui_init',
                     'm10v_adj_extra_camera_init', 'm10v_guides_camera_init',
                     'm10v_torn_init', 'm10v_settings_view_hub_create',
                     'm10v_camera_library_load', 'm10v_isp_effects_camera_snapshot',
                     'm10v_border_camera_snapshot', 'm10v_hdf_cached',
                     'm10v_torn_state', 'm10v_guides_camera_mode'):
            if name in symbols:
                ignored.add(symbols[name])

        def hub_service(u, address, _size, _context):
            if address == symbols['m10v_settings_view_hub']:
                paint = u.reg_read(registers.UC_ARM_REG_R1)
                paint_codes.append(machine.word(paint + 36))
                result = 1
            elif address == symbols['m10v_settings_view_hub_artwork']:
                result = 8
            elif address == symbols['m10v_zoom_camera_snapshot']:
                result = 0xffffffff
            elif address == 0x5316c9d8:
                routes.append(u.reg_read(registers.UC_ARM_REG_R1))
                result = 0
            elif address in ignored:
                result = 0
            else:
                return
            u.reg_write(registers.UC_ARM_REG_R0, result)
            u.reg_write(registers.UC_ARM_REG_PC, u.reg_read(registers.UC_ARM_REG_LR))

        machine.u.hook_add(UC_HOOK_CODE, hub_service)
        machine.run(symbols['m10v_settings_controller_top_ctor'], roll.OWNER)
        page, event, hub = roll.OWNER + 0x6e00, roll.SCRATCH, 0x0200f10a
        machine.run(symbols['m10v_settings_controller_ready'], page, hub)
        machine.run(symbols['m10v_settings_controller_enter'], page, hub, 0)

        def key(code):
            machine.set(event, code)
            self.assertEqual(machine.run(symbols['m10v_settings_controller_key'], page, event), 1)

        for code in (0xcf, 0xd8) + (0xd1,) * 5 + (0xd8,):
            key(code)
        self.assertEqual(paint_codes[-1], 300)
        self.assertEqual(machine.run(symbols['m10v_settings_half_enabled']), 0)
        # Back -> main -> settings -> stock aspect row must stay in the hub.
        for code in (0x89, 0x89, 0xce, 0xd8, 0xd1, 0xd1, 0xd8):
            key(code)
        self.assertEqual(routes, [])
        self.assertEqual(paint_codes[-1], 300)
        # Remote requests may converge to the journal's locked ratio, but
        # may not briefly select a different ratio until the next worker tick.
        remote = symbols['m10v_settings_controller_remote_aspect_write']
        for raw in (4, 6):
            self.assertNotEqual(machine.run(remote, raw), 0)
            self.assertEqual(ratio(machine), 0)
        self.assertEqual(machine.run(remote, 0), 0)
        self.assertEqual(machine.run(symbols['m10v_settings_half_enabled']), 0)
        # Keep the Half data path enabled for the worker restoration checks.
        self.assertEqual(machine.run(symbols['m10v_settings_half_set'], 1), 0)

        for row, raw in ((4, 4), (6, 6)):
            machine.run(self.menu[6], 0, row)
            self.assertEqual(ratio(machine), raw)
            card.tick(machine)
            self.assertEqual(ratio(machine), 0)
        for status, row, raw in ((2, 6, 6), (3, 4, 4)):
            self.assertEqual(machine.run(symbols['m10v_roll_device_change'], status), 1)
            self.assertEqual(machine.run(symbols['m10v_roll_device_locked']), 0)
            self.assertEqual(machine.run(remote, raw), 0)
            if status == 2:
                machine.run(symbols['m10v_settings_controller_enter'], page, hub, 0)
                key(0xd8)
                self.assertEqual(routes, [0x02000073])
                self.assertNotEqual(paint_codes[-1], 300)
            machine.run(self.menu[6], 0, row)
            card.tick(machine)
            self.assertEqual(ratio(machine), raw)
        restarted = boot(active_files)
        self.assertEqual(restarted.run(symbols['m10v_roll_device_locked']), 1)
        restarted.run(self.menu[6], 0, 6)
        self.assertEqual(ratio(restarted), 6)
        card.tick(restarted)
        self.assertEqual(ratio(restarted), 0)

    def test_native_setter_posts_real_aspect_events_to_appmain_ring(self):
        camera = self.camera
        del camera.boundaries[0x532288b0]
        # Only RTOS synchronization terminates here; packet constructor,
        # native AppModel enqueue, and immediate property write all execute.
        for address in (0x536ae71c, 0x536ae870, 0x536a9d1c):
            camera.boundaries[address] = lambda: 1
        queue, ring = 0x550645f0, 0x550b0000
        camera.words(queue + 0x14, ring)
        camera.u.mem_write(queue + 0x18, struct.pack('<5H', 0, 64, 0, 0, 63))
        self.assertEqual(camera.call(self.symbols['m10v_settings_half_set'], 1), 0)
        for index, (row, raw) in enumerate(((4, 4), (6, 6), (0, 0))):
            camera.call(self.menu[6], 0, row)
            self.assertEqual(self.ratio(), raw)
            self.assertEqual(camera.read_words(ring + 12 * index, 3), [0x183, 0, 0])
        self.assertEqual(struct.unpack('<H', camera.u.mem_read(queue + 0x18, 2))[0], 3)
        self.assertFalse(camera.assertions)

    def test_native_menu_and_adj_select_xpan_half_and_back_to_full_frame(self):
        camera = self.camera
        self.assertEqual(camera.call(self.symbols['m10v_settings_half_set'], 1), 0)
        for apply, args, checked in (
            (self.menu[6], lambda row: (0, row), self.menu[8]),
            (self.adj_apply, lambda row: (adj.CONTROLLER, row), self.adj_checked),
        ):
            for row, raw, expected in ((4, 4, (6000, 2208)),
                                       (6, 6, (2992, 4000)),
                                       (0, 0, (6000, 4000)),
                                       (5, 5, (4672, 4000))):
                with self.subTest(selector=hex(apply), row=row):
                    camera.call(apply, *args(row))
                    self.assertEqual(self.ratio(), raw)
                    self.assertEqual(camera.call(checked, *args(row)), 1)
                    self.assertEqual(self.dimensions(), expected)
        self.assertFalse(camera.assertions)

    def test_disabling_half_restores_full_frame_and_cancels_owned_pair_state(self):
        camera = self.camera
        # Locate the initialized private session in its explicit owner storage.
        # Its magic and generation are part of the retained session ABI; this
        # observes actual cancellation even when release logging is compiled out.
        data = bytes(camera.u.mem_read(support.OWNER, 0x10000))
        marker = struct.pack('<I', 0x37535048)
        offset = data.index(marker)
        self.assertEqual(data.find(marker, offset + 4), -1)
        session = support.OWNER + offset
        self.assertEqual(camera.read_words(session + 12, 1), [1])
        self.assertEqual(camera.call(self.symbols['m10v_settings_half_set'], 1), 0)
        camera.call(self.menu[6], 0, 6)
        self.assertEqual(self.ratio(), 6)
        self.assertEqual(camera.call(self.symbols['m10v_settings_half_set'], 0), 0)
        self.assertEqual(self.ratio(), 0)
        self.assertEqual(self.dimensions(), (6000, 4000))
        self.assertEqual(camera.read_words(session + 12, 1), [2])
        self.assertEqual(camera.read_words(session + 4, 2), [0, 1])
        self.assertEqual(camera.call(self.menu[2]), 6)
        self.assertFalse(camera.assertions)

    def test_session_default_rejects_half_and_preserves_xpan(self):
        camera = self.camera
        for apply, args in ((self.menu[6], lambda row: (0, row)),
                            (self.adj_apply, lambda row: (adj.CONTROLLER, row))):
            with self.subTest(selector=hex(apply)):
                camera.call(apply, *args(4))
                self.assertEqual(self.ratio(), 4)
                camera.call(apply, *args(6))
                self.assertEqual(self.ratio(), 4)
                self.assertEqual(self.dimensions(), (6000, 2208))
        self.assertFalse(camera.assertions)
