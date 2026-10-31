"""Execute compiled ARM controller + state and original BaseController lifetime.

Storage, view operations, owner TopMenu construction, factory trampolines and
registration/dispatch are explicit boundary mocks. Base constructor/destructor,
unregister loop and previous-route return execute original firmware instructions.
No camera or full event-loop claim is made.
"""
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
from scripts.build_gr3_m10v_library import FLAGS, link_object, AB_CONTROLLER_EXPORTS
from scripts.analyze_gr3_settings import read_firmware
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import *
ROOT=Path(__file__).resolve().parents[1]
CODE=0x540c0000
STATE=0x540d0000
STUB=0x540b0000
OWNER=0x10002000
PAGE=OWNER+0x13bc
STRIDE=0x2c0
VIEW=0x158
SAVED_STATE=VIEW+164
SCREEN=SAVED_STATE+104

class ControllerLifetimeTests(unittest.TestCase):
 ab_enabled=True
 debug=False
 native_host=False
 appended_slots=False
 owner_cache=False
 exit_trace=False
 @classmethod
 def setUpClass(cls):
  p=Path(os.environ.get('M10V_GR3_ORIGINAL_RTOS','/tmp/m10v-sd-research/rtos.bin'))
  if not p.exists():raise unittest.SkipTest('official GR III 2.10 RTOS required')
  cls.firmware=read_firmware(p)
  names=['m10v_settings_factory_original','m10v_settings_top_dtor_original',
         'm10v_settings_controller_vtable','m10v_settings_view_create',
         'm10v_settings_view_draw','m10v_settings_view_destroy',
         'm10v_camera_library_load','m10v_sd_camera_item','m10v_sd_camera_install',
         'm10v_camera_library_stamp','m10v_camera_library_film_name_stamp','m10v_debug_log','m10v_debug_batch','m10v_library_name','m10v_sd_camera_custom_name',*[f'm10v_ab_{n}_original' for n in ['selector','mapper','live_enter','live_leave','live_destroy','live_event','adj_event']]]
  names += [f'm10v_ab_adj_{n}_original' for n in ('refresh','exit','destroy','changed')]
  names += ['m10v_ab_dispatch_original','m10v_zoom_menu_open','m10v_zoom_menu_key','m10v_zoom_camera_load','m10v_zoom_camera_save','m10v_settings_view_zoom','m10v_zoom_live_apply','m10v_zoom_live_slot']
  names += ['m10v_library_valid','m10v_library_count','m10v_sd_camera_directory_item','m10v_sd_camera_directory_extent','m10v_sd_camera_directory_install','m10v_camera_library_remove','m10v_camera_library_shooting_count']
  names += ['m10v_camera_library_reconcile_legacy_selection','m10v_camera_library_preview_init','m10v_camera_library_preview_clear','m10v_camera_library_mutation_begin','m10v_camera_library_mutation_end']
  names += ['m10v_camera_library_preview']
  cls.externals={n:STUB+i*4 for i,n in enumerate(names)}
  cc=os.environ.get('M10V_LLVM_CLANG') or '/opt/homebrew/opt/llvm/bin/clang'
  if not Path(cc).exists():cc=shutil.which('clang')
  with tempfile.TemporaryDirectory() as d:
   blobs=[]
   for file,addr in [('m10v_settings.c',STATE),('m10v_settings_controller.c',CODE)]:
    obj=Path(d)/'module.o'
    subprocess.run([cc,*FLAGS,f'-DM10V_AB_ENABLED={int(cls.ab_enabled)}',f'-DM10V_DEBUG_MODE={int(cls.debug)}',f'-DM10V_ADJ_EXIT_TRACE={int(cls.exit_trace)}',f'-DM10V_AB_NATIVE_HOST={int(cls.native_host)}',f'-DM10V_APPENDED_SLOTS={int(cls.appended_slots)}',f'-DM10V_LIVE_COLOR={int(cls.owner_cache)}','-c',str(ROOT/'native/gr3'/file),'-o',str(obj)],check=True,capture_output=True)
    blob,symbols=link_object(obj.read_bytes(),addr,cls.externals,prefix='m10v_settings_controller_' if 'controller' in file else 'm10v_settings_',additional_exports=AB_CONTROLLER_EXPORTS if 'controller' in file else ())
    cls.externals.update(symbols);blobs.append((addr,blob))
   cls.blobs=blobs

 def machine(self):
  u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
  for a,n in [(0x53000000,0x2000000),(0x55000000,0x1000000),(0x10000000,0x200000)]:u.mem_map(a,n)
  u.mem_write(0x53000000,self.firmware)
  u.mem_write(0x55000000,self.firmware[0x107b540:0x107b540+0x3a080])
  for a,b in self.blobs:u.mem_write(a,b)
  u.reg_write(UC_ARM_REG_C1_C0_2,0xf00000);u.reg_write(UC_ARM_REG_FPEXC,0x40000000)
  u.mem_write(0x5536d074,struct.pack('<II',1,struct.unpack_from('<I',self.firmware,0x6b7058)[0]))
  self.events=[];self.executed=set();self.load_fail=False;self.view_fail=False
  self.install_fail=False
  self.ab_tone=12;self.ab_files={};self.ab_storage_fail=False;self.ab_clock=1000
  self.route=0x0200f100;self.fallback=0x10008000
  reverse={a:n for n,a in self.externals.items() if STUB<=a<STUB+0x100}
  def hook(m,a,n,_):
   self.executed.add(a)
   r=[m.reg_read(reg) for reg in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)]
   name=reverse.get(a)
   if name:
    self.events.append((name,*r,*([self.word(m,m.reg_read(UC_ARM_REG_SP))] if name=='m10v_debug_log' else [])))
    if name=='m10v_ab_live_event_original' and getattr(self,'native_event_callback',None):self.native_event_callback(m)
    result=0
    if name=='m10v_debug_batch':
     for i in range(r[1]):self.events.append(('m10v_debug_log',*struct.unpack('<5I',m.mem_read(r[0]+20*i,20))))
    if name=='m10v_ab_dispatch_original' and getattr(self,'real_dispatch',False):
     m.reg_write(UC_ARM_REG_PC,0x5316d5dc);return
    if name=='m10v_settings_factory_original' and getattr(self,'real_factory',False):
     m.reg_write(UC_ARM_REG_PC,0x5316f3b8);return
    if name=='m10v_settings_factory_original':result=getattr(self,'stock_owner',OWNER) if r[1]==0x0200004a else self.fallback
    elif name=='m10v_settings_top_dtor_original':result=r[0]
    elif name=='m10v_settings_controller_vtable':result=STUB+0x800
    elif name=='m10v_settings_view_create':
     if self.view_fail:result=0xffffffff
     else:m.mem_write(r[0],struct.pack('<I',0x10009000));m.mem_write(r[0]+160,struct.pack('<I',37))
    elif name=='m10v_settings_view_destroy':m.mem_write(r[0],bytes(164))
    elif name in ('m10v_camera_library_load','m10v_camera_library_preview'):
     result=int(getattr(self,'preview_ready',False)) if name.endswith('_preview') else 0xffffffff if self.load_fail else 0
     state=bytearray(184 if self.appended_slots else 104)
     for i in range(5):struct.pack_into('<H',state,12+8*i,getattr(self,'fresh_films',[33,34,35,36,37])[i])
     m.mem_write(r[0],bytes(state))
    elif name=='m10v_camera_library_reconcile_legacy_selection':result=0xffffffff if getattr(self,'reconcile_fail',False) else 0
    elif name=='m10v_sd_camera_directory_extent':result=46
    elif name=='m10v_sd_camera_item':result=33+r[0]*8+r[1]
    elif name=='m10v_sd_camera_install':result=0xffffffff if self.install_fail else 0
    elif name=='m10v_library_valid':result=1 # state decoding is exercised by real-library tests
    elif name=='m10v_library_count':result=sum(self.word(m,r[0]+12+8*i)&65535!=0 for i in range(10))
    elif name=='m10v_camera_library_shooting_count':result=17 if self.appended_slots else 12
    elif name=='m10v_camera_library_mutation_begin':result=1
    m.reg_write(UC_ARM_REG_R0,result)
   elif a==0x5320ad88:m.reg_write(UC_ARM_REG_R0,0x55007000)
   elif a==0x5320ba9c:m.reg_write(UC_ARM_REG_R0,0x55008000)
   elif a==0x5320afbc:m.reg_write(UC_ARM_REG_R0,0) # debug-only navigation-gate observation
   elif a==0x5320aefc:m.reg_write(UC_ARM_REG_R0,0x55008000)
   elif a==0x532c26c0:
    self.assertEqual(bytes(m.mem_read(r[0]+0x1b,1)),b'\0','Setup must activate shooting context, regardless of stale ImageControl context')
    self.events.append(('activate_tone',*r))
    if not getattr(self,'ab_set_fail',False):self.ab_tone=r[1]
   elif a==0x532bd61c:self.events.append(('negative.clear',*r));m.reg_write(UC_ARM_REG_R0,0)
   elif a==0x532bd6b4:m.reg_write(UC_ARM_REG_R0,self.ab_tone)
   elif a==0x53050b7c:
    m.mem_write(r[0],struct.pack('<II',self.ab_clock//1000,(self.ab_clock%1000)*1000));m.reg_write(UC_ARM_REG_R0,0)
   elif a==0x53828014:
    m.mem_write(0x55009008,struct.pack('<I',0x55009020));m.mem_write(0x55009020,struct.pack('<I',0x55009100));m.mem_write(0x55009120,b'\1')
    m.reg_write(UC_ARM_REG_R0,0x55009000)
   elif a in (0x53825648,0x53825fa8):
    name=bytes(m.mem_read(r[1],12)).split(b'\0')[0].decode()
    if a==0x53825fa8:
     if not self.ab_storage_fail:self.ab_files[name]=bytes(m.mem_read(r[3],r[2]))
     m.reg_write(UC_ARM_REG_R0,int(not self.ab_storage_fail))
    else:
     data=self.ab_files.get(name)
     if data:m.mem_write(r[3],data)
     m.reg_write(UC_ARM_REG_R0,int(bool(data)))
   elif a==0x5319aa68:
    self.events.append(('stock_top_ctor',r[0]));m.mem_write(r[0],bytes(0x13bc))
   elif a==0x5316d354:
    self.events.append(('register',*r));self.assertEqual(self.word(m,r[0]+4),0)
    m.mem_write(r[0]+4,struct.pack('<I',r[2]))
   elif a==0x533abc5c:self.events.append(('unregister',r[0]))
   elif a==0x5316c9d8:
    self.events.append(('dispatch',*r))
    if getattr(self,'real_navigation',False):return
   elif a==0x53228c4c:m.reg_write(UC_ARM_REG_R0,self.route)
   elif a in (0x536af2e4,0x536af358):self.fail('unexpected free of embedded controller/object '+hex(r[0]))
   elif a in (0x536b93d0,0x53820074):self.fail('original assertion '+hex(a))
   else:return
   m.reg_write(UC_ARM_REG_PC,m.reg_read(UC_ARM_REG_LR))
  u.hook_add(UC_HOOK_CODE,hook)
  return u

 @staticmethod
 def word(u,a):return struct.unpack('<I',u.mem_read(a,4))[0]
 def call(self,u,name,*args):
  addr=self.externals['m10v_settings_controller_'+name] if isinstance(name,str) else name
  for reg,v in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3),args):u.reg_write(reg,v)
  u.reg_write(UC_ARM_REG_SP,0x100f0000);u.reg_write(UC_ARM_REG_LR,0x10000000)
  u.emu_start(addr,0x10000000,count=1000000)
  self.assertEqual(u.reg_read(UC_ARM_REG_PC),0x10000000)
  self.assertEqual(u.reg_read(UC_ARM_REG_SP),0x100f0000)
  return u.reg_read(UC_ARM_REG_R0)
 def count(self,name):return sum(e[0]==name for e in self.events)
 def setup_owner(self,u):self.call(u,'top_ctor',OWNER)

 def test_zoom_route_reuses_first_owner_and_avoids_film_state(self):
  u=self.machine();self.setup_owner(u)
  self.assertEqual(self.call(u,'factory',0x55123400,0x0200f105),PAGE)
  self.assertEqual(self.call(u,'ready',PAGE,0x0200f105),1)
  self.assertEqual(self.count('m10v_zoom_menu_open'),1)
  self.assertEqual(self.count('m10v_camera_library_load'),0)
  self.call(u,'enter',PAGE,0x0200f105,0)
  self.assertEqual(self.count('m10v_settings_view_zoom'),1)
  u.mem_write(0x10000100,struct.pack('<H',0xd8));self.call(u,'key',PAGE,0x10000100)
  self.assertEqual(self.count('m10v_zoom_menu_key'),1)
  self.assertEqual(self.count('m10v_settings_view_draw'),0)

 def test_zoom_confirm_return_and_key_mapping_preserve_native_parent(self):
  u=self.machine();self.setup_owner(u);self.call(u,'ready',PAGE,0x0200f105)
  for raw,key in [(0xce,0),(0xcf,1),(0xd0,2),(0xd1,3),(0xd8,4),(0x86,5)]:
   u.mem_write(0x10000100,struct.pack('<H',raw));self.call(u,'key',PAGE,0x10000100)
   self.assertEqual([e for e in self.events if e[0]=='m10v_zoom_menu_key'][-1][3],key)
  u.mem_write(PAGE+0x150,struct.pack('<I',0x0200004a))
  u.mem_write(PAGE+SAVED_STATE+28,struct.pack('<I',1)) # menu confirmed/closed
  u.mem_write(0x10000100,struct.pack('<H',0xd8));self.call(u,'key',PAGE,0x10000100)
  self.assertIn(0x5316ca28,self.executed)
  self.assertIn(('dispatch',PAGE,0x0200004a,0x10000000),[e[:4] for e in self.events])

 def test_dynamic_card_ids_resolve_all_five_owned_descriptors(self):
  u=self.machine();owner=0x55040000;page=owner+0x13bc;heap=0x55080000
  u.mem_write(0x55063910,struct.pack('<I',1));u.mem_write(0x55063988,struct.pack('<I',owner))
  u.mem_write(page,struct.pack('<I',STUB+0x800))
  u.mem_write(page+VIEW+160,struct.pack('<I',37));u.mem_write(page+VIEW+39*4,struct.pack('<I',heap))
  for i in range(5):u.mem_write(heap+470440+4*i,struct.pack('<I',heap+470400+8*i))
  directory=self.call(u,'card_directory')
  for i in range(5):self.assertEqual(self.word(u,directory+(749+i)*4),heap+470400+8*i)

 def test_embedded_initialization_and_stable_factory_identity(self):
  u=self.machine();u.mem_write(OWNER+0x193c,b"CANARY!!");self.setup_owner(u)
  self.assertEqual(bytes(u.mem_read(OWNER+0x193c,8)),b"CANARY!!")
  self.assertEqual(self.call(u,'owner_size'),0x193c)
  self.assertIn(0x5316c8d4,self.executed)
  for i,route in enumerate((0x0200f100,0x0200f101)):
   p=PAGE+i*STRIDE
   self.assertEqual(self.word(u,p),STUB+0x800)
   self.assertEqual(self.word(u,p+0x150),0x10000000)
   for _ in range(3):self.assertEqual(self.call(u,'factory',0x55123400,route),p)
  for route in (0x0200004e,0x08000000,0x0200ffff):
   self.assertEqual(self.call(u,'factory',0x55123400,route),self.fallback)
   self.assertEqual(self.events[-1][:3],('m10v_settings_factory_original',0x55123400,route))

 def test_independent_install_binds_catalog_id_and_activates_exact_slot_tone(self):
  for slot,tone in enumerate((25,26,27,28,29) if self.appended_slots else (12,18,19,20,21)):
   u=self.machine();self.setup_owner(u);p=PAGE
   self.call(u,'ready',p,0x0200f100)
   u.mem_write(p+SCREEN+4,struct.pack('<I',slot))
   def key(raw):
    u.mem_write(0x10000100,struct.pack('<H',raw));self.call(u,'key',p,0x10000100)
   key(0xd8)
   u.mem_write(p+SCREEN+12,struct.pack('<II',35,68))
   self.install_fail=True;key(0xd8)
   self.assertEqual(self.word(u,p+SCREEN),2)
   self.assertEqual(self.count('activate_tone'),0)
   u.mem_write(0x5500801b,b'\x01')
   self.install_fail=False;key(0xd8)
   installs=[e[1:] for e in self.events if e[0]=='m10v_sd_camera_install']
   self.assertEqual(installs,[(4,3,68,slot)]*2)
   self.assertEqual(bytes(u.mem_read(0x5500801b,1)),b'\x01')
   self.assertEqual(self.word(u,p+SCREEN),1)
   self.assertEqual([e[2] for e in self.events if e[0]=='activate_tone'],[tone])

 def test_ready_denies_storage_and_view_failure(self):
  u=self.machine();self.setup_owner(u)
  self.load_fail=True
  self.assertEqual(self.call(u,'ready',PAGE,0x0200f100),0)
  self.assertEqual(self.count('m10v_settings_view_create'),0)
  self.load_fail=False;self.view_fail=True
  self.assertEqual(self.call(u,'ready',PAGE,0x0200f100),0)
  self.assertEqual(self.count('register'),0)
  self.view_fail=False
  self.assertEqual(self.call(u,'ready',PAGE,0x0200f100),1)

 def test_cached_view_reentry_reuses_widgets_and_unregisters(self):
  u=self.machine();self.setup_owner(u)
  for cycle in range(3):
   self.assertEqual(self.call(u,'ready',PAGE,0x0200f100),1)
   self.call(u,'enter',PAGE,0x0200f100,0)
   self.assertEqual(self.word(u,PAGE+4),0x10009000)
   self.call(u,0x5316ce8c,PAGE)
   self.assertEqual(self.word(u,PAGE+4),0)
  self.assertEqual(self.count('m10v_settings_view_create'),1)
  self.assertEqual(self.count('register'),3);self.assertEqual(self.count('unregister'),3)

 def test_return_key_preserves_previous_route_and_actual_return_routine(self):
  u=self.machine();self.setup_owner(u);self.call(u,'ready',PAGE,0x0200f100)
  u.mem_write(PAGE+0x150,struct.pack('<I',0x0200004a));u.mem_write(0x10000100,struct.pack('<H',0x86))
  self.call(u,'key',PAGE,0x10000100)
  self.assertEqual(self.word(u,PAGE+SCREEN),0)
  self.assertIn(0x5316ca28,self.executed)
  self.assertIn(('dispatch',PAGE,0x0200004a,0x10000000),[e[:4] for e in self.events])
  self.assertEqual(self.word(u,PAGE+0x150),0x0200004a)

 def test_destruction_unregisters_before_view_and_never_frees_tail(self):
  u=self.machine();self.setup_owner(u);self.call(u,'ready',PAGE,0x0200f100);self.call(u,'enter',PAGE,0,0)
  self.call(u,'top_dtor',OWNER)
  self.assertIn(0x5316c774,self.executed)
  self.assertEqual(self.count('m10v_settings_view_destroy'),2)
  names=[e[0] for e in self.events]
  self.assertLess(names.index('unregister'),names.index('m10v_settings_view_destroy'))
  self.assertEqual(names[-1],'m10v_settings_top_dtor_original')

 def test_recognized_keys_stop_base_event_propagation(self):
  u=self.machine();self.setup_owner(u);self.call(u,'ready',PAGE,0x0200f100)
  # BaseController5316d8c8 falls through to a shared model when handler returns0.
  for event in (0xd0,0xd1,0xce,0xcf,0xd4,0xd5):
   u.mem_write(0x10000100,struct.pack('<H',event))
   self.assertEqual(self.call(u,'key',PAGE,0x10000100),1,
                    'recognized key must be consumed before shared model fallback')
  u.mem_write(0x10000100,struct.pack('<H',0xffff))
  self.assertEqual(self.call(u,'key',PAGE,0x10000100),0)

 def test_actual_base_dispatch_tail_consumes_back_and_navigation(self):
  u=self.machine();self.setup_owner(u)
  u.mem_write(STUB+0x800+0x28,struct.pack('<I',self.externals['m10v_settings_controller_key']))
  u.mem_write(PAGE+0x150,struct.pack('<I',0x0200004a))
  for event in (0xd0,0xd1,0xce,0xcf,0x86):
   self.call(u,'ready',PAGE,0x0200f100)
   u.mem_write(0x10000100,struct.pack('<H',event))
   u.reg_write(UC_ARM_REG_R4,0x10000100)
   u.reg_write(UC_ARM_REG_R5,0x55012300)
   u.reg_write(UC_ARM_REG_R7,PAGE)
   u.reg_write(UC_ARM_REG_SP,0x100f0000)
   self.executed.clear()
   # Execute the original virtual+28 dispatch and consumption branch; stop at
   # its shared return label before restoring the outer (not entered) frame.
   u.emu_start(0x5316d7ec,0x5316d81c,count=100000)
   self.assertEqual(u.reg_read(UC_ARM_REG_PC),0x5316d81c)
   self.assertIn(0x5316d8c4,self.executed)
   self.assertNotIn(0x5316d804,self.executed)
   self.assertNotIn(0x5320b79c,self.executed)

 def test_key_alias_only_translates_private_route_return_value(self):
  u=self.machine()
  for route in (0x0200f100,0x0200f101,0x0200f103,0x0200004e,0x08000000,0x0200ffff):
   self.route=route
   self.assertEqual(self.call(u,'key_route',0x55012300),0x0200004a if route in (0x0200f100,0x0200f101,0x0200f103) else route)
   self.assertEqual(self.route,route)

class ControllerDebugTests(ControllerLifetimeTests):
 debug=True
 def test_timestamp_keys_report_state_and_redraw_without_changing_films(self):
  u=self.machine();self.setup_owner(u);p=PAGE+STRIDE
  self.call(u,'ready',p,0x0200f101);self.call(u,'enter',p,0x0200f101,0)
  before=bytes(u.mem_read(p+SAVED_STATE+12,40))
  def key(k):
   u.mem_write(0x10000100,struct.pack('<H',k));self.call(u,'key',p,0x10000100)
  key(0xd8) # edit mode
  self.assertEqual(self.word(u,p+SCREEN),4)
  key(0xcf) # date only
  self.assertEqual(self.word(u,p+SCREEN+20),1)
  key(0xd8) # commit
  self.assertEqual(self.word(u,p+SCREEN),3)
  self.assertEqual(bytes(u.mem_read(p+SAVED_STATE+52,1)),b'\1')
  key(0xd1) # next row
  self.assertEqual(self.word(u,p+SCREEN+4),1)
  self.assertEqual(bytes(u.mem_read(p+SAVED_STATE+12,40)),before)
  logs=[e[1] for e in self.events if e[0]=='m10v_debug_log']
  self.assertEqual(logs,[80,81]+[82,83,84]*4)
  self.assertEqual(self.count('m10v_camera_library_stamp'),1)
  states=[e[2:] for e in self.events if e[0]=='m10v_debug_log' and e[1]==83]
  self.assertEqual(states,[(0xd8,4,0,0),(0xcf,4,0,1),(0xd8,3,0,1),(0xd1,3,1,1)])

if __name__=='__main__':unittest.main()
