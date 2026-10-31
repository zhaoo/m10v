"""Build actual BE blocking file boundary hooks with unchanged stock SP."""
import argparse,hashlib,importlib.util,json,shutil,struct,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('save_trace_builder',ROOT/'scripts/build_gr3_save_trace.py');save=importlib.util.module_from_spec(spec);spec.loader.exec_module(save)
ASM='''
.syntax unified
.arm
.fpu neon
.text
.global m10v_module_trace_pre
.type m10v_module_trace_pre,%function
m10v_module_trace_pre:
 push {r0-r12,lr}
 mrs r4,cpsr
 push {r4,r5}
 vmrs r4,fpscr
 push {r4,r5}
 vpush {d0-d15}
 vpush {d16-d31}
 sub sp,sp,#8
 mov r4,#0
 str r4,[sp]
 mov r2,r9
 mov r3,#204
 bl m10v_module_trace_mark
 add sp,sp,#8
 vpop {d16-d31}
 vpop {d0-d15}
 pop {r4,r5}
 vmsr fpscr,r4
 pop {r4,r5}
 msr cpsr_f,r4
 pop {r0-r12,lr}
 bx r9
.global m10v_module_trace_post
.type m10v_module_trace_post,%function
m10v_module_trace_post:
 push {r0-r12,lr}
 mrs r4,cpsr
 push {r4,r5}
 vmrs r4,fpscr
 push {r4,r5}
 vpush {d0-d15}
 vpush {d16-d31}
 sub sp,sp,#8
 str r0,[sp]
 mov r0,r8
 mov r1,r7
 mov r2,r9
 mov r3,#205
 bl m10v_module_trace_mark
 add sp,sp,#8
 vpop {d16-d31}
 vpop {d0-d15}
 pop {r4,r5}
 vmsr fpscr,r4
 pop {r4,r5}
 msr cpsr_f,r4
 pop {r0-r12,lr}
 ldr r7,[fp,#-0x34]
 b stock_continue
'''
SINK_ASM='''
.global m10v_module_trace_sink
.type m10v_module_trace_sink,%function
m10v_module_trace_sink:
 push {r0-r12,lr}
 mrs r4,cpsr
 push {r4,r5}
 vmrs r4,fpscr
 push {r4,r5}
 vpush {d0-d15}
 vpush {d16-d31}
 mov r0,r5
 mov r1,r9
 bl m10v_module_trace_finish
 vpop {d16-d31}
 vpop {d0-d15}
 pop {r4,r5}
 vmsr fpscr,r4
 pop {r4,r5}
 msr cpsr_f,r4
 pop {r0-r12,lr}
 ldr r0,[r5,#0x10]
 b stock_sink_continue
'''
def build(out,base,mark,rtos=None,take=None,batch=None,border_debug=False,pure_isp_debug=False):
 if type(pure_isp_debug)is not bool or (pure_isp_debug and take is None):raise ValueError('pure ISP diagnostics require safe sink')
 if (take is None)!=(batch is None):raise ValueError('store sink requires both take and batch')
 sink=take is not None
 out=Path(out);out.mkdir(parents=True,exist_ok=True)
 if base&3 or not 0x540b6000<=base<=0x54ff0000:raise ValueError('invalid code base')
 for address in [mark,*([take,batch] if sink else [])]:
  if address&3 or not 0x53000000<=address<0x55000000:raise ValueError('invalid function address')
 stock=Path(rtos or ROOT/'builds/gr3-extension-validation/official-rtos.bin').read_bytes()
 if hashlib.sha256(stock).hexdigest()!=save.SHA:raise ValueError('wrong locked RTOS')
 with tempfile.TemporaryDirectory() as temp:
  temp=Path(temp);asm=temp/'file.S';asm.write_text(ASM+(SINK_ASM if sink else ''));script=temp/'link.ld';script.write_text('SECTIONS { . = '+hex(base)+'; .text : { *(.text*) *(.rodata*) } /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) } }')
  objects=[]
  for source in [ROOT/'native/gr3/m10v_module_dispatch_trace.c',asm]:
   obj=temp/(source.stem+'.o');subprocess.run(['clang',*save.FLAGS,f'-DM10V_MODULE_SAFE_STORE_SINK={int(sink)}',f'-DM10V_DEBUG_MODE={int(sink)}',
    *(['-DM10V_PURE_ISP_EFFECTS=1','-DM10V_ISP_EFFECTS_SHOT_OFFSET=0x5778'] if pure_isp_debug else []),
    *(['-DM10V_BORDER_ENABLED=1'] if border_debug else []),'-c',str(source),'-o',str(obj)],check=True,capture_output=True);objects.append(obj)
   for name,row in save.sections(obj.read_bytes()):
    if row[2]&3==3 and row[5]:raise ValueError('writable section '+name)
  elfpath=out/'m10v_module_dispatch_trace.elf';defs={'m10v_save_trace_recipe_mark':mark,'stock_continue':0x53505d80}
  if sink:defs.update(m10v_save_trace_recipe_take=take,m10v_debug_batch=batch,stock_sink_continue=0x53505dc0)
  subprocess.run([shutil.which('ld.lld') or 'ld.lld','-m','armelf','-T',str(script),*[f'--defsym={k}={v}' for k,v in defs.items()],*map(str,objects),'-o',str(elfpath)],check=True,capture_output=True)
 elf=elfpath.read_bytes();rows=save.sections(elf);exports={};blob=None
 for name,row in rows:
  if row[2]&2 and row[5]:
   if name!='.text' or row[2]&1 or row[3]!=base:raise ValueError('unexpected section')
   blob=elf[row[4]:row[4]+row[5]]
  if row[1]==2:
   strings_row=rows[row[6]][1];strings=elf[strings_row[4]:strings_row[4]+strings_row[5]]
   for at in range(row[4],row[4]+row[5],16):
    ni,value,length,info,other,index=struct.unpack_from('<IIIBBH',elf,at);symbol=strings[ni:].split(b'\0',1)[0].decode()
    if symbol and index==0:raise ValueError('undefined '+symbol)
    if symbol.startswith('m10v_module_trace_') and info&15==2:exports[symbol]=value
 if blob is None:raise ValueError('no text')
 def bl(at,target):
  off=target-at-8
  if off&3 or not -(1<<25)<=off<(1<<25):raise ValueError('BL range')
  return struct.pack('<I',0xeb000000|((off>>2)&0xffffff))
 patches=[]
 def patch(at,expected,replacement,role):
  if stock[at-0x53000000:at-0x53000000+4]!=expected:raise ValueError('stock mismatch '+hex(at))
  patches.append(dict(address=at,expected_hex=expected.hex(),replacement_hex=replacement.hex(),role=role))
 patch(0x53505d78,bytes.fromhex('39ff2fe1'),bl(0x53505d78,exports['m10v_module_trace_pre']),'generic actual module handler begin')
 at=0x53505d7c;target=exports['m10v_module_trace_post'];off=target-at-8
 if off&3 or not -(1<<25)<=off<(1<<25):raise ValueError('B range')
 patch(at,bytes.fromhex('34701be5'),struct.pack('<I',0xea000000|((off>>2)&0xffffff)),'generic actual module handler return')
 if sink:
  at=0x53505dbc;off=exports['m10v_module_trace_sink']-at-8
  if off&3 or not -(1<<25)<=off<(1<<25):raise ValueError('B range')
  patch(at,bytes.fromhex('100095e5'),struct.pack('<I',0xea000000|((off>>2)&0xffffff)),'post StoreImageProcess safe caller sink')
 manifest=dict(schema=1,base=base,bytes=len(blob),sha256=hashlib.sha256(blob).hexdigest(),required_rtos_sha256=save.SHA,exports=exports,patches=patches,mutable_global_bytes=0,camera_tested=False,border_debug=border_debug,callback_filesystem_calls=0,probe_filesystem_calls=0,sink_filesystem_calls='existing debug batch only' if sink else 0,module_direct_allocation_calls=0,stock_handler_sp='unchanged',event_schema={'204':['recipe','kind','actual_handler_or_border_dimensions','module'],'205':['recipe','kind','actual_handler_or_border_dimensions','result']},owner_topology={'message':'recipe+0x3b0+24*kind','message_plus_12':'recipe+0x5f0+32*kind','metadata_plus_20':'recipe'},kind_range=[0,23],final_recipe_drain_proven=False,post_store_drain_attempted=sink,store_sink_enabled=sink,store_handler=0x5350c764,store_opcodes={'0x01000001':'main save5350bfb0','0x01000002':'alternate save5350b2fc'},sink_contract='Common generic receiver after handler return and refcounter mutex release, before recipe owner callback; StoreImageProcess only' if sink else None,limitations=['Uses existing bounded recipe trace; contention/full rings drop observations.','Post-JPEG records may be retired before an existing safe sink drains them.','A handler return is not media durability or directory visibility.','Local reference-counter mutex release is proven; absence of every transitive global filesystem lock is not proven.','Known JPEG handler535047d4 is physically observed, but this generic dispatch patch itself is not yet camera-tested.'])
 if pure_isp_debug:
  manifest['pure_isp_debug']=True
  manifest['sink_contract']+='; active pure ISP shots also drain kinds19/4/12/10/11/5 at this same post-return boundary'
 (out/'m10v_module_dispatch_trace.bin').write_bytes(blob);(out/'patch-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');return blob,manifest
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--base',type=lambda x:int(x,0),required=True);p.add_argument('--mark',type=lambda x:int(x,0),required=True);p.add_argument('--take',type=lambda x:int(x,0));p.add_argument('--batch',type=lambda x:int(x,0));a=p.parse_args();_,manifest=build(a.output,a.base,a.mark,take=a.take,batch=a.batch);print(json.dumps(manifest,indent=2))
