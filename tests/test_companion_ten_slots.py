import ctypes as C,json,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class TenSlots(unittest.TestCase):
 def test_latest_sixty_film_ids_parse_and_future_id_is_rejected(self):
  p={'protocol':1,'requestId':'11'*16,'bootId':'22'*16,'baseRevision':'33'*32,'catalogHash':'44'*32,'rendererHash':'55'*32,'activateSlot':None}
  self.lib.parse_ten_film.argtypes=[C.c_char_p,C.c_uint,C.c_uint]
  for film in range(327,331):
   p['patch']=[{'slot':9,'filmId':film,'grain':1}];raw=json.dumps(p).encode()
   with self.subTest(film=film):self.assertEqual(self.lib.parse_ten_film(raw,len(raw),film),0)
  p['patch']=[{'slot':9,'filmId':331}];raw=json.dumps(p).encode()
  self.assertNotEqual(self.lib.parse_ten(raw,len(raw)),0)

 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup);out=Path(cls.tmp.name)/'ten.dylib'
  files=['native/companion/auth.c','native/companion/json.c','native/companion/operations.c','native/companion/transaction.c','native/gr3/m10v_library.c','native/gr3/halation_core.c','native/gr3/film_5207.c','native/gr3/film_harman.c','native/gr3/film_curated.c','native/gr3/film_newstocks.c','native/gr3/film_style_filters_0.c','native/gr3/film_style_filters_1.c','native/gr3/film_d76_0.c','native/gr3/film_d76_1.c','tests/support_companion_ten.c']
  result=subprocess.run(['clang','-O2','-Wall','-Wextra','-Werror','-DM10V_UNIVERSAL_HALATION=1','-DM10V_APPENDED_SLOTS=1','-dynamiclib',*[str(ROOT/p) for p in files],'-o',str(out)],capture_output=True,text=True)
  if result.returncode:raise AssertionError(result.stderr[:2500])
  cls.lib=C.CDLL(str(out));cls.lib.test_ten_case.argtypes=[C.c_uint];cls.lib.parse_ten.argtypes=[C.c_char_p,C.c_uint]
 def test_last_slot_changes_revision_and_single_commit_preserves_others(self):
  for case in range(11):
   with self.subTest(case=case):self.assertEqual(self.lib.test_ten_case(case),0)
 def test_parse_slot_nine_and_reject_out_of_range(self):
  p={'protocol':1,'requestId':'11'*16,'bootId':'22'*16,'baseRevision':'33'*32,'catalogHash':'44'*32,'rendererHash':'55'*32,'patch':[{'slot':9,'filmId':321,'grain':2}],'activateSlot':None}
  raw=json.dumps(p).encode();self.assertEqual(self.lib.parse_ten(raw,len(raw)),0)
  p['patch'][0]['slot']=10;raw=json.dumps(p).encode();self.assertNotEqual(self.lib.parse_ten(raw,len(raw)),0)

 def test_full_ten_slot_envelope_fits_bounded_parser(self):
  params={'grain':2,'haloGain':1,'haloSpread':3,'haloThreshold':5,'haloProfile':4,'filmExposure':0,'charmeraColor':0}
  p={'protocol':1,'requestId':'11'*16,'bootId':'22'*16,'baseRevision':'33'*32,'catalogHash':'44'*32,'rendererHash':'55'*32,'patch':[{'slot':i,'filmId':321,**params} for i in range(10)],'activateSlot':None}
  raw=json.dumps(p).encode();self.assertEqual(self.lib.parse_ten_full(raw,len(raw)),0)

 def test_readonly_fields_rejected_by_parser(self):
  p={'protocol':1,'requestId':'11'*16,'bootId':'22'*16,'baseRevision':'33'*32,'catalogHash':'44'*32,'rendererHash':'55'*32,'activateSlot':None}
  for field in ['grainSize','leakGain','leakPosition','leakSpread','leakVariation']:
   p['patch']=[{'slot':9,'filmId':321,field:0}];raw=json.dumps(p).encode()
   with self.subTest(field=field):self.assertNotEqual(self.lib.parse_ten(raw,len(raw)),0)

 def test_latest_c41_films_parse_without_accepting_unknown_future_ids(self):
  p={'protocol':1,'requestId':'11'*16,'bootId':'22'*16,'baseRevision':'33'*32,'catalogHash':'44'*32,'rendererHash':'55'*32,'activateSlot':None}
  for film in range(322,327):
   p['patch']=[{'slot':9,'filmId':film,'grain':1}];raw=json.dumps(p).encode()
   self.lib.parse_ten_film.argtypes=[C.c_char_p,C.c_uint,C.c_uint]
   with self.subTest(film=film):self.assertEqual(self.lib.parse_ten_film(raw,len(raw),film),0)
  p['patch']=[{'slot':9,'filmId':331}];raw=json.dumps(p).encode();self.assertNotEqual(self.lib.parse_ten(raw,len(raw)),0)
