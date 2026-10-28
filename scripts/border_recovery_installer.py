#!/usr/bin/env python3
"""Checks returned guard artifacts and executes their installed original routes."""
import unittest,hashlib,tempfile
from pathlib import Path
from unicorn import UC_PROT_READ,UC_PROT_EXEC,UC_PROT_WRITE
from border_recovery_wait_guard import WaitGuard as _WaitGuard
from border_recovery_contract import ROOT,A
from build_gr3_border_wait_guard import build,apply_patch_plan,arm_bl,MODELS
class InstallerTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.stock=(ROOT/'builds/gr3-extension-validation/official-rtos.bin').read_bytes()
  cls.other=(ROOT/'builds/gr3-border-iip-20261027/gr3x-official-rtos.bin').read_bytes()
  cls.code,cls.report=build(0x54160000,cls.stock,border_enabled=True,internal_guard_research=True)
 def test_default_off_needs_no_fixture_and_does_not_compile_or_write(self):
  with tempfile.TemporaryDirectory() as folder:
   code,report=build(stock=None,out_dir=Path(folder)/'unused')
   self.assertEqual(code,b'');self.assertFalse(report['enabled']);self.assertEqual(report['patches'],[])
   self.assertFalse((Path(folder)/'unused').exists())
 def test_explicit_research_requires_border_model_and_immutable_input(self):
  for kwargs in ({'stock':self.stock,'internal_guard_research':True},
    {'stock':self.stock,'border_enabled':True,'internal_guard_research':True,'camera_model':'gr4'},
    {'stock':self.other,'border_enabled':True,'internal_guard_research':True,'camera_model':'gr3'},
    {'stock':self.stock+b'\0','border_enabled':True,'internal_guard_research':True}):
   with self.assertRaises(ValueError):build(**kwargs)
 def test_deterministic_component_all_patch_preimages_and_serialization_manifest(self):
  again,report=build(0x54160000,self.stock,border_enabled=True,internal_guard_research=True)
  self.assertEqual(self.code,again);self.assertEqual(self.report,report)
  self.assertEqual(len(report['patches']),18);self.assertEqual(report['code_sha256'],hashlib.sha256(again).hexdigest())
  self.assertTrue(report['contract']['serialized_private_chain_required'])
  self.assertEqual(report['contract']['private_client_bytes'],76)
  self.assertEqual(report['contract']['fill_bundle']['maximum_rectangles'],132)
  self.assertIn('m10v_border_fill_bundle_submit',report['symbols'])
  self.assertEqual(report['worker_allocations']['transfer_first']['owned'],0x58)
  self.assertFalse(report['hardware_activation']);self.assertFalse(report['pixel_pipeline_enabled'])
  self.assertTrue(any('teardown' in reason for reason in report['activation_blockers']))
  patched=apply_patch_plan(self.stock,report['patches'])
  with self.assertRaises(ValueError):apply_patch_plan(patched,report['patches'])
 def test_gr3x_independent_hash_and_whole_touched_spans_match_without_hardware_claim(self):
  self.assertEqual(hashlib.sha256(self.other).hexdigest(),MODELS['gr3x']['rtos_sha256'])
  code,report=build(0x54160000,self.other,border_enabled=True,internal_guard_research=True,camera_model='gr3x')
  self.assertEqual(code,self.code);self.assertEqual(report['patches'],self.report['patches'])
  self.assertEqual(report['verified_abi_spans'],self.report['verified_abi_spans'])
  self.assertEqual(len(report['verified_abi_spans']),21)
  self.assertEqual(report['original_rtos_sha256'],MODELS['gr3x']['rtos_sha256'])
  self.assertFalse(report['physical_model_support_verified'])
 def test_reviewable_output_contains_code_manifest_only(self):
  with tempfile.TemporaryDirectory() as folder:
   code,report=build(0x54160000,self.stock,border_enabled=True,internal_guard_research=True,out_dir=folder)
   self.assertEqual(sorted(p.name for p in Path(folder).iterdir()),['m10v-border-guard-arm.bin','m10v-border-guard-arm.json'])
   self.assertEqual((Path(folder)/'m10v-border-guard-arm.bin').read_bytes(),code)
class InstalledRoutes(unittest.TestCase):
 reg=_WaitGuard.reg;put=_WaitGuard.put;word=_WaitGuard.word;call=_WaitGuard.call
 invoke=_WaitGuard.invoke;notify=_WaitGuard.notify;configure_other_owner=_WaitGuard.configure_other_owner
 hook=_WaitGuard.hook
 @classmethod
 def setUpClass(cls):
  cls.stock=(ROOT/'builds/gr3-extension-validation/official-rtos.bin').read_bytes()
  cls.code,cls.report=build(0x54160000,cls.stock,border_enabled=True,internal_guard_research=True)
  cls.symbols=cls.report['symbols']
 def setUp(self):
  _WaitGuard.setUp(self)
  mapped=(len(self.stock)+4095)&~4095
  self.u.mem_protect(0x53000000,mapped,UC_PROT_READ|UC_PROT_WRITE|UC_PROT_EXEC)
  self.u.mem_write(0x53000000,self.stock)
  self.u.mem_protect(0x53000000,mapped,UC_PROT_READ|UC_PROT_EXEC)
  self.assertEqual(apply_patch_plan(self.stock,self.report['patches'])[:4],self.stock[:4])
  for patch in self.report['patches']:
   pc=patch['address'];page=pc&~4095
   self.u.mem_protect(page,4096,UC_PROT_READ|UC_PROT_WRITE|UC_PROT_EXEC)
   self.assertEqual(self.word(pc),patch['expected']);self.put(pc,patch['replacement'])
   self.u.mem_protect(page,4096,UC_PROT_READ|UC_PROT_EXEC)
 def patch_bl(self,pc,target,expected):
  # Reused route checks ask to install a hook. Here it MUST ALREADY be the
  # actual component plan's hook; do not substitute a separately built probe.
  patch=next(p for p in self.report['patches'] if p['address']==pc)
  self.assertEqual(patch['expected'],expected);self.assertEqual(patch['target'],target)
  self.assertEqual(self.word(pc),arm_bl(pc,target))
 test_built_original_public_route_retains_both_stacks=_WaitGuard.test_full_original_public_copy_keeps_both_stack_frames_on_failed_wait
 test_built_dispatch_body_binds_then_notifies=_WaitGuard.test_dispatch_body_binds_exact_owned_job_then_clears_tail_before_notification
 test_built_fill_parent_and_wait_retry=_WaitGuard.test_original_fill_lower_prologue_proves_parent_worker_and_wait_retry
 test_built_resize_parent_and_wait_retry=_WaitGuard.test_original_resize_lower_prologue_proves_parent_r7_and_context_before_retry
 test_built_resize_dma_shortcut=_WaitGuard.test_resize_equal_size_dma_shortcut_wait_is_also_guarded
 def test_built_factory_allocation_and_ctor_hooks_are_installed_as_a_pair(self):
  factory,dmafactory,second=0x55008000,0x55009000,0x5500a000
  self.put(dmafactory+4,0x5500b000)
  self.stubs.update({0x537e2d6c:dmafactory,0x536b93d0:0,0x5369a164:1,0x5369ad9c:1})
  self.allocations=[];self.heap_results=[self.worker,second]
  self.invoke(0x53699fc4,(factory,))
  self.assertEqual(self.allocations,[0x58,0x44]);self.assertEqual(self.word(self.worker+0x44),0x42575431)
  self.assertEqual(self.word(self.worker+0x54),0)
 def test_relocated_component_constructs_its_own_native_vtable(self):
  code,report=build(0x54180000,self.stock,border_enabled=True,internal_guard_research=True,camera_model=self.report['camera_model'])
  self.u.mem_map(0x54180000,0x10000);self.u.mem_write(0x54180000,code)
  client=0x55020000
  self.invoke(report['symbols']['m10v_border_client_construct'],(client,))
  self.assertTrue(0x54180000<=self.word(client)<0x54190000)
  self.assertEqual(self.word(self.word(client)+8),report['symbols']['m10v_border_client_notify'])
class InstalledRoutesGr3x(InstalledRoutes):
 @classmethod
 def setUpClass(cls):
  cls.stock=(ROOT/'builds/gr3-border-iip-20261027/gr3x-official-rtos.bin').read_bytes()
  cls.code,cls.report=build(0x54160000,cls.stock,border_enabled=True,internal_guard_research=True,camera_model='gr3x')
  cls.symbols=cls.report['symbols']
if __name__=='__main__':unittest.main(defaultTest=['InstallerTests','InstalledRoutes','InstalledRoutesGr3x'],verbosity=2)
