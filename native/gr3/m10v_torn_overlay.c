#include "m10v_torn_overlay.h"
#include "m10v_isp_effect_granulation.h"
#include "m10v_isp_effect_memory.h"
#include "m10v_isp_effect_transfer_runtime.h"
#include "m10v_torn_curves.h"
#define U(p) ((uint32_t)(uintptr_t)(p))
#define MAGIC 0x31534f54u
#define CAPACITY (6144u*4096u*3u/2u)
#define MASK_BYTES (TORN_MASK_WIDTH*TORN_MASK_HEIGHT*3u/2u)
#define LEASE 1u
#define CLOSING 2u
extern uint32_t m10v_save_trace_recipe_raw_status(uint32_t,uint32_t,uint32_t,uint32_t);
extern const uint8_t torn_masks[];
typedef struct {uint32_t magic,control,stage,generation,pending,token,manager,plane,capacity;
                uint32_t random_state,last_mask,pending_mask,pending_orientation;} session;
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
static uint32_t choose_mask(session *s){
 uint32_t x=s->random_state;
 x^=x<<13;x^=x>>17;x^=x<<5;s->random_state=x;
 if(s->last_mask>=TORN_MASK_COUNT)return x%TORN_MASK_COUNT;
 uint32_t index=x%(TORN_MASK_COUNT-1u);
 return index>=s->last_mask?index+1u:index;
}
void m10v_torn_init(uint32_t owner){session *s=storage(owner);if(!s)return;zero(s,sizeof(*s));s->generation=1;__atomic_store_n(&s->magic,MAGIC,__ATOMIC_RELEASE);}
void m10v_torn_destroy(uint32_t owner){session *s=storage(owner);if(!s||__atomic_load_n(&s->magic,__ATOMIC_ACQUIRE)!=MAGIC)return;__atomic_fetch_or(&s->control,CLOSING,__ATOMIC_ACQ_REL);while(__atomic_load_n(&s->control,__ATOMIC_ACQUIRE)&LEASE)((void(*)(uint32_t))0x536b0a74u)(1);if(s->pending){m10v_torn_snapshot *p=shot(s->pending);if(owned(p,s->pending)&&p->owner==owner&&p->generation==s->generation&&!p->completion){p->result=-(int32_t)M10V_TORN_CANCELLED;p->completion=0;}}s->pending=0;release(s);s->generation++;s->stage=0;__atomic_store_n(&s->magic,0,__ATOMIC_RELEASE);}
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
  uint32_t time[2]={0,0};
  (void)((int(*)(uint32_t *))0x53050b7cu)(time);
  s->random_state=(owner^s->generation^time[0]^time[1])|1u;
  s->last_mask=TORN_MASK_COUNT;
  s->stage=1;
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
  if(!enter(s)){reason=2;p->result=-(int32_t)(M10V_TORN_FREEZE_REJECTION+reason);p->completion=0;}
  else{
   p->owner=owner;p->generation=s->generation;stage=s->stage;reason=3;
   if(stage==1u){
    reason=s->pending?4u:!s->token?5u:!m10v_torn_eligible(recipe,si)?6u:0u;
    if(reason){p->result=-(int32_t)(M10V_TORN_FREEZE_REJECTION+reason);p->completion=0;}
    else{p->phase=stage;p->completion=0;s->pending=recipe;s->pending_orientation=orientation(si);
         s->pending_mask=choose_mask(s);}
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
static int reject(session *s,m10v_torn_snapshot *p,uint32_t reason,uint32_t detail){
 /* The recipe survives until JPEG handoff even when its shared trace fills. */
 p->result=-(int32_t)(reason|(detail<<8));p->completion=0;
 s->stage=4;
 if(s->pending==p->recipe)s->pending=0;
 M10V_TORN_MARK(p->recipe,M10V_TORN_EXEC,(p->phase<<8)|reason,p->generation);
 return -1;
}
static void cache(uint32_t p,uint32_t n){((void(*)(uint32_t,uint32_t))0x5383c8a8u)(p,n);__asm__ volatile("dmb ish" ::: "memory");}
int m10v_torn_execute(uint32_t recipe,uint32_t context,const uint32_t photo[8]){
 m10v_torn_snapshot *p=shot(recipe);if(!owned(p,recipe)){M10V_TORN_MARK(recipe,M10V_TORN_EXEC,1,0);return -1;}
 if(p->result<0)return -1;if(!p->phase||p->completion)return 1;
 session *s=storage(p->owner);
 if(p->owner!=current()||!enter(s)){M10V_TORN_MARK(recipe,M10V_TORN_EXEC,(p->phase<<8)|2u,p->generation);return -1;}
 /* Freeze assigns a phase only after validating the copied shooting info
  * and film selection. Native workers can update that info in place.
  * Use the admitted phase for this recipe and validate the actual buffers
  * and orientation below before submitting any IIP work. */
 uint32_t reason=p->generation!=s->generation||s->pending!=recipe||s->stage!=p->phase||!s->token?3u:
                 !ram(context,0x40)||!ram(U(photo),32)?4u:0u;
 if(reason){int r=reject(s,p,reason,0);leave(s);return r;}
 uint32_t d[8];for(uint32_t i=0;i<8;i++)d[i]=photo[i];uint32_t w=d[4]&65535u,h=d[4]>>16,pitch=d[5]&65535u,rows=d[5]>>16,alpha_pitch=(w+15u)&~15u,n=pitch*h,an=alpha_pitch*h,dir=orientation(p->si);
 uint32_t layout_faults=0;
 if((d[0]&255u)!=1u)layout_faults|=1u;
 if(w<2u||w>6144u||h<2u||h>4096u||((w|h)&1u))layout_faults|=2u;
 if((pitch|d[1]|d[2])&3u)layout_faults|=4u;
 if(pitch<((w+15u)&~15u)||pitch>6144u||rows<h||rows>4096u)layout_faults|=8u;
 if(d[3]||d[6])layout_faults|=16u;
 if((d[7]&255u)!=2u)layout_faults|=32u;
 if(dir>3u||dir!=s->pending_orientation)layout_faults|=64u;
 if(an+an/2u>s->capacity)layout_faults|=128u;
 M10V_TORN_MARK(recipe,M10V_TORN_LAYOUT,d[4],d[5]);
 M10V_TORN_MARK(recipe,M10V_TORN_FORMAT,(d[0]&255u)|((d[7]&255u)<<8)|((d[3]!=0)<<16)|((d[6]!=0)<<17),dir);
 if(layout_faults){int r=reject(s,p,6,layout_faults);leave(s);return r;}
 uint32_t bytes=pitch*rows,mask_bytes=CAPACITY+63u;
 uint32_t raw=word(recipe+0x60u),dims=word(recipe+0x230u),request=word(recipe+0x5cu);
 uint32_t conflicts=0;
 if(!m10v_isp_effect_buffer_span(d[1],bytes))conflicts|=1u;
 if(!m10v_isp_effect_buffer_span(d[2],bytes))conflicts|=2u;
 if(!conflicts){
  if(overlap(d[1],bytes,d[2],bytes))conflicts|=4u;
  if(overlap(d[1],bytes,s->token,mask_bytes)||overlap(d[2],bytes,s->token,mask_bytes))conflicts|=8u;
  const uint32_t addresses[]={recipe,p->si,p->owner,context,U(photo),request,dims};
  const uint32_t lengths[]={M10V_TORN_RECIPE_BYTES,0x74270u,M10V_TORN_OWNER_BYTES,0x40u,32u,0x3cu,4u};
  for(uint32_t i=0;i<7;i++){
   uint32_t address=addresses[i],length=lengths[i];
   if(!address)continue;
   if(overlap(address,length,d[1],bytes)||overlap(address,length,d[2],bytes))conflicts|=16u<<i;
   if(i!=2u&&overlap(address,length,s->token,mask_bytes))conflicts|=2048u<<i;
  }
 }
 if(conflicts){int r=reject(s,p,7,conflicts);leave(s);return r;}
 uint32_t raw_fault=0;
 if(raw){
  if(!ram(dims,4))raw_fault=1;
  else{uint32_t size=word(dims),rw=size&65535u,rh=size>>16,rn=2u*rw*rh;
   if(!rw||!rh||rw>8192u||rh>8192u)raw_fault=2;
   else if(!m10v_isp_effect_buffer_span(raw,rn))raw_fault=3;
   else if(overlap(raw,rn,d[1],bytes)||overlap(raw,rn,d[2],bytes))raw_fault=4;
   else if(overlap(raw,rn,s->token,mask_bytes))raw_fault=5;
  }
 }else{
  uint32_t status=m10v_save_trace_recipe_raw_status(recipe,p->si,word(recipe+0x2f4u),0);
  if(status!=2u){int r=reject(s,p,0x10u+(status&15u),0);leave(s);return r;}
 }
 if(raw_fault){int r=reject(s,p,8,raw_fault);leave(s);return r;}
 uint32_t mask=s->pending_mask;
 if(mask>=TORN_MASK_COUNT){int r=reject(s,p,10,0);leave(s);return r;}
 const m10v_isp_effect_texture texture={U(torn_masks)+mask*MASK_BYTES,MASK_BYTES,
     TORN_MASK_WIDTH,TORN_MASK_HEIGHT,TORN_MASK_WIDTH};
 m10v_isp_effect_transfer transfer;
 if(m10v_isp_effect_transfer_plan_format(&texture,s->plane,s->capacity,w,h,
        TORN_MASK_WIDTH,TORN_MASK_HEIGHT,0,2,&transfer)!=1||
    m10v_isp_effect_transfer_execute(&transfer,p->si)!=1){
  int r=reject(s,p,11,0);leave(s);return r;
 }
 d[0]=1;d[7]=2;
 uint32_t view[8];for(uint32_t i=0;i<8;i++)view[i]=d[i];
 view[2]=0;
 uint32_t edge[8];for(uint32_t i=0;i<8;i++)edge[i]=view[i];
 edge[1]=s->plane;edge[5]=alpha_pitch|(h<<16);
 /* Equal endpoint curves sharpen the resized distance field independently
  * of the weight input. The unchanged photo Y supplies a disjoint weight
  * plane, so sharpening needs no additional full-frame allocation. */
 cache(d[1],n);
 if(m10v_isp_effect_granulation_plane((void*)(uintptr_t)context,edge,edge,
     (void*)(uintptr_t)d[1],n,pitch,torn_curves[0])!=1){
  int r=reject(s,p,12,0);leave(s);return r;
 }
 for(uint32_t c=0;c<2;c++){
  view[1]=d[1u+c];
  cache(view[1],n);
  if(m10v_isp_effect_granulation_plane((void*)(uintptr_t)context,view,view,
      (void*)(uintptr_t)s->plane,an,alpha_pitch,torn_curves[1u+c])!=1){
   for(;;)((void(*)(uint32_t))0x536b0a74u)(1);
  }
 }
 s->last_mask=mask;
 p->result=1;p->completion=1;s->pending=0;leave(s);
 M10V_TORN_MARK(recipe,M10V_TORN_EXEC,(p->phase<<8)|((mask+1u)<<16),p->generation);
 return 1;
}
int m10v_torn_encoder_admit(uint32_t recipe,uint32_t si){
 m10v_torn_snapshot *p=shot(recipe);
 if(!owned(p,recipe)||p->si!=si){M10V_TORN_MARK(recipe,M10V_TORN_ENCODER,0xffffffffu,0);return 0;}
 int admit=p->result<0?!p->completion:!p->phase?p->completion==1u:p->result==1&&p->completion==1u;
 M10V_TORN_MARK(recipe,M10V_TORN_ENCODER,(p->phase<<24)|((p->result<0?255u:(uint32_t)p->result)<<16)|(p->completion<<8)|(uint32_t)admit,p->generation);
 return admit;
}
