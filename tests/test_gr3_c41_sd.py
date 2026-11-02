"""Real C validator preserves the previous release and admits only exact new recipes."""
import ctypes,gzip,struct,subprocess,tempfile,unittest,zlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class C41SdTests(unittest.TestCase):
 def test_old_builtin_custom_and_new_c41_records_validate_without_abi_change(self):
  with tempfile.TemporaryDirectory() as tmp:
   so=Path(tmp)/'sd.so';subprocess.run(['clang','-shared','-fPIC','-O2','-Wall','-Wextra','-Werror',str(ROOT/'native/gr3/m10v_sd_library.c'),'-o',str(so)],check=True,capture_output=True)
   lib=ctypes.CDLL(str(so));lib.m10v_sd_record.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32]
   old=gzip.decompress((ROOT/'tests/fixtures/gr3-pre-c41-films.m10.gz').read_bytes())
   new=subprocess.check_output(['node','--input-type=module','-e',"import{buildSdFilmPack}from'./node/gr3-sd-film-pack.mjs';process.stdout.write(buildSdFilmPack([312,313,322,323,324,325,326]));"],cwd=ROOT)
   previous=subprocess.check_output(['node','--input-type=module','-e',"import{sdFilmRecord,sdCrc}from'./node/gr3-sd-film-pack.mjs';import{readFileSync}from'node:fs';const p=JSON.parse(readFileSync('node/gr3-sd-pre-five-c41-contract.json'));const records=p.ids.map(id=>{const r=sdFilmRecord(id);Buffer.from(p.renderer,'hex').copy(r,8448);r.writeUInt32LE(sdCrc(r.subarray(0,-4)),12284);return r;});const h=Buffer.alloc(4096);h.writeUInt32LE(records.length,16);process.stdout.write(Buffer.concat([h,...records]));"],cwd=ROOT)
   for pack in [old,previous,new]:
    n=struct.unpack_from('<I',pack,16)[0]
    for i in range(n):
     record=bytearray(pack[4096+i*12288:4096+(i+1)*12288]);film=struct.unpack_from('<I',record,8)[0]
     self.assertEqual(lib.m10v_sd_record(bytes(record),12288,film),film)
     record[100]^=1;struct.pack_into('<I',record,12284,zlib.crc32(record[:-4]))
     self.assertEqual(lib.m10v_sd_record(bytes(record),12288,film),0)
 def test_separate_readonly_profile_module_matches_all_integer_profiles_and_rejects_bad_indexes(self):
  with tempfile.TemporaryDirectory() as tmp:
   so=Path(tmp)/'profiles.so';subprocess.run(['clang','-shared','-fPIC','-O2','-Wall','-Wextra','-Werror',str(ROOT/'native/gr3/m10v_c41_native_data.c'),'-o',str(so)],check=True,capture_output=True)
   lib=ctypes.CDLL(str(so));get=lib.m10v_c41_native_data
   get.argtypes=[ctypes.c_uint32,ctypes.c_uint32];get.restype=ctypes.c_void_p
   profiles=json.loads((ROOT/'native/gr3/c41-reference.json').read_text())['native_profiles_full']
   for i,q in enumerate(profiles):
    packed=struct.unpack('<18h6H',ctypes.string_at(get(0,i),48))
    self.assertEqual(list(packed[:9]),[v for row in q['matrix_q13'] for v in row])
    self.assertEqual(list(packed[9:18]),[v for row in q['post_q9'] for v in row])
    self.assertEqual(list(packed[18:21]),[c[0] for c in q['curves']])
    self.assertTrue(get(1,i))
    self.assertEqual(list(struct.unpack('<108h',ctypes.string_at(get(2,i),216))),[v for sector in q['hue_q10'] for row in sector for v in row])
   for part,index in [(0,7),(1,7),(2,7),(3,0),(0,0xffffffff)]:self.assertIsNone(get(part,index))
