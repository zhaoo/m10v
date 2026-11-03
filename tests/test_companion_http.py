"""Actual C authentication and HTTP parser; Python hashlib is the oracle."""
import ctypes,hashlib,hmac,json,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class HttpCore(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.temp.cleanup);d=Path(cls.temp.name)
  result=subprocess.run(['clang','-std=c11','-Wall','-Wextra','-Werror','-shared','-fPIC',str(ROOT/'native/companion/auth.c'),str(ROOT/'native/companion/http_parser.c'),'-I',str(ROOT/'native/companion'),str(ROOT/'tests/support_companion_auth.c'),'-o',str(d/'http.dylib')],capture_output=True,text=True)
  if result.returncode:raise AssertionError(result.stderr)
  cls.lib=ctypes.CDLL(str(d/'http.dylib'))
  cls.lib.m10v_sha256.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_void_p]
  cls.lib.m10v_hmac256.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_void_p]
 def test_sha_and_hmac_match_independent_vectors(self):
  for payload in [b'',b'abc',b'a'*1000000,bytes(range(256))*63]:
   output=ctypes.create_string_buffer(32);self.lib.m10v_sha256(payload,len(payload),output);self.assertEqual(output.raw,hashlib.sha256(payload).digest())
   key=bytes(range(32));self.lib.m10v_hmac256(key,len(key),payload,len(payload),output);self.assertEqual(output.raw,hmac.digest(key,payload,'sha256'))
 def test_contract_auth_fixture(self):
  fixture=json.loads((ROOT/'contracts/companion-v1-fixtures.json').read_text())['authentication']
  output=ctypes.create_string_buffer(32);key=bytes.fromhex(fixture['keyHex']);payload=fixture['canonical'].encode();self.lib.m10v_hmac256(key,len(key),payload,len(payload),output);self.assertEqual(output.raw.hex(),fixture['signatureHex'])
 def test_strict_http_rejects_smuggling_and_non_camera_paths(self):
  validate=self.lib.m10v_http_validate_head;validate.argtypes=[ctypes.c_char_p,ctypes.c_uint32];validate.restype=ctypes.c_int
  good=b'GET /m10v/v1/state HTTP/1.1\r\nHost: camera\r\nContent-Length: 0\r\n\r\n'
  self.assertEqual(validate(good,len(good)),0)
  for raw in [good.replace(b'GET ',b'GET http://other/'),good.replace(b'state',b'../state'),good.replace(b'state',b'%2estate'),good.replace(b'Content-Length: 0',b'Transfer-Encoding: chunked'),good.replace(b'Content-Length: 0',b'Content-Length: 0\r\nContent-Length: 1'),good.replace(b'Content-Length: 0',b'Content-Length: 16385'),good.replace(b'\r\nHost:',b'\nHost:'),good.replace(b'Content-Length: 0',b'Content-Length: +0')]:
   with self.subTest(raw=raw):self.assertNotEqual(validate(raw,len(raw)),0)

 def test_sessions_sequences_nonce_and_replay_window(self):
  self.lib.m10v_test_auth_case.argtypes=[ctypes.c_uint];self.lib.m10v_test_auth_case.restype=ctypes.c_int
  for mode in range(10):
   with self.subTest(mode=mode):self.assertEqual(self.lib.m10v_test_auth_case(mode),0)

 def test_signed_response_binds_status_boot_session_and_body(self):
  signature=ctypes.create_string_buffer(65);self.assertEqual(self.lib.m10v_test_response_signature(signature),0)
  canonical='RESPONSE\nGET\n/m10v/v1/capabilities\n'+'01'+'00'*15+'\n000102030405060708090a0b0c0d0e0f\n0\n'+'0'*31+'1\n200\n'+hashlib.sha256(b'{}').hexdigest()
  self.assertEqual(signature.value.decode(),hmac.digest(bytes(range(32)),canonical.encode(),'sha256').hex())
