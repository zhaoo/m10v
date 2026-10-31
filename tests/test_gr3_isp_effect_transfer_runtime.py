"""Execute real ARM runtime with explicit services doubles; pixels unmapped."""
import ctypes
import hashlib
import sys
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm_const as A
from scripts.build_gr3_border_wait_guard import FLAGS, HOOKS, arm_bl

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'native/gr3/m10v_isp_effect_transfer_runtime.c'
BASE = 0x54160000
PLAN = 0x55000000
TOKEN = 0x55001234
STUB_NAMES = (
    'm10v_border_stage_enter', 'm10v_border_stage_leave',
    'm10v_border_client_construct', 'm10v_border_client_prepare',
    'm10v_border_client_done', 'm10v_border_client_destroy_if_done',
    'm10v_border_transfer_construct', 'm10v_border_fill_construct',
    'm10v_border_resize_construct', 'm10v_border_client_wait',
    'border_recovery_transfer_body_hook', 'border_recovery_transfer_wait_hook',
    'border_recovery_fill_body_hook', 'border_recovery_fill_wait_hook',
    'border_recovery_resize_body_hook', 'border_recovery_resize_wait_hook',
    'border_recovery_resize_dma_wait_hook', 'border_recovery_fill_release_hook',
    'border_recovery_resize_release_hook', 'm10v_isp_effect_resize_status_hook')
STUBS = {name: 0x53000100 + 4*i for i, name in enumerate(STUB_NAMES)}


class TransferRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.folder.cleanup)
        p = Path(cls.folder.name)
        obj, elf, link = p/'runtime.o', p/'runtime.elf', p/'link.ld'
        subprocess.run([shutil.which('clang'), *FLAGS, '-c', str(SOURCE), '-o', str(obj)], check=True, capture_output=True)
        link.write_text('\n'.join(f'{n} = {v};' for n, v in STUBS.items()) + f'\nSECTIONS {{ . = {BASE}; .text : {{ *(.text*) }} .rodata : {{ *(.rodata*) }} /DISCARD/ : {{ *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }} }}')
        subprocess.run([shutil.which('ld.lld'), '-T', str(link), '--entry=m10v_isp_effect_transfer_execute', str(obj), '-o', str(elf)], check=True, capture_output=True)
        binary = elf.read_bytes()
        sh, = struct.unpack_from('<I', binary, 32)
        count, = struct.unpack_from('<H', binary, 48)
        rows = [struct.unpack_from('<10I', binary, sh+40*i) for i in range(count)]
        cls.sections = []
        for r in rows:
            if r[2]&2 and r[5]:
                assert r[1] == 1 and not r[2]&1, 'no writable globals'
                cls.sections.append((r[3], binary[r[4]:r[4]+r[5]]))
        cls.entry, = struct.unpack_from('<I', binary, 24)

    def setUp(self):
        self.u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        for address, length in ((0x53000000, 4096), (0x53400000, 0x400000),
                                (0x53800000, 0x100000), (BASE, 0x10000), (0x55000000, 0x10000), (0x55ff0000, 0x10000)):
            self.u.mem_map(address, length)
        for at, data in self.sections:
            self.u.mem_write(at, data)
        self.events = []
        self.mode = ''
        self.client = 0
        self.calls = 0
        self.u.hook_add(UC_HOOK_CODE, self.hook)
        for at, old, target, _ in HOOKS:
            self.put(at, arm_bl(at, STUBS[target]) if isinstance(target, str) else target)
        self.put(0x53771620, arm_bl(0x53771620, STUBS['m10v_isp_effect_resize_status_hook']) & ~0x01000000)
        for i, (_, offset, tag_offset, tag) in enumerate(self.factories()):
            self.put(0x55002000+i*0x100+offset, 0x55003000+i*0x100)
            self.put(0x55003000+i*0x100+tag_offset, tag)
        self.plan = [2, 0x54400000, 0x54401000, 0, 32|(32<<16), 64|(64<<16), 2|(2<<16), 2,
                     2, 0x70000000, 0x70000400, 0, 32|(32<<16), 32|(32<<16), 0, 2, 1536]
        self.put(PLAN, *self.plan)

    @staticmethod
    def factories():
        return ((0x5369a0e8, 4, 0x44, 0x42575431),
                (0x53658a68, 4, 0x58, 0x42465731),
                (0x53672c48, 12, 0x48, 0x42525731))

    def put(self, at, *values):
        self.u.mem_write(at, struct.pack('<'+'I'*len(values), *values))

    def word(self, at):
        return struct.unpack('<I', self.u.mem_read(at, 4))[0]

    def reg(self, index):
        return self.u.reg_read(getattr(A, f'UC_ARM_REG_R{index}'))

    def ret(self, value=0):
        self.u.reg_write(A.UC_ARM_REG_R0, value & 0xffffffff)
        self.u.reg_write(A.UC_ARM_REG_PC, self.u.reg_read(A.UC_ARM_REG_LR))

    def hook(self, u, pc, size, data):
        for i, (getter, _, _, _) in enumerate(self.factories()):
            if pc == getter:
                self.ret(0x55002000+i*0x100)
                return
        names = {v: n for n, v in STUBS.items()}
        name = names.get(pc)
        if name:
            self.events.append(name)
            if name == 'm10v_border_stage_enter':
                self.assertEqual(self.reg(0), TOKEN)
                self.ret(0 if self.mode == 'gate' else 0x55003000)
            elif name == 'm10v_border_stage_leave':
                self.assertEqual((self.reg(0), self.reg(1)), (0x55003000, TOKEN))
                self.ret(0 if self.mode == 'leave' else 1)
            elif name == 'm10v_border_client_construct':
                self.client = self.reg(0)
                self.put(self.client, *([0]*19))
                self.put(self.client+32, 0x42574331)
                self.ret()
            elif name == 'm10v_border_client_prepare':
                self.assertEqual((self.reg(1), self.reg(2)), (0x03020002, 0x40))
                if self.mode == 'prepare':
                    self.ret(0)
                    return
                self.put(self.client+36, 1, 0, 0, 0, 0x03020002, 0x40, 0, 0, 0, 0)
                self.ret(1)
            elif name == 'm10v_border_client_done':
                self.ret(0 if self.mode == 'done' else 1)
            elif name == 'm10v_border_client_destroy_if_done':
                self.ret(0 if self.mode == 'destroy' else 1)
            else:
                self.fail('unexpected service '+name)
            return
        if pc == 0x5383c8a8:
            self.events.append('workspace-clean-invalidate')
            self.assertEqual((self.reg(0),self.reg(1)),(self.plan[9],self.plan[16]))
            self.ret()
            return
        if pc == 0x534ab6b8:
            self.calls += 1
            self.events.append('native-resize')
            self.assertEqual(self.reg(0), self.client)
            self.assertEqual(self.reg(3), 1)
            self.assertEqual(self.word(self.client+68), 0x31584645)
            self.assertEqual(bytes(u.mem_read(self.reg(1), 32)), struct.pack('<8I', *self.plan[:8]))
            self.assertEqual(bytes(u.mem_read(self.reg(2), 32)), struct.pack('<8I', *self.plan[8:16]))
            self.put(self.client+36, 0, 0, 0 if self.mode == 'completion' else 1)
            if self.mode == 'error': self.put(self.client+72, 1)
            if self.mode == 'owner': self.put(self.client+32, 0)
            if self.mode == 'pending': self.put(self.client+36, 1)
            if self.mode == 'inflight': self.put(self.client+40, 1)
            if self.mode == 'event': self.put(self.client+52, 0)
            if self.mode == 'marker': self.put(self.client+68, 0)
            self.ret()
        if pc == 0x536b0a74:
            self.events.append('fatal-hold')
            u.emu_stop()

    def execute(self, token=TOKEN):
        self.u.reg_write(A.UC_ARM_REG_R0, PLAN)
        self.u.reg_write(A.UC_ARM_REG_R1, token)
        self.u.reg_write(A.UC_ARM_REG_SP, 0x55ffe000)
        self.u.reg_write(A.UC_ARM_REG_LR, 0x55fff000)
        self.u.emu_start(self.entry, 0x55fff000, count=100000)
        return self.reg(0)

    def test_owned_success_uses_native_resize_then_destroys_and_leaves(self):
        self.assertEqual(self.execute(), 1)
        self.assertEqual(self.calls, 1)
        self.assertEqual(self.events[-3:], ['m10v_border_client_done', 'm10v_border_client_destroy_if_done', 'm10v_border_stage_leave'])

    def test_each_dma_write_cleans_and_invalidates_exact_workspace_before_enqueue(self):
        self.assertEqual(self.execute(),1)
        self.assertEqual(self.events.count('workspace-clean-invalidate'),1)
        self.assertLess(self.events.index('m10v_border_stage_enter'),self.events.index('workspace-clean-invalidate'))
        self.assertLess(self.events.index('m10v_border_client_prepare'),self.events.index('workspace-clean-invalidate'))
        self.assertLess(self.events.index('workspace-clean-invalidate'),self.events.index('native-resize'))
        self.events=[];self.assertEqual(self.execute(),1)
        self.assertEqual(self.events.count('workspace-clean-invalidate'),1)

    def test_yuv422_accepts_full_height_chroma_and_exact48mb_workspace(self):
        self.plan[8]=1;self.plan[10]=0x70000000+24000000
        self.plan[12]=6000|(4000<<16);self.plan[13]=6000|(4000<<16);self.plan[16]=48000000
        self.put(PLAN,*self.plan)
        self.assertEqual(self.execute(),1);self.assertEqual(self.calls,1)

    def test_upper_data_bank_remains_unmapped_and_uses_same_native_lifetime(self):
        self.plan[9]=0xA4000000;self.plan[10]=0xA4000400
        self.put(PLAN,*self.plan)
        self.assertEqual(self.execute(),1)
        self.assertEqual(self.calls,1)
        self.assertEqual(self.events[-1],'m10v_border_stage_leave')

    def test_each_format_rejects_other_format_workspace_without_enqueue(self):
        for fmt,workspace in ((1,1536),(2,2048)):
            self.plan[8]=fmt;self.plan[16]=workspace
            self.put(PLAN,*self.plan)
            self.assertEqual(self.execute(),0xffffffff)
            self.assertEqual(self.events,[])

    def test_every_installed_guard_is_required_before_gate(self):
        for at, old, target, _ in (*HOOKS, (0x53771620, 0, 'm10v_isp_effect_resize_status_hook', 'status')):
            installed = self.word(at)
            self.put(at, old)
            self.assertEqual(self.execute(), 0xffffffff, hex(at))
            self.assertEqual(self.events, [])
            self.put(at, installed)

    def test_each_worker_tag_is_required(self):
        for i, (_, _, offset, tag) in enumerate(self.factories()):
            at = 0x55003000+i*0x100+offset
            self.put(at, 0)
            self.assertEqual(self.execute(), 0xffffffff)
            self.assertEqual(self.events, [])
            self.put(at, tag)

    def test_inline_status_hook_must_preserve_lr_with_b_instead_of_bl(self):
        self.put(0x53771620, arm_bl(0x53771620, STUBS['m10v_isp_effect_resize_status_hook']))
        self.assertEqual(self.execute(), 0xffffffff)
        self.assertEqual(self.events, [])

    def test_invalid_descriptors_rejected_without_gate_or_pixels(self):
        for index, bad in ((0, 1), (1, 0x55000000), (2, 0), (3, 1), (4, 3|(32<<16)),
                           (5, 63|(64<<16)), (6, 40), (7, 0), (8, 1), (9, 0x54fffff0),
                           (10, 0x70000000), (12, 0), (13, 16|(32<<16)), (14, 2), (16, 1535)):
            with self.subTest(index=index):
                p = self.plan.copy(); p[index] = bad
                self.put(PLAN, *p)
                self.assertEqual(self.execute(), 0xffffffff)
                self.assertEqual(self.events, [])
        self.put(PLAN, *self.plan)
        self.assertEqual(self.execute(token=0), 0xffffffff)

    def test_gate_failure_is_before_client_or_enqueue(self):
        self.mode = 'gate'
        self.assertEqual(self.execute(), 0xffffffff)
        self.assertEqual(self.calls, 0)

    def test_prepare_failure_destroys_idle_client_and_leaves_without_enqueue(self):
        self.mode = 'prepare'
        self.assertEqual(self.execute(), 0xffffffff)
        self.assertEqual(self.calls, 0)
        self.assertEqual(self.events[-2:], ['m10v_border_client_destroy_if_done', 'm10v_border_stage_leave'])

    def test_rom_ram_spans_and_plan_overlap_are_checked(self):
        for index, bad in ((1, 0x540b5fc0), (1, 0x54ffffc0), (9, 0x7ffffff0),
                           (9, PLAN), (2, 0x54401040), (10, 0x70000410), (16, 1537)):
            p = self.plan.copy(); p[index] = bad
            if index == 1: p[2] = bad+4096
            if index == 9: p[10] = bad+1024
            self.put(PLAN, *p)
            self.assertEqual(self.execute(), 0xffffffff, (index, hex(bad)))
            self.assertEqual(self.events, [])

    def test_completed_error_returns_failure_after_release(self):
        self.mode = 'error'
        self.assertEqual(self.execute(), 0xfffffffc)
        self.assertEqual(self.events[-2:], ['m10v_border_client_destroy_if_done', 'm10v_border_stage_leave'])

    def test_unexpected_postsubmit_ownership_or_completion_retains_stack_gate(self):
        for mode in ('owner', 'completion', 'done', 'pending', 'inflight', 'event', 'marker', 'destroy', 'leave'):
            with self.subTest(mode=mode):
                self.setUp(); self.mode = mode
                self.execute()
                self.assertEqual(self.events[-1], 'fatal-hold')
                if mode not in ('destroy', 'leave'):
                    self.assertNotIn('m10v_border_client_destroy_if_done', self.events)
                    self.assertNotIn('m10v_border_stage_leave', self.events)

    def test_original_cache_backend_is_clean_invalidate_with_native_barriers_and_ack_contract(self):
        # Actual original ARM paths; CP15/cache geometry and remote ACKs are
        # explicit doubles, never fixture pixels or physical coherency claims.
        sys.path.insert(0,str(ROOT/'scripts'))
        from border_cache_contract import probe_cache,probe_remote
        from scripts.build_gr3_border_runtime import RUNTIME_SPANS
        from scripts.build_gr3_border_wait_guard import MODELS
        _,start,end,pinned=next(s for s in RUNTIME_SPANS if s[0]=='cache_backend')
        for model in ('gr3','gr3x'):
            rom=(ROOT/f'builds/gr3-pure-isp-feasibility-20261031/{model}-official-rtos.bin').read_bytes()
            self.assertEqual(hashlib.sha256(rom).hexdigest(),MODELS[model]['rtos_sha256'])
            self.assertEqual(hashlib.sha256(rom[start-0x53000000:end-0x53000000]).hexdigest(),pinned)
            result=probe_cache(rom,entry=0x5383c8a8,length=48000000,address=0x70000000)
            events=result['events'];ops=[e for e in events if e['kind']=='maintenance']
            self.assertTrue(ops);self.assertEqual({e['mode'] for e in ops},{'clean_invalidate'})
            self.assertEqual({e['scope'] for e in ops},{'setway'});self.assertEqual({e['level'] for e in ops},{0,1})
            self.assertEqual(events[0],dict(kind='backend',pc=0x5383c8a8,address=0x70000000,bytes=48000000))
            self.assertEqual(events[-1]['kind'],'dsb');self.assertTrue(result['remote_ack_is_double'])
            self.assertTrue(result['maintenance_is_recorded_not_physical']);self.assertFalse(result['pixels_mapped']);self.assertFalse(result['camera_tested'])
            invalidate=probe_cache(rom,entry=0x5383c834,length=128,address=0x70000000)
            self.assertEqual({e['mode'] for e in invalidate['events'] if e['kind']=='maintenance'},{'invalidate'})
            for core in (0,1):
                remote=probe_remote(rom,mode=2,core=core)['events']
                ack=next(i for i,e in enumerate(remote) if e['kind']=='ack_store' and e['value']==1)
                self.assertTrue(any(e['kind']=='maintenance' and e['mode']=='clean_invalidate' for e in remote[:ack]))
                self.assertEqual(remote[ack-1]['kind'],'dsb');self.assertEqual(remote[ack+1]['kind'],'dsb')

    def test_host_is_explicitly_unsupported(self):
        out = Path(self.folder.name)/'host.dylib'
        subprocess.run([shutil.which('clang'), '-shared', '-fPIC', '-Wall', '-Wextra', '-Werror', str(SOURCE), '-o', str(out)], check=True, capture_output=True)
        lib = ctypes.CDLL(str(out))
        self.assertEqual(lib.m10v_isp_effect_transfer_execute(None, 1), -3)
