import struct,subprocess,tempfile,unittest
from pathlib import Path
from scripts.build_gr3_m10v_library import link_object
class ConditionalRelocation(unittest.TestCase):
 def test_conditional_call_preserves_condition_link_and_target(self):
  with tempfile.TemporaryDirectory()as tmp:
   p=Path(tmp);source=p/'call.S';source.write_text('.syntax unified\n.arm\n.text\n'+''.join('.global m10v_companion_ui_'+n+'\n.type m10v_companion_ui_'+n+',%function\nm10v_companion_ui_'+n+':\n'+body+'\n' for n,body in [('init','push {r4,lr}\ncmp r0,#0\nblne m10v_companion_ui_start\npop {r4,pc}'),('start','mov r0,#7\nbx lr'),('stop','bx lr'),('timer','bx lr'),('storage_enter','bx lr'),('storage_leave','bx lr')]))
   subprocess.run(['clang','--target=armv7-none-eabi','-marm','-c',str(source),'-o',str(p/'call.o')],check=True,capture_output=True)
   data=(p/'call.o').read_bytes();code,symbols=link_object(data,0x54100000,prefix='m10v_companion_ui_');word=struct.unpack_from('<I',code,8)[0]
   self.assertEqual(word>>24,0x1b);delta=(word&0xffffff)<<2
   if delta&0x2000000:delta-=0x4000000
   self.assertEqual(0x54100000+8+8+delta,symbols['m10v_companion_ui_start'])
   shoff=struct.unpack_from('<I',data,32)[0];size,count=struct.unpack_from('<HH',data,46)
   sections=[struct.unpack_from('<10I',data,shoff+i*size) for i in range(count)];text=next(row for row in sections if row[1]==1 and row[2]&4)
   for bad in [0xfbfffffe,0xebfffffe,0xe1a00000]:
    patched=bytearray(data);struct.pack_into('<I',patched,text[4]+8,bad)
    with self.subTest(bad=hex(bad)),self.assertRaises(ValueError):link_object(bytes(patched),0x54100000,prefix='m10v_companion_ui_')
