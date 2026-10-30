"""Native reader retains exact old artwork records, rejects CRC-repaired edits."""
import ctypes,gzip,struct,subprocess,tempfile,unittest,zlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class SquareArtCompatibilityTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.folder=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.folder.cleanup)
  path=Path(cls.folder.name)/'sd.dylib'
  subprocess.run(['clang','-shared','-fPIC','-O2','-I',str(ROOT/'native/gr3'),str(ROOT/'native/gr3/m10v_sd_library.c'),'-o',str(path)],check=True)
  cls.lib=ctypes.CDLL(str(path));cls.lib.m10v_sd_record.argtypes=[ctypes.c_char_p,ctypes.c_uint32,ctypes.c_uint32];cls.lib.m10v_sd_record.restype=ctypes.c_uint32

 def test_exact_old_builtin_pack_including_instax_and_repaired_artwork(self):
  pack=gzip.decompress((ROOT/'tests/fixtures/gr3-pre-square-art-films.m10.gz').read_bytes())
  for i in range(struct.unpack_from('<I',pack,16)[0]):
   record=pack[4096+i*12288:4096+(i+1)*12288];film=struct.unpack_from('<I',record,8)[0]
   self.assertEqual(self.lib.m10v_sd_record(record,len(record),film),film)
   damaged=bytearray(record);damaged[2248]^=1;struct.pack_into('<I',damaged,12284,zlib.crc32(damaged[:-4]))
   self.assertEqual(self.lib.m10v_sd_record(bytes(damaged),len(damaged),film),0)
