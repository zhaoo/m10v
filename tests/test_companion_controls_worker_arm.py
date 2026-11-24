"""Execute R20 diagnostics in the exact shipped ELF while Live is disabled."""
import unittest
from tests import test_companion_formal_worker_arm as formal_fixture
from tests import test_companion_worker_arm as worker_fixture

class ControlsDiagnosticWorkerTests(unittest.TestCase):
    def test_r20_worker_keeps_offline_roll_progress_without_live_requests(self):
        worker=formal_fixture.FormalWorkerTests().machine()
        self.assertEqual(worker.diagnostic_prefix,'R20')
        respond=worker.respond
        def stop_after_roll():
            respond()
            if worker.commands.count(9)>=3:worker.machine.emu_stop()
        worker.respond=stop_after_roll
        worker.execute('_start')
        self.assertGreaterEqual(worker.commands.count(9),3)
        self.assertNotIn(11,worker.commands)
        self.assertNotIn(12,worker.commands)
        self.assertNotIn('m10v_linux_live_sample',worker.symbols)
        self.assertTrue(worker.published_files['/media/storage1/M10V/R20WORK.TXT'])
        self.assertIn('/media/storage1/M10V/R20FAULT.TXT',worker.open_paths)
        self.assertTrue(any(b'R20_ELF_ENTRY' in line for _,line in worker.logs))
        self.assertIsNone(worker.exit_code)

    def test_r20_review_suffix_and_legacy_payloads_are_drained_only_by_worker(self):
        base=bytes(5)+worker_fixture.words(1,*range(12))
        suffix=worker_fixture.words(0x3156524d,4,3,123456,789,0x000002,0x010100,0x000002,12,34)
        handoff=worker_fixture.words(0x3256524d,*sum(([2,100+i,*range(8)]for i in range(6)),[]),*range(7))
        for payload,expected in ((base,False),(base+suffix,True),(base+suffix+handoff,True),
                                 (base+worker_fixture.words(0)+suffix[4:],False),
                                 (base+suffix[:-1],False)):
            with self.subTest(bytes=len(payload),expected=expected):
                worker=formal_fixture.FormalWorkerTests().machine()
                worker.recovery_payload=payload
                respond=worker.respond
                def stop_after_roll():
                    respond()
                    if worker.commands.count(9)>=3:worker.machine.emu_stop()
                worker.respond=stop_after_roll
                worker.execute('_start')
                lines=[line for _,line in worker.logs if b'R20_REVIEW ' in line]
                self.assertEqual(bool(lines),expected)
                if expected:self.assertIn(b'3156524d 00000004 00000003 0001e240 00000315',lines[0])
                self.assertNotIn(11,worker.commands);self.assertNotIn(12,worker.commands)
                stages=[line for _,line in worker.logs if b'R20_STAGE ' in line]
                if len(payload)==369:
                    self.assertGreaterEqual(len(stages),6)
                    self.assertEqual({int(line.split()[2],16)for line in stages},set(range(1,7)))
                    self.assertTrue(any(b'R20_BANK 'in line for _,line in worker.logs))
                else:self.assertEqual(stages,[])


    def test_r20_sd_trace_ram_entry_and_fault_handlers_execute(self):
        for name in ('test_sd_trace_is_published_on_close_before_return',
                     'test_ram_entry_precedes_any_sd_open',
                     'test_fault_logs_pc_and_address_when_inherited_stdout_fails'):
            with self.subTest(name=name):
                worker=worker_fixture.WorkerArmTests(methodName=name)
                worker.setUp()
                self.assertEqual(worker.diagnostic_prefix,'R20')
                getattr(worker,name)()
