"""Offline private package checks. No installation, service launch or publication."""
import hashlib,importlib.util,json,os,shutil,stat,tempfile,unittest,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'scripts/package_gremote_connection.py'

def load():
 spec=importlib.util.spec_from_file_location('gremote_package',SCRIPT)
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

class PackageBoundaryTests(unittest.TestCase):
 def test_public_packager_exists(self):self.assertTrue(SCRIPT.is_file(),'GRemote package builder is missing')
 def test_rejects_unsupported_model_without_creating_output_or_pairing(self):
  self.assertTrue(SCRIPT.is_file(),'GRemote package builder is missing');module=load()
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);candidate=p/'candidate';candidate.mkdir()
   receipt={'model':'GR IIIx','camera_model':'gr3x','public_version':'1.60','filename':'fwdc243b.bin'}
   (candidate/'M10V-build-receipt.json').write_text(json.dumps(receipt))
   with self.assertRaisesRegex(ValueError,'GR III 2.10'):module.package_connection(candidate,p/'never.zip')
   self.assertFalse((p/'never.zip').exists());self.assertEqual(sorted(x.name for x in p.iterdir()),['candidate'])

@unittest.skipUnless(os.environ.get('M10V_GREMOTE_PACKAGE_NATIVE'),'requires a real audited GR III companion candidate')
class ActualConnectionPackageTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.module=load();cls.temp=tempfile.TemporaryDirectory();cls.d=Path(cls.temp.name)
  source=Path(os.environ['M10V_GREMOTE_PACKAGE_NATIVE']);cls.candidate=cls.d/'candidate';cls.candidate.mkdir()
  for target,names in {'fwdc239b.bin':['fwdc239b.bin','01_FIRMWARE/SD_ROOT/fwdc239b.bin'],'M10V-build-receipt.json':['M10V-build-receipt.json','evidence/firmware-receipt.json'],'M10V-runtime-manifest.json':['M10V-runtime-manifest.json','evidence/runtime-manifest.json']}.items():
   src=next(source/n for n in names if (source/n).is_file());shutil.copy2(src,cls.candidate/target)
  cls.outputs=[]
  for index in range(2):
   out=cls.d/f'connection-{index}.zip';meta=cls.module.package_connection(cls.candidate,out);cls.outputs.append((out,meta))
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()
 def test_no_static_pairing_and_unique_service_instances(self):
  services=[]
  for out,meta in self.outputs:
   with zipfile.ZipFile(out) as z:
    self.assertNotIn('private/pairing.json',z.namelist())
    elf=z.read('02_SERVICE/SD_ROOT/SCRIPT/MCW1101/SERVICE.BIN')
    receipt=json.loads(z.read('evidence/service-receipt.json'))
   self.assertEqual(receipt['pairingPolicy'],'camera-hotspot-per-boot')
   self.assertEqual(receipt['serviceSha256'],hashlib.sha256(elf).hexdigest())
   self.assertEqual(meta['pairing_policy'],'camera-hotspot-per-boot')
   services.append(elf)
  self.assertNotEqual(*services)
 def test_archive_paths_hashes_instructions_and_safety(self):
  out,meta=self.outputs[0]
  self.assertEqual(stat.S_IMODE(out.stat().st_mode),0o600)
  self.assertLessEqual(out.stat().st_size,70*1024*1024)
  with zipfile.ZipFile(out) as z:
   self.assertIsNone(z.testzip());names=z.namelist();self.assertEqual(len(names),len(set(names)))
   self.assertFalse(any(n.startswith('/') or '..' in Path(n).parts or n.endswith('.apk') or 'ModeSet' in n or 'DEVELOP.MOD' in n for n in names))
   self.assertIn('03_FILMS/SD_ROOT/M10V/FILMS.M10',names)
   manifest=json.loads(z.read('manifest.json'));self.assertFalse(manifest['camera_tested']);self.assertFalse(manifest['installation_allowed'])
   for line in z.read('SHA256SUMS').decode().splitlines():
    digest,name=line.split('  ',1);self.assertEqual(hashlib.sha256(z.read(name)).hexdigest(),digest)
   for name,item in manifest['files'].items():self.assertEqual(hashlib.sha256(z.read(name)).hexdigest(),item['sha256'])
   text=z.read('开始前必读.txt').decode()
   for phrase in ['GR III 2.10','IIIx','尚未通过','自动建立会话','不要直接覆盖','不要删除整个 SCRIPT','不自动','GRemote','无需导入','备份','回退']:
    with self.subTest(phrase=phrase):self.assertIn(phrase,text)
   self.assertNotIn('keyHex',text)
   self.assertIn('/tmp/m10v-companion-1101.lock',z.read('02_SERVICE/SD_ROOT/SCRIPT/MCW1101/SERVICE.SH').decode())
  self.assertEqual(meta['sha256'],hashlib.sha256(out.read_bytes()).hexdigest())
 def test_mismatched_identity_and_changed_firmware_fail_before_output(self):
  for field in ['identity','both-buildId','both-catalogHash','both-rendererHash','firmware']:
   with self.subTest(field=field),tempfile.TemporaryDirectory() as d:
    p=Path(d);candidate=p/'candidate';shutil.copytree(self.candidate,candidate)
    if field=='identity':
     path=candidate/'M10V-build-receipt.json';r=json.loads(path.read_text());r['companion_identity']['buildId']='11'*32;path.write_text(json.dumps(r))
    elif field.startswith('both-'):
     key=field.split('-',1)[1]
     path=candidate/'M10V-build-receipt.json';r=json.loads(path.read_text());r['companion_identity'][key]='11'*32;path.write_text(json.dumps(r))
     path=candidate/'M10V-runtime-manifest.json';m=json.loads(path.read_text());m['companion']['identity'][key]='11'*32;path.write_text(json.dumps(m))
    else:
     path=candidate/'fwdc239b.bin';b=bytearray(path.read_bytes());b[100]^=1;path.write_bytes(b)
    with self.assertRaisesRegex(ValueError,'identity|firmware'):self.module.package_connection(candidate,p/'never.zip')
    self.assertFalse((p/'never.zip').exists())
