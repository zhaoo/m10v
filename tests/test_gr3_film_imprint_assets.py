import importlib.util
import tempfile
import unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
class ImprintAssetTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  source=ROOT/'scripts/build_gr3_film_imprints.py'
  if not source.exists():raise AssertionError('ISP imprint resource compiler is missing')
  spec=importlib.util.spec_from_file_location('imprints',source);cls.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.module)
 def test_transparent_pixels_have_zero_weight_in_both_isp_fields(self):
  rgba=np.full((2,64,4),255,dtype=np.uint8);rgba[:,:,3]=0
  self.assertEqual(self.module.pack_imprint(rgba),(bytes(192),bytes(192)))
 def test_primary_colors_route_to_the_correct_unsigned_weight_fields(self):
  cases=[((255,0,0),76,(0,255),(86,0)),
         ((0,255,0),150,(0,0),(169,214)),
         ((0,0,255),29,(255,0),(0,41))]
  for rgb,y,pos,neg in cases:
   rgba=np.zeros((2,64,4),np.uint8);rgba[:]=(*rgb,255)
   positive,negative=self.module.pack_imprint(rgba)
   self.assertEqual((positive[0],negative[0]),(0,y))
   self.assertEqual(tuple(positive[128:130]),pos)
   self.assertEqual(tuple(negative[128:130]),neg)
 def test_all_styles_have_two_sharper_sensor_coordinate_fields(self):
  with tempfile.TemporaryDirectory() as td:
   manifest,raw=self.module.build(Path(td)/'imprints')
   self.assertEqual(len(raw),3268608);self.assertEqual(len(manifest['assets']),14)
   self.assertEqual(manifest['coordinates'],'sensor-fixed; EXIF rotates photo and print together')
   self.assertEqual([(a['style'],a['polarity']) for a in manifest['assets']],
                    [(style,sign) for style in range(1,8) for sign in ('positive','negative')])
   self.assertFalse(manifest['camera_tested']);self.assertFalse(manifest['exact_rgb_screen'])
   for a in manifest['assets']:
    self.assertEqual(a['offset']%64,0)
    self.assertEqual(a['length'],a['stride']*a['height']*3//2)
 def test_sensor_geometry_preserves_circle_proportions_at_full_resolution(self):
  with tempfile.TemporaryDirectory() as td:
   m,raw=self.module.build(Path(td)/'imprints')
   self.assertEqual({(a['width'],a['height'],a['stride']) for a in m['assets']},{(512,304,512)})
if __name__=='__main__':unittest.main()
