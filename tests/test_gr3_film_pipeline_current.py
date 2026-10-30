"""Current ten-slot ABI: real Still Make to encoder admission, no completion stub.

The ISP hardware and filesystem are not emulated. The tests deliberately fail
on pixel/cache/allocation access in an authenticated native-only capture.
"""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import zlib
import io,zipfile
from unicorn import UC_HOOK_CODE
from unicorn import arm_const as A
from tests.test_gr3_isp_base import StockISP, ROOT


class CurrentFilmPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        official = ROOT / 'builds/gr3-extension-validation/official-rtos.bin'
        cls.rom = official.read_bytes()
        assert hashlib.sha256(cls.rom).hexdigest() == '8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67'
        delivery = os.environ.get('M10V_CURRENT_PIPELINE_CANDIDATE')
        if delivery:
            folder = Path(delivery)
            cls.manifest = json.loads((folder / 'M10V-runtime-manifest.json').read_text())
            receipt = json.loads((folder / 'M10V-build-receipt.json').read_text())
            binary = folder / receipt['filename']
            assert hashlib.sha256(binary.read_bytes()).hexdigest() == receipt['candidate_sha256']
            js = "import{readFileSync}from'node:fs';import{decodeFrameMap}from'./node/gr3-frames.mjs';const b=readFileSync(process.argv[1]),d=decodeFrameMap(b,b.readUInt32LE(b.length-8)).decoded;process.stdout.write(d.subarray(0x10870,0x10870+d.readUInt32LE(0x1086c)));"
            cls.image = subprocess.check_output(['node', '--input-type=module', '-e', js, str(binary)], cwd=ROOT)
        else:
            cls.temp = tempfile.TemporaryDirectory()
            cls.addClassCleanup(cls.temp.cleanup)
            folder = Path(cls.temp.name)
            subprocess.run(['node', 'scripts/export_gr3_m10v_native.mjs', str(folder)],
                cwd=ROOT, check=True, capture_output=True)
            cls.manifest = json.loads((folder / 'M10V-runtime-manifest.json').read_text())
            js = "import{readFileSync}from'node:fs';import{decodeFrameMap}from'./node/gr3-frames.mjs';const b=readFileSync(process.argv[1]),d=decodeFrameMap(b,b.readUInt32LE(b.length-8)).decoded;process.stdout.write(d.subarray(0x10870,0x10870+d.readUInt32LE(0x1086c)));"
            cls.image = subprocess.check_output(['node', '--input-type=module', '-e', js, str(folder / 'fwdc239b.bin')], cwd=ROOT)
        offset = cls.manifest['base'] - 0x53000000
        runtime = cls.image[offset:offset + cls.manifest['code_bytes']]
        assert hashlib.sha256(runtime).hexdigest() == cls.manifest['code_sha256']

    def call(self, e, name, *args):
        e.call(self.manifest['symbols'][name], *args)
        return e.u.reg_read(A.UC_ARM_REG_R0)

    def fixture(self, film=66, slot=0, stage=1):
        e = StockISP(self.image)
        recipe = e.alloc(self.manifest['capture_lifecycle']['owner']['storage']['extended_recipe_bytes'])
        e.w32(recipe, 0x53d0fc90)
        e.w32(recipe + 0x4778, 0x31545653)
        obj = e.cursor
        e.make(25 + slot, stage)
        frame = obj + 0x1400
        si = int.from_bytes(e.u.mem_read(frame + 0x82d0, 4), 'little')
        # Stage1 uses the embedded sub-shot; encoder identity remains base SI.
        e.u.mem_write(si + 0x77c, bytes([25 + slot]))
        request = e.alloc(0x40)
        e.w32(recipe + 0x44c8, si)
        e.w32(recipe + 0x5c, request)
        # Run the original setup writes, not a guessed context offset.
        e.u.reg_write(A.UC_ARM_REG_R0, recipe)
        e.u.reg_write(A.UC_ARM_REG_R4, recipe)
        e.u.emu_start(0x5350eb10, 0x5350eb38, count=100)
        state = bytearray(184)
        struct.pack_into('<IHHI', state, 0, 0x5630314d, 5, 184, 7)
        # Earlier slots are valid distinct enabled films; trailing slots empty.
        for index in range(slot + 1):
            struct.pack_into('<H6B', state, 12 + 8 * index,
                film if index == slot else 34 + index, 0, 0, 0, 3, 5, 2)
        if 79<=film<=288:state[96+slot*8+6]=21
        struct.pack_into('<I', state, 180, zlib.crc32(state[:180]))
        data = e.alloc(184)
        e.u.mem_write(data, bytes(state))
        self.assertEqual(self.call(e, 'm10v_isp_frame_recipe_snapshot', recipe, data), 1)
        return e, recipe, obj, frame, si, request, data

    def publish_owner(self, e, data):
        owner = e.alloc(self.manifest['settings_menu']['owner_bytes'])
        e.w32(0x55063910, 1)
        e.w32(0x55063914 + 0x74, owner)
        e.w32(owner + 0x213c, 0x3856504d)
        e.w32(owner + 0x2140, 2)
        e.u.mem_write(owner + 0x2144, bytes(e.u.mem_read(data, 184)))
        return owner

    def test_owner_query_matches_inline_custom_cache_allocation(self):
        e=StockISP(self.image)
        self.assertEqual(self.call(e,'m10v_settings_controller_owner_size'),self.manifest['settings_menu']['owner_bytes'])

    def test_real_task_producer_records_pool_owned_film_without_storage_or_pixels(self):
        e,recipe,obj,frame,old_si,request,data=self.fixture(66,stage=0)
        # Dedicated pool allocation includes16 owned metadata bytes. Keep the
        # stock SI contents and real setup/producer/Still/encoder entrypoints.
        si=e.alloc(0x74280)
        e.u.mem_write(si,bytes(e.u.mem_read(old_si,0x74270)))
        e.w32(recipe+0x44c8,si);e.w32(frame+0x82d0,si)
        e.u.reg_write(A.UC_ARM_REG_R0,recipe);e.u.reg_write(A.UC_ARM_REG_R4,recipe)
        e.u.emu_start(0x5350eb10,0x5350eb38,count=100)
        manager=e.alloc(0x218);e.w32(manager+0x20,0x74280);e.w32(manager+0x88,si);e.w32(0x55345328,manager)
        owner=self.publish_owner(e,data)
        e.u.mem_write(recipe+0x4a08,bytes(1796))
        self.enqueue(e,recipe,19)
        self.assertEqual(self.call(e,'m10v_isp_frame_identity_code',si),0x1000+66)
        # A subsequent selection cannot retarget this queued photo.
        e.u.mem_write(owner+0x2144,bytes(184));e.w32(owner+0x2140,8)
        self.make(e,recipe,obj,frame)
        self.assertEqual(self.call(e,'m10v_isp_frame_recipe_completed',recipe,si,25,data),1)
        self.assertEqual(self.capture(e,recipe,si,request),0)
        self.assertEqual(self.call(e,'m10v_isp_frame_identity_code',si),0x1000+66)

    def test_custom_isp_ui_cache_real_producer_freezes_target_and_native_only_capture(self):
        for stage in (0,1):
            e,recipe,obj,frame,si,request,data=self.fixture(79,stage=stage)
            owner=self.publish_owner(e,data)
            record=bytearray(12288)
            struct.pack_into('<4I',record,6688,0x5053494d,1,1572,0)
            struct.pack_into('<18h',record,6704,8192,0,0,0,8192,0,0,0,8192,512,0,0,0,512,0,0,0,512)
            struct.pack_into('<768H',record,6740,*([round(i*16383/255) for i in range(256)]*3))
            reads=[]
            def storage(u,at,n,d):
                if at!=self.manifest['symbols']['m10v_sd_camera_custom_record']:return
                reads.append(at);u.mem_write(u.reg_read(A.UC_ARM_REG_R2),bytes(record))
                u.reg_write(A.UC_ARM_REG_R0,1);u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
            h=e.u.hook_add(UC_HOOK_CODE,storage)
            self.assertEqual(self.call(e,'m10v_camera_library_mutation_begin'),1)
            self.call(e,'m10v_camera_library_mutation_end',data)
            e.u.hook_del(h);self.assertEqual(len(reads),1)
            e.u.mem_write(recipe+0x4a08,bytes(1796))
            self.enqueue(e,recipe,19)
            # The owner is now a newer UI selection. This shot must own a copy.
            e.u.mem_write(owner+0x2144,bytes(184));e.w32(owner+0x2140,8)
            self.make(e,recipe,obj,frame)
            self.assertEqual(self.call(e,'m10v_isp_frame_recipe_completed',recipe,si,25,data),1)
            self.assertEqual(self.capture(e,recipe,si,request),0)

    def test_custom_offline_fit_actual_live_callback_and_still_fields_match_report(self):
        js="""import{exportSdFilms}from'./node/gr3-sd-film-export.mjs';
const lines=['LUT_3D_SIZE 2'];for(let b=0;b<2;b++)for(let g=0;g<2;g++)for(let r=0;r<2;r++)lines.push([.98*r+.02*g,.97*g+.03*r,.94*b+.06*g].join(' '));
const v=await exportSdFilms({ids:[],customFilms:[{name:'Warm',filename:'warm.cube',base64:Buffer.from(lines.join('\\n')).toString('base64')}]});process.stdout.write(v.zip);"""
        blob=subprocess.check_output(['node','--input-type=module','-e',js],cwd=ROOT)
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            record=z.read('SD/M10V/FILMS.M10')[4096:16384]
            report=json.loads(z.read('manifest.json'))['custom_lut_assessment']['profiles'][0]['quality']['provenance']['native_frame']
        e,recipe,obj,frame,si,request,data=self.fixture(79,stage=0)
        self.publish_owner(e,data)
        def storage(u,at,n,d):
            if at!=self.manifest['symbols']['m10v_sd_camera_custom_record']:return
            u.mem_write(u.reg_read(A.UC_ARM_REG_R2),record);u.reg_write(A.UC_ARM_REG_R0,1);u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
        h=e.u.hook_add(UC_HOOK_CODE,storage)
        self.call(e,'m10v_camera_library_mutation_begin');self.call(e,'m10v_camera_library_mutation_end',data);e.u.hook_del(h)
        e.u.mem_write(recipe+0x4a08,bytes(1796));self.enqueue(e,recipe,19);self.make(e,recipe,obj,frame)
        def fields(at):
            def signed(v,bits):return ((v&((1<<bits)-1))^(1<<(bits-1)))-(1<<(bits-1))
            return [[signed(v,bits) for v in struct.unpack('<9H',e.u.mem_read(at+offset,18))] for offset,bits in ((0x140,12),(0x12a0,9))]
        expected=[report['cca_signed12'],report['csp_signed9']]
        self.assertEqual(fields(frame),expected)
        # Stage1-shaped metadata exercises original Live Make without the
        # sensor-specific stage0 AWB/black-level calibration boundary.
        live_obj=e.cursor;e.make(25,stage=1,live=True,actual_live=True);live_frame=live_obj+0x1400
        callback=int.from_bytes(e.u.mem_read(0x53dbd954,4),'little')
        e.call(callback,live_obj,live_frame)
        self.assertEqual(fields(live_frame),expected)
        self.assertEqual(bytes(e.u.mem_read(live_frame+0x4888,2048)),bytes(e.u.mem_read(frame+0x4888,2048)))
        self.assertEqual(self.call(e,'m10v_isp_frame_recipe_completed',recipe,si,25,data),1)
        self.assertEqual(self.capture(e,recipe,si,request),0)

    def enqueue(self, e, recipe, kind):
        # Original task producer constructs both the packet and its recipe
        # metadata. OS mode selection/setup and message transport are boundaries.
        owner = e.alloc(0xb00)
        plan = e.alloc(0x300)
        e.w32(recipe + 0x1c, plan)
        e.u.mem_write(plan + 0x204, struct.pack('<H', kind))
        e.w32(owner + 0x9b4 + kind * 4, 0x60030000)
        seen = []
        def services(u, at, n, _):
            if at in (0x5351e888, 0x5350e624):
                u.reg_write(A.UC_ARM_REG_R0, 0)
            elif at == 0x536abd28:
                msg = u.reg_read(A.UC_ARM_REG_R1)
                meta = int.from_bytes(u.mem_read(msg + 12, 4), 'little')
                seen.append((msg, meta, int.from_bytes(u.mem_read(meta + 20, 4), 'little')))
                u.reg_write(A.UC_ARM_REG_R0, 0)
            elif at == self.manifest['symbols']['m10v_camera_library_load']:
                raise AssertionError('task submission must not enter storage')
            else:
                return
            u.reg_write(A.UC_ARM_REG_PC, u.reg_read(A.UC_ARM_REG_LR))
        hook = e.u.hook_add(UC_HOOK_CODE, services)
        try:
            e.call(0x5351ea9c, owner, recipe)
        finally:
            e.u.hook_del(hook)
        self.assertEqual(seen, [(recipe + 0x3b0 + kind * 24, recipe + 0x5f0 + kind * 32, recipe)])

    def test_device_task_order_freezes_before_develop_without_buffer_retirement(self):
        # Device log: kind19/0/16/1/8/9/2/4 precede JPEG kind6. The former
        # 5351ae44 hook is in buffer retirement, which has not occurred here.
        for film in (62, 299):
            for stage in (0, 1):
                with self.subTest(film=film, stage=stage):
                    e, recipe, obj, frame, si, request, data = self.fixture(film, stage=stage)
                    e.u.mem_write(recipe + 0x4a08, bytes(1796))
                    owner = self.publish_owner(e, data)
                    ui = e.alloc(0x200)
                    e.w32(0x55063ed0, 1)
                    e.w32(0x55063f34, ui)
                    e.u.mem_write(ui + 0x1c2, bytes([34]))  # newer UI is not this shot
                    for kind in (19, 0, 16, 1, 8, 9, 2, 4):
                        self.enqueue(e, recipe, kind)
                        self.assertEqual(self.call(e, 'm10v_isp_frame_recipe_state', recipe, data), 1)
                    self.assertEqual(int.from_bytes(e.u.mem_read(recipe + 0x4a08 + 22, 2), 'little'), 25)
                    # Changing the owner's configuration cannot retarget queued work.
                    newer = bytearray(e.u.mem_read(data, 184))
                    struct.pack_into('<I', newer, 8, 8)
                    struct.pack_into('<I', newer, 180, zlib.crc32(newer[:180]))
                    e.u.mem_write(owner + 0x2144, bytes(newer))
                    e.w32(owner + 0x2140, 4)
                    self.make(e, recipe, obj, frame)
                    self.assertEqual(self.call(e, 'm10v_isp_frame_recipe_completed', recipe, si, 25, data), 1)
                    self.assertEqual(self.capture(e, recipe, si, request), 0)

    def make(self, e, recipe, obj, frame):
        for reg, value in ((0, obj), (1, frame), (3, 0x536dd8f0), (6, recipe + 0x96c)):
            e.u.reg_write(getattr(A, 'UC_ARM_REG_R' + str(reg)), value)
        e.u.reg_write(A.UC_ARM_REG_SP, 0x5effff00)
        e.u.reg_write(A.UC_ARM_REG_LR, 0x53501d6c)
        e.u.emu_start(0x53501d68, 0x53501d6c, count=5000000)
        self.assertEqual(e.u.reg_read(A.UC_ARM_REG_PC), 0x53501d6c)

    def capture(self, e, recipe, si, request, advanced=None):
        context = recipe + 0x9b8
        for offset, value in ((0, 0x53d0fbe0), (0x30, recipe + 0x1a8),
                (0x34, si), (0x38, request), (0x3c, recipe + 0xb0),
                (0x40, recipe + 0xd0), (0x44, recipe + 0xf0),
                (0x48, recipe + 0x110), (0x4c, recipe + 0x130)):
            e.w32(context + offset, value)
        e.w32(request, 0x53d0fe60)
        e.u.mem_write(request + 12, b'\1\1')
        e.u.mem_write(recipe + 0x140, b'\1')
        e.w32(recipe + 0x60, 0x70000000)
        dimensions = e.alloc(4)
        e.u.mem_write(dimensions, struct.pack('<HH', 6112, 4064))
        e.w32(recipe + 0x230, dimensions)
        # 24MP image planes intentionally unmapped: native-only must not access them.
        e.u.mem_write(recipe + 0xb0, struct.pack('<4I8H', 1, 0x65000000, 0x68000000, 0, 6000, 4000, 6000, 4000, 0, 0, 2, 0))
        e.u.mem_write(recipe + 0x110, struct.pack('<4I8H', 1, 0x6b000000, 0x6b100000, 0, 720, 480, 720, 480, 0, 0, 2, 0))
        if advanced is not None:
            # Small real owned JPEG/thumbnail planes; RAW stays unmapped.
            w,h,stride=4,4,6
            advanced['planes']=[]
            groups=[(1,0x65000000,0x68000000,recipe+0xb0),
                    (advanced['format'],0x6c000000,0x6c100000,recipe+0xd0)]
            groups.append((advanced['format'],0x6c000000 if advanced['alias'] else 0x6d000000,
                0x6c100000 if advanced['alias'] else 0x6d100000,recipe+0xf0))
            for fmt,yp,cp,descriptor in groups:
                e.u.mem_write(descriptor,struct.pack('<4I8H',fmt,yp,cp,0,w,h,stride,h,0,0,2,0))
                if any(yp==v[0] for v in advanced['planes']):continue
                e.u.mem_map(yp,4096);e.u.mem_map(cp,4096)
                yy=bytes((30+row*29+x*x*17)%256 if x<w else 222 for row in range(h) for x in range(stride))
                ch=h//2 if fmt==2 else h
                cc=bytes((77+row*37+x*19)%256 if x<w else 223 for row in range(ch) for x in range(stride))
                e.u.mem_write(yp,yy);e.u.mem_write(cp,cc)
                advanced['planes'].append((yp,cp,yy,cc,ch))
            e.services.add(0x5383c8a8)
        forbidden = {0x536af2a8, 0x5383c8a8, 0x53828014,
            self.manifest['symbols']['m10v_camera_library_load']}
        def boundary(u, at, n, _):
            if advanced is not None and at in (0x536af2a8,0x5383c8a8):
                if at==0x536af2a8 and advanced.get('fail_alloc'):
                    u.reg_write(A.UC_ARM_REG_R0,0);u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
                return
            if at in forbidden:
                raise AssertionError(f'native-only capture reached pixel/allocation/filesystem boundary {at:#x}')
            if self.manifest['debug_mode'] and at == self.manifest['symbols']['m10v_debug_batch']:
                # SD transport is external. Timing and control still run real code.
                u.reg_write(A.UC_ARM_REG_R0, 0)
                u.reg_write(A.UC_ARM_REG_PC, u.reg_read(A.UC_ARM_REG_LR))
        e.u.hook_add(UC_HOOK_CODE, boundary)
        return self.call(e, 'm10v_capture_library', context)

    def test_5207_and_5219_actual_still_completion_reaches_24mp_zero_pixel_fast_path(self):
        for film in (62, 66):
            for slot in (0, 4, 9):
                with self.subTest(film=film, slot=slot):
                    e, recipe, obj, frame, si, request, data = self.fixture(film, slot)
                    self.make(e, recipe, obj, frame)
                    self.assertEqual(self.call(e, 'm10v_isp_frame_recipe_completed', recipe, si, 25 + slot, data), 1)
                    self.assertEqual(self.capture(e, recipe, si, request), 0)

    def test_seven_new_looks_real_task_producer_to_unmapped_24mp_encoder(self):
        for film in (294,309,310,311):
            for stage in (0,1):
                with self.subTest(film=film,stage=stage):
                    e,recipe,obj,frame,si,request,data=self.fixture(film,stage=stage)
                    # Discard fixture snapshot; only the actual task producer
                    # can publish this shot before the original Still Make.
                    e.u.mem_write(recipe+0x4a08,bytes(1796))
                    self.publish_owner(e,data)
                    self.enqueue(e,recipe,19)
                    self.make(e,recipe,obj,frame)
                    self.assertEqual(self.call(e,'m10v_isp_frame_recipe_completed',recipe,si,25,data),1)
                    self.assertEqual(self.capture(e,recipe,si,request),0)

    def test_c41_looks_real_task_producer_to_unmapped_24mp_encoder(self):
        for film in (312,313):
            for stage in (0,1):
                with self.subTest(film=film,stage=stage):
                    e,recipe,obj,frame,si,request,data=self.fixture(film,stage=stage)
                    # Discard fixture snapshot; only the actual task producer
                    # can publish this shot before the original Still Make.
                    e.u.mem_write(recipe+0x4a08,bytes(1796))
                    self.publish_owner(e,data)
                    self.enqueue(e,recipe,19)
                    self.make(e,recipe,obj,frame)
                    self.assertEqual(self.call(e,'m10v_isp_frame_recipe_completed',recipe,si,25,data),1)
                    self.assertEqual(self.capture(e,recipe,si,request),0)

    def test_extra_films_real_task_producer_to_unmapped_24mp_encoder(self):
        for film in (314,315,316,317):
            for stage in (0,1):
                with self.subTest(film=film,stage=stage):
                    e,recipe,obj,frame,si,request,data=self.fixture(film,stage=stage)
                    # Discard fixture snapshot; only the actual task producer
                    # can publish this shot before the original Still Make.
                    e.u.mem_write(recipe+0x4a08,bytes(1796))
                    self.publish_owner(e,data)
                    self.enqueue(e,recipe,19)
                    self.make(e,recipe,obj,frame)
                    self.assertEqual(self.call(e,'m10v_isp_frame_recipe_completed',recipe,si,25,data),1)
                    self.assertEqual(self.capture(e,recipe,si,request),0)

    def test_repeated_still_make_does_not_accumulate_color_banks(self):
        for film in (62, 66):
            e, recipe, obj, frame, *_ = self.fixture(film)
            self.make(e, recipe, obj, frame)
            first = bytes(e.u.mem_read(frame, 0x9000))
            for _ in range(3):
                self.make(e, recipe, obj, frame)
                self.assertEqual(bytes(e.u.mem_read(frame, 0x9000)), first)

    def test_every_native_task_kind_freezes_once_without_storage(self):
        for kind in range(24):
            with self.subTest(kind=kind):
                e, recipe, obj, frame, si, request, data = self.fixture(62)
                e.u.mem_write(recipe + 0x4a08, bytes(1796))
                self.publish_owner(e, data)
                self.enqueue(e, recipe, kind)
                self.assertEqual(self.call(e, 'm10v_isp_frame_recipe_state', recipe, data), 1)

    def test_unpublished_or_busy_cache_never_loads_storage_in_scheduler(self):
        for version in (0, 1):
            with self.subTest(version=version):
                e, recipe, obj, frame, si, request, data = self.fixture(62)
                e.u.mem_write(recipe + 0x4a08, bytes(1796))
                owner = self.publish_owner(e, data)
                e.w32(owner + 0x2140, version)
                self.enqueue(e, recipe, 19)
                self.assertEqual(self.call(e, 'm10v_isp_frame_recipe_state', recipe, data), 0)

    def test_durable_ui_load_publishes_owner_used_by_actual_task_submission(self):
        e, recipe, obj, frame, si, request, data = self.fixture(62)
        e.u.mem_write(recipe + 0x4a08, bytes(1796))
        owner = e.alloc(self.manifest['settings_menu']['owner_bytes'])
        e.w32(0x55063910, 1)
        e.w32(0x55063988, owner)
        self.call(e, 'm10v_camera_library_preview_init', owner)
        manager, app, fs = e.alloc(12), e.alloc(4), e.alloc(0x24)
        e.w32(manager + 8, app)
        e.w32(app, fs)
        e.u.mem_write(fs + 0x20, b'\1')
        saved = bytes(e.u.mem_read(data, 184))
        reads = []
        def storage(u, at, n, _):
            if at == 0x53828014:
                u.reg_write(A.UC_ARM_REG_R0, manager)
            elif at == 0x53825648:
                self.assertEqual(u.reg_read(A.UC_ARM_REG_R2), 184)
                reads.append(at)
                u.mem_write(u.reg_read(A.UC_ARM_REG_R3), saved)
                u.reg_write(A.UC_ARM_REG_R0, 1)
            else:
                return
            u.reg_write(A.UC_ARM_REG_PC, u.reg_read(A.UC_ARM_REG_LR))
        hook = e.u.hook_add(UC_HOOK_CODE, storage)
        self.assertEqual(self.call(e, 'm10v_camera_library_load', data), 0)
        e.u.hook_del(hook)
        self.assertEqual(len(reads), 2)
        self.enqueue(e, recipe, 19)
        self.make(e, recipe, obj, frame)
        self.assertEqual(self.call(e, 'm10v_isp_frame_recipe_completed', recipe, si, 25, data), 1)
        self.assertEqual(self.capture(e, recipe, si, request), 0)

    def test_submission_wrapper_preserves_stock_entry_and_fp_abi(self):
        e, recipe, *_ = self.fixture(62)
        registers = [0x12340000 + i for i in range(13)]
        registers[1] = recipe
        helper = self.manifest['symbols']['m10v_isp_frame_recipe_producer']
        def adversarial_helper(u, at, n, _):
            if at != helper:
                return
            for i in range(13):
                u.reg_write(getattr(A, 'UC_ARM_REG_R' + str(i)), 0xdead0000 + i)
            for i in range(32):
                u.reg_write(getattr(A, 'UC_ARM_REG_D' + str(i)), 0xdeadbeef00000000 + i)
            u.reg_write(A.UC_ARM_REG_FPSCR, 0x00400000)
            u.reg_write(A.UC_ARM_REG_CPSR, 0x60000013)
            u.reg_write(A.UC_ARM_REG_PC, u.reg_read(A.UC_ARM_REG_LR))
        e.u.hook_add(UC_HOOK_CODE, adversarial_helper)
        for i, value in enumerate(registers):
            e.u.reg_write(getattr(A, 'UC_ARM_REG_R' + str(i)), value)
        fpregs = [0xabcdef1200000000 + i for i in range(32)]
        for i, value in enumerate(fpregs):
            e.u.reg_write(getattr(A, 'UC_ARM_REG_D' + str(i)), value)
        e.u.reg_write(A.UC_ARM_REG_FPSCR, 0x00800000)
        e.u.reg_write(A.UC_ARM_REG_CPSR, 0xa0000013)
        e.u.reg_write(A.UC_ARM_REG_SP, 0x5effff00)
        e.u.reg_write(A.UC_ARM_REG_LR, 0x53123400)
        e.u.emu_start(0x5351ea9c, 0x5351eaa0, count=100000)
        registers[12] = 0x5effff00  # displaced stock mov ip,sp
        self.assertEqual([e.u.reg_read(getattr(A, 'UC_ARM_REG_R' + str(i))) for i in range(13)], registers)
        self.assertEqual(e.u.reg_read(A.UC_ARM_REG_SP), 0x5effff00)
        self.assertEqual(e.u.reg_read(A.UC_ARM_REG_LR), 0x53123400)
        self.assertEqual(e.u.reg_read(A.UC_ARM_REG_CPSR) & 0xf0000000, 0xa0000000)
        self.assertEqual([e.u.reg_read(getattr(A, 'UC_ARM_REG_D' + str(i))) for i in range(32)], fpregs)
        self.assertEqual(e.u.reg_read(A.UC_ARM_REG_FPSCR), 0x00800000)

    def test_final_bin_retires_old_hook_and_independent_auditor_rejects_wrong_recipe(self):
        old = 0x5351ae44 - 0x53000000
        self.assertEqual(self.image[old:old + 4], self.rom[old:old + 4])
        snapshot = self.manifest['capture_lifecycle']['snapshot']
        self.assertEqual(snapshot['producer_sites'], [0x5351ea9c])
        self.assertEqual(snapshot['filesystem_calls'], 0)
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            (folder / 'manifest.json').write_text(json.dumps(self.manifest))
            at = self.manifest['base'] - 0x53000000
            (folder / 'runtime.bin').write_bytes(self.image[at:at + self.manifest['code_bytes']])
            js = """import{readFileSync}from'node:fs';import{createHash}from'node:crypto';
import assert from'node:assert/strict';import{buildNativeLibrary}from'./node/gr3-m10v-native-build.mjs';
const folder=process.argv[1],m=JSON.parse(readFileSync(folder+'/manifest.json')),
r=readFileSync(folder+'/runtime.bin'),s=readFileSync('bin/fwdc239b-gr3-official.bin');
buildNativeLibrary(s,r,m);
const at=m.capture_lifecycle.snapshot.patches[1].entry-m.base;
r.writeUInt32LE(0xe59000f0,at+24); // former owner+f0 recipe instead of this task's r1
m.code_sha256=createHash('sha256').update(r).digest('hex');
assert.throws(()=>buildNativeLibrary(s,r,m),/snapshot submission wrapper instruction differs/);
"""
            subprocess.run(['node', '--input-type=module', '-e', js, str(folder)], cwd=ROOT, check=True, capture_output=True)

    def test_still_snapshot_cache_exists_when_live_color_preview_is_disabled(self):
        with tempfile.TemporaryDirectory() as d:
            js = """import{writeFileSync}from'node:fs';
import{readNativeOfficial,prepareNative,generateNative}from'./node/gr3-native-library.mjs';
import{defaultConfiguration}from'./web/gr3/native-library-state.mjs';import{decodeFrameMap}from'./node/gr3-frames.mjs';
const model=process.argv[2],s=await readNativeOfficial(model),c=defaultConfiguration(model),o={debug_mode:true,live_color:false,hdf_enabled:false};
const p=prepareNative(s,c,o),r=await generateNative(s,c,p.configuration_sha256,o);
const b=decodeFrameMap(r.candidate).decoded;
writeFileSync(process.argv[1]+'/rtos.bin',b.subarray(0x10870,0x10870+b.readUInt32LE(0x1086c)));
writeFileSync(process.argv[1]+'/manifest.json',JSON.stringify(r.manifest));
"""
            subprocess.run(['node', '--input-type=module', '-e', js, d, self.manifest.get('camera_model','gr3')], cwd=ROOT, check=True, capture_output=True)
            self.manifest = json.loads((Path(d) / 'manifest.json').read_text())
            self.image = (Path(d) / 'rtos.bin').read_bytes()
            self.assertFalse(self.manifest['capture_lifecycle']['snapshot']['live_color'])
            self.assertEqual(self.manifest['settings_menu']['owner_bytes'], 0x613c)
            self.test_durable_ui_load_publishes_owner_used_by_actual_task_submission()

    def test_ordinary_builtin_profiles_complete_under_native_parameter_changes(self):
        for film in range(33, 79):
            for extra in ({}, {0x77d: 1, 0x77e: 7, 0x780: 2, 0x793: 6, 0x794: 2}):
                with self.subTest(film=film, extra=extra):
                    e, recipe, obj, frame, si, request, data = self.fixture(film)
                    for offset, value in extra.items():
                        e.u.mem_write(si + 0x71248 + offset, bytes([value]))
                    self.make(e, recipe, obj, frame)
                    self.assertEqual(self.call(e, 'm10v_isp_frame_recipe_completed', recipe, si, 25, data), 1)
                    self.assertEqual(self.capture(e, recipe, si, request), 0)

    def test_fitted_builtin_films_use_isp_for_stills_without_pixel_fallback(self):
        # User-approved ISP approximation: the same profiles already used by
        # live view must also own still color, including IDs beyond 78.
        for film in (77, 298, *range(291, 298), *range(299, 306), *range(309,317)):
            with self.subTest(film=film):
                e, recipe, obj, frame, si, request, data = self.fixture(film)
                self.make(e, recipe, obj, frame)
                self.assertEqual(self.call(e, 'm10v_isp_frame_recipe_completed', recipe, si, 25, data), 1)
                self.assertEqual(self.capture(e, recipe, si, request), 0)

    def test_committed_film_with_stock_shooting_tone_does_not_complete_native_color(self):
        # Reproduce a source-level coverage gap, not a claimed device diagnosis:
        # encoder accepts frozen UI tone, while Still begin requires a carrier SI.
        for film in (62, 299):
            with self.subTest(film=film):
                e, recipe, obj, frame, si, request, data = self.fixture(film)
                e.u.mem_write(recipe + 0x4a08 + 22, struct.pack('<H', 25))
                e.u.mem_write(si + 0x77c, b'\x0b')
                e.u.mem_write(si + 0x71248 + 0x77c, b'\x0b')
                self.make(e, recipe, obj, frame)
                self.assertEqual(self.call(e, 'm10v_isp_frame_recipe_completed', recipe, si, 11, data), 0)
                # Capture must reach the real image-processing boundary instead
                # of returning through the native-only zero-work route.
                with self.assertRaisesRegex(AssertionError, 'pixel/allocation/filesystem boundary'):
                    self.capture(e, recipe, si, request)

    def test_charmera_and_pixel_do_not_claim_native_color_completion(self):
        for film in (289, 290):
            e, recipe, obj, frame, si, request, data = self.fixture(film)
            self.make(e, recipe, obj, frame)
            self.assertEqual(self.call(e, 'm10v_isp_frame_recipe_completed', recipe, si, 25, data), 0)

    def test_all_factory_tones_bypass_custom_color_without_pixel_or_storage_work(self):
        # Include both official positive/negative looks without relying on UI
        # labels: every original tone 11..22 keeps the factory encoder path.
        for tone in range(11, 23):
            with self.subTest(tone=tone):
                e, recipe, obj, frame, si, request, data = self.fixture(62)
                e.u.mem_write(si + 0x77c, bytes([tone]))
                e.u.mem_write(si + 0x71248 + 0x77c, bytes([tone]))
                self.make(e, recipe, obj, frame)
                self.assertEqual(self.call(e, 'm10v_isp_frame_recipe_completed', recipe, si, tone, data), 0)
                self.assertEqual(self.capture(e, recipe, si, request), 0xfffffffc)

    def test_wrong_frame_or_changed_configuration_cannot_skip_cpu_color(self):
        e, recipe, obj, frame, si, request, data = self.fixture()
        self.make(e, recipe, obj, frame)
        self.assertEqual(self.call(e, 'm10v_isp_frame_recipe_completed', recipe, si + 4, 25, data), 0)
        self.assertEqual(self.call(e, 'm10v_isp_frame_recipe_completed', recipe, si, 26, data), 0)
        changed = bytearray(e.u.mem_read(data, 184))
        struct.pack_into('<I', changed, 8, 8)
        struct.pack_into('<I', changed, 180, zlib.crc32(changed[:180]))
        e.u.mem_write(data, bytes(changed))
        self.assertEqual(self.call(e, 'm10v_isp_frame_recipe_completed', recipe, si, 25, data), 0)

if __name__ == '__main__':
    unittest.main()
