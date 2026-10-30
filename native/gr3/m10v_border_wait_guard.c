#include "m10v_border_wait_guard.h"
_Static_assert(sizeof(m10v_border_fill_rectangle)==12,"native Fill params size");
_Static_assert(sizeof(m10v_border_fill_bundle)==12,"bundle header size");
_Static_assert(sizeof(m10v_border_native_client)==76,"private client ABI size");
#ifndef M10V_BORDER_TRACE_LOG
#define M10V_BORDER_TRACE_LOG 0u
#endif
#if M10V_BORDER_TRACE_LOG
#define TRACE(p,a,b,c) ((void)((int(*)(uint32_t,uint32_t,uint32_t,uint32_t,uint32_t))M10V_BORDER_TRACE_LOG)(224u,(p),(a),(b),(c)))
#else
#define TRACE(p,a,b,c) ((void)0)
#endif
#define TAIL_TAG 0x42575431u
#define U(p) ((uint32_t)(uintptr_t)(p))
typedef struct {uint32_t tag,client,job,active;} transfer_tail;
static void barrier(void){__asm__ volatile("dmb ish" ::: "memory");}
static uint32_t native_wait(void *event,uint32_t mask,uint32_t *bits,uint32_t timeout){
 return ((uint32_t(*)(void*,uint32_t,uint32_t*,uint32_t))0x536a9e8cu)(event,mask,bits,timeout);
}
static void yield(void){((void(*)(uint32_t))0x536b0a74u)(1);}
static const uint32_t client_vtable[]={0x534ac164u,0x534ac18cu,(uint32_t)(uintptr_t)m10v_border_client_notify,0};
/* Read only the original object's first word until private vtable identity
 * proves that appended client fields exist. Caller still owns valid object. */
static int owned(m10v_border_native_client *c){return c && c->native[0]==U(client_vtable) && c->tag==M10V_BORDER_CLIENT_TAG;}
void m10v_border_client_construct(m10v_border_native_client *c){
 for(uint32_t i=0;i<sizeof(*c)/4;i++)((uint32_t*)c)[i]=0;
 ((void(*)(void*))0x534aacc8u)(c);c->native[0]=U(client_vtable);c->tag=M10V_BORDER_CLIENT_TAG;
}
int m10v_border_client_prepare(m10v_border_native_client *c,uint32_t event,uint32_t mask){
 if(!owned(c)||c->pending||c->inflight||!event||!mask)return 0;
 c->expected_event=event;c->expected_mask=mask;c->worker=0;c->job=0;c->completed=0;c->wait_failures=0;c->fill_bundle=0;c->bundle_error=0;
 barrier();c->pending=1;barrier();return 1;
}
uint32_t m10v_border_client_notify(m10v_border_native_client *c,uint32_t event,uint32_t payload){
 c->inflight++;barrier();TRACE(70u,U(c),event,payload);
 uint32_t result=((uint32_t(*)(void*,uint32_t,uint32_t))0x534aab0cu)(c,event,payload);
 TRACE(71u,U(c),event,result);barrier();if(owned(c)&&c->pending==1&&event==c->expected_event){c->completed++;c->pending=0;}
 barrier();c->inflight--;barrier();return result;
}
int m10v_border_client_done(m10v_border_native_client *c){barrier();return owned(c)&&!c->pending&&!c->inflight;}
int m10v_border_client_destroy_if_done(m10v_border_native_client *c){
 if(!m10v_border_client_done(c))return 0;
 ((void(*)(void*))0x534ac164u)(c);c->tag=0;return 1;
}
uint32_t m10v_border_client_wait(void *event,uint32_t mask,uint32_t *bits,uint32_t timeout){
 m10v_border_native_client *c=(m10v_border_native_client*)((uint8_t*)event-4);
 if(!owned(c)||mask!=c->expected_mask)return native_wait(event,mask,bits,timeout);
 TRACE(50u,U(c),mask,timeout);uint32_t result=native_wait(event,mask,bits,timeout);TRACE(51u,U(c),result,c->pending);uint32_t consumed=(result==1);
 while(!m10v_border_client_done(c)){
  if(consumed||c->inflight){yield();continue;}
  c->wait_failures++;yield();
  /* Recheck after yielding: callback may have finished without a successful
   * wait. Never block on an event already consumed by an earlier success. */
  if(m10v_border_client_done(c))break;
  result=native_wait(event,mask,bits,0xffffffffu);consumed=(result==1);
 }
 return result;
}
static transfer_tail *tail(void *w){return (transfer_tail*)((uint8_t*)w+0x44);}
void *m10v_border_transfer_construct(void *w){
 ((void*(*)(void*))0x5369a2c0u)(w);
 transfer_tail *t=tail(w);t->tag=TAIL_TAG;t->client=0;t->job=0;t->active=0;*(uint32_t*)((uint8_t*)w+0x54)=0;return w;
}
uint32_t m10v_border_transfer_body(void *w,void *parameters,uint32_t *job){
 transfer_tail *t=tail(w);m10v_border_native_client *c=(m10v_border_native_client*)(uintptr_t)job[1];
 int bind=t->tag==TAIL_TAG&&!t->active&&owned(c)&&c->pending==1&&c->expected_event==0x03050006u&&c->expected_mask==0x400u;
 if(bind){c->worker=U(w);c->job=U(job);t->client=U(c);t->job=U(job);barrier();t->active=1;barrier();}
 if(bind)TRACE(60u,U(w),U(c),U(parameters));uint32_t result=((uint32_t(*)(void*,void*))0x5369a948u)(w,parameters);if(bind)TRACE(61u,U(w),U(c),result);
 if(bind){barrier();t->active=0;t->client=0;t->job=0;barrier();}
 return result;
}
uint32_t m10v_border_transfer_wait(void *event,uint32_t mask,uint32_t *bits,uint32_t timeout,void *w){
 transfer_tail *t=tail(w);m10v_border_native_client *c=(m10v_border_native_client*)(uintptr_t)t->client;
 int protect=t->tag==TAIL_TAG&&t->active&&owned(c)&&c->pending==1&&c->worker==U(w)&&c->job==t->job&&
  *(uint32_t*)(uintptr_t)(t->job+4)==U(c)&&event==(uint8_t*)w+0x38&&mask==0x03050001u;
 if(protect)TRACE(62u,U(w),mask,timeout);uint32_t result=native_wait(event,mask,bits,timeout);if(protect)TRACE(63u,U(w),result,bits?*bits:0u);
 if(!protect)return result;
 while(result!=1||!bits||(*bits&mask)!=mask){c->wait_failures++;yield();result=native_wait(event,mask,bits,0xffffffffu);}
 return result;
}
/* Fill and Resize use separately enlarged original worker objects. */
#define FILL_TAIL 0x58u
#define RESIZE_TAIL 0x48u
#define FILL_TAG 0x42465731u
#define RESIZE_TAG 0x42525731u
static transfer_tail *at_tail(void *w,uint32_t offset){return (transfer_tail*)((uint8_t*)w+offset);}
static void init_tail(void *w,uint32_t offset,uint32_t tag){transfer_tail *t=at_tail(w,offset);t->tag=tag;t->client=0;t->job=0;t->active=0;}
static m10v_border_native_client *active_client(void *w,uint32_t offset,uint32_t tag,uint32_t event,uint32_t mask){
 transfer_tail *t=at_tail(w,offset);if(t->tag!=tag||!t->active)return 0;
 m10v_border_native_client *c=(m10v_border_native_client*)(uintptr_t)t->client;
 if(!owned(c)||c->pending!=1||c->worker!=U(w)||c->job!=t->job||!t->job||
  *(uint32_t*)(uintptr_t)(t->job+4)!=U(c)||c->expected_event!=event||c->expected_mask!=mask)return 0;
 return c;
}
/* Validate all rectangle metadata before enqueue AND before first native Fill.
 * Valid readable pointers and immutable owners remain caller prerequisites. */
static uint32_t valid_bundle(const m10v_border_fill_bundle *b){
 if(!b||(U(b)&3))return 0;
 uint32_t count=b->count;
 if(b->tag!=M10V_BORDER_FILL_BUNDLE_TAG||!count||
    count>M10V_BORDER_FILL_BUNDLE_MAX||b->bytes!=12u+count*12u)return 0;
 for(uint32_t i=0;i<count;i++){
  const m10v_border_fill_rectangle *r=&b->rectangles[i];
  if(!r->destination||(r->destination&3)||r->reserved)return 0;
  const uint8_t *d=(const uint8_t*)(uintptr_t)r->destination;
  if(d[0]>2)return 0;
  const uint16_t *h=(const uint16_t*)(d+0x10);
  if(!h[0]||!h[1]||!h[2]||!h[3]||
     (uint32_t)h[0]+h[4]>h[2]||(uint32_t)h[1]+h[5]>h[3])return 0;
 }
 return count;
}
static uint32_t invalid_bundle_hold(m10v_border_native_client *c){
 c->bundle_error=1;barrier();for(;;){c->wait_failures++;yield();}
}
int m10v_border_fill_bundle_submit(m10v_border_native_client *c,const m10v_border_fill_bundle *b){
 if(!owned(c)||c->pending||c->inflight||!valid_bundle(b))return 0;
 if(!m10v_border_client_prepare(c,0x03070004u,0x10u))return 0;
 c->fill_bundle=U(b);barrier();
 /* Only this prepared=1 entry can carry header-as-destination. Neither stock
  * pre/post image method may see the bundle header. */
 ((void(*)(void*,const void*,uint32_t,uint32_t,uint32_t,uint32_t))0x534abc18u)(c,b,0,0,0,1);
 if(!m10v_border_client_done(c)||c->completed!=1||c->bundle_error)return (int)invalid_bundle_hold(c);
 c->fill_bundle=0;barrier();return 1;
}
static uint32_t scoped_body(void *w,void *params,uint32_t *job,uint32_t offset,uint32_t tag,uint32_t event,uint32_t mask,uint32_t body){
 transfer_tail *t=at_tail(w,offset);m10v_border_native_client *c=(m10v_border_native_client*)(uintptr_t)job[1];
 int bind=t->tag==tag&&!t->active&&owned(c)&&c->pending==1&&c->expected_event==event&&c->expected_mask==mask;
 if(bind){c->worker=U(w);c->job=U(job);t->client=U(c);t->job=U(job);barrier();t->active=1;barrier();}
 uint32_t result;
 if(body==0x5365900cu&&owned(c)&&c->fill_bundle){
  const m10v_border_fill_bundle *b=(const m10v_border_fill_bundle*)(uintptr_t)c->fill_bundle;
  uint32_t count;
  if(!bind||!params||*(uint32_t*)params!=U(b)||!(count=valid_bundle(b)))return invalid_bundle_hold(c);
  result=0;
  for(uint32_t i=0;i<count;i++)
   result=((uint32_t(*)(void*,const void*))0x5365900cu)(w,&b->rectangles[i]);
 }else result=((uint32_t(*)(void*,void*))(uintptr_t)body)(w,params);
 if(bind){barrier();t->active=0;t->client=0;t->job=0;barrier();}return result;
}
static uint32_t protected_wait(m10v_border_native_client *c,void *event,uint32_t mask,uint32_t *bits,uint32_t timeout){
 if(!c)return native_wait(event,mask,bits,timeout);
 uint32_t local_bits=0,*observed=bits?bits:&local_bits,result;
 for(;;){
  *observed=0;result=native_wait(event,mask,observed,timeout);
  if(result==1&&(*observed&mask)==mask)return result;
  c->wait_failures++;yield();timeout=0xffffffffu;
 }
}
void *m10v_border_fill_construct(void *w){((void*(*)(void*))0x53658c78u)(w);init_tail(w,FILL_TAIL,FILL_TAG);return w;}
void *m10v_border_resize_construct(void *w){((void*(*)(void*))0x53672e10u)(w);init_tail(w,RESIZE_TAIL,RESIZE_TAG);return w;}
uint32_t m10v_border_fill_body(void *w,void *params,uint32_t *job){return scoped_body(w,params,job,FILL_TAIL,FILL_TAG,0x03070004u,0x10u,0x5365900cu);}
uint32_t m10v_border_resize_body(void *w,void *params,uint32_t *job){return scoped_body(w,params,job,RESIZE_TAIL,RESIZE_TAG,0x03020002u,0x40u,0x53673098u);}
uint32_t m10v_border_fill_wait(void *event,uint32_t mask,uint32_t *bits,uint32_t timeout,uint32_t *frame,void *context){
 /* 53769a78 saves caller r5 at fp-36 and caller LR at fp-4. Do not read
  * that r5 as a worker unless it came from the two locked Fill call sites. */
 uint32_t lr=frame[-1];m10v_border_native_client *c=0;
 if((lr==0x536591ccu||lr==0x53659258u)&&mask==1&&event==(uint8_t*)context+0x20){
  void *w=(void*)(uintptr_t)frame[-9];
  if(*(uint32_t*)((uint8_t*)w+0x44)==U(context))c=active_client(w,FILL_TAIL,FILL_TAG,0x03070004u,0x10u);
 }
 return protected_wait(c,event,mask,bits,timeout);
}
uint32_t m10v_border_resize_wait(void *event,uint32_t mask,uint32_t *bits,uint32_t timeout,uint32_t *frame){
 /* 53770bf0 saves original caller r7 at fp-28; its native context argument
  * is preserved in fp-0x2d0. Only the verified Resize body LR is admitted. */
 m10v_border_native_client *c=0;
 if(frame[-1]==0x536733e4u&&mask==4){
  void *w=(void*)(uintptr_t)frame[-7];void *context=(void*)(uintptr_t)frame[-0x2d0/4];
  if(event==(uint8_t*)context+0x48&&*(uint32_t*)((uint8_t*)w+0x34)==U(context))c=active_client(w,RESIZE_TAIL,RESIZE_TAG,0x03020002u,0x40u);
 }
 return protected_wait(c,event,mask,bits,timeout);
}
uint32_t m10v_border_resize_dma_wait(void *event,uint32_t mask,uint32_t *bits,uint32_t timeout,void *w){
 m10v_border_native_client *c=0;
 if(event==(uint8_t*)w+0x3c&&mask==3)c=active_client(w,RESIZE_TAIL,RESIZE_TAG,0x03020002u,0x40u);
 return protected_wait(c,event,mask,bits,timeout);
}
/* Observe the stock driver's ordinary release conditions BEFORE stock release
 * drops callbacks/category reservations. This is not an abort or bus-drain API. */
static uint32_t u32_at(void *p,uint32_t offset){return *(uint32_t*)((uint8_t*)p+offset);}
static int reservation_matches(void *service,uint32_t callback,const uint8_t *info){
 uint32_t category=info[3];if(category>2||!info[0x74])return 0;
 uint32_t mask=*(const uint32_t*)(info+0x78);
 return mask && u32_at(service,0x100+category*4)==mask && u32_at(service,0x40+category*0x1c)==callback;
}
static void fatal_hold(m10v_border_native_client *c){for(;;){c->wait_failures++;yield();}}
static void drop_service_locks(void *service,m10v_border_native_client *c){
 if(((uint32_t(*)(void*))0x536a8544u)((uint8_t*)service+0x14)!=1)fatal_hold(c);
 if(((uint32_t(*)(void*))0x536ae870u)((uint8_t*)service+0x90)!=1)fatal_hold(c);
}
static uint32_t guarded_release(m10v_border_native_client *c,void *service,uint32_t callback,uint8_t *info){
 if(c){
  for(;;){
   if(((uint32_t(*)(void*,uint32_t))0x536ae71cu)((uint8_t*)service+0x90,0xffffffffu)!=1){c->wait_failures++;yield();continue;}
   if(((uint32_t(*)(void*,uint32_t))0x536a848cu)((uint8_t*)service+0x14,5000)!=1){
    if(((uint32_t(*)(void*))0x536ae870u)((uint8_t*)service+0x90)!=1)fatal_hold(c);
    c->wait_failures++;yield();continue;
   }
   /* These fields are read only under the same native locks protecting the
    * original active-count transition. Missing ownership is fatal, not stock
    * fallback: releasing an unknown reservation cannot free our plane owner. */
   if(!reservation_matches(service,callback,info)||!((uint8_t*)service)[0xfc])fatal_hold(c);
   void *driver=(void*)(uintptr_t)u32_at(service,0x24);
   int accepted=0;
   if(((uint8_t*)service)[0xfc]==1 && ((uint32_t(*)(void*))0x53778490u)(driver)==0){
    ((void(*)(void*,uint32_t))0x53778458u)(driver,0);
    accepted=((uint32_t(*)(void*))0x53778474u)(driver)==0;
   }
   drop_service_locks(service,c);
   if(accepted)break;
   c->wait_failures++;yield();
  }
 }
 /* Verified own-job conditions were observed while sole-active. Native locks
  * must be released before entering its original acquisition path. A later
  * other reservation may make the shared engine busy again; this is not a
  * claim that global engine state stays idle across this handoff. */
 return ((uint32_t(*)(void*,uint32_t,uint8_t*))0x5376ed74u)(service,callback,info);
}
uint32_t m10v_border_fill_release(void *service,uint32_t callback,uint8_t *info,uint32_t *frame,void *context){
 m10v_border_native_client *c=0;uint32_t lr=frame[-1];
 if(lr==0x536591ccu||lr==0x53659258u){
  void *w=(void*)(uintptr_t)frame[-9];
  c=active_client(w,FILL_TAIL,FILL_TAG,0x03070004u,0x10u);
  if(c&&(u32_at(w,0x44)!=U(context)||u32_at(context,0xc)!=U(service)||callback!=U(context)+4||info!=(uint8_t*)frame-0xb0))fatal_hold(c);
 }
 return guarded_release(c,service,callback,info);
}
uint32_t m10v_border_resize_release(void *service,uint32_t callback,uint8_t *info,uint32_t *frame){
 m10v_border_native_client *c=0;
 if(frame[-1]==0x536733e4u){
  void *w=(void*)(uintptr_t)frame[-7];void *context=(void*)(uintptr_t)frame[-0x2d0/4];
  c=active_client(w,RESIZE_TAIL,RESIZE_TAG,0x03020002u,0x40u);
  if(c&&(u32_at(w,0x34)!=U(context)||u32_at(context,0x38)!=U(service)||callback!=frame[-0x2e4/4]||info!=(uint8_t*)frame-0x194))fatal_hold(c);
 }
 return guarded_release(c,service,callback,info);
}
/* First Transfer worker is singleton-owned original runtime storage. The
 * extra gate word is explicitly allocated at +0x54, never stock padding.
 * Caller must prevent native factory teardown for the whole private chain. */
uint32_t m10v_border_stage_enter(uint32_t token){
 if(!token)return 0;
 void *factory=((void*(*)(void))0x5369a0e8u)();
 void *w=(void*)(uintptr_t)u32_at(factory,4);
 if(!w||tail(w)->tag!=TAIL_TAG)return 0;
 uint32_t *gate=(uint32_t*)((uint8_t*)w+0x54);TRACE(80u,U(w),token,*gate);
 for(;;){uint32_t expected=0;
  if(__atomic_compare_exchange_n(gate,&expected,token,0,__ATOMIC_ACQUIRE,__ATOMIC_RELAXED))return U(w);
  yield();
 }
}
uint32_t m10v_border_stage_leave(uint32_t worker,uint32_t token){
 void *w=(void*)(uintptr_t)worker;
 if(!w||!token||tail(w)->tag!=TAIL_TAG)return 0;
 uint32_t expected=token;
 return __atomic_compare_exchange_n((uint32_t*)((uint8_t*)w+0x54),&expected,0,0,__ATOMIC_RELEASE,__ATOMIC_RELAXED);
}
