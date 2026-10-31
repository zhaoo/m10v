"""Independent settings wiring for exactly GR III 2.10, not enabled by default.

Returned patches are preimage-checked by the independent firmware auditor.
Owner tail contains two controllers, not arbitrary writable RAM globals.
"""
import struct
from scripts.build_gr3_menu_patches import assembly, branch, movw
BASE_VTABLE=[0x5316c7e0,0x5316c774,0x5316c7bc,0x5316c740,0x5316c748,
 0x5316dfa8,0x5316c74c,0x5316c750,0x5316c754,0x5316c758,
 0x5316c760,0x5316c768,0x5316d0f0,0x5316c76c,0x5316cec8]

def build_settings_hooks(base,symbols,live_color=False,appended_slots=False,custom_zoom=True):
 image=bytearray();exports={};patches=[];rows=[]
 def data(raw):
  image.extend(bytes(-len(image)&3));a=base+len(image);image.extend(raw);return a
 def stub(text):
  image.extend(bytes(-len(image)&3));return data(assembly(text,base+len(image)))
 def patch(a,expected,replacement,label):
  patches.append(dict(address=a,expected=expected.hex(),replacement=replacement.hex(),label=label))
 def word(a,old,new,label):patch(a,struct.pack('<I',old),struct.pack('<I',new),label)
 def trampoline(name,a,old):
  at=base+len(image);exports[name]=data(struct.pack('<II',old,branch(at+4,a+4)))
 trampoline('m10v_settings_factory_original',0x5316f3b8,0xe300313b)
 trampoline('m10v_settings_top_dtor_original',0x5319667c,0xe1a0c00d)
 ab_hooks=[]
 for name,address in [('selector',0x53221a1c),('mapper',0x5320c844),('live_enter',0x5317696c),('live_leave',0x53176de4),('live_destroy',0x53170b50),('live_event',0x531771c0),('adj_event',0x531a4db8),('adj_refresh',0x531a4114),('adj_exit',0x531a3e88),('adj_destroy',0x5319ff24),('adj_changed',0x531a4cfc),('dispatch',0x5316d5dc)]:
  old=0xe1d130b0 if name=='adj_event' else 0xe5d02270 if name=='adj_exit' else 0xe1a0c00d
  trampoline('m10v_ab_'+name+'_original',address,old)
  ab_hooks.append(dict(address=address,expected=old,replacement=branch(address,symbols['m10v_settings_controller_ab_'+name]),name='A/B '+name))
 table=list(BASE_VTABLE)
 table[0x30//4]=symbols['m10v_settings_controller_ab_render']
 for offset,name in [(4,'destroy'),(8,'destroy'),(0x1c,'enter'),(0x24,'ready'),(0x28,'key')]:
  table[offset//4]=symbols['m10v_settings_controller_'+name]
 vt=data(struct.pack('<15I',*table))
 from scripts.gr3_target_relocations import relocations
 relocations.data(vt,struct.pack('<15I',*table))
 exports['m10v_settings_controller_vtable']=stub(f'movw r0,#{vt&65535};movt r0,#{vt>>16};bx lr')
 for address,original,name,link in [(0x5316f3b8,0xe300313b,'factory',False),
   (0x5319667c,0xe1a0c00d,'top_dtor',False),(0x5316fcf8,0xeb00ab5a,'top_ctor',True),
   (0x53221a4c,0xeb001c7e,'key_route',True)]:
  word(address,original,branch(address,symbols['m10v_settings_controller_'+name],link),'settings '+name)
 word(0x5316fcec,0xe30103bc,movw(0,0x613c if live_color else 0x213c),'TopMenu owned controller tail')
 word(0x53b36adc,0x1e1d1b19,(32<<24)|0x1d1b19,'Setup row count')
 for i,caption in enumerate([937,938]):
  render=stub('push {r4,lr};mov r4,r1;mov r0,r4;mov r1,#0;bl 0x5339de20;'+
   f'mov r0,r4;movw r1,#{caption};mov r2,r1;pop {{r4,lr}};b 0x5339dc70')
  rows.append(render)
  patch(0x53b36bd0+i*8,bytes(8),struct.pack('<II',render,0),'Setup independent row renderer')
  word(0x53b36c88+i*4,0x10000000,[0x0200f100,0x0200f101][i],'Setup independent destination')
 if custom_zoom:word(0x53b37018,0x02000074,0x0200f105,'Crop selection and focal editor entry')
 return bytes(image),dict(exports=exports,vtable=vt,rows=rows,patches=patches,owner_bytes=0x613c if live_color else 0x213c,
   private_routes=[0x0200f100,0x0200f101,0x0200f103,0x0200f104]+([0x0200f105] if custom_zoom else []),ab_hooks=ab_hooks,
   ab_host={'stage':'compare','route':0x02000000,'menu_parent':0x02000012,'custom_root':False,'tone_changes':True,'root_rows':0,'direct_pair':True,'live_ui':False,'picker_page_rows':6,'choices':22 if appended_slots else 12},camera_tested=False)
