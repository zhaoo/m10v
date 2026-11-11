"""Execute real ARM menu scrolling and the single torn toggle."""
import unittest
from tests import test_gr3_isp_effects_menu as effects

class TornMenuTests(unittest.TestCase):
 EXTRA_FLAGS=['-DM10V_TORN_ENABLED=1','-DM10V_COMPANION_ENABLED=1']
 setUpClass=classmethod(effects.EffectsMenuTests.setUpClass.__func__)
 setUp=effects.EffectsMenuTests.setUp
 put=effects.EffectsMenuTests.put
 get=effects.EffectsMenuTests.get
 call=effects.EffectsMenuTests.call
 key=effects.EffectsMenuTests.key
 ready=effects.EffectsMenuTests.ready
 rows=effects.EffectsMenuTests.rows
 child=effects.EffectsMenuTests.child
 def test_fifth_effect_scrolls_without_replacing_legacy_rows(self):
  self.ready();self.call('m10v_hdf_menu_enter',self.page,0,0)
  self.assertEqual(self.rows(),[1141,1155,1203,1214])
  for _ in range(4):self.key(0xd1)
  self.assertEqual(self.rows(),[1155,1203,1214,1221])
  self.assertEqual(self.get(self.page+0x1a4),4)
  self.key(0xd8);self.assertEqual(self.torn_actions,[])
  self.assertEqual(self.rows()[:2],[1220,1219])
  self.key(0xd1);self.assertEqual(self.torn_actions,[])
  self.key(0xd8);self.assertEqual(self.torn_actions,[(self.owner,1)])
  self.assertEqual(self.rows(),[1155,1203,1214,1222])
  self.torn_stage=2;self.call('m10v_hdf_menu_enter',self.page,0,0)
  self.assertEqual(self.rows()[-1],1223)
  self.key(0xd8);self.key(0xd0);self.key(0xd8)
  self.assertEqual(self.torn_actions,[(self.owner,1),(self.owner,0)])
  self.assertEqual(self.rows()[-1],1221)
  for _ in range(4):self.key(0xd0)
  self.assertEqual(self.rows(),[1141,1155,1203,1214])
  self.assertEqual(self.saved_settings,[]);self.assertEqual(self.hdf_saved,[]);self.assertEqual(self.border_saved,[])
 def test_busy_rejection_and_read_only_stage_never_become_actions(self):
  self.ready()
  for _ in range(4):self.key(0xd1)
  self.torn_stage=2;self.call('m10v_hdf_menu_enter',self.page,0,0)
  self.assertEqual(self.rows()[-1],1223)
  self.key(0xd8);self.key(0xd0)
  self.torn_busy=True;self.key(0xd8)
  self.assertEqual(self.torn_actions,[]);self.assertEqual(self.get(self.page+0x188),1)
  self.key(0x86);self.assertEqual(self.torn_actions,[])
 def test_pending_companion_result_blocks_local_session_mutation(self):
  self.ready()
  for _ in range(4):self.key(0xd1)
  self.key(0xd8);self.key(0xd1)
  self.storage_allowed=False;self.key(0xd8)
  self.assertEqual(self.torn_actions,[]);self.assertEqual(self.get(self.page+0x188),1)
  self.storage_allowed=True;self.storage_current=False;self.key(0xd8)
  self.assertEqual(self.torn_actions,[(self.owner,1)]);self.assertEqual(self.get(self.page+0x188),1)
  self.assertEqual(self.saved_settings,[]);self.assertEqual(self.hdf_saved,[])
