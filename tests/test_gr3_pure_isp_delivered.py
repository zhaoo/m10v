"""Final BIN/receipt identity and genuine pure-ISP capture ingress contracts.

Photo/workspace planes are unmapped. Appended texture ROM remains in the exact
decoded image, with CPU read/write traps over the entire asset span. Kernel
queue/filesystem/heap services are explicit doubles. These tests establish
software control contracts, never silicon output, physical DMA or performance.
The combination test executes original buffer layout and Setup11/5/6 metadata
handoffs; the unchanged downstream phase5 DSP pixel conversion is not executed.
"""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import unittest
import zlib

from tests.test_gr3_isp_base import StockISP, BASE
from tests import test_gr3_film_pipeline_current as current
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn import arm_const as A

ROOT = Path(__file__).resolve().parents[1]


class DeliveredPureIspTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = Path(os.environ.get('M10V_PURE_ISP_CANDIDATE', ROOT / 'builds/gr3-pure-isp-candidate-r1'))
        receipt_path = folder / 'M10V-build-receipt.json'
        manifest_path = folder / 'M10V-runtime-manifest.json'
        if not manifest_path.exists():
            manifest_path = folder / 'evidence/M10V-runtime-manifest.json'
        if not receipt_path.exists() or not manifest_path.exists():
            raise unittest.SkipTest('build final audited pure ISP candidate first')
        cls.folder = folder
        cls.receipt = json.loads(receipt_path.read_text())
        cls.manifest = json.loads(manifest_path.read_text())
        cls.binary = folder / cls.receipt.get('filename', 'fwdc239b.bin')
        if not cls.binary.exists():
            raise AssertionError('receipt names missing final BIN')
        data = cls.binary.read_bytes()
        if hashlib.sha256(data).hexdigest() != cls.receipt['candidate_sha256']:
            raise AssertionError('final BIN no longer matches receipt')
        js = "import{readFileSync}from'node:fs';import{decodeFrameMap}from'./node/gr3-frames.mjs';let b=readFileSync(process.argv[1]),d=decodeFrameMap(b,b.readUInt32LE(b.length-8)).decoded;process.stdout.write(d.subarray(0x10870,0x10870+d.readUInt32LE(0x1086c)));"
        cls.image = subprocess.check_output(['node', '--input-type=module', '-e', js, str(cls.binary)], cwd=ROOT)
        start = cls.manifest['base'] - BASE
        runtime = cls.image[start:start + cls.manifest['code_bytes']]
        if hashlib.sha256(runtime).hexdigest() != cls.manifest['code_sha256']:
            raise AssertionError('decoded final runtime no longer matches manifest')
        if cls.manifest['pure_isp_effects'].get('enabled') is not True:
            raise AssertionError('final artifact is not a pure ISP candidate')
        cls.symbols = cls.manifest['symbols']

    def call(self, e, name, *args):
        e.call(self.symbols[name], *args)
        return e.u.reg_read(A.UC_ARM_REG_R0)

    enqueue = current.CurrentFilmPipelineTests.enqueue
    make = current.CurrentFilmPipelineTests.make
    capture = current.CurrentFilmPipelineTests.capture

    def fixture(self, settings=(0, 0, 0, 1, 0, 0, 0, 0), width=640, height=480, cold=False):
        e = StockISP(self.image)
        e.events, e.files, e.writes, e.filesystem_online = [], {}, [], True
        e.hold_expected, e.held, e.forbid_files = False, False, False
        e.width, e.height = width, height
        assets = self.manifest['pure_isp_effects']['runtime_assets']
        def pixel_access(u, access, address, size, value, data):
            raise AssertionError(f'CPU accessed immutable texture pixels at {address:#x}')
        e.u.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, pixel_access,
                    begin=assets['base'], end=assets['base'] + assets['bytes'] - 1)
        filesystem, link, fs = e.alloc(16), e.alloc(4), e.alloc(0x40)
        e.w32(filesystem + 8, link)
        e.w32(link, fs)
        e.u.mem_write(fs + 0x20, b'\x01')
        e.debug_records = []
        def services(u, pc, size, data):
            if pc == self.symbols['m10v_debug_batch']:
                pointer, count = u.reg_read(A.UC_ARM_REG_R0), u.reg_read(A.UC_ARM_REG_R1)
                for index in range(count):
                    e.debug_records.append(struct.unpack('<5I', u.mem_read(pointer + index * 20, 20)))
            if pc not in (0x5368A92C, 0x536B0A74, 0x53828014, 0x53825648, 0x53825FA8):
                if pc in (self.symbols['m10v_isp_effects_render'], self.symbols['m10v_isp_effect_granulation_owned'],self.symbols['m10v_isp_effect_granulation_luma']):
                    e.events.append(pc)
                return
            if pc == 0x5368A92C:
                self.fail('stock CPU RNG was reached')
            if pc == 0x536B0A74 and e.hold_expected:
                e.held = True
                u.emu_stop()
                return
            if pc == 0x53828014:
                self.assertFalse(e.forbid_files, 'JPEG path touched filesystem')
                result = filesystem if e.filesystem_online else 0
            elif pc in (0x53825648, 0x53825FA8):
                r = [u.reg_read(getattr(A, f'UC_ARM_REG_R{i}')) for i in range(4)]
                name = bytes(u.mem_read(r[1], 16)).split(b'\0')[0].decode()
                if pc == 0x53825648:
                    data = e.files.get(name)
                    result = int(data is not None and len(data) == r[2])
                    if result:
                        u.mem_write(r[3], data)
                else:
                    e.files[name] = bytes(u.mem_read(r[3], r[2]))
                    e.writes.append(name)
                    result = 1
            else:
                return
            u.reg_write(A.UC_ARM_REG_R0, result)
            u.reg_write(A.UC_ARM_REG_PC, u.reg_read(A.UC_ARM_REG_LR))
        e.u.hook_add(UC_HOOK_CODE, services)
        owner = e.alloc(self.manifest['settings_menu']['owner_bytes'])
        e.w32(0x55063910, 1)
        e.w32(0x55063988, owner)
        self.call(e, 'm10v_camera_library_preview_init', owner)
        self.call(e, 'm10v_isp_effects_camera_init', owner)
        self.assertEqual(self.call(e, 'm10v_border_camera_refresh', owner), 0)
        setting_pointer = e.alloc(32)
        e.u.mem_write(setting_pointer, struct.pack('<8I', *settings))
        self.assertEqual(self.call(e, 'm10v_isp_effects_camera_save', owner, setting_pointer), 0)
        self.assertTrue(any(name.startswith('ISPFX') for name in e.writes))
        if cold:
            # UI lifecycle refresh cannot reach storage: its exact API keeps
            # this cache cold. Do not inject a shot or completion marker.
            e.filesystem_online = False
            self.call(e, 'm10v_isp_effects_camera_init', owner)
            e.filesystem_online = True
        state = bytearray(184)
        struct.pack_into('<IHHI', state, 0, 0x5630314D, 5, 184, 7)
        struct.pack_into('<H6B', state, 12, 66, 0, 0, 0, 3, 5, 2)
        struct.pack_into('<I', state, 180, zlib.crc32(state[:180]))
        state_pointer = e.alloc(184)
        e.u.mem_write(state_pointer, bytes(state))
        self.assertEqual(self.call(e, 'm10v_camera_library_mutation_begin'), 1)
        self.call(e, 'm10v_camera_library_mutation_end', state_pointer)
        recipe = e.alloc(0x57D8)
        e.w32(recipe, 0x53D0FC90)
        e.w32(recipe + 0x4778, 0x31545653)
        obj = e.cursor
        e.make(25, 1)
        frame = obj + 0x1400
        si = int.from_bytes(e.u.mem_read(frame + 0x82D0, 4), 'little')
        e.u.mem_write(si + 0x77C, b'\x0B' if cold else b'\x19')
        # e.make(stage1) initializes the embedded sub-shot. The original
        # digital settings producer consumes this BASE saved SI instead.
        # Menu4 is neutral shading/Clarity; base zero would request native-4.
        e.u.mem_write(si + 0x793, b'\x04')
        e.u.mem_write(si + 0x794, b'\x04')
        request = e.alloc(0x40)
        e.w32(recipe + 0x44C8, si)
        e.w32(recipe + 0x5C, request)
        e.u.reg_write(A.UC_ARM_REG_R0, recipe)
        e.u.reg_write(A.UC_ARM_REG_R4, recipe)
        e.u.emu_start(0x5350EB10, 0x5350EB38, count=1000)
        reservation_owner = e.alloc(0x100)
        e.w32(reservation_owner + 0xF0, recipe)
        e.u.reg_write(A.UC_ARM_REG_R4, reservation_owner)
        e.u.reg_write(A.UC_ARM_REG_SP, 0x5EFFF000)
        e.u.reg_write(A.UC_ARM_REG_LR, 0x5E000000)
        e.u.emu_start(0x5351AED4, 0x5351AED8, count=100000)
        self.enqueue(e, recipe, 19)
        self.make(e, recipe, obj, frame)
        digital = recipe + 0x4320
        e.w32(digital, 0x53D0FC60)
        e.w32(digital + 0x30, recipe + 0x1A8)
        e.w32(digital + 0x34, si)
        a, b, native = e.alloc(32), e.alloc(32), e.alloc(0x100)
        for descriptor, y, uv in ((a, 0x65000000, 0x68000000), (b, 0x6B000000, 0x6E000000)):
            e.u.mem_write(descriptor, struct.pack('<4I6HI', 1, y, uv, 0, width, height, width, height, 0, 0, 2))
        def params():
            pointer, values = e.alloc(0x40), e.alloc(16)
            e.w32(pointer + 4, a)
            e.w32(pointer + 8, b)
            e.w32(pointer + 0x10, values)
            e.w32(pointer + 0x2C, 0x74000000)
            return pointer, values
        e.params = params
        return e, recipe, obj, frame, si, request, owner, setting_pointer, digital, native, state_pointer

    def at(self, e, site, digital, *args):
        for i in range(13):
            e.u.reg_write(getattr(A, f'UC_ARM_REG_R{i}'), args[i] if i < len(args) else 0)
        e.u.reg_write(A.UC_ARM_REG_R4, digital)
        e.u.reg_write(A.UC_ARM_REG_R12, digital)
        e.u.reg_write(A.UC_ARM_REG_SP, 0x5EFFF000)
        e.u.reg_write(A.UC_ARM_REG_LR, 0x5E000000)
        self.run_native(e, site, site + 4)
        self.assertEqual(e.u.reg_read(A.UC_ARM_REG_PC), site + 4,
            f'LR={e.u.reg_read(A.UC_ARM_REG_LR):#x} driver={getattr(e,"driver_events",[])[-12:]} granwait={getattr(e,"gran_wait_observed",None)} rawwait={getattr(e,"raw_wait_calls",0)}')
        return e.u.reg_read(A.UC_ARM_REG_R0)

    def run_native(self, e, start, stop, depth=0):
        e.u.emu_start(start, stop, count=10000000)
        while getattr(e, 'dispatch_due', None):
            due = e.dispatch_due
            e.dispatch_due = None
            paused = e.u.context_save()
            e.u.reg_write(A.UC_ARM_REG_SP, 0x63EFE000 - depth * 0x10000)
            e.u.reg_write(A.UC_ARM_REG_LR, 0x5E000000)
            if due['kind'] == 'worker':
                e.resize_dispatches = getattr(e, 'resize_dispatches', 0) + 1
                e.u.reg_write(A.UC_ARM_REG_R0, e.resize_worker)
                e.u.reg_write(A.UC_ARM_REG_R1, due['job'])
                entry = 0x53673F48
            else:
                e.irq_services = getattr(e, 'irq_services', []) + [due['service']]
                e.u.reg_write(A.UC_ARM_REG_R0, due['service'])
                e.u.reg_write(A.UC_ARM_REG_R1, 0x5B)
                e.u.reg_write(A.UC_ARM_REG_R2, 0x100)
                entry = 0x5376D0E8
            try:
                self.run_native(e, entry, 0x5E000000, depth + 1)
            except Exception as error:
                raise AssertionError(f'native Resize PC={e.u.reg_read(A.UC_ARM_REG_PC):#x} LR={e.u.reg_read(A.UC_ARM_REG_LR):#x} regs={[hex(e.u.reg_read(getattr(A, f"UC_ARM_REG_R{i}"))) for i in range(4)]} last_driver={e.driver_events[-8:]}') from error
            self.assertEqual(e.u.reg_read(A.UC_ARM_REG_PC), 0x5E000000,
                'native Resize dispatcher did not return: ' + repr(e.driver_events[-12:]) +
                ' release=' + repr(getattr(e, 'release_observed', None)))
            e.u.context_restore(paused)
            posted = e.kernel_events.get(due['event'], 0) & due['mask']
            self.assertNotEqual(posted, 0, 'real native callback did not post the requested event')
            if due['out']:
                e.w32(due['out'], posted)
            e.hardware_running = False
            e.u.reg_write(A.UC_ARM_REG_R0, 1)
            e.u.reg_write(A.UC_ARM_REG_PC, e.u.reg_read(A.UC_ARM_REG_LR))
            try:
                e.u.emu_start(e.u.reg_read(A.UC_ARM_REG_PC), stop, count=10000000)
            except Exception as error:
                fp=e.u.reg_read(A.UC_ARM_REG_FP)
                raise AssertionError(f'capture resume PC={e.u.reg_read(A.UC_ARM_REG_PC):#x} LR={e.u.reg_read(A.UC_ARM_REG_LR):#x} savedLR={int.from_bytes(e.u.mem_read(fp-4,4),"little"):#x} regs={[hex(e.u.reg_read(getattr(A, f"UC_ARM_REG_R{i}"))) for i in range(8)]}') from error

    def enable_native_driver_fixture(self, e, native):
        """Original graph/Resize workers; only driver/kernel endpoints doubled.

        Controller, IIP service, worker, lower context and driver are distinct
        objects. No private-client or effect completion field is written here.
        """
        driver = e.alloc(0x100)
        e.u.mem_map(0x28880000, 0x10000)
        e.w32(0x28880004, 2)  # Native driver's no-handshake metadata mode.
        e.w32(driver + 0x14, 0x28880000)
        e.w32(driver + 0x18, 0x28884000)  # Native coefficient-register aperture.
        register_bank, control_bank, registry = e.alloc(0x400), e.alloc(0x400), e.alloc(4)
        driver_vtable = e.alloc(0x40)
        for offset in range(0, 0x40, 4):
            e.w32(driver_vtable + offset, 0x5E000100)
        e.w32(driver, driver_vtable)
        e.w32(driver + 4, driver_vtable)
        irq_device = e.alloc(0x400)
        e.w32(irq_device, driver_vtable)
        e.w32(irq_device + 4, driver_vtable)
        irq_device_b = e.alloc(0x400)
        e.w32(irq_device_b, driver_vtable)
        e.w32(irq_device_b + 4, driver_vtable)
        irq_device_c = e.alloc(0x400)
        e.w32(irq_device_c, driver_vtable)
        e.w32(irq_device_c + 4, driver_vtable)
        irq_devices = {0x145: irq_device, 0x146: irq_device_b, 0x147: irq_device_c}
        # Native interface initializer537829d8 requests exactly145..15c.
        for device_id in range(0x148, 0x15D):
            obj = e.alloc(0x400)
            e.w32(obj, driver_vtable)
            e.w32(obj + 4, driver_vtable)
            irq_devices[device_id] = obj
        irq_manager = e.alloc(0x100)
        board_device = e.alloc(0x400)
        e.w32(board_device, driver_vtable)
        e.w32(board_device + 4, driver_vtable)
        power_device = e.alloc(0x400)
        e.w32(power_device, driver_vtable)
        e.w32(power_device + 4, driver_vtable)
        # Actual driver APIs consume per-unit register pointers from the
        # banks returned by native registry IDs130/131. Registers are RAM
        # fixtures; no silicon is accessed or emulated.
        for n in range(32):
            e.w32(register_bank + 0x14 + n * 8, 0x28880300 + n * 64)
            e.w32(control_bank + 0x14 + n * 4, 0x28880C00 + n * 16)
        e.driver_events, e.bitset_steps, e.jobs, e.dispatch_due = [], [], [], None
        e.kernel_events, e.pending_irq = {}, None
        e.handle_index = 0
        kernel = {0x536ABC78: 0, 0x536A9BF8: 0, 0x536AA3A4: 1, 0x536AA34C: 0,
            0x536A9DD4: 0, 0x536A9D1C: 1, 0x536A848C: 1, 0x536A8544: 1,
            0x536AE71C: 1, 0x536AE870: 1, 0x536A2954: 0, 0x536A29B4: 0,
            0x536B00C8: 1, 0x536B0014: 0, 0x53778490: 0, 0x53778474: 0,
            0x53778458: 0, 0x537780A8: 0, 0x53775018: 0, 0x5377C4D4: 0,
            0x53870CC8: 0, 0x53870D38: 0, 0x5387110C: 0,
            0x536BBC30: 0, 0x536BBCAC: 0, 0x536BBC3C: 0, 0x5383C8A8: 0,
            0x5377C1C8: 0, 0x53779E74: 0, 0x5E000100: 1,
            0x5377808C: 1, 0x537780B8: 1, 0x537780E4: 1,
            0x537780D4: 1, 0x53778100: 1, 0x537787DC: 0, 0x537787F8: 0,
            0x53778814: 0, 0x53783820: 0, 0x538C8444: 1, 0x538C84AC: 0,
            0x5356310C: 0, 0x5356307C: 1}
        e.hardware_running, e.board_casts = False, []
        kernel.update({0x53779570: 1, 0x5377955C: 0})
        def driver_boundary(u, pc, size, data):
            if pc == 0x5376E55C:
                e.pending_irq = u.reg_read(A.UC_ARM_REG_R0)
            if pc == self.symbols['m10v_isp_effect_granulation_wait']:
                frame = u.reg_read(A.UC_ARM_REG_R2)
                info = int.from_bytes(u.mem_read(frame + 8, 4), 'little')
                e.gran_wait_observed = ([hex(u.reg_read(getattr(A, f'UC_ARM_REG_R{i}'))) for i in range(3)],
                    [hex(v) for v in struct.unpack('<13I', u.mem_read(info, 52))])
            if pc == 0x5368A510:
                e.raw_wait_calls = getattr(e, 'raw_wait_calls', 0) + 1
            if pc == 0x53771968:
                svc, callback, info = (u.reg_read(getattr(A, f'UC_ARM_REG_R{i}')) for i in range(3))
                e.release_observed = (hex(svc), hex(callback), hex(info), bytes(u.mem_read(info + 0x74, 8)).hex(),
                    bytes(u.mem_read(info + 3, 1)).hex(),
                    [hex(int.from_bytes(u.mem_read(svc + off, 4), 'little')) for off in (0x40, 0x5C, 0x78, 0xFC, 0x100, 0x104, 0x108)])
            if pc not in kernel and pc not in (0x536B0A74, 0x5376C434, 0x5376C45C,
                    0x536ABD28, 0x536A9E8C, 0x535629B0, 0x53562AC8, 0x53562FF0, 0x53779DD4, 0x538C8330):
                return
            r = [u.reg_read(getattr(A, f'UC_ARM_REG_R{i}')) for i in range(4)]
            if pc == 0x536B0A74:
                e.driver_events.append((pc, u.reg_read(A.UC_ARM_REG_LR)))
                u.emu_stop()
                return
            if pc in (0x5376C434, 0x5376C45C):
                # Unicorn2.1.4 cannot execute these two original resource
                # bitset u64 shifts. Substitute only A32 metadata semantics.
                shift = u.reg_read(A.UC_ARM_REG_D17) & 255
                if shift & 128:
                    shift -= 256
                value = u.reg_read(A.UC_ARM_REG_D8)
                result = (((value << shift) if shift >= 0 else (value >> -shift)) & 0xFFFFFFFFFFFFFFFF) if abs(shift) < 64 else 0
                u.reg_write(A.UC_ARM_REG_D16, result)
                u.reg_write(A.UC_ARM_REG_PC, pc + 4)
                e.bitset_steps.append(pc)
                return
            if pc == 0x538C8330:
                # Opaque BOARD hardware adaptation only. No forged RTTI and
                # no bypass of any graph/controller/worker cast or ownership.
                if tuple(r[:3]) != (board_device, 0x53C1DD88, 0x53D5BCCC):
                    return
                e.board_casts.append(tuple(r[:3]))
                result = board_device
            elif pc == 0x536ABD28:
                job = r[1]
                if job < 0x55000000 or job > 0x80000000 - 16:
                    return
                if int.from_bytes(u.mem_read(job + 12, 4), 'little') != 0x00708002:
                    return
                output = int.from_bytes(u.mem_read(u.reg_read(A.UC_ARM_REG_SP) + 8, 4), 'little')
                e.w32(output, 0)
                e.w32(output + 4, 0)
                e.jobs.append(job)
                result = 1
            elif pc == 0x536A9E8C:
                if r[1] == 0x40 and e.jobs:
                    e.dispatch_due = dict(kind='worker',job=e.jobs.pop(0),event=r[0],mask=r[1],out=r[2])
                    u.emu_stop()
                    return
                if e.pending_irq is not None:
                    e.dispatch_due = dict(kind='irq',service=e.pending_irq,event=r[0],mask=r[1],out=r[2])
                    e.pending_irq = None
                    u.emu_stop()
                    return
                posted = e.kernel_events.get(r[0], 0) & r[1]
                self.assertNotEqual(posted, 0, 'kernel event wait has no posted success input')
                if r[2]:
                    e.w32(r[2], posted)
                e.hardware_running = False
                result = 1
            elif pc == 0x535629B0:
                result = registry
            elif pc == 0x53562AC8:
                bindings = {0: board_device, 0x130: register_bank, 0x131: control_bank,
                    0x12F: driver, 0x174: power_device, **irq_devices}
                self.assertIn(r[1], bindings, f'driver registry caller {u.reg_read(A.UC_ARM_REG_LR):#x}')
                result = bindings[r[1]]
            elif pc == 0x53562FF0:
                result = irq_manager
            elif pc == 0x53779DD4:
                result = e.handle_index
                e.handle_index += 1
            elif pc == 0x537780A8:
                result = int(e.hardware_running)
            elif pc in kernel:
                result = kernel[pc]
                if pc == 0x536A9D1C:
                    e.kernel_events[r[0]] = e.kernel_events.get(r[0], 0) | r[1]
                if pc == 0x536A9DD4:
                    e.kernel_events[r[0]] = e.kernel_events.get(r[0], 0) & ~r[1]
                if pc == 0x538C84AC:
                    e.w32(r[0], 1)
                if pc == 0x5377808C:
                    e.hardware_running = bool(r[1])
            else:
                return
            e.driver_events.append(pc)
            u.reg_write(A.UC_ARM_REG_R0, result)
            u.reg_write(A.UC_ARM_REG_PC, u.reg_read(A.UC_ARM_REG_LR))
        e.u.hook_add(UC_HOOK_CODE, driver_boundary)
        # These native boot singletons otherwise retain null object slots in
        # a freshly mapped offline BSS. Run their real create/connect paths.
        e.call(0x537887A0)
        interface_factory = e.u.reg_read(A.UC_ARM_REG_R0)
        e.call(0x53788730, interface_factory)
        e.call(0x53788678, interface_factory)
        e.call(0x5377ECFC)
        power_factory = e.u.reg_read(A.UC_ARM_REG_R0)
        power_vtable = int.from_bytes(e.u.mem_read(power_factory, 4), 'little')
        e.call(int.from_bytes(e.u.mem_read(power_vtable + 8, 4), 'little'), power_factory)
        # Real initialized singleton retains all module objects used by the
        # original Submit's cache/register sweep; no Submit boundary double.
        e.call(0x537700A0)
        factory = e.u.reg_read(A.UC_ARM_REG_R0)
        factory_vtable = int.from_bytes(e.u.mem_read(factory, 4), 'little')
        factory_init = int.from_bytes(e.u.mem_read(factory_vtable + 8, 4), 'little')
        try:
            e.call(factory_init, factory)
        except Exception as error:
            svc = int.from_bytes(e.u.mem_read(factory + 4, 4), 'little')
            raise AssertionError(f'IIP factory init r0={e.u.reg_read(A.UC_ARM_REG_R0):#x} service={svc:#x} service28={int.from_bytes(e.u.mem_read(svc + 0x28, 4), "little"):#x}') from error
        actual_service = int.from_bytes(e.u.mem_read(factory + 4, 4), 'little')
        actual_lower = int.from_bytes(e.u.mem_read(factory + 0x38, 4), 'little')
        e.driver_service = actual_service
        e.call(0x5368A48C, native)
        native_vtable = int.from_bytes(e.u.mem_read(native, 4), 'little')
        e.call(int.from_bytes(e.u.mem_read(native_vtable + 8, 4), 'little'), native)
        e.call(int.from_bytes(e.u.mem_read(native_vtable + 12, 4), 'little'), native)
        e.driver_controller = int.from_bytes(e.u.mem_read(native + 8, 4), 'little')
        self.assertNotEqual(e.driver_controller, actual_service)
        self.assertEqual(int.from_bytes(e.u.mem_read(e.driver_controller + 4, 4), 'little'), actual_service)
        for name, guard, factory, offset, size in (
            ('transfer', 0x5536C018, 0x5536C00C, 4, 0x58),
            ('fill', 0x55363278, 0x5536327C, 4, 0x68),
            ('resize', 0x5536BF6C, 0x5536BF5C, 12, 0x58)):
            worker = e.alloc(size)
            self.call(e, 'm10v_border_' + name + '_construct', worker)
            e.w32(guard, 1)
            e.w32(factory + offset, worker)
            if name == 'resize':
                e.resize_worker = worker
                e.w32(worker + 0x34, actual_lower)

    def jpeg(self, e, recipe, si, request, *, hold=False, prepared_photo=False):
        # Original Setup6/JPEG context ABI, with actual delivered trampoline
        # tail-chaining into the original queue service. No capture helper is
        # mocked and no native/shot completion is injected.
        context = recipe + 0x9B8
        e.w32(context, 0x53D0FBE0)
        if prepared_photo:
            e.call(0x5350E624, recipe, 6)
            self.assertEqual(int.from_bytes(e.u.mem_read(context + 0x3C, 4), 'little'), recipe + 0xB0)
        else:
            for offset, value in ((0x30, recipe + 0x1A8), (0x34, si),
                    (0x38, request), (0x3C, recipe + 0xB0), (0x40, recipe + 0xD0),
                    (0x44, recipe + 0xF0), (0x48, recipe + 0x110), (0x4C, recipe + 0x130)):
                e.w32(context + offset, value)
        e.w32(request, 0x53D0FE60)
        e.u.mem_write(request + 12, b'\1\1')
        e.u.mem_write(recipe + 0x140, b'\1')
        e.w32(recipe + 0x60, 0x70000000)
        dimensions = e.alloc(4)
        e.u.mem_write(dimensions, struct.pack('<HH', 6112, 4064))
        e.w32(recipe + 0x230, dimensions)
        if not prepared_photo:
            e.u.mem_write(recipe + 0xB0, struct.pack('<4I8H', 1, 0x65000000, 0x68000000, 0,
                e.width, e.height, e.width, e.height, 0, 0, 2, 0))
        else:
            self.assertEqual(bytes(e.u.mem_read(recipe + 0xB0, 32)), e.jpeg_expected_main)
        if not prepared_photo:
            e.u.mem_write(recipe + 0x110, struct.pack('<4I8H', 1, 0x6B000000, 0x6B100000, 0, 720, 480, 720, 480, 0, 0, 2, 0))
        entered = []
        encoder_message = e.alloc(32)
        def encoder(u, pc, size, data):
            if pc == 0x536ABD28:
                entered.append(pc)
                u.reg_write(A.UC_ARM_REG_R0, 0)
                u.reg_write(A.UC_ARM_REG_PC, u.reg_read(A.UC_ARM_REG_LR))
        hook = e.u.hook_add(UC_HOOK_CODE, encoder)
        e.hold_expected, e.forbid_files = hold, True
        for reg in range(13):
            e.u.reg_write(getattr(A, f'UC_ARM_REG_R{reg}'), context if reg == 4 else encoder_message if reg == 1 else 0)
        e.u.reg_write(A.UC_ARM_REG_SP, 0x5EFFF000)
        e.u.reg_write(A.UC_ARM_REG_LR, 0x5E000000)
        try:
            e.u.emu_start(self.symbols['m10v_chain_capture'], 0x5E000000, count=10000000)
        finally:
            e.u.hook_del(hook)
        if hold:
            self.assertTrue(e.held)
            self.assertEqual(e.u.reg_read(A.UC_ARM_REG_PC), 0x536B0A74)
            self.assertEqual(entered, [])
        else:
            self.assertEqual(e.u.reg_read(A.UC_ARM_REG_PC), 0x5E000000)
            self.assertEqual(entered, [0x536ABD28])

    def test_final_bin_runtime_assets_and_receipt_are_one_identity(self):
        pure = self.manifest['pure_isp_effects']
        assets = pure['runtime_assets']
        data = self.image[assets['base'] - BASE:assets['base'] - BASE + assets['bytes']]
        self.assertEqual(hashlib.sha256(data).hexdigest(), assets['sha256'])
        self.assertEqual(pure['recipe_bytes'], 0x57D8)
        self.assertEqual(len(pure['patches']), 7)
        self.assertEqual(self.receipt.get('runtime_sha256', self.manifest['code_sha256']), self.manifest['code_sha256'])

    def test_final_bin_zero_weight_endpoints_are_identity_including_unselected_uv_bytes(self):
        # Inspect actual decoded delivered data, independently of builder's
        # Python curve generator. This proves data binding, not ISP arithmetic.
        at=self.symbols['m10v_render_curves']-BASE
        tables=struct.unpack('<7680h',self.image[at:at+15360])
        for profile in range(9):
            offset=profile*768
            self.assertEqual(tables[offset+256:offset+512],tuple(range(256)))
            self.assertEqual(tables[offset+512:offset+768],tuple(range(256)))
        self.assertEqual(tables[9*768:9*768+256],(0,)*256)
        self.assertEqual(tables[9*768+256:9*768+512],tuple(range(256)))

    def test_all_off_real_producer_query_execution_and_jpeg_bridge_have_zero_pixel_access(self):
        e, recipe, obj, frame, si, request, owner, setting, digital, native, state = self.fixture()
        planning, _ = e.params()
        self.at(e, 0x535033D8, digital, planning, si, 1)
        queried = e.alloc(4)
        self.assertEqual(self.at(e, 0x535033E8, digital, native, planning, queried), 1)
        self.assertEqual(int.from_bytes(e.u.mem_read(queried, 4), 'little'), 0)
        execution, _ = e.params()
        self.at(e, 0x53503AA0, digital, execution, si, 1)
        self.assertEqual(self.at(e, 0x53503AB4, digital, native, execution, 0), 1)
        self.assertEqual(e.events, [])
        self.jpeg(e, recipe, si, request)

    def test_queued_ui_update_cannot_retarget_combined_effects_or48mb_query(self):
        settings = (2, 1, 2, 3, 1, 2, 1, 0)
        e, recipe, obj, frame, si, request, owner, setting, digital, native, state = self.fixture(settings, 6000, 4000)
        e.u.mem_write(setting, struct.pack('<8I', *([0] * 8)))
        self.assertEqual(self.call(e, 'm10v_isp_effects_camera_save', owner, setting), 0)
        self.enqueue(e, recipe, 0)
        output = e.alloc(96)
        self.assertEqual(self.call(e, 'm10v_isp_effects_shot_read', recipe, output), 1)
        self.assertEqual(bytes(e.u.mem_read(output + 16, 32)), struct.pack('<8I', *settings))
        planning, values = e.params()
        self.at(e, 0x535033D8, digital, planning, si, 1)
        self.assertEqual(struct.unpack('<h', e.u.mem_read(values + 4, 2))[0], 0)
        queried = e.alloc(4)
        self.assertEqual(self.at(e, 0x535033E8, digital, native, planning, queried), 1)
        self.assertGreaterEqual(int.from_bytes(e.u.mem_read(queried, 4), 'little'), 48000000)
        self.assertEqual(int.from_bytes(e.u.mem_read(recipe + 0x5778 + 68, 4), 'little'), 0)

    def test_untouched_cold_stock_first_shot_passes_gate_into_original_jpeg_route(self):
        e, recipe, obj, frame, si, request, owner, setting, digital, native, state = self.fixture(cold=True)
        self.assertEqual(int.from_bytes(e.u.mem_read(recipe + 0x5778 + 8, 4), 'little'), 2)
        self.assertEqual(self.call(e, 'm10v_isp_effects_pipeline_encoder_admit', recipe, si), 1)
        # -4 is the existing stock-tone bypass, chained by the original JPEG
        # hook. It must return, rather than holding an untouched cold frame.
        self.jpeg(e, recipe, si, request)
        self.assertEqual(e.events, [])

    def test_missing_own_completion_cannot_reach_actual_jpeg_queue(self):
        e, recipe, obj, frame, si, request, owner, setting, digital, native, state = self.fixture((0, 0, 0, 2, 0, 0, 0, 0))
        planning, _ = e.params()
        self.at(e, 0x535033D8, digital, planning, si, 1)
        queried = e.alloc(4)
        self.at(e, 0x535033E8, digital, native, planning, queried)
        self.assertEqual(int.from_bytes(e.u.mem_read(recipe + 0x5778 + 68, 4), 'little'), 0)
        self.jpeg(e, recipe, si, request, hold=True)
        if self.manifest['debug_mode']:
            facts = {r[2]: r for r in e.debug_records if r[0] == 198 and r[1] == recipe}
            self.assertEqual(facts[0x46583033][3:], (1, 0))
            self.assertEqual(facts[0x46583035][4], 1)
            checkpoints = [r[3] for r in e.debug_records if r[0] == 198 and r[2] == 0x46584800]
            self.assertEqual(checkpoints, [1, 2, 24])

    def test_disabled_ui_strength_memory_round_trips_journal_but_not_capture_pixels(self):
        preferences=0x46580000|3|(4<<2)|(2<<5)
        e,recipe,obj,frame,si,request,owner,setting,digital,native,state=self.fixture((0,1,1,1,1,0,1,preferences))
        self.assertEqual(self.call(e,'m10v_isp_effects_strength',setting,0),3)
        self.assertEqual(self.call(e,'m10v_isp_effects_strength',setting,1),4)
        shot=e.alloc(96)
        self.assertEqual(self.call(e,'m10v_isp_effects_shot_read',recipe,shot),1)
        self.assertEqual(int.from_bytes(e.u.mem_read(shot+44,4),'little'),0)
        planning,_=e.params();self.at(e,0x535033D8,digital,planning,si,1)
        queried=e.alloc(4)
        self.assertEqual(self.at(e,0x535033E8,digital,native,planning,queried),1)
        self.assertEqual(int.from_bytes(e.u.mem_read(queried,4),'little'),0)
        execution,_=e.params();self.at(e,0x53503AA0,digital,execution,si,1)
        self.assertEqual(self.at(e,0x53503AB4,digital,native,execution,0),1)
        self.assertEqual(e.events,[])
        self.jpeg(e,recipe,si,request)

    def test_grain_real_resize_worker_and_graph_completion_reach_original_jpeg_queue(self):
        e, recipe, obj, frame, si, request, owner, setting, digital, native, state = self.fixture((0, 0, 0, 2, 0, 0, 0, 0))
        self.enable_native_driver_fixture(e, native)
        planning, _ = e.params()
        self.at(e, 0x535033D8, digital, planning, si, 1)
        queried = e.alloc(4)
        self.at(e, 0x535033E8, digital, native, planning, queried)
        execution, _ = e.params()
        self.at(e, 0x53503AA0, digital, execution, si, 1)
        e.w32(execution + 0x30, int.from_bytes(e.u.mem_read(queried, 4), 'little'))
        self.assertEqual(self.at(e, 0x53503AB4, digital, native, execution, 0), 1)
        self.assertEqual(int.from_bytes(e.u.mem_read(recipe + 0x5778 + 68, 4), 'little'), 1)
        self.assertEqual(e.resize_dispatches, 1)
        self.assertTrue(e.bitset_steps)
        self.jpeg(e, recipe, si, request)

    def test_leak_and_grain_reuse_real_resize_service_and_granulation_before_jpeg(self):
        self.leak_and_grain_original_worker_case()

    def test_luma_mask_real_native_loader_uses_original_roi_stride_and_nv12_row_step(self):
        for fmt in (1,2):
            e,recipe,obj,frame,si,request,owner,setting,digital,native,state=self.fixture()
            self.enable_native_driver_fixture(e,native)
            photo,mask=e.alloc(32),e.alloc(32)
            width,height,stride=320,240,352
            mh=height if fmt==1 else height//2
            y=0xb1000004
            e.u.mem_write(photo,struct.pack('<8I',fmt,y,0xb2000004,0,width|(height<<16),stride|(height<<16),0,2))
            e.u.mem_write(mask,struct.pack('<8I',fmt,0x74000000,0,0,width|(mh<<16),width|(mh<<16),0,2))
            observed=[];cache=[]
            def trace(u,pc,size,data):
                if pc==0x5367afdc:
                    fp=u.reg_read(A.UC_ARM_REG_FP)
                    source=int.from_bytes(u.mem_read(fp-0x638,4),'little')
                    observed.append((int.from_bytes(u.mem_read(source+0x48,4),'little'),int.from_bytes(u.mem_read(source+0x38,4),'little')))
                if pc==0x536bbcac:cache.append((u.reg_read(A.UC_ARM_REG_R1),u.reg_read(A.UC_ARM_REG_R2)))
            e.u.hook_add(UC_HOOK_CODE,trace)
            args=(native,mask,photo,self.symbols['m10v_render_curves']+9*1536)
            for n,value in enumerate(args):e.u.reg_write(getattr(A,f'UC_ARM_REG_R{n}'),value)
            e.u.reg_write(A.UC_ARM_REG_SP,0x5efff000);e.u.reg_write(A.UC_ARM_REG_LR,0x5e000000)
            self.run_native(e,self.symbols['m10v_isp_effect_granulation_luma'],0x5e000000)
            self.assertEqual(e.u.reg_read(A.UC_ARM_REG_R0),1)
            self.assertEqual(observed,[(y,stride*(1 if fmt==1 else 2))])
            self.assertIn((y,stride*height),cache)
            self.assertGreaterEqual(len(e.irq_services),1)

    def test_native_constructor_with_dirty_descriptor_padding_still_completes_before_jpeg(self):
        self.leak_and_grain_original_worker_case(dirty_padding=True, grain=False)

    def test_native_upper_bank_unaligned_allocation_completes_before_jpeg(self):
        self.leak_and_grain_original_worker_case(dirty_padding=True, grain=False, raw_work=0xA4000008)

    def test_native_low_bank_allocation_margin_is_used_for_alignment(self):
        self.leak_and_grain_original_worker_case(dirty_padding=True, grain=False, raw_work=0x74000008)

    def test_padded_native_format_allows_original_blur_workspace_query(self):
        e, recipe, obj, frame, si, request, owner, setting, digital, native, state = self.fixture(
            (0, 0, 0, 1, 0, 1, 0, 0), 6000, 4000)
        planning, _ = e.params()
        for offset in (4, 8):
            descriptor = int.from_bytes(e.u.mem_read(planning + offset, 4), 'little')
            e.u.mem_write(descriptor + 1, b'\xA5' * 3)
        self.at(e, 0x535033D8, digital, planning, si, 1)
        queried = e.alloc(4)
        self.assertEqual(self.at(e, 0x535033E8, digital, native, planning, queried), 1)
        self.assertEqual(int.from_bytes(e.u.mem_read(queried, 4), 'little'), 64012768)
        self.assertEqual(int.from_bytes(e.u.mem_read(recipe + 0x5778 + 64, 4), 'little'), 1)
        self.assertEqual(int.from_bytes(e.u.mem_read(recipe + 0x5778 + 84, 4), 'little'), 1)

    def leak_and_grain_original_worker_case(self, dirty_padding=False, grain=True, raw_work=0x74000000):
        settings = (2, 1, 2, 3 if grain else 1, 1, 0, 0, 0)
        e, recipe, obj, frame, si, request, owner, setting, digital, native, state = self.fixture(settings, 6000, 4000)
        self.enable_native_driver_fixture(e, native)
        native_alloc = e.alloc
        def allocator(n):
            p = native_alloc(n)
            if dirty_padding and n == 0xB8:
                e.u.mem_write(p, b'\xA5' * n)
            return p
        e.alloc = allocator
        # Original recipe factory allocates an independent0xb8-byte holder,
        # binds it at44c4/435c, then Setup copies the source into BOTH native
        # A/B descriptors. Never alias this holder to the JPEG header.
        for reg, value in ((0, recipe), (3, 0), (4, recipe), (5, 0),
                           (6, request), (7, recipe + 0x4000),
                           (8, int.from_bytes(e.u.mem_read(0x5350FE10, 4), 'little'))):
            e.u.reg_write(getattr(A, f'UC_ARM_REG_R{reg}'), value)
        e.u.reg_write(A.UC_ARM_REG_SP, 0x5EFFF000)
        e.u.emu_start(0x5350FC60, 0x5350FDB8, count=100000)
        holder = int.from_bytes(e.u.mem_read(digital + 0x3C, 4), 'little')
        self.assertEqual(holder, int.from_bytes(e.u.mem_read(recipe + 0x44C4, 4), 'little'))
        self.assertNotEqual(holder, recipe + 0xAC)
        # The bounded factory fragment also clears its saved-SI slot. Restore
        # the same canonical producer input before executing its Setup block.
        e.w32(recipe + 0x44C8, si)
        for descriptor, y, uv in ((recipe + 0x70, 0x65000000, 0x68000000),
                                   (recipe + 0xD0, 0x6B000000, 0x6E000000)):
            e.u.mem_write(descriptor, struct.pack('<4I8H', 1, y, uv, 0,
                e.width, e.height, e.width, e.height, 0, 0, 2, 0))
        # Run original SetBufferAddress, which independently lays out source
        # and JPEG destination planes. Neither header nor planes are aliased.
        for offset, value in ((0x252, e.width), (0x256, e.width), (0x258, e.height),
                              (0x25C, 720), (0x25E, 720), (0x260, 480)):
            e.u.mem_write(recipe + offset, struct.pack('<H', value))
        e.call(0x5350DB3C, recipe, 0x65000000)
        e.call(0x5350E624, recipe, 11)
        for copied in (holder + 4, holder + 0x24):
            a = bytes(e.u.mem_read(copied, 32))
            b = bytes(e.u.mem_read(recipe + 0x70, 32))
            # Original536a3d84 copies byte fields as bytes, leaving their
            # three padding bytes untouched in the allocated native object.
            self.assertEqual(a[0], b[0])
            self.assertEqual(a[4:28], b[4:28])
            self.assertEqual(a[28], b[28])
            if dirty_padding:
                self.assertEqual(a[1:4], b'\xA5' * 3)
        # Complete original digital worker: virtual sizing, allocation,
        # execution and cleanup, with no substitute stage implementation.
        e.u.mem_write(digital + 0x48, b'\x01\x00')
        manager, vtable, message = e.alloc(0x8B00), e.alloc(0x40), e.alloc(16)
        e.w32(manager, vtable)
        e.w32(vtable + 0x2C, 0x535032B4)
        e.w32(manager + 0x8A0C, native)
        e.w32(message + 4, 0x01100002)
        e.w32(message + 8, digital)
        allocations, rendered_photos, rendered_buffers, released = [], [], [], []
        def task_boundary(u, pc, size, data):
            if pc == self.symbols['m10v_isp_effects_render']:
                rendered_photos.append(u.reg_read(A.UC_ARM_REG_R1))
                rendered_buffers.append((u.reg_read(A.UC_ARM_REG_R2), u.reg_read(A.UC_ARM_REG_R3)))
            if pc not in (0x536A2424, 0x536A27E8, 0x536A248C):
                return
            if pc == 0x536A27E8:
                allocations.append(u.reg_read(A.UC_ARM_REG_R1))
                result = raw_work
            else:
                if pc == 0x536A248C:
                    released.append(u.reg_read(A.UC_ARM_REG_R1))
                result = 1
            u.reg_write(A.UC_ARM_REG_R0, result)
            u.reg_write(A.UC_ARM_REG_PC, u.reg_read(A.UC_ARM_REG_LR))
        task_hook = e.u.hook_add(UC_HOOK_CODE, task_boundary)
        for reg in range(13):
            e.u.reg_write(getattr(A, f'UC_ARM_REG_R{reg}'), manager if reg == 0 else message if reg == 1 else 0)
        e.u.reg_write(A.UC_ARM_REG_SP, 0x5EFFF000)
        e.u.reg_write(A.UC_ARM_REG_LR, 0x5E000000)
        try:
            self.run_native(e, 0x535036CC, 0x5E000000)
        except Exception as error:
            raise AssertionError(f'original digital worker PC={e.u.reg_read(A.UC_ARM_REG_PC):#x} LR={e.u.reg_read(A.UC_ARM_REG_LR):#x}') from error
        e.u.hook_del(task_hook)
        self.assertEqual(e.u.reg_read(A.UC_ARM_REG_PC), 0x5E000000)
        # Original53503398..39c adds its16-byte allocation margin to every
        # nonzero query; the shot retains the original stock query of zero.
        self.assertEqual(allocations, [48000000 + 16])
        aligned_work=(raw_work+15)&~15
        self.assertEqual(rendered_buffers,[(aligned_work,48000016-(aligned_work-raw_work))])
        self.assertEqual(released,[raw_work])
        self.assertEqual(rendered_photos, [holder + 4])
        self.assertEqual(int.from_bytes(e.u.mem_read(recipe + 0x5778 + 80, 4), 'little'), 0)
        self.assertEqual(int.from_bytes(e.u.mem_read(recipe + 0x5778 + 68, 4), 'little'), 3 if grain else 2)
        self.assertEqual(e.events.count(self.symbols['m10v_isp_effect_granulation_owned']), 4 if grain else 3)
        self.assertEqual(e.events.count(self.symbols['m10v_isp_effect_granulation_luma']),2)
        self.assertEqual(e.resize_dispatches, 3 if grain else 2)
        # Multi-plane native Resize can submit more than one hardware job;
        # every delivered IRQ must still target this same real IIP service.
        self.assertGreaterEqual(len(e.irq_services), 7 if grain else 5)
        self.assertEqual(set(e.irq_services), {e.driver_service})
        self.assertEqual(len(e.board_casts), 1)
        # Original downstream phase5 consumes the effects source and writes
        # the separate JPEG photo. This proves metadata handoff, not execution
        # of that later DSP conversion or its physical pixel output.
        e.call(0x5350E624, recipe, 5)
        self.assertEqual(int.from_bytes(e.u.mem_read(recipe + 0x940, 4), 'little'), recipe + 0x70)
        self.assertEqual(int.from_bytes(e.u.mem_read(recipe + 0x944, 4), 'little'), recipe + 0xB0)
        self.assertNotEqual(bytes(e.u.mem_read(recipe + 0x74, 4)), bytes(e.u.mem_read(recipe + 0xB4, 4)))
        e.jpeg_expected_main = bytes(e.u.mem_read(recipe + 0xB0, 32))
        self.jpeg(e, recipe, si, request, prepared_photo=True)


if __name__ == '__main__':
    unittest.main()
