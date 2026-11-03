import ctypes as C,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class ResidentBridge(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup);p=Path(cls.tmp.name)/'bridge.dylib'
  source=ROOT/'native/companion/resident_bridge.c'
  if source.exists():
   r=subprocess.run(['clang','-O2','-Wall','-Wextra','-Werror','-dynamiclib',str(source),str(ROOT/'tests/support_resident_bridge.c'),'-o',str(p)],capture_output=True,text=True)
   if r.returncode:raise AssertionError(r.stderr)
   cls.lib=C.CDLL(str(p))
  else:cls.lib=None
 def test_valid_duplicate_busy_bad_crc_dead_owner_and_cache_failures(self):
  self.assertIsNotNone(self.lib,'missing resident bridge')
  for mode in range(10):
   with self.subTest(mode=mode):self.assertEqual(self.lib.test_resident_case(mode),0)
