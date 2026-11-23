"""Exercise the installed ARM menu, SD loader and native pixel blitter."""
import json
import os
from pathlib import Path
import struct
import subprocess
import unittest

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm_const as A
from PIL import Image

HUB = 0x0200F10A
RAM = 0x55000000
OWNER = RAM + 0x70000
PAGE = OWNER + 0x6E00
PACKET = RAM + 0x2000
EVENT = RAM + 0x2100
STOP = RAM + 0x4000
HEAP = RAM + 0x100000
FRAMEBUFFER = RAM + 0x300000
REGS = (A.UC_ARM_REG_R0, A.UC_ARM_REG_R1, A.UC_ARM_REG_R2, A.UC_ARM_REG_R3)


class FinalMenuHub(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = os.getenv("M10V_MENU_HUB_CANDIDATE")
        if not directory:
            raise unittest.SkipTest("M10V_MENU_HUB_CANDIDATE is required")
        candidate = Path(directory)
        cls.assets = Path(os.environ["M10V_MENU_HUB_ASSETS"])
        cls.pack = (cls.assets / "MENU.M10").read_bytes()
        cls.manifest = json.loads((candidate / "M10V-runtime-manifest.json").read_text())
        cls.symbols = cls.manifest["symbols"]
        cls.rt = subprocess.check_output(["node", "--input-type=module",
            "-e", """
            import {readFileSync} from 'node:fs';
            import {decodeFrameMap} from './node/gr3-frames.mjs';
            const data=decodeFrameMap(readFileSync(process.argv[1])).decoded;
            let at=0;
            while(data.toString('ascii',at,at+4)!=='RTOS')at+=16+data.readUInt32LE(at+12);
            process.stdout.write(data.subarray(at+16,at+16+data.readUInt32LE(at+12)));
            """, candidate / "fwdc239b.bin"])

    def setUp(self):
        self.arm = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        self.arm.mem_map(0x53000000, 0x2000000)
        self.arm.mem_write(0x53000000, self.rt)
        self.arm.mem_map(RAM, 0x500000)
        self.arm.mem_write(0x55063910,struct.pack("<I",1))
        self.arm.mem_write(0x55063988,struct.pack("<I",OWNER))
        self.draws, self.routes = [], []
        self.painted_roll_film = 0
        self.draw_real_view = False
        self.detail_widgets = False
        self.rects, self.colors, self.inks, self.captions, self.visibility = {}, {}, {}, {}, {}
        self.icons, self.closed_routes, self.saved_effects = {}, [], []
        self.effect_fixture = False
        self.fn_row = 0
        self.library_state = None
        self.alloc = HEAP
        self.arm.mem_write(RAM+0x9028, struct.pack("<I", RAM+0x9100))
        self.arm.mem_write(RAM+0x9034, struct.pack("<I", RAM+0x9100))
        self.file = self.pack
        self.short_read = False
        self.position = 0
        self.closed = 0
        fs, manager, vt, fs_calls = RAM+0x8000, RAM+0x8100, 0x530B8000, 0x530BB000
        self.arm.mem_write(manager+20, struct.pack("<I", fs))
        self.arm.mem_write(fs, struct.pack("<I", vt))
        self.arm.mem_write(vt, struct.pack("<14I", *(fs_calls+4*i for i in range(14))))
        symbols = self.symbols
        callbacks = {
            0x5316C9D8: self.routes.append,
            0x5316CA28: self.closed_routes.append,
        }
        stubs = {
            0x5319AA68: 0, 0x5316C8D4: 0, 0x5316D354: 0, 0x5316CA28: 0,
            symbols["m10v_settings_view_hub_create"]: 0,
            symbols["m10v_debug_log"]: 0,
            symbols["m10v_camera_library_load"]: 0,
            0x53828014: 0,
            0x5320AD88: 0,  # No stock shooting model in the touch-only fixture.
            self.manifest["settings_menu"]["exports"]["m10v_settings_factory_original"]: OWNER,
        }
        for name in ("m10v_camera_library_preview_init", "m10v_companion_ui_init",
                     "m10v_adj_extra_camera_init", "m10v_guides_camera_init",
                     "m10v_torn_init", "m10v_half_pair_init",
                     "m10v_isp_effects_camera_snapshot", "m10v_border_camera_snapshot",
                     "m10v_guides_camera_mode", "m10v_torn_state",
                     "m10v_hdf_load", "m10v_border_camera_refresh"):
            if name in symbols:
                stubs[symbols[name]] = 0
        stubs[symbols["m10v_isp_effects_camera_refresh"]] = 0
        for name in ("m10v_hdf_cached", "m10v_zoom_camera_snapshot", "m10v_settings_controller_remote_aspect_read"):
            stubs[symbols[name]] = 0xFFFFFFFF

        def boundary(arm, address, _size, _context):
            result = stubs.get(address, 0)
            if self.library_state and address == symbols["m10v_camera_library_load"]:
                arm.mem_write(arm.reg_read(A.UC_ARM_REG_R0), self.library_state)
            elif self.library_state and address == symbols["m10v_sd_camera_directory_extent"]:
                result = 64
            elif self.library_state and address == symbols["m10v_sd_camera_directory_item"]:
                index = arm.reg_read(A.UC_ARM_REG_R0)
                result = 331 + index - 60 if 60 <= index <= 63 else 0
            elif self.effect_fixture and address == symbols["m10v_isp_effects_camera_snapshot"]:
                arm.mem_write(arm.reg_read(A.UC_ARM_REG_R0), bytes(32))
                result = 1
            elif self.effect_fixture and address == symbols["m10v_isp_effects_camera_save"]:
                word, = struct.unpack("<I",arm.mem_read(arm.reg_read(A.UC_ARM_REG_R1)+28,4))
                self.saved_effects.append(word)
            elif self.fn_row and address == 0x53394758:
                result = self.fn_row
            elif self.fn_row and address == 0x53390D6C:
                arm.mem_write(arm.reg_read(A.UC_ARM_REG_R0)+0xea,
                              bytes([arm.reg_read(A.UC_ARM_REG_R1)]))
            elif (self.fn_row or self.detail_widgets) and address == 0x533AB548:
                widget, rect = (arm.reg_read(reg) for reg in REGS[:2])
                arm.mem_write(widget+0x20, bytes(arm.mem_read(rect,16)))
            elif self.detail_widgets and address == 0x53390EF8:
                self.detail_name = bytes(arm.mem_read(arm.reg_read(A.UC_ARM_REG_R1), 24)).split(b"\0")[0]
            elif self.detail_widgets and address == 0x536AF2A8:
                result = self.alloc
                self.alloc += (arm.reg_read(A.UC_ARM_REG_R0) + 15) & ~15
            elif self.detail_widgets and address in (0x5339199C, 0x53393D84, 0x53396944,
                                                       0x5339A908, 0x53390CA0):
                widget, x, y, width = (arm.reg_read(reg) for reg in REGS)
                height, = struct.unpack("<I", arm.mem_read(arm.reg_read(A.UC_ARM_REG_SP), 4))
                self.rects[widget] = (x, y, width, height)
                arm.mem_write(widget, struct.pack("<I", RAM+0x9000))
            elif self.detail_widgets and address in (0x53393E00, 0x5339658C, 0x53396F80, 0x533AD3C0, 0x5339A9A0):
                records = {0x53393E00:self.colors, 0x5339658C:self.inks,
                           0x53396F80:self.captions, 0x533AD3C0:self.visibility, 0x5339A9A0:self.icons}
                records[address][arm.reg_read(A.UC_ARM_REG_R0)] = arm.reg_read(A.UC_ARM_REG_R1)
            elif self.detail_widgets and address in (0x533ABA64, 0x533AD308, 0x5339AA30,
                                                       0x5339AA44, 0x53396644, 0x53396658, RAM+0x9100):
                pass
            elif address == symbols["m10v_settings_view_hub"]:
                if self.draw_real_view:
                    return
                pointer = arm.reg_read(A.UC_ARM_REG_R1)
                self.draws.append(struct.unpack("<9I", arm.mem_read(pointer, 36)))
                self.painted_roll_film, = struct.unpack("<I", arm.mem_read(pointer+44,4))
                result = 1
            elif self.draw_real_view and address == 0x535847D8:
                result = manager
            elif self.draw_real_view and fs_calls <= address < fs_calls + 56:
                slot = (address-fs_calls)//4
                _, r1, r2, r3 = (arm.reg_read(reg) for reg in REGS)
                result = 1
                if slot == 7:
                    self.assertEqual(bytes(arm.mem_read(r1, 17)).split(b"\0")[0], b"C:\\M10V\\MENU.M10")
                    arm.mem_write(r3, struct.pack("<I", 1))
                    self.position = 0
                elif slot == 8:
                    self.closed += 1
                elif slot == 9:
                    if self.short_read and r3 > 100000:
                        r3 -= 4
                    arm.mem_write(r2, self.file[self.position:self.position+r3])
                    self.position += r3
                elif slot == 11:
                    self.position = r2
                elif slot in (12,13):
                    arm.mem_write(r2, struct.pack("<I", len(self.file) if slot==12 else self.position))
                else:
                    self.fail(f"Unexpected FS operation {slot}")
            elif self.draw_real_view and address == 0x536C7520:
                result = FRAMEBUFFER
            elif self.draw_real_view and address == 0x536AF2A8:
                result = HEAP
            elif self.draw_real_view and address in (0x533AD3C0, 0x53396F80, 0x5339A9A0, 0x533AD308, 0x533AB548, 0x53390EF8):
                pass
            elif address in callbacks:
                callbacks[address](tuple(arm.reg_read(register) for register in
                    (A.UC_ARM_REG_R0, A.UC_ARM_REG_R1, A.UC_ARM_REG_R2, A.UC_ARM_REG_R3)))
            elif address not in stubs:
                return
            arm.reg_write(A.UC_ARM_REG_R0, result)
            arm.reg_write(A.UC_ARM_REG_PC, arm.reg_read(A.UC_ARM_REG_LR))

        self.arm.hook_add(UC_HOOK_CODE, boundary)
        self.call("top_ctor", OWNER)
        self.assertEqual(self.call("factory", 0, HUB), PAGE)
        self.assertEqual(self.call("ready", PAGE, HUB), 1)
        self.call("enter", PAGE, HUB, 0)

    def call(self, name, *args):
        return self.call_symbol("m10v_settings_controller_" + name, *args)

    def call_symbol(self, name, *args, stack=()):
        for register, value in zip(REGS, args):
            self.arm.reg_write(register, value)
        sp = RAM + 0xF0000
        self.arm.reg_write(A.UC_ARM_REG_SP, sp)
        if stack:
            self.arm.mem_write(sp, struct.pack(f"<{len(stack)}I", *stack))
        self.arm.reg_write(A.UC_ARM_REG_LR, STOP)
        self.arm.emu_start(self.symbols[name] if isinstance(name, str) else name, STOP, count=9000000)
        self.assertEqual(self.arm.reg_read(A.UC_ARM_REG_PC), STOP)
        return self.arm.reg_read(A.UC_ARM_REG_R0)

    def touch(self, kind, x, y, controller=PAGE):
        packet = bytearray(0x58)
        packet[0] = int(kind in (1, 5))
        packet[0x50] = kind
        struct.pack_into("<II", packet, 8, x, y)
        packet[0x28] = 1
        struct.pack_into("<II", packet, 0x30, x, y)
        self.arm.mem_write(PACKET, bytes(packet))
        self.arm.mem_write(EVENT, struct.pack("<II", 0x30, PACKET))
        self.call_symbol("m10v_settings_controller_key" if controller in (PAGE,OWNER+0x13bc) else "m10v_hdf_menu_key",
                         controller, EVENT)

    def tap(self, x, y):
        self.touch(1, x, y)
        self.touch(2, x, y)
        self.touch(10, x, y)

    def swipe(self, start, end):
        self.touch(1, start, 192)
        self.touch(5, end, 203)
        self.touch(10, end, 203)

    def test_swipe_reaches_second_screen_without_opening_info(self):
        self.assertEqual(self.draws[-1][0], 0)
        self.swipe(430, 275)
        self.assertEqual(self.draws[-1][0], 3)
        self.assertEqual(self.routes, [])
        self.tap(237, 250)
        self.assertEqual(self.draws[-1][0], 10)
        self.tap(52, 31)
        self.assertEqual(self.draws[-1][0], 3)
        self.tap(474, 270)
        self.assertEqual(self.draws[-1][0], 12)
        self.tap(52, 31)
        self.assertEqual(self.draws[-1][0], 11)
        self.swipe(260, 420)
        self.assertEqual(self.draws[-1][0], 0)

    def test_effect_rows_and_bottom_edge_use_new_geometry(self):
        self.tap(560, 250)
        self.assertEqual(self.draws[-1][0], 7)
        self.tap(454, 85)
        self.tap(454, 457)
        self.assertEqual(self.routes, [])
        self.tap(454, 86)
        self.assertEqual(self.routes[-1][:3], (PAGE, 0x0200F110, HUB))
        self.tap(454, 139)
        self.assertEqual(self.routes[-1][:3], (PAGE, 0x0200F111, HUB))
        self.tap(454, 456)
        self.assertEqual(self.routes[-1][:3], (PAGE, 0x0200F104, HUB))
        self.call("ready", PAGE, HUB)
        self.call("enter", PAGE, HUB, 0)
        self.assertEqual(self.draws[-1][0], 7)
        self.tap(52, 31)
        self.assertEqual(self.draws[-1][0], 1)

    def test_first_screen_settings_and_optional_album(self):
        self.tap(143, 250)
        self.assertEqual(self.draws[-1][0], 9)
        self.tap(100, 108)
        self.assertEqual(self.routes[-1][:3], (PAGE, 0x0200F101, HUB))
        self.tap(100, 160)
        self.assertEqual(self.routes[-1][:3], (PAGE, 0x0200F109, HUB))
        self.tap(52, 31)
        self.tap(360, 265)
        self.assertEqual(self.routes[-1][:3], (PAGE, 0x0200F100, HUB))

    def test_half_effect_opens_inside_hub_and_cancel_keeps_the_existing_value(self):
        self.tap(560, 250)
        self.tap(450, 365)
        self.assertEqual(self.routes, [])
        self.assertEqual(self.draws[-1][:2], (13, 0))
        self.tap(450, 158)
        self.assertEqual(self.draws[-1][:2], (13, 1))
        self.tap(507, 439)
        self.assertEqual(self.draws[-1][0], 7)
        self.tap(450, 365)
        self.assertEqual(self.draws[-1][:2], (13, 0))

    def test_physical_keys_focus_cards_in_screen_order(self):
        for key, expected in ((0xce,2),(0xcf,0),(0xcf,1),(0xcf,3),(0xcf,11),(0xce,3),(0xce,1)):
            self.arm.mem_write(EVENT, struct.pack("<I", key))
            self.call("key", PAGE, EVENT)
            self.assertEqual(self.draws[-1][0], expected)
        self.assertEqual(self.routes, [])

    def test_r8_moves_selection_between_all_second_screen_cards(self):
        filename = os.getenv("M10V_MENU_ROLL_ASSET")
        if not filename:
            self.skipTest("M10V_MENU_ROLL_ASSET is required")
        self.file = Path(filename).read_bytes()
        self.assertEqual(self.art(0), 1)
        self.assertEqual(self.call_symbol("m10v_settings_view_hub_artwork", self.view), 8)

        def framebuffer(x, y):
            return struct.unpack("<I", self.arm.mem_read(HEAP+(y*720+x)*4,4))[0]

        def key(code):
            self.arm.mem_write(EVENT,struct.pack("<I",code))
            self.call("key", PAGE, EVENT)

        gold = 0xff7fd1ef
        self.swipe(430,275)
        self.assertEqual(framebuffer(39,220),gold)
        self.assertNotEqual(framebuffer(360,152),gold)
        self.assertNotEqual(framebuffer(488,220),gold)
        key(0xcf)
        self.assertNotEqual(framebuffer(39,220),gold)
        self.assertEqual(framebuffer(360,152),gold)
        key(0xcf)
        self.assertNotEqual(framebuffer(360,152),gold)
        self.assertEqual(framebuffer(488,220),gold)
        self.tap(580,256)
        offset, = struct.unpack_from("<I",self.file,16+12*16)
        self.assertEqual(bytes(self.arm.mem_read(HEAP,720*480*4)),
                         self.file[offset:offset+720*480*4])

    def pixels(self, x, y):
        directory = self.call("card_directory", 859)
        self.assertNotEqual(directory, 0)
        descriptor, = struct.unpack("<I", self.arm.mem_read(directory+859*4,4))
        size, word_address = struct.unpack("<II", self.arm.mem_read(descriptor,8))
        self.assertEqual(size,720|(480<<16))
        return struct.unpack("<I", self.arm.mem_read(word_address*4+(y*720+x)*4,4))[0]

    def test_installed_watermark_uses_flat_warm_focus(self):
        self.detail_widgets = True
        view, state = RAM+0x5200, RAM+0x5400
        self.assertEqual(self.call_symbol("m10v_settings_view_create", view), 0)
        self.arm.mem_write(state+184, struct.pack("<II", 9, 0))
        self.call_symbol("m10v_settings_view_draw", view, state, 0)
        widgets = struct.unpack("<47I", self.arm.mem_read(view, 47*4))
        self.assertEqual(self.icons[widgets[46]],859)
        self.assertEqual(self.rects[widgets[36]],(60,87,280,50))
        self.assertEqual(self.pixels(33,85),self.pixels(80,85))
        self.assertEqual(self.pixels(35,109),0xff7ac4ea)
        self.assertNotEqual(self.pixels(42,109),self.pixels(42,162))

    def test_catalog_fn_opens_the_named_enabled_film_without_switching_routes(self):
        state = RAM + 0x5000
        self.call_symbol("m10v_library_init", state)
        size, = struct.unpack("<H", self.arm.mem_read(state+6, 2))
        self.library_state = bytes(self.arm.mem_read(state, size))
        self.detail_widgets = True
        films = 0x0200F100
        catalog = self.call("factory", 0, films)
        self.assertEqual(self.call("ready", catalog, films), 1)
        self.call("enter", catalog, films, 0)
        # The name of the second tile begins below its 128 px cover.
        for kind in (1, 2, 10):
            self.touch(kind, 185, 213, catalog)
        self.arm.mem_write(PACKET, struct.pack("<II", 1, 1))
        self.arm.mem_write(EVENT, struct.pack("<II", 0x1b, PACKET))
        self.assertEqual(self.call("key", catalog, EVENT), 1)
        self.assertEqual(self.detail_name, b"Leica Brass")
        self.assertEqual(self.routes, [])
        self.arm.mem_write(EVENT, struct.pack("<I", 0x89))
        self.assertEqual(self.call("key", catalog, EVENT), 1)
        self.assertEqual(self.closed_routes, [])

    def effect_screen(self, route):
        self.detail_widgets = self.effect_fixture = True
        controller = RAM+0x82000
        self.assertEqual(self.call_symbol("m10v_hdf_menu_ready", controller, route),1)
        self.call_symbol("m10v_hdf_menu_enter", controller, route,0)
        widgets = struct.unpack("<9I",self.arm.mem_read(controller+0x158,36))
        self.assertEqual(self.icons[widgets[1]],859)
        return controller,widgets

    def test_roll_catalog_picks_a_late_film_without_editing_library(self):
        filename = os.getenv("M10V_MENU_ROLL_ASSET")
        if not filename:
            self.skipTest("M10V_MENU_ROLL_ASSET is required")
        self.file = Path(filename).read_bytes()
        self.assertEqual(self.art(0),1)
        self.draw_real_view = False
        self.swipe(430,275)
        self.tap(350,250)
        self.tap(666,34)
        self.tap(431,248)
        films = 0x0200f100
        self.assertEqual(self.routes[-1][1:3],(films,HUB))
        state = RAM+0x5000
        self.call_symbol("m10v_library_init",state)
        size, = struct.unpack("<H",self.arm.mem_read(state+6,2))
        self.library_state = bytes(self.arm.mem_read(state,size))
        self.detail_widgets = True
        catalog = self.call("factory",0,films)
        self.assertEqual(self.call("ready",catalog,films),1)
        for raw in (0xcf,0xcf,0xd8):
            self.arm.mem_write(EVENT,struct.pack("<I",raw))
            self.assertEqual(self.call("key",catalog,EVENT),1)
        self.assertEqual(self.closed_routes[-1][0],catalog)
        self.call("enter",PAGE,HUB,0)
        self.assertEqual(self.painted_roll_film,333)

    def effect_gesture(self, controller, x, start, end):
        self.touch(1,x,start,controller)
        if start!=end:
            self.touch(5,x,end,controller)
        self.touch(2,x,end,controller)
        self.touch(10,x,end,controller)

    def test_all_imprints_share_one_screen_and_save_the_last_row(self):
        controller, widgets = self.effect_screen(0x0200f112)
        self.assertEqual(self.captions[widgets[2]],1203)
        options, = struct.unpack("<I",self.arm.mem_read(controller+0x1bc,4))
        choices = struct.unpack("<8I",self.arm.mem_read(options,32))
        self.assertEqual([self.captions[w] for w in choices],[1169,*range(1204,1211)])
        self.assertEqual([self.rects[w][1] for w in choices],list(range(87,407,40)))
        self.assertTrue(all(self.visibility[w] for w in choices))
        self.assertFalse(any(self.visibility[w] for w in widgets[4:8]))
        self.effect_gesture(controller,160,244,110)
        self.assertEqual(self.saved_effects,[])
        self.assertTrue(all(self.visibility[w] for w in choices))
        self.effect_gesture(controller,140,378,378)
        self.assertEqual(self.saved_effects,[])
        self.effect_gesture(controller,622,444,444)
        self.assertEqual([v >> 7 & 7 for v in self.saved_effects],[7])
        self.assertEqual(self.closed_routes[-1][0],controller)
        self.assertEqual(self.captions[widgets[2]],1203)

    def test_vignette_has_two_rows_and_correct_back_levels(self):
        controller,widgets=self.effect_screen(0x0200f113)
        self.assertEqual([self.captions[w] for w in widgets[4:6]],[1215,1216])
        self.effect_gesture(controller,170,160,160)
        self.assertEqual(self.captions[widgets[4]],973)
        self.effect_gesture(controller,52,39,39)
        self.assertEqual([self.captions[w] for w in widgets[4:6]],[1215,1216])
        self.assertEqual(self.closed_routes,[])
        self.effect_gesture(controller,52,39,39)
        self.assertEqual(self.closed_routes[-1][0],controller)
        self.assertEqual(self.captions[widgets[2]],1214)

    def test_fn_private_value_skin_restores_stock_rail_geometry(self):
        ui, rail, row, label, icon = (RAM+i for i in range(0x86000,0x86a00,0x200))
        self.fn_row = row
        self.arm.mem_write(ui+0x194,struct.pack("<I",rail))
        self.arm.mem_write(ui+0x198,bytes([25,0,0,0,0,0]))
        self.arm.mem_write(row+0xf0,struct.pack("<II",icon,label))
        for widget in (label,icon):
            self.arm.mem_write(widget+0x20,struct.pack("<4I",50,10,40,40))
        self.arm.mem_write(label+0xea,b"\x1f")
        self.call_symbol("m10v_detail_control",8,ui,21<<16)
        self.assertEqual(struct.unpack("<4I",self.arm.mem_read(label+0x20,16)),(52,10,64,40))
        self.assertEqual(bytes(self.arm.mem_read(label+0xea,1)),b"\x0a")
        self.call_symbol("m10v_detail_control",8,ui,1<<16)
        self.assertEqual(struct.unpack("<4I",self.arm.mem_read(label+0x20,16)),(50,10,40,40))
        self.assertEqual(bytes(self.arm.mem_read(label+0xea,1)),b"\x1f")

    def art(self, frame, patch=0, film=0):
        self.draw_real_view = True
        self.view, paint = PAGE + 0x158, RAM + 0x5200
        self.arm.mem_write(self.view + 56 * 4, struct.pack("<I", 6))
        self.arm.mem_write(paint, struct.pack("<13I", frame, 0xffffffff, patch, *([0]*8), film, 0))
        return self.call_symbol("m10v_settings_view_hub", self.view, paint)

    def test_approved_default_screens_match_native_blit_pixel_for_pixel(self):
        surface = RAM + 0x20000
        self.arm.mem_write(surface+0x18, struct.pack("<H",720))
        for frame in (0,1,2,3,7,9,10,11,12,13,14):
            with self.subTest(frame=frame):
                self.assertEqual(self.art(frame), 1)
                directory = self.call_symbol("m10v_settings_view_hub_directory", self.view)
                descriptor, = struct.unpack("<I", self.arm.mem_read(directory+858*4,4))
                self.assertEqual(struct.unpack("<II", self.arm.mem_read(descriptor,8)), (720|480<<16, HEAP//4))
                self.assertEqual(self.call_symbol(0x53209FCC,0,858),720)
                self.assertEqual(self.call_symbol(0x5320A000,0,858),480)
                self.call_symbol(0x5320A020,RAM+0x20400,surface,0,0,stack=(0,0,720,480,descriptor,HEAP))
                expected = Image.open(self.assets/"reference"/f"{frame}.png").convert("RGBA").tobytes()
                self.assertEqual(bytes(self.arm.mem_read(FRAMEBUFFER,len(expected))), expected)

    def test_status_patch_does_not_replace_the_base_art(self):
        patch = 64+3*48+3  # HDF strong in the fully featured effects screen
        self.assertEqual(self.art(7,patch),1)
        expected = Image.open(self.assets/"reference"/"7.png").convert("RGBA")
        _,_,x,y,w,h = struct.unpack_from("<II4H", self.pack,16+patch*16)
        variant = Image.open(self.assets/"reference"/f"{patch}.png").convert("RGBA")
        expected.paste(variant.crop((x,y,x+w,y+h)),(x,y))
        self.assertEqual(bytes(self.arm.mem_read(HEAP,720*480*4)),expected.tobytes())

    def test_short_or_corrupt_read_invalidates_bitmap_and_closes(self):
        self.assertEqual(self.art(0),1)
        self.short_read=True
        self.assertEqual(self.art(1),0)
        self.assertEqual(self.call_symbol("m10v_settings_view_hub_directory",self.view),0)
        self.short_read=False
        offset, = struct.unpack_from("<I",self.pack,16)
        bad = bytearray(self.pack)
        bad[offset] ^= 1
        self.file=bytes(bad)
        self.assertEqual(self.art(0),0)
        self.assertEqual(self.closed,3)

    def test_roll_menu_loads_v8_artwork_and_gates_start_without_camera_adapter(self):
        filename = os.getenv("M10V_MENU_ROLL_ASSET")
        if not filename:
            self.skipTest("M10V_MENU_ROLL_ASSET is required")
        self.file = Path(filename).read_bytes()
        self.assertEqual(self.art(0), 1)
        self.assertEqual(self.call_symbol("m10v_settings_view_hub_artwork", self.view), 8)

        def record(index):
            offset, _, x, y, width, height = struct.unpack_from(
                "<II4H", self.file, 16 + index * 16)
            length = 1024 + width * height if index >= 512 else width * height * 4
            return self.file[offset:offset + length], (x, y, width, height)

        def current_matches(index, patch_ids=(), canister=None):
            data, size = record(index)
            self.assertEqual(size, (0, 0, 720, 480))
            expected = Image.frombytes("RGBA", (720, 480), data)
            for patch_id in patch_ids:
                patch, (x, y, width, height) = record(patch_id)
                expected.paste(Image.frombytes("RGBA", (width, height), patch), (x, y))
            if canister is not None:
                tile, (_, _, width, height) = record(canister)
                palette, indices = tile[:1024], tile[1024:1024 + width * height]
                display = index == 386
                left, top = (163, 123) if display else (86, 138)
                dest_w, dest_h = (width, height) if display else (109, 150)
                for y in range(dest_h):
                    for x in range(dest_w):
                        color = indices[(y * height // dest_h) * width + x * width // dest_w]
                        if color:
                            expected.putpixel((left + x, top + y), tuple(palette[4 * color:4 * color + 4]))
            actual = bytes(self.arm.mem_read(HEAP, 720 * 480 * 4))
            self.assertEqual(actual, expected.tobytes())

        for frame in (386, 387):
            self.assertEqual(self.art(frame, film=333), 1)  # Leica Teal
            current_matches(frame, canister=574)
        self.assertEqual(self.art(0), 1)
        self.swipe(430, 275)
        self.tap(350, 250)
        current_matches(386, canister=512)
        self.tap(666, 34)
        current_matches(387, (480,), canister=512)
        self.tap(312, 150)
        self.tap(360, 295)
        current_matches(387, (457, 458, 478, 480), canister=576)
        self.tap(645, 411)  # 联调中: staging build cannot create camera state
        current_matches(387, (457, 458, 478, 480), canister=576)
        self.assertEqual(self.routes, [])
        self.tap(52, 31)
        current_matches(386, (414,), canister=576)
        self.tap(52, 31)
        self.tap(558, 260)
        current_matches(12)  # Original donation QR artwork
        self.tap(52, 31)
        self.swipe(260, 420)
        self.tap(560, 250)
        if "m10v_live_device_mode" in self.symbols:
            self.tap(500, 386)  # Live picker with unavailable recorder.
            header, (x, y, width, height) = record(390)
            actual = bytes(self.arm.mem_read(HEAP, 720 * 480 * 4))
            image = Image.frombytes("RGBA", (720, 480), actual)
            self.assertEqual(image.crop((x, y, x + width, y + height)).tobytes(), header)
            self.tap(52, 31)
        self.assertEqual(self.routes, [])
        self.tap(500, 334)  # Half stays in front of Live.
        expected, _ = record(13)
        actual = bytes(self.arm.mem_read(HEAP, 720 * 480 * 4))
        row_start, row_end = 86 * 720 * 4, (86 + 53) * 720 * 4
        self.assertEqual(actual[:row_start], expected[:row_start])
        self.assertEqual(actual[row_end:], expected[row_end:])
        focus_marker = (92 * 720 + 34) * 4
        self.assertEqual(actual[focus_marker:focus_marker + 4], bytes.fromhex("eac47aff"))
