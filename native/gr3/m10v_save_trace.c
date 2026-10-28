/* Recipe-owned diagnostics. Only the checked factory wrapper allocates via
 * stock pool7; no SD calls, globals or locks held across stock calls. */
#include "m10v_save_trace.h"
typedef uint32_t (*fn2)(uint32_t,uint32_t);
typedef uint32_t (*fn3)(uint32_t,uint32_t,uint32_t);
extern const uint32_t m10v_save_trace_vtable[3];
typedef struct {
 uint32_t prefix[5]; /* stock 0x14-byte callback/event wrapper prefix */
 m10v_save_trace *trace;
 uint32_t original,task;
} save_proxy;
_Static_assert(sizeof(save_proxy)==32,"stock ARM proxy ABI");
static int ram(uint32_t p,uint32_t n){return !(p&3)&&p>=0x55000000u&&p<0x80000000u&&n<=0x80000000u-p;}
static int valid(m10v_save_trace *t){return t&&ram((uint32_t)(uintptr_t)t,sizeof(*t))&&t->magic==M10V_SAVE_TRACE_MAGIC;}
/* One exclusive attempt, no spin or blocking. The event callback can overlap
 * a caller on another CPU; dropped records are explicit. */
static uint32_t try_enter(uint32_t *p){
 uint32_t old,result;
 __asm__ volatile("ldrex %0,[%2]\n"
                  "cmp %0,#0\n"
                  "bne 1f\n"
                  "strex %1,%3,[%2]\n"
                  "b 2f\n"
                  "1: clrex\n"
                  "mov %1,#1\n"
                  "2:" :"=&r"(old),"=&r"(result):"r"(p),"r"(1u):"cc","memory");
 if(result)return 0;
 __asm__ volatile("dmb ish":::"memory");return 1;
}
void m10v_save_trace_init(m10v_save_trace *t){
 if(!t||!ram((uint32_t)(uintptr_t)t,sizeof(*t)))return;
 uint32_t *p=(uint32_t *)t;for(uint32_t i=0;i<sizeof(*t)/4;i++)p[i]=0;
 t->magic=M10V_SAVE_TRACE_MAGIC;
}
uint32_t m10v_save_trace_append(m10v_save_trace *t,uint32_t e,uint32_t a,uint32_t b,uint32_t c,uint32_t d){
 if(!valid(t)||!try_enter(&t->busy))return 0;
 uint32_t n=t->count;
#if M10V_BORDER_ENABLED && M10V_DEBUG_MODE
 /* Slot31 is never appended: the ordinary limit is31 and the full ring
  * reserves its final slot. Keep the latest border rejection across earlier
  * trace drains so the camera's bounded file pages cannot hide its reason. */
 if(e==197u&&b==0x424f5244u){uint32_t *last=t->events[31];last[0]=e;last[1]=a;last[2]=b;last[3]=c;last[4]=d;}
#endif
 if(n>=(e>=190u&&e<=199u?M10V_SAVE_TRACE_CAPACITY-1u:M10V_SAVE_TRACE_CAPACITY-7u)){if(t->dropped!=0xffffffffu)t->dropped++;__asm__ volatile("dmb ish":::"memory");t->busy=0;return 0;}
 uint32_t *r=t->events[n];r[0]=e;r[1]=a;r[2]=b;r[3]=c;r[4]=d;
 __asm__ volatile("dmb ish":::"memory");t->count=n+1;
 __asm__ volatile("dmb ish":::"memory");t->busy=0;return 1;
}
uint32_t m10v_save_trace_callback(uint32_t address,uint32_t opcode,uint32_t payload){
 save_proxy *p=(save_proxy *)(uintptr_t)address;
 /* Only our private callback vtable selects this entry, so p is the active
  * bridge's stack proxy; no generic function-entry hook can call it. */
 uint32_t status=0xffffffffu;
 if(ram(payload,5))status=*(const uint8_t *)(uintptr_t)(payload+4);
 m10v_save_trace_append(p->trace,M10V_SAVE_EVENT_PAYLOAD,p->original,opcode,status,p->task);
 /* Original callback retains all opcode/status/unknown-status behavior,
  * updates proxy+10 and signals the very same stock event handle. */
 return ((fn3)0x534ec9b8u)(address,opcode,payload);
}
uint32_t m10v_save_trace_bridge(uint32_t object,uint32_t info,m10v_save_trace *trace,uint32_t task){
 if(!valid(trace)||!ram(object,0x14)||*(const uint32_t *)(uintptr_t)object!=0x53c5ed78u)
  return ((fn2)0x534ecb3cu)(object,info);
 save_proxy proxy;
 const uint32_t *source=(const uint32_t *)(uintptr_t)object;
 for(uint32_t i=0;i<5;i++)proxy.prefix[i]=source[i];
 proxy.prefix[0]=(uint32_t)(uintptr_t)m10v_save_trace_vtable;
 proxy.trace=trace;proxy.original=object;proxy.task=task;
 m10v_save_trace_append(trace,M10V_SAVE_EVENT_BEGIN,object,info,task,source[4]&255u);
 /* Stock bridge publishes callback pointer, waits forever, clears event and
  * reads result byte. Shared event identity is copied, never constructed or
  * destroyed here. Its owning original object outlives this call. */
 uint32_t result=((fn2)0x534ecb3cu)((uint32_t)(uintptr_t)&proxy,info);
 __asm__ volatile("dmb ish":::"memory");
 *(uint8_t *)(uintptr_t)(object+0x10)=((const uint8_t *)proxy.prefix)[0x10];
 m10v_save_trace_append(trace,M10V_SAVE_EVENT_RETURN,object,result,task,((const uint8_t *)proxy.prefix)[0x10]);
 return result;
}
void m10v_save_trace_raw_set(m10v_save_trace *t,uint32_t r,uint32_t id,uint32_t input,uint32_t caller){m10v_save_trace_append(t,M10V_SAVE_EVENT_RAW_SET,r,id,input,caller);}
void m10v_save_trace_allocation(m10v_save_trace *t,uint32_t r,uint32_t id,uint32_t n,uint32_t result){m10v_save_trace_append(t,M10V_SAVE_EVENT_ALLOC,r,id,n,result);}
void m10v_save_trace_transfer(m10v_save_trace *t,uint32_t r,uint32_t target,uint32_t backing,uint32_t source){m10v_save_trace_append(t,M10V_SAVE_EVENT_TRANSFER,r,target,backing,source);}
void m10v_save_trace_release(m10v_save_trace *t,uint32_t r,uint32_t id,uint32_t backing,uint32_t caller){m10v_save_trace_append(t,M10V_SAVE_EVENT_RELEASE,r,id,backing,caller);}

/* All hooks below are installed only in the SHA-locked recipe factory and
 * callers. Stock allocator/free/encoder behavior remains authoritative. */
static m10v_save_trace *recipe_trace(uint32_t recipe){
 if(!ram(recipe,M10V_SAVE_RECIPE_BYTES+sizeof(m10v_save_trace))||
    *(const uint32_t *)(uintptr_t)recipe!=0x53d0fc90u)return 0;
 m10v_save_trace *t=(m10v_save_trace *)(uintptr_t)(recipe+M10V_SAVE_RECIPE_BYTES);
 return valid(t)?t:0;
}
static m10v_capture_raw_lifetime *raw_token(uint32_t recipe){
 if(!recipe_trace(recipe)||!ram(recipe,M10V_SAVE_RECIPE_EXTENDED_BYTES))return 0;
 return (m10v_capture_raw_lifetime *)(uintptr_t)(recipe+M10V_CAPTURE_RAW_TOKEN_OFFSET);
}
uint32_t m10v_save_trace_recipe_raw_status(uint32_t recipe,uint32_t si,uint32_t backing,uint32_t source){
 m10v_capture_raw_lifetime *s=raw_token(recipe);
 if(!s||*(const uint32_t *)(uintptr_t)(recipe+0x44c8u)!=si||*(const uint32_t *)(uintptr_t)(recipe+0x2f4u)!=backing||*(const uint32_t *)(uintptr_t)(recipe+0x60u)!=source)return M10V_CAPTURE_RAW_REJECT;
 return m10v_capture_raw_classify(s,recipe,si,backing,source);
}
void m10v_save_trace_recipe_pool_return(uint32_t recipe,uint32_t id,uint32_t backing,uint32_t result){
 m10v_capture_raw_lifetime *s=raw_token(recipe);
 if(s)m10v_capture_raw_pool_return(s,recipe,*(const uint32_t *)(uintptr_t)(recipe+0x44c8u),id,backing,result);
}
uint32_t m10v_save_trace_recipe_alloc(uint32_t bytes){
 /* Only the exact factory size is extended. Other allocations retain ABI. */
 uint32_t result=((uint32_t (*)(uint32_t))0x5351091cu)(bytes==M10V_SAVE_RECIPE_BYTES?M10V_SAVE_RECIPE_EXTENDED_BYTES:bytes);
 if(bytes==M10V_SAVE_RECIPE_BYTES&&ram(result,M10V_SAVE_RECIPE_EXTENDED_BYTES)){
  uint32_t *tail=(uint32_t *)(uintptr_t)(result+bytes);
  for(uint32_t i=0;i<(M10V_SAVE_RECIPE_EXTENDED_BYTES-bytes)/4;i++)tail[i]=0;
  m10v_save_trace_init((m10v_save_trace *)tail);
  m10v_capture_raw_init((m10v_capture_raw_lifetime *)(uintptr_t)(result+M10V_CAPTURE_RAW_TOKEN_OFFSET),result);
 }
 return result;
}
uint32_t m10v_save_trace_recipe_set(uint32_t recipe,uint32_t id,uint32_t backing){
 m10v_save_trace *t=recipe_trace(recipe);
 m10v_capture_raw_lifetime *s=raw_token(recipe);
 uint32_t old_backing=0,old_source=0,si=0;
 if(s&&id==1){old_backing=*(const uint32_t *)(uintptr_t)(recipe+0x2f4u);old_source=*(const uint32_t *)(uintptr_t)(recipe+0x60u);si=*(const uint32_t *)(uintptr_t)(recipe+0x44c8u);if(backing)m10v_capture_raw_invalidate(s,recipe);}
 uint32_t caller=(uint32_t)(uintptr_t)__builtin_return_address(0);
 if(t&&id==1){
  m10v_save_trace_append(t,M10V_SAVE_EVENT_RAW_BEFORE,recipe,
   *(const uint32_t *)(uintptr_t)(recipe+0x2f4),*(const uint32_t *)(uintptr_t)(recipe+0x60),caller);
  m10v_save_trace_raw_set(t,recipe,id,backing,caller);
 }
 uint32_t result=((fn3)0x5350d7e8u)(recipe,id,backing);
 if(s&&id==1)m10v_capture_raw_set_after(s,recipe,si,id,backing,old_backing,old_source,*(const uint32_t *)(uintptr_t)(recipe+0x2f4u),*(const uint32_t *)(uintptr_t)(recipe+0x60u));
 return result;
}
uint32_t m10v_save_trace_recipe_allocate(uint32_t owner,uint32_t recipe,uint32_t id,uint32_t policy){
 if(id==1)m10v_capture_raw_invalidate(raw_token(recipe),recipe);
 uint32_t result=((uint32_t (*)(uint32_t,uint32_t,uint32_t,uint32_t))0x535216d0u)(owner,recipe,id,policy);
 if(id==1)m10v_save_trace_append(recipe_trace(recipe),M10V_SAVE_EVENT_ALLOC_RESULT,recipe,id,policy,result);
 return result;
}
uint32_t m10v_save_trace_recipe_release(uint32_t owner,uint32_t recipe,uint32_t id){
 m10v_save_trace *t=recipe_trace(recipe);
 m10v_capture_raw_lifetime *s=raw_token(recipe);
 if(s&&id==1)m10v_capture_raw_release_begin(s,recipe,*(const uint32_t *)(uintptr_t)(recipe+0x44c8u),*(const uint32_t *)(uintptr_t)(recipe+0x2f4u),*(const uint32_t *)(uintptr_t)(recipe+0x60u),(uint32_t)(uintptr_t)__builtin_return_address(0));
 if(t&&id==1)m10v_save_trace_release(t,recipe,id,*(const uint32_t *)(uintptr_t)(recipe+0x2f4),(uint32_t)(uintptr_t)__builtin_return_address(0));
 uint32_t result=((fn3)0x53521d14u)(owner,recipe,id);
 if(s&&id==1)m10v_capture_raw_release_finish(s,recipe,*(const uint32_t *)(uintptr_t)(recipe+0x44c8u),*(const uint32_t *)(uintptr_t)(recipe+0x2f4u),*(const uint32_t *)(uintptr_t)(recipe+0x60u));
 if(t&&id==1)m10v_save_trace_append(t,M10V_SAVE_EVENT_RELEASE_RETURN,recipe,id,*(const uint32_t *)(uintptr_t)(recipe+0x2f4),result);
 return result;
}
uint32_t m10v_save_trace_recipe_take(uint32_t recipe,uint32_t *out,uint32_t capacity){
 m10v_save_trace *t=recipe_trace(recipe);
 if(!t||capacity<M10V_SAVE_TRACE_CAPACITY||!ram((uint32_t)(uintptr_t)out,M10V_SAVE_TRACE_CAPACITY*20)||!try_enter(&t->busy))return 0;
 uint32_t n=t->count;if(n>M10V_SAVE_TRACE_CAPACITY)n=M10V_SAVE_TRACE_CAPACITY;
 for(uint32_t i=0;i<n;i++)for(uint32_t j=0;j<5;j++)out[i*5+j]=t->events[i][j];
 if(t->dropped){uint32_t *r=out+n*5;r[0]=199u;r[1]=recipe;r[2]=t->dropped;r[3]=t->count;r[4]=0;n++;}
 t->count=0;t->dropped=0;
 __asm__ volatile("dmb ish":::"memory");t->busy=0;return n;
}

uint32_t m10v_save_trace_recipe_mark(uint32_t recipe,uint32_t event,uint32_t a,uint32_t b,uint32_t c){return m10v_save_trace_append(recipe_trace(recipe),event,recipe,a,b,c);}
