import subprocess,types,unittest
from scripts.build_gr3_settings_hooks import build_settings_hooks
from scripts.build_gr3_hdf_menu import build_hooks
BASE=0x540b6000
class Layout(unittest.TestCase):
 def symbols(self):
  names=['factory','top_dtor','top_ctor','key_route','destroy','enter','ready','key']
  ab=['selector','mapper','live_enter','live_leave','live_destroy','live_event','adj_event','adj_refresh','adj_exit','adj_destroy','adj_changed','dispatch','render']
  return {**{f'm10v_settings_controller_{n}':BASE+0x100+i*16 for i,n in enumerate(names)},**{f'm10v_settings_controller_ab_{n}':BASE+0x1000+i*16 for i,n in enumerate(ab)},**{f'm10v_hdf_menu_{n}':BASE+0x2000+i*16 for i,n in enumerate(['top_ctor','top_dtor','factory','key_route','destroy','enter','ready','key'])}}
 def test_default_off_hooks_identical_to_latest_main(self):
  code=subprocess.check_output(['git','show','a24ccc2:scripts/build_gr3_settings_hooks.py'],text=True);m=types.ModuleType('old');exec(compile(code,'old','exec'),m.__dict__)
  self.assertEqual(build_settings_hooks(BASE,self.symbols(),live_color=True),m.build_settings_hooks(BASE,self.symbols(),live_color=True))
 def test_reserved_descriptor_follows_all_existing_owner_regions(self):
  _,settings=build_settings_hooks(BASE,self.symbols(),live_color=True,companion=True)
  self.assertEqual(settings['owner_bytes'],0x6440)
  _,hdf=build_hooks(BASE,self.symbols(),settings,True,live_color=True,pure_isp_effects=True,companion=True)
  self.assertEqual(hdf['owner_offset'],0x613c);self.assertLessEqual(hdf['owner_offset']+hdf['controller_bytes']+44,0x6400)
  self.assertEqual(hdf['owner_bytes'],0x6440)
