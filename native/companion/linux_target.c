#include "linux_target.h"
#include "../gr3/m10v_companion_owner.h"
#include <stddef.h>
_Static_assert(sizeof(m10v_resident_wire)==2432,"resident wire ABI");
_Static_assert(sizeof(m10v_companion_result)==584,"owner result ABI");
_Static_assert(sizeof(m10v_companion_patch)==732,"owner patch ABI");
static void clear(void*p,uint32_t n){for(uint32_t i=0;i<n;i++)((uint8_t*)p)[i]=0;}
static void copy(void*d,const void*s,uint32_t n){for(uint32_t i=0;i<n;i++)((uint8_t*)d)[i]=((const uint8_t*)s)[i];}
static int equal(const void*a,const void*b,uint32_t n){return m10v_constant_equal(a,b,n);}
static int nonzero(const uint8_t*p,uint32_t n){uint8_t v=0;for(uint32_t i=0;i<n;i++)v|=p[i];return v!=0;}
static int ram(uint32_t p,uint32_t n){return n&&n<=0x60000000u-0x55804374u&&p>=0x55804374u&&p<=0x60000000u-n;}
static int read_mem(m10v_linux_target*t,uint32_t p,void*out,uint32_t n){return t->io.read(t->io.ctx,p,out,n);}
static int fail(m10v_linux_target*t){t->failed=1;t->ready=0;return M10V_ERROR_BRIDGE_UNAVAILABLE;}
static int discover(m10v_linux_target*t,int initial){
 uint32_t guard,owner,again;uint8_t head[128],verify[128];m10v_companion_ui_descriptor d,e;
 if(!read_mem(t,0x55063910u,&guard,4)||!(guard&1u)||!read_mem(t,0x55063988u,&owner,4)||!ram(owner,0x6440u)||(owner&3u))return fail(t);
 if(!read_mem(t,owner+0x6400u,&d,sizeof(d))||d.magic!=M10V_COMPANION_DESCRIPTOR_MAGIC||d.version!=2||d.bytes!=64||d.wire_bytes!=sizeof(m10v_resident_wire)||!ram(d.context,128+sizeof(m10v_resident_wire))||(d.context&127u)||d.wire!=d.context+128u||d.epoch!=d.context)return fail(t);
 for(unsigned i=0;i<9;i++)if(d.reserved[i])return fail(t);
 if(!read_mem(t,d.wire,head,128))return fail(t);
 uint32_t words[6];copy(words,head,24);
 if(words[0]!=M10V_RESIDENT_MAGIC||words[1]!=2||words[2]!=sizeof(m10v_resident_wire)||words[3]!=1||words[4]!=owner||words[5]!=d.epoch||!equal(head+24,t->config.build,32))return fail(t);
 if(!read_mem(t,0x55063988u,&again,4)||again!=owner||!read_mem(t,owner+0x6400u,&e,sizeof(e))||!equal(&d,&e,sizeof(d))||!read_mem(t,d.wire,verify,128)||!equal(head,verify,128)||!read_mem(t,0x55063910u,&guard,4)||!(guard&1u))return fail(t);
 if(!initial&&(owner!=t->owner||d.context!=t->context||d.wire!=t->wire||d.epoch!=t->epoch))return fail(t);
 if(initial){t->owner=owner;t->context=d.context;t->wire=d.wire;t->epoch=d.epoch;}
 return 0;
}
int m10v_linux_target_init(m10v_linux_target*t,const m10v_linux_target_config*c,const m10v_linux_target_transport*io){
 if(!t||!c||!io||!io->read||!io->write||!io->bind_request||!io->now_ms)return M10V_ERROR_BRIDGE_UNAVAILABLE;
 clear(t,sizeof(*t));copy(&t->config,c,sizeof(*c));copy(&t->io,io,sizeof(*io));
 if(!nonzero(c->build,32)||!nonzero(c->catalog,32)||!nonzero(c->renderer,32)||!nonzero(c->nonce,16)||c->timeout_ms<100||c->timeout_ms>60000)return fail(t);
 const uint32_t addresses[4]={0x5316fcf8u,0x5319667cu,0x5383c834u,0x5383c870u};uint8_t bytes[16];
 for(unsigned i=0;i<4;i++)if(!nonzero(c->rom[i],16)||!read_mem(t,addresses[i],bytes,16)||!equal(bytes,c->rom[i],16))return fail(t);
 if(discover(t,1))return M10V_ERROR_BRIDGE_UNAVAILABLE;
 uint32_t a,b;if(!read_mem(t,t->wire+128,&a,4)||!read_mem(t,t->wire+128+sizeof(m10v_resident_message),&b,4)||a||b)return fail(t);
 if(!t->io.bind_request(t->io.ctx,t->wire+128,sizeof(m10v_resident_message)))return fail(t);
 return 0;
}
static int publish(m10v_linux_target*t,uint32_t command,const void*data,uint32_t bytes){
 if(t->failed||t->pending_command||bytes>M10V_RESIDENT_PAYLOAD||t->sequence>0xfffffffcu||discover(t,0))return fail(t);
 clear(&t->scratch,sizeof(t->scratch));uint32_t seq=t->sequence+2;
 t->scratch.sequence=seq;t->scratch.command=command;t->scratch.bytes=bytes;if(bytes)copy(t->scratch.payload,data,bytes);
 t->scratch.crc=m10v_resident_crc(&t->scratch,seq);t->pending_crc=t->scratch.crc;t->pending_command=command;t->sequence=seq;t->pending_since=t->io.now_ms(t->io.ctx);
 /* Publish odd first, complete body second, even last. A failed syscall can
  * have written bytes: poison this adapter; never replay an uncertain APPLY. */
 uint32_t odd=seq|1u,request=t->wire+128;
 if(!t->io.write(t->io.ctx,request,&odd,4)||!t->io.write(t->io.ctx,request+4,(uint8_t*)&t->scratch+4,sizeof(t->scratch)-4)||!t->io.write(t->io.ctx,request,&seq,4))return fail(t);
 return 0;
}
/* 1=pending,0=stable correlated result,negative=poisoned transport. */
static int receive(m10v_linux_target*t){
 if(t->failed||!t->pending_command||discover(t,0))return -1;
 uint64_t now=t->io.now_ms(t->io.ctx);if(now<t->pending_since||now-t->pending_since>=t->config.timeout_ms){fail(t);return -1;}
 uint32_t address=t->wire+128+sizeof(m10v_resident_message),before,after;
 if(!read_mem(t,address,&before,4))return fail(t),-1;
 if(before!=t->sequence||(before&1u))return 1;
 if(!read_mem(t,address,&t->scratch,sizeof(t->scratch))||!read_mem(t,address,&after,4))return fail(t),-1;
 if(before!=after||t->scratch.sequence!=before)return 1;
 if(t->scratch.bytes>M10V_RESIDENT_PAYLOAD||t->scratch.command!=t->pending_command||t->scratch.correlation!=t->pending_crc||m10v_resident_crc(&t->scratch,before)!=t->scratch.crc)return fail(t),-1;
 if(discover(t,0))return -1;
 return 0;
}
int m10v_linux_target_hello(m10v_linux_target*t){
 if(!t||t->failed)return M10V_ERROR_BRIDGE_UNAVAILABLE;if(t->ready)return discover(t,0);
 if(!t->pending_command){if(publish(t,1,t->config.nonce,16))return M10V_ERROR_BRIDGE_UNAVAILABLE;return M10V_ERROR_BUSY;}
 if(t->pending_command!=1)return fail(t);int result=receive(t);if(result)return result>0?M10V_ERROR_BUSY:M10V_ERROR_BRIDGE_UNAVAILABLE;
 if(t->scratch.code||t->scratch.bytes!=48||!equal(t->scratch.payload,t->config.nonce,16)||!equal(t->scratch.payload+16,t->config.build,32))return fail(t);
 t->pending_command=0;t->ready=1;return 0;
}
static int identity(m10v_linux_target*t,const m10v_companion_snapshot*s){
 m10v_sha256_context hash;uint8_t config[32],revision[32],generation[4],sequence[4];
 const char prefix[]="m10v-config/v2",revision_prefix[]="m10v-revision/v2";
 m10v_sha256_init(&hash);m10v_sha256_update(&hash,(const uint8_t*)prefix,sizeof(prefix)-1);
 m10v_sha256_update(&hash,(const uint8_t*)&s->state+12,168);m10v_sha256_update(&hash,(const uint8_t*)s->custom_hashes,320);m10v_sha256_update(&hash,(const uint8_t*)&s->active_slot,1);m10v_sha256_finish(&hash,config);
 if(!equal(config,s->config_hash,32))return 0;
 for(unsigned i=0;i<4;i++){generation[i]=(uint8_t)(t->epoch>>(8*i));sequence[i]=(uint8_t)(s->state.sequence>>(8*i));}
 m10v_sha256_init(&hash);m10v_sha256_update(&hash,(const uint8_t*)revision_prefix,sizeof(revision_prefix)-1);
 m10v_sha256_update(&hash,t->config.nonce,16);m10v_sha256_update(&hash,t->config.build,32);m10v_sha256_update(&hash,t->config.catalog,32);m10v_sha256_update(&hash,t->config.renderer,32);m10v_sha256_update(&hash,config,32);m10v_sha256_update(&hash,sequence,4);m10v_sha256_update(&hash,generation,4);m10v_sha256_finish(&hash,revision);return equal(revision,s->revision,32);
}
static int extension_exchange(m10v_linux_target*t,const m10v_backend_request*r,m10v_backend_response*out){
 const m10v_extension_patch*p=(const void*)r->patch;unsigned read=r->command==M10V_BACKEND_READ_EXTENSIONS;
 if(!read&&!p)return M10V_ERROR_INVALID_RECIPE;
 if(r->command==M10V_BACKEND_SUBMIT_EXTENSIONS){uint8_t hash[32];m10v_unhex(M10V_EXTENSIONS_HASH,32,hash);if(!equal(p->boot_id,t->config.nonce,16))return M10V_ERROR_REVISION_CONFLICT;if(!equal(hash,p->contract_hash,32))return M10V_ERROR_INCOMPATIBLE_RENDERER;}
 if(t->pending_command&&t->pending_command<5)return M10V_ERROR_BUSY;
 if(!t->pending_command){unsigned command=read?5:r->command==M10V_BACKEND_SUBMIT_EXTENSIONS?6:7;if(!read)copy(t->pending_id,p->request_id,16);if(command==6)m10v_sha256((const uint8_t*)p,sizeof(*p),t->pending_digest);
  if(publish(t,command,read?0:command==6?(const void*)p:p->request_id,read?0:command==6?sizeof(*p):16))return M10V_ERROR_BRIDGE_UNAVAILABLE;out->status=M10V_OPERATION_APPLYING;return 0;}
 if((t->pending_command==5)!=read||(!read&&!equal(t->pending_id,p->request_id,16)))return M10V_ERROR_BUSY;
 if(t->pending_command==6&&r->command==M10V_BACKEND_SUBMIT_EXTENSIONS){uint8_t digest[32];m10v_sha256((const uint8_t*)p,sizeof(*p),digest);if(!equal(digest,t->pending_digest,32))return M10V_ERROR_INVALID_RECIPE;}
 int received=receive(t);if(received){if(received>0){out->status=M10V_OPERATION_APPLYING;return 0;}return M10V_ERROR_BRIDGE_UNAVAILABLE;}
 if(t->scratch.bytes!=sizeof(m10v_extension_result)||t->scratch.code>M10V_ERROR_RESULT_UNKNOWN)return fail(t);m10v_extension_result result;copy(&result,t->scratch.payload,sizeof(result));
 if(result.status>M10V_OPERATION_UNKNOWN||result.code!=t->scratch.code||result.has_snapshot>1||(result.has_snapshot&&(!out->snapshot||!m10v_extensions_valid(&result.snapshot)))||(result.status==M10V_OPERATION_COMMITTED&&!result.has_snapshot))return fail(t);
 if(result.has_snapshot)copy(out->snapshot,&result.snapshot,sizeof(result.snapshot));t->pending_command=0;out->status=result.status;out->has_snapshot=result.has_snapshot;return (int)result.code;
}
int m10v_linux_target_exchange(void*v,const m10v_backend_request*r,m10v_backend_response*out){
 m10v_linux_target*t=v;if(!out)return M10V_ERROR_BRIDGE_UNAVAILABLE;out->has_snapshot=0;out->status=M10V_OPERATION_UNKNOWN;
 if(!t||!r||t->failed||!t->ready)return M10V_ERROR_BRIDGE_UNAVAILABLE;
 if(r->command>=M10V_BACKEND_READ_EXTENSIONS&&r->command<=M10V_BACKEND_POLL_EXTENSIONS)return extension_exchange(t,r,out);
 if(r->command!=M10V_BACKEND_READ_STATE&&r->command!=M10V_BACKEND_SUBMIT&&r->command!=M10V_BACKEND_POLL)return M10V_ERROR_BRIDGE_UNAVAILABLE;
 if(t->pending_command>=5)return M10V_ERROR_BUSY;
 if(r->command!=M10V_BACKEND_READ_STATE&&!r->patch)return M10V_ERROR_INVALID_RECIPE;
 if(r->command==M10V_BACKEND_SUBMIT&&(!equal(r->patch->boot_id,t->config.nonce,16)||!equal(r->patch->catalog_hash,t->config.catalog,32)||!equal(r->patch->renderer_hash,t->config.renderer,32)))return M10V_ERROR_INCOMPATIBLE_RENDERER;
 if(!t->pending_command){
  unsigned command=r->command==M10V_BACKEND_READ_STATE?2:r->command==M10V_BACKEND_SUBMIT?3:4;
  if(command!=2)copy(t->pending_id,r->patch->request_id,16);
  if(command==3)m10v_sha256(r->patch,sizeof(*r->patch),t->pending_digest);
  if(publish(t,command,command==2?0:command==3?(const void*)r->patch:r->patch->request_id,command==2?0:command==3?sizeof(*r->patch):16))return M10V_ERROR_BRIDGE_UNAVAILABLE;
  out->status=M10V_OPERATION_APPLYING;return 0;
 }
 if((t->pending_command==2)!=(r->command==M10V_BACKEND_READ_STATE)|| (t->pending_command!=2&&!equal(t->pending_id,r->patch->request_id,16)))return M10V_ERROR_BUSY;
 if(t->pending_command==3&&r->command==M10V_BACKEND_SUBMIT){uint8_t digest[32];m10v_sha256(r->patch,sizeof(*r->patch),digest);if(!equal(digest,t->pending_digest,32))return M10V_ERROR_INVALID_RECIPE;}
 int received=receive(t);if(received){if(received>0){out->status=M10V_OPERATION_APPLYING;return 0;}return M10V_ERROR_BRIDGE_UNAVAILABLE;}
 if(t->scratch.bytes!=sizeof(m10v_companion_result)||t->scratch.code>M10V_ERROR_RESULT_UNKNOWN)return fail(t);
 m10v_companion_result result;copy(&result,t->scratch.payload,sizeof(result));
 if(result.status>M10V_OPERATION_UNKNOWN||result.has_snapshot>1||result.code!=t->scratch.code||(result.has_snapshot&&!out->snapshot))return fail(t);
 if(result.has_snapshot){uint32_t crc=~0u;const uint8_t*p=(const void*)&result.snapshot.state;for(uint32_t i=0;i<180;i++){crc^=p[i];for(unsigned j=0;j<8;j++)crc=(crc>>1)^(0xedb88320u&(0u-(crc&1u)));}
  if(result.snapshot.state.magic!=0x5630314du||result.snapshot.state.version!=5u||result.snapshot.state.size!=sizeof(m10v_library_state)||result.snapshot.state.crc!=~crc||result.snapshot.active_slot < -1||result.snapshot.active_slot>=10||result.snapshot.busy>1||!identity(t,&result.snapshot))return fail(t);
  copy(out->snapshot,&result.snapshot,sizeof(result.snapshot));
 }
 t->pending_command=0;out->status=result.status;out->has_snapshot=result.has_snapshot;return (int)result.code;
}
#if defined(__arm__) && !defined(M10V_COMPANION_HOST_TEST)
static long call6(unsigned n,unsigned a,unsigned b,unsigned c,unsigned d,unsigned e,unsigned f){register unsigned r0 __asm__("r0")=a,r1 __asm__("r1")=b,r2 __asm__("r2")=c,r3 __asm__("r3")=d,r4 __asm__("r4")=e,r5 __asm__("r5")=f,r7 __asm__("r7")=n;__asm__ volatile("svc 0":"+r"(r0):"r"(r1),"r"(r2),"r"(r3),"r"(r4),"r"(r5),"r"(r7):"memory","cc");return (long)r0;}
static int transfer(m10v_linux_devmem*d,uint32_t address,void*buffer,uint32_t n,int write){
 if(!n||n>1152||address>0xffffffffu-n)return 0;
 if(write&&(address<d->request||address+n>d->request+d->request_bytes))return 0;
 if(!write&&!((address>=0x53000000u&&address+n<=0x55000000u)||(address>=0x55000000u&&address+n<=0x60000000u)))return 0;
 uint32_t offset=address&4095u,length=(offset+n+4095u)&~4095u;
 long mapped=call6(192,0,length,write?3:1,1,(unsigned)(write?d->write_fd:d->read_fd),address>>12);
 if((uint32_t)mapped>=0xfffff001u)return 0;volatile uint8_t*p=(volatile uint8_t*)(uintptr_t)((uint32_t)mapped+offset);uint8_t*b=buffer;
 __asm__ volatile("dmb sy":::"memory");
 if(write){for(uint32_t i=0;i<n;i++)p[i]=b[i];}else{for(uint32_t i=0;i<n;i++)b[i]=p[i];}
 __asm__ volatile("dmb sy":::"memory");return call6(91,(unsigned)mapped,length,0,0,0,0)==0;
}
static int physical_read(void*v,uint32_t a,void*p,uint32_t n){return transfer(v,a,p,n,0);}
static int physical_write(void*v,uint32_t a,const void*p,uint32_t n){return transfer(v,a,(void*)p,n,1);}
static int bind(void*v,uint32_t a,uint32_t n){m10v_linux_devmem*d=v;if(d->request||!ram(a,n)||(a&127u)||n!=sizeof(m10v_resident_message))return 0;d->request=a;d->request_bytes=n;return 1;}
int m10v_linux_devmem_open(m10v_linux_devmem*d,m10v_linux_target_transport*io,uint64_t(*now)(void*)){
 if(!d||!io||!now)return 0;d->request=d->request_bytes=0;d->read_fd=d->write_fd=-1;
 long fd=call6(5,(unsigned)(uintptr_t)"/dev/mem",0x101000u,0,0,0,0);if(fd<0)return 0;d->read_fd=(int)fd;
 fd=call6(5,(unsigned)(uintptr_t)"/dev/mem",0x101002u,0,0,0,0);if(fd<0){m10v_linux_devmem_close(d);return 0;}d->write_fd=(int)fd;
 *io=(m10v_linux_target_transport){d,physical_read,physical_write,bind,now};return 1;
}
void m10v_linux_devmem_close(m10v_linux_devmem*d){if(!d)return;if(d->read_fd>=0)call6(6,(unsigned)d->read_fd,0,0,0,0,0);if(d->write_fd>=0)call6(6,(unsigned)d->write_fd,0,0,0,0,0);d->read_fd=d->write_fd=-1;d->request=d->request_bytes=0;}
#else
int m10v_linux_devmem_open(m10v_linux_devmem*d,m10v_linux_target_transport*io,uint64_t(*now)(void*)){(void)d;(void)io;(void)now;return 0;}
void m10v_linux_devmem_close(m10v_linux_devmem*d){(void)d;}
#endif
