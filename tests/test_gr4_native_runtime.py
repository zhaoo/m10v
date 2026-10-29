import tempfile
import unittest
from pathlib import Path
class Gr4NativeRuntimeTests(unittest.TestCase):
    def test_gr4_runtime_links_every_ui_and_capture_entry(self):
        from scripts.build_gr4_m10v_library import build
        rtos=Path('data/research/gr4/RTOS.bin').read_bytes()
        with tempfile.TemporaryDirectory() as d:
            m=build(Path(d),0x54400000,rtos=rtos)
            code=(Path(d)/'m10v-library-arm.bin').read_bytes()
            self.assertEqual(len(code),m['code_bytes'])
            for name in ['m10v_capture_library','m10v_chain_capture','m10v_camera_library_load',
                'm10v_sd_camera_item','m10v_settings_controller_factory','m10v_detail_control','m10v_menu_confirm']:
                self.assertGreaterEqual(m['symbols'][name],m['base'])
                self.assertLess(m['symbols'][name],m['base']+len(code))
            for name in ['m10v_camera_library_preview','m10v_camera_library_preview_init','m10v_camera_library_preview_clear','m10v_camera_library_custom_profile','m10v_settings_controller_card_directory']:
                self.assertNotIn(name,m['symbols']) # GR III-only APIs must not leak into GR IV.
            self.assertEqual(m['film_count'],78)
            self.assertEqual(m['carrier_tones'],[36,37,38,39,40])
            self.assertTrue(m['settings_menu']['patches'])
            self.assertTrue(m['detail']['patches'])
