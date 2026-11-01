"""Feature-gated production adapters, compiled for the actual ARM ABI."""
import tempfile,unittest
from pathlib import Path
from scripts.build_gr3_companion_owner import build_companion_owner
class NativeExtensions(unittest.TestCase):
 def test_feature_build_requires_and_links_owned_adapters(self):
  names=['m10v_camera_library_read_current','m10v_camera_library_mutation_begin','m10v_camera_library_mutation_end','m10v_camera_library_mutation_busy','m10v_camera_library_commit_snapshot','m10v_sd_camera_custom_record','m10v_library_valid','m10v_settings_controller_remote_busy','m10v_settings_controller_remote_ab_read','m10v_settings_controller_remote_ab_write','m10v_settings_controller_remote_aspect_read','m10v_settings_controller_remote_aspect_write','m10v_hdf_remote_snapshot','m10v_hdf_save','m10v_border_camera_snapshot','m10v_border_camera_save','m10v_border_camera_sequence','m10v_isp_effects_set_enabled','m10v_isp_effects_set_strength','m10v_isp_effects_camera_snapshot','m10v_isp_effects_camera_save','m10v_zoom_camera_snapshot','m10v_zoom_camera_save','m10v_zoom_live_slot','m10v_zoom_live_apply']
  imports={n:0x54010000+i*64 for i,n in enumerate(names)}
  with tempfile.TemporaryDirectory() as tmp:
   code,report=build_companion_owner(0x54100000,imports,{'buildId':'11'*32,'catalogHash':'22'*32,'rendererHash':'33'*32},Path(tmp),extensions={'ab':True,'hdf':True,'border':True,'isp':True,'zoom':True,'aspect':True})
   self.assertGreater(len(code),1024);self.assertEqual(report['extensions']['available'],(1<<21)-1)
   self.assertIn('m10v_extensions_apply',report['symbols'])
   self.assertIn('native/companion/extensions.c',report['sources'])

# Execute the production private A/B and aspect adapters with native getter,
# setter and filesystem boundaries doubled. Existing DISP code remains real.
import struct,os
from tests import test_gr3_settings_controller as adapter
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_PC,UC_ARM_REG_LR
class RemoteNativeAdapters(unittest.TestCase):
 companion=True;half_pair=True;ab_enabled=True;debug=False;native_host=False;appended_slots=True;owner_cache=False;exit_trace=False
 setUpClass=classmethod(adapter.ControllerLifetimeTests.setUpClass.__func__)
 machine=adapter.ControllerLifetimeTests.machine
 call=adapter.ControllerLifetimeTests.call
 word=staticmethod(adapter.ControllerLifetimeTests.word)
 count=adapter.ControllerLifetimeTests.count
 def test_remote_pair_toggle_preserves_physical_debounce_and_native_fn(self):
  u=self.machine();owner=0x55040000;self.call(u,'top_ctor',owner)
  u.mem_write(0x55063910,struct.pack('<I',1));u.mem_write(0x55063988,struct.pack('<I',owner));self.route=0x08000000
  out=0x55070000;seq=out+16
  self.assertEqual(self.call(u,'remote_ab_read',out,seq),0);self.assertEqual(struct.unpack('<3I',u.mem_read(out,12)),(0,12,5))
  self.assertEqual(self.call(u,'remote_ab_write',1,0),0)
  self.assertEqual(self.call(u,'remote_ab_read',out,seq),0);self.assertEqual(self.word(u,out+4),0);self.assertEqual(self.word(u,seq),1)
  # Stock-only pair avoids any film substitution, activates through native setter.
  self.assertEqual(self.call(u,'remote_ab_write',0,1),0);self.assertEqual(self.ab_tone,11)
  self.assertEqual(self.call(u,'remote_ab_write',1,2),1) # active pair is immutable
  self.call(u,'ab_mapper',0,0x37);self.assertEqual(self.ab_tone,16)
  self.call(u,'ab_mapper',0,0x37);self.assertEqual(self.ab_tone,16)
  self.call(u,'ab_mapper',0,0x36);self.call(u,'ab_mapper',0,0x37);self.assertEqual(self.ab_tone,11)
  before=self.count('m10v_ab_mapper_original');self.call(u,'ab_mapper',0,0x22);self.assertEqual(self.count('m10v_ab_mapper_original'),before+1)
  self.assertEqual(self.call(u,'remote_ab_write',0,0),0)
  self.route=0x0200f100;self.assertEqual(self.call(u,'remote_ab_write',0,1),1)
 def test_remote_aspect_uses_half_session_wrapper_and_rejects_editor(self):
  u=self.machine();owner=0x55040000;self.call(u,'top_ctor',owner)
  u.mem_write(0x55063910,struct.pack('<I',1));u.mem_write(0x55063988,struct.pack('<I',owner));self.route=0x08000000
  actual=[0];selected=[]
  address=self.externals['m10v_half_pair_select']
  def hook(m,pc,n,ctx):
   if pc==address:actual[0]=m.reg_read(UC_ARM_REG_R1);selected.append(actual[0]);value=0
   elif pc==0x53245260:value=actual[0]
   elif pc==0x5320b31c:value=0x55060000
   else:return
   m.reg_write(UC_ARM_REG_R0,value);m.reg_write(UC_ARM_REG_PC,m.reg_read(UC_ARM_REG_LR))
  u.hook_add(UC_HOOK_CODE,hook)
  for raw in range(7):self.assertEqual(self.call(u,'remote_aspect_write',raw),0)
  self.assertEqual(selected,list(range(7)))
  self.assertEqual(self.call(u,'remote_aspect_write',7),1)
  self.route=0x02000012;self.assertEqual(self.call(u,'remote_aspect_write',0),1);self.assertEqual(len(selected),7)
