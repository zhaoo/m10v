"""Check final-BIN Still Make, RAW recipe isolation and MakerNote output."""
import json
import os
from pathlib import Path
import struct
import unittest

from tests import test_gr3_film_pipeline_current as film_pipeline
from tests.test_gr3_isp_base import StockISP
from scripts.probe_gr3_raw_guides_adj import ROM, decode, sha
from unicorn import UC_HOOK_CODE
from unicorn import arm_const as arm


class DeliveredRawIspTests(unittest.TestCase):
    make = film_pipeline.CurrentFilmPipelineTests.make

    @classmethod
    def setUpClass(cls):
        cls.artifacts = {}
        for model in ('gr3', 'gr3x'):
            value = os.environ.get('M10V_RAW_ISP_' + model.upper())
            if not value:
                raise unittest.SkipTest('set both audited RAW candidate directories')
            folder = Path(value)
            manifest = json.loads((folder / 'M10V-runtime-manifest.json').read_text())
            receipt = json.loads((folder / 'M10V-build-receipt.json').read_text())
            binary = folder / receipt['filename']
            image = decode(binary)
            assert sha(binary.read_bytes()) == receipt['candidate_sha256']
            start = manifest['base'] - ROM
            assert sha(image[start:start + manifest['code_bytes']]) == manifest['code_sha256']
            cls.artifacts[model] = (manifest, image)

    def test_owned_raw_make_and_writer_follow_the_processed_film(self):
        for model, (manifest, image) in self.artifacts.items():
            with self.subTest(model=model):
                symbols = manifest['symbols']
                camera = StockISP(image)
                recipe = camera.alloc(manifest['capture_lifecycle']['owner']['storage']['extended_recipe_bytes'])
                camera.w32(recipe, 0x53d0fc90)
                camera.w32(recipe + 0x4778, 0x31545653)
                obj = camera.cursor
                camera.make(11, stage=0)
                frame = obj + 0x1400
                si, = struct.unpack('<I', camera.u.mem_read(frame + 0x82d0, 4))
                camera.w32(recipe + 0x44c8, si)
                camera.u.reg_write(arm.UC_ARM_REG_R0, recipe)
                camera.u.reg_write(arm.UC_ARM_REG_R4, recipe)
                camera.u.emu_start(0x5350eb10, 0x5350eb38, count=100)
                pool = camera.alloc(0x218)
                camera.w32(0x55345328, pool)
                camera.w32(pool + 0x20, 0x74280)
                camera.w32(pool + 0x88, si)
                writes = []

                def writer(u, address, size, context):
                    writes.append((address, u.reg_read(arm.UC_ARM_REG_R2)))
                    u.reg_write(arm.UC_ARM_REG_PC, u.reg_read(arm.UC_ARM_REG_LR))

                for address in (0x535d02c8, 0x535c780c):
                    camera.u.hook_add(UC_HOOK_CODE, writer, begin=address, end=address)

                def run(name, *args):
                    camera.call(symbols[name], *args)
                    return camera.u.reg_read(arm.UC_ARM_REG_R0)

                # This layer checks the consumer independently of storage/UI
                # service doubles. The transport has its own stock-site test.
                output = {}
                for mode, film in ((9, 33), (12, 33), (12, 67), (12, 0), (10, 67), (11, 67)):
                    camera.w32(recipe + 0x18, mode)
                    run('m10v_isp_frame_raw_snapshot', recipe, mode, (0x1000 + film) if film else 0)
                    self.assertEqual(run('m10v_isp_frame_identity_code', si), 0)
                    self.make(camera, recipe, obj, frame)
                    self.assertEqual(bytes(camera.u.mem_read(si + 0x77c, 1)), b'\x0b')
                    gamma = bytes(camera.u.mem_read(frame + 0x4888, 2048))
                    if film in output:
                        self.assertEqual(output[film], gamma)
                    output[film] = gamma
                    expected = 0x1000 + film if mode == 12 and film else 0
                    self.assertEqual(run('m10v_isp_frame_identity_code', si), expected)
                    entry = manifest['appended_slots']['playback']['identity_hooks']['writer']
                    camera.call(entry, 0, 0, si)
                    self.assertEqual(writes[-1], (0x535d02c8, expected) if expected else (0x535c780c, si))
                self.assertNotEqual(output[33], output[67])
                self.assertNotEqual(output[33], output[0])

                # A tuning failure after a valid request cannot label the
                # neutral result as that film. The temporary tone still restores.
                camera.w32(recipe + 0x18, 12)
                self.assertEqual(run('m10v_isp_frame_raw_snapshot', recipe, 12, 0x1021), 1)
                gamma_at = obj + 0x17c
                gamma = bytes(camera.u.mem_read(gamma_at, 4))
                finish = symbols['m10v_isp_frame_recipe_finish']

                def no_gamma(u, address, size, context):
                    camera.w32(gamma_at, 0)

                hook = camera.u.hook_add(UC_HOOK_CODE, no_gamma, begin=finish, end=finish)
                self.make(camera, recipe, obj, frame)
                camera.u.hook_del(hook)
                camera.u.mem_write(gamma_at, gamma)
                self.assertEqual(run('m10v_isp_frame_identity_code', si), 0)
                self.assertEqual(bytes(camera.u.mem_read(si + 0x77c, 1)), b'\x0b')
