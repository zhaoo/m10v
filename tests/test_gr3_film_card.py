"""Bounds checks for the native cartridge rasterizer used by the camera view."""
import ctypes as C
import json,hashlib
from pathlib import Path
import subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
class FilmCardTests(unittest.TestCase):
 def test_square_card_contract(self):
  self.assertIn('M10V_CARD_WIDTH=128, M10V_CARD_HEIGHT=128', (ROOT/'native/gr3/m10v_film_card.h').read_text())
 def test_checked_in_artwork_matches_the_generator(self):
  from scripts.generate_m10v_film_cards import generate
  self.assertEqual((ROOT/'native/gr3/m10v_film_card_data.h').read_text(),generate())
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
  library=Path(cls.tmp.name)/'cards.so'
  subprocess.run(['clang','-shared','-fPIC','-O2','-Wall','-Wextra','-Werror',str(ROOT/'native/gr3/m10v_film_card.c'),'-o',str(library)],check=True,capture_output=True)
  cls.lib=C.CDLL(str(library));cls.draw=cls.lib.m10v_film_card_render
  cls.draw.argtypes=[C.POINTER(C.c_uint32),C.c_uint32,C.c_uint32,C.c_uint32];cls.draw.restype=C.c_int
 def test_all_films_fit_the_owned_buffer_and_emit_rgba(self):
  count=128*128;buffer=(C.c_uint32*(count+2))();pixels=C.cast(C.byref(buffer,4),C.POINTER(C.c_uint32))
  for film in list(range(1,79))+list(range(289,331)):
   for slot in range(10):
    buffer[0]=buffer[-1]=0x12345678
    self.assertEqual(self.draw(pixels,film,slot,slot==2),0)
    self.assertEqual((buffer[0],buffer[-1]),(0x12345678,0x12345678))
  self.draw(pixels,34,0,0) # Red Ektar label: RGBA, not blue ARGB bytes.
  at=(65*128+45)*4
  r,g,b,a=C.string_at(pixels,count*4)[at:at+4]
  self.assertGreater(r,g*2);self.assertGreater(r,b*2);self.assertEqual(a,255)
 def test_invalid_catalog_or_slot_does_not_touch_pixels(self):
  pixels=(C.c_uint32*(128*128))(*([0x12345678]*(128*128)))
  before=bytes(pixels)
  for film,slot in [(0,0),(79,0),(1,10),(0xffffffff,0)]:
   self.assertEqual(self.draw(pixels,film,slot,0),-1);self.assertEqual(bytes(pixels),before)
  self.assertEqual(self.draw(None,1,0,0),-1)

 def test_directory_cards_are_distinct_and_replace_reused_phoenix_pixels(self):
  directory=json.loads((ROOT/'web/gr3/film-directory.json').read_text())
  films=[film['id'] for group in directory['groups'] for film in group['films']]
  pixels=(C.c_uint32*(128*128))();fresh=(C.c_uint32*(128*128))()
  images={}
  for film in films:
   self.assertEqual(self.draw(pixels,67,0,0),0)
   self.assertEqual(self.draw(pixels,film,0,0),0,film)
   self.assertEqual(self.draw(fresh,film,0,0),0,film)
   self.assertEqual(bytes(pixels),bytes(fresh),film)
   digest=hashlib.sha256(bytes(pixels)).hexdigest()
   self.assertNotIn(digest,images,(film,images.get(digest)))
   images[digest]=film
  self.assertEqual(len(images),60)

 def test_custom_names_produce_distinct_bounded_art_without_builtin_alias(self):
  draw=self.lib.m10v_film_card_custom
  draw.argtypes=[C.POINTER(C.c_uint32),C.c_char_p,C.c_uint32,C.c_uint32]
  count=128*128;b=(C.c_uint32*(count+2))();p=C.cast(C.byref(b,4),C.POINTER(C.c_uint32))
  images=[]
  for name in [b'LOMO',b'Portra 400',b'12345678901234567890123',b'!@#$%^&*()_+-=[]{}:;,.?']:
   b[0]=b[-1]=0x12345678
   self.assertEqual(draw(p,name,1,1),0)
   self.assertEqual((b[0],b[-1]),(0x12345678,0x12345678));images.append(bytes(b))
  self.assertNotEqual(images[0],images[1])
  self.draw(p,33,1,1);self.assertNotEqual(images[0],bytes(b))
  before=bytes(b)
  for name in [None,b'',b'A'*24]:
   self.assertEqual(draw(p,name,1,1),-1);self.assertEqual(bytes(b),before)
