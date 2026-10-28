"""The camera diagnostic must reach the separately built trace modules."""
import tempfile
import unittest
from pathlib import Path

from scripts.build_gr3_save_trace import build as build_save
from scripts.build_gr3_module_dispatch_trace import build as build_module

ROOT = Path(__file__).resolve().parents[1]


class BorderDebugCompileTests(unittest.TestCase):
    def test_both_trace_components_compile_border_diagnostics(self):
        rom = ROOT / 'builds/gr3-extension-validation/official-rtos.bin'
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            plain, plain_manifest = build_save(root / 'plain-save', 0x540e0000, rtos=rom)
            active, active_manifest = build_save(root / 'border-save', 0x540e0000,
                                                 rtos=rom, border_debug=True)
            self.assertFalse(plain_manifest['border_debug'])
            self.assertTrue(active_manifest['border_debug'])
            self.assertNotEqual(plain, active)

            kwargs = dict(rtos=rom, take=active_manifest['exports']['m10v_save_trace_recipe_take'],
                          batch=0x540c0000)
            plain, plain_manifest = build_module(root / 'plain-module', 0x540f0000,
                                                 active_manifest['exports']['m10v_save_trace_recipe_mark'],
                                                 **kwargs)
            active, active_manifest = build_module(root / 'border-module', 0x540f0000,
                                                   active_manifest['exports']['m10v_save_trace_recipe_mark'],
                                                   border_debug=True, **kwargs)
            self.assertFalse(plain_manifest['border_debug'])
            self.assertTrue(active_manifest['border_debug'])
            self.assertNotEqual(plain, active)


if __name__ == '__main__':
    unittest.main()
