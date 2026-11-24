import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
try:
    spec=importlib.util.spec_from_file_location('controls_packager',ROOT/'scripts/package_gr3_controls_log.py')
    packager=importlib.util.module_from_spec(spec);spec.loader.exec_module(packager)
finally:sys.path.pop(0)

class ControlsPackageTests(unittest.TestCase):
    def test_rejects_formal_firmware_and_any_live_producer_before_service_build(self):
        base={'roll_capture':True,'menu_hub':True,'debug_mode':True,'debug_scope':'controls','debug_log':{'build_id':17,'adj_exit_trace':True},
              'companion':{'debug_mode':True,'extensions':{'features':{'live':False}}},'symbols':{}}
        cases=[({**base,'debug_mode':False},'debug mode'),
               ({**base,'companion':{'debug_mode':False,'extensions':{'features':{'live':False}}}},'debug mode'),
               ({**base,'companion':{'debug_mode':True,'extensions':{'features':{'live':True}}}},'Live disabled'),
               ({**base,'symbols':{'m10v_live_device_camera':0x540b6000}},'producer')]
        for native,reason in cases:
            with self.subTest(native=native),tempfile.TemporaryDirectory() as directory:
                out=Path(directory)/'R20.zip'
                with patch.object(packager,'_candidate',return_value=({},b'fw',native,{})),patch.object(packager,'build_service') as build:
                    with self.assertRaisesRegex(ValueError,reason):packager.package(Path(directory),Path(directory)/'missing.apk',out)
                    build.assert_not_called();self.assertFalse(out.exists())

    def test_r20_launch_is_once_per_boot_and_retains_r20_markers(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);service=root/'service';service.mkdir();logs=root/'logs';logs.mkdir()
            count=root/'count';lock=root/'lock';ram=root/'ram';ram.write_text('R20 RAM\n')
            executable=service/'SERVICE.BIN'
            executable.write_text('#!/bin/sh\necho ran >>"'+str(count)+'"\nexit 0\n');executable.chmod(0o700)
            script=packager.R20_START
            for old,new in [('/media/storage1/SCRIPT/MCW1101',service),('/media/storage1/M10V',logs),
                            ('/tmp/m10v-companion-1101.lock',lock),('/tmp/m10v-worker-1101.log',ram)]:
                script=script.replace(old.encode(),str(new).encode())
            self.assertNotIn(b'R16',script)
            for _ in range(2):self.assertEqual(subprocess.run(['sh'],input=script,capture_output=True).returncode,0)
            for _ in range(100):
                if (logs/'R20BOOT.TXT').exists() and 'R20_SERVICE_EXIT_0' in (logs/'R20BOOT.TXT').read_text():break
                time.sleep(.01)
            self.assertEqual(count.read_text().splitlines(),['ran'])
            self.assertIn('R20_EXEC_SD_BEGIN',(logs/'R20BOOT.TXT').read_text())
            self.assertEqual((logs/'R20RAM.TXT').read_text(),'R20 RAM\n')
            self.assertIn(b'R20TTL.TXT',packager.R20_TTL)
            self.assertNotIn(b'R16',packager.R20_TTL)
