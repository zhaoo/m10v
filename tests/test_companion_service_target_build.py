import hashlib,importlib.util,json,os,shutil,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('builder',ROOT/'scripts/build_companion_service.py');builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
class ServiceTargetBuildTests(unittest.TestCase):
 def test_rejects_changed_firmware_before_creating_pairing_material(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'fwdc239b.bin').write_bytes(b'changed')
   (p/'M10V-build-receipt.json').write_text(json.dumps({'filename':'fwdc239b.bin','candidate_sha256':hashlib.sha256(b'expected').hexdigest()}))
   with self.assertRaisesRegex(ValueError,'candidate hash'):
    builder.build_service(p/'out',catalog_hash='22'*32,renderer_hash='33'*32,candidate_dir=p)
   self.assertFalse((p/'out').exists())
 def test_rejects_candidate_path_escape(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'M10V-build-receipt.json').write_text(json.dumps({'filename':'../anything','candidate_sha256':'11'*32}))
   with self.assertRaisesRegex(ValueError,'filename'):
    builder.build_service(p/'out',catalog_hash='22'*32,renderer_hash='33'*32,candidate_dir=p)

 def test_independent_extension_routes_fit_static_and_reachable_stack_budget(self):
  with tempfile.TemporaryDirectory() as d:
   receipt=builder.build_service(Path(d)/'service',catalog_hash='03'*32,renderer_hash='04'*32,key=bytes(range(32)),instance_id=bytes(range(16)))
   self.assertLessEqual(receipt['reachableStackBoundBytes'],4096)
   self.assertLessEqual(receipt['stagingStaticBytes']+4096,65536)
   self.assertFalse(receipt['cameraPassed'])

@unittest.skipUnless(os.environ.get('M10V_GREMOTE_PACKAGE_NATIVE'),'requires a real audited GR III companion candidate')
class ServiceEmbeddedIdentityTests(unittest.TestCase):
 def test_both_json_identities_cannot_relabel_unchanged_runtime(self):
  source=Path(os.environ['M10V_GREMOTE_PACKAGE_NATIVE'])
  for field in ['buildId','catalogHash','rendererHash']:
   with self.subTest(field=field),tempfile.TemporaryDirectory() as d:
    p=Path(d)
    for target,names in {'fwdc239b.bin':['fwdc239b.bin','01_FIRMWARE/SD_ROOT/fwdc239b.bin'],'M10V-build-receipt.json':['M10V-build-receipt.json','evidence/firmware-receipt.json'],'M10V-runtime-manifest.json':['M10V-runtime-manifest.json','evidence/runtime-manifest.json']}.items():
     shutil.copy2(next(source/n for n in names if (source/n).is_file()),p/target)
    path=p/'M10V-runtime-manifest.json';m=json.loads(path.read_text());m['companion']['identity'][field]='11'*32;path.write_text(json.dumps(m))
    path=p/'M10V-build-receipt.json';r=json.loads(path.read_text());r['companion_identity'][field]='11'*32;path.write_text(json.dumps(r))
    ident=m['companion']['identity']
    with self.assertRaisesRegex(ValueError,'embedded.*identity|runtime.*identity'):
     builder._target_metadata(p,ident['catalogHash'],ident['rendererHash'])
    self.assertFalse((p/'service').exists())
