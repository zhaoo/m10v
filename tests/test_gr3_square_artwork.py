"""Shared identity, compact-specific raster and generated asset contracts."""
import json,unittest
from PIL import Image
from scripts.generate_m10v_icons import ROOT,artwork,box_icon

class SquareArtworkTests(unittest.TestCase):
 def test_reference_families_have_distinct_content_and_full_identity(self):
  refs=[(34,'EKTAR',0),(35,'GOLD',1),(37,'PORTRA',2),(33,'800T',3),(314,'ACROS II',4),(76,'AEROCHROME',5)]
  for film,title,motif in refs:
   self.assertEqual((artwork(title,film)[1],artwork(title,film)[-1]),(title,motif))
   small=box_icon(title,film);large=box_icon(title,film,160)
   self.assertEqual(small.size,(40,40));self.assertEqual(large.size,(160,160))
   self.assertNotEqual(small.tobytes(),large.resize((40,40),Image.Resampling.LANCZOS).tobytes())
 def test_all_generated_assets_are_square_and_coverage_is_exact(self):
  catalog=json.loads((ROOT/'web/gr3/film-icons/catalog.json').read_text())
  expected=set(range(1,79))|set(range(289,306))|set(range(309,318))
  self.assertEqual({r['id'] for r in catalog},expected)
  for row in catalog:
   with Image.open(ROOT/f"web/gr3/film-icons/{row['id']:02d}.png") as im:self.assertEqual(im.size,(40,40))
   with Image.open(ROOT/f"web/gr3/film-icons/{row['id']:02d}-large.png") as im:self.assertEqual(im.size,(160,160))
   self.assertIn('?v=',row['icon_url']);self.assertIn('?v=',row['icon_compact_url'])
   self.assertEqual(row['artwork_revision'],'classic-square-v1')
