"""Real C validator preserves the previous release and admits only exact new recipes."""
import ctypes,gzip,struct,subprocess,tempfile,unittest,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class C41SdTests(unittest.TestCase):
 def test_old_builtin_custom_and_new_c41_records_validate_without_abi_change(self):
  with tempfile.TemporaryDirectory() as tmp:
   so=Path(tmp)/'sd.so';subprocess.run(['clang','-shared','-fPIC','-O2','-Wall','-Wextra','-Werror',str(ROOT/'native/gr3/m10v_sd_library.c'),'-o',str(so)],check=True,capture_output=True)
   lib=ctypes.CDLL(str(so));lib.m10v_sd_record.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32]
   old=gzip.decompress((ROOT/'tests/fixtures/gr3-pre-c41-films.m10.gz').read_bytes())
   new=subprocess.check_output(['node','--input-type=module','-e',"import{buildSdFilmPack}from'./node/gr3-sd-film-pack.mjs';process.stdout.write(buildSdFilmPack([312,313]));"],cwd=ROOT)
   for pack in [old,new]:
    n=struct.unpack_from('<I',pack,16)[0]
    for i in range(n):
     record=bytearray(pack[4096+i*12288:4096+(i+1)*12288]);film=struct.unpack_from('<I',record,8)[0]
     self.assertEqual(lib.m10v_sd_record(bytes(record),12288,film),film)
     record[100]^=1;struct.pack_into('<I',record,12284,zlib.crc32(record[:-4]))
     self.assertEqual(lib.m10v_sd_record(bytes(record),12288,film),0)
