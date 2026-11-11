#include "m10v_torn_overlay.h"
#include "m10v_isp_effect_granulation.h"
#include "m10v_isp_effect_memory.h"
#include "m10v_torn_curves.h"
#define U(p) ((uint32_t)(uintptr_t)(p))
#define MAGIC 0x31534f54u
#define CAPACITY (6144u*4096u)
#define LEASE 1u
#define CLOSING 2u
extern uint32_t m10v_save_trace_recipe_raw_status(uint32_t,uint32_t,uint32_t,uint32_t);
typedef struct {uint32_t magic,control,stage,generation,pending,token,manager,plane,capacity,width,height,pitch,orientation,pending_orientation;} session;
_Static_assert(sizeof(session)<=0x100,"torn owner tail");
_Static_assert(sizeof(m10v_torn_snapshot)==32,"torn recipe tail");
static uint32_t word(uint32_t p){return *(const uint32_t*)(uintptr_t)p;}
static int ram(uint32_t p,uint32_t n){return !(p&3u)&&p>=0x55000000u&&p<0x80000000u&&n<=0x80000000u-p;}
static int overlap(uint32_t a,uint32_t n,uint32_t b,uint32_t m){return n&&m&&a<b+m&&b<a+n;}
static void zero(void *p,uint32_t n){for(uint32_t i=0;i<n/4u;i++)((volatile uint32_t*)p)[i]=0;}
static session *storage(uint32_t owner){return ram(owner,M10V_TORN_OWNER_BYTES)?(void*)(uintptr_t)(owner+M10V_TORN_OWNER_OFFSET):0;}
static uint32_t current(void){if(!(word(0x55063910u)&1u))return 0;uint32_t o=__atomic_load_n((uint32_t*)0x55063988u,__ATOMIC_ACQUIRE);session *s=storage(o);return s&&__atomic_load_n(&s->magic,__ATOMIC_ACQUIRE)==MAGIC?o:0;}
static int enter(session *s){uint32_t v=0;return s&&__atomic_load_n(&s->magic,__ATOMIC_ACQUIRE)==MAGIC&&__atomic_compare_exchange_n(&s->control,&v,LEASE,0,__ATOMIC_ACQ_REL,__ATOMIC_RELAXED);}
static void leave(session *s){__atomic_fetch_and(&s->control,~LEASE,__ATOMIC_RELEASE);}
static void release(session *s){if(s->token){((void(*)(uint32_t,uint32_t))0x536a248cu)(s->manager,s->token);s->token=0;s->plane=0;s->capacity=0;}}
static m10v_torn_snapshot *shot(uint32_t r){return ram(r,M10V_TORN_RECIPE_BYTES)&&word(r)==0x53d0fc90u?(void*)(uintptr_t)(r+M10V_TORN_SHOT_OFFSET):0;}
static int owned(m10v_torn_snapshot *p,uint32_t r){return p&&p->magic==M10V_TORN_SHOT_MAGIC&&p->recipe==r&&ram(p->si,0x74270u)&&word(r+0x44c8u)==p->si;}
static uint32_t orientation(uint32_t si){const uint8_t *p=(void*)(uintptr_t)si;uint32_t v=p[p[0x71e03]?0x71e04:0xc8];return v<=3u?v:0xffffffffu;}
void m10v_torn_init(uint32_t owner){session *s=storage(owner);if(!s)return;zero(s,sizeof(*s));s->generation=1;__atomic_store_n(&s->magic,MAGIC,__ATOMIC_RELEASE);}
void m10v_torn_destroy(uint32_t owner){session *s=storage(owner);if(!s||__atomic_load_n(&s->magic,__ATOMIC_ACQUIRE)!=MAGIC)return;__atomic_fetch_or(&s->control,CLOSING,__ATOMIC_ACQ_REL);while(__atomic_load_n(&s->control,__ATOMIC_ACQUIRE)&LEASE)((void(*)(uint32_t))0x536b0a74u)(1);if(s->pending){m10v_torn_snapshot *p=shot(s->pending);if(owned(p,s->pending)&&p->owner==owner&&p->generation==s->generation&&!p->completion){p->result=-1;p->completion=0;}}s->pending=0;release(s);s->generation++;s->stage=0;__atomic_store_n(&s->magic,0,__ATOMIC_RELEASE);}
int m10v_torn_state(uint32_t *stage,uint32_t *generation){session *s=storage(current());if(!s||!stage||!generation)return 0;*stage=__atomic_load_n(&s->stage,__ATOMIC_ACQUIRE);*generation=__atomic_load_n(&s->generation,__ATOMIC_ACQUIRE);return 1;}
int m10v_torn_busy(void){session *s=storage(current());return (s&&(__atomic_load_n(&s->control,__ATOMIC_ACQUIRE)||__atomic_load_n(&s->pending,__ATOMIC_ACQUIRE)))||m10v_torn_camera_busy();}
int m10v_torn_set(uint32_t owner,uint32_t action){
 if(action>1u||owner!=current()||m10v_torn_camera_busy())return -1;session *s=storage(owner);if(!enter(s))return -1;
 if(s->pending||(action&&!m10v_torn_eligible(0,0))){leave(s);return -1;}
 if(action){
  if(!s->token){uint32_t manager=((uint32_t(*)(void))0x536a2424u)();if(!ram(manager,4)){leave(s);return -1;}uint32_t token=((uint32_t(*)(uint32_t,uint32_t,uint32_t))0x536a27e8u)(manager,CAPACITY+63u,2u);
   if(!token){leave(s);return -1;}
   if(!m10v_isp_effect_buffer_span(token,CAPACITY+63u)||overlap(token,CAPACITY+63u,owner,M10V_TORN_OWNER_BYTES)){((void(*)(uint32_t,uint32_t))0x536a248cu)(manager,token);leave(s);return -1;}
   s->manager=manager;s->token=token;s->plane=(token+63u)&~63u;s->capacity=CAPACITY;
  }
  s->width=s->height=s->pitch=s->orientation=0;s->stage=1;
 }else{release(s);s->stage=0;}
 s->generation++;leave(s);return 0;
}
void m10v_torn_reserve(uint32_t recipe){m10v_torn_snapshot *p=shot(recipe);if(p)zero(p,sizeof(*p));}
int m10v_torn_freeze(uint32_t recipe){
 m10v_torn_snapshot *p=shot(recipe);if(!p)return 0;if(p->magic)return owned(p,recipe);
 uint32_t si=word(recipe+0x44c8u);if(!ram(si,0x74270u))return 0;
 p->recipe=recipe;p->si=si;p->completion=1;
 uint32_t owner=current();session *s=storage(owner);uint32_t reason=1,stage=0;
 if(s){
  if(!enter(s)){reason=2;p->result=-1;p->completion=0;}
  else{
   p->owner=owner;p->generation=s->generation;stage=s->stage;reason=3;
   if(stage==1u||stage==2u){
    reason=s->pending?4u:!s->token?5u:!m10v_torn_eligible(recipe,si)?6u:0u;
    if(reason){s->stage=4;p->result=-1;p->completion=0;}
    else{p->phase=stage;p->completion=0;s->pending=recipe;s->pending_orientation=orientation(si);}
   }
   leave(s);
  }
 }
#if M10V_DEBUG_MODE
 const uint8_t *saved=(const void*)(uintptr_t)si;
 M10V_TORN_MARK(recipe,M10V_TORN_FREEZE,(stage<<8)|reason,p->generation);
 if(stage==1u||stage==2u)
  M10V_TORN_MARK(recipe,M10V_TORN_SI,((uint32_t)saved[0xfb9]<<24)|((uint32_t)saved[0x799]<<16)|((uint32_t)saved[0x7b6]<<8)|saved[0x77c],orientation(si));
#endif
 __atomic_store_n(&p->magic,M10V_TORN_SHOT_MAGIC,__ATOMIC_RELEASE);return 1;
}
static int reject(session *s,m10v_torn_snapshot *p,uint32_t reason){
 p->result=-1;p->completion=0;if(s){s->stage=4;if(s->pending==p->recipe)s->pending=0;}
 M10V_TORN_MARK(p->recipe,M10V_TORN_EXEC,(p->phase<<8)|reason,p->generation);
 return -1;
}
static void cache(uint32_t p,uint32_t n){((void(*)(uint32_t,uint32_t))0x5383c8a8u)(p,n);__asm__ volatile("dmb ish" ::: "memory");}
int m10v_torn_execute(uint32_t recipe,uint32_t context,const uint32_t photo[8]){
 m10v_torn_snapshot *p=shot(recipe);if(!owned(p,recipe)){M10V_TORN_MARK(recipe,M10V_TORN_EXEC,1,0);return -1;}
 if(p->result==-1)return -1;if(!p->phase||p->completion)return 1;
 session *s=storage(p->owner);
 if(p->owner!=current()||!enter(s)){M10V_TORN_MARK(recipe,M10V_TORN_EXEC,(p->phase<<8)|2u,p->generation);return -1;}
 uint32_t reason=p->generation!=s->generation||s->pending!=recipe||s->stage!=p->phase||!s->token?3u:
                 !ram(context,0x40)||!ram(U(photo),32)?4u:!m10v_torn_eligible(recipe,p->si)?5u:0u;
 if(reason){int r=reject(s,p,reason);leave(s);return r;}
 uint32_t d[8];for(uint32_t i=0;i<8;i++)d[i]=photo[i];uint32_t w=d[4]&65535u,h=d[4]>>16,pitch=d[5]&65535u,rows=d[5]>>16,alpha_pitch=(w+63u)&~63u,n=pitch*h,an=alpha_pitch*h,dir=orientation(p->si);
 int ok=(d[0]&255u)==1u&&w>=2u&&w<=6144u&&h>=2u&&h<=4096u&&!((w|h)&1u)&&!((pitch|d[1]|d[2])&3u)&&pitch>=((w+15u)&~15u)&&pitch<=6144u&&rows>=h&&rows<=4096u&&!d[3]&&!d[6]&&(d[7]&255u)==2u&&dir<=3u&&dir==s->pending_orientation&&an<=s->capacity;
 M10V_TORN_MARK(recipe,M10V_TORN_LAYOUT,d[4],d[5]);
 M10V_TORN_MARK(recipe,M10V_TORN_FORMAT,(d[0]&255u)|((d[7]&255u)<<8)|((d[3]!=0)<<16)|((d[6]!=0)<<17),dir);
 if(!ok)reason=6;
 for(uint32_t i=1;i<=2&&ok;i++)ok=m10v_isp_effect_buffer_span(d[i],pitch*rows)&&!overlap(d[i],pitch*rows,s->token,CAPACITY+63u)&&!overlap(d[i],pitch*rows,recipe,M10V_TORN_RECIPE_BYTES)&&!overlap(d[i],pitch*rows,p->si,0x74270u)&&!overlap(d[i],pitch*rows,p->owner,M10V_TORN_OWNER_BYTES)&&!overlap(d[i],pitch*rows,context,0x40)&&!overlap(d[i],pitch*rows,U(photo),32);
 ok=ok&&!overlap(d[1],pitch*rows,d[2],pitch*rows)&&!overlap(s->token,CAPACITY+63u,recipe,M10V_TORN_RECIPE_BYTES)&&!overlap(s->token,CAPACITY+63u,p->si,0x74270u)&&!overlap(s->token,CAPACITY+63u,context,0x40)&&!overlap(s->token,CAPACITY+63u,U(photo),32);
 uint32_t raw=word(recipe+0x60u),dims=word(recipe+0x230u),request=word(recipe+0x5cu);
 if(request)ok=ok&&!overlap(request,0x3cu,d[1],pitch*rows)&&!overlap(request,0x3cu,d[2],pitch*rows)&&!overlap(request,0x3cu,s->token,CAPACITY+63u);
 if(dims)ok=ok&&!overlap(dims,4,d[1],pitch*rows)&&!overlap(dims,4,d[2],pitch*rows)&&!overlap(dims,4,s->token,CAPACITY+63u);
 if(!ok&&!reason)reason=7;
 if(raw){
  if(!ram(dims,4))ok=0;
  else{uint32_t size=word(dims),rw=size&65535u,rh=size>>16,rn=2u*rw*rh;
   ok=ok&&rw&&rh&&rw<=8192u&&rh<=8192u&&m10v_isp_effect_buffer_span(raw,rn)&&!overlap(raw,rn,d[1],pitch*rows)&&!overlap(raw,rn,d[2],pitch*rows)&&!overlap(raw,rn,s->token,CAPACITY+63u)&&!overlap(dims,4,s->token,CAPACITY+63u);
  }
 }else if(ok){
  uint32_t status=m10v_save_trace_recipe_raw_status(recipe,p->si,word(recipe+0x2f4u),0);
  if(status!=2u){ok=0;reason=0x10u+(status&15u);}
 }
 if(!ok&&!reason)reason=8;
 if(p->phase==2u)ok=ok&&s->width==w&&s->height==h&&s->orientation==dir&&s->pitch==alpha_pitch;
 if(!ok){int r=reject(s,p,reason?reason:9u);leave(s);return r;}
 d[0]=1;d[7]=2;uint32_t view[8],source[8];for(uint32_t i=0;i<8;i++){view[i]=d[i];source[i]=d[i];}view[2]=0;source[2]=0;
 if(p->phase==1u){
  view[1]=s->plane;view[5]=alpha_pitch|(h<<16);
  cache(s->plane,an);cache(d[1],n);
  if(m10v_isp_effect_granulation_plane((void*)(uintptr_t)context,view,source,(void*)(uintptr_t)d[1],n,pitch,torn_curves[0])!=1){for(;;)((void(*)(uint32_t))0x536b0a74u)(1);}
  s->width=w;s->height=h;s->pitch=alpha_pitch;s->orientation=dir;uint32_t expected=1u;__atomic_compare_exchange_n(&s->stage,&expected,2u,0,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE);
 }else{
  cache(s->plane,an);
  for(uint32_t c=0;c<2;c++){
   view[1]=d[1u+c];
   cache(view[1],n);
   if(m10v_isp_effect_granulation_plane((void*)(uintptr_t)context,view,view,(void*)(uintptr_t)s->plane,an,alpha_pitch,torn_curves[1u+c])!=1){for(;;)((void(*)(uint32_t))0x536b0a74u)(1);}
  }
  uint32_t expected=2u;__atomic_compare_exchange_n(&s->stage,&expected,3u,0,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE);release(s);
 }
 p->result=1;p->completion=1;s->pending=0;leave(s);
 M10V_TORN_MARK(recipe,M10V_TORN_EXEC,p->phase<<8,p->generation);
 return 1;
}
int m10v_torn_encoder_admit(uint32_t recipe,uint32_t si){
 m10v_torn_snapshot *p=shot(recipe);
 if(!owned(p,recipe)||p->si!=si){M10V_TORN_MARK(recipe,M10V_TORN_ENCODER,0xffffffffu,0);return 0;}
 int admit=p->result==-1?!p->completion:!p->phase?p->completion==1u:p->result==1&&p->completion==1u;
 M10V_TORN_MARK(recipe,M10V_TORN_ENCODER,(p->phase<<24)|((p->result&255u)<<16)|(p->completion<<8)|(uint32_t)admit,p->generation);
 return admit;
}
