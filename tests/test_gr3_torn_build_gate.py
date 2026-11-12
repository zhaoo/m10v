"""Native opt-in/allocation gates; not hardware performance evidence."""
import inspect, subprocess, tempfile, unittest
from pathlib import Path
from scripts import build_gr3_m10v_library as build
from scripts import build_gr3_torn_overlay as torn
ROOT=Path(__file__).resolve().parents[1]
class TornBuildGate(unittest.TestCase):
 def test_each_mask_splits_one_frame_with_a_single_matching_center_tear(self):
  width,height=torn.MASK_WIDTH,torn.MASK_HEIGHT
  plane=width*height
  stride=plane*3//2
  masks=torn._mask_blob()
  self.assertEqual(len(masks),stride*3)
  self.assertEqual(stride%64,0)
  self.assertEqual(width%64,0)
  self.assertLessEqual(len(masks),23040)
  for offset in range(0,len(masks),stride):
   self.assertEqual(masks[offset+plane:offset+stride],bytes([128])*(plane//2))
   left,right=[],[]
   for row in range(height):
    y=masks[offset+row*width:offset+(row+1)*width]
    gap=[x for x,value in enumerate(y) if value>=120]
    self.assertTrue(gap)
    self.assertEqual(gap,list(range(gap[0],gap[-1]+1)))
    self.assertGreaterEqual(len(gap),3)
    self.assertLessEqual(len(gap),8)
    self.assertTrue(.35*width<gap[0]<gap[-1]<.65*width)
    left.append(gap[0])
    right.append(gap[-1])
   self.assertGreaterEqual(max(left)-min(left),5)
   self.assertGreaterEqual(max(right)-min(right),5)
   self.assertGreater(len({b-a for a,b in zip(left,right)}),2)

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
