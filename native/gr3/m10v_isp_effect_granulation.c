#include "m10v_isp_effect_granulation.h"
#include "m10v_isp_effect_memory.h"
#define U(x) ((uint32_t)(uintptr_t)(x))
#define MAGIC 0x474e5031u
extern void m10v_isp_effect_granulation_return(void);
static int ram(uint32_t p,uint32_t n){return !(p&3u)&&p>=0x55000000u&&p<=0x80000000u-n;}
static uint32_t word(const void *p,uint32_t n){return *(const uint32_t*)((const uint8_t*)p+n);}
static void yield(void){((void(*)(uint32_t))0x536b0a74u)(1);}
static void hold(m10v_isp_effect_granulation_info *i){i->failed=1;for(;;){i->wait_failures++;yield();}}
/* Runs BEFORE the original pitch*height/capacity calculation. Stock calls and
 * existing prepared textures retain the original registers and alignment.
 * The luma source is an existing native image plane, whose byte stride and
 * ROI address must be preserved, just as on the normal image loader. */
void m10v_isp_effect_granulation_setup(uint32_t *f,uint32_t r[14]){
 if(!f||f[-1]!=U(m10v_isp_effect_granulation_return))return;
 m10v_isp_effect_granulation_info *i=(void*)(uintptr_t)f[2];
 if(!i)for(;;)yield();
 if(i->magic!=MAGIC||i->nonce!=(MAGIC^U(i)^i->context^i->noise_plane^i->noise_stride)||i->context!=f[-0x63c/4])hold(i);
 if(!i->noise_stride)return;
 uint32_t w=f[-0x64c/4],h=f[-0x644/4],pitch=i->noise_stride;
 if(!r||!w||!h||pitch<w||pitch>32768u||(pitch&3u)||pitch*h!=i->noise_bytes||i->capacity!=i->noise_bytes||f[1]!=i->noise_plane||!m10v_isp_effect_buffer_span(i->noise_plane,i->noise_bytes))hold(i);
 f[-0x648/4]=i->noise_plane;f[-0x650/4]=pitch;
 r[7]=i->noise_plane;r[12]=0;r[13]=pitch;
}
static m10v_isp_effect_granulation_info *owned(uint32_t *f,int rng){
 if(!f||f[-1]!=U(m10v_isp_effect_granulation_return))return 0;
 m10v_isp_effect_granulation_info *i=(void*)(uintptr_t)f[2];
 /* Exact private return site establishes that sixth argument is our full info. */
 if(!i)for(;;)yield();
 if(i->magic!=MAGIC||i->nonce!=(MAGIC^U(i)^i->context^i->noise_plane^i->noise_stride))hold(i);
 uint32_t plane=i->noise_stride?f[1]:(f[1]+15u)&~15u;
 if(!i->context||i->context!=f[-0x63c/4]||!plane||plane!=i->noise_plane||i->capacity<i->noise_bytes)hold(i);
 if(rng){uint32_t width=f[-0x650/4],height=f[-0x644/4];
  if(plane!=f[-0x648/4]||!width||!height||width>65536u||height>65535u||width*height>i->noise_bytes)hold(i);
 }else if(i->rng_skipped!=1)hold(i);
 return i;
}
int m10v_isp_effect_granulation_is_owned(uint32_t *f){return owned(f,0)!=0;}
int m10v_isp_effect_granulation_rng(uint32_t *f){m10v_isp_effect_granulation_info *i=owned(f,1);if(!i)return 0;if(i->rng_skipped)hold(i);i->rng_skipped=1;return 1;}
void m10v_isp_effect_granulation_submit(uint32_t *f,void *graph){
 m10v_isp_effect_granulation_info *i=owned(f,0);if(!i)return;
 if(!graph||i->submitted||word(graph,0x38)!=i->context+4)hold(i);
 const int16_t *curves=(const void*)(uintptr_t)i->curves;
 const uint32_t offsets[3]={0x5c,0x6c,0x60},duplicates[3]={0x64,0x70,0x68};
 for(uint32_t c=0;c<3;c++){
  uint32_t p=word(graph,offsets[c]);
  if(!p||(p&1)||p!=word(graph,duplicates[c])||word(graph,0x74+c*8)!=256||word(graph,0x78+c*8)!=256)hold(i);
 }
 if(curves){
  for(uint32_t n=0;n<768;n++)if(curves[n]<0||curves[n]>255)hold(i);
  for(uint32_t c=0;c<3;c++){int16_t *out=(void*)(uintptr_t)word(graph,offsets[c]);for(uint32_t n=0;n<256;n++)out[n]=curves[c*256+n];}
 }
 i->submitted=U(graph);
}
uint32_t m10v_isp_effect_granulation_wait(void *ctx,uint32_t mask,uint32_t *f){
 m10v_isp_effect_granulation_info *i=owned(f,0);
 if(i&&(U(ctx)!=i->context||mask!=0x400||!i->submitted))hold(i);
 uint32_t result=((uint32_t(*)(void*,uint32_t))0x5368a510u)(ctx,mask);
 if(i){while(result!=1){i->wait_failures++;yield();result=((uint32_t(*)(void*,uint32_t))0x5368a510u)(ctx,mask);}i->completed=1;}
 return result;
}
static void unlock(void *s,m10v_isp_effect_granulation_info *i){
 if(((uint32_t(*)(void*))0x536a8544u)((uint8_t*)s+0x14)!=1)hold(i);
 if(((uint32_t(*)(void*))0x536ae870u)((uint8_t*)s+0x90)!=1)hold(i);
}
uint32_t m10v_isp_effect_granulation_release(void *g,uint32_t *f){
 m10v_isp_effect_granulation_info *i=owned(f,0);
 if(i){
  if(U(g)!=i->submitted||!i->completed||i->released||!((uint8_t*)g)[0x40]||word(g,0x38)!=i->context+4)hold(i);
  /* Native submit5376c4b0 resolves the graph-controller wrapper's +4
   * service;5376c6e8..f0 stores THAT nested owner at graph+9c. The wrapper
   * itself is a different object and must never substitute for the service. */
  uint32_t wrapper=word((void*)(uintptr_t)i->context,8);
  if(!ram(wrapper,8))hold(i);
  uint32_t service=word((void*)(uintptr_t)wrapper,4);
  if(!ram(service,0x10c)||word(g,0x9c)!=service)hold(i);
  void *s=(void*)(uintptr_t)service;uint8_t *info=(uint8_t*)g+0xa0;
  for(;;){
   if(((uint32_t(*)(void*,uint32_t))0x536ae71cu)((uint8_t*)s+0x90,0xffffffffu)!=1){i->wait_failures++;yield();continue;}
   if(((uint32_t(*)(void*,uint32_t))0x536a848cu)((uint8_t*)s+0x14,5000)!=1){if(((uint32_t(*)(void*))0x536ae870u)((uint8_t*)s+0x90)!=1)hold(i);i->wait_failures++;yield();continue;}
   uint32_t c=info[3],mask=word(info,0x78);
   if(c>2||!info[0x74]||!mask||word(s,0x100+c*4)!=mask||word(s,0x40+c*0x1c)!=i->context+4||!((uint8_t*)s)[0xfc])hold(i);
   void *d=(void*)(uintptr_t)word(s,0x24);int safe=0;
   if(((uint8_t*)s)[0xfc]==1&&((uint32_t(*)(void*))0x53778490u)(d)==0){((void(*)(void*,uint32_t))0x53778458u)(d,0);safe=((uint32_t(*)(void*))0x53778474u)(d)==0;}
   unlock(s,i);if(safe)break;i->wait_failures++;yield();
  }
 }
 uint32_t result=((uint32_t(*)(void*))0x5376c044u)(g);
 if(i){if(!result||word(g,0x9c)||((uint8_t*)g)[0x40])hold(i);i->released=1;}
 return result;
}
static int run(void *ctx,void *dst,const void *src,uint32_t strength,void *plane,uint32_t bytes,const int16_t curves[3][256],uint32_t noise_stride){
 if(!ctx||!dst||!src||!plane||(U(plane)&(noise_stride?3u:15u))||strength<1||strength>3||(U(dst)&3)||(U(src)&3)||(U(ctx)&3)||(curves&&(U(curves)&1)))return -1;
 const uint8_t *d=dst,*s=src;uint32_t w=*(const uint16_t*)(d+0x10),h=*(const uint16_t*)(d+0x12),pitch=(w+15u)&~15u;
 if(d[0]<1||d[0]>2||s[0]<1||s[0]>2||!w||!h||*(const uint16_t*)(s+0x10)!=w||*(const uint16_t*)(s+0x12)!=h||pitch*h>bytes||*(const uint16_t*)(d+0x14)<w||*(const uint16_t*)(s+0x14)<w||!word(dst,4)||!word(src,4))return -1;
 if(curves)for(uint32_t c=0;c<3;c++)for(uint32_t n=0;n<256;n++)if(curves[c][n]<0||curves[c][n]>255)return -1;
 if(noise_stride&&(noise_stride<w||noise_stride>32768u||(noise_stride&3u)||noise_stride*h!=bytes||!m10v_isp_effect_buffer_span(U(plane),bytes)))return -1;
 m10v_isp_effect_granulation_info i={bytes,MAGIC,U(ctx),U(plane),bytes,U(curves),0,0,0,0,0,0,0,noise_stride};i.nonce=MAGIC^U(&i)^U(ctx)^U(plane)^noise_stride;
 uint32_t result=m10v_isp_effect_granulation_call(ctx,dst,src,strength,plane,&i);
 return result==1&&!i.failed&&i.completed==1&&i.released==1&&i.rng_skipped==1?1:-4;
}
int m10v_isp_effect_granulation_owned(void *ctx,void *dst,const void *src,uint32_t strength,void *plane,uint32_t bytes,const int16_t curves[3][256]){
 return run(ctx,dst,src,strength,plane,bytes,curves,0);
}
int m10v_isp_effect_granulation_luma(void *ctx,void *mask,const uint32_t photo[8],const int16_t curves[3][256]){
 if(!mask||!photo||!curves||(U(mask)&3u)||(U(photo)&3u))return -1;
 uint32_t *m=mask,w=m[4]&65535u,h=m[4]>>16,ph=photo[4]>>16,pitch=photo[5]&65535u;
 uint32_t format=photo[0]&255u,factor=format==1?1u:2u;
 if((format!=1&&format!=2)||!h||ph!=h*factor||(photo[4]&65535u)!=w||pitch<w||pitch>16384u||photo[6]||m[6])return -1;
 uint32_t n=pitch*ph,mn=(m[5]&65535u)*h;
 if(!m10v_isp_effect_buffer_span(photo[1],n)||!m10v_isp_effect_buffer_span(m[1],mn)||
    (photo[1]<m[1]+mn&&m[1]<photo[1]+n))return -1;
 return run(ctx,mask,mask,1,(void*)(uintptr_t)photo[1],n,curves,pitch*factor);
}
