"""Installed owner and JPEG borders, with only OS clock/heap/SD substituted."""
import json,struct,tempfile,unittest
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn import arm_const as A
from scripts.build_gr3_m10v_library import build,ROOT

class CaptureLifecycleIntegrationTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
  cls.manifest=build(Path(cls.tmp.name),debug_mode=True,lifecycle_trace=True)
  cls.code=(Path(cls.tmp.name)/'m10v-library-arm.bin').read_bytes()
  cls.rom=(ROOT/'builds/gr3-extension-validation/official-rtos.bin').read_bytes()
 def fixture(self):
  u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0x53000000,0x1200000);u.mem_write(0x53000000,self.rom);u.mem_write(self.manifest['base'],self.code);u.mem_map(0x55000000,0x100000)
  batches=[];ticks=[123];heap=[0x55020000];owner=self.manifest['capture_lifecycle']['owner'];storage=owner['storage']
  expected=max(storage['trace_offset']+storage['bytes'],storage['color_offset']+storage['color_bytes'],
   storage['raw_token_offset']+storage['raw_token_bytes'],storage['stamp_offset']+storage['stamp_bytes'],
   storage['custom_isp_offset']+storage['custom_isp_bytes'])
  self.assertEqual(storage['extended_recipe_bytes'],expected)
  for p in self.manifest['capture_lifecycle']['patches']:
   self.assertEqual(bytes(u.mem_read(p['address'],4)).hex(),p['expected_hex']);u.mem_write(p['address'],bytes.fromhex(p['replacement_hex']))
  def service(machine,pc,size,data):
   if pc==0x5351091c:
    self.assertEqual(machine.reg_read(A.UC_ARM_REG_R0),expected);machine.reg_write(A.UC_ARM_REG_R0,heap[0]);heap[0]+=0x6000
   elif pc==0x53050b7c:
    machine.mem_write(machine.reg_read(A.UC_ARM_REG_R0),struct.pack('<II',0,ticks[0]));ticks[0]+=10;machine.reg_write(A.UC_ARM_REG_R0,0)
   elif pc==self.manifest['symbols']['m10v_debug_batch']:
    pointer=machine.reg_read(A.UC_ARM_REG_R0);count=machine.reg_read(A.UC_ARM_REG_R1)
    batches.append([struct.unpack('<5I',machine.mem_read(pointer+i*20,20)) for i in range(count)]);machine.reg_write(A.UC_ARM_REG_R0,1)
   else:return
   machine.reg_write(A.UC_ARM_REG_PC,machine.reg_read(A.UC_ARM_REG_LR))
  u.hook_add(UC_HOOK_CODE,service)
  return u,batches
 def call(self,u,name,*args):
  for i in range(4):u.reg_write(getattr(A,f'UC_ARM_REG_R{i}'),args[i]if i<len(args)else 0)
  u.reg_write(A.UC_ARM_REG_SP,0x550ff000);u.reg_write(A.UC_ARM_REG_LR,0x550fff00)
  u.emu_start(self.manifest['symbols'][name],0x550fff00,count=2000000)
  self.assertEqual(u.reg_read(A.UC_ARM_REG_PC),0x550fff00);return u.reg_read(A.UC_ARM_REG_R0)
 def test_recipe_rings_follow_owner_and_submit_return_does_not_write_sd_before_wait(self):
  u,batches=self.fixture();recipes=[]
  for _ in range(2):
   recipe=self.call(u,'m10v_save_trace_recipe_alloc',0x4778);recipes.append(recipe);u.mem_write(recipe,struct.pack('<I',0x53d0fc90))
  r,r2=recipes
  self.call(u,'m10v_save_trace_recipe_mark',r2,188,1,2,3)
  self.call(u,'m10v_save_trace_recipe_mark',r,188,4,5,6)
  for event in (193,194,190,191,192):
   count=len(batches);self.call(u,'m10v_lifecycle_phase',r+0x9b8,event,0)
   if event in (191,194):self.assertEqual(len(batches),count)
  self.assertEqual([[e[0] for e in b]for b in batches],[[188,193],[194,190],[191,192]])
  self.assertTrue(all(e[1]==r for b in batches for e in b))
  self.call(u,'m10v_lifecycle_phase',r2+0x9b8,193,0)
  self.assertEqual([e[0]for e in batches[-1]],[188,193]);self.assertTrue(all(e[1]==r2 for e in batches[-1]))
 def test_manifest_has_only_checked_owner_and_jpeg_patches_and_preserves_original_wait(self):
  m=self.manifest['capture_lifecycle'];self.assertEqual(len(m['patches']),19)
  self.assertTrue(m['jpeg']['native_wait_preserved']);self.assertTrue(m['jpeg']['stack_arguments_untouched']);self.assertFalse(m['buffer_policy_changed'])
