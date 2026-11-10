"""Native opt-in/allocation gates; not hardware performance evidence."""
import inspect, subprocess, tempfile, unittest
from pathlib import Path
from scripts import build_gr3_m10v_library as build
ROOT=Path(__file__).resolve().parents[1]
class TornBuildGate(unittest.TestCase):
 def test_builder_rejects_torn_without_exact_owned_gr3_pipeline(self):
  self.assertIn('torn_overlay',inspect.signature(build.build).parameters)
  with tempfile.TemporaryDirectory() as d:
   for opts in ({},{'camera_model':'gr3x'},{'torn_overlay':1}):
    with self.subTest(opts=opts),self.assertRaisesRegex(ValueError,'torn'):
     build.build(d,**{'torn_overlay':True,**opts})
 def test_recipe_extension_is_separate_and_opt_in(self):
  for enabled,wanted in ((0,0x57d8),(1,0x57f8)):
   code='#include "m10v_save_trace.h"\n_Static_assert(M10V_SAVE_RECIPE_EXTENDED_BYTES=='+str(wanted)+',"recipe extent");\n'
   p=subprocess.run(['clang','-x','c','-fsyntax-only','-DM10V_PURE_ISP_EFFECTS=1',f'-DM10V_TORN_ENABLED={enabled}','-I',str(ROOT/'native/gr3'),'-'],input=code,text=True,capture_output=True)
   self.assertEqual(p.returncode,0,p.stderr)
