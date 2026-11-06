import ctypes as C
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from scripts import generate_m10v_icons as icon_generator

ROOT = Path(__file__).resolve().parents[1]


class Target(C.Structure):
    _fields_ = [('matrix', C.c_int16 * 9), ('post', C.c_int16 * 9), ('curves', (C.c_uint16 * 256) * 3)]


class Look(C.Structure):
    _fields_ = [(name, C.c_uint32) for name in ('magic', 'version', 'generation', 'film', 'exposure', 'status', 'frame')] + [('target', Target)]


class ThreeFilmNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        output = Path(cls.temp.name) / 'three-films.so'
        files = [
            'm10v_library.c', 'film_5207.c', 'film_harman.c', 'film_curated.c', 'film_newstocks.c',
            'film_style_filters_0.c', 'film_style_filters_1.c', 'film_d76_0.c',
            'film_d76_1.c', 'halation_core.c', 'm10v_isp_native_look.c', 'm10v_isp_frame_color.c',
            'm10v_isp_multiaxis.c',
        ]
        subprocess.run([
            'clang', '-shared', '-fPIC', '-O2', '-Wall', '-Wextra', '-Werror',
            '-I', str(ROOT / 'native/gr3'),
            *[str(ROOT / 'native/gr3' / name) for name in files], '-o', str(output),
        ], check=True, capture_output=True)
        cls.lib = C.CDLL(str(output))
        cls.lib.m10v_isp_native_look_prepare.argtypes = [C.POINTER(Look), C.c_uint32, C.c_uint32, C.c_uint32]
        cls.lib.m10v_isp_native_look_prepare.restype = C.c_int

    def prepare(self, film):
        look = Look()
        self.assertEqual(self.lib.m10v_isp_native_look_prepare(C.byref(look), film, 0, 71), 1)
        return look

    def test_shd50_uses_independent_red_weak_monochrome_curve(self):
        reference = json.loads((ROOT / 'native/gr3/three-film-reference.json').read_text())
        shd = self.prepare(328).target
        expected_luma = reference['shd50']['luma_weights_q13']
        self.assertEqual(list(shd.matrix), expected_luma * 3)
        self.assertEqual(list(shd.post), [512, 0, 0, 0, 512, 0, 0, 0, 512])
        expected_curve = [value * 64 for value in reference['shd50']['curve_u8']]
        self.assertEqual([list(channel) for channel in shd.curves], [expected_curve] * 3)
        self.assertLess(expected_luma[0], expected_luma[2])
        self.assertLess(expected_luma[2], expected_luma[1])
        self.assertEqual(expected_curve[-1], 16320)

    def test_rainbow_films_reuse_colorplus_native_base_exactly(self):
        colorplus = bytes(self.prepare(323).target)
        self.assertEqual(bytes(self.prepare(329).target), colorplus)
        self.assertEqual(bytes(self.prepare(330).target), colorplus)

    def test_new_ids_reject_exposure_variants_and_unknown_neighbors(self):
        for film in (328, 329, 330):
            look = Look()
            self.assertEqual(self.lib.m10v_isp_native_look_prepare(C.byref(look), film, 1, 71), 0)
        for film in (331, 332):
            look = Look()
            self.assertEqual(self.lib.m10v_isp_native_look_prepare(C.byref(look), film, 0, 71), 0)

    def test_three_film_icon_artifacts_do_not_require_official_firmware(self):
        build = getattr(icon_generator, 'three_film_artifacts', None)
        self.assertTrue(callable(build))
        artifacts = build()
        self.assertEqual([row['id'] for row, _, _ in artifacts], [328, 329, 330])
        self.assertEqual([len(compact.tobytes()) for _, compact, _ in artifacts], [6400] * 3)
        self.assertEqual([large.size for _, _, large in artifacts], [(160, 160)] * 3)


if __name__ == '__main__':
    unittest.main()
