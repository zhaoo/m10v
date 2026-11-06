"""Native-only rainbow film freeze and immutable renderer contracts."""
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from scripts.build_gr3_m10v_library import FLAGS, link_object
from scripts import build_gr3_isp_effect_render as render
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM
from unicorn import arm_const as A

ROOT = Path(__file__).resolve().parents[1]
BASE, RECIPE, OFFSET, OUT, SI = 0x541D0000, 0x55010000, 0x5778, 0x55009000, 0x55030000
SHOT = RECIPE + OFFSET


class RainbowShotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        folder = Path(cls.temp.name)
        src, obj = folder / 'rainbow-shot.c', folder / 'rainbow-shot.o'
        src.write_text(f'''#include "{ROOT / 'native/gr3/m10v_isp_effects_state.c'}"
#include "{ROOT / 'native/gr3/m10v_library.h'}"
int m10v_library_valid(const m10v_library_state *s) {{ return s && s->magic == 0x5630314du; }}
#include "{ROOT / 'native/gr3/m10v_isp_effects_shot.c'}"
void rainbow_test_seed(uint32_t recipe,uint32_t si,uint32_t film,uint32_t generation,uint32_t identity) {{
 m10v_isp_recipe_color *c=(void *)(uintptr_t)(recipe+M10V_SAVE_COLOR_OFFSET);
 for(uint32_t i=0;i<sizeof(*c);i++)((uint8_t *)c)[i]=0;
 c->magic=M10V_ISP_RECIPE_COLOR_MAGIC;c->version=1;c->bytes=sizeof(*c);c->sequence=7;
 c->selected_tone=12;c->state.magic=0x5630314du;c->state.sequence=7;c->state.slots[m10v_tone_slot(12)].film=(uint16_t)film;
 m10v_film_identity *p=(void *)(uintptr_t)(si+M10V_FILM_SI_BYTES);
 p->generation=generation;p->code=identity;p->check=~identity^generation;p->magic=M10V_FILM_IDENTITY_MAGIC;
}}
''')
        subprocess.run([shutil.which('clang'), *FLAGS, '-DM10V_PURE_ISP_EFFECTS=1',
            '-DM10V_ISP_EFFECTS_SHOT_OFFSET=' + hex(OFFSET), '-c', str(src), '-o', str(obj)],
            check=True, capture_output=True)
        exports = tuple('m10v_isp_effects_shot_' + name for name in
            ('reserve', 'freeze', 'read', 'plan', 'complete')) + ('rainbow_test_seed',)
        cls.code, cls.symbols = link_object(obj.read_bytes(), BASE, {}, prefix='m10v_settings_',
            omitted_exports=('m10v_settings_open', 'm10v_settings_key'), additional_exports=exports)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        self.u.mem_map(BASE, 0x10000); self.u.mem_write(BASE, self.code)
        self.u.mem_map(0x55000000, 0x100000); self.u.mem_map(0x55300000, 0x100000)
        self.put(RECIPE, 0x53D0FC90); self.put(RECIPE + 0x4778, 0x31545653)
        self.put(RECIPE + 0x44C8, SI); self.u.mem_write(SI + 0x77C, b'\x0c')
        self.u.mem_write(SI + 0xC8, b'\x00')
        manager = 0x55350000
        self.put(0x55345328, manager); self.put(manager + 0x20, 0x74280); self.put(manager + 0x88, SI)
        self.call('m10v_isp_effects_shot_reserve', RECIPE)

    def put(self, address, *values):
        self.u.mem_write(address, struct.pack('<' + 'I' * len(values), *values))

    def word(self, address):
        return struct.unpack('<I', self.u.mem_read(address, 4))[0]

    def call(self, symbol, *args):
        for index in range(4):
            self.u.reg_write(getattr(A, f'UC_ARM_REG_R{index}'), args[index] if index < len(args) else 0)
        self.u.reg_write(A.UC_ARM_REG_SP, 0x550FD000); self.u.reg_write(A.UC_ARM_REG_LR, 0x550FF000)
        self.u.emu_start(self.symbols[symbol], 0x550FF000, count=100000)
        self.assertEqual(self.u.reg_read(A.UC_ARM_REG_PC), 0x550FF000)
        return self.u.reg_read(A.UC_ARM_REG_R0)

    def seed(self, film, generation, identity=None):
        self.call('rainbow_test_seed', RECIPE, SI, film, generation)
        if identity is not None:
            self.put(SI + 0x74270 + 8, identity)
            self.put(SI + 0x74270 + 12, ~identity & 0xFFFFFFFF ^ generation)

    def test_four_variants_freeze_once_and_pegasus_ignores_exif_rotation(self):
        for film, kind in ((329, 1), (330, 2)):
            variants = set()
            for generation in range(4):
                self.call('m10v_isp_effects_shot_reserve', RECIPE)
                self.seed(film, generation, 0x1000 + film)
                self.u.mem_write(SI + 0xC8, bytes((generation,)))
                self.assertEqual(self.call('m10v_isp_effects_shot_freeze', RECIPE), 1)
                descriptor = self.word(SHOT + 92)
                self.assertTrue(m10v_rainbow_valid(descriptor))
                self.assertEqual(m10v_rainbow_kind(descriptor), kind)
                self.assertEqual(m10v_rainbow_strength(descriptor), 1)
                variants.add(m10v_rainbow_variant(descriptor))
                frozen = descriptor
                self.u.mem_write(SI + 0xC8, b'\x03')
                self.assertEqual(self.call('m10v_isp_effects_shot_freeze', RECIPE), 1)
                self.assertEqual(self.word(SHOT + 92), frozen)
            self.assertEqual(variants, set(range(4)))

    def test_wrong_or_missing_identity_rejects_rainbow_without_cpu_fallback(self):
        for identity in (0, 0x1000 + 328, 0x1000 + 330):
            self.call('m10v_isp_effects_shot_reserve', RECIPE)
            self.seed(329, 9, identity)
            self.assertEqual(self.call('m10v_isp_effects_shot_freeze', RECIPE), 0)
            self.assertEqual(self.word(SHOT + 8), 2)
            self.assertEqual(self.word(SHOT + 92), 0)

    def test_workspace_and_completion_include_dedicated_rainbow_bit(self):
        self.seed(329, 5, 0x1000 + 329)
        self.assertEqual(self.call('m10v_isp_effects_shot_freeze', RECIPE), 1)
        self.assertEqual(self.call('m10v_isp_effects_shot_plan', RECIPE, SI, 162, 24, 0), 1)
        self.assertEqual(self.word(SHOT + 56), 8448)
        self.assertEqual(self.call('m10v_isp_effects_shot_complete', RECIPE, SI, 8), 1)
        self.assertEqual(self.word(SHOT + 68), 8)


def m10v_rainbow_valid(value):
    return value & 0xFFC00000 == 0x52400000


def m10v_rainbow_kind(value):
    return value & 3


def m10v_rainbow_variant(value):
    return value >> 4 & 3


def m10v_rainbow_strength(value):
    return value >> 12 & 255


class RainbowRenderBindingTests(unittest.TestCase):
    def test_builder_requires_all_48_immutable_signed_component_fields(self):
        source = (ROOT / 'scripts/build_gr3_isp_effect_render.py').read_text()
        self.assertIn("'rainbows'", source)
        self.assertIn('m10v_render_rainbows[2][4][3][2]', source)
        self.assertIn('rainbow KOLOR/Pegasus signed Y/Cb/Cr', source)
        renderer = (ROOT / 'native/gr3/m10v_isp_effects_render.c').read_text()
        self.assertIn('m10v_isp_rainbow_valid', renderer)
        self.assertIn('for(uint32_t component=0;component<3;component++)', renderer)
        self.assertIn('for(uint32_t sign=0;sign<2;sign++)', renderer)
        self.assertNotIn('CPU fallback', renderer)


if __name__ == '__main__':
    unittest.main()
