"""Flat catalog with original GR III constructors, setters and teardown."""
import struct,unittest,tempfile,json,math
from pathlib import Path
from tests import test_gr3_settings_view as support
IDS=[film['id'] for group in json.loads((support.ROOT/'web/gr3/film-directory.json').read_text())['groups'] for film in group['films']]

class DirectoryViewTests(unittest.TestCase):
 setUpClass=classmethod(support.SettingsViewTests.setUpClass.__func__)
 machine=support.SettingsViewTests.machine
 call=support.SettingsViewTests.call
 def state(self,u,index):
  s=bytearray(216)
  for i,film in enumerate([38,75,79]):struct.pack_into('<H',s,12+8*i,film)
  struct.pack_into('<8I',s,184,2,0,0,index,IDS[index],0,0,0)
  u.mem_write(0x10002000,bytes(s))
  u.mem_write(0x10003000,struct.pack('<7I',0,0,0x540b0010,0,0,0,0))
 def test_all_four_pages_have_bounded_cards_no_name_overlay_and_reuse_buffers(self):
  u=self.machine(catalog_ids=dict(enumerate(IDS)));self.assertEqual(self.call(u,'create',0x10001000),0)
  w=struct.unpack('<56I',u.mem_read(0x10001000,224));allocated=None
  for index in [*range(0,len(IDS),10),len(IDS)-1,0]:
   self.state(u,index);self.call(u,'draw',0x10001000,0x10002000,0x10003000)
   self.assertEqual(u.mem_read(w[3]+0x9e,1),b'\0')
   self.assertEqual([u.mem_read(w[i]+0x9e,1)[0] for i in range(26,36)],([1]*min(10,len(IDS)-index//10*10)+[0]*max(0,index//10*10+10-len(IDS))))
   self.assertEqual([u.mem_read(w[i]+0x9e,1)[0] for i in range(44,52)],[0]*8)
   name_ptr=struct.unpack('<I',u.mem_read(w[52]+0xf0,4))[0]
   self.assertEqual(bytes(u.mem_read(name_ptr,8)).decode('utf-16le').split('\0')[0],f'{index//10+1}/{math.ceil(len(IDS)/10)}')
   heap=struct.unpack('<I',u.mem_read(0x10001000+55*4,4))[0]
   for i in range(min(10,len(IDS)-index//10*10)):
    self.assertEqual(struct.unpack('<HH',u.mem_read(heap+655360+8*i,4)),(128,128))
    x,y,width,height=struct.unpack('<4I',u.mem_read(w[26+i]+0x20,16))
    self.assertEqual((width,height),(128,128))
    self.assertLessEqual(x+width,720);self.assertLessEqual(y+height,378)
   if allocated is not None:self.assertEqual(len(self.live),allocated)
   allocated=len(self.live)
  self.call(u,'destroy',0x10001000);self.assertFalse(self.live)
 def test_card_heap_failure_keeps_exact_fallback_icons_and_teardown(self):
  u=self.machine(fail_cards=True,catalog_ids=dict(enumerate(IDS)));self.call(u,'create',0x10001000)
  w=struct.unpack('<56I',u.mem_read(0x10001000,224))
  for index in [0,10,20]:
   self.state(u,index);self.call(u,'draw',0x10001000,0x10002000,0x10003000)
   icon=lambda film:875 if film==317 else 871+film-314 if 314<=film<=316 else 869+film-312 if 312<=film<=313 else 858+film-306 if 306<=film<=311 else 775+film-299 if 299<=film<=305 else 774 if film==298 else 762+film-291 if 291<=film<=297 else 761 if film==290 else 755 if film==289 else 670+film
   self.assertEqual([struct.unpack('<H',u.mem_read(w[26+i]+0xea,2))[0] for i in range(10)],[icon(v) for v in IDS[index:index+10]])
  self.call(u,'destroy',0x10001000);self.assertFalse(self.live)

class LinkedDirectoryViewTests(DirectoryViewTests):
 @classmethod
 def setUpClass(cls):
  super().setUpClass()
  from scripts.build_gr3_m10v_library import build
  with tempfile.TemporaryDirectory() as tmp:
   manifest=build(Path(tmp),base=support.BASE,sd_library=True,appended_slots=True)
   cls.code=(Path(tmp)/'m10v-library-arm.bin').read_bytes()
   cls.symbols=manifest['symbols'];cls.card=b'';cls.captions=b''
   assert not any(n in cls.symbols for n in ('caption_offsets','caption_rle'))
if __name__=='__main__':unittest.main()
