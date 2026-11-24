#include "linux_target.h"
#include "../gr3/m10v_companion_owner.h"
#if M10V_ROLL_LINUX_SERVICE
#include "linux_io.h"
#include "linux_roll.h"
#endif
#if M10V_COMPANION_LIVE_SOURCE
#include "linux_live.h"
#endif
#include <stddef.h>
_Static_assert(sizeof(m10v_resident_wire)==2432,"resident wire ABI");
_Static_assert(sizeof(m10v_companion_result)==584,"owner result ABI");
_Static_assert(sizeof(m10v_companion_patch)==732,"owner patch ABI");
/* One bounded page, retained with the service process, allocated only when a
 * caller leaves a completed read behind. Keep it outside the static HTTP arena. */
struct m10v_linux_read_cache {
 m10v_companion_result film;
 m10v_extension_result extension;
};
_Static_assert(sizeof(struct m10v_linux_read_cache)<=4096,"bounded read cache page");
#if defined(M10V_COMPANION_HOST_TEST)
#include <stdlib.h>
static struct m10v_linux_read_cache *allocate_reads(void){
 return calloc(1,sizeof(struct m10v_linux_read_cache));
}
#else
static struct m10v_linux_read_cache *allocate_reads(void){
 register unsigned r0 __asm__("r0")=0,r1 __asm__("r1")=4096,r2 __asm__("r2")=3,
  r3 __asm__("r3")=0x22,r4 __asm__("r4")=~0u,r5 __asm__("r5")=0,r7 __asm__("r7")=192;
 __asm__ volatile("svc 0":"+r"(r0):"r"(r1),"r"(r2),"r"(r3),"r"(r4),"r"(r5),"r"(r7):"memory","cc");
 return r0>=0xfffff001u?0:(void *)(uintptr_t)r0;
}
#endif
static void clear(void*p,uint32_t n){for(uint32_t i=0;i<n;i++)((uint8_t*)p)[i]=0;}
static void copy(void*d,const void*s,uint32_t n){for(uint32_t i=0;i<n;i++)((uint8_t*)d)[i]=((const uint8_t*)s)[i];}
static int equal(const void*a,const void*b,uint32_t n){return m10v_constant_equal(a,b,n);}
static int nonzero(const uint8_t*p,uint32_t n){uint8_t v=0;for(uint32_t i=0;i<n;i++)v|=p[i];return v!=0;}
static int ram(uint32_t p,uint32_t n){return n&&n<=0x60000000u-0x55804374u&&p>=0x55804374u&&p<=0x60000000u-n;}
static int read_mem(m10v_linux_target*t,uint32_t p,void*out,uint32_t n){return t->io.read(t->io.ctx,p,out,n);}
static int fail(m10v_linux_target*t){t->failed=1;t->ready=0;return M10V_ERROR_BRIDGE_UNAVAILABLE;}
static int discover(m10v_linux_target*t,int initial){
 uint32_t guard,owner,again;uint8_t head[128],verify[128];m10v_companion_ui_descriptor d,e;
 t->probe_phase=2;
 if(!read_mem(t,0x55063910u,&guard,4)||!(guard&1u)||!read_mem(t,0x55063988u,&owner,4)||!ram(owner,0x6440u)||(owner&3u))return fail(t);
 t->probe_phase=3;
 if(!read_mem(t,owner+0x6400u,&d,sizeof(d))||d.magic!=M10V_COMPANION_DESCRIPTOR_MAGIC||d.version!=2||d.bytes!=64||d.wire_bytes!=sizeof(m10v_resident_wire)||!ram(d.context,128+sizeof(m10v_resident_wire))||(d.context&127u)||d.wire!=d.context+128u||d.epoch!=d.context)return fail(t);
 for(unsigned i=0;i<9;i++)if(d.reserved[i])return fail(t);
 t->probe_phase=4;
 if(!read_mem(t,d.wire,head,128))return fail(t);
 uint32_t words[6];copy(words,head,24);
 if(words[0]!=M10V_RESIDENT_MAGIC||words[1]!=2||words[2]!=sizeof(m10v_resident_wire)||words[3]!=1||words[4]!=owner||words[5]!=d.epoch||!equal(head+24,t->config.build,32))return fail(t);
 t->probe_phase=5;
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
 t->probe_phase=1;
 for(unsigned i=0;i<4;i++)if(!nonzero(c->rom[i],16)||!read_mem(t,addresses[i],bytes,16)||!equal(bytes,c->rom[i],16))return fail(t);
 if(discover(t,1))return M10V_ERROR_BRIDGE_UNAVAILABLE;
 t->probe_phase=6;
 uint32_t a,b;if(!read_mem(t,t->wire+128,&a,4)||!read_mem(t,t->wire+128+sizeof(m10v_resident_message),&b,4)||a||b)return fail(t);
 t->probe_phase=7;
 if(!t->io.bind_request(t->io.ctx,t->wire+128,sizeof(m10v_resident_message)))return fail(t);
 return 0;
}
#if M10V_COMPANION_DIAGNOSTICS && M10V_ROLL_LINUX_SERVICE
static void roll_log(const char *, const uint32_t *, unsigned);
static int trace_command(uint32_t command) {
 return command==1 || command==2 || command==5
#if M10V_COMPANION_LIVE_SOURCE
  || command==M10V_LIVE_DESCRIBE_COMMAND
#endif
  ;
}
#endif
static int publish(m10v_linux_target*t,uint32_t command,const void*data,uint32_t bytes){
 if(t->failed||t->pending_command||bytes>M10V_RESIDENT_PAYLOAD||t->sequence>0xfffffffcu)return fail(t);
#if M10V_COMPANION_DIAGNOSTICS && M10V_ROLL_LINUX_SERVICE
 if(command==1)roll_log("HELLO_DISCOVER_BEGIN",0,0);
#endif
 if(discover(t,0))return fail(t);
#if M10V_COMPANION_DIAGNOSTICS && M10V_ROLL_LINUX_SERVICE
 if(command==1)roll_log("HELLO_DISCOVER_OK",0,0);
#endif
#if M10V_COMPANION_DIAGNOSTICS && M10V_ROLL_LINUX_SERVICE
 if(command==1)roll_log("HELLO_CLEAR_BEGIN",(uint32_t[]){(uint32_t)(uintptr_t)&t->scratch,sizeof(t->scratch)},2);
#endif
 clear(&t->scratch,sizeof(t->scratch));uint32_t seq=t->sequence+2;
#if M10V_COMPANION_DIAGNOSTICS && M10V_ROLL_LINUX_SERVICE
 if(command==1)roll_log("HELLO_CLEAR_OK",0,0);
#endif
 t->scratch.sequence=seq;t->scratch.command=command;t->scratch.bytes=bytes;
#if M10V_COMPANION_DIAGNOSTICS && M10V_ROLL_LINUX_SERVICE
 if(command==1)roll_log("HELLO_COPY_BEGIN",(uint32_t[]){(uint32_t)(uintptr_t)data,bytes},2);
#endif
 if(bytes)copy(t->scratch.payload,data,bytes);
#if M10V_COMPANION_DIAGNOSTICS && M10V_ROLL_LINUX_SERVICE
 if(command==1)roll_log("HELLO_COPY_OK",0,0);
 if(command==1)roll_log("HELLO_CRC_BEGIN",(uint32_t[]){seq,t->scratch.command,t->scratch.bytes},3);
#endif
 t->scratch.crc=m10v_resident_crc(&t->scratch,seq);
#if M10V_COMPANION_DIAGNOSTICS && M10V_ROLL_LINUX_SERVICE
 if(command==1)roll_log("HELLO_CRC_OK",(uint32_t[]){t->scratch.crc},1);
#endif
 t->pending_crc=t->scratch.crc;t->pending_command=command;t->sequence=seq;
#if M10V_COMPANION_DIAGNOSTICS && M10V_ROLL_LINUX_SERVICE
 if(command==1)roll_log("HELLO_CLOCK_BEGIN",(uint32_t[]){t->scratch.crc},1);
#endif
 t->pending_since=t->io.now_ms(t->io.ctx);
#if M10V_COMPANION_DIAGNOSTICS && M10V_ROLL_LINUX_SERVICE
 if(command==1)roll_log("HELLO_CLOCK_OK",(uint32_t[]){(uint32_t)t->pending_since,(uint32_t)(t->pending_since>>32)},2);
#endif
 /* Publish odd first, complete body second, even last. A failed syscall can
  * have written bytes: poison this adapter; never replay an uncertain APPLY. */
 uint32_t odd=seq|1u,request=t->wire+128;
#if M10V_COMPANION_DIAGNOSTICS && M10V_ROLL_LINUX_SERVICE
 if(trace_command(command))roll_log("OWNER_REQUEST_BEGIN",(uint32_t[]){command,seq},2);
#endif

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
#if M10V_COMPANION_DIAGNOSTICS && M10V_ROLL_LINUX_SERVICE
 if(trace_command(t->pending_command))
  roll_log("OWNER_REPLY",(uint32_t[]){t->pending_command,t->sequence,t->scratch.code},3);
#endif
 return 0;
}
int m10v_linux_target_hello(m10v_linux_target*t){
 if(!t||t->failed)return M10V_ERROR_BRIDGE_UNAVAILABLE;if(t->ready)return discover(t,0);
 if(!t->pending_command){if(publish(t,1,t->config.nonce,16))return M10V_ERROR_BRIDGE_UNAVAILABLE;return M10V_ERROR_BUSY;}
 if(t->pending_command!=1)return fail(t);int result=receive(t);if(result)return result>0?M10V_ERROR_BUSY:M10V_ERROR_BRIDGE_UNAVAILABLE;
 if(t->scratch.code||t->scratch.bytes!=48||!equal(t->scratch.payload,t->config.nonce,16)||!equal(t->scratch.payload+16,t->config.build,32))return fail(t);
 t->pending_command=0;t->ready=1;return 0;
}
#if M10V_ROLL_LINUX_SERVICE
static void roll_log(const char *event, const uint32_t *values, unsigned count) {
#if !M10V_COMPANION_DIAGNOSTICS
 (void)event; (void)values; (void)count;
#else
 m10v_linux_trace(event, values, count);
#endif
}

static int roll_exchange(m10v_linux_target *t, uint32_t command, const void *data, uint32_t size) {
 if(publish(t,command,data,size))return 0;
 while(1){
  int result=receive(t);
  if(result==0){t->pending_command=0;return 1;}
  if(result<0||!m10v_linux_pause_ms(25)){fail(t);return 0;}
 }
}
#if M10V_COMPANION_LIVE_SOURCE
static void tick_live(m10v_linux_target *t, uint64_t now) {
 static uint64_t next;
 static uint32_t attached;
 static uint32_t heartbeat_status=0xffffffffu;
 if(attached)m10v_linux_live_sample(t,now);
 if(now<next||t->pending_command)return;
 next=now+1600;
 if(!attached){
  m10v_live_ingress_offer offer;
  if(!roll_exchange(t,M10V_LIVE_DESCRIBE_COMMAND,0,0)||t->scratch.code||
     t->scratch.bytes!=sizeof(offer))return;
  copy(&offer,t->scratch.payload,sizeof(offer));
  if(!m10v_linux_live_attach(&offer,t->epoch))return;
  m10v_linux_devmem *mem=t->io.ctx;
  mem->live=offer.address;
  mem->live_bytes=offer.bytes;
  attached=1;
  roll_log("LIVE_ARENA_OK",0,0);
 }
 uint32_t epoch=t->epoch;
 uint32_t status=roll_exchange(t,M10V_LIVE_HEARTBEAT_COMMAND,&epoch,sizeof(epoch))?
  t->scratch.code:0xffffffffu;
 if(status!=heartbeat_status||status){
  roll_log("LIVE_HEARTBEAT",(uint32_t[]){status,(uint32_t)now},2);
  heartbeat_status=status;
 }
}
#endif
void m10v_linux_target_roll_tick(m10v_linux_target *t, uint8_t *workspace){
 static uint64_t next;
 static uint32_t attempted_ticket, next_diagnostic, last_still, last_frames;
#if M10V_COMPANION_DIAGNOSTICS
 static uint32_t last_review_state, last_jpeg_returns, last_handoff[M10V_REVIEW_HANDOFF_STAGES];
#endif
 static unsigned attempts;
 if(!t||!t->ready||t->failed)return;
 m10v_linux_target_idle(t);
 if(t->failed||t->pending_command)return;
 uint64_t now=m10v_linux_now_ms(0);if(!now)return;
#if M10V_COMPANION_LIVE_SOURCE
 tick_live(t,now);
 if(t->failed||t->pending_command)return;
#endif
 if(now<next)return;
 next=now+500;
 if(!roll_exchange(t,M10V_ROLL_RECOVERY_NEEDED,0,0)||t->scratch.code)return;
 if(t->scratch.bytes==5+sizeof(m10v_roll_diagnostic)||
    t->scratch.bytes==5+sizeof(m10v_roll_diagnostic)+sizeof(m10v_review_diagnostic)||
    t->scratch.bytes==5+sizeof(m10v_roll_diagnostic)+sizeof(m10v_review_diagnostic)+sizeof(m10v_review_handoff)){
  m10v_roll_diagnostic diag;
  copy(&diag,t->scratch.payload+5,sizeof(diag));
  uint32_t time=(uint32_t)now;
  int emitted=0;
  if(diag.version==M10V_ROLL_DIAGNOSTIC_VERSION&&
     (!next_diagnostic||(int32_t)(time-next_diagnostic)>=0||
      diag.still_producer!=last_still||diag.confirmed_frames!=last_frames)){
   uint32_t values[1+sizeof(diag)/sizeof(uint32_t)];
   values[0]=time;copy(values+1,&diag,sizeof(diag));
   roll_log("ROLL_DIAG",values,sizeof(values)/sizeof(values[0]));
   emitted=1;
   next_diagnostic=time+5000;last_still=diag.still_producer;last_frames=diag.confirmed_frames;
  }
#if M10V_COMPANION_DIAGNOSTICS
  if(t->scratch.bytes==5+sizeof(diag)+sizeof(m10v_review_diagnostic)||
     t->scratch.bytes==5+sizeof(diag)+sizeof(m10v_review_diagnostic)+sizeof(m10v_review_handoff)){
   m10v_review_diagnostic review;
   copy(&review,t->scratch.payload+5+sizeof(diag),sizeof(review));
   if(review.magic==M10V_REVIEW_DIAGNOSTIC_MAGIC&&
      (emitted||review.quick_state!=last_review_state||review.jpeg_returns!=last_jpeg_returns)){
    uint32_t values[1+sizeof(review)/sizeof(uint32_t)];
    values[0]=time;copy(values+1,&review,sizeof(review));
    roll_log("R20_REVIEW",values,sizeof(values)/sizeof(values[0]));
    last_review_state=review.quick_state;last_jpeg_returns=review.jpeg_returns;
   }
  }
  if(t->scratch.bytes==5+sizeof(diag)+sizeof(m10v_review_diagnostic)+sizeof(m10v_review_handoff)){
   const uint8_t *h=t->scratch.payload+5+sizeof(diag)+sizeof(m10v_review_diagnostic);
   uint32_t magic;copy(&magic,h,4);
   if(magic==M10V_REVIEW_HANDOFF_MAGIC)for(uint32_t i=0;i<M10V_REVIEW_HANDOFF_STAGES;i++){
    uint32_t values[12];values[0]=time;values[1]=i+1u;
    copy(values+2,h+4u+i*40u,40u);
    if(!(values[2]&1u)&&values[2]&&(emitted||values[2]!=last_handoff[i])){
     roll_log("R20_STAGE",values,12);
     last_handoff[i]=values[2];
     if(!i){
      copy(values+1,h+offsetof(m10v_review_handoff,bank),28u);
      roll_log("R20_BANK",values,8);
     }
    }
   }
  }
#else
  (void)emitted;
#endif
 }else if(t->scratch.bytes!=5)return;
 if(t->scratch.payload[0]!=1)return;
 uint32_t ticket;copy(&ticket,t->scratch.payload+1,sizeof(ticket));
 if(ticket!=attempted_ticket){attempted_ticket=ticket;attempts=0;}
 m10v_roll_recovery proof;
 int scanned=m10v_linux_roll_scan(&proof,workspace);
 int received=scanned&&roll_exchange(t,M10V_ROLL_RECOVERY_COMMAND,&proof,sizeof(proof));
 uint32_t status=received?(uint32_t)t->scratch.code:UINT32_MAX;
 const uint32_t evidence[]={ (uint32_t)now,ticket,(uint32_t)scanned,status,
  (uint32_t)proof.pages[0],(uint32_t)proof.pages[1],proof.records[0].sequence,
  proof.records[1].sequence,proof.found[0][0],proof.found[0][1],proof.found[1][0],proof.found[1][1] };
 roll_log("ROLL_SD",evidence,sizeof(evidence)/sizeof(evidence[0]));
 if(received&&!status)attempts=0;
 else if(++attempts>=(ticket?4u:12u)) {
  int aborted=roll_exchange(t,M10V_ROLL_RECOVERY_ABORT,&ticket,sizeof(ticket));
  const uint32_t result[]={(uint32_t)now,ticket,attempts,aborted?(uint32_t)t->scratch.code:UINT32_MAX};
  roll_log("ROLL_STOP",result,sizeof(result)/sizeof(result[0]));
 }
 next=m10v_linux_now_ms(0)+1500;
}
#endif
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
static int film_exchange(m10v_linux_target*t,const m10v_backend_request*r,m10v_backend_response*out){
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
int m10v_linux_target_exchange(void*v,const m10v_backend_request*r,m10v_backend_response*out){
 m10v_linux_target*t=v;if(!out)return M10V_ERROR_BRIDGE_UNAVAILABLE;out->has_snapshot=0;out->status=M10V_OPERATION_UNKNOWN;
 if(!t||!r||t->failed||!t->ready)return M10V_ERROR_BRIDGE_UNAVAILABLE;
 unsigned read_state=r->command==M10V_BACKEND_READ_STATE;
 unsigned read_extensions=r->command==M10V_BACKEND_READ_EXTENSIONS;
 if((read_state&&t->pending_command==5)||(read_extensions&&t->pending_command==2)){
  m10v_linux_target_idle(t);
  if(t->failed)return M10V_ERROR_BRIDGE_UNAVAILABLE;
 }
 if((read_state&&t->read_cached)||(read_extensions&&t->extension_cached)){
  if(discover(t,0))return M10V_ERROR_BRIDGE_UNAVAILABLE;
  if(!out->snapshot)return M10V_ERROR_BRIDGE_UNAVAILABLE;
  if(read_state){
   m10v_companion_result*cached=&t->reads->film;
   out->status=cached->status;out->has_snapshot=cached->has_snapshot;
   if(cached->has_snapshot)copy(out->snapshot,&cached->snapshot,sizeof(cached->snapshot));
   t->read_cached=0;return (int)cached->code;
  }
  m10v_extension_result*cached=&t->reads->extension;
  out->status=cached->status;out->has_snapshot=cached->has_snapshot;
  if(cached->has_snapshot)copy(out->snapshot,&cached->snapshot,sizeof(cached->snapshot));
  t->extension_cached=0;return (int)cached->code;
 }
 if(r->command==M10V_BACKEND_SUBMIT||r->command==M10V_BACKEND_SUBMIT_EXTENSIONS)
  t->read_cached=t->extension_cached=0;
 if(r->command>=M10V_BACKEND_READ_EXTENSIONS&&r->command<=M10V_BACKEND_POLL_EXTENSIONS)return extension_exchange(t,r,out);
 return film_exchange(t,r,out);
}
void m10v_linux_target_idle(m10v_linux_target*t){
 if(!t||t->failed||!t->ready)return;
 uint32_t pending=t->pending_command;
 if(pending!=2&&pending!=5)return;
 if(!t->reads){t->reads=allocate_reads();if(!t->reads){fail(t);return;}}
 m10v_backend_request request={.command=pending==2?M10V_BACKEND_READ_STATE:M10V_BACKEND_READ_EXTENSIONS};
 m10v_backend_response response={M10V_OPERATION_UNKNOWN,0,
  pending==2?(void*)&t->reads->film.snapshot:(void*)&t->reads->extension.snapshot};
 int code=pending==2?film_exchange(t,&request,&response):extension_exchange(t,&request,&response);
 if(t->failed||t->pending_command)return;
 if(pending==2){
  t->reads->film.status=response.status;t->reads->film.code=(uint32_t)code;
  t->reads->film.has_snapshot=response.has_snapshot;t->read_cached=1;
 }else{
  t->reads->extension.status=response.status;t->reads->extension.code=(uint32_t)code;
  t->reads->extension.has_snapshot=response.has_snapshot;t->extension_cached=1;
 }
}
#if defined(__arm__) && !defined(M10V_COMPANION_HOST_TEST)
static long call6(unsigned n,unsigned a,unsigned b,unsigned c,unsigned d,unsigned e,unsigned f){register unsigned r0 __asm__("r0")=a,r1 __asm__("r1")=b,r2 __asm__("r2")=c,r3 __asm__("r3")=d,r4 __asm__("r4")=e,r5 __asm__("r5")=f,r7 __asm__("r7")=n;__asm__ volatile("svc 0":"+r"(r0):"r"(r1),"r"(r2),"r"(r3),"r"(r4),"r"(r5),"r"(r7):"memory","cc");return (long)r0;}
static int transfer(m10v_linux_devmem*d,uint32_t address,void*buffer,uint32_t n,int write){
 if(!n||address>0xffffffffu-n)return 0;
#if M10V_COMPANION_LIVE_SOURCE
 if(n>1152&&(write||n!=M10V_LIVE_INGRESS_FRAME_BYTES||!d->live_bytes||
     address<d->live||address+n>d->live+d->live_bytes))return 0;
#else
 if(n>1152)return 0;
#endif
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
 if(!d||!io||!now)return 0;d->request=d->request_bytes=d->live=d->live_bytes=0;d->read_fd=d->write_fd=-1;
 long fd=call6(5,(unsigned)(uintptr_t)"/dev/mem",0x101000u,0,0,0,0);if(fd<0)return 0;d->read_fd=(int)fd;
 fd=call6(5,(unsigned)(uintptr_t)"/dev/mem",0x101002u,0,0,0,0);if(fd<0){m10v_linux_devmem_close(d);return 0;}d->write_fd=(int)fd;
 *io=(m10v_linux_target_transport){d,physical_read,physical_write,bind,now};return 1;
}
void m10v_linux_devmem_close(m10v_linux_devmem*d){if(!d)return;if(d->read_fd>=0)call6(6,(unsigned)d->read_fd,0,0,0,0,0);if(d->write_fd>=0)call6(6,(unsigned)d->write_fd,0,0,0,0,0);d->read_fd=d->write_fd=-1;d->request=d->request_bytes=d->live=d->live_bytes=0;}
#else
int m10v_linux_devmem_open(m10v_linux_devmem*d,m10v_linux_target_transport*io,uint64_t(*now)(void*)){(void)d;(void)io;(void)now;return 0;}
void m10v_linux_devmem_close(m10v_linux_devmem*d){(void)d;}
#endif
