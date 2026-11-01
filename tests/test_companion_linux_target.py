"""Exercise real Linux adapter + resident CRC/consumer against bounded memory.

No camera, /dev/mem, service, network or bypass-ready flag. Only the physical
transport and owner command executor are fixtures; production bridge consumes
actual published request bytes and produces real correlated responses.
"""
from pathlib import Path
import ctypes as C
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
FIXTURE=r'''
#include "linux_target.h"
#include "../gr3/m10v_companion_owner.h"
#include <string.h>
#define OWNER 0x56000000u
#define CONTEXT 0x56010000u
#define WIRE (CONTEXT+128u)
#define REQUIRE(x) do{if(!(x))return __LINE__;}while(0)
typedef struct {m10v_linux_target t;m10v_linux_target_config cfg;m10v_companion_ui_descriptor d;m10v_resident_wire w;m10v_resident_consumer consumer;uint64_t now;unsigned writes,execute,violation,fail_write,torn,nonce_bad;uint32_t bound,guard,owner;} fixture;
static const uint32_t anchors[]={0x5316fcf8u,0x5319667cu,0x5383c834u,0x5383c870u};
static int rd(void*v,uint32_t a,void*out,uint32_t n){
 fixture*f=v;
 if(a==0x55063910u&&n==4){memcpy(out,&f->guard,4);return 1;}
 if(a==0x55063988u&&n==4){memcpy(out,&f->owner,4);return 1;}
 for(unsigned i=0;i<4;i++)if(a==anchors[i]&&n==16){memcpy(out,f->cfg.rom[i],16);return 1;}
 if(a>=OWNER+0x6400u&&a+n<=OWNER+0x6440u){memcpy(out,(uint8_t*)&f->d+(a-OWNER-0x6400u),n);return 1;}
 if(a>=WIRE&&a+n<=WIRE+sizeof(f->w)){
  memcpy(out,(uint8_t*)&f->w+(a-WIRE),n);
  if(f->torn&&a==WIRE+128+sizeof(m10v_resident_message)&&n==4){f->torn--;if(!f->torn){uint32_t odd=f->w.response.sequence|1u;memcpy(out,&odd,4);}}
  return 1;
 }
 return 0;
}
static int wr(void*v,uint32_t a,const void*in,uint32_t n){fixture*f=v;f->writes++;
 if(!f->bound||a<f->bound||n>sizeof(f->w.request)||a+n>f->bound+sizeof(f->w.request)){f->violation++;return 0;}
 memcpy((uint8_t*)&f->w+(a-WIRE),in,n);return f->fail_write!=f->writes;
}
static int bind_req(void*v,uint32_t a,uint32_t n){fixture*f=v;if(f->bound||a!=WIRE+128||n!=1152)return 0;f->bound=a;return 1;}
static uint64_t clock_ms(void*v){return ((fixture*)v)->now;}
static uint32_t crc(const void*p,unsigned n){uint32_t c=~0u;const uint8_t*b=p;for(unsigned i=0;i<n;i++){c^=b[i];for(unsigned j=0;j<8;j++)c=(c>>1)^(0xedb88320u&(0u-(c&1u)));}return ~c;}
static void identity(fixture*f,m10v_companion_snapshot*s){
 uint8_t buffer[512];unsigned n=14;memcpy(buffer,"m10v-config/v2",14);memcpy(buffer+n,(uint8_t*)&s->state+12,168);n+=168;memcpy(buffer+n,s->custom_hashes,320);n+=320;buffer[n++]=(uint8_t)s->active_slot;m10v_sha256(buffer,n,s->config_hash);
 n=16;memcpy(buffer,"m10v-revision/v2",16);memcpy(buffer+n,f->cfg.nonce,16);n+=16;memcpy(buffer+n,f->cfg.build,32);n+=32;memcpy(buffer+n,f->cfg.catalog,32);n+=32;memcpy(buffer+n,f->cfg.renderer,32);n+=32;memcpy(buffer+n,s->config_hash,32);n+=32;memcpy(buffer+n,&s->state.sequence,4);n+=4;memcpy(buffer+n,&f->d.epoch,4);n+=4;m10v_sha256(buffer,n,s->revision);
}
static int execute(void*v,uint32_t command,const uint8_t*in,uint32_t n,uint8_t*out,uint32_t*bytes){
 fixture*f=v;f->execute++;
 if(command==1){if(n!=16)return 10;memcpy(out,in,16);if(f->nonce_bad)out[0]^=1;memcpy(out+16,f->cfg.build,32);*bytes=48;return 0;}
 if(command>=5&&command<=7){m10v_extension_result e={.status=M10V_OPERATION_COMMITTED,.has_snapshot=1};e.snapshot.available=1;e.snapshot.values[0]=1;e.snapshot.revision[0]=42;memcpy(out,&e,sizeof(e));*bytes=sizeof(e);return 0;}
 m10v_companion_result result={0};result.status=M10V_OPERATION_COMMITTED;result.has_snapshot=1;result.snapshot.active_slot=9;result.snapshot.state.magic=0x5630314du;result.snapshot.state.version=5;result.snapshot.state.size=184;result.snapshot.state.sequence=7;result.snapshot.state.slots[9].film=321;result.snapshot.state.crc=crc(&result.snapshot.state,180);identity(f,&result.snapshot);memcpy(out,&result,sizeof(result));*bytes=sizeof(result);return 0;
}
static int cache(void*v,void*p,uint32_t n){(void)v;(void)p;(void)n;return 1;}
static int consume(fixture*f){m10v_resident_ops io={f,cache,cache,execute};return m10v_resident_consume(&f->w,&f->consumer,&io);}
static void fixture_init(fixture*f){memset(f,0,sizeof(*f));f->guard=1;f->owner=OWNER;f->now=100;memset(f->cfg.build,1,32);memset(f->cfg.catalog,2,32);memset(f->cfg.renderer,3,32);memset(f->cfg.nonce,4,16);for(unsigned i=0;i<4;i++)memset(f->cfg.rom[i],i+5,16);f->cfg.timeout_ms=500;f->d=(m10v_companion_ui_descriptor){.magic=M10V_COMPANION_DESCRIPTOR_MAGIC,.version=2,.bytes=64,.context=CONTEXT,.wire=WIRE,.wire_bytes=2432,.epoch=CONTEXT};f->w.magic=M10V_RESIDENT_MAGIC;f->w.version=2;f->w.bytes=2432;f->w.alive=1;f->w.owner=OWNER;f->w.epoch=CONTEXT;memcpy(f->w.build,f->cfg.build,32);}
static int initialize(fixture*f){m10v_linux_target_transport io={f,rd,wr,bind_req,clock_ms};return m10v_linux_target_init(&f->t,&f->cfg,&io);}
static int hello(fixture*f){if(m10v_linux_target_hello(&f->t)!=M10V_ERROR_BUSY||consume(f)||m10v_linux_target_hello(&f->t))return 1;return 0;}
static void patch(fixture*f,m10v_companion_patch*p){memset(p,0,sizeof(*p));memcpy(p->boot_id,f->cfg.nonce,16);memcpy(p->catalog_hash,f->cfg.catalog,32);memcpy(p->renderer_hash,f->cfg.renderer,32);p->request_id[0]=9;p->activate_slot=9;}
int linux_target_case(unsigned mode){fixture f;fixture_init(&f);m10v_companion_patch p;patch(&f,&p);m10v_companion_snapshot snapshot;m10v_backend_response out={0,0,&snapshot};m10v_backend_request request={M10V_BACKEND_READ_STATE,0,0};
 if(mode==1){m10v_linux_target_config cfg=f.cfg;cfg.rom[0][0]^=1;m10v_linux_target_transport io={&f,rd,wr,bind_req,clock_ms};REQUIRE(m10v_linux_target_init(&f.t,&cfg,&io)==10);REQUIRE(!f.writes);return 0;}
 if(mode==2)f.d.wire+=128;if(mode==3)f.w.alive=0;if(mode==4)f.w.build[0]^=1;if(mode==5)f.w.request.sequence=2;
 if(mode>=2&&mode<=5){REQUIRE(initialize(&f)==10);REQUIRE(!f.writes);return 0;}
 REQUIRE(initialize(&f)==0);REQUIRE(f.writes==0);
 if(mode==18){REQUIRE(m10v_linux_target_exchange(&f.t,&request,&out)==10);REQUIRE(!f.writes);return 0;}
 if(mode==7){f.nonce_bad=1;REQUIRE(m10v_linux_target_hello(&f.t)==6);REQUIRE(!consume(&f));REQUIRE(m10v_linux_target_hello(&f.t)==10);REQUIRE(!f.t.ready);return 0;}
 REQUIRE(!hello(&f));REQUIRE(f.t.ready);
 if(mode==6){f.d.epoch+=128;REQUIRE(m10v_linux_target_exchange(&f.t,&request,&out)==10);REQUIRE(f.writes==3);return 0;}
 if(mode==13){p.catalog_hash[0]^=1;request.command=M10V_BACKEND_SUBMIT;request.patch=&p;REQUIRE(m10v_linux_target_exchange(&f.t,&request,&out)==4);REQUIRE(f.writes==3);return 0;}
 if(mode==8||mode==9||mode==14||mode==19){request.command=M10V_BACKEND_SUBMIT;request.patch=&p;if(mode==9)f.fail_write=5;int code=m10v_linux_target_exchange(&f.t,&request,&out);
  if(mode==9){REQUIRE(code==10);REQUIRE(f.w.request.sequence&1u);REQUIRE(m10v_linux_target_exchange(&f.t,&request,&out)==10);REQUIRE(f.writes==5);return 0;}
  REQUIRE(!code);REQUIRE(out.status==1);request.command=M10V_BACKEND_POLL;
  if(mode==8){f.now+=500;unsigned writes=f.writes;REQUIRE(m10v_linux_target_exchange(&f.t,&request,&out)==10);REQUIRE(out.status==4);REQUIRE(m10v_linux_target_exchange(&f.t,&request,&out)==10);REQUIRE(f.writes==writes);return 0;}
  if(mode==19){request.command=M10V_BACKEND_SUBMIT;p.values[9][0]=1;REQUIRE(m10v_linux_target_exchange(&f.t,&request,&out)==5);REQUIRE(f.writes==6);return 0;}
  p.request_id[0]^=1;REQUIRE(m10v_linux_target_exchange(&f.t,&request,&out)==6);REQUIRE(f.writes==6);return 0;
 }
 REQUIRE(!m10v_linux_target_exchange(&f.t,&request,&out));REQUIRE(!out.has_snapshot);REQUIRE(!consume(&f));
 if(mode==10)f.w.response.crc^=1;
 if(mode==11){f.w.response.correlation^=1;f.w.response.crc=m10v_resident_crc(&f.w.response,f.w.response.sequence);}
 if(mode==15){f.w.response.bytes--;f.w.response.crc=m10v_resident_crc(&f.w.response,f.w.response.sequence);}
 if(mode==16||mode==17){m10v_companion_result result;memcpy(&result,f.w.response.payload,sizeof(result));if(mode==16)result.snapshot.state.crc^=1;else result.snapshot.revision[0]^=1;memcpy(f.w.response.payload,&result,sizeof(result));f.w.response.crc=m10v_resident_crc(&f.w.response,f.w.response.sequence);}
 if(mode==12){f.torn=2;REQUIRE(!m10v_linux_target_exchange(&f.t,&request,&out));REQUIRE(!out.has_snapshot);REQUIRE(!f.t.failed);}
 int received=m10v_linux_target_exchange(&f.t,&request,&out);
 if(mode==10||mode==11||mode==15||mode==16||mode==17){REQUIRE(received==10);REQUIRE(!out.has_snapshot);return 0;}
 REQUIRE(received==0);REQUIRE(out.has_snapshot);REQUIRE(snapshot.active_slot==9);REQUIRE(snapshot.state.slots[9].film==321);
 request.command=M10V_BACKEND_SUBMIT;request.patch=&p;REQUIRE(!m10v_linux_target_exchange(&f.t,&request,&out));REQUIRE(!consume(&f));request.command=M10V_BACKEND_POLL;REQUIRE(!m10v_linux_target_exchange(&f.t,&request,&out));REQUIRE(out.has_snapshot&&out.status==2);
 REQUIRE(!m10v_linux_target_exchange(&f.t,&request,&out));REQUIRE(f.w.request.command==4);REQUIRE(f.w.request.bytes==16);REQUIRE(!consume(&f));REQUIRE(!m10v_linux_target_exchange(&f.t,&request,&out));REQUIRE(!f.violation);REQUIRE(f.execute==4);return 0;
}
int linux_extension_case(void){fixture f;fixture_init(&f);REQUIRE(!initialize(&f));REQUIRE(!hello(&f));m10v_extension_snapshot snap;m10v_backend_response out={0,0,(void*)&snap};m10v_backend_request r={.command=M10V_BACKEND_READ_EXTENSIONS};
 REQUIRE(!m10v_linux_target_exchange(&f.t,&r,&out));REQUIRE(f.w.request.command==5);m10v_backend_request film={.command=M10V_BACKEND_READ_STATE};unsigned before=f.writes;REQUIRE(m10v_linux_target_exchange(&f.t,&film,&out)==M10V_ERROR_BUSY);REQUIRE(f.writes==before);REQUIRE(!consume(&f));REQUIRE(!m10v_linux_target_exchange(&f.t,&r,&out));REQUIRE(out.has_snapshot&&snap.values[0]==1&&snap.revision[0]==42);
 m10v_extension_patch p={.field=0,.value=1};p.request_id[0]=4;memcpy(p.boot_id,f.cfg.nonce,16);m10v_unhex(M10V_EXTENSIONS_HASH,32,p.contract_hash);r.command=M10V_BACKEND_SUBMIT_EXTENSIONS;r.patch=(const void*)&p;
 REQUIRE(!m10v_linux_target_exchange(&f.t,&r,&out));REQUIRE(f.w.request.command==6&&f.w.request.bytes==sizeof(p));unsigned writes=f.writes;p.value=0;REQUIRE(m10v_linux_target_exchange(&f.t,&r,&out)==M10V_ERROR_INVALID_RECIPE);REQUIRE(f.writes==writes);p.value=1;
 REQUIRE(!consume(&f));r.command=M10V_BACKEND_POLL_EXTENSIONS;REQUIRE(!m10v_linux_target_exchange(&f.t,&r,&out));REQUIRE(out.status==M10V_OPERATION_COMMITTED);REQUIRE(!m10v_linux_target_exchange(&f.t,&r,&out));REQUIRE(f.w.request.command==7&&f.w.request.bytes==16);REQUIRE(!consume(&f));REQUIRE(!m10v_linux_target_exchange(&f.t,&r,&out));return 0;
}
'''
class LinuxTargetTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup);private=Path(cls.tmp.name);source=private/'fixture.c';source.write_text(FIXTURE);library=private/'linux-target.dylib'
  result=subprocess.run(['clang','-std=c11','-O2','-Wall','-Wextra','-Werror','-DM10V_COMPANION_HOST_TEST','-dynamiclib','-I',str(ROOT/'native/companion'),str(source),str(ROOT/'native/companion/linux_target.c'),str(ROOT/'native/companion/resident_bridge.c'),str(ROOT/'native/companion/auth.c'),str(ROOT/'native/companion/extensions.c'),'-o',str(library)],capture_output=True,text=True)
  if result.returncode:raise AssertionError(result.stderr)
  cls.lib=C.CDLL(str(library));cls.lib.linux_target_case.argtypes=[C.c_uint];cls.lib.linux_target_case.restype=C.c_int
 def test_extension_read_apply_poll_use_separate_bounded_frames(self):self.assertEqual(self.lib.linux_extension_case(),0)
 def test_async_hello_read_apply_poll_and_ten_slot_identity(self):self.assertEqual(self.lib.linux_target_case(0),0)
 def test_discovery_rejects_wrong_rom_descriptor_dead_owner_build_and_existing_sequence(self):
  for mode in range(1,6):
   with self.subTest(mode=mode):self.assertEqual(self.lib.linux_target_case(mode),0)
 def test_epoch_change_nonce_mismatch_and_uninitialized_access_fail_closed(self):
  for mode in (6,7,18):
   with self.subTest(mode=mode):self.assertEqual(self.lib.linux_target_case(mode),0)
 def test_apply_timeout_or_partial_publication_never_replays(self):
  for mode in (8,9):
   with self.subTest(mode=mode):self.assertEqual(self.lib.linux_target_case(mode),0)
 def test_crc_correlation_torn_response_length_state_and_revision_are_checked(self):
  for mode in (10,11,12,15,16,17):
   with self.subTest(mode=mode):self.assertEqual(self.lib.linux_target_case(mode),0)
 def test_foreign_catalog_or_competing_operation_never_replaces_inflight(self):
  for mode in (13,14,19):
   with self.subTest(mode=mode):self.assertEqual(self.lib.linux_target_case(mode),0)
 def test_production_arm_transport_compiles_strictly(self):
  result=subprocess.run(['/opt/homebrew/opt/llvm/bin/clang','--target=armv7-none-eabi','-mcpu=cortex-a9','-marm','-mfloat-abi=soft','-Os','-std=c11','-ffreestanding','-fno-builtin','-Wall','-Wextra','-Werror','-c',str(ROOT/'native/companion/linux_target.c'),'-o',str(Path(self.tmp.name)/'target-arm.o')],capture_output=True,text=True)
  self.assertEqual(result.returncode,0,result.stderr)
 def test_production_arm_mmap_syscalls_enforce_direction_bounds(self):
  import struct
  from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_INTR
  from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R7, UC_ARM_REG_SP, UC_ARM_REG_LR
  private=Path(self.tmp.name);objects=[]
  for name in ('linux_target','resident_bridge','auth','runtime','extensions'):
   obj=private/(name+'-arm.o')
   subprocess.run(['/opt/homebrew/opt/llvm/bin/clang','--target=armv7-none-eabi','-mcpu=cortex-a9','-marm','-mfloat-abi=soft','-Os','-std=c11','-ffreestanding','-fno-builtin','-fno-stack-protector','-c',str(ROOT/'native/companion'/f'{name}.c'),'-o',str(obj)],check=True,capture_output=True)
   objects.append(str(obj))
  executable=private/'target-arm.elf'
  subprocess.run(['/opt/homebrew/bin/ld.lld','-m','armelf_linux_eabi','-Ttext=0x10000','--entry=m10v_linux_devmem_open',*objects,'-o',str(executable)],check=True,capture_output=True)
  elf=executable.read_bytes();u=Uc(UC_ARCH_ARM,UC_MODE_ARM);u.mem_map(0,0x100000);u.mem_map(0x10000000,0x10000);u.mem_map(0x20000000,0x2000)
  phoff=struct.unpack_from('<I',elf,28)[0];phsize,phcount=struct.unpack_from('<HH',elf,42)
  for i in range(phcount):
   row=struct.unpack_from('<8I',elf,phoff+i*phsize)
   if row[0]==1:u.mem_write(row[2],elf[row[1]:row[1]+row[4]])
  shoff=struct.unpack_from('<I',elf,32)[0];shsize,shcount=struct.unpack_from('<HH',elf,46);sections=[struct.unpack_from('<10I',elf,shoff+i*shsize) for i in range(shcount)];symbols={}
  for row in sections:
   if row[1]!=2:continue
   string_section=sections[row[6]];strings=elf[string_section[4]:string_section[4]+string_section[5]]
   for i in range(row[4],row[4]+row[5],16):
    name,value,size,info,other,section=struct.unpack_from('<IIIBBH',elf,i)
    if section:symbols[strings[name:].split(b'\0',1)[0].decode()]=value
  calls=[]
  def syscall(m,interrupt,_):
   number=m.reg_read(UC_ARM_REG_R7);args=[m.reg_read(r) for r in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5)];calls.append((number,args))
   if number==5:result=10+sum(n==5 for n,a in calls)-1
   elif number==192:
    result=0x20000000
    if args[2]==1:
     m.mem_write(result,bytes(8192));m.mem_write(result+0xcf8,b'ROM!')
   elif number in (6,91):result=0
   else:raise AssertionError(f'unexpected syscall {number}')
   m.reg_write(UC_ARM_REG_R0,result)
  u.hook_add(UC_HOOK_INTR,syscall)
  def run(address,*args):
   u.reg_write(UC_ARM_REG_SP,0x1000f000);u.reg_write(UC_ARM_REG_LR,0x80000)
   for r,v in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3),args):u.reg_write(r,v)
   u.emu_start(address,0x80000,count=100000);return u.reg_read(UC_ARM_REG_R0)
  device,io,buffer=0x10000000,0x10000100,0x10000200
  self.assertEqual(run(symbols['m10v_linux_devmem_open'],device,io,0x70000),1)
  self.assertEqual([a[1] for n,a in calls if n==5],[0x101000,0x101002])
  ctx,read,write,bind,clock=struct.unpack('<5I',u.mem_read(io,20));self.assertEqual(ctx,device)
  self.assertEqual(run(read,ctx,0x5316fcf8,buffer,4),1);self.assertEqual(bytes(u.mem_read(buffer,4)),b'ROM!')
  mmap_args=[a for n,a in calls if n==192][-1];self.assertEqual(mmap_args[2:],[1,1,10,0x5316f])
  self.assertEqual(run(bind,ctx,0x56010100,1152),1)
  before=len(calls);self.assertEqual(run(write,ctx,0x56010080,buffer,4),0);self.assertEqual(len(calls),before)
  u.mem_write(buffer,b'REQ!');self.assertEqual(run(write,ctx,0x56010100,buffer,4),1)
  self.assertEqual(bytes(u.mem_read(0x20000100,4)),b'REQ!');mmap_args=[a for n,a in calls if n==192][-1];self.assertEqual(mmap_args[2:],[3,1,11,0x56010])
  before=len(calls);self.assertEqual(run(write,ctx,0x5601057f,buffer,2),0);self.assertEqual(len(calls),before)
  run(symbols['m10v_linux_devmem_close'],device);self.assertEqual([a[0] for n,a in calls if n==6],[10,11])
if __name__=='__main__':unittest.main()
