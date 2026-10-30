"""Execute real ARM native look + original ISP writer; pixels require camera."""
import hashlib,json,random,struct,tempfile,unittest
from unicorn import UC_PROT_READ,UC_PROT_EXEC,UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_SP
from tests.test_gr3_isp_base import StockISP,ROOT
from scripts.build_gr3_isp_native_look import build,profiles,encode_curve_deltas,decode_curve_deltas

class NativeLookTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.rom=(ROOT/'builds/gr3-extension-validation/official-rtos.bin').read_bytes()
  with tempfile.TemporaryDirectory() as d:cls.code,cls.manifest=build(d)
 def fixture(self,tone=11,extra=None):
  e=StockISP(self.rom);e.make(tone,extra=extra)
  at=self.manifest['base'];e.u.mem_map(at,65536);e.u.mem_write(at,self.code);e.u.mem_protect(at,65536,UC_PROT_READ|UC_PROT_EXEC)
  gamma=struct.unpack('<I',e.u.mem_read(0x6000017c,4))[0]
  return e,e.alloc(1600),0x60001400,gamma
 def call(self,e,name,*args):
  e.call(self.manifest['symbols']['m10v_isp_native_look_'+name],*args);return e.u.reg_read(UC_ARM_REG_R0)
 def test_phoenix_ei120_has_an_independent_native_profile_and_matching_generation(self):
  e,s,f,g=self.fixture()
  self.assertEqual(self.call(e,'prepare',s,67,0,12),1)
  standard=bytes(e.u.mem_read(s+28,1572))
  self.assertEqual(self.call(e,'prepare',s,67,1,13),1)
  self.assertNotEqual(bytes(e.u.mem_read(s+28,1572)),standard)
  self.assertEqual(self.call(e,'apply',s,g,f,0),1)
  self.assertEqual(self.call(e,'matches',s,67,1,13),1)
  self.assertEqual(self.call(e,'matches',s,67,0,13),0)
  self.assertEqual(self.call(e,'prepare',s,67,2,14),0)
 def test_all_films_and_red_exposures_apply_owned_frame_without_cached_mutation(self):
  for film,exposure in [(f,0) for f in list(range(33,79))+list(range(290,297))+[317]]+[(68,1),(68,2)]:
   with self.subTest(film=film,exposure=exposure):
    e,s,f,g=self.fixture();before=bytes(e.u.mem_read(f,0x9000));cached=bytes(e.u.mem_read(g,0x3240));obj=bytes(e.u.mem_read(0x60000000,0x400))
    self.assertEqual(self.call(e,'prepare',s,film,exposure,41),1)
    self.assertEqual(self.call(e,'matches',s,film,exposure,41),0)
    self.assertEqual(self.call(e,'apply',s,g,f,0),1)
    self.assertEqual(self.call(e,'matches',s,film,exposure,41),1)
    self.assertEqual(self.call(e,'matches',s,film,exposure,42),0)
    after=bytes(e.u.mem_read(f,0x9000));diff=[i for i,(a,b) in enumerate(zip(before,after)) if a!=b]
    self.assertTrue(diff)
    self.assertTrue(all(0x140<=i<0x152 or 0x12a0<=i<0x12b2 or 0x2688<=i<0x5088 or ((film in (66,67) or film>=69) and 0x1c0<=i<0x12a0) for i in diff))
    self.assertEqual(bytes(e.u.mem_read(g,0x3240)),cached)
    self.assertEqual(bytes(e.u.mem_read(0x60000000,0x400)),obj)
    self.assertEqual(self.call(e,'apply',s,g,f,0),0)
    self.assertEqual(bytes(e.u.mem_read(f,0x9000)),after)
 def test_rejection_and_reprepare_prevent_stale_cpu_skip(self):
  e,s,f,g=self.fixture()
  self.assertEqual(self.call(e,'prepare',s,66,0,7),1);self.assertEqual(self.call(e,'apply',s,g,f,0),1)
  for film,exposure,generation in [(32,0,8),(79,0,8),(66,1,8),(68,3,8),(68,0,0)]:
   self.assertEqual(self.call(e,'prepare',s,film,exposure,generation),0)
   self.assertEqual(self.call(e,'matches',s,66,0,7),0)
  self.assertEqual(self.call(e,'prepare',s,67,0,9),1)
  before=bytes(e.u.mem_read(f,0x9000));e.u.mem_write(s+28+36+80*2,b'\0\0')
  self.assertEqual(self.call(e,'apply',s,g,f,0),0)
  self.assertEqual(bytes(e.u.mem_read(f,0x9000)),before)
  self.assertEqual(self.call(e,'matches',s,67,0,9),0)
 def test_gamma_alias_and_frame_alias_and_color_space_fail_without_mutation(self):
  for mode in ('gamma','state','space'):
   e,s,f,g=self.fixture();self.call(e,'prepare',s,66,0,7);before=bytes(e.u.mem_read(f,0x9000))
   self.assertEqual(self.call(e,'apply',s,f if mode=='gamma' else g,s if mode=='state' else f,2 if mode=='space' else 0),0)
   self.assertEqual(bytes(e.u.mem_read(f,0x9000)),before)
 def test_packed_profiles_decode_exactly_and_sector_writes_match_original_blob(self):
  fit=json.loads((ROOT/'builds/gr3-native-film-fit/native-film-fit.json').read_text())
  for film,name in ((66,'5207'),(67,'phoenix_ii')):
   e,s,f,g=self.fixture();self.assertEqual(self.call(e,'prepare',s,film,0,7),1)
   actual=struct.unpack('<18h768H',e.u.mem_read(s+28,1572));q=fit['targets'][name]['parameters']
   expected=tuple(v for key in ('matrix_q13','post_q9','curves') for row in q[key] for v in row)
   self.assertEqual(actual,expected)
   raw=(ROOT/f'builds/gr3-native-film-fit/{name}-multiaxis.bin').read_bytes();t=e.alloc(len(raw));e.u.mem_write(t,raw);record=e.alloc(24);reference=e.alloc(0x9000)
   e.u.mem_write(reference,bytes(e.u.mem_read(f,0x9000)))
   for i,o in enumerate((0,32,52,2212,3652,3694)):e.w32(record+i*4,t+o)
   e.call(0x536df55c,record,reference+0x120)
   self.assertEqual(self.call(e,'apply',s,g,f,0),1)
   self.assertEqual(bytes(e.u.mem_read(f+0x1c0,0x12a0-0x1c0)),bytes(e.u.mem_read(reference+0x1c0,0x12a0-0x1c0)))
 def test_actual_arm_stack_high_water_has_no_nested_sector_and_gamma_workspaces(self):
  rows=[]
  for film in (33,66,67,68,72):
   e,s,f,g=self.fixture(tone=12);self.assertEqual(self.call(e,'prepare',s,film,0,7),1)
   entry=0x5effff00;low=[entry]
   def observe(u,at,size,data):low[0]=min(low[0],u.reg_read(UC_ARM_REG_SP))
   hook=e.u.hook_add(UC_HOOK_CODE,observe)
   try:self.assertEqual(self.call(e,'apply',s,g,f,0),1)
   finally:e.u.hook_del(hook)
   used=entry-low[0];rows.append((film,used))
   self.assertLessEqual(used,4000 if film in (66,67,72) else 2400)
  self.assertGreater(dict(rows)[66],dict(rows)[33])
 def test_each_red_ei_has_distinct_profile(self):
  e,s,f,g=self.fixture();targets=[]
  for exposure in (0,1,2):
   self.assertEqual(self.call(e,'prepare',s,68,exposure,9),1);targets.append(bytes(e.u.mem_read(s+28,1572)))
  self.assertEqual(len(set(targets)),3)
 def test_stock_user_adjustments_survive_native_color_composition(self):
  e,s,f,g=self.fixture(tone=12);self.call(e,'prepare',s,66,0,7);self.assertEqual(self.call(e,'apply',s,g,f,0),1)
  baseline=bytes(e.u.mem_read(f,0x9000))
  for offset in (0x77d,0x77e,0x780,0x781,0x782,0x784):
   with self.subTest(offset=hex(offset)):
    e,s,f,g=self.fixture(tone=12,extra={offset:8});before=bytes(e.u.mem_read(f,0x9000));self.call(e,'prepare',s,66,0,7)
    self.assertEqual(self.call(e,'apply',s,g,f,0),1);after=bytes(e.u.mem_read(f,0x9000))
    self.assertNotEqual(after,baseline)
    self.assertEqual(before[0x529c:0x541c],after[0x529c:0x541c])
 def test_lossless_bitstream_roundtrip_including_escapes(self):
  rng=random.Random(670068)
  for delta in ([0]*255,[255]*255,[i%256 for i in range(255)],[rng.randrange(256) for _ in range(255)]):
   self.assertEqual(decode_curve_deltas(encode_curve_deltas(delta)),delta)
 def test_all_six_profiles_and_entire_native_frame_match_precompression_arm(self):
  # Frozen from the original808-byte/profile ARM implementation, before the
  # 2bit encoder existed. Both decoded1572-byte target and full0x9000 frame.
  expected=[(33, 0, 'af4e1c174ab2762b98f4bec6d4ea11cf6ab9feb5e25836e2626d854c9265c4b3', '5394b1b6d97ec5e109bc933d0f1149ab3c66ede8f1dc515b41e1cc7327b281de'), (66, 0, '343edf0c16f5015cae11c1f88dad2493ad14ae68b2ff462123af6779edc41900', '3bdbd8783d28413377132cf7c2d0b8a31d2f51b06189ca52174f3742ebee7ff9'), (67, 0, 'b90c5627e1c95e6e218f5992e8a8490a978fae439f1338affa3e13d1f5c4568a', '11c17f66e2c326e3014182c9d6757c002397b22c4d1b038a8c712a9c1ad549c5'), (68, 0, '1efe4018330d2e51a067fd66e1c8a5a75af3f44751233490bf1aee9b1f838271', '15cb9291b7b06a5bd813dd30f41dcb1404f709fa258f67d3313c19641c5c1278'), (68, 1, '23336c8a098f3611b162f05e331fb2682fb1168cd606bcbf699b6e9d4b83b85f', '265097a5ddc3c05376d67671eb0d714503a16704ab75414cf620e62d153a4e1e'), (68, 2, 'eef5c0a23140c15de54bd872e1e60fd7bb377ce1d055a516f9573c2108ffc710', 'a39ee65be69deff28240167dea3ef9334a516db035fa52c4d6667a35514f35cf')]
  for film,exposure,target_hash,frame_hash in expected:
   with self.subTest(film=film,exposure=exposure):
    e,s,f,g=self.fixture();self.assertEqual(self.call(e,'prepare',s,film,exposure,41),1)
    self.assertEqual(hashlib.sha256(bytes(e.u.mem_read(s+28,1572))).hexdigest(),target_hash)
    self.assertEqual(self.call(e,'apply',s,g,f,0),1)
    self.assertEqual(hashlib.sha256(bytes(e.u.mem_read(f,0x9000))).hexdigest(),frame_hash)
 def test_checked_in_profiles_reproducible_and_no_equivalence_claim(self):
  header,evidence=profiles();self.assertEqual(header,(ROOT/'native/gr3/m10v_isp_native_look_profiles.h').read_text())
  self.assertFalse(evidence['camera_validated']);self.assertFalse(evidence['old_cpu_color_equivalent'])
