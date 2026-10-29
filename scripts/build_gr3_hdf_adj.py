"""Exact GR III 2.10 independent ADJ extension (IIIx uses verified port).

All19 materialized table readers and all15 list consumers are relocated.
The original20 records are copied byte-for-byte; no original function ID is
repurposed. Native settings persist ID20 without changing their record ABI.
"""
import hashlib,struct
from scripts.build_gr3_menu_patches import assembly,branch,movw
from scripts.build_gr3_digital_hdf import SHA,official_rtos
TABLE=0x53b39a14
READERS=((0x5319fff8,0x531a002c),(0x531a1e3c,0x531a1e40),
 (0x531a2a48,0x531a2a50),(0x531a2ac0,0x531a2ac8),(0x531a2c6c,0x531a2c74),
 (0x531a3128,0x531a3130),(0x531a31c4,0x531a31cc),(0x531a3c24,0x531a3c2c),
 (0x531a3c9c,0x531a3ca4),(0x531a3dcc,0x531a3dd4),(0x531a3ee0,0x531a3ee8),
 (0x531a4080,0x531a4088),(0x531a4234,0x531a4238),(0x531a4488,0x531a4494),
 (0x531a458c,0x531a4594),(0x531a468c,0x531a4694),(0x531a46f4,0x531a4704),
 (0x531a47b0,0x531a47c0),(0x531a487c,0x531a4884))
LISTS=(0x53b4eba0,0x53b5a430,0x53b5a404,0x53b58fb0,0x53b5a4b4)
# draw, setter, is-current; original functions retain all their native calls.
LIST_READERS=tuple(((0x531b55a4+i*0x5c,0x531b55ac+i*0x5c),
 (0x531b71cc+i*0x30,0x531b71d0+i*0x30),
 (0x531b895c+i*0x34,0x531b8960+i*0x34)) for i in range(5))
ORIGINAL_LIST=bytes((0,1,2,3,4,16,5,6,7,8,9,18,19,10,11,12,13,17,14))

def build(base,symbols,rtos=None,icon_id=874,parent_event=None):
 rom=bytes(rtos) if rtos is not None else official_rtos()
 if hashlib.sha256(rom).hexdigest()!=SHA:raise ValueError('HDF ADJ requires exact official GR III RTOS')
 image=bytearray();patches=[]
 def word(a):return struct.unpack_from('<I',rom,a-0x53000000)[0]
 def data(raw):
  image.extend(bytes(-len(image)&3));a=base+len(image);image.extend(raw);return a
 def stub(text):return data(assembly(text,base+len(image)))
 def patch(a,new,name,expected=None):
  old=word(a)
  if expected is not None and old!=expected:raise ValueError('HDF ADJ preimage differs: '+hex(a))
  patches.append(dict(address=a,expected=old,replacement=new,name='HDF ADJ '+name))
 def relocate(lo,hi,old,new):
  reg=(word(lo)>>12)&15
  patch(lo,movw(reg,new&65535),'table/list pointer low',movw(reg,old&65535))
  patch(hi,movw(reg,new>>16,True),'table/list pointer high',movw(reg,old>>16,True))
 handlers={n:symbols['m10v_hdf_adj_'+n] for n in ('enter','draw','current','set','count','available','event')}
 record=[0]*17
 for off,name in ((0,'enter'),(0x18,'draw'),(0x20,'current'),(0x28,'set'),(0x30,'count'),(0x3c,'available')):record[off//4]=handlers[name]
 table=data(rom[TABLE-0x53000000:TABLE-0x53000000+0x550]+struct.pack('<17I',*record))
 for lo,hi in READERS:relocate(lo,hi,TABLE,table)
 length=stub('add r6,r4,#0x550;add r6,r6,#0x44;b 0x531a1e58')
 patch(0x531a1e54,branch(0x531a1e54,length),'constructor21-record walk',0xe2846e55)
 lists=[]
 for i,old in enumerate(LISTS):
  if rom[old-0x53000000:old-0x53000000+19]!=ORIGINAL_LIST:raise ValueError('HDF ADJ assignment list differs')
  new=data(ORIGINAL_LIST+bytes([20]));lists.append(dict(original=old,address=new,count=20))
  for lo,hi in LIST_READERS[i]:relocate(lo,hi,old,new)
  patch(0x531b3bac+i*8,0xe3a00014,'assignment list count',0xe3a00013)
  at=0x53246340+i*12;off=0x918+i*2
  getter=stub(f'ldrb r0,[r3,#{off}];cmp r0,#20;movhi r0,#0;bx lr')
  patch(at,branch(at,getter),'bounded persisted slot getter',0xe5d30000|off)
 # Extend tails, preserving the exact case19 and unknown-ID default.
 name=stub('cmp r1,#20;movweq r0,#970;bxeq lr;cmp r1,#19;movne r0,#0;moveq r0,#0x49;bx lr')
 patch(0x532928b0,branch(0x532928b0,name),'independent name',0xe3510013)
 icon=stub(f'cmp r1,#20;movweq r0,#{icon_id};bxeq lr;sub r0,r1,#19;clz r0,r0;lsr r0,r0,#5;bx lr')
 patch(0x53293ad0,branch(0x53293ad0,icon),'independent icon',0xe2410013)
 # Event hook is composed with existing A/B; root removes its superseded
 # address entry so there is exactly one preimage-checked branch per site.
 patch(0x531a4db8,branch(0x531a4db8,handlers['event']),'event controller',0xe1d130b0)
 image.extend(bytes(-len(image)&3))
 return bytes(image),dict(schema='m10v-gr3-hdf-adj/v1',base=base,bytes=len(image),patches=patches,
  function_id=20,record_count=21,record_bytes=0x44,table=table,table_readers=READERS,
  original_table=TABLE,original_table_bytes=0x550,lists=lists,handlers=handlers,
  resource_ids=[970,972,973,974,975,976],icon_id=icon_id,
  parent_event=parent_event,required_rtos_sha256=SHA,camera_tested=False,
  slot_offsets=[0x918+2*i for i in range(5)],
  persistence={'storage':'native settings bytes, unchanged whole-record ABI','valid_ids':[0,20],
   'invalid_id':'getter returns stock Off without changing the stored record',
   'u_recall':'native53270ba4..53270be8 copy five slot bytes unchanged',
   'restoration':'Before installing firmware without this extension, assign all five ADJ slots to stock options in every saved U profile and save; stock firmware does not support ID20.'},
  cache={'owner':'TopMenu HDF page','offset':0x190,'bytes':20,'page_bytes':0x1c0,'capture_filesystem_calls':0})
