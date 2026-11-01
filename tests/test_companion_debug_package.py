"""Opt-in audits against actual compiler outputs; never installs or starts them."""
import hashlib,importlib.util,json,os,shutil,stat,tempfile,unittest,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('package_debug',ROOT/'scripts/package_companion_debug.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
@unittest.skipUnless(os.environ.get('M10V_PACKAGE_APK'),'requires actual APK/native/service outputs')
class DebugPackageTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.d=Path(self.temp.name)
  self.native=Path(os.environ['M10V_PACKAGE_NATIVE']);self.service=Path(os.environ['M10V_PACKAGE_SERVICE']);self.apk=Path(os.environ['M10V_PACKAGE_APK'])
 def test_actual_apk_firmware_service_and_zip_hashes_match(self):
  out=self.d/'delivery';result=module.package_debug(self.native,self.service,self.apk,out)
  self.assertFalse(result['cameraPassed']);self.assertFalse(result['wirelessReady'])
  with zipfile.ZipFile(out.with_suffix('.zip'))as z:
   self.assertIsNone(z.testzip());files={n:z.read(n)for n in z.namelist()}
  for line in files['SHA256SUMS'].decode().splitlines():
   digest,name=line.split('  ',1);self.assertEqual(hashlib.sha256(files[name]).hexdigest(),digest)
  self.assertEqual(stat.S_IMODE(out.with_suffix('.zip').stat().st_mode),0o600)
  self.assertFalse(any(n.endswith('FILMS.M10')or'ModeSet'in n or'DEVELOP.MOD'in n for n in files))
  script=files['02_SERVICE/SD_ROOT/SCRIPT/MCW1101/SERVICE.SH'].decode();self.assertIn('/tmp/m10v-companion-1101.log',script)
  self.assertNotIn('keyHex',files['手机安装说明.txt'].decode())
 def test_other_valid_pairing_key_rejected_before_output(self):
  service=self.d/'service';shutil.copytree(self.service,service)
  path=service/'pairing.json';pair=json.loads(path.read_text());key=bytes.fromhex(pair['keyHex']);key=bytes([key[0]^1])+key[1:];pair['keyHex']=key.hex();pair['keyId']=hashlib.sha256(key).hexdigest()[:32];path.write_text(json.dumps(pair))
  with self.assertRaisesRegex(ValueError,'pairing differs'):module.package_debug(self.native,service,self.apk,self.d/'never')
  self.assertFalse((self.d/'never').exists())
 def test_changed_apk_camera_catalog_rejected_before_output(self):
  apk=self.d/'changed.apk';prefix='assets/flutter_assets/assets/films/'
  with zipfile.ZipFile(self.apk)as original,zipfile.ZipFile(apk,'w')as changed:
   catalog=json.loads(original.read(prefix+'camera-catalog.json'));catalog['entries'][0]['name']='changed'
   changed.writestr(prefix+'camera-catalog.json',json.dumps(catalog));changed.writestr(prefix+'camera-contract.json',original.read(prefix+'camera-contract.json'))
  with self.assertRaisesRegex(ValueError,'APK camera catalog differs'):module.package_debug(self.native,self.service,apk,self.d/'never')
  self.assertFalse((self.d/'never').exists())
