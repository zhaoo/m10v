"""Execute the linked M10V ARM runtime; camera services are not emulated."""
from contextlib import contextmanager
import ctypes as C
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_PROT_READ, UC_PROT_EXEC
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC
from unicorn.arm_const import UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11, UC_ARM_REG_R12, UC_ARM_REG_CPSR
from scripts.build_gr3_m10v_library import build
from tests import test_gr3_m10v_library as host_tests
State, Image, Date = host_tests.State, host_tests.Image, host_tests.Date


class FilmLibraryArmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(); cls.addClassCleanup(cls.tmp.cleanup)
        cls.manifest = build(Path(cls.tmp.name),native_grain=True,native_color=True,recipe_snapshot=True,lifecycle_trace=True)
        cls.code = (Path(cls.tmp.name) / 'm10v-library-arm.bin').read_bytes()
        host_tests.NativeFilmLibraryTests.setUpClass(); cls.addClassCleanup(host_tests.NativeFilmLibraryTests.doClassCleanups)

    @contextmanager
    def runtime_profile(self,**options):
        original_manifest,original_code=self.manifest,self.code
        try:
            with tempfile.TemporaryDirectory() as folder:
                self.manifest=build(Path(folder),**options)
                self.code=(Path(folder)/'m10v-library-arm.bin').read_bytes()
                yield
        finally:self.manifest,self.code=original_manifest,original_code

    def test_software_halation_edits_clear_legacy_grain_without_losing_other_slots(self):
        with self.runtime_profile():
            u=self.machine();state=0x55001000;ui=0x55007000
            self.call(u,'m10v_library_init',state)
            old=bytearray(u.mem_read(state,C.sizeof(State)))
            struct.pack_into('<H',old,20,33);old[22]=3
            struct.pack_into('<I',old,8,7);struct.pack_into('<I',old,100,zlib.crc32(old[:100]))
            self.files['M10V5B.bin']=bytes(old)
            u.mem_write(ui+0x198,bytes([18,0,8,0,0,0,0,0]))
            self.assertEqual(self.call(u,'m10v_detail_control',2,ui,6),1)
            self.assertEqual(self.call(u,'m10v_camera_library_load',state),0)
            saved=State.from_buffer_copy(u.mem_read(state,C.sizeof(State)))
            self.assertEqual((saved.slots[1].halo_gain,saved.slots[1].grain),(6,0))
            original=State.from_buffer_copy(old)
            self.assertEqual(bytes(saved.slots[0]),bytes(original.slots[0]))
            self.assertEqual(self.files['M10V5B.bin'],bytes(old))
            model=0x55068200;u.mem_write(model+0x1d,b'\x01')
            ids=[self.call(u,'m10v_menu_index',model,i) for i in range(self.call(u,'m10v_menu_count',model))]
            self.assertEqual(ids,[129,132,133,214]);u.mem_write(model+0x1d,b'\x03')
            self.assertEqual(self.call(u,'m10v_menu_count',model),0)

    def machine(self):
        base = self.manifest['base']; u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        u.mem_map(base, (len(self.code) + 4095) & ~4095); u.mem_write(base, self.code)
        u.mem_protect(base,(len(self.code)+4095)&~4095,UC_PROT_READ|UC_PROT_EXEC)
        u.mem_map(0x55000000, 0x100000)
        self.store_result = 0; self.saved = []; self.files = {}; self.file_calls = []
        self.focus = 0; self.current_tone = 18; self.native_tones = []; self.redraws = 0; self.captions = []; self.forwarded = []
        for address in (0x53828000, 0x53825000): u.mem_map(address, 8192)
        u.mem_write(0x55004008, struct.pack('<I', 0x55004100))
        u.mem_write(0x55004100, struct.pack('<I', 0x55004200))
        u.mem_write(0x55004220, b'\x01')
        u.mem_write(0x55068200, bytes([18]) + bytes(31))
        u.mem_write(0x55005174, struct.pack('<I', 0x55005200))
        u.mem_write(0x55005160, struct.pack('<I', 0x55005300))
        for address in (0x5320a000, 0x532bd000, 0x53394000, 0x53396000, 0x531ac000): u.mem_map(address, 8192)
        def services(uc, address, size, data):
            if address == 0x550ff100:
                self.saved.append(bytes(uc.mem_read(uc.reg_read(UC_ARM_REG_R1), C.sizeof(State))))
                uc.reg_write(UC_ARM_REG_R0, self.store_result & 0xffffffff)
                uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
            elif address == 0x53828014:
                uc.reg_write(UC_ARM_REG_R0, 0x55004000); uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
            elif address in (0x53825648, 0x53825fa8):
                fs, name, length, buffer = [uc.reg_read(r) for r in
                    (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)]
                self.assertEqual(fs, 0x55004200); self.assertIn(length,(C.sizeof(State),64,44))
                filename = bytes(uc.mem_read(name, 12)).split(b'\0')[0].decode()
                self.assertIn(filename, ('M10V5A.bin','M10V5B.bin','M10V4A.bin','M10V4B.bin','M10V3A.bin','M10V3B.bin','M10V2A.bin','M10V2B.bin','M10V0.bin','M10V1.bin'))
                self.file_calls.append((address, filename))
                result = 0
                if address == 0x53825fa8 and self.store_result == 0:
                    self.files[filename] = bytes(uc.mem_read(buffer, length)); result = 1
                elif address == 0x53825648 and filename in self.files and len(self.files[filename])==length:
                    uc.mem_write(buffer, self.files[filename]); result = 1
                uc.reg_write(UC_ARM_REG_R0, result); uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
            elif address in (0x5320ad88, 0x5320ba9c, 0x532bd6b4, 0x53394820, 0x53395430, 0x531ac074, 0x53396f80):
                if address == 0x5320ad88: uc.reg_write(UC_ARM_REG_R0, 0x55006000)
                elif address == 0x5320ba9c: uc.reg_write(UC_ARM_REG_R0, 0x55068200)
                elif address == 0x532bd6b4: uc.reg_write(UC_ARM_REG_R0, self.current_tone)
                elif address == 0x53394820: uc.reg_write(UC_ARM_REG_R0, self.focus)
                elif address == 0x53395430: self.focus = uc.reg_read(UC_ARM_REG_R1)
                elif address == 0x531ac074: self.redraws += 1
                elif address == 0x53396f80: self.captions.append(uc.reg_read(UC_ARM_REG_R1))
                uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
            elif base <= address < base + 0x100 and (address - base) % 16 == 0:
                offset = address - base; self.forwarded.append(offset)
                if offset == 0:
                    self.current_tone = uc.reg_read(UC_ARM_REG_R1)
                    self.native_tones.append(self.current_tone)
                if offset == 0x80: uc.reg_write(UC_ARM_REG_R0, 12)
                if offset == 0x90: uc.reg_write(UC_ARM_REG_R0, 11 + uc.reg_read(UC_ARM_REG_R1))
                uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
        u.hook_add(UC_HOOK_CODE, services); return u

    def call(self, u, name, *args):
        sp = 0x550fe000; stop = 0x550ff000
        for reg, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), args[:4]):
            u.reg_write(reg, value)
        for i, value in enumerate(args[4:]): u.mem_write(sp + i * 4, struct.pack('<I', value))
        u.reg_write(UC_ARM_REG_SP, sp); u.reg_write(UC_ARM_REG_LR, stop)
        u.emu_start(self.manifest['symbols'][name], stop, count=20000000)
        self.assertEqual(u.reg_read(UC_ARM_REG_PC), stop)
        result = u.reg_read(UC_ARM_REG_R0)
        return result if result < 0x80000000 else result - 0x100000000

    def test_icon_catalog_and_five_slots_follow_selected_films(self):
        u=self.machine()
        for film in range(1,79):
            tone=144+film-1 if film<=32 else 213 if film==33 else 344+film-69 if film>=69 else 288+film-66 if film>=66 else 256+film-34
            self.assertEqual(self.call(u,'m10v_menu_icon',0,tone),762+film-291 if 291<=film<=297 else 755 if film==290 else 749 if film==289 else 670+film)
        state=0x55008000
        self.call(u,'m10v_library_init',state)
        self.assertEqual(self.call(u,'m10v_camera_library_select',state,1,65),0)
        self.assertEqual(self.call(u,'m10v_menu_icon',0,18),735)
        self.assertEqual(self.call(u,'m10v_menu_icon',0,209),735)
        self.assertEqual(self.call(u,'m10v_menu_icon',0,21),703)

    def test_detail_lists_offer_only_controls_consumed_by_each_film(self):
        common = [21]
        for film, ids in ((33,[18,19,20]+common),(35,common),(66,common),
                          (67,[18,19,20]+common+[28]),(68,common+[28]),(289,[29]),(290,[])):
            with self.subTest(film=film):
                u=self.machine();state=0x55001000;ui=0x55007000
                self.call(u,'m10v_library_init',state)
                self.assertEqual(self.call(u,'m10v_camera_library_select',state,1,film),0)
                u.mem_write(ui+0x198,bytes([18,0,8,0,0,0,0,0]))
                table=self.call(u,'m10v_detail_table',ui)
                self.assertNotEqual(table,0x53b3488c)
                pointer,count=struct.unpack('<II',u.mem_read(table+8*8,8))
                entries=bytes(u.mem_read(pointer,count*2))
                self.assertEqual([v for v in entries[1::2] if v>=18],ids)
                # One immediate callback must be visible to a fresh capture load.
                self.assertEqual(self.call(u,'m10v_detail_control',2,ui,(3<<8)|3),0 if film in (289,290) else 1)
                self.assertEqual(self.call(u,'m10v_camera_library_load',state),0)
                saved=State.from_buffer_copy(u.mem_read(state,C.sizeof(State)))
                self.assertEqual(saved.slots[1].grain,0 if film in (289,290) else 3)
                self.assertEqual(saved.slots[0].grain,0)

    def test_charmera_native_color_row_persists_four_values_and_rejects_overflow(self):
        u=self.machine();state=0x55001000;ui=0x55007000
        self.call(u,'m10v_library_init',state);self.call(u,'m10v_camera_library_select',state,1,289)
        u.mem_write(ui+0x198,bytes([18,0,8,0,0,0,0,0]))
        for color in range(4):
            self.assertEqual(self.call(u,'m10v_detail_control',2,ui,(11<<8)|color),1)
            self.assertEqual(self.call(u,'m10v_detail_control',1,ui,11),color)
            self.call(u,'m10v_camera_library_load',state)
            saved=State.from_buffer_copy(u.mem_read(state,C.sizeof(State)))
            self.assertEqual(saved.effects[1][7],color)
        before=dict(self.files);self.assertEqual(self.call(u,'m10v_detail_control',2,ui,(11<<8)|4),0)
        self.assertEqual(self.files,before);self.store_result=-1
        self.assertEqual(self.call(u,'m10v_detail_control',2,ui,(11<<8)|0),0);self.assertEqual(self.files,before)

    def test_detail_effect_callbacks_are_bounded_persistent_and_failure_atomic(self):
        for film in (35,66,67,68):
            u=self.machine();state=0x55001000;ui=0x55007000
            self.call(u,'m10v_library_init',state)
            self.call(u,'m10v_camera_library_select',state,1,film)
            u.mem_write(ui+0x198,bytes([18,0,8,0,0,0,0,0]))
            before=dict(self.files);initial=bytes(u.mem_read(state,C.sizeof(State)))
            for field,value in ((5,2),(6,8),(7,5),(8,8),(9,1)):
                self.assertEqual(self.call(u,'m10v_detail_control',2,ui,(field<<8)|value),0)
                self.assertEqual(self.files,before)
                self.assertEqual(bytes(u.mem_read(state,C.sizeof(State))),initial)
            # Supported grain callbacks still save atomically and restore on failure.
            self.assertEqual(self.call(u,'m10v_detail_control',2,ui,(3<<8)|3),1)
            before=dict(self.files);self.store_result=-1
            self.assertEqual(self.call(u,'m10v_detail_control',2,ui,(3<<8)|0),0)
            self.assertEqual(self.files,before)
            self.store_result=0
            self.assertEqual(self.call(u,'m10v_detail_control',2,ui,(10<<8)|2),1 if film==68 else 0)

    def test_detail_reset_restores_all_visible_fields_in_one_atomic_slot_commit(self):
        for film,grain,gain,retired_spread in ((33,0,0,0),(35,0,0,4),(66,0,0,0),(67,0,0,0),(68,0,0,0)):
            with self.subTest(film=film):
                u=self.machine();state=0x55001000;ui=0x55007000
                self.call(u,'m10v_library_init',state)
                self.call(u,'m10v_camera_library_select',state,1,film)
                u.mem_write(ui+0x198,bytes([18,0,8,0,0,0,0,0]))
                for field,v in ((3,3),(4,3),(5,2),(6,8),(7,5),(8,8),(9,1)):
                    self.call(u,'m10v_detail_control',2,ui,(field<<8)|v)
                if film in (33,67):self.call(u,'m10v_detail_control',2,ui,8)
                if film==68:self.call(u,'m10v_detail_control',2,ui,(10<<8)|2)
                self.call(u,'m10v_camera_library_load',state)
                old=State.from_buffer_copy(u.mem_read(state,C.sizeof(State)))
                self.file_calls.clear()
                self.assertEqual(self.call(u,'m10v_detail_control',7,ui,0),1)
                self.assertEqual(sum(a==0x53825fa8 for a,_ in self.file_calls),1)
                self.call(u,'m10v_camera_library_load',state)
                fresh=State.from_buffer_copy(u.mem_read(state,C.sizeof(State)))
                self.assertEqual((fresh.slots[1].film,fresh.slots[1].grain,fresh.slots[1].soft),(film,grain,0))
                if film in (33,67):self.assertEqual((fresh.slots[1].halo_gain,fresh.slots[1].halo_spread,fresh.slots[1].halo_threshold),(gain,3,5))
                self.assertEqual(list(fresh.effects[1]),[0,0,0,retired_spread,0,0,0,0])
                self.assertEqual(bytes(fresh.slots[0]),bytes(old.slots[0]))
                self.assertEqual(bytes(fresh.effects[0]),bytes(old.effects[0]))
                before=dict(self.files);self.store_result=-1
                self.assertEqual(self.call(u,'m10v_detail_control',7,ui,0),0)
                self.assertEqual(self.files,before)

    def test_failed_detail_load_never_exposes_defaults_as_saved_settings(self):
        u=self.machine();state=0x55001000;ui=0x55007000
        self.call(u,'m10v_library_init',state)
        self.call(u,'m10v_camera_library_select',state,1,66)
        u.mem_write(ui+0x198,bytes([18,0,8,0,0,0,0,0]))
        before=dict(self.files);u.mem_write(0x55004220,b'\0')
        self.assertEqual(self.call(u,'m10v_detail_table',ui),0x53b3488c)
        self.assertEqual(self.call(u,'m10v_detail_control',2,ui,(3<<8)|3),0)
        self.assertEqual(self.files,before)

    def test_slot_names_follow_saved_films_in_main_and_slot_selection_lists(self):
        u = self.machine(); state = 0x55008000
        self.call(u, 'm10v_library_init', state)
        # Catalog IDs and captions are independently assigned: 33 is 800T;
        # legacy catalog 34..65 occupies captions 879..910.
        for slot, film, caption in [(0, 1, 786), (1, 64, 909), (2, 56, 901),
                                    (3, 54, 899), (4, 33, 860), (0, 67, 930), (1, 68, 931)]:
            self.assertEqual(self.call(u, 'm10v_camera_library_select', state, slot, film), 0)
            tone = (12, 18, 19, 20, 21)[slot]
            self.assertEqual(self.call(u, 'm10v_menu_name', 0, tone), caption)
            self.assertEqual(self.call(u, 'm10v_menu_name', 0, 208 + slot), caption)
        self.assertEqual(self.call(u, 'm10v_camera_library_select', state, 4, 65), 0)
        self.assertEqual(self.call(u, 'm10v_menu_name', 0, 21), 910)
        self.assertEqual(self.call(u, 'm10v_menu_name', 0, 212), 910)

    def test_open_library_targets_highlighted_slot_instead_of_entry_snapshot(self):
        u = self.machine(); state = 0x55008000; model = 0x55068200
        self.call(u, 'm10v_library_init', state)
        self.assertEqual(self.call(u, 'm10v_camera_library_select', state, 4, 33), 0)
        self.assertEqual(self.call(u, 'm10v_camera_library_halation', state, 4, 8, 1, 7, 3), 0)
        # Stock m[0] is the entry snapshot; browsing changed the active tone.
        self.current_tone = 21
        self.focus = 12; self.call(u, 'm10v_menu_confirm', 0x55005000)
        self.assertEqual(u.mem_read(model, 1), b'\x12')
        self.focus = 4; self.call(u, 'm10v_menu_confirm', 0x55005000)
        self.focus = 0; self.call(u, 'm10v_menu_confirm', 0x55005000)
        self.assertEqual(u.mem_read(model + 0x1d, 1), b'\x0b')
        self.assertEqual(self.focus, 8)
        self.assertFalse(self.native_tones)
        # Pick another slot without altering the stock cancellation snapshot.
        u.mem_write(model + 0x1d, b'\x06'); self.focus = 3
        self.call(u, 'm10v_menu_confirm', 0x55005000)
        self.assertEqual(u.mem_read(model, 1), b'\x12')
        self.assertEqual(u.mem_read(model + 0x1e, 1), b'\x14')

    def test_original_icon_dimensions_and_bitmap_pointer_with_flags_preserved(self):
        from subprocess import check_output
        root=Path(__file__).resolve().parents[1]
        js="import {readFileSync} from 'node:fs';import {officialResources} from './node/gr3-stock-presets.mjs';const {decoded:d,sections:s}=officialResources(readFileSync('bin/fwdc239b-gr3-official.bin'));process.stdout.write(d.subarray(s.RTOS.offset,s.RTOS.offset+s.RTOS.size));"
        rtos=check_output(['node','--input-type=module','-e',js],cwd=root)
        u=self.machine();u.mem_map(0x53209000,4096)
        table=self.manifest['icons']['table']
        for start,end in [(0x53209fb8,0x53209fec),(0x53209fec,0x5320a020)]:
            u.mem_write(start,rtos[start-0x53000000:end-0x53000000])
            u.mem_write(start,struct.pack('<I',0xe300329e+0x41)) # 670 -> 735
            low=start+20;high=start+24
            def mov(op,reg,val):return op|((val&0xf000)<<4)|(reg<<12)|(val&0xfff)
            u.mem_write(low,struct.pack('<II',mov(0xe3000000,3,table&65535),mov(0xe3400000,3,table>>16)))
            for identifier in [671,703,735,736]:
                u.reg_write(UC_ARM_REG_R1,identifier);u.reg_write(UC_ARM_REG_LR,0x550ff000)
                u.emu_start(start,0x550ff000,count=100)
                self.assertEqual(u.reg_read(UC_ARM_REG_R0),40 if identifier<=735 else 0)
        # Run the new pointer shim at the exact point where stock drawing
        # consumes an ICONBIN-relative word offset. Private pixels are ROM.
        for identifier in [548,671,703,735]:
            u.mem_write(0x55009024,struct.pack('<H',identifier))
            offset=(self.manifest['icons']['pixels']+(identifier-671)*6400)//4 if identifier>=671 else 1234
            for reg,val in [(UC_ARM_REG_R0,11),(UC_ARM_REG_R1,22),(UC_ARM_REG_R2,33),(UC_ARM_REG_R3,44),(UC_ARM_REG_R5,0x55009000),(UC_ARM_REG_R6,offset),(UC_ARM_REG_LR,0x57000000),(UC_ARM_REG_SP,0x550fe000)]:u.reg_write(reg,val)
            u.reg_write(UC_ARM_REG_CPSR,0xa00001d3)
            u.emu_start(self.manifest['symbols']['m10v_icon_pixels'],0x5320a838,count=100)
            self.assertEqual(u.reg_read(UC_ARM_REG_R12),offset*4+(0 if identifier>=671 else 0x57000000))
            for reg,val in [(UC_ARM_REG_R0,11),(UC_ARM_REG_R1,22),(UC_ARM_REG_R2,33),(UC_ARM_REG_R3,44),(UC_ARM_REG_SP,0x550fe000)]:self.assertEqual(u.reg_read(reg),val)
            self.assertEqual(u.reg_read(UC_ARM_REG_CPSR)&0xf8000000,0xa0000000)
        from PIL import Image as PILImage
        pixels=(root/'native/gr3/m10v_icons.rgba').read_bytes()
        for i in range(78):
            with PILImage.open(root/f'web/gr3/film-icons/{i+1:02d}.png') as im:self.assertEqual(im.convert('RGBA').tobytes(),pixels[i*6400:(i+1)*6400])
        red=pixels[32*6400+(8*40+20)*4:32*6400+(8*40+20)*4+4]
        self.assertGreater(red[0],red[1]*2)

    def test_official_list_consumer_allocates_57_rows_and_renders_55_visible_films(self):
        # The raw instruction fixture comes from the official decompression,
        # not a reimplementation of its row count/loop.
        from subprocess import check_output
        root = Path(__file__).resolve().parents[1]
        script = "import {readFileSync} from 'node:fs';import {decodeFrameMap} from './node/gr3-frames.mjs';import {inspectOfficial} from './node/firmware.mjs';const b=readFileSync('bin/fwdc239b-gr3-official.bin'),d=decodeFrameMap(b).decoded;let at=0;for(const row of inspectOfficial(b).sections){if(row.name==='RTOS'){process.stdout.write(d.subarray(at+16,at+row.size));break;}at+=row.size;}"
        rtos = check_output(['node','--input-type=module','-e',script],cwd=root)
        self.assertEqual(__import__('hashlib').sha256(rtos).hexdigest(), '8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67')
        u = self.machine()
        u.mem_map(0x531ab000,4096);u.mem_map(0x532c2000,4096);u.mem_map(0x53293000,4096);u.mem_map(0x532a9000,4096);u.mem_map(0x533a1000,4096)
        for address,length in [(0x531abc18,36),(0x531ab7e4,0x130)]:
            u.mem_write(address,rtos[address-0x53000000:address-0x53000000+length])
        for address,name in [(0x532c2b7c,'m10v_menu_max_count'),(0x532c2a9c,'m10v_menu_count'),(0x532c2c80,'m10v_menu_index'),(0x532935dc,'m10v_menu_icon'),(0x532a9988,'m10v_menu_value_icon')]:
            delta=self.manifest['symbols'][name]-address-8
            u.mem_write(address,struct.pack('<I',0xea000000|((delta>>2)&0xffffff)))
        rows=[]
        def view(uc,address,size,data):
            if address == 0x5320b67c: uc.reg_write(UC_ARM_REG_R0,0x55007000)
            elif address == 0x53394758:
                index=uc.reg_read(UC_ARM_REG_R1);rows.append(index);self.assertLess(index,57)
                uc.reg_write(UC_ARM_REG_R0,0x55008000+index*4)
            elif address != 0x533a1734: return
            uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
        u.hook_add(UC_HOOK_CODE,view)
        u.reg_write(UC_ARM_REG_SP,0x550fe000);u.reg_write(UC_ARM_REG_LR,0x550ff000)
        u.emu_start(0x531abc18,0x550ff000,count=100000)
        self.assertEqual(u.reg_read(UC_ARM_REG_R0),57)
        u.mem_write(0x5506821d,b'\x02');u.mem_write(0x550051a9,b'\x2d')
        u.reg_write(UC_ARM_REG_SP,0x550fe000);u.reg_write(UC_ARM_REG_LR,0x550ff000);u.reg_write(UC_ARM_REG_R0,0x55005000)
        u.emu_start(0x531ab7e4,0x550ff000,count=100000)
        self.assertEqual(rows,list(range(57)))

    def test_compiled_browser_defaults_initialize_exact_arm_state(self):
        initial = bytearray(104)
        struct.pack_into('<IHHI', initial, 0, 0x5630314d, 4, 104, 0)
        for i in range(5): struct.pack_into('<H6B', initial, 12+i*8, 65-i, i%4, (i+2)%4,8,1,7,3)
        initial[52:56] = bytes([2,3,2,1])
        for i in range(5):initial[56+i*8]=1;initial[59+i*8]=4
        struct.pack_into('<I', initial, 100, zlib.crc32(initial[:100]))
        with tempfile.TemporaryDirectory() as folder:
            manifest = build(Path(folder), initial_state_hex=initial.hex(),native_grain=True,native_color=True,recipe_snapshot=True,lifecycle_trace=True)
            code = (Path(folder)/'m10v-library-arm.bin').read_bytes()
        u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        u.mem_map(manifest['base'], (len(code)+4095)&~4095); u.mem_write(manifest['base'], code)
        u.mem_map(0x55000000, 0x100000)
        u.reg_write(UC_ARM_REG_SP,0x550fe000);u.reg_write(UC_ARM_REG_R0,0x55001000);u.reg_write(UC_ARM_REG_LR,0x550ff000)
        u.emu_start(manifest['symbols']['m10v_library_init'],0x550ff000,count=100000)
        self.assertEqual(bytes(u.mem_read(0x55001000,C.sizeof(State))),bytes(initial))
        self.assertEqual(manifest['initial_state_hex'],initial.hex())
        with tempfile.TemporaryDirectory() as folder:
            initial[52] = 9
            with self.assertRaises(ValueError): build(Path(folder), initial_state_hex=initial.hex())

    def test_arm_initialization_and_persist_failure_are_atomic(self):
        u = self.machine(); state = 0x55001000
        self.call(u, 'm10v_library_init', state)
        before = bytes(u.mem_read(state, C.sizeof(State)))
        self.assertEqual([s.film for s in State.from_buffer_copy(before).slots], [34,35,36,37,33])
        self.assertTrue(all(not v.grain and not v.soft and not v.halo_gain for v in State.from_buffer_copy(before).slots))
        self.assertEqual(self.call(u, 'm10v_library_valid', state), 1)
        self.store_result = -1
        self.assertEqual(self.call(u, 'm10v_library_select', state, 4, 32, 0x550ff100, 0), -2)
        self.assertEqual(bytes(u.mem_read(state, C.sizeof(State))), before)
        self.store_result = 0
        self.assertEqual(self.call(u, 'm10v_library_select', state, 4, 32, 0x550ff100, 0), 0)
        self.assertEqual(State.from_buffer_copy(u.mem_read(state, C.sizeof(State))).slots[4].film, 32)
        self.assertEqual(self.call(u, 'm10v_library_valid', state), 1)

    def test_arm_all_effects_match_host_and_preserve_pixel_padding(self):
        u = self.machine(); state = 0x55001000
        self.call(u, 'm10v_library_init', state)
        self.call(u, 'm10v_library_select', state, 0, 2, 0x550ff100, 0)
        self.call(u, 'm10v_library_texture', state, 0, 2, 3, 0x550ff100, 0)
        self.call(u, 'm10v_library_stamp', state, 2, 2, 3, 1, 0x550ff100, 0)
        width, height, stride = 128, 96, 136; size = stride * height
        y = bytearray([64] * size + [173] * 32); uv = bytearray([128] * size + [197] * 32)
        for row in range(height):
            y[row * stride + width:(row + 1) * stride] = bytes([173] * 8)
            uv[row * stride + width:(row + 1) * stride] = bytes([197] * 8)
        y[48 * stride + 64] = 255
        date = Date(2026, 10, 14, 23, 59)
        u.mem_write(0x55002000, struct.pack('<7I', 0x55010000, 0x55020000, size, size, width, height, stride))
        u.mem_write(0x55003000, bytes(date)); u.mem_write(0x55010000, bytes(y)); u.mem_write(0x55020000, bytes(uv))
        u.mem_write(0x55030000, bytes([91]) * (2 * width * height + 32))
        self.assertEqual(self.call(u, 'm10v_library_render', 0x55002000, state, 0, 0x55003000,
                                  123, 0x55030000, 2 * width * height), 0)
        host_state = State.from_buffer_copy(u.mem_read(state, C.sizeof(State)))
        host_y = (C.c_uint8 * len(y)).from_buffer_copy(y); host_uv = (C.c_uint8 * len(uv)).from_buffer_copy(uv)
        scratch = (C.c_uint8 * (2 * width * height))()
        image = Image(host_y, host_uv, size, size, width, height, stride)
        self.assertEqual(host_tests.NativeFilmLibraryTests.lib.m10v_library_render(C.byref(image), C.byref(host_state),
                         0, C.byref(date), 123, scratch, len(scratch)), 0)
        self.assertEqual(bytes(u.mem_read(0x55010000, len(y))), bytes(host_y))
        self.assertEqual(bytes(u.mem_read(0x55020000, len(uv))), bytes(host_uv))
        self.assertEqual(bytes(u.mem_read(0x55030000 + 2 * width * height, 32)), bytes([91]) * 32)

    def test_internal_camera_journal_uses_native_fs_abi_and_survives_bad_latest_record(self):
        u = self.machine(); state = 0x55001000
        self.assertEqual(self.call(u, 'm10v_camera_library_load', state), 1)
        self.assertEqual(self.call(u, 'm10v_camera_library_select', state, 1, 32), 0)
        first = bytes(u.mem_read(state, C.sizeof(State)))
        self.assertIn('M10V5B.bin', self.files)
        self.assertEqual(self.call(u, 'm10v_camera_library_select', state, 4, 17), 0)
        self.assertIn('M10V5A.bin', self.files)
        fresh = 0x55002000
        self.assertEqual(self.call(u, 'm10v_camera_library_load', fresh), 0)
        self.assertEqual(bytes(u.mem_read(fresh, C.sizeof(State))), bytes(u.mem_read(state, C.sizeof(State))))
        damaged = bytearray(self.files['M10V5A.bin']); damaged[16] ^= 1
        self.files['M10V5A.bin'] = bytes(damaged)
        self.assertEqual(self.call(u, 'm10v_camera_library_load', fresh), 0)
        self.assertEqual(bytes(u.mem_read(fresh, C.sizeof(State))), first)
        self.store_result = -1; before = bytes(u.mem_read(fresh, C.sizeof(State)))
        self.assertEqual(self.call(u, 'm10v_camera_library_select', fresh, 0, 31), -2)
        self.assertEqual(bytes(u.mem_read(fresh, C.sizeof(State))), before)

    def test_menu_browsing_has_no_writes_and_confirm_installs_into_cached_target_slot(self):
        u = self.machine(); model = 0x55068200; controller = 0x55005000
        self.assertEqual(self.call(u, 'm10v_menu_count', model), 13)
        self.assertEqual(self.call(u, 'm10v_menu_index', model, 12), 128)
        self.call(u, 'm10v_menu_focus', controller, 12)
        self.assertFalse(self.native_tones); self.assertFalse(self.files)
        self.focus = 12; self.call(u, 'm10v_menu_confirm', controller)
        self.assertEqual(u.mem_read(model + 0x1d, 1), b'\x01')

        self.assertEqual(self.call(u, 'm10v_menu_count', model), 4)
        self.focus = 0; self.call(u, 'm10v_menu_confirm', controller)
        self.assertEqual(self.call(u, 'm10v_menu_count', model), 55)
        self.call(u, 'm10v_menu_focus', controller, 45)
        self.assertFalse(self.files); self.assertFalse(self.native_tones)
        self.focus = 45; self.call(u, 'm10v_menu_confirm', controller)
        state = State.from_buffer_copy(self.files['M10V5B.bin'])
        self.assertEqual(state.slots[1].film, 64)
        self.assertEqual(self.native_tones, [18])
        self.assertTrue(all(value < 25 for value in self.native_tones))
        self.assertEqual(u.mem_read(model + 0x1d, 1), b'\x01')

    def test_visible_catalog_index_names_and_icons_are_consistent(self):
        u=self.machine(); model=0x55068200
        u.mem_write(model+0x1d,b'\x02')
        self.assertEqual(self.call(u,'m10v_menu_max_count'),55)
        self.assertEqual(self.call(u,'m10v_menu_count',model),55)
        ids=[33,66,67,68,69,70,71,72,73,74,75,76,77,78,289]+list(range(34,66))+[290]+list(range(291,298))
        for index,film in enumerate(ids):
            tone=self.call(u,'m10v_menu_index',model,index)
            self.assertEqual(tone,400+film-291 if 291<=film<=297 else 360 if film==290 else 354 if film==289 else 213 if film==33 else 344+film-69 if film>=69 else 288+film-66 if film>=66 else 256+film-34)
            self.assertEqual(self.call(u,'m10v_menu_name',0,tone),954+film-291 if 291<=film<=297 else 953 if film==290 else 947 if film==289 else 860 if film==33 else 937+film-69 if film>=69 else 930+film-67 if film>=67 else 911 if film==66 else 879+film-34)
            self.assertEqual(self.call(u,'m10v_menu_icon',0,tone),762+film-291 if 291<=film<=297 else 755 if film==290 else 749 if film==289 else 670+film)
        self.assertEqual(self.call(u,'m10v_menu_index',model,55),0)
        self.assertFalse(self.files);self.assertFalse(self.native_tones)

    def test_legacy_simulation_really_executes_on_arm_with_pixel_exact_host_output(self):
        for film in (34,38,45,65,67,68,69,70,71,72,289,290):
            u=self.machine();state=0x55001000
            self.call(u,'m10v_library_init',state);self.call(u,'m10v_library_select',state,0,film,0x550ff100,0)
            if film==67:self.call(u,'m10v_library_halation',state,0,0,3,5,2,0x550ff100,0)
            width,height,stride=32,16,40;size=stride*height
            y=bytes((i*37+19)%256 for i in range(size));uv=bytes((i*13+97)%256 for i in range(size))
            u.mem_write(0x55010000,y);u.mem_write(0x55020000,uv)
            u.mem_write(0x55002000,struct.pack('<7I',0x55010000,0x55020000,size,size,width,height,stride))
            self.assertEqual(self.call(u,'m10v_library_render',0x55002000,state,0,0,0,0,0),0)
            hstate=State.from_buffer_copy(u.mem_read(state,C.sizeof(State)));hy=(C.c_uint8*size).from_buffer_copy(y);hc=(C.c_uint8*size).from_buffer_copy(uv)
            image=Image(hy,hc,size,size,width,height,stride)
            self.assertEqual(host_tests.NativeFilmLibraryTests.lib.m10v_library_render(C.byref(image),C.byref(hstate),0,None,0,None,0),0)
            self.assertEqual(bytes(u.mem_read(0x55010000,size)),bytes(hy));self.assertEqual(bytes(u.mem_read(0x55020000,size)),bytes(hc))
            self.assertNotEqual(bytes(hy),y)
            for row in range(height):
                self.assertEqual(bytes(hy)[row*stride+width:(row+1)*stride],y[row*stride+width:(row+1)*stride])
                self.assertEqual(bytes(hc)[row*stride+width:(row+1)*stride],uv[row*stride+width:(row+1)*stride])

    def test_previous_800t_journal_migrates_without_reusing_aggressive_parameters(self):
        u=self.machine();addr=0x55001000
        self.call(u,'m10v_library_init',addr)
        old=bytearray(u.mem_read(addr,56))+bytearray(8);struct.pack_into('<HHI',old,4,2,64,19)
        struct.pack_into('<H6B',old,44,33,2,1,8,8,0,3)
        struct.pack_into('<I',old,60,zlib.crc32(old[:60]));self.files['M10V2B.bin']=bytes(old)
        self.assertEqual(self.call(u,'m10v_camera_library_load',addr),2)
        state=State.from_buffer_copy(u.mem_read(addr,C.sizeof(State)));v=state.slots[4]
        self.assertEqual([v.halo_gain,v.halo_spread,v.halo_threshold,v.halo_profile],[3,3,5,2])
        self.assertEqual([v.grain,v.soft],[2,1]);self.assertEqual(state.sequence,19)
        self.assertEqual(self.files['M10V2B.bin'],bytes(old))
        self.assertEqual(self.call(u,'m10v_camera_library_detail',addr,4,6,2,7,1,2),0)
        self.assertIn('M10V5A.bin',self.files)
        self.assertEqual(self.call(u,'m10v_camera_library_load',addr),0)
        state=State.from_buffer_copy(u.mem_read(addr,C.sizeof(State)))
        self.assertEqual([state.slots[4].halo_gain,state.slots[4].soft],[6,2])

    def test_old_44_byte_journal_migrates_without_overwriting_legacy_files(self):
        u=self.machine();old=bytearray(44)
        struct.pack_into('<IHHI',old,0,0x5630314d,1,44,7)
        for i in range(5):struct.pack_into('<HBB',old,12+4*i,33-i,i%4,(i+1)%4)
        old[32:36]=bytes([2,3,2,1]);struct.pack_into('<I',old,40,zlib.crc32(old[:40]))
        self.files['M10V1.bin']=bytes(old)
        self.assertEqual(self.call(u,'m10v_camera_library_load',0x55001000),3)
        state=State.from_buffer_copy(u.mem_read(0x55001000,C.sizeof(State)))
        self.assertEqual((state.version,state.size,state.sequence),(4,104,7))
        self.assertEqual([s.film for s in state.slots],[33,32,31,30,29])
        self.assertEqual([state.slots[0].halo_gain,state.slots[0].halo_spread,state.slots[0].halo_threshold,state.slots[0].halo_profile],[0,3,5,2])
        self.assertEqual(self.call(u,'m10v_camera_library_halation',0x55001000,0,8,1,7,3),0)
        self.assertEqual(self.files['M10V1.bin'],bytes(old));self.assertIn('M10V5A.bin',self.files)
        self.assertEqual(self.call(u,'m10v_camera_library_load',0x55001000),0)
        state=State.from_buffer_copy(u.mem_read(0x55001000,C.sizeof(State)));self.assertEqual(state.slots[0].halo_gain,8)

    def test_halation_menu_commits_three_controls_and_reopens_from_journal(self):
        u=self.machine();model=0x55068200;controller=0x55005000
        for mode,index in [(11,8),(12,1),(13,7)]:
            u.mem_write(model+0x1d,bytes([mode]));self.focus=index
            self.assertEqual(self.call(u,'m10v_menu_confirm',controller),0)
            self.assertEqual(u.mem_read(model+0x1d,1),b'\x0a')
        self.assertEqual(self.call(u,'m10v_camera_library_load',0x55001000),0)
        state=State.from_buffer_copy(u.mem_read(0x55001000,C.sizeof(State)));slot=state.slots[1]
        self.assertEqual([slot.halo_gain,slot.halo_spread,slot.halo_threshold,slot.halo_profile],[8,1,7,2])
        self.assertEqual(self.call(u,'m10v_library_valid',0x55001000),1)
        self.assertFalse(self.native_tones)

    def test_local_switch_pointer_relocation_is_bounded_to_arm_text(self):
        import subprocess,shutil
        from scripts.build_gr3_m10v_library import link_object
        compiler='/opt/homebrew/opt/llvm/bin/clang'
        if not Path(compiler).is_file():compiler=shutil.which('clang')
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            for addend in (0,4096):
                source=folder/'switch.S';obj=folder/'switch.o'
                source.write_text('.syntax unified\n.arm\n.text\n.global m10v_resource_primary\n.type m10v_resource_primary,%function\nm10v_resource_primary: bx lr\n.global m10v_resource_secondary\n.type m10v_resource_secondary,%function\nm10v_resource_secondary: bx lr\n.section .rodata\n.word m10v_resource_secondary+'+str(addend)+'\n')
                subprocess.run([compiler,'--target=armv7-none-eabi','-marm','-c',str(source),'-o',str(obj)],check=True,capture_output=True)
                if addend:
                    with self.assertRaisesRegex(ValueError,'leaves local immutable image'):link_object(obj.read_bytes(),0x540b6000,prefix='m10v_resource_')
                else:
                    code,symbols=link_object(obj.read_bytes(),0x540b6000,prefix='m10v_resource_')
                    self.assertEqual(struct.unpack_from('<I',code,len(code)-4)[0],symbols['m10v_resource_secondary'])

    def test_local_rodata_pointer_relocation_is_bounded_to_immutable_image(self):
        import subprocess,shutil
        from scripts.build_gr3_m10v_library import link_object
        compiler='/opt/homebrew/opt/llvm/bin/clang'
        if not Path(compiler).is_file():compiler=shutil.which('clang')
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            for addend in (0,4096):
                source=folder/'pointer.S';obj=folder/'pointer.o'
                source.write_text('.syntax unified\n.arm\n.text\n.global m10v_resource_primary\n.type m10v_resource_primary,%function\nm10v_resource_primary: bx lr\n.word local_data+'+str(addend)+'\n.global m10v_resource_secondary\n.type m10v_resource_secondary,%function\nm10v_resource_secondary: bx lr\n.section .rodata\nlocal_data: .word 0x12345678\n')
                subprocess.run([compiler,'--target=armv7-none-eabi','-marm','-c',str(source),'-o',str(obj)],check=True,capture_output=True)
                if addend:
                    with self.assertRaisesRegex(ValueError,'leaves local immutable image'):link_object(obj.read_bytes(),0x540b6000,prefix='m10v_resource_')
                else:
                    code,_=link_object(obj.read_bytes(),0x540b6000,prefix='m10v_resource_')
                    target=struct.unpack_from('<I',code,4)[0]
                    self.assertEqual(struct.unpack_from('<I',code,target-0x540b6000)[0],0x12345678)

    def test_parameter_lists_focus_saved_values_without_writing_on_open(self):
        u=self.machine();model=0x55068200;controller=0x55005000
        self.call(u,'m10v_library_init',0x55001000)
        self.call(u,'m10v_camera_library_halation',0x55001000,1,8,1,7,3)
        before=dict(self.files)
        for index,expected in enumerate((8,1,7)):
            u.mem_write(model+0x1d,b'\x0a');self.focus=index
            self.call(u,'m10v_menu_confirm',controller)
            self.assertEqual(self.focus,expected)
            self.assertEqual(self.files,before)

    def test_menu_save_failure_remains_open_and_shows_error_without_native_tone_write(self):
        u = self.machine(); model = 0x55068200; controller = 0x55005000
        u.mem_write(model + 0x1d, b'\x02'); self.focus = 31; self.store_result = -1
        self.call(u, 'm10v_menu_confirm', controller)
        self.assertEqual(u.mem_read(model + 0x1d, 1), b'\x02')
        self.assertEqual(self.captions, [824]); self.assertFalse(self.native_tones)
        self.assertFalse(self.files)

    def test_menu_texture_and_timestamp_actions_commit_real_runtime_settings(self):
        u = self.machine(); model = 0x55068200; controller = 0x55005000
        for group, value in ((3, 3), (5, 2), (7, 2), (8, 3), (9, 1)):
            u.mem_write(model + 0x1d, bytes([group])); self.focus = value
            self.call(u, 'm10v_menu_confirm', controller)
        self.call(u, 'm10v_camera_library_load', 0x55001000)
        state = State.from_buffer_copy(u.mem_read(0x55001000, C.sizeof(State)))
        self.assertEqual((state.slots[1].grain, state.slots[1].soft, state.reserved), (3, 0, 0))
        self.assertEqual((state.stamp, state.format, state.corner, state.color), (2, 2, 3, 1))
        self.assertEqual(state.sequence, 5)
        self.assertEqual(self.call(u, 'm10v_library_valid', 0x55001000), 1)
        self.assertEqual([self.call(u, 'm10v_menu_name', 0, 144 + i) for i in range(32)], list(range(786, 818)))

    def test_private_utf16_resource_hooks_preserve_stock_fallback_and_locale(self):
        static_last=1006 if self.manifest['resources']['last_id']==1011 else self.manifest['resources']['last_id']
        u = self.machine(); stop = 0x550ff000; table = 0x55008000; stock_record = 0x55009000
        for language in (0, 1, 20): u.mem_write(0x55002bac + 4 * language, struct.pack('<I', table))
        for identifier in (4, 785, self.manifest['resources']['last_id']+1): u.mem_write(table + identifier * 4, struct.pack('<I', stock_record))
        calls = []
        def done(uc, address, size, data):
            if address in (0x53396700, 0x5339710c): calls.append(address); uc.reg_write(UC_ARM_REG_PC, stop)
        u.hook_add(UC_HOOK_CODE, done)
        for language in (0, 1, 20):
            for identifier in (4, 785, 786, 817, 859, 936, static_last,self.manifest['resources']['last_id']+1):
                expected = (stock_record if identifier < 786 or identifier>static_last else self.manifest['resources']['descriptors'][identifier - 786])
                for symbol, continuation in (('m10v_resource_primary', 0x53396700), ('m10v_resource_secondary', 0x5339710c)):
                    u.reg_write(UC_ARM_REG_R7, identifier); u.reg_write(UC_ARM_REG_R9, language)
                    u.reg_write(UC_ARM_REG_R0, language); u.reg_write(UC_ARM_REG_R11, 0x550fe080)
                    u.emu_start(self.manifest['symbols'][symbol], stop, count=1000)
                    self.assertEqual(calls[-1], continuation)
                    self.assertEqual(u.reg_read(UC_ARM_REG_R7 if continuation == 0x53396700 else UC_ARM_REG_R3), expected)
                    if continuation == 0x5339710c: self.assertEqual(u.reg_read(UC_ARM_REG_R0), language)
                    else: self.assertEqual(u.reg_read(UC_ARM_REG_R0), 0x550fe080 - 0xb0)

    def test_independent_settings_resource_getters_include_last_caption_and_exclude_aspect(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.manifest=build(Path(tmp),sd_library=True)
            self.code=(Path(tmp)/'m10v-library-arm.bin').read_bytes()
        self.assertEqual(self.manifest['resources']['last_id'],1110)
        self.assertEqual(len(self.manifest['resources']['descriptors']),1110-786+1)
        self.test_private_utf16_resource_hooks_preserve_stock_fallback_and_locale()

    def test_v2_journal_migrates_to_v3_and_keeps_old_bytes_on_failed_save(self):
        u=self.machine();old=bytearray(64)
        struct.pack_into('<IHHI',old,0,0x5630314d,2,64,17)
        for i in range(5):struct.pack_into('<H6B',old,12+i*8,65-i,2,1,8,1,7,3)
        old[52:56]=bytes([2,3,2,1]);struct.pack_into('<I',old,60,zlib.crc32(old[:60]))
        self.files['M10V2B.bin']=bytes(old)
        self.assertEqual(self.call(u,'m10v_camera_library_load',0x55001000),2)
        s=State.from_buffer_copy(u.mem_read(0x55001000,C.sizeof(State)))
        self.assertEqual((s.version,s.size,s.sequence),(4,104,17))
        self.assertEqual([v.film for v in s.slots],[65,64,63,62,61])
        self.assertEqual(list(s.effects[0])[:5],[1,0,0,4,0])
        self.store_result=-1
        self.assertEqual(self.call(u,'m10v_camera_library_select',0x55001000,0,66),-2)
        self.assertEqual(self.files['M10V2B.bin'],bytes(old))
        self.assertEqual(bytes(u.mem_read(0x55001000,C.sizeof(State))),bytes(s))

    def test_experimental_texture_journal_migrates_old_halation_and_preserves_leak(self):
        u=self.machine();addr=0x55001000;self.call(u,'m10v_library_init',addr)
        old=bytearray(u.mem_read(addr,C.sizeof(State)))
        struct.pack_into('<H6B',old,12,33,2,1,8,8,0,0)
        struct.pack_into('<H',old,4,3);old[57]=7;struct.pack_into('<I',old,100,zlib.crc32(old[:100]))
        self.files['M10V3B.bin']=bytes(old)
        self.assertEqual(self.call(u,'m10v_camera_library_load',addr),2)
        s=State.from_buffer_copy(u.mem_read(addr,C.sizeof(State)))
        self.assertEqual(s.slots[0].halo_gain,0);self.assertEqual(s.effects[0][1],7)
        self.assertEqual(self.files['M10V3B.bin'],bytes(old))

    def test_published_energy_journal_preserves_controls_in_new_texture_namespace(self):
        u=self.machine();old=bytearray(64)
        struct.pack_into('<IHHI',old,0,0x5630314d,2,64,17)
        for i in range(5):struct.pack_into('<H6B',old,12+i*8,33,2,1,8,1,7,2)
        struct.pack_into('<I',old,60,zlib.crc32(old[:60]))
        self.files['M10V3B.bin']=bytes(old)
        self.assertEqual(self.call(u,'m10v_camera_library_load',0x55001000),2)
        s=State.from_buffer_copy(u.mem_read(0x55001000,C.sizeof(State)))
        self.assertEqual((s.slots[0].halo_gain,s.slots[0].halo_spread,s.slots[0].halo_threshold),(8,1,7))
        self.assertEqual(self.call(u,'m10v_camera_library_stamp',0x55001000,1,0,0,0),0)
        self.assertEqual(self.files['M10V3B.bin'],bytes(old));self.assertIn('M10V5A.bin',self.files)

    def test_old_journals_ignore_compiled_red_ei_defaults(self):
        initial=bytearray.fromhex(self.manifest['initial_state_hex'])
        struct.pack_into('<H',initial,12,68);initial[61]=2
        struct.pack_into('<I',initial,100,zlib.crc32(initial[:100]))
        with tempfile.TemporaryDirectory() as folder:
            self.manifest=build(folder,initial_state_hex=initial.hex())
            self.code=(Path(folder)/'m10v-library-arm.bin').read_bytes()
        for size,name,version in [(44,'M10V1.bin',1),(64,'M10V3B.bin',2)]:
            u=self.machine();addr=0x55001000
            self.assertEqual(self.call(u,'m10v_camera_library_load',addr),1)
            self.assertEqual(State.from_buffer_copy(u.mem_read(addr,104)).effects[0][5],2)
            old=bytearray(size);struct.pack_into('<IHHI',old,0,0x5630314d,version,size,17)
            for i in range(5):
                if size==44:struct.pack_into('<HBB',old,12+i*4,33,1,0)
                else:struct.pack_into('<H6B',old,12+i*8,33,1,0,3,3,5,2)
            struct.pack_into('<I',old,size-4,zlib.crc32(old[:-4]))
            self.files[name]=bytes(old)
            self.assertGreaterEqual(self.call(u,'m10v_camera_library_load',addr),2)
            migrated=State.from_buffer_copy(u.mem_read(addr,104))
            self.assertEqual(migrated.slots[0].film,33)
            self.assertEqual(list(migrated.effects[0]),[1,0,0,4,0,0,0,0])
            self.assertEqual(self.call(u,'m10v_library_valid',addr),1)

    def test_published_texture_v3_preserves_effects_and_energy_then_writes_v5(self):
        u=self.machine();state=0x55001000
        self.call(u,'m10v_library_init',state)
        old=bytearray(u.mem_read(state,C.sizeof(State)))
        struct.pack_into('<H',old,4,3)
        struct.pack_into('<H6B',old,12,33,2,1,8,1,7,2)
        old[56:61]=bytes([2,8,5,7,1])
        struct.pack_into('<I',old,100,zlib.crc32(old[:100]))
        self.files={'M10V4B.bin':bytes(old)}
        self.assertGreaterEqual(self.call(u,'m10v_camera_library_load',state),0)
        migrated=State.from_buffer_copy(u.mem_read(state,C.sizeof(State)))
        self.assertEqual(migrated.version,4)
        self.assertEqual((migrated.slots[0].halo_gain,migrated.slots[0].halo_spread,migrated.slots[0].halo_threshold),(8,1,7))
        self.assertEqual(list(migrated.effects[0]),[2,8,5,7,1,0,0,0])
        self.assertEqual(self.call(u,'m10v_camera_library_stamp',state,1,0,0,0),0)
        self.assertEqual(self.files['M10V4B.bin'],bytes(old))
        self.assertTrue(any(name.startswith('M10V5') for name in self.files))

    def test_red_exposure_menu_round_trip_and_common_reset_preserves_ei(self):
        u=self.machine();state=0x55001000;model=0x55068200;controller=0x55005000
        self.call(u,'m10v_library_init',state)
        self.assertEqual(self.call(u,'m10v_camera_library_select',state,1,68),0)
        u.mem_write(model+0x1d,b'\x01');self.focus=4
        self.call(u,'m10v_menu_confirm',controller)
        self.assertEqual(u.mem_read(model+0x1d,1),b'\x15')
        for index in range(3):
            u.mem_write(model+0x1d,b'\x15');self.focus=index
            self.assertEqual(self.call(u,'m10v_menu_index',model,index),341+index)
            self.assertEqual(self.call(u,'m10v_menu_name',0,341+index),934+index)
            self.call(u,'m10v_menu_confirm',controller)
            self.assertEqual(u.mem_read(model+0x1d,1),b'\x01')
            self.call(u,'m10v_camera_library_load',state)
            s=State.from_buffer_copy(u.mem_read(state,C.sizeof(State)))
            self.assertEqual(s.effects[1][5],index)
        self.call(u,'m10v_camera_library_effects',state,1,5,0)
        self.assertEqual(State.from_buffer_copy(u.mem_read(state,C.sizeof(State))).effects[1][5],2)

    def test_all_films_have_common_menu_and_stock_specific_entries(self):
        u=self.machine();state=0x55001000;model=0x55068200
        self.call(u,'m10v_library_init',state)
        for film in range(1,79):
            self.assertEqual(self.call(u,'m10v_camera_library_select',state,1,film),0)
            u.mem_write(model+0x1d,b'\x01')
            self.assertEqual(self.call(u,'m10v_menu_count',model),5 if film in (33,67,68) else 4)
            self.assertEqual(self.call(u,'m10v_menu_index',model,4),214 if film==33 else 339 if film==67 else 340 if film==68 else 0)
        u.mem_write(model+0x1d,b'\x03')
        self.assertEqual(self.call(u,'m10v_menu_count',model),4)
        self.assertEqual(self.call(u,'m10v_menu_index',model,4),0)

    def test_retired_texture_menu_routes_cannot_write_settings(self):
        u=self.machine();state=0x55001000;model=0x55068200;controller=0x55005000
        self.call(u,'m10v_library_init',state)
        self.assertEqual(self.call(u,'m10v_camera_library_select',state,1,66),0)
        before=dict(self.files)
        for group,index in [(16,2),(17,8),(18,1),(19,7),(20,1)]:
            u.mem_write(model+0x1d,bytes([group]));self.focus=index
            self.assertEqual(self.call(u,'m10v_menu_count',model),0)
            self.assertEqual(self.call(u,'m10v_menu_confirm',controller),0)
            self.assertEqual(self.files,before)
        self.call(u,'m10v_camera_library_load',state)
        s=State.from_buffer_copy(u.mem_read(state,C.sizeof(State)))
        self.assertEqual(s.effects[1][0],0);self.assertEqual(s.effects[1][1],0)

    def test_5207_arm_ignores_legacy_texture_bytes_and_preserves_padding(self):
        u=self.machine();state=0x55001000;self.call(u,'m10v_library_init',state)
        self.call(u,'m10v_camera_library_select',state,0,66)
        # Historical texture bytes are synthesized directly; retired setters reject them.
        old=bytearray(u.mem_read(state,C.sizeof(State)));old[56:61]=bytes([2,8,4,7,1]);old[14]=3
        struct.pack_into('<I',old,100,zlib.crc32(old[:100]));u.mem_write(state,bytes(old))
        width,height,stride=32,16,40;size=stride*height
        y=bytes((i*37+19)%256 for i in range(size));uv=bytes((i*13+97)%256 for i in range(size))
        u.mem_write(0x55010000,y);u.mem_write(0x55020000,uv)
        u.mem_write(0x55002000,struct.pack('<7I',0x55010000,0x55020000,size,size,width,height,stride))
        self.assertEqual(self.call(u,'m10v_library_render',0x55002000,state,0,0,5207,0,0),0)
        s=State.from_buffer_copy(u.mem_read(state,C.sizeof(State)))
        hy=(C.c_uint8*size).from_buffer_copy(y);hc=(C.c_uint8*size).from_buffer_copy(uv);im=Image(hy,hc,size,size,width,height,stride)
        self.assertEqual(host_tests.NativeFilmLibraryTests.lib.m10v_library_render(C.byref(im),C.byref(s),0,None,5207,None,0),0)
        self.assertEqual(bytes(u.mem_read(0x55010000,size)),bytes(hy));self.assertEqual(bytes(u.mem_read(0x55020000,size)),bytes(hc))
        for row in range(height):self.assertEqual(bytes(hy[row*stride+width:(row+1)*stride]),y[row*stride+width:(row+1)*stride])

    def test_capture_chain_restores_registers_flags_and_unaligned_caller_stack(self):
        with self.runtime_profile():self.assert_default_capture_chain_preserves_abi()

    def assert_default_capture_chain_preserves_abi(self):
        registers = (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_R4,
                     UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8, UC_ARM_REG_R9,
                     UC_ARM_REG_R10, UC_ARM_REG_R11, UC_ARM_REG_R12)
        for sp in (0x550fe000, 0x550fe004):
            u = self.machine(); u.mem_map(0x536ab000, 4096)
            values = [0x55000a00 + 4 * i for i in range(13)]; cpsr = 0x68050013; seen = []
            def intercept(uc, address, size, data):
                if address == self.manifest['symbols']['m10v_capture_library']:
                    self.assertEqual(uc.reg_read(UC_ARM_REG_R0), values[4])
                    self.assertEqual(uc.reg_read(UC_ARM_REG_SP) & 7, 0)
                    for register in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_R12): uc.reg_write(register, 0xdeadbeef)
                    uc.reg_write(UC_ARM_REG_CPSR, 0x980a0013); uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
                elif address == 0x536abd28:
                    seen.append(address); self.assertEqual([uc.reg_read(r) for r in registers], values)
                    self.assertEqual(uc.reg_read(UC_ARM_REG_SP), sp)
                    self.assertEqual(uc.reg_read(UC_ARM_REG_CPSR) & 0xff0f0000, cpsr & 0xff0f0000)
                    uc.reg_write(UC_ARM_REG_R0, 99); uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
            u.hook_add(UC_HOOK_CODE, intercept)
            for register, value in zip(registers, values): u.reg_write(register, value)
            u.reg_write(UC_ARM_REG_CPSR, cpsr); u.reg_write(UC_ARM_REG_SP, sp); u.reg_write(UC_ARM_REG_LR, 0x550ff000)
            u.emu_start(self.manifest['symbols']['m10v_chain_capture'], 0x550ff000, count=1000)
            self.assertEqual(seen, [0x536abd28]); self.assertEqual(u.reg_read(UC_ARM_REG_R0), 99)
