"""Execute the disabled A/B gate while retaining the existing film lifecycle tests."""
from tests import test_gr3_settings_controller as controller


class AbDisabledTests(controller.ControllerLifetimeTests):
 ab_enabled=False

 def test_disabled_gate_never_reads_picker_payload_or_opens_private_route(self):
  u=self.machine()
  self.assertEqual(self.call(u,'ab_available'),0)
  self.events=[]
  # An unmapped event pointer proves the off path does not inspect the event.
  self.assertEqual(self.call(u,'ab_setup',0,0xdead0000,0x02000012),0)
  self.assertEqual(self.events,[])
  self.assertEqual(self.call(u,'factory',0,0x0200f104),self.fallback)


def load_tests(loader, tests, pattern):
 # The parent fixture supplies the emulator; its legacy tests run in their own module.
 import unittest
 return unittest.TestSuite([AbDisabledTests('test_disabled_gate_never_reads_picker_payload_or_opens_private_route')])
