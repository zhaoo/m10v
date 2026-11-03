"""Exercise original routing and RAM partition construction, never Flash success."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.probe_gr3_anniversary_dispatch import dispatch_case, partition_layout, prepare_combined_cpu, second_stage_decoded
from scripts.probe_gr3_anniversary_downgrade import PROFILES
from scripts.probe_gr3_anniversary_container import source

ROOT = Path(__file__).resolve().parents[1]


class DispatchProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sections = {}
        cls.decoded = {}
        cls.spans = {}
        cls.old = {}
        for model, variable in [('gr3', 'M10V_GR3_220_FIXTURE'), ('gr3x', 'M10V_GR3X_170_FIXTURE')]:
            if os.environ.get(variable):
                _, decoded, _, spans = source(os.environ[variable], model)
                cls.sections[model] = {name: decoded[a:b] for name, (a, b) in spans.items()}
                cls.decoded[model], cls.spans[model] = decoded, spans
                name = 'fwdc239b-gr3-official.bin' if model == 'gr3' else 'fwdc243b-gr3x-official.bin'
                cls.old[model] = second_stage_decoded(ROOT/'bin'/name, model)

    def fixtures(self):
        if len(self.sections) != 2:
            self.skipTest('requires both pinned official anniversary fixtures')
        return self.sections.values()

    def test_combined_cpu_failure_returns_before_dsp_for_every_combined_kind(self):
        for sections in self.fixtures():
            for kind in (2, 3, 4):
                result = dispatch_case(sections['RTOS'], kind, cpu_failure=True)
                self.assertEqual(result['boundary'], 'returned')
                self.assertEqual(result['return_value'], 0)
                self.assertEqual(result['writer_entries'], ['cpu'])
                self.assertFalse(result['flash_write_executed'])
                self.assertEqual(result['fault_injection'], 'CPU writer returns failure (0)')

    def test_routes_stop_before_either_real_writer_is_executed(self):
        for sections in self.fixtures():
            for kind, writer in [(0, 'dsp'), (1, 'dsp'), (2, 'cpu'), (3, 'cpu'), (4, 'cpu'), (6, 'cpu')]:
                result = dispatch_case(sections['RTOS'], kind)
                self.assertEqual(result['boundary'], writer+'_writer_entry')
                self.assertEqual(result['writer_entries'], [writer])
                self.assertFalse(result['writer_body_executed'])
            result = dispatch_case(sections['RTOS'], 5)
            self.assertEqual(result['boundary'], 'returned')
            self.assertEqual(result['return_value'], 0)

    def test_original_disabled_cpu_flag_skips_writer_without_fake_success(self):
        for sections in self.fixtures():
            result = dispatch_case(sections['RTOS'], 2, cpu_enabled=False)
            self.assertEqual(result['writer_entries'], ['dsp'])
            self.assertEqual(result['boundary'], 'dsp_writer_entry')
            self.assertIsNone(result['fault_injection'])
            result = dispatch_case(sections['RTOS'], 2, cpu_enabled=False, dsp_enabled=False)
            self.assertEqual(result['return_value'], 1)
            self.assertEqual(result['writer_entries'], [])

    def test_cpu_enabled_flag_is_validity_not_same_version_skip(self):
        self.fixtures()
        for model, sections in self.sections.items():
            result = prepare_combined_cpu(sections['RTOS'], self.decoded[model], PROFILES[model]['project'])
            self.assertTrue(result['cpu_enabled'])
            self.assertEqual(result['cpu_bytes'], 131072)
            self.assertEqual(result['version_getters_called'], [])
            self.assertFalse(result['flash_write_executed'])
            broken = bytearray(self.decoded[model])
            broken[self.spans[model]['CPU'][0]+0x1000] ^= 1
            rejected = prepare_combined_cpu(sections['RTOS'], broken, PROFILES[model]['project'])
            self.assertFalse(rejected['cpu_enabled'])
            self.assertEqual(rejected['boundary'], 'cpu_flag_written')
            wrong = prepare_combined_cpu(sections['RTOS'], self.decoded[model], PROFILES[model]['project']+1)
            self.assertFalse(wrong['cpu_enabled'])

    def test_exact_old_official_cpu_also_passes_new_updater_local_preparation(self):
        self.fixtures()
        for model, sections in self.sections.items():
            result = prepare_combined_cpu(sections['RTOS'], self.old[model], PROFILES[model]['project'])
            self.assertTrue(result['cpu_enabled'])
            self.assertEqual(result['cpu_bytes'], 131072)
            self.assertFalse(result['flash_write_executed'])
            self.assertEqual(result['version_getters_called'], [])

    def test_original_partpara_builder_matches_all_32_records_and_clamps_count(self):
        for sections in self.fixtures():
            result = partition_layout(sections['RTOS'], sections['PARTPARA'])
            self.assertTrue(result['matches_independent_layout'])
            self.assertEqual(len(result['partitions']), 32)
            self.assertEqual(result['sector_bytes_assumption'], 512)
            self.assertFalse(result['actual_device_geometry_read'])
            self.assertFalse(result['flash_write_executed'])
            clamped = partition_layout(sections['RTOS'], sections['PARTPARA'], count=33)
            self.assertEqual(clamped['partitions'], result['partitions'])
            self.assertEqual(partition_layout(sections['RTOS'], sections['PARTPARA'], count=0)['partitions'], [])

    def test_partition_ceil_and_bank_selection_are_executed_by_original_arm(self):
        for sections in self.fixtures():
            data = bytearray(sections['PARTPARA'])
            data[4] ^= 1  # first size becomes non-sector-aligned
            result = partition_layout(sections['RTOS'], data, count=2, bank=1)
            self.assertTrue(result['matches_independent_layout'])
            self.assertEqual(result['partitions'][1]['start_sector'], 1536+897)

    def test_invalid_inputs_and_modified_dispatch_code_are_rejected(self):
        for sections in self.fixtures():
            rom = bytearray(sections['RTOS'])
            rom[0x628e34] ^= 1
            with self.assertRaisesRegex(ValueError, 'code identity differs'):
                dispatch_case(rom, 2)
            with self.assertRaisesRegex(ValueError, 'footer kind'):
                dispatch_case(sections['RTOS'], 7)
            with self.assertRaisesRegex(ValueError, 'PARTPARA length'):
                partition_layout(sections['RTOS'], b'')

    def test_second_stage_cannot_use_the_other_models_official_package(self):
        self.fixtures()
        for model, other in [('gr3', 'fwdc243b-gr3x-official.bin'), ('gr3x', 'fwdc239b-gr3-official.bin')]:
            with self.assertRaisesRegex(ValueError, 'official source SHA-256 differs'):
                second_stage_decoded(ROOT/'bin'/other, model)

    def test_cli_rejects_bin_and_existing_report_before_reading_input(self):
        with tempfile.TemporaryDirectory() as directory:
            for name, existing in [('output.bin', False), ('report.json', True)]:
                report = Path(directory)/name
                if existing:
                    report.write_text('keep')
                result = subprocess.run([sys.executable, '-m', 'scripts.probe_gr3_anniversary_dispatch',
                    '--new', 'missing.bin', '--old', 'missing.bin', '--model', 'gr3', '--report', str(report)],
                    cwd=ROOT, capture_output=True, text=True)
                self.assertEqual(result.returncode, 1)
                self.assertNotIn('No such file', result.stdout)
                self.assertEqual(report.read_text() if existing else report.exists(), 'keep' if existing else False)


if __name__ == '__main__':
    unittest.main()
