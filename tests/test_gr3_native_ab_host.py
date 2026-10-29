"""Compiled ARM native-host adapter. Native UI APIs are explicit boundaries;
this validates ownership/order/route contracts, not LCD or physical power-off."""
import struct
from tests import test_gr3_settings_controller as adapter
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import *

class NativeHostTests(adapter.ControllerLifetimeTests):
 native_host=True
 debug=True
 def begin(self):
  u=self.machine();self.owner=0x55040000;self.page=self.owner+0x13bc;self.stock_owner=self.owner
  self.call(u,'top_ctor',self.owner)
  u.mem_write(0x55063910,struct.pack('<I',1));u.mem_write(0x55063988,struct.pack('<I',self.owner))
  u.mem_write(0x55008000+0x1b,bytes(5))
  self.controller=0x55050000;self.list=0x55060000;self.ui=[];self.list_cursor=0;self.row_texts=[]
  u.mem_write(self.controller,struct.pack('<I',0x53b394e0))
  for off,value in [(0x124,0x02000000),(4,0x55061000),(0x15c,0x55061000),(0x160,0x55062000),(0x164,0x55063000),(0x168,0x55064000),(0x1ac,0x55065000),(0x1f0,self.list),(0x150,0x02000012)]:u.mem_write(self.controller+off,struct.pack('<I',value))
  u.mem_write(self.list+0xf4,struct.pack('<II',0x55074000,0x55074000+24*4))
  u.mem_write(self.list,struct.pack('<I',0x55066000));u.mem_write(0x55066018,struct.pack('<I',0x55067000));u.mem_write(0x55067000,bytes.fromhex('1eff2fe1'))
  def boundary(m,a,n,_):
   r=[m.reg_read(v) for v in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2)]
   if a==0x533947f0:m.mem_write(r[1],struct.pack('<I',7));m.mem_write(r[2],struct.pack('<I',9));v=0
   elif a==0x53394758:v=0x55070000+r[1]*0x200
   elif a==0x533948c4:v=360
   elif a==0x53394820:v=self.list_cursor
   elif a in (0x53394e8c,0x533a1808,0x533a1734,0x533a18e0,0x533a19b4,0x53395430,0x53395260,0x53396f80,0x533ad3c0,0x533ad308,0x53395224):
    self.ui.append((a,*r));v=0
    if a==0x53395430:self.list_cursor=r[1]
    if a==0x533a18e0 and r[1]:self.row_texts.append(bytes(m.mem_read(r[1],80)).split(b'\0')[0])
   elif a==0x531a2820:v=getattr(self,'adj_type',12)
   elif a==0x532a9988:v=0x224+r[1] # stock translator boundary; real captions/icons have separate ARM coverage
   else:return
   m.reg_write(UC_ARM_REG_R0,v);m.reg_write(UC_ARM_REG_PC,m.reg_read(UC_ARM_REG_LR))
  u.hook_add(UC_HOOK_CODE,boundary);self.route=0x02000000
  return u
 def event(self,u,key):
  u.mem_write(0x10000100,struct.pack('<HHI',key,0,0x10000120));u.mem_write(0x10000120,struct.pack('<II',2,0))
  return 0x10000100
 def test_adj_activates_existing_list_without_navigation_or_tone_change(self):
  u=self.begin();self.call(u,'ab_setup',self.controller,self.event(u,0x37),self.route)
  self.assertFalse(self.count('dispatch'))
  self.assertTrue(any(e[0]==0x53394e8c and e[1:3]==(self.list,5 if self.appended_slots else 6) for e in self.ui))
  self.assertFalse(self.count('activate_tone'))
 def test_pixel_world_slot_keeps_its_icon_in_ab_picker(self):
  self.fresh_films=[290,34,35,36,37]
  u=self.begin();self.call(u,'ab_setup',self.controller,self.event(u,0x37),self.route)
  # The native icon setter receives the appended builtin resource.
  self.assertTrue(any(e[0]==0x533a1734 and 761 in e[1:] for e in self.ui))
 def test_d76_and_anime_e6_slots_keep_icons_in_ab_picker(self):
  for film,icon in [*[(299+i,775+i) for i in range(7)],*[(306+i,858+i) for i in range(6)]]:
   self.fresh_films=[film,34,35,36,37]
   u=self.begin();self.call(u,'ab_setup',self.controller,self.event(u,0x37),self.route)
   self.assertTrue(any(e[0]==0x533a1734 and e[2]==icon for e in self.ui),(film,icon))

 def test_anime_e6_picker_displays_film_names_instead_of_retired_probe_captions(self):
  for film,caption in [(306,1142),(307,1143),(308,1144),(309,1145),(310,1146),(311,1147)]:
   self.fresh_films=[film,34,35,36,37]
   u=self.begin();self.call(u,'ab_setup',self.controller,self.event(u,0x37),self.route)
   self.assertTrue(any(e[0]==0x533a1808 and e[2]==caption for e in self.ui),film)

 def test_power_close_discards_picker_before_native_exit_without_rebuilding_ui(self):
  for key in (1,0x35): # physical MAIN and native ADJ close (MAIN/S1/S2)
   with self.subTest(key=key):
    u=self.begin();self.call(u,'ab_setup',self.controller,self.event(u,0x37),self.route)
    before=len(self.ui);refresh=self.count('m10v_ab_adj_refresh_original')
    self.call(u,'ab_adj_event',self.controller,self.event(u,key))
    self.call(u,'ab_adj_exit',self.controller)
    self.assertEqual(len(self.ui),before,'shutdown must not rebuild or reposition the private list')
    self.assertEqual(self.count('m10v_ab_adj_refresh_original'),refresh)
    self.assertEqual(self.count('m10v_ab_adj_event_original'),1)
    self.assertEqual(self.count('m10v_ab_adj_exit_original'),1)
    self.call(u,'ab_adj_refresh',self.controller)
    self.assertEqual(len(self.ui),before,'late refresh must not reattach a closing picker')
    self.assertFalse(self.count('dispatch'));self.assertFalse(self.count('activate_tone'))

 def test_native_close_still_queues_original_exit_without_private_ui_or_io(self):
  u=self.begin();self.call(u,'ab_setup',self.controller,self.event(u,0x37),self.route)
  before=len(self.ui);queued=[]
  forbidden={self.externals[n] for n in ('m10v_ab_adj_refresh_original','m10v_debug_log','m10v_debug_batch')}
  def native(m,a,n,_):
   if a in forbidden:self.fail('closing ADJ performed UI refresh or diagnostic IO')
   if a==self.externals['m10v_ab_adj_event_original']:
    m.reg_write(UC_ARM_REG_R0,self.controller)
    m.reg_write(UC_ARM_REG_R1,0x10000100)
    m.reg_write(UC_ARM_REG_PC,0x531a4db8)
   elif a==0x53525d5c:
    m.mem_write(0x55079000,struct.pack('<I',0x5507a000))
    m.reg_write(UC_ARM_REG_R0,0x55079000);m.reg_write(UC_ARM_REG_PC,m.reg_read(UC_ARM_REG_LR))
   elif a==0x535493ac:
    m.reg_write(UC_ARM_REG_R0,2);m.reg_write(UC_ARM_REG_PC,m.reg_read(UC_ARM_REG_LR))
   elif a==0x532288b0:
    queued.append(m.reg_read(UC_ARM_REG_R1))
    m.reg_write(UC_ARM_REG_R0,0);m.reg_write(UC_ARM_REG_PC,m.reg_read(UC_ARM_REG_LR))
  u.hook_add(UC_HOOK_CODE,native)
  self.call(u,'ab_adj_event',self.controller,self.event(u,0x35))
  self.assertEqual(queued,[0xb8]) # Original 531a4d80 close request, not a custom LiveView route.
  self.call(u,'ab_adj_exit',self.controller)
  self.assertEqual(len(self.ui),before)
  self.assertFalse(self.count('dispatch'));self.assertFalse(self.count('activate_tone'))

 def test_main_off_return_to_live_keeps_native_entry_without_storage_or_factory(self):
  u=self.begin()
  event=self.event(u,1)
  u.mem_write(event+4,struct.pack('<I',0x55000120))
  u.mem_write(0x55000120,struct.pack('<II',2,0)) # Native MAIN off edge.
  self.call(u,'ab_dispatch',self.controller,event)
  before=len(self.events)
  self.call(u,'ab_live_enter',self.controller,0x08000000,0)
  names=[e[0] for e in self.events[before:]]
  self.assertEqual(names.count('m10v_ab_live_enter_original'),1)
  self.assertFalse(set(names)&{'m10v_settings_factory_original','m10v_camera_library_reconcile_legacy_selection',
                              'm10v_camera_library_load','dispatch','activate_tone'},
                   'ADJ power-off return must not initialize menus, migrate journals or reload SD state')

 def main_switch(self,u,phase,value):
  e=self.event(u,1);u.mem_write(e+4,struct.pack('<I',0x55000120))
  u.mem_write(0x55000120,struct.pack('<II',phase,value))
  self.call(u,'ab_dispatch',self.controller,e)

 def test_shutdown_survives_owner_invalidation_inside_original_live_entry(self):
  u=self.begin();self.main_switch(u,2,0)
  def retire(m,a,n,_):
   if a==self.externals['m10v_ab_live_enter_original']:m.mem_write(0x55063910,bytes(4))
  u.hook_add(UC_HOOK_CODE,retire)
  before=self.count('m10v_settings_factory_original')
  self.call(u,'ab_live_enter',self.controller,0x08000000,0)
  self.assertEqual(self.count('m10v_settings_factory_original'),before)

 def test_new_owner_restores_normal_live_initialization(self):
  u=self.begin();self.main_switch(u,2,0);self.call(u,'top_ctor',self.owner)
  before=self.count('m10v_settings_factory_original')
  self.call(u,'ab_live_enter',self.controller,0x08000000,0)
  self.assertEqual(self.count('m10v_settings_factory_original'),before+1)

 def test_main_press_and_shutter_edges_do_not_suppress_normal_live_initialization(self):
  for key,phase,value in ((1,1,0),(1,1,1),(1,2,1),(2,2,0),(3,2,0)):
   with self.subTest(key=key,phase=phase,value=value):
    u=self.begin();e=self.event(u,key);u.mem_write(e+4,struct.pack('<I',0x55000120))
    u.mem_write(0x55000120,struct.pack('<II',phase,value))
    self.call(u,'ab_dispatch',self.controller,e)
    before=self.count('m10v_settings_factory_original')
    self.call(u,'ab_live_enter',self.controller,0x08000000,0)
    self.assertEqual(self.count('m10v_settings_factory_original'),before+1)

 def test_power_latch_precedes_reentrant_native_dispatch_and_preserves_return(self):
  u=self.begin();queued=[]
  def reenter(m,a,n,_):
   if a==self.externals['m10v_ab_dispatch_original']:
    m.reg_write(UC_ARM_REG_R0,self.controller);m.reg_write(UC_ARM_REG_R1,0x08000000)
    m.reg_write(UC_ARM_REG_R2,0)
    m.reg_write(UC_ARM_REG_PC,self.externals['m10v_settings_controller_ab_live_enter'])
   elif a==self.externals['m10v_ab_live_enter_original']:
    queued.append(a);m.reg_write(UC_ARM_REG_R0,0x73)
  u.hook_add(UC_HOOK_CODE,reenter)
  e=self.event(u,1);u.mem_write(e+4,struct.pack('<I',0x55000120))
  u.mem_write(0x55000120,struct.pack('<II',2,0))
  self.assertEqual(self.call(u,'ab_dispatch',self.controller,e),0x73)
  self.assertEqual(len(queued),1)
  self.assertFalse(self.count('m10v_settings_factory_original'))
  self.assertFalse(self.count('m10v_camera_library_reconcile_legacy_selection'))

 def test_invalid_main_packet_press_and_hold_do_not_clear_pending_poweroff(self):
  for payload,phase in ((0,1),(0x55000120,1),(0x55000120,2)):
   with self.subTest(payload=payload,phase=phase):
    u=self.begin();self.main_switch(u,2,0)
    e=self.event(u,1);u.mem_write(e+4,struct.pack('<I',payload))
    u.mem_write(0x55000120,struct.pack('<II',phase,1))
    self.call(u,'ab_dispatch',self.controller,e)
    before=self.count('m10v_settings_factory_original')
    self.call(u,'ab_live_enter',self.controller,0x08000000,0)
    self.assertEqual(self.count('m10v_settings_factory_original'),before)

 def test_main_release_outside_adj_does_not_latch_shutdown_during_startup(self):
  u=self.begin();self.route=0x08000000;self.main_switch(u,2,0)
  before=self.count('m10v_settings_factory_original')
  self.call(u,'ab_live_enter',self.controller,0x08000000,0)
  self.assertEqual(self.count('m10v_settings_factory_original'),before+1)

 def test_direct_native_main_selector_also_protects_shutdown_live_return(self):
  # Native 532231e4 forwards MAIN directly to 53221a1c; it need not pass
  # through our BaseController physical-packet recovery hook first.
  u=self.begin();self.call(u,'ab_selector',0x55070000,1)
  before=self.count('m10v_settings_factory_original')
  self.call(u,'ab_live_enter',self.controller,0x08000000,0)
  self.assertEqual(self.count('m10v_settings_factory_original'),before)
  self.assertEqual(self.count('m10v_ab_selector_original'),1)

 def test_direct_adj_main_event_also_protects_shutdown_live_return(self):
  u=self.begin();self.call(u,'ab_adj_event',self.controller,self.event(u,1))
  before=self.count('m10v_settings_factory_original')
  self.call(u,'ab_live_enter',self.controller,0x08000000,0)
  self.assertEqual(self.count('m10v_settings_factory_original'),before)

 def test_initialized_live_return_never_repeats_factory_or_journal_migration(self):
  u=self.begin();self.call(u,'ab_live_enter',self.controller,0x08000000,0)
  before=len(self.events)
  self.call(u,'ab_live_enter',self.controller,0x08000000,0)
  names={e[0] for e in self.events[before:]}
  self.assertFalse(names&{'m10v_settings_factory_original','m10v_camera_library_reconcile_legacy_selection',
                          'm10v_camera_library_load'},'A/B exit must reuse the initialized shooting state')

 def test_camera_log_main_close_late_disp_a1_never_reopens_or_swallows_navigation(self):
  # D1 camera sequences224..244: physical DISP opens host; MAIN ->0x35;
  # delayed logical0x37 arrives afterwards, followed by native0xa1.
  u=self.begin();self.call(u,'ab_setup',self.controller,self.event(u,0x37),self.route)
  self.call(u,'ab_selector',0x55070000,1)
  for key in (1,0x35):self.call(u,'ab_adj_event',self.controller,self.event(u,key))
  before=len(self.ui)
  self.call(u,'ab_adj_event',self.controller,self.event(u,0x37))
  self.assertEqual(len(self.ui),before,'late DISP must not reopen the shutting-down picker')
  native=self.count('m10v_ab_adj_event_original')
  self.assertEqual(self.call(u,'ab_adj_event',self.controller,self.event(u,0xa1)),0)
  self.assertEqual(self.count('m10v_ab_adj_event_original'),native+1)

 def test_direct_adj_host_has_no_pending_navigation_to_consume_native_a1(self):
  u=self.begin();self.call(u,'ab_setup',self.controller,self.event(u,0x37),self.route)
  native=self.count('m10v_ab_adj_event_original')
  self.assertEqual(self.call(u,'ab_adj_event',self.controller,self.event(u,0xa1)),0)
  self.assertEqual(self.count('m10v_ab_adj_event_original'),native+1)

 def test_menu_navigation_only_consumes_a1_while_attachment_is_actually_pending(self):
  u=self.begin();self.route=0x02000012;source=0x55051000
  self.call(u,'ab_setup',source,self.event(u,0x37),self.route)
  self.assertEqual(self.call(u,'ab_setup',source,self.event(u,0xa1),self.route),1)
  self.assertEqual(self.call(u,'ab_setup',source,self.event(u,0xa1),self.route),0)
  self.call(u,'ab_adj_refresh',self.controller);self.route=0x02000000
  self.assertEqual(self.call(u,'ab_adj_event',self.controller,self.event(u,0xa1)),0)

 def test_main_selector_before_raw_close_also_blocks_active_picker_disp(self):
  u=self.begin();self.call(u,'ab_setup',self.controller,self.event(u,0x37),self.route)
  self.call(u,'ab_selector',0x55070000,1)
  before=len(self.ui)
  for key in (0x36,0x37):self.call(u,'ab_adj_event',self.controller,self.event(u,key))
  self.assertEqual(len(self.ui),before)
  self.assertFalse(self.count('dispatch'),'MAIN is already closing; DISP must not queue a competing return')

 def test_late_disp_release_press_during_queued_live_return_cannot_reopen(self):
  u=self.begin();self.call(u,'ab_setup',self.controller,self.event(u,0x37),self.route)
  self.call(u,'ab_adj_event',self.controller,self.event(u,0x36))
  self.call(u,'ab_adj_event',self.controller,self.event(u,0x37))
  before=len(self.ui)
  for key in (0x36,0x37):self.call(u,'ab_adj_event',self.controller,self.event(u,key))
  self.assertEqual(len(self.ui),before,'queued navigation is still closing the original ADJ')
  self.assertEqual(self.count('dispatch'),1)
  self.assertEqual(self.call(u,'ab_adj_event',self.controller,self.event(u,0xa1)),0)
  self.route=0x08000000;self.call(u,'ab_live_enter',self.controller,self.route,0)
  self.route=0x02000000
  self.call(u,'ab_setup',self.controller,self.event(u,0x36),self.route)
  self.call(u,'ab_setup',self.controller,self.event(u,0x37),self.route)
  self.assertGreater(len(self.ui),before,'a new ADJ session after native LiveView is allowed')

 def test_physical_disp_closing_host_does_not_reopen_it_in_dispatch_recovery(self):
  u=self.begin();self.stock_input_gate(u);self.real_dispatch=False
  original=self.externals['m10v_ab_dispatch_original']
  physical=self.physical(u)
  def forward(m,a,n,_):
   if a==original:
    m.reg_write(UC_ARM_REG_R0,self.controller);m.reg_write(UC_ARM_REG_R1,physical)
    m.reg_write(UC_ARM_REG_PC,self.externals['m10v_settings_controller_ab_adj_exit'])
  u.hook_add(UC_HOOK_CODE,forward)
  self.call(u,'ab_setup',self.controller,self.event(u,0x37),self.route)
  self.call(u,'ab_setup',self.controller,self.event(u,0x36),self.route)
  before=sum(e[0]==0x53394e8c for e in self.ui)
  physical=self.physical(u)
  self.call(u,'ab_dispatch',self.controller,physical)
  self.assertEqual(sum(e[0]==0x53394e8c for e in self.ui),before)
  self.assertEqual(self.count('m10v_ab_adj_exit_original'),1)
 def test_5213_slot_keeps_its_name_and_icon_in_ab_picker(self):
  for film,caption,icon in [(298,1128,774),(291,1104,762),(292,1105,763),(296,1109,767),(297,1110,768)]:
   self.fresh_films=[film,34,35,36,37]
   u=self.begin();self.call(u,'ab_setup',self.controller,self.event(u,0x37),self.route)
   self.assertTrue(any(e[0]==0x533a1734 and e[2]==icon for e in self.ui),film)
   self.assertTrue(any(e[0]==0x533a1808 and e[2]==caption for e in self.ui),film)

 def test_menu_uses_native_adj_route_and_original_parent(self):
  u=self.begin();self.route=0x02000012;source=0x55051000
  self.call(u,'ab_setup',source,self.event(u,0x37),self.route)
  self.assertTrue(any(e[0]=='dispatch' and e[1:4]==(source,0x02000000,0x02000012) for e in self.events))
  self.assertFalse(any(e[0]=='dispatch' and e[2]==0x0200f104 for e in self.events))
  self.route=0x02000000;self.call(u,'ab_adj_refresh',self.controller)
  self.assertTrue(any(e[0]==0x53394e8c for e in self.ui))
 def test_exit_restores_list_before_original_exit_and_destroy_does_not_refresh(self):
  u=self.begin();self.call(u,'ab_setup',self.controller,self.event(u,0x37),self.route)
  self.call(u,'ab_adj_exit',self.controller)
  self.assertTrue(any(e[0]==0x53395224 and e[1:]==(self.list,7,9) for e in self.ui))
  self.assertEqual(self.count('m10v_ab_adj_exit_original'),1)
  self.call(u,'ab_setup',self.controller,self.event(u,0x36),self.route)
  self.call(u,'ab_setup',self.controller,self.event(u,0x37),self.route)
  before=self.count('m10v_ab_adj_refresh_original');self.call(u,'ab_adj_destroy',self.controller)
  self.assertEqual(self.count('m10v_ab_adj_refresh_original'),before)
  self.assertEqual(self.count('m10v_ab_adj_destroy_original'),1)
 def test_power_passes_original_without_navigation_and_private_callbacks_dont_apply(self):
  u=self.begin();self.call(u,'ab_setup',self.controller,self.event(u,0x37),self.route)
  self.call(u,'ab_adj_changed',self.controller)
  self.assertEqual(self.count('m10v_ab_adj_changed_original'),0)
  self.call(u,'ab_adj_event',self.controller,self.event(u,1))
  self.assertEqual(self.count('m10v_ab_adj_event_original'),1)
  self.assertFalse(self.count('dispatch'));self.assertFalse(self.count('activate_tone'))
 def test_foreign_callbacks_and_refresh_do_not_take_active_host(self):
  u=self.begin();self.call(u,'ab_setup',self.controller,self.event(u,0x37),self.route)
  other=self.controller+0x1000
  self.call(u,'ab_adj_changed',other)
  self.assertEqual(self.count('m10v_ab_adj_changed_original'),1)
  before=len(self.ui);self.call(u,'ab_adj_refresh',other)
  self.assertEqual(len(self.ui),before)
  self.call(u,'ab_adj_destroy',other)
  self.call(u,'ab_adj_changed',self.controller)
  self.assertEqual(self.count('m10v_ab_adj_changed_original'),1)
 def test_menu_back_returns_native_parent_and_swallows_duplicate_confirm(self):
  u=self.begin();source=0x55051000;self.route=0x02000012
  self.call(u,'ab_setup',source,self.event(u,0x37),self.route)
  self.route=0x02000000;self.call(u,'ab_adj_refresh',self.controller)
  self.call(u,'ab_adj_event',self.controller,self.event(u,5))
  self.assertTrue(any(e[0]=='dispatch' and e[1:4]==(self.controller,0x02000012,0x10000000) for e in self.events))
  self.assertEqual(self.word(u,self.controller+0x154)&255,1)
  self.route=0x02000012
  self.assertEqual(self.call(u,'ab_setup',source,self.event(u,0xd8),self.route),1)
  self.assertEqual(self.call(u,'ab_setup',source,self.event(u,8),self.route),0)
  self.assertEqual(self.call(u,'ab_setup',source,self.event(u,0xd8),self.route),0)
  self.assertFalse(self.count('activate_tone'))
 def test_reentry_after_exit_and_fn_remains_original(self):
  u=self.begin()
  for _ in range(3):
   self.call(u,'ab_setup',self.controller,self.event(u,0x37),self.route)
   self.call(u,'ab_adj_event',self.controller,self.event(u,0x1b))
   self.call(u,'ab_setup',self.controller,self.event(u,0x36),self.route)
  self.assertEqual(self.count('m10v_ab_adj_event_original'),3)
  self.assertEqual(sum(e[0]==0x53395224 for e in self.ui),3)
  self.assertFalse(self.count('activate_tone'));self.assertFalse(self.count('dispatch'))
 def test_canvas_uses_owned_root_even_when_registration_slot_is_empty(self):
  u=self.begin();root=0x55068000
  u.mem_write(self.controller+4,bytes(4));u.mem_write(self.controller+0x15c,struct.pack('<I',root))
  self.call(u,'ab_setup',self.controller,self.event(u,0x37),self.route)
  self.assertTrue(any(e[0]==0x533ad308 and e[1]==root for e in self.ui))
 def test_pending_menu_attaches_while_global_route_still_reports_source(self):
  u=self.begin();self.route=0x02000012;source=0x55051000
  u.mem_write(self.controller+0x124,struct.pack('<I',0x02000000))
  self.call(u,'ab_setup',source,self.event(u,0x37),self.route)
  self.call(u,'ab_adj_refresh',self.controller)
  self.assertTrue(any(e[0]==0x53394e8c for e in self.ui))
 def stock_input_gate(self,u,enabled=0):
  # Execute original BaseController filtering, including 5316ccf8/5323bc4c.
  # Models/other UI services are boundaries; the physical press gate is real.
  self.real_dispatch=True;keyboard=0x55078000;other=0x5507a000;vt=0x5507c000;noop=0x5507d000
  u.mem_write(noop,bytes.fromhex('0000a0e31eff2fe1'))
  u.mem_write(vt,struct.pack('<16I',*([noop]*16)))
  for at in (keyboard,other):u.mem_write(at,struct.pack('<I',vt))
  u.mem_write(keyboard+0x520,bytes([enabled]));u.mem_write(self.controller+0x124,struct.pack('<I',self.route))
  self.physical_gate=[]
  getters={0x5320b19c,0x5320b73c,0x5320b8bc,0x5320b13c,0x5320b3dc,0x5320b07c,0x5320ae3c,0x5320bcdc,0x5320c03c,0x5320c120,0x5320addc,0x5320b79c,0x5320af5c}
  callbacks={0x53229464,0x5322ae44,0x532b2618,0x5322ce9c,0x532ae708}
  def services(m,a,n,_):
   if a==0x5323bc4c:self.physical_gate.append((m.reg_read(UC_ARM_REG_R1),bytes(m.mem_read(keyboard+0x520,1))[0]));return
   if a==0x5320b1fc:v=keyboard
   elif a==0x5320addc and getattr(self,'physical_mapper',0):v=self.physical_mapper
   elif a in getters:v=other
   elif a in callbacks:v=0
   else:return
   m.reg_write(UC_ARM_REG_R0,v);m.reg_write(UC_ARM_REG_PC,m.reg_read(UC_ARM_REG_LR))
  u.hook_add(UC_HOOK_CODE,services)
 def physical(self,u,phase=1,repeats=1):
  e=self.event(u,4);u.mem_write(e+4,struct.pack('<I',0x55000120));u.mem_write(0x55000120,struct.pack('<II',phase,repeats));return e
 def test_physical_disp_after_original_press_gate_is_filtered(self):
  u=self.begin();self.stock_input_gate(u)
  entry=self.externals.get('m10v_settings_controller_ab_dispatch',0x5316d5dc)
  self.call(u,entry,self.controller,self.physical(u))
  self.assertIn((4,0),self.physical_gate)
  self.assertTrue(any(e[0]==0x53394e8c for e in self.ui))
  self.assertFalse(self.count('activate_tone'));self.assertFalse(self.count('dispatch'))
 def test_filtered_release_and_hold_do_not_open_and_non_ic_remains_original(self):
  u=self.begin();self.stock_input_gate(u)
  entry=self.externals.get('m10v_settings_controller_ab_dispatch',0x5316d5dc)
  self.call(u,entry,self.controller,self.physical(u,2,0))
  self.call(u,entry,self.controller,self.physical(u,2,1))
  self.assertFalse(self.ui)
  self.adj_type=8
  self.call(u,entry,self.controller,self.physical(u))
  self.assertFalse(self.ui)
 def test_failed_native_attachment_does_not_open_on_a_later_refresh(self):
  u=self.begin();self.route=0x02000012
  self.call(u,'ab_setup',0x55051000,self.event(u,0x37),self.route)
  u.mem_write(self.controller+0x15c,bytes(4));self.call(u,'ab_adj_refresh',self.controller)
  u.mem_write(self.controller+0x15c,struct.pack('<I',0x55061000));self.route=0x02000000
  self.call(u,'ab_adj_refresh',self.controller)
  self.assertFalse(self.ui)
 def test_dispatch_other_buttons_and_other_controller_keep_original(self):
  u=self.begin()
  for key in (1,0x1b,0xd0,0xd8):self.call(u,'ab_dispatch',self.controller,self.event(u,key))
  self.call(u,'ab_dispatch',self.controller+0x1000,self.physical(u))
  self.assertEqual(self.count('m10v_ab_dispatch_original'),5)
  self.assertFalse(self.ui);self.assertFalse(self.count('dispatch'))
 def test_invalid_direct_adj_attach_leaves_no_deferred_open(self):
  u=self.begin();u.mem_write(self.controller+0x15c,bytes(4))
  self.call(u,'ab_setup',self.controller,self.event(u,0x37),self.route)
  u.mem_write(self.controller+0x15c,struct.pack('<I',0x55061000))
  self.call(u,'ab_adj_refresh',self.controller)
  self.assertFalse(self.ui)

class CachedLiveReturnTests(NativeHostTests):
 owner_cache=True
 appended_slots=True
 debug=False
 def test_active_pair_live_return_checks_cache_without_storage_and_keeps_switching(self):
  self.preview_ready=True
  u=self.begin();self.route=0x08000000
  self.call(u,'ab_live_enter',self.controller,self.route,0)
  self.route=0x02000000
  self.call(u,'ab_setup',self.controller,self.event(u,0x37),self.route)
  self.call(u,'ab_adj_event',self.controller,self.event(u,0xd8))
  self.call(u,'ab_adj_event',self.controller,self.event(u,0xd8))
  self.assertEqual(self.ab_tone,25)
  self.route=0x08000000;before=len(self.events)
  self.call(u,'ab_live_enter',self.controller,self.route,0)
  names={e[0] for e in self.events[before:]}
  self.assertNotIn('m10v_camera_library_load',names)
  self.assertNotIn('m10v_camera_library_reconcile_legacy_selection',names)
  self.assertIn('m10v_camera_library_preview',names)
  self.call(u,'ab_selector',0,0x36);self.call(u,'ab_selector',0,0x37)
  self.assertEqual(self.ab_tone,16,'cached return must preserve the active pair')

 def test_failed_initialization_retries_then_stops_reloading_until_owner_replaced(self):
  for failure in ('load_fail','reconcile_fail'):
   with self.subTest(failure=failure):
    u=self.begin();self.route=0x08000000;setattr(self,failure,True)
    self.call(u,'ab_live_enter',self.controller,self.route,0)
    setattr(self,failure,False);before=self.count('m10v_camera_library_reconcile_legacy_selection')
    self.call(u,'ab_live_enter',self.controller,self.route,0)
    self.assertEqual(self.count('m10v_camera_library_reconcile_legacy_selection'),before+1)
    before=self.count('m10v_camera_library_load')
    self.call(u,'ab_live_enter',self.controller,self.route,0)
    self.assertEqual(self.count('m10v_camera_library_load'),before)

 def test_missing_or_changed_pair_cache_stops_ab_without_storage_fallback(self):
  for reason in ('missing','changed'):
   with self.subTest(reason=reason):
    self.preview_ready=True
    u=self.begin();self.route=0x08000000;self.call(u,'ab_live_enter',self.controller,self.route,0)
    self.route=0x02000000
    self.call(u,'ab_setup',self.controller,self.event(u,0x37),self.route)
    for _ in range(2):self.call(u,'ab_adj_event',self.controller,self.event(u,0xd8))
    if reason=='missing':self.preview_ready=False
    else:self.fresh_films=[38,34,35,36,37]
    self.route=0x08000000;before=self.count('m10v_camera_library_load')
    self.call(u,'ab_live_enter',self.controller,self.route,0)
    self.assertEqual(self.count('m10v_camera_library_load'),before)
    before=self.count('activate_tone');native=self.count('m10v_ab_selector_original')
    self.call(u,'ab_selector',0,0x36);self.call(u,'ab_selector',0,0x37)
    self.assertEqual(self.count('activate_tone'),before)
    self.assertEqual(self.count('m10v_ab_selector_original'),native+2)

class ExitCheckpointTests(NativeHostTests):
 debug=True
 exit_trace=True
 def checkpoints(self):return [e[1] for e in self.events if e[0]=='m10v_debug_log' and 230<=e[1]<=269]
 def test_native_exit_has_before_and_after_with_no_trace_dependency(self):
  u=self.begin();self.events.clear()
  self.call(u,'ab_adj_event',self.controller,self.event(u,0x35))
  self.call(u,'ab_adj_exit',self.controller)
  self.assertEqual(self.checkpoints(),[230,231,237,264,238])
  self.assertEqual(self.count('m10v_ab_adj_exit_original'),1)
 def test_host_restore_and_disp_navigation_have_ordered_checkpoints(self):
  u=self.begin();self.call(u,'ab_setup',self.controller,self.event(u,0x37),self.route)
  self.call(u,'ab_adj_event',self.controller,self.event(u,0x36));self.events.clear()
  self.call(u,'ab_adj_event',self.controller,self.event(u,0x37))
  self.assertEqual(self.checkpoints(),[230,248,232,233,234,235,236,249,250,231])
  self.assertEqual(self.count('dispatch'),1)
 def test_native_block_leaves_pre_call_checkpoint_without_inventing_return(self):
  u=self.begin();self.events.clear()
  def stop(m,a,n,_):
   if a==self.externals['m10v_ab_adj_exit_original']:m.emu_stop()
  u.hook_add(UC_HOOK_CODE,stop)
  u.reg_write(UC_ARM_REG_R0,self.controller);u.reg_write(UC_ARM_REG_SP,0x100f0000);u.reg_write(UC_ARM_REG_LR,0x10000000)
  u.emu_start(self.externals['m10v_settings_controller_ab_adj_exit'],0x10000000,count=1000000)
  self.assertEqual(self.checkpoints(),[237,264])
