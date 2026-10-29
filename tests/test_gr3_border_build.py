"""Opt-in menu/cache build must remain independent of HDF and hardware output."""
import tempfile, unittest
from pathlib import Path
from scripts.build_gr3_m10v_library import build

class BorderBuildTests(unittest.TestCase):
 def test_enabled_border_without_hdf_keeps_owned_menu_and_explicit_unready_pipeline(self):
  with tempfile.TemporaryDirectory() as out:
   m=build(out,sd_library=True,hdf_enabled=False,border_enabled=True)
   self.assertTrue(m['border']['enabled']);self.assertFalse(m['border']['hardware_ready'])
   self.assertFalse(m['border']['pixel_pipeline_enabled']);self.assertFalse(m['hdf_enabled'])
   self.assertEqual(m['border']['cache_owner_offset'],0x22e4)
   self.assertEqual(m['hdf_menu']['owner_offset'],0x213c)
   self.assertEqual(m['hdf_menu']['route'],0x0200f102)
   self.assertEqual(m['hdf_menu']['effects_children'],['Border'])
   self.assertEqual(m['resources']['texts'][1155-786:1158-786],['边框','拍立得','胶卷'])
   for name in ('refresh','save','cached','snapshot'):
    self.assertIn('m10v_border_camera_'+name,m['symbols'])
   self.assertNotIn('m10v_hdf_load',m['symbols'])
   for name in ('native/gr3/m10v_border_camera.c','native/gr3/m10v_border_camera.h','native/gr3/m10v_border.h'):
    self.assertIn(name,m['sources'])
   self.assertFalse(list(Path(out).glob('fwdc*.bin')))
   self.check_startup_loads_saved_border_before_effects_is_opened(m,out)
 def check_startup_loads_saved_border_before_effects_is_opened(self,m,out):
  from tests.test_gr3_border_camera import BorderCameraTests
  from unicorn import UC_HOOK_CODE
  from unicorn import arm_const as A
  e=BorderCameraTests();e.base=m['base'];e.code=(Path(out)/'m10v-library-arm.bin').read_bytes();e.symbols=m['symbols'];e.setUp()
  e.page=e.owner+0x213c;e.cache=e.owner+0x22e4
  original=m['settings_menu']['exports']
  def ui_services(u,at,n,d):
   result=None
   if at==original['m10v_settings_factory_original']:result=e.owner
   elif at==original['m10v_ab_live_enter_original']:result=0x1234
   elif at in (m['symbols']['m10v_camera_library_reconcile_legacy_selection'],m['symbols']['m10v_camera_library_load']):result=0
   elif at==0x5320ad88:result=0x55003000
   elif at==0x5320ba9c:result=0x55068200
   if result is not None:u.reg_write(A.UC_ARM_REG_R0,result);u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
  e.u.hook_add(UC_HOOK_CODE,ui_services)
  e.call('m10v_hdf_menu_top_ctor',e.owner)
  e.files['BORDERB.BIN']=e.record(5,2)
  self.assertEqual(e.call('m10v_border_camera_snapshot',0x55007000),0)
  e.call('m10v_settings_controller_ab_live_enter',0x55008000,0x08000001,0)
  self.assertEqual(e.reads,[],'other UI routes must not perform border initialization')
  self.assertEqual(e.call('m10v_settings_controller_ab_live_enter',0x55008000,0x08000000,0),0x1234)
  self.assertEqual(e.call('m10v_border_camera_snapshot',0x55007000),1);self.assertEqual(e.get(0x55007000),2)
  self.assertEqual(e.reads,['BORDERA.BIN','BORDERB.BIN']);self.assertEqual(e.writes,[])
  e.call('m10v_settings_controller_ab_live_enter',0x55008000,0x08000000,0)
  self.assertEqual(e.reads,['BORDERA.BIN','BORDERB.BIN'],'normal UI return must not reload a ready border cache')
 def test_default_build_has_no_border_backend_and_preserves_resource_count(self):
  with tempfile.TemporaryDirectory() as out:
   m=build(out,sd_library=True)
   self.assertFalse(m['border']['enabled']);self.assertFalse(m['border']['pixel_pipeline_enabled'])
   self.assertNotIn('m10v_border_camera_snapshot',m['symbols'])
   self.assertEqual(len(m['resources']['texts']),1155-786)
 def test_snapshot_owner_cache_moves_border_cache_without_overlap(self):
  with tempfile.TemporaryDirectory() as out:
   m=build(out,sd_library=True,hdf_enabled=False,border_enabled=True,
           recipe_snapshot=True,lifecycle_trace=True,debug_mode=True)
   self.assertEqual(m['hdf_menu']['owner_offset'],0x223c)
   self.assertEqual(m['border']['cache_owner_offset'],0x23e4)
   self.assertEqual(m['hdf_menu']['owner_bytes'],0x23fc)
   self.assertTrue(m['capture_lifecycle']['snapshot']['snapshot_ingress_installed'])
   self.assertTrue(m['border']['snapshot_installed'])
   self.assertEqual(m['border']['shot_offset'],0x510c)
   for name in ('freeze','read','orientation'):
    self.assertIn('m10v_border_shot_'+name,m['symbols'])
   self.check_real_task_ingress_freezes_border(m,out)
 def check_real_task_ingress_freezes_border(self,m,out):
  import struct
  from tests.test_gr3_isp_base import StockISP
  from tests.test_gr3_film_pipeline_current import CurrentFilmPipelineTests
  from unicorn import arm_const as A
  rom=bytearray(Path('builds/gr3-extension-validation/official-rtos.bin').read_bytes())
  runtime=(Path(out)/'m10v-library-arm.bin').read_bytes();offset=m['base']-0x53000000
  if len(rom)<offset+len(runtime):rom.extend(bytes(offset+len(runtime)-len(rom)))
  rom[offset:offset+len(runtime)]=runtime
  # Only the real task-submission entry is patched for this bounded test.
  patch=next(p for p in m['capture_lifecycle']['snapshot']['patches'] if p['address']==0x5351ea9c)
  at=patch['address']-0x53000000
  self.assertEqual(rom[at:at+4],bytes.fromhex(patch['expected_hex']))
  rom[at:at+4]=bytes.fromhex(patch['replacement_hex'])
  e=StockISP(bytes(rom));recipe=e.alloc(0x5140);e.w32(recipe,0x53d0fc90);e.w32(recipe+0x4778,0x31545653)
  si=e.alloc(0x74270);e.w32(recipe+0x44c8,si);e.u.mem_write(si+0x77c,b'\x0b')
  e.u.mem_write(si+0xc8,b'\x03')
  owner=e.alloc(0x2400);e.w32(0x55063910,1);e.w32(0x55063988,owner)
  state=e.alloc(184);e.call(m['symbols']['m10v_library_init'],state)
  e.w32(owner+0x213c,0x3856504d);e.w32(owner+0x2140,2)
  e.u.mem_write(owner+0x2144,bytes(e.u.mem_read(state,184)))
  border=owner+m['border']['cache_owner_offset'];e.w32(border,0x3143424d);e.w32(border+4,2)
  e.w32(border+8,1);e.w32(border+12,7)
  runner=CurrentFilmPipelineTests();runner.manifest=m
  for kind in (19,0,16,1,8,9,2,4,6):
   runner.enqueue(e,recipe,kind)
   e.w32(border+8,2);e.w32(border+4,4)
   e.u.mem_write(si+0xc8,b'\x01')
   output=e.alloc(4);e.w32(output,99)
   e.call(m['symbols']['m10v_border_shot_read'],recipe,output)
   self.assertEqual(e.u.reg_read(A.UC_ARM_REG_R0),1)
   self.assertEqual(int.from_bytes(e.u.mem_read(output,4),'little'),1)
   e.call(m['symbols']['m10v_border_shot_orientation'],recipe,output)
   self.assertEqual(e.u.reg_read(A.UC_ARM_REG_R0),1)
   self.assertEqual(int.from_bytes(e.u.mem_read(output,4),'little'),6)
  self.assertEqual(bytes(e.u.mem_read(recipe+0x5110,48)),bytes(48),'RAW/HDF owner untouched')
  # Isolated dedup contract, not a claim that image hardware completed:
  # a later JPEG call must not apply residual processing for a second time.
  request=e.alloc(0x40);e.w32(request,0x53d0fe60);e.u.mem_write(request+12,b'\x01\x01')
  e.w32(recipe+0x5c,request);e.w32(recipe+0x9b8,0x53d0fbe0)
  e.call(0x5350e624,recipe,6);e.u.mem_write(recipe+0x140,b'\x01')
  for old,new in ((0,1),(1,2)):
   e.call(m['symbols']['m10v_border_shot_transition'],recipe,old,new)
   self.assertEqual(e.u.reg_read(A.UC_ARM_REG_R0),1)
   if new==1:
    e.call(m['symbols']['m10v_capture_library'],recipe+0x9b8)
    self.assertEqual(e.u.reg_read(A.UC_ARM_REG_R0),(-14)&0xffffffff,
                     'owned early stock bypass is distinct from a processing error')
  for phase in (2,3):
   e.call(m['symbols']['m10v_capture_library'],recipe+0x9b8)
   self.assertEqual(e.u.reg_read(A.UC_ARM_REG_R0),0)
   if phase==2:e.call(m['symbols']['m10v_border_shot_transition'],recipe,2,3)
 def test_invalid_capability_options_fail_before_building(self):
  for options in ({'border_enabled':1},{'border_enabled':True},{'border_enabled':True,'sd_library':True,'film_library':False}):
   with self.subTest(options=options),tempfile.TemporaryDirectory() as out:
    with self.assertRaisesRegex(ValueError,'border'):
     build(out,**options)

if __name__=='__main__':unittest.main()
