"""Instax provenance and packed recipe contracts; no camera fidelity claim."""
import json, unittest
from pathlib import Path
from scripts.verify_gr3_extra_films_reference import verify

ROOT=Path(__file__).resolve().parents[1]

class InstaxTests(unittest.TestCase):
 def test_quantized_recipe_and_reference_are_verifiable_and_honest(self):
  ref=verify(ROOT)
  spec=ref['stocks'][-1];profile=ref['native_profiles_full'][-1]
  self.assertEqual(spec['id'],317)
  self.assertEqual(profile['film_id'],317)
  self.assertEqual(profile['holdout']['samples'],32768)
  self.assertFalse(profile['gate']['eligible'])
  self.assertFalse(ref['camera_validated'])
  p=ref['parameters']['instax']
  self.assertEqual((p['official_iso'],p['model_iso'],p['exposure_kelvin']),(800,1000,5500))
  self.assertFalse(p['border'])
  self.assertFalse(p['camera_verified'])
  self.assertIn('deliberately compensates',p['iso_note'])
  self.assertEqual(p['official_datasheet']['sha256'],'c1d4963f6e1b6c58449092754742048ec0fb55930f138ad5e892ebc0fc2c8923')
  model='third_party/spectral-film-lut/src/spectral_film_lut/reversal_film/fuji_instax_color.py'
  self.assertIn(model,ref['files'])
  self.assertIn('third_party/spectral-film-lut/LICENSE',ref['files'])
