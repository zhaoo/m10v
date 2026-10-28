#!/usr/bin/env python3
"""Build an opt-in internal GR III/IIIx guard component and exact native hook plan.

Returns code plus preimage-checked patches; never writes camera firmware. The
central builder/Node export remain unchanged. Open ownership contracts stay
explicit in the manifest, so this artifact does not authorize activation.
"""
import argparse,hashlib,json,re,shutil,struct,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
RTOS_BASE=0x53000000
RTOS_SHA256='8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67'
MODELS={'gr3':{'version':'2.10','rtos_sha256':RTOS_SHA256},
 'gr3x':{'version':'1.60','rtos_sha256':'0f11b0d28bc67932d044c5d01bc0314844a756057c89984278c73a23449a24c6'}}
FLAGS=['--target=armv7-none-eabi','-mcpu=cortex-a9','-marm','-mfloat-abi=soft',
 '-O2','-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-unwind-tables',
 '-fno-asynchronous-unwind-tables','-Wall','-Wextra','-Werror']

# Whole touched ABI/control spans are byte-identical in both independently
# pinned originals. These range fingerprints are locked from GR III 2.10.
ABI_SPANS=(
 ('public_resize_copy_fill',0x534ab6b8,0x534abf00,'65e4a8db3071a86d09dbac4bdb163e79915d33408d0c124a054e7b81fc8e331b'),
 ('native_client',0x534aab0c,0x534aad0c,'29632dde15214bf4aa96768fb4139e1b3867c486240decf3c971dada42bf839d'),
 ('common_client_wait',0x534aad6c,0x534aae9c,'2126949562f5b056980081f50c086f415a3e75b1f790d87044d30ec0f0b65d4d'),
 ('native_client_destructors',0x534ac164,0x534ac1bc,'41af1592074b8fec3dd8e4b69242f67693a02a8715eb1a04d676a11c2268d579'),
 ('transfer_factory_and_constructor',0x53699e7c,0x5369a328,'3c7ffa18edb4842d0b810e6c89f4e58a794fb601e83dc4b310c4e80ca6bb27c5'),
 ('transfer_worker_and_dispatch',0x5369a40c,0x5369ad08,'942785c7bcf2704fbd8f714180dcfa46772b3305e196668dc8d43276c3512bb6'),
 ('fill_factory_and_constructor',0x53658988,0x53658cfc,'bfa6d1570a4a4cdb56016cc275ccd406b121060623c515073fdfd32dcb1ee659'),
 ('fill_body',0x5365900c,0x5365929c,'89d35795062f85ebfdf2ecb200a91048f967371fce2f31104be504b41b5036c3'),
 ('fill_dispatch',0x5365935c,0x53659530,'4fd582624c9eaa5982983ef3861dd65506e9e4582bfc72f6a34a77ab922ba28e'),
 ('resize_factory',0x536729ec,0x53672c48,'f150242d8fab4fa6c2bd8c39261ccc3b1e45c7d014da0e0ff93b028ab7333687'),
 ('resize_constructor',0x53672e10,0x53672e84,'965aa5b9b38d15af6026eb0376305ebf47432330516da8c4fdb3334b837742e4'),
 ('resize_body',0x53673098,0x5367357c,'34146ce39c24248eb243b642e671ff2efba8866280a4aae5a587317e9a1bd5d0'),
 ('resize_dispatch',0x53673f48,0x53674090,'beafddbfd64b5ec58be7a2b8a274fbc36f3ca475a03fad39efdec41bfcf2e6c1'),
 ('fill_iip_lower',0x53769a78,0x5376a3b8,'4b9de45135a7d9d2aa0f9136b9ffe1e161c9ae47b85ad6f44c2b3c979784f224'),
 ('resize_iip_lower',0x53770bf0,0x53771bc0,'26168b7bdaf72dad9a32d7a501bc8bd84120293d1e3089d9c6a0827aa24d2a54'),
 ('iip_service_control',0x5376cd48,0x5376f1b0,'ebfb4eff84b42b71100ee486a60b17b9581d79946ee252e5ffc59c55312b95ec'),
 ('iip_driver_conditions',0x53778458,0x537784a4,'cf1ea8f09720cae0295e68f19043c9d30f2a4b77d8a93b49a2416d8e35e12778'),
 ('native_mutex_wrappers',0x536a848c,0x536a85e0,'7cfa9f3b9173976a38c93fea58140139538961283100dbebe001f19436f53cdb'),
 ('native_lock_wrappers',0x536ae71c,0x536ae974,'05f67f1fc8802ebf2eb0cbe953747fb723b04e2d1f5d96e6a2f1c66cb5234e1d'),
 ('native_event_wrappers',0x536a9d1c,0x536a9fac,'156d6a87aae9b50e2aca343014ed732850c9988f15f7d07dffc7608ea1f0956d'),
 ('native_yield',0x536b0a74,0x536b0af4,'1f46c2d8080d43063d82b6434e9497da386330920ead349a33935450a1135afb'),
)
# Factory allocation and ctor edits are indivisible: no running stock-size
# singleton may receive a tail-aware hook. Only named worker shapes grow.
HOOKS=(
 (0x5369a010,0xe3a00044,0xe3a00058,'first_transfer_allocation'),
 (0x5369a01c,0xeb0000a7,'m10v_border_transfer_construct','first_transfer_constructor'),
 (0x5369ac4c,0xebffff3d,'border_recovery_transfer_body_hook','transfer_body'),
 (0x5369a478,0xeb003e83,'border_recovery_transfer_wait_hook','transfer_wait'),
 (0x534aae28,0xeb07fc17,'m10v_border_client_wait','owned_outer_client_wait'),
 (0x536589fc,0xe3a00058,0xe3a00068,'fill_allocation'),
 (0x53658a08,0xeb00009a,'m10v_border_fill_construct','fill_constructor'),
 (0x536594a0,0xebfffed9,'border_recovery_fill_body_hook','fill_body'),
 (0x5376a370,0xebfcfec5,'border_recovery_fill_wait_hook','fill_wait'),
 (0x53672bac,0xe3a00048,0xe3a00058,'resize_allocation'),
 (0x53672bb8,0xeb000094,'m10v_border_resize_construct','resize_constructor'),
 (0x53674014,0xebfffc1f,'border_recovery_resize_body_hook','resize_body'),
 (0x5377160c,0xebfce21e,'border_recovery_resize_wait_hook','resize_iip_wait'),
 (0x53673244,0xeb00db10,'border_recovery_resize_dma_wait_hook','resize_dma_wait0'),
 (0x5367331c,0xeb00dada,'border_recovery_resize_dma_wait_hook','resize_dma_wait1'),
 (0x53673384,0xeb00dac0,'border_recovery_resize_dma_wait_hook','resize_dma_wait2'),
 (0x5376a38c,0xeb001278,'border_recovery_fill_release_hook','fill_pre_release'),
 (0x53771968,0xebfff501,'border_recovery_resize_release_hook','resize_pre_release'),
)
SOURCES=('native/gr3/m10v_border_wait_guard.c','native/gr3/m10v_border_wait_guard.h',
 'scripts/border_recovery_wait_guard.S','scripts/border_recovery_wait_guard_contract.json',
 'scripts/build_gr3_border_wait_guard.py','native/gr3/m10v_border_fill_bundle.h')
def digest(data):return hashlib.sha256(data).hexdigest()
def arm_bl(at,target):
 delta=target-at-8
 if (at|target)&3 or not -(1<<25)<=delta<(1<<25):raise ValueError('guard ARM BL out of range')
 return 0xeb000000|((delta>>2)&0xffffff)
def _compile(base):
 compiler,linker=shutil.which('clang'),shutil.which('ld.lld')
 if not compiler or not linker:raise RuntimeError('clang and ld.lld required for internal guard component')
 expected=set(re.findall(r'\b(m10v_border_\w+)\s*\(', (ROOT/SOURCES[1]).read_text()))
 expected.update(re.findall(r'^\.global\s+(\w+)',(ROOT/SOURCES[2]).read_text(),re.M))
 with tempfile.TemporaryDirectory(prefix='border-guard-link-') as folder:
  temp=Path(folder);objects=[]
  for i,source in enumerate((SOURCES[0],SOURCES[2])):
   obj=temp/f'guard{i}.o'
   subprocess.run([compiler,*FLAGS,'-c',str(ROOT/source),'-o',str(obj)],check=True,capture_output=True);objects.append(str(obj))
  link=temp/'guard.ld';link.write_text(f'SECTIONS {{ . = {base}; .text : {{ *(.text*) }} .rodata : {{ *(.rodata*) }} /DISCARD/ : {{ *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }} }}')
  elf=temp/'guard.elf'
  subprocess.run([linker,'-T',str(link),'--entry=m10v_border_client_construct',*objects,'-o',str(elf)],check=True,capture_output=True)
  data=elf.read_bytes()
  if data[:7]!=b'\x7fELF\x01\x01\x01' or struct.unpack_from('<HH',data,16)!=(2,40):raise ValueError('invalid linked guard ARM ELF')
  sh=struct.unpack_from('<I',data,32)[0];size,count,names_index=struct.unpack_from('<HHH',data,46)
  if size!=40 or sh+count*size>len(data) or names_index>=count:raise ValueError('invalid guard ELF section directory')
  rows=[struct.unpack_from('<10I',data,sh+i*40) for i in range(count)];nr=rows[names_index];names=data[nr[4]:nr[4]+nr[5]]
  image=bytearray();symbols={};ranges=[]
  for row in rows:
   name=names[row[0]:].split(b'\0',1)[0].decode()
   if row[2]&2 and row[5]:
    if row[1]!=1 or row[2]&1 or name not in ('.text','.rodata') or not base<=row[3]<base+65536 or row[3]+row[5]>base+65536:
     raise ValueError('guard must contain only bounded read-only code/rodata, found '+name)
    off=row[3]-base
    if len(image)<off+row[5]:image.extend(bytes(off+row[5]-len(image)))
    image[off:off+row[5]]=data[row[4]:row[4]+row[5]];ranges.append({'name':name,'address':row[3],'bytes':row[5]})
   if row[1]==2:
    sr=rows[row[6]];strings=data[sr[4]:sr[4]+sr[5]]
    for at in range(row[4],row[4]+row[5],16):
     n,value,_,info,_,section=struct.unpack_from('<IIIBBH',data,at);symbol=strings[n:].split(b'\0',1)[0].decode()
     if not section and symbol:raise ValueError('undefined guard symbol '+symbol)
     if symbol in expected and info&15==2:
      if value&3 or not base<=value<base+65536:raise ValueError('invalid guard function address '+symbol)
      symbols[symbol]=value
  if not image or set(symbols)!=expected:raise ValueError('guard exports differ from reviewed header/assembly contract')
 return bytes(image),symbols,ranges,subprocess.check_output([compiler,'--version'],text=True).splitlines()[0]
def build(base=0x54160000,stock=None,*,border_enabled=False,internal_guard_research=False,camera_model='gr3',out_dir=None):
 if type(border_enabled)is not bool or type(internal_guard_research)is not bool:raise ValueError('guard and border options must be explicit booleans')
 disabled={'schema':'m10v-border-guard-component/v1','enabled':False,'internal_research':False,
  'code_bytes':0,'symbols':{},'patches':[],'firmware_artifact':False,'hardware_activation':False}
 if not internal_guard_research:return b'',disabled
 if not border_enabled:raise ValueError('internal guard research requires border_enabled')
 if camera_model not in MODELS:raise ValueError('guard installer admits only independently pinned GR III/IIIx inputs')
 model=MODELS[camera_model]
 if type(base)is not int or base&15 or not 0x540b6000<=base<=0x54ef0000:raise ValueError('invalid caller-selected guard component base')
 if not isinstance(stock,bytes) or digest(stock)!=model['rtos_sha256']:raise ValueError('guard installer requires exact model-locked official RTOS')
 spans=[]
 for name,start,end,locked in ABI_SPANS:
  if digest(stock[start-RTOS_BASE:end-RTOS_BASE])!=locked:raise ValueError('guard touched ABI span differs: '+name)
  spans.append({'name':name,'start':start,'end':end,'sha256':locked})
 for at,expected,target,role in HOOKS:
  if struct.unpack_from('<I',stock,at-RTOS_BASE)[0]!=expected:raise ValueError('guard preimage differs at '+hex(at))
 code,symbols,ranges,compiler=_compile(base)
 patches=[]
 for at,expected,target,role in HOOKS:
  replacement=arm_bl(at,symbols[target]) if isinstance(target,str) else target
  patches.append({'address':at,'expected':expected,'replacement':replacement,'role':role,
   **({'target':symbols[target],'symbol':target} if isinstance(target,str) else {})})
 if len({p['address'] for p in patches})!=len(patches):raise ValueError('duplicate guard patch address')
 contract=json.loads((ROOT/SOURCES[3]).read_text())
 contract.update(abi_basis_model='gr3',model=camera_model,firmware=model['version'],rtos_sha256=model['rtos_sha256'])
 report={'schema':'m10v-border-guard-component/v1','enabled':True,'internal_research':True,
  'base':base,'code_bytes':len(code),'code_sha256':digest(code),'symbols':symbols,'sections':ranges,
  'patches':patches,'camera_model':camera_model,'original_version':model['version'],'original_rtos_sha256':model['rtos_sha256'],
  'verified_abi_spans':spans,'model_layout_verified':True,'physical_model_support_verified':False,
  'compiler':compiler,'flags':FLAGS,'sources':{p:digest((ROOT/p).read_bytes()) for p in SOURCES},
  'contract':contract,'worker_allocations':{'transfer_first':{'stock':0x44,'owned':0x58,'gate_offset':0x54},
   'fill':{'stock':0x58,'owned':0x68},'resize':{'stock':0x48,'owned':0x58},'transfer_second_preserved':0x44},
  'firmware_artifact':False,'hardware_activation':False,'pixel_pipeline_enabled':False,'camera_tested':False,
  'activation_blockers':['native reservation semaphore-acquisition errors are not independently guarded',
   'native factory teardown must not reclaim stage-gate worker while owners or waiters exist',
   'complete-frame private stage enter/leave must be installed by the owning publisher',
   'bundled prepared=1 requires once-per-canvas REAL native cache ownership pre/post by caller',
   'physical pixels/cache, memory admission and performance require acceptance'],
  'integration':'Append code at base; merge all 18 indivisible patches after conflict/preimage checks; no central builder or Node export modified',
  'mutable_static_bytes':0,'tls_bytes':0,'caller_address_ownership_required':True}
 if out_dir is not None:
  out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
  (out/'m10v-border-guard-arm.bin').write_bytes(code)
  (out/'m10v-border-guard-arm.json').write_text(json.dumps(report,indent=2)+'\n')
 return code,report
def apply_patch_plan(stock,patches):
 """Apply reviewable instructions to an in-memory fixture, never a file/device."""
 output=bytearray(stock);seen=set()
 for patch in patches:
  at=patch['address'];off=at-RTOS_BASE
  if at in seen or at&3 or not 0<=off<=len(output)-4:raise ValueError('invalid/colliding guard patch')
  seen.add(at)
  if struct.unpack_from('<I',output,off)[0]!=patch['expected']:raise ValueError('guard patch collision/preimage differs at '+hex(at))
  struct.pack_into('<I',output,off,patch['replacement'])
 return bytes(output)
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--base',type=lambda v:int(v,0),default=0x54160000)
 parser.add_argument('--rtos',type=Path);parser.add_argument('--out',type=Path)
 parser.add_argument('--camera-model',choices=sorted(MODELS),default='gr3')
 parser.add_argument('--border-enabled',action='store_true');parser.add_argument('--internal-guard-research',action='store_true')
 args=parser.parse_args();stock=args.rtos.read_bytes() if args.internal_guard_research and args.rtos else None
 code,report=build(args.base,stock,border_enabled=args.border_enabled,internal_guard_research=args.internal_guard_research,camera_model=args.camera_model,out_dir=args.out)
 print(json.dumps(report,indent=2))
