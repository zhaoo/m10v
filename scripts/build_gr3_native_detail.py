"""Exact GR III 2.10 stock detail lifecycle relocation for unified runtime.
Stock snapshots are verified against official RTOS again by the Node auditor.
No old standalone state/allocator hooks are included.
"""
import struct
from scripts.build_gr3_menu_patches import assembly, branch, movw
BASE=0x53000000
FIELDS=['Halation Gain','Halation Spread','Highlight Gate','Film Grain','Halation Mode','','','','','','RED Exposure','Charmera Color']
DETAIL_IDS={'halo':[18,19,20,21],'common':[21],'red':[21,28],'charmera':[29],'phoenix':[18,19,20,21,28],'pixel':[]}
STOCK_TABLE=bytes.fromhex('2c4cb35309000000f04ab35309000000144ab3530a000000104fb353090000008c4ab353090000005050b3530a0000000c50b35309000000ac4ab35309000000ec4fb3530a000000584eb3530a000000d049b35304000000b849b3530a000000f449b3530a000000644cb3530a000000784eb3530b000000104bb3530a000000544fb3530a000000304fb3530b000000944fb3530a0000001c4eb3530a000000ec4eb3530b000000844cb3530b000000444ab35305000000b44eb3530b000000f449b3530a000000644cb3530a000000784eb3530b000000104bb3530a000000544fb3530a000000304fb3530b000000944fb3530a0000001c4eb3530a000000ec4eb3530b000000844cb3530b000000444ab35305000000b44eb3530b000000')
STOCK_CAPTIONS=bytes.fromhex('e3011901e1011b01e2011d01da011f01db012101dc012301e5012501e9012f01e9012f0167012f01e9012f01e9013f01dd012701e4013701d9013101de013301e0013501f8000000')
STOCK_SLIDER=bytes.fromhex('0dc0a0e1f0d82de97c5705e3055445e304b04ce268d04de2003095e50060a0e10040a0e320300be55b7701eb9f7a01eb9811d6e5305904eb0afdffeb04408de50f30a0e300308de51420a0e30c208de5233ea0e310308de54020a0e314208de5c730a0e318308de50070a0e108408de50410a0e10820a0e32d30a0e354004be248c807eb093da0e30420a0e100308de50710a0e11e30a0e354004be258c807eb54004be20410a0e15dc807eb647196e554104be20700a0e19fc807eb5c400be50c00a0e37c0814eb0030a0e1d02f00e31b2345e30700a0e1002083e5042a0ce3044083e51a2345e3086083e564104be264300be55c390ce358200be51a3345e35c300be56efb07eb5c301be5040053e10300000a64004be20320a0e30010a0e133ff2fe120201be5003095e5030052e10100001a1cd04be2f0a89de8d1cb19eb')
STOCK_LISTS={1404259372: '0200020102020203020402050206020d000e', 1404259056: '0200020102020203020402050206020d000e', 1404258836: '020202030204020502060207020c020d000e000f', 1404260112: '020202030204020502060207020c020d000f', 1404258956: '020202030204020502060207020d000e000f', 1404260432: '020202030204020502060207020c020d000e000f', 1404260364: '0200020102020203020402050206020d000e', 1404258988: '0200020102020203020402050206020d000e', 1404260332: '02000201020202030204020502060208020d000e', 1404259928: '02000201020202030204020502060209020d000e', 1404258768: '02000201020a0010', 1404258744: '0200020102020203020402050206020b020d000e', 1404258804: '02110200020102020203020402050206020d000e', 1404259428: '02110200020102020203020402050206020d000e', 1404259960: '0211020202030204020502060207020c020d000e000f', 1404259088: '0211020202030204020502060207020c020d000f', 1404260180: '0211020202030204020502060207020d000e000f', 1404260144: '0211020202030204020502060207020c020d000e000f', 1404260244: '02110200020102020203020402050206020d000e', 1404259868: '02110200020102020203020402050206020d000e', 1404260076: '021102000201020202030204020502060208020d000e', 1404259460: '021102000201020202030204020502060209020d000e', 1404258884: '021102000201020a0010', 1404260020: '02110200020102020203020402050206020b020d000e'}

def build_detail(base,symbols,sd_library=True,appended_slots=False,native_grain=False,universal_halation=False):
 if type(native_grain)is not bool:raise ValueError("native grain capability must be boolean")
 detail_ids={variant:[id for id in ids if id!=21 or native_grain] for variant,ids in DETAIL_IDS.items()}
 if universal_halation:
  for variant in detail_ids:
   detail_ids[variant]=[22,18,19,20]+[i for i in detail_ids[variant] if i not in (18,19,20)]
 active_ids=[18,19,20]+([21] if native_grain else [])+([22] if universal_halation else [])+[28,29]
 image=bytearray();entries={};blocks=[]
 def data(raw,label):
  image.extend(bytes(-len(image)&3));a=base+len(image);image.extend(raw);blocks.append([a,a+len(raw),label]);return a
 def stub(text,label):
  image.extend(bytes(-len(image)&3));a=base+len(image);return data(assembly(text,a),label)
 def addr(reg,a):return f'movw {reg},#{a&65535};movt {reg},#{a>>16};'
 # Clone every stock kind, append only the current film's supported IDs.
 # Runtime validation selects the halo/common/RED table for each carrier.
 # Original stock tones outside the enabled carriers retain their original lists.
 # Dynamic resolution returns this table or the untouched stock table.
 # Previously this was restricted to one 800T

 tables={}
 for variant,ids in detail_ids.items():
  table=bytearray(STOCK_TABLE)
  if appended_slots:table+=STOCK_TABLE[:80]
  for i in range(46 if appended_slots else 36):
   a,n=struct.unpack_from('<II',table,i*8)
   raw=bytes.fromhex(STOCK_LISTS[a]);assert len(raw)==n*2
   if appended_slots:raw=b'';n=0
   a=data(raw+bytes(sum(([0,x] for x in ids),[])),'detail '+variant+' list '+str(i))
   struct.pack_into('<II',table,i*8,a,n+len(ids))
  tables[variant]=data(table,'dynamic '+variant+' detail tables')
 table_address=tables['halo']
 # Existing resource extension occupies IDs786..910. Reuse its text descriptors
 # for three captions, Grain and Soft Diffusion, avoiding another global hook.
 caption_ids=[862,863,864,827,1137 if universal_halation else 828,913,913,913,913,913,933,1013 if sd_library else 948]
 captions=data(STOCK_CAPTIONS+b''.join(struct.pack('<HH',i,i) for i in caption_ids),'detail caption pairs')
 # Each call site has already saved LR in the genuine stock prologue.
 for name,reg,ui in [('table_ip','ip','r0'),('table_r3','r3','r0'),('table_selected','r3','r4')]:
  text='push {r0-r12,lr};mrs r0,cpsr;push {r0,r1};'+f'ldr r0,[sp,#{8+(0 if ui=="r0" else 16)}];bl {hex(symbols["m10v_detail_table"])};'
  offset=8+(12 if reg=='r3' else 48)
  text+=f'str r0,[sp,#{offset}];pop {{r0,r1}};msr cpsr_fs,r0;'
  # Both ip sites have live lr=12. BL destroys it before entering this shim.
  if reg=='ip':text+='mov lr,#12;'
  text+='pop {r0-r12,pc};'
  entries[name]=stub(text,name)
 # Constructor precedes tone selection; reserve stock max11 + max10 private rows.
 entries['capacity']=stub('mov r0,#22;bx lr','detail constructor capacity')
 control=symbols['m10v_detail_control']
 # The C gate checks actual ui[0x198] carrier and validated journal.
 # Private IDs can only originate in our validated list, but all dispatches
 # revalidate as well; an invalid/stale row takes the exact stock fallback.
 def gate(idreg,ui,fallback):
  return f'sub ip,{idreg},#18;cmp ip,#12;bhi {hex(fallback)};push {{r0-r3,r12,lr}};mov r0,{ui};bl {hex(symbols["m10v_detail_table"])};'+addr('ip',0x53b3488c)+'cmp r0,ip;pop {r0-r3,r12,lr};beq '+hex(fallback)+';'
 # Intercept before the stock computed branch, restore its original R0-R3,
 # IP/LR and CMP flags, and retain its exact 18-entry handler jump table.
 # This enforces native icon/value geometry for both private and stock rows.
 stock_handlers=struct.unpack('<18I',bytes.fromhex('9c001b53ac001b53bc001b53cc001b53dc001b53ec001b53fc001b530c011b531c011b532c011b533c011b534c011b535c011b536c011b537c011b538c011b539c011b5358001b53'))
 entries['row_dispatch']=stub('push {r0-r3,r12,lr};lsl r2,r3,#16;orr r2,r2,r4;mov r1,r5;mov r0,#8;'+f'bl {hex(control)};'+'pop {r0-r3,r12,lr};cmp r3,#17;ldrls pc,[pc,r3,lsl #2];b 0x531b000c;'+''.join('.word '+hex(a)+';' for a in stock_handlers),'row bounds and stock dispatch')
 entries['row']=stub(gate('r3','r5',0x531b01ac)+f'sub r2,r3,#18;lsl r2,r2,#16;orr r2,r2,r4;mov r1,r5;mov r0,#3;bl {hex(control)};b 0x531b0064','row render')
 entries['current']=stub(gate('r4','r5',0x531b0594)+f'sub r2,r4,#18;mov r1,r5;mov r0,#1;bl {hex(control)};mov r4,r0;b 0x531b045c','current value')
 # Slider clones retain the stock callback closure and stock cancel/return.
 default=stub(f'mov r1,r0;mov r0,#4;mov r2,#0;b {hex(control)}','factory default')
 entries['default']=default
 def clone(maximum,color=False):
  image.extend(bytes(-len(image)&3));destination=base+len(image);start=0x531acfec;stop=0x531ad12c
  mapping={a:destination+a-start+(8 if a>=0x531ad0b4 else 0) for a in range(start,stop+4,4)}
  output=bytearray()
  for a in range(start,stop,4):
   at=mapping[a]
   if a==0x531ad0b4:output+=struct.pack('<II',0xe3500000,branch(at-4,mapping[0x531ad110],condition=0))
   w=struct.unpack_from('<I',STOCK_SLIDER,a-start)[0]
   if w&0x0e000000==0x0a000000:
    d=(w&0xffffff)<<2
    if d&(1<<25):d-=1<<26
    target=a+8+d;w=branch(at,mapping.get(target,target),bool(w&0x1000000),w>>28)
   if a==0x531ad01c:w=0xe1a00006
   if a==0x531ad020:w=branch(at,default,True)
   if a==0x531ad024:w=0xe1a00000
   # Match the stock grain slider: resource 57 and 120-pixel tick pitch.
   if a==0x531ad03c and maximum==3:w=0xe3a03039
   if a==0x531ad03c and color:w=movw(3,760 if sd_library else 754)
   if a==0x531ad060:w=0xe3a02000|maximum
   if a==0x531ad064:w=movw(3,360//maximum)
   output+=struct.pack('<I',w)
  from scripts.gr3_target_relocations import relocations
  relocations.code(destination,output)
  return data(output,'stock slider clone '+str(maximum))
 sliders={n:clone(n) for n in (8,3,2,1)}
 color_slider=clone(3,color=True)
 # Private IDs keep stable meanings across the three visible lists.
 # Restore the original setup frame before dispatch; retain the selected ID
 # in ip because r0 must be the stock controller for the slider constructor.
 exposure_dispatch=stub('push {r0,r4,r12,lr};mov r1,r0;mov r0,#9;mov r2,#0;bl '+hex(control)+';cmp r0,#1;pop {r0,r4,r12,lr};beq '+hex(sliders[1])+';b '+hex(sliders[2]),'film-specific exposure range')
 entries['exposure_dispatch']=exposure_dispatch
 dispatch=''
 for id in active_ids:
  maximum=[8,8,8,3,2 if universal_halation else 3,2,8,5,8,1,2,3,3][id-18]
  destination=color_slider if id==29 else exposure_dispatch if id==28 else sliders[maximum]
  dispatch+=f'cmp ip,#{id};beq {hex(destination)};'
 dispatch_stub=stub(dispatch+f'b {hex(sliders[8])}','slider dispatch')
 entries['setup']=stub(gate('r0','r4',0x531b075c)+f'mov ip,r0;mov r0,r4;sub sp,fp,#0x10;ldm sp,{{r4,fp,sp,lr}};b {hex(dispatch_stub)}','setup dispatch')
 entries['callback']=stub(gate('r5','r4',0x531b0e48)+f'sub r2,r5,#18;lsl r2,r2,#8;orr r2,r2,r6;mov r1,r4;mov r0,#2;bl {hex(control)};cmp r0,#0;bne 0x531b0c6c;sub sp,fp,#0x1c;ldm sp,{{r4,r5,r6,r7,fp,sp,pc}}','immediate callback')
 entries['reset']=stub('push {r4,lr};bl 0x532c282c;mov r1,r5;mov r0,#7;mov r2,#0;'+f'bl {hex(control)};pop {{r4,pc}}','preserve stock reset')
 return bytes(image),{'schema':'m10v-gr3-native-detail/v2','tables':table_address,'captions':captions,'entries':entries,'fields':[FIELDS[id-18] for id in active_ids],'ids':active_ids,'native_grain':native_grain,'universal_halation':universal_halation,'halation_modes':['off','spill','streak'] if universal_halation else None,'mode_caption':1137 if universal_halation else None,'appended_slots':appended_slots,'variant_rows':46 if appended_slots else 36,'variant_ids':detail_ids,'variant_tables':tables,'backend':'m10v_camera_library_detail','blocks':blocks,'slider8':sliders[8],'slider3':sliders[3],'sliders':sliders,'slider_dispatch':dispatch_stub,'table_symbol':'m10v_detail_tables','lifecycle':'stock immediate callback; cancel exits without rollback','row_icons':[484,473,398,478,0,0,0,0,0,0,648,648],'row_values':'numeric stock slider index; RED EI125/64/250','row_value_rect':[50,10,40,40],'red_value_rect':[50,10,60,40],'charmera_colors':{'names':['RED','YELLOW','BLUE','GRAY'],'value_icons':list(range(756 if sd_library else 750,760 if sd_library else 754)),'scale_icon':760 if sd_library else 754,'slider':color_slider},'camera_tested':False}
