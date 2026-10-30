"""Execute compiled GR4 menu flows with original count/index/list getter.

Journal writes, redraw, active-tone hardware access and outer native handlers
are explicit mocks; no framebuffer or camera interaction is claimed.
"""
from pathlib import Path
import shutil,struct,subprocess,tempfile,unittest,json,sys
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"vendor/gr4"))
from gr4_editor.firmware import _Memory
from gr4_editor.filter_reader import _native_lookup,_name_resource,_icon_resource
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import *
from scripts.build_gr3_m10v_library import FLAGS,link_object
from scripts.build_gr3_menu_patches import branch
ROOT=Path(__file__).resolve().parents[1]
CODE=0x540c0000
TRAMP=0x540b6000
STUB=0x540b0000
MODEL=0x5508a6dc
CONTROLLER=0x10002000
LIST=0x10004000
class MenuTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.profile=json.loads((ROOT/'native/gr4/ui-abi.json').read_text())
  cls.firmware=(ROOT/'data/research/gr4/RTOS.bin').read_bytes()
  names=['load','select','texture','halation','effects','stamp']
  cls.external={'m10v_camera_library_'+n:STUB+i*4 for i,n in enumerate(names)}
  cls.external['m10v_library_valid']=STUB+0x40
  with tempfile.TemporaryDirectory() as d:
   obj=Path(d)/'menu.o'
   subprocess.run([shutil.which('clang'),*FLAGS,'-c',str(ROOT/'native/gr4/m10v_library_menu.c'),'-o',str(obj)],capture_output=True,check=True)
   cls.code,cls.symbols=link_object(obj.read_bytes(),CODE,cls.external,'m10v_menu_',additional_exports=('m10v_menu_rows',),omitted_exports=('m10v_menu_recorded_icon',))
 def machine(self):
  u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
  for a,n in [(0x53000000,0x2000000),(0x55000000,0x1000000),(0x10000000,0x200000)]:u.mem_map(a,n)
  u.mem_write(0x53000000,self.firmware);u.mem_write(CODE,self.code)
  for a in [0x5508207c,0x55082110]:u.mem_write(a,struct.pack('<I',1))
  for off,a in [(0x80,0x533bebdc),(0x90,0x533bedb0)]+[(off,self.profile['image_control_entries'][name]['address']) for off,name in [(0x10,'name'),(0x20,'value_name'),(0x30,'icon'),(0x40,'value_icon')]]:
   original=self.firmware[a-0x53000000:a-0x53000000+4]
   u.mem_write(TRAMP+off,original+struct.pack('<I',branch(TRAMP+off+4,a+4)))
  native=bytes(list(range(11,31))+list(range(36,41)))
  u.mem_write(0x10007000,native);u.mem_write(MODEL+0x24,struct.pack('<III',0x10007000,0x10007000+len(native),0x10007000+len(native)))
  u.mem_write(CONTROLLER+0x178,struct.pack('<I',LIST));u.mem_write(CONTROLLER+0x164,struct.pack('<I',0x10006000))
  u.mem_write(MODEL,bytes([36]));self.events=[];self.active=40;self.fail_save=False;self.fail_load=False;self.saved=bytearray(104)
  for i in range(5):struct.pack_into('<H',self.saved,12+i*8,33+i)
  rev={a:n for n,a in self.external.items()}
  def hook(m,a,n,c):
   args=[m.reg_read(r) for r in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]]
   name=rev.get(a)
   if name:
    if name=='m10v_camera_library_load':m.mem_write(args[0],bytes(self.saved));result=0xffffffff if self.fail_load else 0
    elif name=='m10v_library_valid':result=1
    else:self.events.append((name,*args));result=0xffffffff if self.fail_save else 0
    m.reg_write(UC_ARM_REG_R0,result)
   elif a==0x533b64e0:m.reg_write(UC_ARM_REG_R0,self.active)
   elif a==TRAMP:self.events.append(('activate',*args))
   elif a==0x531c615c:self.events.append(('redraw',*args))
   elif a==0x53571788:self.events.append(('focus',*args))
   elif a==0x5357338c:self.events.append(('caption',*args))
   elif a in [TRAMP+0x50,TRAMP+0x60,TRAMP+0xa0,TRAMP+0xb0]:self.events.append(('original',a,*args));m.reg_write(UC_ARM_REG_R0,123)
   elif a==0x538ed930:
    self.assertNotEqual(args[0],0,'stock index precondition failed')
   else:return
   m.reg_write(UC_ARM_REG_PC,m.reg_read(UC_ARM_REG_LR))
  u.hook_add(UC_HOOK_CODE,hook);return u
 def call(self,u,name,*args):
  for r,v in zip([UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3],args):u.reg_write(r,v)
  u.reg_write(UC_ARM_REG_SP,0x100f0000);u.reg_write(UC_ARM_REG_LR,0x10000000)
  u.emu_start(name if isinstance(name,int) else self.symbols['m10v_menu_'+name],0x10000000,count=100000)
  self.assertEqual(u.reg_read(UC_ARM_REG_PC),0x10000000);self.assertEqual(u.reg_read(UC_ARM_REG_SP),0x100f0000)
  return u.reg_read(UC_ARM_REG_R0)
 def select(self,u,index):u.mem_write(LIST+0x110,struct.pack('<H',index));self.call(u,'confirm',CONTROLLER)
 def group(self,u,group):u.mem_write(MODEL+0x21,bytes([group]))
 def mode(self,u):return u.mem_read(MODEL+0x21,1)[0]
 def test_native_text_icon_identity_and_icon_flag_contract(self):
  self.assertEqual(self.profile['image_control_entries']['name']['address'],0x5337f824)
  self.assertEqual(self.profile['image_control_entries']['icon']['address'],0x53380fac)
  self.assertEqual(self.profile['image_control_entries']['value_name']['address'],0x53397044)
  self.assertEqual(self.profile['image_control_entries']['value_icon']['address'],0x533971cc)
  memory=_Memory(self.firmware);u=self.machine()
  image=SimpleNamespace(icon_bytes=(ROOT/'data/research/gr4/ICONBIN.bin').read_bytes())
  for style in range(11,31):
   text=_native_lookup(memory,0x5337f824,style)
   icon=_native_lookup(memory,0x53380fac,style)
   self.assertEqual(self.call(u,'name',0,style),text)
   self.assertEqual(self.call(u,'icon',0,style,0),icon)
   self.assertEqual(self.call(u,'icon',0,style,1),0)
   self.assertTrue(_name_resource(memory,text)[0])
   self.assertGreater(_icon_resource(memory,image,icon)['bytes'],0)
  self.assertEqual(_name_resource(memory,self.call(u,'name',0,11))[0],'Standard')
  for value in [11,20,31,32,33]:
   self.assertEqual(self.call(u,'value_name',0,value),self.call(u,0x53397044,0,value))
   self.assertEqual(self.call(u,'value_icon',0,value),self.call(u,0x533971cc,0,value))
 def test_preserves_25_real_stock_and_appends_one_private_entry(self):
  u=self.machine();self.assertEqual(self.call(u,'count',MODEL),26)
  self.assertEqual([self.call(u,'index',MODEL,i) for i in range(25)],list(range(11,31))+list(range(36,41)))
  self.assertEqual(self.call(u,'index',MODEL,25),128)
  for kind in [1,2]:
   u.mem_write(MODEL+0x1f,bytes([kind]));self.assertEqual(self.call(u,'count',MODEL),25)
 def test_private_entry_captures_live_tone_without_destroying_snapshot(self):
  u=self.machine();self.select(u,25)
  self.assertEqual(self.mode(u),1);self.assertEqual(u.mem_read(MODEL+0x22,1)[0],40)
  self.assertEqual(u.mem_read(MODEL,1)[0],36)
  self.assertFalse(any(e[0]=='activate' for e in self.events))
  self.assertTrue(any(e[0]=='redraw' for e in self.events))
 def test_all_five_carriers_activate_exact_native_slot(self):
  for i in range(5):
   u=self.machine();self.group(u,6);self.select(u,i)
   self.assertEqual([e[2] for e in self.events if e[0]=='activate'],[36+i])
   self.assertEqual(self.mode(u),1)
 def test_failed_film_save_keeps_group_and_never_activates(self):
  u=self.machine();self.group(u,2);u.mem_write(MODEL+0x22,b'\x28');self.fail_save=True;self.select(u,3)
  self.assertEqual(self.mode(u),2)
  self.assertFalse(any(e[0]=='activate' for e in self.events))
  self.assertTrue(any(e[0]=='caption' and e[2]==1062 for e in self.events))
  self.fail_save=False;self.select(u,3)
  self.assertEqual(self.mode(u),1)
  self.assertEqual([e[2:4] for e in self.events if e[0]=='m10v_camera_library_select'],[(4,68),(4,68)])
  self.assertEqual([e[2] for e in self.events if e[0]=='activate'],[40])
 def test_nested_controls_keep_stamps_and_retire_texture_routes(self):
  u=self.machine();self.group(u,1)
  self.assertEqual([self.call(u,'index',MODEL,i) for i in range(self.call(u,'count',MODEL))],[129,132,133,214])
  self.select(u,1);self.assertEqual(self.mode(u),5)
  for group in [3,4,15,16,17,18,19,20]:
   self.group(u,group);before=list(self.events)
   self.assertEqual(self.call(u,'count',MODEL),0)
   self.assertEqual(self.call(u,'index',MODEL,0),0)
   self.select(u,0);self.assertEqual(self.events,before)
  self.group(u,5);self.select(u,4);self.assertEqual(self.mode(u),8)
  self.select(u,3);self.assertEqual(self.mode(u),5)
  stamps=[e for e in self.events if e[0]=='m10v_camera_library_stamp'];self.assertEqual(stamps[-1][2:5],(0,0,3))
 def test_back_done_and_third_native_footer_are_bounded(self):
  u=self.machine();self.group(u,2);self.select(u,46);self.assertEqual(self.mode(u),1)
  self.group(u,2);self.select(u,48);self.assertEqual(self.mode(u),2) # third footer is inert in private mode
  self.select(u,47);self.assertEqual(self.mode(u),0)
  self.assertTrue(any(e[0]=='original' and e[1]==TRAMP+0x60 for e in self.events))
 def test_private_pages_have_exactly_two_footers_while_stock_retains_three(self):
  u=self.machine();self.assertEqual(self.call(u,'rows',CONTROLLER),29)
  self.group(u,2);self.assertEqual(self.call(u,'rows',CONTROLLER),48)
  self.group(u,3);self.assertEqual(self.call(u,'rows',CONTROLLER),2)
 def test_gr4_ok_key_and_back_events(self):
  u=self.machine();u.mem_write(LIST+0x110,struct.pack('<H',25));u.mem_write(0x10000100,struct.pack('<H',0xe0))
  self.call(u,'key',CONTROLLER,0x10000100);self.assertEqual(self.mode(u),1)
  u.mem_write(0x10000100,struct.pack('<H',0x8a));self.call(u,'key',CONTROLLER,0x10000100);self.assertEqual(self.mode(u),0)
  self.assertTrue(any(e[0]=='original' and e[1]==TRAMP+0x60 for e in self.events))

if __name__=='__main__':unittest.main()
