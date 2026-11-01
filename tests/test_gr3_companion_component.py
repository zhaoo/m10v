import importlib.util,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class Component(unittest.TestCase):
 def test_compiles_relocatable_owner_with_all_runtime_imports_and_identity(self):
  path=ROOT/'scripts/build_gr3_companion_owner.py';self.assertTrue(path.exists(),'missing optional companion component builder')
  spec=importlib.util.spec_from_file_location('component',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  symbols={name:0x54010000+i*64 for i,name in enumerate(['m10v_camera_library_read_current','m10v_camera_library_mutation_begin','m10v_camera_library_mutation_end','m10v_camera_library_mutation_busy','m10v_camera_library_commit_snapshot','m10v_sd_camera_custom_record','m10v_library_valid'])}
  with tempfile.TemporaryDirectory()as tmp:
   code,report=module.build_companion_owner(0x54100000,symbols,{'buildId':'11'*32,'catalogHash':'22'*32,'rendererHash':'33'*32},Path(tmp))
   self.assertGreater(len(code),1024);self.assertLess(len(code),65536);self.assertEqual(report['descriptor_offset'],0x6400)
   for name in ['init','start','stop','timer']:self.assertIn('m10v_companion_ui_'+name,report['symbols'])
   with self.assertRaises(ValueError):module.build_companion_owner(0x54100000,symbols,{'buildId':'00'},Path(tmp))

 def test_native_builder_rejects_invalid_identity_before_building(self):
  from scripts.build_gr3_m10v_library import build
  with tempfile.TemporaryDirectory()as tmp:
   with self.assertRaisesRegex(ValueError,'identity'):build(Path(tmp)/'never',companion_identity={'buildId':'wrong'})
   self.assertFalse((Path(tmp)/'never').exists())
