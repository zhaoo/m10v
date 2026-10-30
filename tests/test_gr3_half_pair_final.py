"""Execute pair adapter tests from the decoded deliverable, not a fresh object.
Filesystem, pool and trace publication remain explicitly doubled boundaries.
"""
import json,os,struct,unittest
from pathlib import Path
from tests import test_gr3_half_pair_camera as support
class FinalPairCameraTests(support.PairCameraTests):
 @classmethod
 def setUpClass(cls):
  folder=os.environ.get('M10V_HALF_PAIR_FINAL')
  if not folder:raise unittest.SkipTest('requires decoded final candidate directory')
  super().setUpClass()
  folder=Path(folder);cls.base=0x53000000;cls.image=(folder/'final-rtos.bin').read_bytes();cls.manifest=json.loads((folder/'manifest.json').read_text());cls.symbols=cls.manifest['symbols'];cls.build_id=int(cls.manifest['debug_log']['build_id'],16)
 def service(self,u,pc,n,data):
  if pc==self.symbols['m10v_save_trace_recipe_mark']:pc=0x53000100
  elif pc==self.symbols['m10v_save_trace_recipe_raw_status']:pc=0x53000104
  return super().service(u,pc,n,data)
 def test_final_selected_menu_hook_and_both_encoded_policy_sites(self):
  for at,to,link in [(0x531b6be4,self.symbols['m10v_half_pair_select'],False)]:
   word=struct.unpack_from('<I',self.image,at-self.base)[0]
   self.assertEqual(word,0xea000000|(((to-at-8)>>2)&0xffffff))
  from scripts.gr3_aspect_overlay import build_module
  _,entries=build_module()
  for at in (0x53664c60,0x536649f0):
   to=entries['m10v_aspect_encoded_resolution'];word=struct.unpack_from('<I',self.image,at-self.base)[0]
   self.assertEqual(word,0xeb000000|(((to-at-8)>>2)&0xffffff))

 def test_compiled_owner_ctor_and_dtor_call_pair_lifetime_adapters(self):
  runtime=self.image[self.manifest['base']-self.base:]
  for entry,target in [('m10v_settings_controller_top_ctor','m10v_half_pair_init'),('m10v_settings_controller_top_dtor','m10v_half_pair_destroy')]:
   start=self.symbols[entry];end=min([v for v in self.symbols.values() if v>start]+[start+4096])
   calls=[]
   for at in range(start,end,4):
    word=struct.unpack_from('<I',self.image,at-self.base)[0]
    if word==0xeb000000|(((self.symbols[target]-at-8)>>2)&0xffffff):calls.append(at)
   self.assertEqual(len(calls),1,entry+' must own '+target)
