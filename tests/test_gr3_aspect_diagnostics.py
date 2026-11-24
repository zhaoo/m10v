"""Validate the R17 aspect diagnostic schema and its real ARM producers."""
import json
import os
from pathlib import Path
import struct
import unittest
import zlib

from scripts.read_gr3_debug_log import ASPECT_DIAGNOSTIC_FIELDS, EVENTS, page_records
from tests import test_gr3_aspect_formal as formal


def diagnostic_page(events):
    page = bytearray(4096)
    build = 0x17a50001
    for index, (event, arguments) in enumerate(events):
        record = [0x474c564d, 1, index + 1, event, *arguments, build, 1, 0, 0, 0, 0, 0, 0]
        raw = bytearray(struct.pack('<16I', *record))
        struct.pack_into('<I', raw, 60, zlib.crc32(raw[:60]))
        page[64 + 64 * index:128 + 64 * index] = raw
    header = [0x4744564d, 1, build, len(events), len(events), len(events), 1, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    struct.pack_into('<16I', page, 0, *header)
    struct.pack_into('<I', page, 60, zlib.crc32(page[:60]))
    return bytes(page)


class AspectDiagnosticDecoder(unittest.TestCase):
    def test_crc_page_preserves_every_diagnostic_field_and_stage(self):
        events = [(event, [event, 0x55063f30, 6, 1]) for event in ASPECT_DIAGNOSTIC_FIELDS]
        _, records = page_records(diagnostic_page(events))
        self.assertEqual(len(records), len(events))
        for record, (event, arguments) in zip(records, events):
            self.assertEqual(record['stage'], EVENTS[event])
            self.assertEqual(record['channel'], 'menu')
            decoded = record['aspect_diagnostic']
            self.assertTrue(decoded.pop('diagnostic_only'))
            self.assertEqual(decoded, dict(zip(ASPECT_DIAGNOSTIC_FIELDS[event], arguments)))


class AspectDiagnosticArm(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        candidate = os.environ.get('M10V_MENU_HUB_CANDIDATE')
        if not candidate:
            raise unittest.SkipTest('R17 debug final BIN required')
        manifest = json.loads((Path(candidate) / 'M10V-runtime-manifest.json').read_text())
        if not manifest.get('debug_mode') or not manifest.get('debug_log'):
            raise unittest.SkipTest('R17 debug final BIN required; formal logging is disabled')
        formal.FormalAspectSelection.setUpClass()

    def test_installed_selector_logs_requested_properties_owner_and_real_readback(self):
        device = formal.FormalAspectSelection('test_session_default_rejects_half_and_preserves_xpan')
        device.setUp()
        camera, symbols = device.camera, device.symbols
        observed = []

        def collect():
            registers = camera.A
            event = camera.u.reg_read(registers.UC_ARM_REG_R0)
            arguments = [camera.u.reg_read(reg) for reg in (
                registers.UC_ARM_REG_R1, registers.UC_ARM_REG_R2, registers.UC_ARM_REG_R3)]
            arguments += camera.read_words(camera.u.reg_read(registers.UC_ARM_REG_SP), 1)
            observed.append((event, arguments))
            return 0

        camera.boundaries[symbols['m10v_debug_log']] = collect
        camera.call(symbols['m10v_settings_half_set'], 1)
        for row, raw in ((4, 4), (6, 6)):
            observed.clear()
            camera.call(device.menu[6], 0, row)
            records = dict(observed)
            self.assertEqual(records[400][0:2], [device.model, raw])
            self.assertEqual(records[400][3], 1)
            self.assertEqual(records[401][0:2], [device.model, formal.support.PROPERTIES])
            self.assertEqual(records[401][3], 1)
            self.assertEqual(records[402], [device.model, raw, 1, raw])
            self.assertEqual(records[413][0:2], [formal.support.OWNER] * 2)
            self.assertEqual(records[413][2], 0x37535048)
            self.assertEqual(records[417][0], device.model)
            self.assertNotEqual(records[417][1], 0)
