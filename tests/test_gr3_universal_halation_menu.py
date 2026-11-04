import unittest
from scripts.build_gr3_native_detail import build_detail
class UniversalHalationMenuTests(unittest.TestCase):
    def test_generic_modes_and_dedicated_halation_share_the_per_film_effects_rail(self):
        _,m=build_detail(0x54100000,{'m10v_detail_table':0x540b6000,'m10v_detail_control':0x540b6200},native_grain=True,sd_library=True,appended_slots=True,universal_halation=True,per_film_effects=True)
        for variant,ids in m['variant_ids'].items():
            for required in (18,19,20,21,23,24,25,26):self.assertIn(required,ids)
            self.assertEqual(22 in ids,variant not in ('halo','phoenix'))
        self.assertIn(4,m['sliders'])
        self.assertIn('Halation Mode',m['fields']);self.assertEqual(m['halation_modes'],['off','spill','streak'])
        self.assertEqual(m['mode_caption'],1137)
if __name__=='__main__':unittest.main()
