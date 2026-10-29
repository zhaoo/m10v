"""Original address checks, not DMA or silicon acceptance tests."""
import hashlib
import struct
import unittest
from pathlib import Path

from scripts.probe_gr3_border_jpeg_alignment import probe

ROOT = Path(__file__).resolve().parents[1]


class JpegPointerAlignmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.roms = {model: (ROOT / f'builds/gr3-border-iip-20261027/{model}-official-rtos.bin').read_bytes()
                    for model in ('gr3', 'gr3x')}

    def test_exact_official_model_identity_is_required(self):
        for model, rom in self.roms.items():
            for other, data in (('gr4', rom), (None, rom),
                                ('gr3x' if model == 'gr3' else 'gr3', rom),
                                (model, rom[:-1])):
                with self.assertRaises(ValueError):
                    probe(data, other)

    def test_original_driver_preserves_pointer_bits_but_rejects_unaligned_sources(self):
        reports = [probe(rom, model) for model, rom in self.roms.items()]
        self.assertEqual(reports[0]['setter_span'], reports[1]['setter_span'])
        for report in reports:
            for case in report['driver']:
                offset = case['offset']
                self.assertEqual(case['register_values'],
                                 [0x70000000 + offset, 0x74000000 + offset, 0x78000000])
                expected = [] if offset in (0, 8) else [
                    {'caller': 0x537922d0, 'line': 0x373},
                    {'caller': 0x53792328, 'line': 0x378}]
                self.assertEqual(case['assertions'], expected)
                self.assertEqual(case['native_alignment_checks_passed'], offset in (0, 8))
            self.assertFalse(report['hardware_executed'])
            self.assertFalse(report['pixels_mapped'])
            self.assertFalse(report['firmware_emitted'])
            self.assertFalse(report['activation_ready'])

    def test_all_three_original_setters_require_eight_byte_alignment(self):
        # Independently locked instruction/ABI observations; do not derive
        # expected assertions or register addresses from the probe's SETTERS.
        observations = {0x5379228c: (0x298c0430, 0x537922d0, 0x373),
                        0x537922e4: (0x298c0434, 0x53792328, 0x378),
                        0x5379233c: (0x298c0440, 0x53792380, 0x38c)}
        for model, rom in self.roms.items():
            report = probe(rom, model)
            self.assertEqual(report['rtos_sha256'], hashlib.sha256(rom).hexdigest())
            for address in observations:
                self.assertEqual(struct.unpack_from('<I', rom, address - 0x53000000)[0],
                                 0xe3110007)  # Original TST r1,#7.
            self.assertEqual(len(report['setters']), 15)
            for case in report['setters']:
                register, caller, line = observations[case['setter']]
                self.assertEqual(case['register'], register)
                self.assertEqual(case['register_value'], case['pointer'])
                aligned = case['offset'] in (0, 8)
                self.assertEqual(case['assertions'], [] if aligned else [{'caller': caller, 'line': line}])
                self.assertEqual(case['native_alignment_checks_passed'], aligned)


if __name__ == '__main__':
    unittest.main()
