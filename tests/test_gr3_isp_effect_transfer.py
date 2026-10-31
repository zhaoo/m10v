"""Real C metadata planning, no mapped camera texture or photo pixels."""
import ctypes as C
import subprocess
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Texture(C.Structure):
    _fields_ = [(n, C.c_uint32) for n in ('base', 'bytes', 'width', 'height', 'stride')]


class Plan(C.Structure):
    _fields_ = [('source', C.c_uint32 * 8), ('destination', C.c_uint32 * 8),
                ('workspace_bytes', C.c_uint32)]


class IspEffectTransferTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        out = Path(cls.tmp.name) / 'transfer.dylib'
        subprocess.run(['clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-shared', '-fPIC', str(ROOT / 'native/gr3/m10v_isp_effect_transfer.c'),
                        '-o', str(out)], check=True, capture_output=True)
        cls.lib = C.CDLL(str(out))
        cls.lib.m10v_isp_effect_transfer_plan.argtypes = [C.POINTER(Texture)] + [C.c_uint32] * 7 + [C.POINTER(Plan)]
        cls.lib.m10v_isp_effect_transfer_plan.restype = C.c_int

    def texture(self):
        return Texture(0x54400000, 3072 * 2048 * 3 // 2, 3072, 2048, 3072)

    def format_plan(self, fmt, capacity=48000000, out=None, work=0x70000000):
        fn=self.lib.m10v_isp_effect_transfer_plan_format
        fn.argtypes=[C.POINTER(Texture)]+[C.c_uint32]*8+[C.POINTER(Plan)]
        fn.restype=C.c_int
        p=out if out is not None else Plan()
        result=fn(C.byref(self.texture()),work,capacity,6000,4000,3000,2000,9,fmt,C.byref(p))
        return result,p

    def test_yuv422_destination_requires48mb_and_preserves_nv12_source(self):
        result,p=self.format_plan(1)
        self.assertEqual(result,1);self.assertEqual(p.workspace_bytes,48000000)
        self.assertEqual(p.source[0],2);self.assertEqual(p.destination[0],1)
        self.assertEqual(p.destination[2]-p.destination[1],24000000)
        self.assertEqual(p.destination[5],6000|(4000<<16))
        for fmt,capacity in ((1,47999999),(1,36000000),(0,48000000),(3,48000000)):
            p=Plan();C.memset(C.byref(p),0xa5,C.sizeof(p));before=bytes(p)
            result,_=self.format_plan(fmt,capacity,p)
            self.assertEqual(result,-1);self.assertEqual(bytes(p),before)

    def test_explicit_nv12_is_exactly_legacy_api_and_rom_overlap_rejected(self):
        result,p=self.format_plan(2)
        old=Plan()
        self.assertEqual(self.lib.m10v_isp_effect_transfer_plan(C.byref(self.texture()),0x70000000,48000000,6000,4000,3000,2000,9,C.byref(old)),1)
        self.assertEqual(result,1);self.assertEqual(bytes(p),bytes(old))
        self.assertEqual(self.format_plan(1,work=0x54400000)[0],-1)

    def test_upper_data_bank_and_gap_boundaries_match_original_mmu(self):
        self.assertEqual(self.format_plan(1, work=0xA4000000)[0], 1)
        for address in (0x80000000, 0x90000000, 0x9FFFFFF0, 0xDFFF0000, 0xE0000000):
            out=Plan();C.memset(C.byref(out),0xa5,C.sizeof(out));before=bytes(out)
            self.assertEqual(self.format_plan(1,work=address,out=out)[0],-1)
            self.assertEqual(bytes(out),before)

    def test_buffer_banks_are_proven_by_both_pinned_original_startup_tables(self):
        import struct
        from scripts.analyze_gr3_800t_mapping import section_mapping
        from scripts.analyze_gr3_border_iip import validate
        for model in ('gr3','gr3x'):
            rom=(ROOT/f'builds/gr3-pure-isp-feasibility-20261031/{model}-official-rtos.bin').read_bytes()
            validate(rom,model)
            table,domains=struct.unpack_from('<II',rom,0x434)
            for lo,hi in ((0x55000000,0x80000000),(0xA0000000,0xE0000000)):
                for address in range(lo,hi,0x100000):
                    row=section_mapping(rom,table,address)
                    self.assertEqual(row['physical'],address)
                    self.assertEqual(row['descriptor']&0xFFFFF,0x14C26)
                    self.assertEqual((domains>>(row['domain']*2))&3,1)
            for address in (0x80000000,0x90000000,0x9FF00000,0xE0000000):
                self.assertEqual(section_mapping(rom,table,address)['access_permissions'],0)

    def test_yuv422_plan_passes_original_both_model_chroma_routes(self):
        from scripts.border_resize_contract import probe
        result,p=self.format_plan(1);self.assertEqual(result,1)
        for model in ('gr3','gr3x'):
            rom=(ROOT/f'builds/gr3-pure-isp-feasibility-20261031/{model}-official-rtos.bin').read_bytes()
            r=probe(rom,6000,4000,fmt=1,source_format=2,source_size=(3000,2000),
                source_stride=3072,source_rows=2048,source_plane=p.source[1],source_chroma_plane=p.source[2],
                source_roi=(2,2),destination_base=p.destination[1],destination_chroma_plane=p.destination[2],
                destination_stride=6000,texture_research=True)
            self.assertEqual(r['assertions'],[])
            self.assertEqual([a['selected_plane'] for a in r['loader_inputs']],[p.source[1],p.source[2]])
            self.assertEqual(r['scaler_requests'][1]['source']['size'],[1500,1000])
            self.assertEqual(r['scaler_requests'][1]['destination']['size'],[3000,4000])
            self.assertEqual(r['scaler_requests'][1]['destination']['planes'][1],p.destination[2])
            self.assertEqual(r['scaler_requests'][1]['destination']['stride'],6000)
            self.assertEqual(r['events'].count('submit_boundary'),2)
            self.assertEqual(r['events'][-1],'release_boundary')
            self.assertFalse(r['hardware_pixels_executed'])

    def test_freestanding_arm_planner_links_without_aeabi_copy_helpers(self):
        from scripts.build_gr3_border_wait_guard import FLAGS
        folder=Path(self.tmp.name);obj=folder/'planner-arm.o';elf=folder/'planner-arm.elf'
        subprocess.run([shutil.which('clang'),*FLAGS,'-c',str(ROOT/'native/gr3/m10v_isp_effect_transfer.c'),'-o',str(obj)],check=True,capture_output=True)
        subprocess.run([shutil.which('ld.lld'),'--entry=m10v_isp_effect_transfer_plan_format','-Ttext=0x54160000',str(obj),'-o',str(elf)],check=True,capture_output=True)

    def test_two_real_planes_fit_exact_native_workspace(self):
        p = Plan()
        self.assertEqual(self.lib.m10v_isp_effect_transfer_plan(C.byref(self.texture()),
            0x70000000, 36000000, 6000, 4000, 3000, 2000, 0, C.byref(p)), 1)
        self.assertEqual(p.workspace_bytes, 36000000)
        self.assertEqual(list(p.source[:4]), [2, 0x54400000, 0x54a00000, 0])
        self.assertEqual(list(p.destination[:4]), [2, 0x70000000, 0x716e3600, 0])
        self.assertEqual(p.destination[4], 6000 | (4000 << 16))
        self.assertEqual(p.destination[5], 6000 | (4000 << 16))
        self.assertEqual(p.source[4], 3000 | (2000 << 16))
        self.assertEqual(p.source[5], 3072 | (2048 << 16))
        self.assertEqual(p.source[7], 2)

    def test_roi_phase_changes_only_descriptor_metadata(self):
        for phase in range(64):
            p = Plan()
            self.assertEqual(self.lib.m10v_isp_effect_transfer_plan(C.byref(self.texture()),
                0x70000000, 36000000, 6000, 4000, 1500, 1000, phase, C.byref(p)), 1)
            x, y = p.source[6] & 65535, p.source[6] >> 16
            self.assertEqual((x | y) & 1, 0)
            self.assertLessEqual(x + 1500, 3072)
            self.assertLessEqual(y + 1000, 2048)

    def test_rejects_short_workspace_alias_and_non_rom_asset_without_mutation(self):
        for asset, work, capacity, width, height in (
            (self.texture(), 0x70000000, 35999999, 6000, 4000),
            (Texture(0x54f00000, 9437184, 3072, 2048, 3072), 0x70000000, 36000000, 6000, 4000),
            (self.texture(), 0x54400000, 36000000, 6000, 4000),
            (self.texture(), 0x70000000, 36000000, 6001, 4000),
            (self.texture(), 0x70000000, 36000000, 6000, 4001)):
            p = Plan()
            C.memset(C.byref(p), 0xa5, C.sizeof(p))
            before = bytes(p)
            self.assertEqual(self.lib.m10v_isp_effect_transfer_plan(C.byref(asset),
                work, capacity, width, height, 3000, 2000, 0, C.byref(p)), -1)
            self.assertEqual(bytes(p), before)

    def test_zero_output_size_is_no_work_and_no_mutation(self):
        p = Plan()
        C.memset(C.byref(p), 0xa5, C.sizeof(p))
        before = bytes(p)
        self.assertEqual(self.lib.m10v_isp_effect_transfer_plan(C.byref(self.texture()),
            0x70000000, 0, 0, 0, 0, 0, 0, C.byref(p)), 0)
        self.assertEqual(bytes(p), before)

    def test_generated_plan_passes_both_original_model_resize_routes(self):
        from scripts.border_resize_contract import probe
        p = Plan()
        self.assertEqual(self.lib.m10v_isp_effect_transfer_plan(C.byref(self.texture()),
            0x70000000, 36000000, 6000, 4000, 3000, 2000, 9, C.byref(p)), 1)
        for model in ('gr3', 'gr3x'):
            rom = (ROOT / f'builds/gr3-pure-isp-feasibility-20261031/{model}-official-rtos.bin').read_bytes()
            r = probe(rom, 6000, 4000, fmt=2, source_format=2,
                      source_size=(3000, 2000), source_stride=3072, source_rows=2048,
                      source_plane=p.source[1], source_chroma_plane=p.source[2],
                      source_roi=(2, 2), destination_base=p.destination[1],
                      destination_chroma_plane=p.destination[2], destination_stride=6000,
                      texture_research=True)
            self.assertEqual(r['assertions'], [])
            self.assertEqual(len(r['loader_inputs']), 2)
            self.assertEqual([x['selected_plane'] for x in r['loader_inputs']],
                             [p.source[1], p.source[2]])
            self.assertEqual(r['events'].count('submit_boundary'), 2)
            self.assertEqual(r['events'][-1], 'release_boundary')
            self.assertFalse(r['hardware_pixels_executed'])
