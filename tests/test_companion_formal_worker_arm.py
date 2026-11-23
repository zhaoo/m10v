"""Run the shipped formal service: offline roll progress without Live or logging."""
import os
from pathlib import Path
import struct
import unittest
from tests import test_companion_worker_arm as worker_fixture
words = worker_fixture.words

class FormalWorkerTests(unittest.TestCase):
    def machine(self):
        if not os.environ.get('M10V_TEST_SERVICE_ELF'):
            self.skipTest('requires the exact formal service ELF')
        worker = worker_fixture.WorkerArmTests(methodName='runTest')
        worker.setUp()
        config_address = worker.symbols['target_config']
        worker.config = bytes(worker.machine.mem_read(config_address, 180))
        owner, context = 0x56000000, 0x56010000
        worker.put(0x55063910, words(1))
        worker.put(0x55063988, words(owner))
        worker.put(owner + 0x6400, words(0x3244494d, 2, 64, context,
                   worker.wire, 2432, context) + bytes(36))
        worker.put(worker.wire, words(0x32434d4d, 2, 2432, 1, owner, context) + worker.config[:32] + bytes(72))
        for index, address in enumerate((0x5316fcf8, 0x5319667c, 0x5383c834, 0x5383c870)):
            worker.put(address, worker.config[112 + index * 16:128 + index * 16])
        return worker

    def assert_quiet(self, worker):
        self.assertEqual(worker.logs, [])
        self.assertEqual(worker.open_paths, [])
        self.assertEqual(worker.actions, {})
        self.assertNotIn(11, worker.commands)
        self.assertNotIn(12, worker.commands)
        self.assertNotIn('m10v_linux_live_sample', worker.symbols)
        self.assertNotIn('m10v_linux_diagnostics_start', worker.symbols)

    def test_offline_roll_polls_without_live_or_diagnostic_io(self):
        worker = self.machine()
        respond = worker.respond
        def stop_after_roll():
            respond()
            if worker.commands.count(9) >= 3:
                worker.machine.emu_stop()
        worker.respond = stop_after_roll
        worker.execute('_start')
        self.assertGreaterEqual(worker.commands.count(9), 3)
        self.assertIsNone(worker.exit_code)
        self.assert_quiet(worker)

    def test_formal_worker_reaches_hotspot_listener_without_logs(self):
        worker = self.machine()
        worker.wifi_up = True
        worker.stop_on_listen = True
        worker.execute('_start')
        self.assertTrue(any(number == 284 for number, _ in worker.calls))
        self.assertIn(1, worker.commands)
        self.assertIn(9, worker.commands)
        self.assert_quiet(worker)
