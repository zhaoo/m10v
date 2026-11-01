"""Build a static Linux ARM service candidate, kept disabled without target proof.

No install/start, firmware edit, SD write, target-ready override or secret logging.
The pairing file and executable are private artifacts, never source commits.
"""
import argparse,hashlib,json,os,re,secrets,shutil,struct,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCES=['auth.c','http_parser.c','json.c','operations.c','http_server.c','linux_io.c','runtime.c','film_upload.c','../gr3/m10v_sd_library.c']
HEADERS=['auth.h','http_parser.h','json.h','operations.h','http_server.h','linux_io.h','generated_contract.h','film_upload.h','transaction.h','../gr3/m10v_sd_contract.h','../gr3/m10v_sd_library.h']
def _hash(value):return hashlib.sha256(value).hexdigest()
def _metadata(value):
 if type(value)is not str or not re.fullmatch('[a-f0-9]{64}',value):raise ValueError('expected lowercase SHA256 metadata')
 return value

def _audit_elf(elf):
 if elf[:7]!=b'\x7fELF\x01\x01\x01' or struct.unpack_from('<HH',elf,16)!=(2,40):raise ValueError('expected executable ARM ELF32')
 phoff=struct.unpack_from('<I',elf,28)[0];size,count=struct.unpack_from('<HH',elf,42)
 if size!=32 or not count or phoff+size*count>len(elf):raise ValueError('bad ELF program headers')
 for i in range(count):
  kind=struct.unpack_from('<I',elf,phoff+i*size)[0]
  if kind in (2,3):raise ValueError('service must have no dynamic segment or interpreter')

def _stack_audit(elf,path,linker,frames):
 """Bound direct ARM call paths, the guarded JSON recursion, and the three
 fixed callbacks in generated main. Unknown recursion/stack entries fail closed.
 This bounds scratch stack, not kernel process RSS or initial environment pages.
 """
 shoff=struct.unpack_from('<I',elf,32)[0];entsize,count=struct.unpack_from('<HH',elf,46)
 if entsize!=40 or shoff+entsize*count>len(elf):raise ValueError('bad ELF sections')
 sections=[struct.unpack_from('<10I',elf,shoff+i*entsize) for i in range(count)]
 functions={};objects={}
 for row in sections:
  if row[1]!=2:continue
  string_section=sections[row[6]];strings=elf[string_section[4]:string_section[4]+string_section[5]]
  for offset in range(row[4],row[4]+row[5],16):
   name,value,size,info,other,section=struct.unpack_from('<IIIBBH',elf,offset)
   symbol=strings[name:].split(b'\0',1)[0].decode('ascii')
   if info&15==2 and section:functions[value]=symbol
   elif info&15==1 and symbol in ('config','backend'):objects[symbol]=size
 candidates=[os.environ.get('M10V_OBJDUMP'),shutil.which('llvm-objdump'),str(Path(linker).resolve().with_name('llvm-objdump')),'/opt/homebrew/opt/llvm/bin/llvm-objdump','/usr/local/opt/llvm/bin/llvm-objdump']
 objdump=next((Path(p) for p in candidates if p and Path(p).is_file()),None)
 if objdump is None:raise RuntimeError('LLVM objdump is required for ARM stack audit; set M10V_OBJDUMP')
 assembly=subprocess.check_output([str(objdump),'-d','--no-show-raw-insn',str(path)],text=True)
 graph={name:set() for name in functions.values()};current=None
 callbacks={'unavailable','m10v_linux_random','m10v_linux_now_ms'}
 for line in assembly.splitlines():
  label=re.match(r'^[0-9a-f]+ <([^>]+)>:',line)
  if label:current=label.group(1);continue
  instruction=re.search(r':\s+(b[a-z]*)\s+(.*)',line)
  if current not in graph or not instruction:continue
  opcode,operand=instruction.groups()
  direct=re.match(r'0x([0-9a-f]+)',operand)
  if direct:
   target=functions.get(int(direct.group(1),16))
   if target and (target!=current or opcode in ('bl','blx')):graph[current].add(target)
  elif opcode in ('blx','bx') and re.match(r'r[0-9]+',operand):graph[current].update(callbacks)
 def bound(name,trail):
  if name not in frames:raise ValueError('missing ARM stack evidence for '+name)
  count=trail.count(name)
  if count:
   if name!='value':raise ValueError('unproved recursion: '+name)
   if count>=12:return 0
  return frames[name]+max([bound(child,trail+[name]) for child in graph.get(name,[])]+[0])
 maximum=bound('_start',[])
 phoff=struct.unpack_from('<I',elf,28)[0];size,count=struct.unpack_from('<HH',elf,42)
 writable=0
 for index in range(count):
  row=struct.unpack_from('<8I',elf,phoff+index*size)
  if row[0]==1 and row[6]&2:writable+=row[5]
 staging=writable+sum(objects.values())
 if maximum>4096 or staging+4096>65536:raise ValueError('ARM scratch memory budget exceeded')
 return maximum,staging

def build_service(output,*,catalog_hash,renderer_hash,key=None,instance_id=None):
 catalog_hash=_metadata(catalog_hash);renderer_hash=_metadata(renderer_hash)
 key=secrets.token_bytes(32) if key is None else key;instance_id=secrets.token_bytes(16) if instance_id is None else instance_id
 if type(key)is not bytes or len(key)!=32 or type(instance_id)is not bytes or len(instance_id)!=16:raise ValueError('invalid pairing material')
 output=Path(output)
 if output.exists():raise FileExistsError(output)
 clang=shutil.which('clang');linker=shutil.which('ld.lld')
 if not clang or not linker:raise RuntimeError('Clang and LLD are required')
 paths=[Path('native/companion')/name for name in SOURCES+HEADERS]+[Path('native/gr3/m10v_library.h'),Path('contracts/companion-v1.json'),Path('scripts/build_companion_service.py')]
 source_fingerprint=_hash(json.dumps([[str(p),_hash((ROOT/p).read_bytes())] for p in paths],separators=(',',':')).encode())
 # Reject stale generated rules, including metadata-only contract changes.
 check=subprocess.run([os.sys.executable,str(ROOT/'scripts/generate_companion_registry.py'),'--check'],capture_output=True)
 if check.returncode:raise ValueError('generated companion registry is stale')
 output.mkdir(parents=True,mode=0o700)
 key_id=_hash(key)[:32]
 def array(data):return '{'+','.join(str(n) for n in data)+'}'
 main='''#include "linux_io.h"
static int unavailable(void*c,const m10v_backend_request*r,m10v_backend_response*out){(void)c;(void)r;out->status=M10V_OPERATION_UNKNOWN;return M10V_ERROR_BRIDGE_UNAVAILABLE;}
static const m10v_companion_server_config config={.key=KEY,.instance_id=INSTANCE,.build_id=BUILD,.catalog_hash=CATALOG,.renderer_hash=RENDERER,.key_id="KEYID",.random=m10v_linux_random,.now_ms=m10v_linux_now_ms,.operation_timeout_ms=3000,.wifi_verified=0};
static const m10v_companion_backend backend={0,unavailable};
__attribute__((noreturn))void _start(void){int result=m10v_companion_serve(&config,&backend);register unsigned r0 __asm__("r0")=(unsigned)result,r7 __asm__("r7")=1;__asm__ volatile("svc 0"::"r"(r0),"r"(r7):"memory");for(;;){}}
'''
 for token,value in [('KEYID',key_id),('KEY',array(key)),('INSTANCE',array(instance_id)),('BUILD',array(bytes.fromhex(source_fingerprint))),('CATALOG',array(bytes.fromhex(catalog_hash))),('RENDERER',array(bytes.fromhex(renderer_hash)))]:main=main.replace(token,value)
 flags=['--target=armv7-none-eabi','-mcpu=cortex-a9','-marm','-mfloat-abi=soft','-Os','-std=c11','-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-ffunction-sections','-fdata-sections','-fno-vectorize','-fno-slp-vectorize','-Wall','-Wextra','-Werror','-fstack-usage','-I',str(ROOT/'native/companion')]
 stack={}
 with tempfile.TemporaryDirectory(prefix='m10v-companion-build-') as private:
  private=Path(private);os.chmod(private,0o700);(private/'main.c').write_text(main);os.chmod(private/'main.c',0o600);objects=[]
  def run(command):
   result=subprocess.run(command,capture_output=True)
   if result.returncode:
    log=output/'compiler-private.log';log.write_bytes(result.stderr);os.chmod(log,0o600)
    raise RuntimeError('ARM service build failed; diagnostic is in private compiler log')
  for source in [*(ROOT/'native/companion'/name for name in SOURCES),private/'main.c']:
   obj=private/(source.stem+'.o');run([clang,*flags,'-c',str(source),'-o',str(obj)]);objects.append(obj)
  elf_path=output/'m10v-companion.elf';run([linker,'-m','armelf_linux_eabi','-static','--gc-sections','--build-id=none','--entry=_start',*[str(p) for p in objects],'-o',str(elf_path)])
  _audit_elf(elf_path.read_bytes());os.chmod(elf_path,0o700)
  for usage in private.glob('*.su'):
   for line in usage.read_text().splitlines():
    cells=line.split('\t')
    if len(cells)>=2:stack[cells[0].rsplit(':',1)[-1]]=max(stack.get(cells[0].rsplit(':',1)[-1],0),int(cells[1]))
 stack_bound,staging_bytes=_stack_audit(elf_path.read_bytes(),elf_path,linker,stack)
 pairing={'schema':'m10v.companion-pairing/v1','protocol':1,'model':'GR III','instanceId':instance_id.hex(),'keyId':key_id,'keyHex':key.hex()}
 pair=output/'pairing.json';pair.write_text(json.dumps(pairing,indent=2)+'\n');os.chmod(pair,0o600)
 receipt={'schema':'m10v-companion-service/v1','buildId':source_fingerprint[:24],'sourceFingerprint':source_fingerprint,'serviceSha256':_hash(elf_path.read_bytes()),'catalogHash':catalog_hash,'rendererHash':renderer_hash,'registrySha256':_hash((ROOT/'contracts/companion-v1.json').read_bytes()),'installable':False,'listenEnabled':False,'cameraPassed':False,'capabilities':{'readState':False,'writeState':False,'uploadFilm':False,'captureEvidence':False},'linuxAbiEvidence':'compile-only','reason':'residentOwnerCacheAndWifiInterfaceUnproven','functionStackBytes':stack,'stackAllowanceBytes':4096,'reachableStackBoundBytes':stack_bound,'stagingStaticBytes':staging_bytes}
 (output/'service-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
 return receipt
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True);parser.add_argument('--catalog-hash',required=True);parser.add_argument('--renderer-hash',required=True);args=parser.parse_args()
 print(json.dumps(build_service(args.out,catalog_hash=args.catalog_hash,renderer_hash=args.renderer_hash)))
