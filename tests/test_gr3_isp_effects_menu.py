"""Real ARM UI controller with explicit camera persistence service doubles."""
import json
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from unicorn import UC_HOOK_CODE
from unicorn import arm_const as A
from scripts.build_gr3_border_wait_guard import FLAGS
from scripts.build_gr3_digital_hdf import official_rtos
from scripts import build_gr3_hdf_menu as builder
from tests import test_gr3_hdf_menu as legacy

ROOT=Path(__file__).resolve().parents[1]
NAMES=('m10v_hdf_load','m10v_hdf_save','m10v_border_camera_refresh','m10v_border_camera_save',
 'm10v_isp_effects_camera_init','m10v_isp_effects_camera_refresh','m10v_isp_effects_camera_save','m10v_isp_effects_camera_snapshot',
 'm10v_hdf_menu_parent_ctor','m10v_hdf_menu_parent_dtor','m10v_hdf_menu_parent_factory','m10v_hdf_menu_parent_key_route','m10v_hdf_menu_vtable','m10v_debug_log')
STUBS={name:0x53000100+4*i for i,name in enumerate(NAMES)}

class EffectsMenuTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup);p=Path(cls.tmp.name)
  source=ROOT/'native/gr3/m10v_hdf_menu.c';obj=p/'menu.o';stateobj=p/'state.o';elf=p/'menu.elf';link=p/'link.ld'
  cls.flags=[*FLAGS,'-DM10V_PURE_ISP_EFFECTS=1','-DM10V_BORDER_ENABLED=1','-DM10V_HDF_ENABLED=1','-DM10V_ADJ_EXTRA_CAMERA=1','-DM10V_HDF_OWNER_OFFSET=0x13bc','-DM10V_BORDER_CACHE_OWNER_OFFSET=0x1564','-DM10V_ISP_EFFECT_CACHE_OWNER_OFFSET=0x15bc']
  cls.flags.append('-DM10V_DEBUG_MODE=1')
  subprocess.run([shutil.which('clang'),*cls.flags,'-c',str(source),'-o',str(obj)],check=True,capture_output=True)
  subprocess.run([shutil.which('clang'),*FLAGS,'-c',str(ROOT/'native/gr3/m10v_isp_effects_state.c'),'-o',str(stateobj)],check=True,capture_output=True)
  link.write_text('\n'.join(f'{n} = {v};' for n,v in STUBS.items())+'\nSECTIONS { . = 0x54110000; .text : { *(.text*) } .rodata : { *(.rodata*) } /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) } }')
  subprocess.run([shutil.which('ld.lld'),'-T',str(link),'--entry=m10v_hdf_menu_key',str(obj),str(stateobj),'-o',str(elf)],check=True,capture_output=True)
  b=elf.read_bytes();sh=struct.unpack_from('<I',b,32)[0];count=struct.unpack_from('<H',b,48)[0]
  rows=[struct.unpack_from('<10I',b,sh+40*i) for i in range(count)];image=bytearray();symbols={}
  for r in rows:
   if r[2]&2 and r[5]:
    assert r[1]==1 and not r[2]&1
    off=r[3]-0x54110000;image.extend(bytes(max(0,off+r[5]-len(image))));image[off:off+r[5]]=b[r[4]:r[4]+r[5]]
   if r[1]==2:
    sr=rows[r[6]];strings=b[sr[4]:sr[4]+sr[5]]
    for at in range(r[4],r[4]+r[5],16):
     name,value,_,info,_,section=struct.unpack_from('<IIIBBH',b,at);name=strings[name:].split(b'\0')[0].decode()
     assert section or not name
     if name and info&15==2:symbols[name]=value
  cls.m={'base':0x54110000,'symbols':symbols};cls.b=bytes(image);cls.rom=official_rtos()
 put=legacy.HdfMenuTests.put
 get=legacy.HdfMenuTests.get
 call=legacy.HdfMenuTests.call
 key=legacy.HdfMenuTests.key
 ready=legacy.HdfMenuTests.ready
 def setUp(self):
  legacy.HdfMenuTests.setUp(self);self.settings=[0]*8;self.saved_settings=[];self.camera_events=[];self.save_error=False;self.hdf_saved=[];self.border_saved=[];self.traces=[];self.refresh_error=False
  def service(u,pc,n,data):
   names={v:k for k,v in STUBS.items()};name=names.get(pc)
   if not name:return
   r=[u.reg_read(getattr(A,f'UC_ARM_REG_R{i}')) for i in range(4)];result=0;self.camera_events.append(name)
   if name=='m10v_debug_log':self.traces.append(r+[self.get(u.reg_read(A.UC_ARM_REG_SP))])
   elif name=='m10v_isp_effects_camera_refresh':result=0xfffffffe if self.refresh_error else 0
   elif name=='m10v_isp_effects_camera_snapshot':u.mem_write(r[0],struct.pack('<8I',*self.settings));self.put(r[1],1);result=1
   elif name=='m10v_isp_effects_camera_save':
    self.saved_settings.append(list(struct.unpack('<8I',u.mem_read(r[1],32))))
    if self.save_error:result=0xffffffff
    else:self.settings=self.saved_settings[-1].copy()
   elif name=='m10v_hdf_load':self.put(r[0],0)
   elif name=='m10v_hdf_save':self.hdf_saved.append(r[0])
   elif name=='m10v_border_camera_save':self.border_saved.append(r[1]);self.put(self.page+0x1b0,r[1])
   elif name=='m10v_isp_effects_camera_init':
    u.mem_write(self.page+0x200,bytes(44));self.put(self.page+0x200,0x31434649);self.put(self.page+0x204,2)
   elif name=='m10v_hdf_menu_vtable':result=0x55009000
   elif name.startswith('m10v_hdf_menu_parent_'):result=r[0]
   u.reg_write(A.UC_ARM_REG_R0,result);u.reg_write(A.UC_ARM_REG_PC,u.reg_read(A.UC_ARM_REG_LR))
  self.u.hook_add(UC_HOOK_CODE,service)
 def rows(self):
  return [next((id for w,id in reversed(self.captions) if w==self.get(self.page+0x158+(4+i)*4)),None) for i in range(4)]
 def child(self,index):
  for _ in range(index):self.key(0xd1)
  self.key(0xd8)
 def test_effects_root_only_shows_hdf_and_border(self):
  self.ready();self.call('m10v_hdf_menu_enter',self.page,0,0)
  for _ in range(4):self.key(0xd1)
  self.assertEqual(self.get(self.page+0x1a4),1)
  self.assertEqual(self.rows()[:2],[1141,1155])
  self.assertFalse(any('isp_effects' in event for event in self.camera_events))
 def test_resources_keep_fn_labels_and_direction_choices(self):
  words=json.loads((ROOT/'native/gr3/m10v_isp_effects_resources.json').read_text())
  self.assertEqual(len(words),23)
  self.assertEqual(words[:3],['漏光','颗粒','模糊'])
  self.assertEqual(words[4],'漏光位置 左上右下随机')
  self.assertEqual([words[i] for i in (12,7,13,8,14)],['左','上','右','下','随机'])
 def test_hdf_border_remain_independent_children(self):
  self.ready();self.child(0);self.key(0xd1);self.key(0xd8)
  self.assertEqual(self.hdf_saved,[1]);self.assertEqual(self.get(self.page+0x18c),1)
  self.key(0xd1);self.key(0xd8);self.key(0xd1);self.key(0xd1);self.key(0xd8)
  self.assertEqual(self.border_saved,[2]);self.assertEqual(self.get(self.page+0x18c),1)
  self.assertEqual(self.saved_settings,[])
 def test_adj_border_opens_directly_and_closes_to_parent(self):
  route=0x0200f108
  self.assertEqual(self.call('m10v_hdf_menu_factory',self.owner,route),self.page)
  self.assertEqual(self.call('m10v_hdf_menu_ready',self.page,route),1)
  self.call('m10v_hdf_menu_enter',self.page,route,0)
  self.assertEqual(self.rows()[:3],[972,1156,1157])
  self.assertNotIn('m10v_hdf_load',self.camera_events)
  self.key(0xd1);self.key(0xd8)
  self.assertEqual(self.border_saved,[1])
  self.assertEqual(self.closed,[self.page])
  self.assertEqual(self.call('m10v_hdf_menu_ready',self.page,route),1)
  self.key(0xd1);self.key(0x86)
  self.assertEqual(self.border_saved,[1])
  self.assertEqual(self.closed,[self.page,self.page])
  self.ready()
  self.assertEqual(self.get(self.page+0x18c),1)
 def test_controller_keeps_preexisting_owner_extent(self):
  symbols={f'm10v_hdf_menu_{n}':0x54101000+i*4 for i,n in enumerate(('destroy','enter','ready','key','factory','top_ctor','top_dtor','key_route'))}
  settings={'rows':[],'exports':{'m10v_settings_top_dtor_original':0x53190000,'m10v_settings_factory_original':0x53190004}}
  _,m=builder.build_hooks(0x54120000,symbols,settings,film_library=False,pure_isp_effects=True)
  self.assertEqual(m['owner_bytes'],0x13bc+0x22c)
  self.call('m10v_hdf_menu_top_dtor',self.owner)
  self.assertFalse(any('isp_effects' in event for event in self.camera_events))
