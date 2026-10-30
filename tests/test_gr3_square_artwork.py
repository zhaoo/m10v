"""Shared identity, compact-specific raster and generated asset contracts."""
import json,unittest,tempfile
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from scripts.generate_m10v_icons import ROOT,artwork,box_icon

class SquareArtworkTests(unittest.TestCase):
 def test_build_uses_accepted_custom_pixels_without_host_font_rendering(self):
  from scripts.generate_m10v_film_cards import custom_icon
  with patch('PIL.ImageFont.truetype',side_effect=AssertionError('build must not rerasterize text')):
   self.assertEqual(custom_icon(),(ROOT/'native/gr3/m10v_custom_icon.rgba').read_bytes())
 def test_pinned_custom_raster_rejects_corrupt_pixels_and_wrong_extent(self):
  import scripts.generate_m10v_film_cards as cards
  original=json.loads((ROOT/'native/gr3/m10v_square_icon_raster.json').read_text())
  for changes in ({'width':39},{'custom_icon_sha256':'0'*64},{'font_sha256':'0'*64},{'custom_icon_base64':'AA=='}):
   with tempfile.TemporaryDirectory() as folder:
    target=Path(folder)/'native/gr3';target.mkdir(parents=True)
    (target/'m10v_square_icon_raster.json').write_text(json.dumps({**original,**changes}))
    with patch.object(cards,'ROOT',Path(folder)):
     with self.assertRaises(ValueError):cards.custom_icon()
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
