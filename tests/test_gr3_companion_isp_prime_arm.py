"""Production AppMain timer recovers a cold ISP cache without a remote write."""
import unittest
from tests import test_gr3_companion_ui_owner_arm as owner_support

class ColdIspOwner(unittest.TestCase):
 setUpClass=classmethod(owner_support.ProductionOwner.setUpClass.__func__)
 exchange=owner_support.ProductionOwner.exchange
 feature_flags=['-DM10V_COMPANION_EXT_ISP=1']
 native_sources=['native/gr3/m10v_isp_effects_state.c']
 extra_ports=['m10v_isp_effects_camera_snapshot','m10v_isp_effects_camera_save','m10v_isp_effects_camera_refresh']
 def machine(self):
  m=owner_support.ProductionOwner.machine(self);m.isp_warm=False;m.fs_ready=False;m.isp_refreshes=0
  return m
 def extra_port(self,m,pc,args):
  if pc==self.ports['m10v_isp_effects_camera_snapshot']:
   if m.isp_warm:m.u.mem_write(args[0],bytes(32));m.set(args[1],1)
   return int(m.isp_warm)
  if pc==self.ports['m10v_isp_effects_camera_refresh']:
   self.assertEqual(args[0],0x55860000);m.isp_refreshes+=1
   m.isp_warm=m.fs_ready
   return 0 if m.isp_warm else 0xffffffff
  self.fail('read-side priming must never save ISP settings')
 def test_cold_filesystem_recovers_on_owner_timer_and_warm_cache_is_untouched(self):
  m=self.machine();m.run(self.symbols['m10v_companion_ui_init'],0x55860000)
  m.run(self.symbols['m10v_companion_ui_start'],0x55860000)
  wire=m.word(0x55860000+0x6400+16)
  code,_=self.exchange(m,wire,2,1,bytes([7]*16));self.assertEqual(code,0)
  code,_=self.exchange(m,wire,4,5);self.assertNotEqual(code,0)
  m.fs_ready=True
  for _ in range(12):
   m.alarm_active=False;m.queue_timer_wakeup();m.drain_on_appmain()
  code,data=self.exchange(m,wire,6,5);self.assertEqual(code,0)
  self.assertEqual(int.from_bytes(data[12:16],'little')&(1<<21),1<<21)
  self.assertGreaterEqual(m.isp_refreshes,1)
  before=m.isp_refreshes
  self.assertEqual(self.exchange(m,wire,8,5)[0],0)
  self.assertEqual(m.isp_refreshes,before);self.assertEqual(m.saves,0)
