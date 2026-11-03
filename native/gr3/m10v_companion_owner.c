/* All entry points run on the native AppMain owner. Linux never calls them.
 * One dedicated allocation is retained until poweroff: a dead owner cancels
 * polling but cannot make a stale Linux producer write into reused heap. */
#include "m10v_companion_owner.h"
#include "m10v_library.h"
#include "m10v_tone.h"
#include "m10v_sd_library.h"
#include "../companion/resident_bridge.h"
#include "../companion/transaction.h"
#include "../companion/auth.h"
#include "../companion/extensions.h"
#include <stddef.h>
#if !M10V_COMPANION_ENABLED || !M10V_LIVE_COLOR || !M10V_APPENDED_SLOTS
#error Companion owner requires explicit opt-in, live cache and ten appended slots
#endif
#ifndef M10V_COMPANION_BUILD_BYTES
#error Companion build and catalog identities must be generated
#endif
typedef uint32_t (*fn1)(uint32_t);
typedef uint32_t (*fn2)(uint32_t,uint32_t);
typedef uint32_t (*fn3)(uint32_t,uint32_t,uint32_t);
typedef void (*cache_fn)(void*,uint32_t);
typedef struct {
 uint32_t vtable,ui_owner,timer_id,session_bound,vtable_words[3],locked,store_depth,store_generation;
 _Alignas(128) m10v_resident_wire wire;
 m10v_resident_consumer consumer;
 m10v_companion_owner transaction;
 m10v_extension_owner extensions;
 m10v_companion_owner_services services;
 m10v_companion_snapshot base;
} ui_context;
_Static_assert(sizeof(ui_context)<16384,"bounded permanent owner allocation");
_Static_assert(sizeof(m10v_companion_result)<=M10V_RESIDENT_PAYLOAD,"result fits mailbox");
_Static_assert(sizeof(m10v_companion_patch)<=M10V_RESIDENT_PAYLOAD,"patch fits mailbox");
static void zero(void*p,uint32_t n){for(uint32_t i=0;i<n;i++)((uint8_t*)p)[i]=0;}
static void copy(void*d,const void*s,uint32_t n){for(uint32_t i=0;i<n;i++)((uint8_t*)d)[i]=((const uint8_t*)s)[i];}
static int ram(uint32_t p,uint32_t n){return !(p&3u)&&p>=0x55804374u&&p<=0x60000000u-n;}
static m10v_companion_ui_descriptor*descriptor(uint32_t owner){
 if(!ram(owner,M10V_COMPANION_DESCRIPTOR_OFFSET+M10V_COMPANION_DESCRIPTOR_BYTES))return 0;
 return (void*)(uintptr_t)(owner+M10V_COMPANION_DESCRIPTOR_OFFSET);
}
static ui_context*context(uint32_t owner){
 m10v_companion_ui_descriptor*d=descriptor(owner);
 if(!d||d->magic!=M10V_COMPANION_DESCRIPTOR_MAGIC||d->version!=2||d->bytes!=sizeof(*d)||!ram(d->context,sizeof(ui_context))||(d->context&127u))return 0;
 ui_context*c=(void*)(uintptr_t)d->context;
 return d->wire==(uint32_t)(uintptr_t)&c->wire&&c->ui_owner==owner?c:0;
}
static int current(void*v){
 ui_context*c=v;
 return c->wire.alive==1&&c->ui_owner&&(*(const volatile uint32_t*)0x55063910u&1u)&&*(const volatile uint32_t*)0x55063988u==c->ui_owner&&context(c->ui_owner)==c;
}
uint32_t m10v_companion_ui_storage_enter(uint32_t remote){
 ui_context*c=0;
 if(*(const volatile uint32_t*)0x55063910u&1u)c=context(*(const volatile uint32_t*)0x55063988u);
 if(!c)return remote?0:1;
 if(!remote&&(c->extensions.pending.present||c->transaction.pending.present))return 0;
 if(c->store_generation==0xffffffffu||c->store_depth||(remote?!c->locked:c->locked))return 0;
 if(remote&&!current(c))return 0;
 c->store_depth=1;c->store_generation++;return (uint32_t)(uintptr_t)c;
}
uint32_t m10v_companion_ui_storage_current(uint32_t token){
 if(token==1)return 1;
 if(!ram(token,sizeof(ui_context))||(token&127u))return 0;
 ui_context*c=(void*)(uintptr_t)token;
 return c->wire.magic==M10V_RESIDENT_MAGIC&&c->store_depth&&c->ui_owner&&(*(const volatile uint32_t*)0x55063910u&1u)&&*(const volatile uint32_t*)0x55063988u==c->ui_owner&&context(c->ui_owner)==c;
}
uint32_t m10v_companion_ui_storage_leave(uint32_t token){
 if(token==1)return 1;
 if(!ram(token,sizeof(ui_context))||(token&127u))return 0;
 ui_context*c=(void*)(uintptr_t)token;
 if(c->wire.magic!=M10V_RESIDENT_MAGIC||!c->store_depth)return 0;
 uint32_t valid=m10v_companion_ui_storage_current(token);c->store_depth=0;return valid;
}
static int busy(void*v){
 (void)v;
 if(!(*(const volatile uint32_t*)0x55064398u&1u)||!(*(const volatile uint32_t*)0x55063eccu&1u))return 1;
 const volatile uint8_t*shoot=(const volatile uint8_t*)0x55067958u;
 return shoot[0x2c]||shoot[0x2d]||shoot[0x880]!=3||*(const volatile uint8_t*)(0x55063ddcu+0x27u);
}
static int enter(void*v){ui_context*c=v;if(c->locked||!current(c)||busy(c)||!m10v_camera_library_mutation_begin())return 0;c->locked=1;return 1;}
static void leave(void*v){
 ui_context*c=v;if(!c->locked)return;c->locked=0;
 if(current(c)){
  int loaded=m10v_camera_library_read_current(&c->base.state);
  if(current(c))m10v_camera_library_mutation_end(loaded==0?&c->base.state:0);
 }
}
static uint32_t model(void){
 if(!(*(const volatile uint32_t*)0x55063dccu&1u))return 0;
 uint32_t root=((uint32_t(*)(void))0x5320ad88u)();return ((fn1)0x5320ba9cu)(root);
}
static int active(void){uint32_t m=model();if(!m)return -1;if(((fn1)0x532bd6d4u)(m))return -1;uint32_t n=m10v_tone_slot(((fn1)0x532bd6b4u)(m));return n<M10V_SLOT_COUNT?(int)n:-1;}
static int snapshot(void*v,m10v_companion_snapshot*out){
 ui_context*c=v;if(!current(c))return M10V_ERROR_BRIDGE_UNAVAILABLE;
 if(c->store_depth||(!c->locked&&m10v_camera_library_mutation_busy()))return M10V_ERROR_BUSY;
 uint32_t generation=c->store_generation;
 zero(out,sizeof(*out));
 int loaded=m10v_camera_library_read_current(&out->state);
 if(!current(c))return M10V_ERROR_BRIDGE_UNAVAILABLE;
 if(generation!=c->store_generation||c->store_depth||(!c->locked&&m10v_camera_library_mutation_busy()))return M10V_ERROR_BUSY;
 if(loaded!=0)return M10V_ERROR_BRIDGE_UNAVAILABLE;
 out->active_slot=(int8_t)active();out->busy=(uint8_t)busy(c);
 uint8_t*record=0;int code=0;
 for(uint32_t i=0;i<M10V_SLOT_COUNT;i++)if(M10V_CUSTOM(out->state.slots[i].film)){
  if(!record)record=(void*)(uintptr_t)((fn1)0x536af2a8u)(M10V_SD_RECORD_BYTES);
  if(!record||!m10v_sd_camera_custom_record(&out->state,i,record,M10V_SD_RECORD_BYTES)||!current(c)){code=M10V_ERROR_BRIDGE_UNAVAILABLE;break;}
  m10v_sha256(record,M10V_SD_RECORD_BYTES,out->custom_hashes[i]);
 }
 if(record)((void(*)(void*))0x536af2e4u)(record);
 if(code||!current(c))return M10V_ERROR_BRIDGE_UNAVAILABLE;
 if(generation!=c->store_generation||c->store_depth||(!c->locked&&m10v_camera_library_mutation_busy())||active()!=out->active_slot)return M10V_ERROR_BUSY;
 return m10v_companion_snapshot_identity(&c->services.metadata,out);
}
static int persist(void*v,const m10v_library_state*state){
 ui_context*c=v;if(!current(c)||!c->locked||busy(c))return M10V_IO_NOT_WRITTEN;
 return m10v_camera_library_commit_snapshot(state)==0?M10V_IO_OK:M10V_IO_UNCERTAIN;
}
static int set_tone(void*v,unsigned slot){
 ui_context*c=v;if(!current(c)||!c->locked||busy(c)||slot>=M10V_SLOT_COUNT||!c->base.state.slots[slot].film)return M10V_IO_NOT_WRITTEN;
 uint32_t m=model();if(!m)return M10V_IO_NOT_WRITTEN;
 uint8_t*bytes=(void*)(uintptr_t)m;uint8_t prior=bytes[0x1b];bytes[0x1b]=0;
 ((fn2)0x532bd61cu)(m,0);((fn2)0x532c26c0u)(m,m10v_slot_tone(slot));bytes[0x1b]=prior;
 return current(c)&&active()==(int)slot?M10V_IO_OK:M10V_IO_UNCERTAIN;
}
static int cache_in(void*v,void*p,uint32_t n){ui_context*c=v;if(p!=&c->wire.request||n!=sizeof(c->wire.request))return 0;((cache_fn)0x5383c834u)(p,n);return 1;}
static int cache_out(void*v,void*p,uint32_t n){ui_context*c=v;if(p!=&c->wire.response||n>sizeof(c->wire.response))return 0;((cache_fn)0x5383c870u)(p,n);return 1;}
static int film_enter(void*v){ui_context*c=v;return !c->extensions.pending.present&&enter(v);}
#include "m10v_companion_extensions.inc"
static int execute(void*v,uint32_t command,const uint8_t*in,uint32_t bytes,uint8_t*out,uint32_t*length){
 ui_context*c=v;
 if(command==1){
  *length=0;if(bytes!=16||!current(c))return M10V_ERROR_BRIDGE_UNAVAILABLE;
  if(c->session_bound&&!m10v_constant_equal(c->services.metadata.boot_id,in,16))return M10V_ERROR_BRIDGE_UNAVAILABLE;
  copy(c->services.metadata.boot_id,in,16);c->session_bound=1;
  copy(out,in,16);copy(out+16,c->wire.build,32);*length=48;return 0;
 }
 if(command>=M10V_READ_EXTENSIONS&&command<=M10V_POLL_EXTENSIONS){
  *length=sizeof(m10v_extension_result);m10v_extension_result*r=(void*)out;zero(r,sizeof(*r));r->status=M10V_OPERATION_REJECTED;
  if(!c->session_bound||!current(c)){r->code=M10V_ERROR_BRIDGE_UNAVAILABLE;return (int)r->code;}
  m10v_extension_services s=extension_services(c);
  if(command==M10V_READ_EXTENSIONS&&!bytes){r->code=(uint32_t)extension_read(c,&r->snapshot);r->has_snapshot=!r->code;r->status=r->code?M10V_OPERATION_REJECTED:M10V_OPERATION_COMMITTED;return (int)r->code;}
  if(command==M10V_APPLY_EXTENSIONS&&bytes==sizeof(m10v_extension_patch))return m10v_extensions_apply((const void*)in,&s,r);
  if(command==M10V_POLL_EXTENSIONS&&bytes==16)return m10v_extensions_poll(in,&s,r);
  r->code=M10V_ERROR_INVALID_RECIPE;return (int)r->code;
 }
 *length=sizeof(m10v_companion_result);m10v_companion_result*r=(void*)out;zero(r,sizeof(*r));r->status=M10V_OPERATION_REJECTED;
 if(!c->session_bound||!current(c)){r->code=M10V_ERROR_BRIDGE_UNAVAILABLE;return (int)r->code;}
 if(command==2&&!bytes){r->code=(uint32_t)snapshot(c,&r->snapshot);r->has_snapshot=!r->code;r->status=r->code?M10V_OPERATION_REJECTED:M10V_OPERATION_COMMITTED;return (int)r->code;}
 if(command==3&&bytes==sizeof(m10v_companion_patch)){
  int code=snapshot(c,&c->base);if(code){r->code=(uint32_t)code;return code;}
  return m10v_companion_apply(&c->base,(const void*)in,&c->services,r);
 }
 if(command==4&&bytes==16)return m10v_companion_owner_poll(&c->services,in,r);
 r->code=M10V_ERROR_INVALID_RECIPE;return (int)r->code;
}
static uint32_t noop(uint32_t a,uint32_t b,uint32_t c){(void)a;(void)b;(void)c;return 0;}
void m10v_companion_ui_init(uint32_t owner){
 m10v_companion_ui_descriptor*d=descriptor(owner);if(!d)return;zero(d,sizeof(*d));
 uint32_t allocated=((fn1)0x536af2a8u)(sizeof(ui_context)+127u),address=(allocated+127u)&~127u;
 if(!allocated||allocated>0xffffffffu-127u||!ram(address,sizeof(ui_context)))return;
 ui_context*c=(void*)(uintptr_t)address;zero(c,sizeof(*c));c->ui_owner=owner;
 c->vtable_words[0]=c->vtable_words[1]=(uint32_t)(uintptr_t)noop;c->vtable_words[2]=(uint32_t)(uintptr_t)m10v_companion_ui_timer;c->vtable=(uint32_t)(uintptr_t)c->vtable_words;
 c->wire.magic=M10V_RESIDENT_MAGIC;c->wire.version=2;c->wire.bytes=sizeof(c->wire);c->wire.owner=owner;c->wire.epoch=address;c->services.metadata.owner_generation=address;
 const uint8_t build[32]=M10V_COMPANION_BUILD_BYTES,catalog[32]=M10V_COMPANION_CATALOG_BYTES,renderer[32]=M10V_COMPANION_RENDERER_BYTES;
 copy(c->wire.build,build,32);copy(c->services.metadata.build_id,build,32);copy(c->services.metadata.catalog_hash,catalog,32);copy(c->services.metadata.renderer_hash,renderer,32);
 c->services.ctx=c;c->services.owner=&c->transaction;c->services.is_current=current;c->services.enter=film_enter;c->services.leave=leave;c->services.is_busy=busy;c->services.snapshot=snapshot;c->services.persist_once=persist;c->services.set_tone=set_tone;
 ((cache_fn)0x5383c870u)(&c->wire,sizeof(c->wire));
 d->version=2;d->bytes=sizeof(*d);d->context=address;d->wire=(uint32_t)(uintptr_t)&c->wire;d->wire_bytes=sizeof(c->wire);d->epoch=address;d->magic=M10V_COMPANION_DESCRIPTOR_MAGIC;
 ((cache_fn)0x5383c870u)(d,sizeof(*d));
}
void m10v_companion_ui_start(uint32_t owner){
 ui_context*c=context(owner);if(!c||c->timer_id||!(*(const volatile uint32_t*)0x550645acu&1u))return;
 c->wire.alive=1;((cache_fn)0x5383c870u)(&c->wire,128);
 uint32_t root=((uint32_t(*)(void))0x5320ad88u)(),timer_model=((fn1)0x5320b01cu)(root);
 c->timer_id=((fn3)0x5322b468u)(timer_model,100,(uint32_t)(uintptr_t)c);
 if(!c->timer_id){c->wire.alive=0;((cache_fn)0x5383c870u)(&c->wire,128);}
}
uint32_t m10v_companion_ui_timer(uint32_t value,uint32_t timer,uint32_t ignored){
 (void)ignored;ui_context*c=(void*)(uintptr_t)value;
 if(!ram(value,sizeof(*c))||(value&127u)||c->timer_id!=timer||!current(c))return 0;
 c->timer_id=0;m10v_resident_ops ops={c,cache_in,cache_out,execute};
 (void)m10v_resident_consume(&c->wire,&c->consumer,&ops);
 if(current(c))m10v_companion_ui_start(c->ui_owner);return 0;
}
void m10v_companion_ui_stop(uint32_t owner){
 ui_context*c=context(owner);if(!c)return;
 c->wire.alive=0;((cache_fn)0x5383c870u)(&c->wire,128);
 uint32_t timer=c->timer_id;c->timer_id=0;
 if(timer&&(*(const volatile uint32_t*)0x550645acu&1u)){uint32_t root=((uint32_t(*)(void))0x5320ad88u)();((fn2)0x5322b1ecu)(((fn1)0x5320b01cu)(root),timer);}
 c->ui_owner=0;m10v_companion_ui_descriptor*d=descriptor(owner);d->magic=0;((cache_fn)0x5383c870u)(d,sizeof(*d));
 /* Do not free: a late Linux writer may still hold this bounded allocation. */
}
