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
  self.options={}
  if os.environ.get('M10V_PACKAGE_PRIOR_PAIRING'):self.options['prior_pairing']=Path(os.environ['M10V_PACKAGE_PRIOR_PAIRING'])
  if os.environ.get('M10V_PACKAGE_FILM_PACK'):self.options['film_pack']=Path(os.environ['M10V_PACKAGE_FILM_PACK'])
 def test_actual_apk_firmware_service_and_zip_hashes_match(self):
  out=self.d/'delivery';result=module.package_debug(self.native,self.service,self.apk,out,**self.options)
  self.assertFalse(result['cameraPassed']);self.assertFalse(result['wirelessReady'])
  with zipfile.ZipFile(out.with_suffix('.zip'))as z:
   self.assertIsNone(z.testzip());files={n:z.read(n)for n in z.namelist()}
  for line in files['SHA256SUMS'].decode().splitlines():
   digest,name=line.split('  ',1);self.assertEqual(hashlib.sha256(files[name]).hexdigest(),digest)
  self.assertEqual(stat.S_IMODE(out.with_suffix('.zip').stat().st_mode),0o600)
  self.assertFalse(any('ModeSet'in n or'DEVELOP.MOD'in n for n in files))
  self.assertEqual(any(n.endswith('FILMS.M10')for n in files),'film_pack'in self.options)
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

 def test_extension_bundle_identity_readme_pairing_and_optional_film_are_hashed(self):
  native=json.loads((self.native/'M10V-runtime-manifest.json').read_text())
  if not native.get('companion',{}).get('extensions'):self.skipTest('legacy v2 package has no extension component')
  options={**self.options,'prior_pairing':self.options.get('prior_pairing',self.service/'pairing.json')}
  out=self.d/'extensions';result=module.package_debug(self.native,self.service,self.apk,out,**options)
  self.assertTrue(result['extensions']['pairingRetained'])
  self.assertEqual(result['extensions']['available'],native['companion']['extensions']['available'])
  with zipfile.ZipFile(out.with_suffix('.zip'))as z:
   contract=z.read('evidence/extensions-contract.json');value=json.loads(contract)
   canonical=json.dumps(value,sort_keys=True,separators=(',',':')).encode()
   self.assertEqual(hashlib.sha256(canonical).hexdigest(),result['extensions']['contractHash'])
   self.assertEqual(z.read('private/pairing.json'),(self.service/'pairing.json').read_bytes())
   self.assertIn('无需重新导入',z.read('手机安装说明.txt').decode())
   for name,meta in result['files'].items():self.assertEqual(hashlib.sha256(z.read(name)).hexdigest(),meta['sha256'])
   if 'film_pack'in options:
    self.assertEqual(z.read('03_FILMS/SD_ROOT/M10V/FILMS.M10'),Path(options['film_pack']).read_bytes())
    self.assertEqual(result['filmPackSha256'],hashlib.sha256(Path(options['film_pack']).read_bytes()).hexdigest())
 def test_prior_pairing_mismatch_rejected_before_any_output(self):
  previous=json.loads((self.service/'pairing.json').read_bytes());previous['instanceId']='aa'*16
  prior=self.d/'prior.json';prior.write_text(json.dumps(previous))
  with self.assertRaisesRegex(ValueError,'prior pairing differs'):
   module.package_debug(self.native,self.service,self.apk,self.d/'never',prior_pairing=prior)
  self.assertFalse((self.d/'never').exists())
 def test_invalid_optional_film_rejected_before_output(self):
  bad=self.d/'FILMS.M10';bad.write_bytes(b'not a film pack')
  with self.assertRaisesRegex(ValueError,'film pack audit failed'):
   module.package_debug(self.native,self.service,self.apk,self.d/'never',film_pack=bad)
  self.assertFalse((self.d/'never').exists())
 def test_extension_apk_without_schema_marker_rejected_before_output(self):
  native=json.loads((self.native/'M10V-runtime-manifest.json').read_text())
  if not native.get('companion',{}).get('extensions'):self.skipTest('legacy v2 package has no extension component')
  apk=self.d/'old-app.apk'
  with zipfile.ZipFile(self.apk)as original,zipfile.ZipFile(apk,'w')as changed:
   for item in original.infolist():
    data=original.read(item.filename)
    if item.filename=='assets/flutter_assets/kernel_blob.bin' or item.filename.endswith('/libapp.so'):
     data=data.replace(b'm10v.extensions/v1',b'm10v.extensions/v0')
    changed.writestr(item,data)
  with self.assertRaisesRegex(ValueError,'APK extension identity differs'):
   module.package_debug(self.native,self.service,apk,self.d/'never')
  self.assertFalse((self.d/'never').exists())
 def test_service_with_previous_extension_contract_rejected_before_output(self):
  native=json.loads((self.native/'M10V-runtime-manifest.json').read_text())
  if not native.get('companion',{}).get('extensions'):self.skipTest('legacy v2 package has no extension component')
  service=self.d/'old-service';shutil.copytree(self.service,service)
  path=service/'m10v-companion.elf';data=path.read_bytes();current=b'c5e4a67763f11333c72f40ceee652919b280ab83235b21a535bc9145b73a224d'
  self.assertIn(current,data);data=data.replace(current,b'f1a60c6593fad7d22ffdbd168c9199567799b2153de15ab84064efcd215f93dc');path.write_bytes(data)
  receipt=service/'service-receipt.json';meta=json.loads(receipt.read_text());meta['serviceSha256']=hashlib.sha256(data).hexdigest();receipt.write_text(json.dumps(meta))
  with self.assertRaisesRegex(ValueError,'service extension identity differs'):
   module.package_debug(self.native,service,self.apk,self.d/'never')
  self.assertFalse((self.d/'never').exists())

class ExtensionDeliveryContractTests(unittest.TestCase):
 def native(self):
  contract=(ROOT/'contracts/extensions-v1.json').read_bytes()
  return {'companion':{'extensions':{'schema':'m10v.extensions/v1','available':(1<<24)-1,'features':dict.fromkeys(['ab','hdf','border','isp','zoom','aspect'],True),'powerImages':'firmwareBuildOnly'},'sources':{'contracts/extensions-v1.json':hashlib.sha256(contract).hexdigest()}}}
 def test_legacy_marker_absence_keeps_v2_delivery(self):
  self.assertTrue(hasattr(module,'_extension_info'),'packager must recognize extension marker independently')
  self.assertIsNone(module._extension_info({'companion':{}}))
 def test_extension_marker_binds_exact_independent_contract(self):
  self.assertTrue(hasattr(module,'_extension_info'),'packager must recognize extension marker independently')
  info=module._extension_info(self.native())
  self.assertEqual(info['contractHash'],'c5e4a67763f11333c72f40ceee652919b280ab83235b21a535bc9145b73a224d')
  self.assertEqual(info['available'],(1<<24)-1)
  for change in ['schema','available','source']:
   native=self.native()
   if change=='schema':native['companion']['extensions']['schema']='future'
   if change=='available':native['companion']['extensions']['available']=1<<24
   if change=='source':native['companion']['sources']['contracts/extensions-v1.json']='00'*32
   with self.subTest(change=change),self.assertRaisesRegex(ValueError,'extension'):
    module._extension_info(native)
 def test_chinese_extension_instructions_cover_controls_and_safe_update(self):
  self.assertTrue(hasattr(module,'_extensions_readme'),'extension delivery instructions are missing')
  text=module._extensions_readme({'buildId':'11'*32},module._extension_info(self.native()),True,False)
  for phrase in ['快切开关','快切 A','快切 B','HDF','边框','颗粒模式','颗粒尺寸','漏光强度','漏光位置','漏光范围','模糊强度','模糊范围','时间水印','日期格式','水印位置','水印颜色','胶卷名称','第一档焦距','第二档焦距','当前焦距档','画幅','只读','重启后默认关闭','两次拍摄','无需重新导入','固件构建','不要重复提交','手动复核','SCRIPT/MCW1101','合并','不要删除整个 SCRIPT','不写入持久模式开关','不能替代真机性能']:
   with self.subTest(phrase=phrase):self.assertIn(phrase,text)
  self.assertNotIn('keyHex',text)
 def test_torn_feature_mask_and_experimental_instructions_are_bound(self):
  native=self.native();native['companion']['extensions']['features']['torn']=True;native['companion']['extensions']['available']=(1<<25)-1
  info=module._extension_info(native);self.assertEqual(info['available'],(1<<25)-1)
  text=module._extensions_readme({'buildId':'11'*32},info,True,False)
  for phrase in ['撕纸叠映','白底暗色','待拍轮廓','待拍素材','原厂 ISP/IIP','YC422','RAW','实验','彩边','不自动','25 项']:
   with self.subTest(phrase=phrase):self.assertIn(phrase,text)
  native['companion']['extensions']['features']['torn']=False
  with self.assertRaisesRegex(ValueError,'extension availability'):module._extension_info(native)
