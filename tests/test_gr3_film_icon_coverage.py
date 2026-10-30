"""Run every built-in film through the MENU and ADJ icon adapters on ARM."""
import json, os, struct, tempfile, unittest
from pathlib import Path
from unicorn import UC_HOOK_CODE
from unicorn import arm_const as A
from scripts.build_gr3_m10v_library import build
from tests.test_gr3_isp_base import StockISP

ROOT=Path(__file__).resolve().parents[1]
class FilmIconCoverageTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
  cls.manifest=build(cls.tmp.name,sd_library=True,appended_slots=True)
  cls.runtime=(Path(cls.tmp.name)/'m10v-library-arm.bin').read_bytes()
  cls.rom=Path(os.environ['M10V_GR3_ORIGINAL_RTOS']).read_bytes()
 def test_all_builtin_films_have_the_same_icon_in_every_slot_and_adapter(self):
  m=self.manifest;image=bytearray(self.rom);at=m['base']-0x53000000
  image.extend(bytes(max(0,at+len(self.runtime)-len(image))));image[at:at+len(self.runtime)]=self.runtime
  e=StockISP(image);state=bytearray.fromhex(m['initial_state_hex'])
  def services(u,pc,n,_):
   if pc==m['symbols']['m10v_camera_library_load']:
    u.mem_write(u.reg_read(A.UC_ARM_REG_R0),bytes(state));result=0
   elif pc==0x5320ad88:result=0x55006000
   elif pc==0x5320ba9c:result=0x55068200
   else:return
   u.reg_write(A.UC_ARM_REG_R0,result);u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
  e.u.hook_add(UC_HOOK_CODE,services)
  inventory=[*[(i,670+i) for i in range(1,79)],(79,754),(288,754),(289,755),(290,761),*[(291+i,762+i) for i in range(7)],(298,774),*[(299+i,775+i) for i in range(7)],*[(306+i,858+i) for i in range(6)],(314,871),(315,872),(316,873),(317,875)]
  for film,icon in inventory:
   for slot in range(10):
    struct.pack_into('<H',state,12+8*slot,film)
    for name in ('m10v_menu_icon','m10v_menu_value_icon'):
     e.call(m['symbols'][name],0,25+slot)
     self.assertEqual(e.u.reg_read(A.UC_ARM_REG_R0),icon,(film,slot,name))
