"""Build a static Linux ARM debug candidate pinned to an audited native owner.

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
 enabled='m10v_linux_target_exchange' in functions.values()
 random='seeded_random' if enabled else 'm10v_linux_random'
 exchange='m10v_linux_target_exchange' if enabled else 'unavailable'
 callbacks={
  'm10v_auth_accept':{random},'m10v_companion_server_init':{random},
  'm10v_companion_tick':{exchange,'m10v_linux_now_ms'},
  'route_authenticated':{exchange,'m10v_linux_now_ms'},
  'route_upload':{exchange,random,'m10v_linux_now_ms'},
  'm10v_companion_serve':{'m10v_linux_now_ms'},'write_all':{'m10v_linux_now_ms'},
  'm10v_linux_target_init':{'physical_read','bind'},'read_mem':{'physical_read'},
  'discover':{'physical_read'},'publish':{'physical_write','m10v_linux_now_ms'},
  'receive':{'physical_read','m10v_linux_now_ms'},'m10v_linux_wifi_discover':{'wifi_query'}}
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
  elif opcode in ('blx','bx') and re.match(r'r[0-9]+',operand):
   if current not in callbacks:raise ValueError('unproved indirect call in '+current)
   graph[current].update(callbacks[current])
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
 if maximum>4096 or staging+4096>65536:raise ValueError(f'ARM scratch memory budget exceeded: stack={maximum}, static={staging}, allowance=4096, limit=65536')
 return maximum,staging

def _target_metadata(folder,catalog_hash,renderer_hash):
 folder=Path(folder);receipt=json.loads((folder/'M10V-build-receipt.json').read_text())
 name=receipt.get('filename')
 if name!='fwdc239b.bin':raise ValueError('unexpected candidate filename')
 binary=folder/name
 if _hash(binary.read_bytes())!=receipt.get('candidate_sha256'):raise ValueError('candidate hash differs')
 manifest=json.loads((folder/'M10V-runtime-manifest.json').read_text());component=manifest.get('companion',{})
 identity=component.get('identity',{})
 if component.get('enabled')is not True or component.get('schema')!='m10v-companion-owner/v2' or component.get('descriptor_offset')!=0x6400 or component.get('owner_bytes')!=0x6440:raise ValueError('candidate has no supported resident owner')
 if identity.get('catalogHash')!=catalog_hash or identity.get('rendererHash')!=renderer_hash:raise ValueError('candidate metadata differs')
 _metadata(identity.get('buildId'))
 for name,digest in manifest['sources'].items():
  if name.startswith('/') or '..' in Path(name).parts or _hash((ROOT/name).read_bytes())!=digest:raise ValueError('candidate source differs: '+name)
 command="import{readFileSync}from'node:fs';import{decodeFrameMap}from'./node/gr3-frames.mjs';const b=readFileSync(process.argv[1]),d=decodeFrameMap(b,b.readUInt32LE(b.length-8)).decoded;process.stdout.write(d.subarray(0x10870,0x10870+d.readUInt32LE(0x1086c)));"
 rom=subprocess.check_output(['node','--input-type=module','-e',command,str(binary)],cwd=ROOT)
 offset=manifest['base']-0x53000000
 if offset<0 or _hash(rom[offset:offset+manifest['code_bytes']])!=manifest['code_sha256']:raise ValueError('candidate runtime hash differs')
 anchors=[]
 for address in [0x5316fcf8,0x5319667c,0x5383c834,0x5383c870]:
  window=rom[address-0x53000000:address-0x53000000+16]
  if len(window)!=16 or not any(window):raise ValueError('missing candidate ROM anchor')
  anchors.append(window)
 return identity,anchors,receipt['candidate_sha256']

def build_service(output,*,catalog_hash,renderer_hash,key=None,instance_id=None,candidate_dir=None):
 catalog_hash=_metadata(catalog_hash);renderer_hash=_metadata(renderer_hash)
 target=_target_metadata(candidate_dir,catalog_hash,renderer_hash) if candidate_dir is not None else None
 key=secrets.token_bytes(32) if key is None else key;instance_id=secrets.token_bytes(16) if instance_id is None else instance_id
 if type(key)is not bytes or len(key)!=32 or type(instance_id)is not bytes or len(instance_id)!=16:raise ValueError('invalid pairing material')
 output=Path(output)
 if output.exists():raise FileExistsError(output)
 clang=shutil.which('clang');linker=shutil.which('ld.lld')
 if not clang or not linker:raise RuntimeError('Clang and LLD are required')
 sources=SOURCES+(['linux_target.c','resident_bridge.c','linux_wifi.c'] if target else [])
 headers=HEADERS+(['linux_target.h','resident_bridge.h','linux_wifi.h','../gr3/m10v_companion_owner.h'] if target else [])
 paths=[Path('native/companion')/name for name in sources+headers]+[Path('native/gr3/m10v_library.h'),Path('contracts/companion-v1.json'),Path('scripts/build_companion_service.py')]
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
 if target:
  identity,anchors,candidate_sha=target
  main='''#include "linux_io.h"
#include "linux_target.h"
static m10v_linux_target target;
static m10v_linux_devmem memory;
static m10v_linux_target_transport transport;
static m10v_linux_target_config target_config={.build=BUILD,.catalog=CATALOG,.renderer=RENDERER,.rom=ANCHORS,.timeout_ms=3000};
static unsigned boot_used;
static void stage(const char*p){unsigned n=0;while(p[n])n++;register unsigned r0 __asm__("r0")=1,r1 __asm__("r1")=(unsigned)(uintptr_t)p,r2 __asm__("r2")=n,r7 __asm__("r7")=4;__asm__ volatile("svc 0":"+r"(r0):"r"(r1),"r"(r2),"r"(r7):"memory","cc");}
static int seeded_random(void*c,uint8_t*out,uint32_t n){(void)c;if(!boot_used){if(n!=16)return 0;for(unsigned i=0;i<16;i++)out[i]=target_config.nonce[i];boot_used=1;return 1;}return m10v_linux_random(0,out,n);}
static m10v_companion_server_config config={.key=KEY,.instance_id=INSTANCE,.build_id=BUILD,.catalog_hash=CATALOG,.renderer_hash=RENDERER,.key_id="KEYID",.random=seeded_random,.now_ms=m10v_linux_now_ms,.operation_timeout_ms=3000,.read_state=1,.write_state=1};
static const m10v_companion_backend backend={&target,m10v_linux_target_exchange};
static int run(void){
 stage("M10V_START\\n");
 if(!m10v_linux_random(0,target_config.nonce,16)||!m10v_linux_devmem_open(&memory,&transport,m10v_linux_now_ms))return 1;
 stage("MEMORY_OPEN\\n");
 int code=1;for(unsigned i=0;i<160;i++){code=m10v_linux_target_init(&target,&target_config,&transport);if(!code)break;if(!m10v_linux_pause_ms(50))goto done;}if(code)goto done;
 stage("OWNER_FOUND\\n");
 for(unsigned i=0;i<160;i++){code=m10v_linux_target_hello(&target);if(!code)break;if(code!=M10V_ERROR_BUSY||!m10v_linux_pause_ms(50))goto done;}
 if(code)goto done;
 stage("HELLO_OK\\n");
 for(unsigned i=0;i<600&&!config.wifi_verified;i++){m10v_linux_prepare_wifi(&config);if(!config.wifi_verified&&!m10v_linux_pause_ms(100)){code=1;goto done;}}
 if(!config.wifi_verified){code=1;goto done;}
 stage("WIFI_OK\\n");code=m10v_companion_serve(&config,&backend);
 done:m10v_linux_devmem_close(&memory);return code;
}
__attribute__((noreturn))void _start(void){int result=run();register unsigned r0 __asm__("r0")=(unsigned)result,r7 __asm__("r7")=1;__asm__ volatile("svc 0"::"r"(r0),"r"(r7):"memory");for(;;){}}
'''
  main=main.replace('ANCHORS','{'+','.join(array(x) for x in anchors)+'}')
 for token,value in [('KEYID',key_id),('KEY',array(key)),('INSTANCE',array(instance_id)),('BUILD',array(bytes.fromhex(target[0]['buildId'] if target else source_fingerprint))),('CATALOG',array(bytes.fromhex(catalog_hash))),('RENDERER',array(bytes.fromhex(renderer_hash)))]:main=main.replace(token,value)
 flags=['--target=armv7-none-eabi','-mcpu=cortex-a9','-marm','-mfloat-abi=soft','-Os','-std=c11','-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-ffunction-sections','-fdata-sections','-fno-vectorize','-fno-slp-vectorize','-Wall','-Wextra','-Werror','-fstack-usage','-I',str(ROOT/'native/companion')]
 stack={}
 with tempfile.TemporaryDirectory(prefix='m10v-companion-build-') as private:
  private=Path(private);os.chmod(private,0o700);(private/'main.c').write_text(main);os.chmod(private/'main.c',0o600);objects=[]
  def run(command):
   result=subprocess.run(command,capture_output=True)
   if result.returncode:
    log=output/'compiler-private.log';log.write_bytes(result.stderr);os.chmod(log,0o600)
    raise RuntimeError('ARM service build failed; diagnostic is in private compiler log')
  for source in [*(ROOT/'native/companion'/name for name in sources),private/'main.c']:
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
 if target:receipt.update({'buildId':target[0]['buildId'],'firmwareSha256':target[2],'installable':True,'reason':'debugCandidateRequiresDeviceValidation','listenPolicy':'residentHelloAndVerifiedWifi','capabilities':{'readState':True,'writeState':True,'uploadFilm':False,'captureEvidence':False}})
 (output/'service-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
 return receipt
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True);parser.add_argument('--catalog-hash',required=True);parser.add_argument('--renderer-hash',required=True);parser.add_argument('--candidate-dir');args=parser.parse_args()
 print(json.dumps(build_service(args.out,catalog_hash=args.catalog_hash,renderer_hash=args.renderer_hash,candidate_dir=args.candidate_dir)))
