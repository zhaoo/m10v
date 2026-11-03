import json, subprocess, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class CompanionExportCliTests(unittest.TestCase):
 def test_invalid_identity_fails_before_reading_firmware(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'identity.json';p.write_text(json.dumps({'buildId':'0'*64,'catalogHash':'11'*32,'rendererHash':'22'*32}))
   r=subprocess.run(['node','scripts/export_gr3_m10v_native.mjs','--companion-identity='+str(p),'--source=/nonexistent-camera.bin',d],cwd=ROOT,text=True,capture_output=True)
   self.assertNotEqual(r.returncode,0)
   self.assertIn('invalid companion identity',r.stderr)
   self.assertNotIn('ENOENT',r.stderr)
