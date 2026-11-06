"""Execute the actual PURE freeze branch, without constructing shot metadata."""
import shutil,subprocess,tempfile,unittest
from pathlib import Path
from unicorn import arm_const as A
from scripts.build_gr3_m10v_library import FLAGS,link_object
from tests import test_gr3_isp_effects_shot as shot
class PureImprintShotTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
  src=Path(cls.tmp.name)/'pure.c';obj=src.with_suffix('.o')
  src.write_text('\n'.join('#include "'+str(shot.ROOT/'native/gr3'/f)+'"' for f in ('m10v_isp_effects_state.c','m10v_isp_effects_shot.c')))
  subprocess.run(['clang',*FLAGS,'-DM10V_PURE_ISP_EFFECTS=1','-DM10V_ISP_EFFECTS_SHOT_OFFSET=0x5778','-c',str(src),'-o',str(obj)],check=True,capture_output=True)
  exports=tuple('m10v_isp_effects_shot_'+n for n in ('reserve','freeze','read','plan','complete','fail','stock_query','unavailable'))
  cls.code,cls.symbols=link_object(obj.read_bytes(),shot.BASE,{'m10v_isp_effects_camera_imprint_snapshot':0x53000100,'m10v_library_valid':0x53000104},'m10v_settings_',omitted_exports=('m10v_settings_open','m10v_settings_key'),additional_exports=exports)
 put=shot.EffectsShotTests.put
 word=shot.EffectsShotTests.word
 call=shot.EffectsShotTests.call
 setUp=shot.EffectsShotTests.setUp
 def hook(self,u,pc,size,data):
  if pc==0x53000100:
   self.calls+=1
   if self.available:self.put(u.reg_read(A.UC_ARM_REG_R0),(self.settings[7]>>7)&7)
   u.reg_write(A.UC_ARM_REG_R0,int(self.available))
  elif pc==0x53000104:u.reg_write(A.UC_ARM_REG_R0,1)
  else:return
  u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
 def test_real_pure_branch_keeps_global_imprint_across_later_selection(self):
  self.settings=(0,)*7+(0x46580000|(7<<7),)
  self.assertEqual(self.call('freeze',shot.RECIPE),1)
  self.settings=(0,)*8
  self.assertEqual(self.call('freeze',shot.RECIPE),1)
  self.assertEqual(self.call('read',shot.RECIPE,shot.OUT),1)
  self.assertEqual(self.word(shot.OUT+44),0x46580000|(7<<7))
  self.assertEqual(self.calls,1)
  self.assertEqual(self.call('plan',shot.RECIPE,shot.SI,6000,4000,0),1)
  self.assertEqual(self.word(shot.SHOT+56),48000000)
 def test_unavailable_global_cache_never_becomes_a_valid_off_selection(self):
  self.available=False
  self.assertEqual(self.call('freeze',shot.RECIPE),0)
  self.assertEqual(self.word(shot.SHOT+8),2)
  self.available=True
  self.assertEqual(self.call('freeze',shot.RECIPE),0)
  self.assertEqual(self.calls,1)
