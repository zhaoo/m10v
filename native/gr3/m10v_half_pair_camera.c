/* GR III 2.10 only. Spatial pairing after native ISP; no CPU color pipeline.
 * All retained bytes are private SD copies, never borrowed native pointers.
 * No descriptors or source pixels change until ALL fallible work succeeds. */
#include "m10v_half_pair_camera.h"
#include "m10v_half_pair.h"
#include "m10v_save_trace.h"
#include "m10v_debug.h"
#include "m10v_settings_controller.h"
#include <stddef.h>
#ifndef M10V_HALF_PAIR_BUILD_ID
#ifdef M10V_DEBUG_BUILD_ID
#define M10V_HALF_PAIR_BUILD_ID M10V_DEBUG_BUILD_ID
#else
#define M10V_HALF_PAIR_BUILD_ID 0u
#endif
#endif
#define U(p) ((uint32_t)(uintptr_t)(p))
#define P(a) ((uint8_t *)(uintptr_t)(a))
#define MAGIC 0x32504648u
#define HEADER_BYTES 40u
static const char path[]="C:\\M10V\\HALFPAIR.BIN";
typedef struct {uint32_t magic,version,build,w,h,orientation,bytes,data_crc,reserved,crc;} header;
typedef struct {uint32_t fs;const uint32_t *v;} filesystem;
typedef struct {uint32_t d[8],yn,cn,at;} thumbnail;
static uint32_t word(uint32_t p){return *(const uint32_t *)(uintptr_t)p;}
static int ram(uint32_t p,uint32_t n){return !(p&3u)&&p>=0x55000000u&&p<0x80000000u&&n<=0x80000000u-p;}
static int raw_ram(uint32_t p,uint32_t n){return ram(p,n)||(!(p&3u)&&p>=0xa0000000u&&p<0xe0000000u&&n<=0xe0000000u-p);}
static int code(uint32_t p,uint32_t n){return !(p&3u)&&p>=0x53000000u&&p<0x540b6000u&&n<=0x540b6000u-p;}
static int overlap(uint32_t a,uint32_t an,uint32_t b,uint32_t bn){return an&&bn&&a<b+bn&&b<a+an;}
static int inside(uint32_t a,uint32_t n,uint32_t base,uint32_t cap){return a>=base&&a-base<=cap&&n<=cap-(a-base);}
static uint32_t crc_more(uint32_t crc,const uint8_t *p,uint32_t n){for(uint32_t i=0;i<n;i++){crc^=p[i];for(uint32_t b=0;b<8;b++)crc=(crc>>1)^(0xedb88320u&(0u-(crc&1u)));}return crc;}
static uint32_t crc(const void *p,uint32_t n){return ~crc_more(0xffffffffu,p,n);}
static int fs_get(filesystem *out){
 uint32_t manager=((uint32_t(*)(void))0x535847d8u)();if(!ram(manager,24))return 0;
 uint32_t fs=word(manager+20);if(!ram(fs,4))return 0;uint32_t vt=word(fs);if(!code(vt,56))return 0;
 const uint32_t *v=(const uint32_t *)(uintptr_t)vt;for(uint32_t i=7;i<=13;i++)if(!code(v[i],4))return 0;
 out->fs=fs;out->v=v;return 1;
}
static int open_file(const filesystem *f,uint32_t mode,uint32_t *h){uint32_t e=0;*h=0;int ok=((int(*)(uint32_t,const char*,uint32_t,uint32_t*,uint32_t*))f->v[7])(f->fs,path,mode,h,&e);return ok&&!e&&*h;}
static int close_file(const filesystem *f,uint32_t h){uint32_t e=0;int ok=((int(*)(uint32_t,uint32_t,uint32_t*))f->v[8])(f->fs,h,&e);return ok&&!e;}
static int exact(const filesystem *f,uint32_t h,uint32_t at,void *p,uint32_t n,int write){
 uint32_t e=0,pos=0;
 if(!((int(*)(uint32_t,uint32_t,uint32_t,uint32_t,uint32_t*))f->v[11])(f->fs,h,at,0,&e)||e)return 0;
 if(!((int(*)(uint32_t,uint32_t,uint32_t*,uint32_t*))f->v[13])(f->fs,h,&pos,&e)||e||pos!=at)return 0;
 if(!((int(*)(uint32_t,uint32_t,void*,uint32_t,uint32_t*))f->v[write?10:9])(f->fs,h,p,n,&e)||e)return 0;
 return ((int(*)(uint32_t,uint32_t,uint32_t*,uint32_t*))f->v[13])(f->fs,h,&pos,&e)&&!e&&pos==at+n;
}
static int invalidate(const filesystem *f){
 uint32_t h=0;header zero;for(uint32_t i=0;i<10;i++)((volatile uint32_t *)&zero)[i]=0;int opened=open_file(f,0,&h),ok=0;
 if(opened)ok=exact(f,h,0,&zero,sizeof(zero),1);
 if(h&&!close_file(f,h))ok=0;return ok;
}
int m10v_half_pair_reset(void){filesystem f;return fs_get(&f)&&invalidate(&f);}
static int valid(const header *h,uint32_t w,uint32_t height,uint32_t orientation){return h->magic==MAGIC&&h->version==2&&h->build==M10V_HALF_PAIR_BUILD_ID&&h->w==w&&h->h==height&&h->orientation==orientation&&h->bytes==2u*w*height&&!h->reserved&&h->crc==crc(h,36);}
static int read_header(const filesystem *f,header *out,uint32_t *handle){
 uint32_t h=0,n=0,e=0;int ok=open_file(f,1,&h);
 if(ok)ok=((int(*)(uint32_t,uint32_t,uint32_t*,uint32_t*))f->v[12])(f->fs,h,&n,&e)&&!e&&n>=HEADER_BYTES&&exact(f,h,0,out,HEADER_BYTES,0)&&n==HEADER_BYTES+out->bytes;
 if(!ok){if(h)(void)close_file(f,h);return 0;}*handle=h;return 1;
}
static int save_first(const filesystem *f,uint32_t y,uint32_t c,uint32_t w,uint32_t h,uint32_t pitch,uint32_t orientation){
 header a={MAGIC,2,M10V_HALF_PAIR_BUILD_ID,w,h,orientation,2u*w*h,0,0,0},zero;for(uint32_t i=0;i<10;i++)((volatile uint32_t *)&zero)[i]=0;uint32_t sum=0xffffffffu;
 for(uint32_t plane=0;plane<2;plane++)for(uint32_t row=0;row<h;row++)sum=crc_more(sum,P((plane?c:y)+row*pitch),w);
 a.data_crc=~sum;a.crc=crc(&a,36);
 uint32_t handle=0;int ok=open_file(f,0,&handle);
 if(ok)ok=exact(f,handle,0,&zero,HEADER_BYTES,1);
 for(uint32_t plane=0;ok&&plane<2;plane++)for(uint32_t row=0;ok&&row<h;row++)ok=exact(f,handle,HEADER_BYTES+(plane*h+row)*w,P((plane?c:y)+row*pitch),w,1);
 if(ok)ok=exact(f,handle,0,&a,HEADER_BYTES,1);
 if(handle&&!close_file(f,handle))ok=0;return ok;
}
static uint32_t align64(uint32_t v){return (v+63u)&~63u;}
static int thumb_plan(thumbnail *t,uint32_t descriptor,uint32_t at,uint32_t cap){
 const uint32_t *d=(const uint32_t *)(uintptr_t)descriptor;for(uint32_t i=0;i<8;i++)t->d[i]=d[i];
 uint32_t w=d[4]&65535u,h=d[4]>>16,pitch=d[5]&65535u,rows=d[5]>>16,format=d[0]&255u;
 if((format!=1&&format!=2)||!w||w>2048u||(w&1u)||!h||h>1536u||pitch<w||pitch>4096u||(pitch&1u)||rows<h||rows>1536u||d[3]||d[6]||(d[7]&255u)!=2u||(format==2u&&((h|rows)&1u)))return 0;
 t->yn=pitch*rows;t->cn=format==2u?t->yn/2u:t->yn;t->at=at;
 return at<=cap&&t->yn<=cap-at&&t->cn<=cap-at-t->yn;
}
/* Bounded restoring division avoids a dependency on libgcc/native math ABI. */
static uint32_t divide(uint32_t a,uint32_t b){uint32_t q=0,r=0;for(uint32_t i=32;i;i--){r=(r<<1)|((a>>(i-1))&1u);if(r>=b){r-=b;q|=1u<<(i-1);}}return q;}
static void thumb_render(thumbnail *t,uint32_t bank,const m10v_half_pair_plan_info *p){
 uint32_t w=t->d[4]&65535u,h=t->d[4]>>16,pitch=t->d[5]&65535u,format=t->d[0]&255u;
 uint8_t *y=P(bank+t->at),*c=y+t->yn;for(uint32_t i=0;i<t->yn;i++)y[i]=16;for(uint32_t i=0;i<t->cn;i++)c[i]=128;
 uint32_t dw=w,dh=divide(p->height*w,p->width);if(dh>h){dh=h;dw=divide(p->width*h,p->height);}dw&=~1u;dh&=~1u;
 uint32_t x0=((w-dw)/2u)&~1u,y0=((h-dh)/2u)&~1u;
 if(dw&&dh)for(uint32_t row=0;row<dh;row++){
  uint32_t sy=divide(row*p->height,dh);const uint8_t *ys=P(bank+sy*p->stride),*cs=P(bank+p->plane_bytes+sy*p->stride);
  for(uint32_t x=0;x<dw;x+=2){uint32_t sx=divide(x*p->width,dw)&~1u;
   y[(row+y0)*pitch+x+x0]=ys[divide(x*p->width,dw)];y[(row+y0)*pitch+x+x0+1]=ys[divide((x+1u)*p->width,dw)];
   if(format==1u||!(row&1u)){uint32_t cr=format==2u?(row+y0)/2u:row+y0;c[cr*pitch+x+x0]=cs[sx];c[cr*pitch+x+x0+1]=cs[sx+1];}
  }
 }
 t->d[1]=U(y);t->d[2]=U(c);
}
static int result(uint32_t recipe,int stage,uint32_t a,uint32_t b){
 /* The recipe diagnostic ring may already be full before JPEG handoff. This
  * consumer is filesystem-safe: persist pairing status independently. */
 M10V_LOG(218u,recipe,(uint32_t)stage,a,b);(void)recipe;(void)a;(void)b;return stage;
}
static int camera_impl(uint32_t context){
 if(!ram(context,0x60)||context<0x550009b8u)return -1;
 uint32_t recipe=context-0x9b8u;if(!ram(recipe,M10V_SAVE_RECIPE_EXTENDED_BYTES)||word(recipe)!=0x53d0fc90u||word(recipe+M10V_SAVE_RECIPE_BYTES)!=M10V_SAVE_TRACE_MAGIC)return -1;
 uint32_t si=word(recipe+0x44c8u);if(!ram(si,0x74270u))return -1;
 if(P(si)[0x7b6]!=6u)return 0; /* zero FS, allocation and pixel work in ordinary modes */
 const uint32_t *ctx=(const uint32_t *)(uintptr_t)context;
 uint32_t req=word(recipe+0x5cu),mode=word(recipe+0x18u);
 if((mode!=0u&&mode!=5u&&mode!=6u)||ctx[0]!=0x53d0fbe0u||ctx[12]!=recipe+0x1a8u||ctx[13]!=si||ctx[14]!=req||ctx[15]!=recipe+0xb0u||ctx[16]!=recipe+0xd0u||ctx[17]!=recipe+0xf0u||ctx[18]!=recipe+0x110u||ctx[19]!=recipe+0x130u||!ram(req,0x3c)||word(req)!=0x53d0fe60u||P(req)[12]!=1u||P(req)[13]>1u||P(recipe+0x130u)[16]!=1u)return result(recipe,-2,mode,req);
 const uint32_t *d=(const uint32_t *)(uintptr_t)(recipe+0xb0u);
 uint32_t w=d[4]&65535u,h=d[4]>>16,pitch=d[5]&65535u,rows=d[5]>>16;
 uint32_t backing=word(recipe+0x304u),capacity=word(recipe+0x364u),orientation=P(si)[0x71e03]?P(si)[0x71e04]:P(si)[0xc8];orientation=orientation==1u?8u:orientation==2u?3u:orientation==3u?6u:1u;
 M10V_LOG(219u,backing,capacity,d[1],d[2]);
 M10V_LOG(220u,recipe,d[4],d[5],d[6]);
 /* Original id5 setter5350d984 keeps the raw allocation token. Its virtual
  * layout5350db3c rounds that token up64 at5350dc48; a valid allocation need
  * not itself be64 aligned. Keep both the owner interval and aligned canvas. */
 /* GR III2.10 original53510cec reads the sensor (not visible crop)
  * height at53510d38 and computes3*sensor_stride*sensor_height at53510da8.
  * The full sensor allocation is6144*4064*3=74,907,648 bytes. The earlier
  * 4000-row fixture accidentally bounded this by the visible JPEG height.
  * Capacity is the native allocation receipt frozen in owned recipe+364.
  * Never re-read sensor/RAW metadata here: RAW may already be released. */
 const uint32_t native_sensor_capacity=3u*6144u*4064u;
 if(!ram(backing,capacity)||capacity>native_sensor_capacity)return result(recipe,-3,backing,capacity);
 uint32_t bank=align64(backing),prefix=bank-backing;
 if(prefix>=capacity)return result(recipe,-3,backing,capacity);
 uint32_t cap=capacity-prefix;
 m10v_half_pair_plan_info plan;
 if((d[0]&255u)!=1u||d[3]||d[6]||(d[7]&255u)!=2u||pitch<w||pitch>8192u||(pitch&1u)||rows<h||rows>4096u||!m10v_half_pair_plan(w,h,orientation,cap,&plan))return result(recipe,-3,w,h);
 /* BackResize retains original pitch/allocated rows while advancing Y/C to
  * the visible crop. CPU copies read only the visible rows, not trailing
  * storage from that displaced origin. Validate precisely that footprint. */
 uint32_t source_bytes=(h-1u)*pitch+w;
 if(!inside(d[1],source_bytes,backing,capacity)||!inside(d[2],source_bytes,backing,capacity)||overlap(d[1],source_bytes,d[2],source_bytes))return result(recipe,-3,d[1],d[2]);
 /* Authenticate the complete mutation interval independently of source crop. */
 uint32_t raw=word(recipe+0x60u),raw_dims=word(recipe+0x230u),raw_bytes=0;
 if(raw){if(!ram(raw_dims,4))return result(recipe,-4,raw,raw_dims);uint32_t rw=*(const uint16_t *)(uintptr_t)raw_dims,rh=*(const uint16_t *)(uintptr_t)(raw_dims+2);if(!rw||rw>8192u||!rh||rh>8192u)return result(recipe,-4,rw,rh);raw_bytes=2u*rw*rh;if(!raw_ram(raw,raw_bytes))return result(recipe,-4,raw,raw_bytes);}
 else if(m10v_save_trace_recipe_raw_status(recipe,si,word(recipe+0x2f4u),raw)!=M10V_CAPTURE_RAW_RELEASED)return result(recipe,-4,raw,0);
 if(overlap(backing,capacity,raw,raw_bytes)||overlap(backing,capacity,recipe,M10V_SAVE_RECIPE_EXTENDED_BYTES)||overlap(backing,capacity,si,0x74270u)||overlap(backing,capacity,req,0x3cu)||overlap(backing,capacity,raw_dims,raw_dims?4u:0u))return result(recipe,-4,backing,capacity);
 thumbnail thumbs[2];uint32_t at=align64(plan.used_bytes);
 if(!thumb_plan(&thumbs[0],recipe+0xd0u,at,cap))return result(recipe,-5,at,cap);
 at=align64(at+thumbs[0].yn+thumbs[0].cn);if(!thumb_plan(&thumbs[1],recipe+0xf0u,at,cap))return result(recipe,-5,at,cap);
 uint32_t used=at+thumbs[1].yn+thumbs[1].cn;
 filesystem f;if(!fs_get(&f))return result(recipe,-6,0,0);
 ((void(*)(void*,uint32_t))0x5383c8a8u)(P(bank),cap);
 header previous;uint32_t handle=0;int found=read_header(&f,&previous,&handle);
 if(!found||!valid(&previous,w,h,orientation)){
  if(found&&!close_file(&f,handle))return result(recipe,-7,0,0);
  int saved=save_first(&f,d[1],d[2],w,h,pitch,orientation);return result(recipe,saved?1:-7,w,h);
 }
 uint32_t frame_bytes=2u*w*h,scratch_bytes=2u*frame_bytes,manager=((uint32_t(*)(void))0x536a2424u)();
 uint32_t allocation=((uint32_t(*)(uint32_t,uint32_t,uint32_t))0x536a27e8u)(manager,scratch_bytes+63u,2u);
 if(!allocation){(void)close_file(&f,handle);return result(recipe,-8,scratch_bytes,0);}
 uint32_t memory=align64(allocation);int ok=ram(allocation,scratch_bytes+63u)&&!overlap(memory,scratch_bytes,backing,capacity)&&!overlap(memory,scratch_bytes,raw,raw_bytes)&&!overlap(memory,scratch_bytes,recipe,M10V_SAVE_RECIPE_EXTENDED_BYTES)&&!overlap(memory,scratch_bytes,si,0x74270u)&&!overlap(memory,scratch_bytes,req,0x3cu)&&!overlap(memory,scratch_bytes,raw_dims,raw_dims?4u:0u);
 if(ok)ok=exact(&f,handle,HEADER_BYTES,P(memory),frame_bytes,0)&&crc(P(memory),frame_bytes)==previous.data_crc;
 if(!close_file(&f,handle))ok=0;
 if(ok){for(uint32_t plane=0;plane<2;plane++)for(uint32_t row=0;row<h;row++)for(uint32_t x=0;x<w;x++)P(memory+frame_bytes)[(plane*h+row)*w+x]=P((plane?d[2]:d[1])+row*pitch)[x];ok=invalidate(&f);}
 if(ok)ok=m10v_half_pair_compose(&plan,P(memory),P(memory+frame_bytes),P(bank),cap);
 if(ok){
  for(uint32_t i=0;i<2;i++)thumb_render(&thumbs[i],bank,&plan);
  uint32_t output[8];for(uint32_t i=0;i<8;i++)output[i]=d[i];output[1]=bank;output[2]=bank+plan.plane_bytes;output[3]=0;output[4]=plan.width|(plan.height<<16);output[5]=plan.stride|(plan.rows<<16);output[6]=0;output[7]=(output[7]&~255u)|2u;
  for(uint32_t i=0;i<8;i++){((uint32_t *)(uintptr_t)(recipe+0x70u))[i]=output[i];((uint32_t *)(uintptr_t)(recipe+0xb0u))[i]=output[i];((uint32_t *)(uintptr_t)(recipe+0x110u))[i]=output[i];((uint32_t *)(uintptr_t)(recipe+0xd0u))[i]=thumbs[0].d[i];((uint32_t *)(uintptr_t)(recipe+0xf0u))[i]=thumbs[1].d[i];}
  ((void(*)(void*,uint32_t))0x5383c8a8u)(P(bank),used);
 }
 ((void(*)(uint32_t,uint32_t))0x536a248cu)(manager,allocation);
 return result(recipe,ok?2:-9,plan.width,plan.height);
}

/* Scalar owner state only. The camera bridge re-resolves the singleton after
 * synchronous services; it never publishes through a retained owner pointer. */
#define STATE_MAGIC 0x32535048u
static uint32_t *owner_state(uint32_t owner){
 uint32_t at=M10V_SETTINGS_OWNER_BYTES+(uint32_t)offsetof(m10v_settings_controller,half_pair);
 if(!ram(owner,at+16u))return 0;return (uint32_t *)(uintptr_t)(owner+at);
}
void m10v_half_pair_init(uint32_t owner){
 uint32_t *s=owner_state(owner);if(!s)return;
 s[1]=0;s[2]=0;s[3]=0;__atomic_store_n(s,STATE_MAGIC,__ATOMIC_RELEASE);
}
/* The original TopMenu destructor leaves its singleton published until delete.
 * Closing and busy share one atomic control word. The destructor holds the
 * native allocation until the synchronous photo consumer releases busy. */
void m10v_half_pair_destroy(uint32_t owner){
 uint32_t *s=owner_state(owner);if(!s)return;
 __atomic_fetch_or(s+1,2u,__ATOMIC_ACQ_REL);
 __atomic_store_n(s,0u,__ATOMIC_RELEASE);
 while(__atomic_load_n(s+1,__ATOMIC_ACQUIRE)&1u)((void(*)(uint32_t))0x536b0a74u)(1u);
}
static uint32_t current_owner(void){
 if(!(word(0x55063910u)&1u))return 0;
 uint32_t owner=__atomic_load_n((const uint32_t *)0x55063988u,__ATOMIC_ACQUIRE);
 uint32_t *s=owner_state(owner);return s&&__atomic_load_n(s,__ATOMIC_ACQUIRE)==STATE_MAGIC?owner:0;
}
/* The real selection callback calls the unmodified model setter first. Merely
 * drawing captions never cancels a group. Cancellation is scalar and no-I/O. */
uint32_t m10v_half_pair_select(uint32_t model,uint32_t raw){
 uint32_t answer=((uint32_t(*)(uint32_t,uint32_t))0x532525a4u)(model,raw);
 if(raw!=6u){uint32_t owner=current_owner();if(owner){uint32_t *s=owner_state(owner);if(!(__atomic_load_n(s+1,__ATOMIC_ACQUIRE)&2u))__atomic_fetch_or(s+3,2u,__ATOMIC_RELEASE);}}
 return answer;
}
int m10v_half_pair_camera(uint32_t context){
 if(!ram(context,0x60u)||context<0x550009b8u)return result(context,-1,context,0);
 uint32_t recipe=context-0x9b8u;
 if(!ram(recipe,M10V_SAVE_RECIPE_EXTENDED_BYTES)||word(recipe)!=0x53d0fc90u||word(recipe+M10V_SAVE_RECIPE_BYTES)!=M10V_SAVE_TRACE_MAGIC)return result(recipe,-1,recipe,1);
 uint32_t si=word(recipe+0x44c8u);if(!ram(si,0x74270u))return result(recipe,-1,si,2);
 uint32_t is_half=P(si)[0x7b6]==6u;
 if(is_half)(void)result(recipe,0,context,si);
 uint32_t owner=current_owner();
 if(!owner)return is_half?result(recipe,-10,0,0):0;
 uint32_t *s=owner_state(owner);
 uint32_t flags=__atomic_load_n(s+3,__ATOMIC_ACQUIRE);
 if(!is_half&&!(flags&1u))return 0;
 uint32_t expected=0;if(!__atomic_compare_exchange_n(s+1,&expected,1u,0,__ATOMIC_ACQ_REL,__ATOMIC_RELAXED))return is_half?result(recipe,-11,0,0):0;
 if(__atomic_load_n(s,__ATOMIC_ACQUIRE)!=STATE_MAGIC){__atomic_fetch_and(s+1,~1u,__ATOMIC_RELEASE);return is_half?result(recipe,-10,0,0):0;}
 uint32_t boot=s[2];flags=__atomic_fetch_and(s+3,~2u,__ATOMIC_ACQ_REL);int stage;
 if((!boot||!is_half||(flags&2u))&&!m10v_half_pair_reset())stage=result(recipe,-12,boot,flags);
 else if(!is_half)stage=result(recipe,3u,0,0);
 else stage=camera_impl(context);
 /* A concurrent closing destructor is draining this busy operation and
  * cannot free the owner until this release. Preserve its closing bit. */
 if(stage==-9||stage==-12)s[2]=0u;else s[2]=1u;
 if(stage==1)__atomic_fetch_or(s+3,1u,__ATOMIC_RELEASE);
 else if(stage==2||stage==3)__atomic_fetch_and(s+3,~1u,__ATOMIC_RELEASE);
 __atomic_fetch_and(s+1,~1u,__ATOMIC_RELEASE);
 return stage;
}
