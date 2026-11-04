import ctypes as C, subprocess, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class WifiTests(unittest.TestCase):
 def test_exact_camera_wireless_interface_only(self):
  with tempfile.TemporaryDirectory() as d:
   output=Path(d)/'wifi.so'
   subprocess.run(['clang','-shared','-fPIC','-Wall','-Wextra','-Werror',str(ROOT/'native/companion/linux_wifi.c'),'-o',str(output)],check=True,capture_output=True)
   lib=C.CDLL(str(output));cb=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_uint,C.c_void_p,C.c_uint)
   def case(mode):
    def query(ctx,command,data,size):
     p=C.cast(data,C.POINTER(C.c_ubyte))
     if command==0x8912:
      count=2 if mode=='ambiguous' else 1
      for j in range(count):
       row=bytearray(32);row[:5]=b'wlan0';row[4]+=j;row[16]=2;row[20:24]=bytes([192,168,0,2 if mode=='wrongIP' else 1]);C.memmove(C.addressof(p.contents)+j*32,bytes(row),32)
      return 31 if mode=='truncated' else count*32
     if command==0x8913:p[16]=8 if mode=='loopback' else 0 if mode=='down' else 1;return 0
     if command==0x8b01:p[16]=0 if mode=='ethernet' else ord('I');return -1 if mode=='failed' else 0
     if command==0x8b07:p[16]=2 if mode=='station' else 3;return -1 if mode=='noMode' else 0
     return -1
    out=C.create_string_buffer(16);fn=cb(query);lib.m10v_linux_wifi_discover.argtypes=[C.c_void_p,cb,C.c_void_p,C.c_int]
    return lib.m10v_linux_wifi_discover(None,fn,out,1),out.value
   self.assertEqual(case('ok'),(1,b'wlan0'))
   for mode in ['ambiguous','wrongIP','truncated','loopback','down','ethernet','failed','station','noMode']:
    with self.subTest(mode=mode):self.assertEqual(case(mode)[0],0)
