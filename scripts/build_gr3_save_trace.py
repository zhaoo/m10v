"""Build SHA-locked recipe-owned diagnostics and installable callsite patches."""
import argparse,hashlib,json,shutil,struct,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SHA='8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67'
FLAGS=['--target=armv7-none-eabi','-mcpu=cortex-a9','-marm','-mfloat-abi=soft','-Os','-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-Wall','-Wextra','-Werror']
def sections(elf):
 if elf[:7]!=b'\x7fELF\x01\x01\x01' or struct.unpack_from('<H',elf,18)[0]!=40:raise ValueError('expected ARM ELF32')
 at=struct.unpack_from('<I',elf,32)[0];size,n,ni=struct.unpack_from('<HHH',elf,46)
 if size!=40:raise ValueError('wrong section size')
 rows=[struct.unpack_from('<10I',elf,at+i*size) for i in range(n)]
 r=rows[ni];names=elf[r[4]:r[4]+r[5]]
 return [(names[r[0]:].split(b'\0',1)[0].decode(),r) for r in rows]
def lifecycle_patches(stock,exports):
 if hashlib.sha256(stock).hexdigest()!=SHA:raise ValueError('wrong locked RTOS')
 def bl(at,target):
  offset=target-at-8
  if offset&3 or not -(1<<25)<=offset<(1<<25):raise ValueError('BL range')
  return struct.pack('<I',0xeb000000|((offset>>2)&0xffffff))
 patches=[]
 def call(at,original,symbol):
  expected=bl(at,original)
  if stock[at-0x53000000:at-0x53000000+4]!=expected:raise ValueError('stock call mismatch '+hex(at))
  patches.append(dict(address=at,expected_hex=expected.hex(),replacement_hex=bl(at,exports[symbol]).hex(),symbol=symbol,kind='aapcs-bl'))
 call(0x53523e0c,0x5351091c,'m10v_save_trace_recipe_alloc')
 for at in [0x535153ec,0x53516e14,0x53516ebc,0x5351897c,0x5351af20,0x5351feb4]:call(at,0x535216d0,'m10v_save_trace_recipe_allocate')
 for at in [0x5351703c,0x535170cc,0x535182f8,0x5351f3a8,0x5351fd50]:call(at,0x53521d14,'m10v_save_trace_recipe_release')
 at=0x53d0fd00;expected=struct.pack('<I',0x5350d7e8)
 if stock[at-0x53000000:at-0x53000000+4]!=expected:raise ValueError('stock setter mismatch')
 patches.append(dict(address=at,expected_hex=expected.hex(),replacement_hex=struct.pack('<I',exports['m10v_save_trace_recipe_set']).hex(),symbol='m10v_save_trace_recipe_set',kind='virtual-aapcs'))
 return patches

def build(out,base=0x540e0000,rtos=None,border_debug=False):
 if type(base)!=int or base&3 or not 0x540b6000<=base<=0x54ff0000:raise ValueError('invalid appendRX base')
 out=Path(out);out.mkdir(parents=True,exist_ok=True)
 obj=out/'m10v_save_trace.o';elfpath=out/'m10v_save_trace.elf'
 objects=[]
 for source in ['m10v_save_trace.c','m10v_capture_raw_lifetime.c']:
  obj=out/(Path(source).stem+'.o');subprocess.run(['clang',*[('-Oz' if flag=='-Os' else flag) for flag in FLAGS],
   *(['-DM10V_BORDER_ENABLED=1','-DM10V_DEBUG_MODE=1'] if border_debug else []),
   '-c',str(ROOT/'native/gr3'/source),'-o',str(obj)],check=True,capture_output=True);objects.append(obj)
 # Object must have no writable allocated data, even a four-byte pointer.
 for obj in objects:
  for name,r in sections(obj.read_bytes()):
   if r[2]&2 and r[2]&1 and r[5]:raise ValueError('mutable allocated section: '+name)
 with tempfile.TemporaryDirectory(prefix='m10v-save-link-') as d:
  linker=Path(d)/'save.ld';linker.write_text('SECTIONS { . = '+hex(base)+'; .text : { *(.text*) *(.rodata*) } /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) } }')
  # Vtable comes after module, with a conservative one-page code budget.
  vt=base+0x1000
  subprocess.run([shutil.which('ld.lld') or 'ld.lld','-m','armelf','-T',str(linker),'--defsym=m10v_save_trace_vtable='+hex(vt),*map(str,objects),'-o',str(elfpath)],check=True,capture_output=True)
 elf=elfpath.read_bytes();rows=sections(elf);exports={};undefined=[];blob=None
 for name,r in rows:
  if r[2]&2 and r[5]:
   if r[2]&1 or name!='.text' or r[3]!=base or r[5]>0x1000:raise ValueError('unexpected linked allocation: '+name)
   blob=elf[r[4]:r[4]+r[5]]
  if r[1]==2:
   sr=rows[r[6]][1];strings=elf[sr[4]:sr[4]+sr[5]]
   for pos in range(r[4],r[4]+r[5],16):
    ni,val,length,info,other,index=struct.unpack_from('<IIIBBH',elf,pos)
    symbol=strings[ni:].split(b'\0',1)[0].decode()
    if symbol and not index:undefined.append(symbol)
    if symbol.startswith('m10v_save_trace_') and info&15==2:exports[symbol]=val
 if blob is None or undefined:raise ValueError('incomplete linked module')
 blob+=bytes(0x1000-len(blob))+struct.pack('<III',0x534ecc2c,0x534ecc54,exports['m10v_save_trace_callback'])
 manifest=dict(schema=1,base=base,bytes=len(blob),sha256=hashlib.sha256(blob).hexdigest(),exports=exports,vtable=vt,undefined_symbols=undefined,mutable_global_bytes=0,camera_tested=False,automatic_hook_installation=False,patches=[],required_rtos_sha256=SHA,border_debug=border_debug,storage=dict(owner='explicit caller-owned RAM; stack proxy alive through stock synchronous wait',bytes=176,records=8,filesystem_calls=0,allocator_calls=0),integration_blockers=['No proven persistent owner propagated through RAW and save tasks; no global lifecycle hooks installed.','No proved filesystem-unlocked worker flush boundary; module never calls debug_batch.','Bridge has explicit four-argument ABI; do not patch stock two-argument BL directly.'],stock_contract=dict(bridge=0x534ecb3c,callback=0x534ec9b8,vptr=0x53c5ed78,result_offset=0x10,event_offset=4,known_status={'0':'success byte 1','1,2':'success byte 0','greater_than_2':'stock preserves previous byte; not a named error'}),abi_contract={'callee_saved':'r4-r11 and sp preserved, tested against original bridge','flags':'AAPCS NZCV are caller-clobbered; no arbitrary instruction-site hook permitted','proxy_bytes':32,'stock_event_lifetime':'original event owner remains alive through synchronous call; duplicate handle is not destroyed'},event_schema={180:['object','image_info','task_identity','initial_result_byte'],181:['object','opcode','payload_status','task_identity'],182:['object','returned_result','task_identity','final_result_byte'],183:['recipe','buffer_id','new_backing','caller_pc'],184:['recipe','buffer_id','requested_bytes','allocator_result'],185:['source_recipe','target_recipe','backing','source'],186:['recipe','buffer_id','backing','caller_pc']})
 stock=Path(rtos or ROOT/'builds/gr3-extension-validation/official-rtos.bin').read_bytes()
 manifest.update(schema=2,automatic_hook_installation=True,patches=lifecycle_patches(stock,exports),
  storage=dict(owner='extended locked BEStillRecipe factory allocation',recipe_bytes=0x4778,trace_offset=0x4778,bytes=656,records=32,color_offset=0x4a08,color_bytes=1796,extended_recipe_bytes=0x5150,stamp_offset=0x5140,stamp_bytes=16,raw_token_offset=0x5110,raw_token_bytes=48,filesystem_calls=0),
  integration_blockers=['Caller must install all checked patches and drain recipe trace at an independently proved filesystem-safe boundary.','Save bridge remains explicit call-owned ABI; RAW recipe to file-write object association is not proven.'],
  lifecycle_contract=dict(factory_call=0x53523e0c,allocator=0x5351091c,deallocator=0x5351098c,allocation_failure='return exact original null; no fallback',transfer='RAW_BEFORE plus RAW_SET preserve old/new backing and original setter LR; target matching by backing',release='original stock free and setter execute unchanged',threading='bounded try-lock only; no filesystem or blocking calls in hooks',overflow='25 ordinary records plus 6 priority phase records 190..198; final record199 reports dropped count at drain',abi='only AAPCS BL callsites and vtable entry; r4-r11/sp preserved; flags caller-clobbered'))
 (out/'m10v_save_trace.bin').write_bytes(blob);(out/'patch-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 return blob,manifest
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',default='builds/gr3-isp-research/save-trace');p.add_argument('--base',type=lambda v:int(v,0),default=0x540e0000);args=p.parse_args();blob,m=build(args.output,args.base);print(json.dumps({'bytes':len(blob),'exports':m['exports'],'patches':m['patches'],'integration_blockers':m['integration_blockers']},indent=2))
