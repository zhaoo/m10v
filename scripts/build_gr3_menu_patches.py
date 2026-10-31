"""Exact GR III 2.10 dedicated menu extension; rejects any changed preimage.

Uses stock menu list, caption lookup, slider lifecycle and callback machinery.
No stock parameter IDs, strings or persisted record prefix are repurposed.
"""
import hashlib,struct,subprocess,tempfile
from pathlib import Path
from scripts.build_gr3_halation import ROOT,FLAGS,extract_text
from scripts.build_gr3_menu_controls import build_menu_controls,MENU_ADDRESS
BASE=0x53000000
START=MENU_ADDRESS
END=0x540c2000
DIGEST='8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67'

def branch(a,b,link=False,condition=14):
 d=b-a-8
 if d&3 or not -(1<<25)<=d<(1<<25):raise ValueError('ARM branch out of range')
 return (condition<<28)|0x0a000000|(int(link)<<24)|((d>>2)&0xffffff)
def movw(reg,value,top=False):return (0xe3400000 if top else 0xe3000000)|((value&0xf000)<<4)|(reg<<12)|(value&0xfff)
def load(reg,address):return [movw(reg,address&65535),movw(reg,address>>16,True)]
def assembly(text,address):
 # Resolve numeric external branches explicitly; local labels stay assembler-owned.
 statements=[x.strip() for x in text.split(';') if x.strip()];cursor=address;out=[]
 cond={'b':14,'bl':14,'beq':0,'bne':1,'bhi':8,'bls':9,'blo':3,'bhs':2}
 for line in statements:
  parts=line.split()
  if len(parts)==2 and parts[0] in cond and parts[1].startswith('0x'):
   line='.word '+hex(branch(cursor,int(parts[1],16),parts[0]=='bl',cond[parts[0]]))
  out.append(line)
  if not line.endswith(':'):cursor+=4
 with tempfile.TemporaryDirectory(prefix='m10v-menu-asm-') as d:
  src=Path(d)/'stub.S';obj=Path(d)/'stub.o'
  src.write_text('.syntax unified\n.arm\n.text\n.global m10v_halation\nm10v_halation:\n'+'\n'.join(out)+'\n')
  r=subprocess.run(['clang',*FLAGS,'-c',str(src),'-o',str(obj)],capture_output=True,text=True)
  if r.returncode:raise ValueError(r.stderr)
  raw=extract_text(obj.read_bytes())
  from scripts.gr3_target_relocations import relocations,firmware_address
  # Explicit .word firmware pointers are data; generated branch .words remain
  # instructions. Pixel resources never pass through this assembler emitter.
  start=address;code=bytearray()
  for line in out:
   if line.endswith(':'):continue
   at=start+len(code)
   parts=line.split()
   pointer=parts[0]=='.word' and firmware_address(int(parts[1],0))
   if pointer:
    relocations.code(start,code);relocations.data(at,raw[at-address:at-address+4]);start=at+4;code=bytearray()
   else:code+=raw[at-address:at-address+4]
  relocations.code(start,code)
  return raw

def build_menu_patches(rtos):
 if hashlib.sha256(rtos).hexdigest()!=DIGEST:raise ValueError('menu requires exact original RTOS')
 tail=bytearray(END-START);patches=[];blocks=[]
 def put(a,data,label):
  if a<START or a+len(data)>END or any(a<e and s<a+len(data) for s,e,_ in blocks):raise ValueError('menu extension overlaps: '+label)
  tail[a-START:a-START+len(data)]=data;blocks.append((a,a+len(data),label));return a
 def patch(a,data,label):
  if any(a<p['address']+len(bytes.fromhex(p['replacement'])) and p['address']<a+len(data) for p in patches):raise ValueError('duplicate menu patch')
  patches.append(dict(address=a,expected=rtos[a-BASE:a-BASE+len(data)].hex(),replacement=data.hex(),label=label))
 def pword(a,w,label):patch(a,struct.pack('<I',w),label)
 def stub(a,s,label):return put(a,assembly(s,a),label)
 put(START,build_menu_controls(),'independent controls backend')
 # Clone all original lists, only kind8 adds four shooting-only (visibility0) IDs.
 data_cursor=0x540c0000
 def data(raw,label):
  nonlocal data_cursor
  data_cursor=(data_cursor+3)&~3;a=data_cursor;data_cursor+=len(raw);return put(a,raw,label)
 table=bytearray(rtos[0xb3488c:0xb3488c+288])
 for s in range(3):
  index=(s*12+8)*8;p,n=struct.unpack_from('<II',table,index)
  copied=rtos[p-BASE:p-BASE+n*2]+bytes(sum(([0,i] for i in range(18,22)),[]))
  new=data(copied,'800T menu list '+str(s));struct.pack_into('<II',table,index,new,n+4)
 table_address=data(table,'parameter tables')
 for lo,hi,reg in [(0x531afa20,0x531afa24,12),(0x531afabc,0x531afacc,3),(0x531affa0,0x531affa8,12),(0x531b01f4,0x531b01f8,3)]:
  pword(lo,movw(reg,table_address&65535),'parameter table low');pword(hi,movw(reg,table_address>>16,True),'parameter table high')
 captions=data(rtos[0xb34bd8:0xb34bd8+72]+b''.join(struct.pack('<HH',0x312+i,0x312+i) for i in range(4)),'caption pairs')
 pword(0x531b0248,movw(3,captions&65535),'caption table low');pword(0x531b024c,movw(3,captions>>16,True),'caption table high')
 # ASCII captions remain readable in every stock font. Chinese is enabled only
 # after verifying the shipped glyph index, never by guessing glyph coverage.
 names=['Halation Gain','Halation Spread','Highlight Gate','Halation Mode']
 desc=[]
 for name in names:
  txt=data((name+'\0').encode('utf-16le'),'caption '+name)
  desc.append(data(struct.pack('<II',((len(name)+1)&255)|0x100,txt),'descriptor '+name))
 labels=data(struct.pack('<4I',*desc),'caption descriptor lookup')
 cn=[]
 for name in ['红晕强度','扩散范围','高光阈值','红晕档位']:
  txt=data((name+'\0').encode('utf-16le'),'简体 '+name)
  cn.append(data(struct.pack('<II',len(name)+1|0x100,txt),'简体descriptor '+name))
 chinese_labels=data(struct.pack('<4I',*cn),'简体caption lookup')
 def addr(reg,value):return f'movw {reg},#{value&65535};movt {reg},#{value>>16};'
 def localized():return addr('r3',labels)+f'cmp r0,#19;movweq r3,#{chinese_labels&65535};movteq r3,#{chinese_labels>>16};'
 # Preserve original invalid-ID/language handling and every original lookup.
 stub(0x540bf000,f'cmp r0,#20;bhi fallback;movw ip,#0x312;sub ip,r7,ip;cmp ip,#3;bhi stock;'+localized()+'ldr r7,[r3,ip,lsl #2];sub r8,fp,#0xb0;mov r0,r8;b 0x53396700;stock:;cmp r0,#20;cmpls r7,r3;bhi fallback;b 0x533966e8;fallback:;b 0x53396850','caption getter A')
 # r3 must hold original311 in stock fallback (custom calculation uses only ip).
 stub(0x540bf080,f'cmp r0,#20;bhi fallback;movw ip,#0x312;sub ip,r7,ip;cmp ip,#3;bhi stock;'+localized()+'ldr r3,[r3,ip,lsl #2];b 0x5339710c;stock:;cmp r7,r3;cmpls r0,#20;bhi fallback;b 0x533970fc;fallback:;b 0x533971e0','caption getter B')
 pword(0x533966e4,branch(0x533966e4,0x540bf000),'caption getter A dispatch');pword(0x533970f8,branch(0x533970f8,0x540bf080),'caption getter B dispatch')
 # For unknown IDs the exact original assert/default remains reachable.
 def gate(idreg,model,fallback):return f'sub ip,{idreg},#18;cmp ip,#3;bhi {hex(fallback)};ldrb ip,[{model},#0x19a];cmp ip,#8;bne {hex(fallback)};ldrb ip,[{model},#0x19d];cmp ip,#0;bne {hex(fallback)};'
 stub(0x540bf100,gate('r3','r5',0x531b01ac)+'sub r2,r3,#18;lsl r2,r2,#16;orr r2,r2,r4;mov r1,r5;mov r0,#3;bl 0x540be000;b 0x531b0064','custom row render')
 stub(0x540bf180,gate('r4','r5',0x531b0594)+'sub r2,r4,#18;mov r1,r5;mov r0,#1;bl 0x540be000;mov r4,r0;b 0x531b045c','custom row current value')
 stub(0x540bf200,gate('r0','r4',0x531b075c)+'cmp r0,#21;mov r0,r4;sub sp,fp,#0x10;ldm sp,{r4,fp,sp,lr};blo 0x540bf700;b 0x540bf900','custom slider setup')
 stub(0x540bf280,gate('r5','r4',0x531b0e48)+'sub r2,r5,#18;lsl r2,r2,#8;orr r2,r2,r6;mov r1,r4;mov r0,#2;bl 0x540be000;b 0x531b0c6c','custom slider callback')
 for a,d in [(0x531b000c,0x540bf100),(0x531b03f8,0x540bf180),(0x531b05e4,0x540bf200),(0x531b0bf4,0x540bf280)]:pword(a,branch(a,d),'extend original dispatcher')
 stub(0x540bf300,'mov r1,r0;mov r0,#4;mov r2,#0;b 0x540be000','factory default shim')
 # Stock allocator virtual ABI preserved, only current-record tail zeroed.
 alloc=stub(0x540bf340,'push {r4,lr};blx ip;cmp r0,#0;beq done;movw r1,#0xb28;add r1,r0,r1;mov r2,#0;mov r3,#8;zero:;str r2,[r1],#4;subs r3,r3,#1;bne zero;done:;pop {r4,pc}','extended allocation initializer')
 for size,call in [(0x5324b338,0x5324b34c),(0x5324b4a4,0x5324b4b4),(0x5324b5b8,0x5324b5c8),(0x5324b6e0,0x5324b6e8)]:
  pword(size,movw(1,0xb48),'current record allocation size');pword(call,branch(call,alloc,True),'initialize private tail')
 stub(0x540bf3a0,'push {r4,lr};bl 0x532c282c;ldrb r2,[r5,#0x19b];cmp r2,#0;bne done;mov r1,r5;mov r0,#7;bl 0x540be000;done:;pop {r4,pc}','reset selected independent settings')
 pword(0x531acd24,branch(0x531acd24,0x540bf3a0,True),'preserve stock reset and reset independent set')
 # Reuse genuine native slider ownership. Relocate all B/BL, internal targets,
 # and insert a null allocation guard before stock delegate construction.
 def clone(destination,maximum):
  original=0x531acfec;stop=0x531ad12c
  mapping={a:destination+(a-original)+(8 if a>=0x531ad0b4 else 0) for a in range(original,stop+4,4)}
  output=bytearray()
  for a in range(original,stop,4):
   at=mapping[a]
   if a==0x531ad0b4:output+=struct.pack('<II',0xe3500000,branch(at-4,mapping[0x531ad110],condition=0))
   w=struct.unpack_from('<I',rtos,a-BASE)[0]
   if (w&0x0e000000)==0x0a000000:
    displacement=(w&0xffffff)<<2
    if displacement&(1<<25):displacement-=1<<26
    target=a+8+displacement
    w=branch(at,mapping.get(target,target),bool(w&0x1000000),w>>28)
   if a==0x531ad01c:w=0xe1a00006 # r0=model
   if a==0x531ad020:w=branch(at,0x540bf300,True)
   if a==0x531ad024:w=0xe1a00000 # own default already UI index
   if a==0x531ad060:w=0xe3a02000|maximum
   output+=struct.pack('<I',w)
  put(destination,output,'native slider clone '+str(maximum))
 clone(0x540bf700,8);clone(0x540bf900,3)
 return bytes(tail),patches,{'schema':'m10v-gr3-independent-menu/v1','tables':{'items':table_address,'captions':captions,'labels':labels},'blocks':blocks,'fields':names,'privateRecordBytes':32,'settingsFile':'C:\\M10V8CFG.BIN','cameraTested':False}
