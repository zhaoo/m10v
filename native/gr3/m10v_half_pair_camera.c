/* GR III2.10 native ISP -> owned IIP spatial pairing -> native JPEG.
 * Only scalar metadata is touched here. No image loads/stores, frame CRC or
 * filesystem operations. First-frame memory is a private pool allocation,
 * never a borrowed recipe bank. Every IIP call is synchronous through its
 * exact native completion; the owner destructor drains before releasing it. */
#include "m10v_half_pair_camera.h"
#include "m10v_half_pair.h"
#include "m10v_half_pair_iip.h"
#include "m10v_save_trace.h"
#include "m10v_debug.h"
#include "m10v_settings_controller.h"
#include <stddef.h>
#define U(p) ((uint32_t)(uintptr_t)(p))
#define P(a) ((uint8_t *)(uintptr_t)(a))
#define MAGIC 0x37535048u
#define BUSY 1u
#define CLOSING 2u
#define CANCEL 1u
#define BANK_MAX (3u*6144u*4064u)
typedef struct {uint32_t token,manager,bytes,d[8];} owned_frame;
typedef struct {uint32_t magic,control,flags,generation;owned_frame first;uint32_t orientation,cookie;} session;
typedef struct {uint32_t recipe,si,req,raw,raw_bytes,raw_dims,bank,capacity,owner;} exposure;
_Static_assert(sizeof(session)<=sizeof(((m10v_settings_controller *)0)->half_pair),"owned session capacity");
static uint32_t word(uint32_t p){return *(const uint32_t *)(uintptr_t)p;}
static int ram(uint32_t p,uint32_t n){return !(p&3u)&&p>=0x55000000u&&p<0x80000000u&&n<=0x80000000u-p;}
static int raw_ram(uint32_t p,uint32_t n){return ram(p,n)||(!(p&3u)&&p>=0xa0000000u&&p<0xe0000000u&&n<=0xe0000000u-p);}
static int overlap(uint32_t a,uint32_t an,uint32_t b,uint32_t bn){return an&&bn&&a<b+bn&&b<a+an;}
static int inside(uint32_t a,uint32_t n,uint32_t b,uint32_t cap){return a>=b&&a-b<=cap&&n<=cap-(a-b);}
static uint32_t align64(uint32_t v){return(v+63u)&~63u;}
static void copy8(uint32_t *d,const uint32_t *s){for(uint32_t i=0;i<8;i++)((volatile uint32_t *)d)[i]=s[i];}
static void zero(void *p,uint32_t n){for(uint32_t i=0;i<n;i++)((volatile uint8_t *)p)[i]=0;}
static int result(uint32_t r,int stage,uint32_t a,uint32_t b){M10V_LOG(218u,r,(uint32_t)stage,a,b);(void)r;(void)a;(void)b;return stage;}
static uint32_t ticks(void){return ((uint32_t(*)(void))0x53050b7cu)();}
static session *state(uint32_t owner){uint32_t at=M10V_SETTINGS_OWNER_BYTES+(uint32_t)offsetof(m10v_settings_controller,half_pair);return ram(owner,at+sizeof(session))?(session *)(uintptr_t)(owner+at):0;}
static uint32_t current_owner(void){if(!(word(0x55063910u)&1u))return 0;uint32_t owner=__atomic_load_n((const uint32_t *)0x55063988u,__ATOMIC_ACQUIRE);session *s=state(owner);return s&&__atomic_load_n(&s->magic,__ATOMIC_ACQUIRE)==MAGIC?owner:0;}
static uint32_t cookie(const session *s){return MAGIC^s->generation^s->orientation^s->first.token^s->first.manager^s->first.bytes^s->first.d[1]^s->first.d[2]^s->first.d[4]^s->first.d[5];}
static int frame_valid(const owned_frame *f){
 uint32_t w=f->d[4]&65535u,h=f->d[4]>>16,pitch=align64(w),rows=(h+15u)&~15u,plane=pitch*rows;
 return w&&w<=2992u&&!(w&15u)&&h&&h<=4000u&&!(h&1u)&&ram(f->manager,4)&&ram(f->token,f->bytes)&&f->bytes==2u*plane+63u&&f->d[0]==1u&&f->d[1]==align64(f->token)&&f->d[2]==f->d[1]+plane&&!f->d[3]&&f->d[5]==(pitch|(rows<<16))&&!f->d[6]&&f->d[7]==2u;
}
static void free_frame(owned_frame *f){if(f->token){((void(*)(uint32_t,uint32_t))0x536a248cu)(f->manager,f->token);f->token=0;}}
static void clear_first(session *s){
 if(s->first.token){
  /* Only our exact original allocation token may reach the pool free API. */
  if(!frame_valid(&s->first)||s->cookie!=cookie(s)){M10V_LOG(218u,0,(uint32_t)-19,s->first.token,s->cookie);return;}
  free_frame(&s->first);
 }
 s->cookie=0;s->orientation=0;s->generation++;
}
void m10v_half_pair_init(uint32_t owner){session *s=state(owner);if(!s)return;zero(s,sizeof(*s));s->generation=1;__atomic_store_n(&s->magic,MAGIC,__ATOMIC_RELEASE);}
void m10v_half_pair_destroy(uint32_t owner){
 session *s=state(owner);if(!s)return;__atomic_fetch_or(&s->control,CLOSING,__ATOMIC_ACQ_REL);__atomic_store_n(&s->magic,0,__ATOMIC_RELEASE);
 while(__atomic_load_n(&s->control,__ATOMIC_ACQUIRE)&BUSY)((void(*)(uint32_t))0x536b0a74u)(1u);
 M10V_LOG(221u,owner,s->generation,s->first.token,3u);clear_first(s);
}
int m10v_half_pair_reset(void){
 uint32_t owner=current_owner();if(!owner)return 1;session *s=state(owner);__atomic_fetch_or(&s->flags,CANCEL,__ATOMIC_RELEASE);
 uint32_t expected=0;if(!__atomic_compare_exchange_n(&s->control,&expected,BUSY,0,__ATOMIC_ACQ_REL,__ATOMIC_RELAXED))return 1;
 if(__atomic_load_n(&s->magic,__ATOMIC_ACQUIRE)==MAGIC){M10V_LOG(221u,owner,s->generation,s->first.token,2u);clear_first(s);}
 __atomic_fetch_and(&s->control,~BUSY,__ATOMIC_RELEASE);return 1;
}
uint32_t m10v_half_pair_select(uint32_t model,uint32_t raw){uint32_t answer=((uint32_t(*)(uint32_t,uint32_t))0x532525a4u)(model,raw);if(raw!=6u)(void)m10v_half_pair_reset();return answer;}
static int protected(const exposure *e,uint32_t a,uint32_t n){return overlap(a,n,e->bank,e->capacity)||overlap(a,n,e->recipe,M10V_SAVE_RECIPE_EXTENDED_BYTES)||overlap(a,n,e->si,0x74270u)||overlap(a,n,e->req,0x3cu)||overlap(a,n,e->raw,e->raw_bytes)||overlap(a,n,e->raw_dims,e->raw_dims?4u:0u)||overlap(a,n,e->owner,0x6300u);}
static int allocate_frame(owned_frame *f,const exposure *e,uint32_t w,uint32_t h,const owned_frame *other){
 zero(f,sizeof(*f));uint32_t pitch=align64(w),rows=(h+15u)&~15u,plane=pitch*rows;
 f->bytes=2u*plane+63u;f->manager=((uint32_t(*)(void))0x536a2424u)();if(!ram(f->manager,4))return 0;
 f->token=((uint32_t(*)(uint32_t,uint32_t,uint32_t))0x536a27e8u)(f->manager,f->bytes,2u);if(!f->token)return 0;
 if(!ram(f->token,f->bytes)||protected(e,f->token,f->bytes)||(other&&overlap(f->token,f->bytes,other->token,other->bytes))){free_frame(f);return 0;}
 f->d[0]=1;f->d[1]=align64(f->token);f->d[2]=f->d[1]+plane;f->d[4]=w|(h<<16);f->d[5]=pitch|(rows<<16);f->d[7]=2;return 1;
}
static int preview(uint32_t out[8],uint32_t descriptor,uint32_t bank,uint32_t at,uint32_t cap,uint32_t *next){
 copy8(out,(const uint32_t *)(uintptr_t)descriptor);uint32_t f=out[0]&255u,w=out[4]&65535u,h=out[4]>>16,pitch=out[5]&65535u,rows=out[5]>>16;
 if((f!=1u&&f!=2u)||!w||w>2048u||(w&1u)||!h||h>1536u||pitch<w||pitch>4096u||(pitch&1u)||rows<h||rows>1536u||out[3]||out[6]||(out[7]&255u)!=2u||(f==2u&&((h|rows)&1u)))return 0;
 uint32_t yn=pitch*rows,cn=f==2u?yn/2u:yn;if(at>cap||yn>cap-at||cn>cap-at-yn)return 0;
 out[1]=bank+at;out[2]=out[1]+yn;*next=align64(at+yn+cn);return 1;
}
static int process(exposure *e,session *s,uint32_t context){
 const uint32_t *ctx=(const uint32_t *)(uintptr_t)context;uint32_t r=e->recipe,mode=word(r+0x18u);e->req=word(r+0x5cu);
 if((mode!=0u&&mode!=5u&&mode!=6u)||ctx[0]!=0x53d0fbe0u||ctx[12]!=r+0x1a8u||ctx[13]!=e->si||ctx[14]!=e->req||ctx[15]!=r+0xb0u||ctx[16]!=r+0xd0u||ctx[17]!=r+0xf0u||ctx[18]!=r+0x110u||ctx[19]!=r+0x130u||!ram(e->req,0x3c)||word(e->req)!=0x53d0fe60u||P(e->req)[12]!=1u||P(e->req)[13]>1u||P(r+0x130u)[16]!=1u)return result(r,-2,mode,e->req);
 const uint32_t *d=(const uint32_t *)(uintptr_t)(r+0xb0u);uint32_t w=d[4]&65535u,h=d[4]>>16,pitch=d[5]&65535u,rows=d[5]>>16;
 e->bank=word(r+0x304u);e->capacity=word(r+0x364u);M10V_LOG(219u,e->bank,e->capacity,d[1],d[2]);M10V_LOG(220u,r,d[4],d[5],d[6]);
 uint32_t orientation=P(e->si)[0x71e03]?P(e->si)[0x71e04]:P(e->si)[0xc8];orientation=orientation==1u?8u:orientation==2u?3u:orientation==3u?6u:1u;
 if(!ram(e->bank,e->capacity)||e->capacity>BANK_MAX)return result(r,-3,e->bank,e->capacity);
 uint32_t bank=align64(e->bank),prefix=bank-e->bank;if(prefix>=e->capacity)return result(r,-3,bank,e->capacity);uint32_t cap=e->capacity-prefix;
 m10v_half_pair_plan_info p;if((d[0]&255u)!=1u||d[3]||d[6]||(d[7]&255u)!=2u||pitch<w||pitch>8192u||(pitch&1u)||rows<h||rows>4096u||!m10v_half_pair_plan(w,h,orientation,cap,&p))return result(r,-3,w,h);
 /* Native cache preparation can cover full stride*rows, including crop padding. */
 uint32_t span=pitch*rows;if(!inside(d[1],span,e->bank,e->capacity)||!inside(d[2],span,e->bank,e->capacity)||overlap(d[1],span,d[2],span))return result(r,-3,d[1],d[2]);
 e->raw=word(r+0x60u);e->raw_dims=word(r+0x230u);e->raw_bytes=0;
 if(e->raw){if(!ram(e->raw_dims,4))return result(r,-4,e->raw,e->raw_dims);uint32_t rw=*(const uint16_t *)(uintptr_t)e->raw_dims,rh=*(const uint16_t *)(uintptr_t)(e->raw_dims+2);if(!rw||rw>8192u||!rh||rh>8192u)return result(r,-4,rw,rh);e->raw_bytes=2u*rw*rh;if(!raw_ram(e->raw,e->raw_bytes))return result(r,-4,e->raw,e->raw_bytes);}
 else if(m10v_save_trace_recipe_raw_status(r,e->si,word(r+0x2f4u),0)!=M10V_CAPTURE_RAW_RELEASED)return result(r,-4,0,0);
 if(overlap(e->bank,e->capacity,e->raw,e->raw_bytes)||overlap(e->bank,e->capacity,r,M10V_SAVE_RECIPE_EXTENDED_BYTES)||overlap(e->bank,e->capacity,e->si,0x74270u)||overlap(e->bank,e->capacity,e->req,0x3c))return result(r,-4,e->bank,e->capacity);
 uint32_t output[8],previews[2][8],next=align64(p.used_bytes);copy8(output,d);output[1]=bank;output[2]=bank+p.plane_bytes;output[4]=p.width|(p.height<<16);output[5]=p.stride|(p.rows<<16);output[6]=0;
 if(!preview(previews[0],r+0xd0u,bank,next,cap,&next)||!preview(previews[1],r+0xf0u,bank,next,cap,&next))return result(r,-5,next,cap);
 if(!m10v_half_pair_iip_ready())return result(r,-15,0,0);
 if(s->first.token&&(!frame_valid(&s->first)||s->cookie!=cookie(s)||protected(e,s->first.token,s->first.bytes)))return result(r,-19,s->first.token,s->cookie);
 if(s->first.token&&(s->first.d[4]!=d[4]||s->orientation!=orientation)){M10V_LOG(221u,e->owner,s->generation,s->first.token,4u);clear_first(s);}
 if(!s->first.token){
  owned_frame first;if(!allocate_frame(&first,e,w,h,0))return result(r,-8,w,h);uint32_t begin=ticks();
  if(!m10v_half_pair_iip_copy(r,d,first.d)){free_frame(&first);return result(r,-16,1,0);}
  for(uint32_t i=0;i<sizeof(first)/4u;i++)((volatile uint32_t *)&s->first)[i]=((const uint32_t *)&first)[i];s->orientation=orientation;s->generation++;s->cookie=cookie(s);
  M10V_LOG(222u,r,1u,ticks()-begin,s->first.token);return result(r,1,w,h);
 }
 owned_frame current;if(!allocate_frame(&current,e,w,h,&s->first))return result(r,-8,w,h);uint32_t begin=ticks();
 if(!m10v_half_pair_iip_copy(r,d,current.d)){free_frame(&current);return result(r,-16,2,0);}
 M10V_LOG(222u,r,2u,ticks()-begin,current.token);begin=ticks();
 int ok=m10v_half_pair_iip_compose(r,s->first.d,current.d,output,(const uint32_t (*)[8])previews,orientation);
 if(!ok){free_frame(&current);return result(r,-16,3,0);}
 for(uint32_t i=0;i<8;i++){((uint32_t *)(uintptr_t)(r+0x70u))[i]=output[i];((uint32_t *)(uintptr_t)(r+0xb0u))[i]=output[i];((uint32_t *)(uintptr_t)(r+0x110u))[i]=output[i];((uint32_t *)(uintptr_t)(r+0xd0u))[i]=previews[0][i];((uint32_t *)(uintptr_t)(r+0xf0u))[i]=previews[1][i];}
 M10V_LOG(222u,r,3u,ticks()-begin,s->first.token);free_frame(&current);clear_first(s);return result(r,2,p.width,p.height);
}
int m10v_half_pair_camera(uint32_t context){
 if(!ram(context,0x60u)||context<0x550009b8u)return result(context,-1,context,0);
 exposure e;zero(&e,sizeof(e));e.recipe=context-0x9b8u;
 if(!ram(e.recipe,M10V_SAVE_RECIPE_EXTENDED_BYTES)||word(e.recipe)!=0x53d0fc90u||word(e.recipe+M10V_SAVE_RECIPE_BYTES)!=M10V_SAVE_TRACE_MAGIC)return result(e.recipe,-1,e.recipe,1);
 e.si=word(e.recipe+0x44c8u);if(!ram(e.si,0x74270u))return result(e.recipe,-1,e.si,2);uint32_t half=P(e.si)[0x7b6]==6u;
 e.owner=current_owner();if(!e.owner)return half?result(e.recipe,-10,0,0):0;session *s=state(e.owner);
 if(!half&&!s->first.token)return 0;uint32_t expected=0;if(!__atomic_compare_exchange_n(&s->control,&expected,BUSY,0,__ATOMIC_ACQ_REL,__ATOMIC_RELAXED))return half?result(e.recipe,-11,0,0):0;
 if(__atomic_load_n(&s->magic,__ATOMIC_ACQUIRE)!=MAGIC){__atomic_fetch_and(&s->control,~BUSY,__ATOMIC_RELEASE);return half?result(e.recipe,-10,0,0):0;}
 M10V_LOG(221u,e.owner,s->generation,s->first.token,s->flags);if(half)(void)result(e.recipe,0,context,e.si);
 uint32_t flags=__atomic_fetch_and(&s->flags,~CANCEL,__ATOMIC_ACQ_REL);if((flags&CANCEL)||!half)clear_first(s);
 int stage=half?process(&e,s,context):result(e.recipe,3,0,0);__atomic_fetch_and(&s->control,~BUSY,__ATOMIC_RELEASE);return stage;
}
