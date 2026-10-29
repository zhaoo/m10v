"""Actual factory hook/task producer/Still with real UI journal cache publication.
No HDF recipe snapshot, native completion mask or hot-path file service is faked.
"""
import struct,unittest
from unicorn import UC_HOOK_CODE
from unicorn import arm_const as A
from tests import test_gr3_film_pipeline_current as pipeline

class HdfTaskPipelineTests(unittest.TestCase):
 setUpClass=classmethod(pipeline.CurrentFilmPipelineTests.setUpClass.__func__)
 call=pipeline.CurrentFilmPipelineTests.call
 fixture=pipeline.CurrentFilmPipelineTests.fixture
 enqueue=pipeline.CurrentFilmPipelineTests.enqueue
 make=pipeline.CurrentFilmPipelineTests.make
 def genuine_recipe_allocation(self,e,recipe):
  # Execute the delivered actual factory BL and its allocation initializer.
  # The allocator is an OS boundary, returning an already reserved test block.
  def allocation(u,at,n,_):
   if at!=0x5351091c:return
   self.assertEqual(u.reg_read(A.UC_ARM_REG_R0),self.manifest['capture_lifecycle']['owner']['storage']['extended_recipe_bytes'])
   u.reg_write(A.UC_ARM_REG_R0,recipe);u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
  h=e.u.hook_add(UC_HOOK_CODE,allocation)
  e.u.reg_write(A.UC_ARM_REG_R0,0x4778);e.u.reg_write(A.UC_ARM_REG_SP,0x5effff00)
  e.u.emu_start(0x53523e0c,0x53523e10,count=100000);e.u.hook_del(h)
  self.assertEqual(e.u.reg_read(A.UC_ARM_REG_PC),0x53523e10)
  self.assertEqual(struct.unpack('<3I',e.u.mem_read(recipe+0x5134,12)),(0,0,0))
 def warm_ui(self,e,data,strength):
  owner=e.alloc(self.manifest['hdf_menu']['owner_bytes'])
  e.w32(0x55063910,1);e.w32(0x55063988,owner)
  self.call(e,'m10v_camera_library_preview_init',owner)
  self.call(e,'m10v_hdf_menu_cache_init',owner)
  manager,app,fs=e.alloc(12),e.alloc(4),e.alloc(0x24)
  e.w32(manager+8,app);e.w32(app,fs);e.u.mem_write(fs+0x20,b'\1')
  state=bytes(e.u.mem_read(data,184));self.files={};self.ui_reads=[]
  def storage(u,at,n,_):
   r=[u.reg_read(getattr(A,'UC_ARM_REG_R'+str(i))) for i in range(4)]
   if at==0x53828014:result=manager
   elif at in (0x53825648,0x53825fa8):
    name=bytes(u.mem_read(r[1],12)).split(b'\0')[0].decode();result=0
    if at==0x53825648:
     self.ui_reads.append((name,r[2]));value=state if r[2]==184 else self.files.get(name)
     if value:u.mem_write(r[3],value);result=1
    else:self.files[name]=bytes(u.mem_read(r[3],r[2]));result=1
   else:return
   u.reg_write(A.UC_ARM_REG_R0,result);u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
  self.storage=storage
  hook=e.u.hook_add(UC_HOOK_CODE,storage)
  self.assertEqual(self.call(e,'m10v_camera_library_load',data),0)
  self.call(e,'m10v_hdf_bootstrap');self.assertEqual(self.call(e,'m10v_hdf_save',strength),0)
  e.u.hook_del(hook)
  self.assertTrue(self.ui_reads);return owner
 def reserve(self,e,recipe):
  original_owner=e.alloc(0x100);e.w32(original_owner+0xf0,recipe)
  e.u.reg_write(A.UC_ARM_REG_R4,original_owner);e.u.reg_write(A.UC_ARM_REG_SP,0x5effff00)
  e.u.emu_start(0x5351aed4,0x5351aed8,count=10000)
  self.assertEqual(e.u.reg_read(A.UC_ARM_REG_PC),0x5351aed8)
  self.assertEqual(struct.unpack('<3I',e.u.mem_read(recipe+0x5134,12)),(0,0,0))
 def trap_storage(self,e):
  def forbid(u,at,n,_):
   if at in (0x53828014,0x53825648,0x53825fa8,self.manifest['symbols']['m10v_camera_library_load']):
    self.fail('actual task/Still touched filesystem at '+hex(at))
  return e.u.hook_add(UC_HOOK_CODE,forbid)
 def test_real_task_ingress_freezes_ui_hdf_and_reuses_recipe_without_hot_fs(self):
  self.assertTrue(self.manifest.get('hdf_adj'))
  e,recipe,obj,frame,si,request,data=self.fixture(62,stage=1)
  self.genuine_recipe_allocation(e,recipe)
  owner=self.warm_ui(e,data,3)
  trap=self.trap_storage(e);self.reserve(e,recipe)
  self.enqueue(e,recipe,19)
  self.assertEqual(struct.unpack('<3I',e.u.mem_read(recipe+0x5134,12)),(1,3,0))
  self.make(e,recipe,obj,frame)
  self.assertEqual(self.call(e,'m10v_isp_frame_recipe_completed',recipe,si,25,data),1)
  e.u.hook_del(trap)
  # UI commits next strength, but the already queued shot keeps its snapshot.
  ui=e.u.hook_add(UC_HOOK_CODE,self.storage);self.assertEqual(self.call(e,'m10v_hdf_save',1),0);e.u.hook_del(ui)
  trap=self.trap_storage(e);self.enqueue(e,recipe,0)
  self.assertEqual(struct.unpack('<3I',e.u.mem_read(recipe+0x5134,12)),(1,3,0))
  # Next exposure can reuse both native recipe and SI addresses. The actual
  # official factory allocation hook clears the complete owned tail even
  # at the identical address, then reservation and true task ingress run.
  self.genuine_recipe_allocation(e,recipe);self.reserve(e,recipe);self.enqueue(e,recipe,19)
  self.assertEqual(struct.unpack('<3I',e.u.mem_read(recipe+0x5134,12)),(1,1,0))
  e.u.hook_del(trap)
 def test_hdf_task_snapshot_is_independent_of_cold_or_busy_color_cache(self):
  for version in (0,1):
   with self.subTest(color_version=version):
    e,recipe,obj,frame,si,request,data=self.fixture(62)
    self.genuine_recipe_allocation(e,recipe);owner=self.warm_ui(e,data,2)
    e.w32(owner+0x2140,version)
    trap=self.trap_storage(e);self.reserve(e,recipe);self.enqueue(e,recipe,19)
    self.assertEqual(struct.unpack('<3I',e.u.mem_read(recipe+0x5134,12)),(1,2,0))
    e.u.hook_del(trap)
