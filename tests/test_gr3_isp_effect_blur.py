"""Offline frequency study and real ARM table selection; no pixel claims."""
import importlib
import hashlib
import json
import math
import struct
import unittest

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM
from unicorn import arm_const as A
from scripts import build_gr3_digital_hdf as hdf


class BlurTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blur = importlib.import_module('scripts.build_gr3_isp_effect_blur')
        cls.rom = hdf.official_rtos()
        cls.exports = {name: 0x54100000+4*i for i, name in enumerate(hdf.HELPERS)}

    def test_all_combinations_have_explicit_native_identity_and_q10_response(self):
        self.assertEqual(len(self.blur.BLUR_ROWS), 36)
        identities = []
        for grade in range(4):
            base = (1024,)*11 if grade == 0 else hdf.ROWS[grade-1]
            for strength in range(1, 4):
                for radius in range(3):
                    value = self.blur.native_value(grade, strength, radius)
                    identities.append(value)
                    expected = self.blur.BLUR_ROWS[value-8]
                    self.assertEqual(expected[-2:], (1024,1024))
                    self.assertTrue(all(0 <= a <= b for a,b in zip(expected, base)))
        self.assertEqual(identities, list(range(8,44)))

    def test_soft_optical_response_preserves_core_and_coarse_contrast(self):
        for strength in range(3):
            for radius in range(3):
                row=self.blur.BLUR_ROWS[strength*3+radius]
                self.assertGreater(row[0],100)  # retain fine core; old strong Gaussian rounded to zero
                self.assertGreater(row[5],940) # >=92 percent contrast on coarse bands
                self.assertEqual(tuple(sorted(row)),row)
                if strength:self.assertTrue(all(a<=b for a,b in zip(row,self.blur.BLUR_ROWS[(strength-1)*3+radius])))
                if radius:self.assertTrue(all(a<=b for a,b in zip(row,self.blur.BLUR_ROWS[strength*3+radius-1])))

    def test_invalid_values_and_mode_are_rejected(self):
        for args in ((-1,1,0),(4,1,0),(0,0,0),(0,4,0),(0,1,3),(True,1,0),(0,1.,0)):
            with self.assertRaises(ValueError): self.blur.native_value(*args)
        for value in (1, None, 'yes'):
            with self.assertRaises(ValueError):
                hdf.build(0x54110000, self.exports, self.rom, pure_isp_blur=value)

    def test_default_exactly_preserved_and_optional_budget_table_manifest(self):
        for shared in (False, True):
            for cache in (False, True):
                args = dict(rtos=self.rom, shared_recipe=shared, ui_cache=cache)
                old, old_m = hdf.build(0x54110000, self.exports, **args)
                explicit, explicit_m = hdf.build(0x54110000, self.exports, pure_isp_blur=False, **args)
                self.assertEqual((old,old_m), (explicit,explicit_m))
                # Captured from the unmodified builder before this extension.
                expected_code = ('438a3d94653d2bf34fe15a4d16208c0f214a67bc9f7a8cff95a59b09be9518bb'
                                 if shared else 'df0768219528d8df1f8b1a10e34c27500547f9b1d92c7278355af7aed3a45073')
                expected_manifest = {
                    (False,False): '3a6c92a9110806834b6f89ead55d69eb077762aad3de287ba8550ca1becc3d3f',
                    (False,True): '0cb09548c6c144071c06d4588356b69299c01a414fcb8711c094ac5fc2d5386a',
                    (True,False): '6858332c9444ff619cf32873aad1e21beef342f0fcd31b3dc81e8c2c6b5f8bfc',
                    (True,True): 'c9fb5277cd10ed4d699c00199fb4776c9a2eb921a58aea71bb240e49a03ebfc6'}[shared,cache]
                self.assertEqual(hashlib.sha256(old).hexdigest(), expected_code)
                self.assertEqual(hashlib.sha256(json.dumps(old_m,sort_keys=True).encode()).hexdigest(), expected_manifest)
                self.assertLessEqual(len(old),1024)
                self.assertNotIn('optional_blur',old_m)
                new, manifest = hdf.build(0x54110000,self.exports,pure_isp_blur=True,**args)
                self.assertLessEqual(len(new),2048)
                self.assertEqual(manifest['pixel_loops'],0)
                self.assertEqual(manifest['mutable_global_bytes'],0)
                self.assertEqual(manifest['ui_cache'],cache)
                self.assertEqual(manifest['shared_recipe'],shared)
                for a,b in zip(old_m['patches'],manifest['patches']):
                    if a['name'] not in ('clarity_bound',): self.assertEqual(a,b)
                row_offset = manifest['rows']-manifest['base']
                self.assertEqual(new[:row_offset],old[:row_offset])
                self.assertEqual(struct.unpack_from('<33h',new,row_offset),tuple(n for row in hdf.ROWS for n in row))
                self.assertEqual(struct.unpack_from('<396h',new,row_offset+66),tuple(n for row in self.blur.BLUR_ROWS for n in row))
                self.assertEqual(manifest['optional_blur']['native_parameter_range'],[8,43])
                self.assertEqual(len(manifest['optional_blur']['rows']),36)
                self.assertEqual(next(p['replacement'] for p in manifest['patches'] if p['name']=='clarity_bound'),0xe358002f)

    def test_exact_rom_identity_is_still_required(self):
        damaged = bytearray(self.rom);damaged[0]^=1
        with self.assertRaisesRegex(ValueError,'exact'):
            hdf.build(0x54110000,self.exports,damaged,pure_isp_blur=True)

    def test_actual_arm_shim_selects_all_rows_preserving_other_registers_and_nzcvq(self):
        base = 0x54110000
        code, manifest = hdf.build(base,self.exports,self.rom,pure_isp_blur=True)
        u = Uc(UC_ARCH_ARM,UC_MODE_ARM)
        u.mem_map(base,0x10000);u.mem_write(base,code)
        u.mem_map(0x55000000,0x10000)
        shim = next(p['entry'] for p in manifest['patches'] if p['name']=='clarity_row')
        for row in range(48):
            for flags in (0,0xa8000000,0xf8000000):
                for n in range(13):u.reg_write(getattr(A,f'UC_ARM_REG_R{n}'),0x12340000+n)
                u.reg_write(A.UC_ARM_REG_R1,0x538f1fd4);u.reg_write(A.UC_ARM_REG_R3,22)
                u.reg_write(A.UC_ARM_REG_R8,row);u.reg_write(A.UC_ARM_REG_LR,0x55002000)
                u.reg_write(A.UC_ARM_REG_SP,0x5500f000);u.reg_write(A.UC_ARM_REG_CPSR,flags|0x13)
                before = [u.reg_read(getattr(A,f'UC_ARM_REG_R{n}')) for n in range(13)]
                u.emu_start(shim,0x5367c7e8,count=100)
                before[8] = 0x538f1fd4+22*row if row<=8 else manifest['rows']+22*(row-9)
                self.assertEqual([u.reg_read(getattr(A,f'UC_ARM_REG_R{n}')) for n in range(13)],before)
                self.assertEqual(u.reg_read(A.UC_ARM_REG_SP),0x5500f000)
                self.assertEqual(u.reg_read(A.UC_ARM_REG_LR),0x55002000)
                self.assertEqual(u.reg_read(A.UC_ARM_REG_CPSR)&0xf8000000,flags)
