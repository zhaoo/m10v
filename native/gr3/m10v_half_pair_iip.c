#include "m10v_half_pair_iip.h"
#include "m10v_border_wait_guard.h"
#include "m10v_border_fill_plan.h"
#include <stddef.h>
#include "m10v_debug.h"
#define TRACE(p,a,b,c) M10V_LOG(223u,(p),(a),(b),(c))
extern void border_recovery_transfer_body_hook(void),border_recovery_transfer_wait_hook(void);
extern void border_recovery_fill_body_hook(void),border_recovery_fill_wait_hook(void);
extern void border_recovery_resize_body_hook(void),border_recovery_resize_wait_hook(void);
extern void border_recovery_resize_dma_wait_hook(void),border_recovery_fill_release_hook(void),border_recovery_resize_release_hook(void);
#define U(p) ((uint32_t)(uintptr_t)(p))
typedef struct {uint32_t d[8],yn,cn,w,h,stride,rows;} image;
typedef struct {uint32_t tag,count,bytes;m10v_border_fill_rectangle rectangle;uint32_t d[8];} separator_fill;
typedef struct {separator_fill separator;m10v_border_fill_plan_info fills;image source[2],canvas,preview[2];uint32_t tiles[2][8],scaled[2][8];} composition;
static int ram(uint32_t p,uint32_t n){return !(p&3u)&&p>=0x55000000u&&p<0x80000000u&&n<=0x80000000u-p;}
static uint32_t word(uint32_t p){return *(const volatile uint32_t *)(uintptr_t)p;}
static void copy8(uint32_t *d,const uint32_t *s){for(uint32_t i=0;i<8u;i++)((volatile uint32_t *)d)[i]=s[i];}
static int overlap(uint32_t a,uint32_t an,uint32_t b,uint32_t bn){return a<b+bn&&b<a+an;}
static void hold(void){for(;;)((void(*)(uint32_t))0x536b0a74u)(1u);}
static int branch(uint32_t at,uint32_t target){int32_t delta=(int32_t)(target-at-8u);return !(target&3u)&&delta>=-(1<<25)&&delta<(1<<25)&&word(at)==(0xeb000000u|(((uint32_t)delta>>2)&0xffffffu));}
int m10v_half_pair_iip_ready(void){
 if(word(0x5369a010u)!=0xe3a00058u||word(0x536589fcu)!=0xe3a00068u||word(0x53672bacu)!=0xe3a00058u)return 0;
 if(!branch(0x5369a01cu,U(m10v_border_transfer_construct))||!branch(0x5369ac4cu,U(border_recovery_transfer_body_hook))||!branch(0x5369a478u,U(border_recovery_transfer_wait_hook))||!branch(0x534aae28u,U(m10v_border_client_wait))||!branch(0x53658a08u,U(m10v_border_fill_construct))||!branch(0x536594a0u,U(border_recovery_fill_body_hook))||!branch(0x5376a370u,U(border_recovery_fill_wait_hook))||!branch(0x53672bb8u,U(m10v_border_resize_construct))||!branch(0x53674014u,U(border_recovery_resize_body_hook))||!branch(0x5377160cu,U(border_recovery_resize_wait_hook))||!branch(0x53673244u,U(border_recovery_resize_dma_wait_hook))||!branch(0x5367331cu,U(border_recovery_resize_dma_wait_hook))||!branch(0x53673384u,U(border_recovery_resize_dma_wait_hook))||!branch(0x5376a38cu,U(border_recovery_fill_release_hook))||!branch(0x53771968u,U(border_recovery_resize_release_hook)))return 0;
 static const uint32_t factories[3][5]={{0x5369a0e8u,4u,0x44u,0x42575431u,0x58u},{0x53658a68u,4u,0x58u,0x42465731u,0x68u},{0x53672c48u,12u,0x48u,0x42525731u,0x58u}};
 for(uint32_t i=0;i<3;i++){const uint32_t *f=factories[i];TRACE(100u+i*2u,f[0],0u,0u);uint32_t factory=((uint32_t(*)(void))(uintptr_t)f[0])();TRACE(101u+i*2u,f[0],factory,0u);if(!ram(factory,16))return 0;uint32_t worker=word(factory+f[1]);if(!ram(worker,f[4])||word(worker+f[2])!=f[3])return 0;}
 return 1;
}
static int load(image *out,const uint32_t *d,int full){
 if(!ram(U(d),32))return 0;copy8(out->d,d);
 uint32_t format=d[0]&255u;out->w=d[4]&65535u;out->h=d[4]>>16;out->stride=d[5]&65535u;out->rows=d[5]>>16;
 if((format!=1u&&format!=2u)||!out->w||!out->h||out->w>8192u||out->h>8192u||((out->w|out->h|out->stride|out->rows)&1u)||out->stride<out->w||out->stride>8192u||out->rows<out->h||out->rows>8192u||d[3]||d[6]||(d[7]&255u)!=2u||((d[1]|d[2])&7u))return 0;
 out->yn=full?out->stride*out->rows:(out->h-1u)*out->stride+out->w;
 out->cn=full?(format==2u?out->yn/2u:out->yn):(format==2u?(out->h/2u-1u)*out->stride+out->w:out->yn);
 return ram(d[1],out->yn)&&ram(d[2],out->cn)&&!overlap(d[1],out->yn,d[2],out->cn);
}
static int images_overlap(const image *a,const image *b){return overlap(a->d[1],a->yn,b->d[1],b->yn)||overlap(a->d[1],a->yn,b->d[2],b->cn)||overlap(a->d[2],a->cn,b->d[1],b->yn)||overlap(a->d[2],a->cn,b->d[2],b->cn);}
static int metadata_overlap(uint32_t p,uint32_t n,const image *a){return overlap(p,n,a->d[1],a->yn)||overlap(p,n,a->d[2],a->cn);}
static void cache_pre(m10v_border_native_client *client,const uint32_t d[8]){((void(*)(void*,const void*))0x534ab1a4u)(client,d);}
static void cache_post(m10v_border_native_client *client,const uint32_t d[8]){((void(*)(void*,const void*))0x534ab60cu)(client,d);}
static void transfer(m10v_border_native_client *client,const uint32_t src[8],const uint32_t dst[8]){
 TRACE(40u,U(client),src[4],dst[4]);if(!m10v_border_client_prepare(client,0x03050006u,0x400u))hold();TRACE(41u,U(client),src[1],dst[1]);
 ((void(*)(void*,uint32_t,const void*,const void*,uint32_t))0x534ab7a0u)(client,0u,src,dst,1u);TRACE(42u,U(client),client->pending,client->completed);
 if(!m10v_border_client_done(client)||client->completed!=1u)hold();
}
int m10v_half_pair_iip_copy(uint32_t token,const uint32_t source[8],const uint32_t destination[8]){
 image src,dst;TRACE(30u,token,U(source),U(destination));if(!token||!load(&src,source,0)||!load(&dst,destination,1)||(src.d[0]&255u)!=1u||(dst.d[0]&255u)!=1u||src.w!=dst.w||src.h!=dst.h||images_overlap(&src,&dst)||metadata_overlap(U(source),32,&src)||metadata_overlap(U(source),32,&dst)||metadata_overlap(U(destination),32,&src)||metadata_overlap(U(destination),32,&dst)||!m10v_half_pair_iip_ready())return 0;
 /* Original image-cache helpers cover stride*height from each plane origin,
  * even for a cropped source. The caller authenticates those native cache
  * spans inside its complete owner bank before admitting this operation. */
 TRACE(33u,token,0u,0u);uint32_t gate=m10v_border_stage_enter(token);TRACE(34u,token,gate,0u);if(!gate)return 0;
 m10v_border_native_client client;TRACE(35u,token,U(&client),0u);m10v_border_client_construct(&client);TRACE(36u,token,U(&client),0u);
 TRACE(37u,token,src.d[1],src.d[5]);cache_pre(&client,src.d);TRACE(38u,token,dst.d[1],dst.d[5]);cache_pre(&client,dst.d);TRACE(39u,token,0u,0u);transfer(&client,src.d,dst.d);TRACE(44u,token,0u,0u);cache_post(&client,dst.d);TRACE(45u,token,0u,0u);
 if(!m10v_border_client_destroy_if_done(&client)||!m10v_border_stage_leave(gate,token))hold();return 1;
}
static uint32_t divide(uint32_t a,uint32_t b){uint32_t q=0,r=0;for(uint32_t i=32;i;i--){r=(r<<1)|((a>>(i-1u))&1u);if(r>=b){r-=b;q|=1u<<(i-1u);}}return q;}
static int fill_image(composition *p,const image *im){
 uint32_t base=p->fills.count;
 for(uint32_t row=0;row<im->rows;row+=128u){uint32_t rows=im->rows-row;if(rows>128u)rows=128u;
  if(base>=M10V_BORDER_FILL_BUNDLE_MAX||im->stride*rows>=0x100000u)return 0;
  uint32_t *d=p->fills.descriptors[base];copy8(d,im->d);d[4]=im->stride|(rows<<16);d[6]=row<<16;
  m10v_border_fill_rectangle *r=&p->fills.rectangles[base];r->destination=U(d);r->y=16u;r->cb=r->cr=128u;r->reserved=0u;base++;
 }
 p->fills.count=base;return 1;
}
/* A film-style center mask keeps the accepted JPEG dimensions and placement.
 * Native Fill covers the inner edges after both Transfers and before Resize;
 * no CPU pixels, resampling, larger frame allocation or retained stack pointer. */
static int separator_plan(composition *p,uint32_t orientation){
 const image *o=&p->canvas;uint32_t horizontal=orientation==1u||orientation==3u;
 uint32_t axis=horizontal?o->w:o->h,gap=(divide(axis,25u)+7u)&~7u;
 if(!gap||gap>=axis)return 0;
 uint32_t width=horizontal?gap:o->w,height=horizontal?o->h:gap;
 if(width*height>=0x100000u)return 0;
 separator_fill *s=&p->separator;s->tag=M10V_BORDER_FILL_BUNDLE_TAG;s->count=1;s->bytes=24;
 copy8(s->d,o->d);s->d[4]=width|(height<<16);s->d[6]=horizontal?(axis-gap)/2u:((axis-gap)/2u)<<16;
 s->rectangle.destination=U(s->d);s->rectangle.y=16;s->rectangle.cb=s->rectangle.cr=128;s->rectangle.reserved=0;
 return 1;
}
static void tile(uint32_t d[8],const image *out,uint32_t w,uint32_t h,uint32_t x,uint32_t y){copy8(d,out->d);d[4]=w|(h<<16);d[6]=x|(y<<16);}
static void fit(uint32_t d[8],const image *source,const image *dest){
 uint32_t w=dest->w,h=divide(source->h*w,source->w);if(h>dest->h){h=dest->h;w=divide(source->w*h,source->h);}w&=~1u;h&=~1u;copy8(d,dest->d);d[4]=w|(h<<16);d[6]=(((dest->w-w)/2u)&~1u)|((((dest->h-h)/2u)&~1u)<<16);
}
int m10v_half_pair_iip_compose(uint32_t token,const uint32_t first[8],const uint32_t second[8],const uint32_t output[8],const uint32_t previews[2][8],uint32_t orientation){
 if(!token||!first||!second||!output||!previews)return 0;
 composition *p=((void*(*)(uint32_t))0x536af2a8u)(sizeof(*p));if(!p)return 0;
 if(!ram(U(p),sizeof(*p)))hold();
 int ok=load(&p->source[0],first,1)&&load(&p->source[1],second,1)&&load(&p->canvas,output,1)&&load(&p->preview[0],previews[0],1)&&load(&p->preview[1],previews[1],1);
 if(ok){
  image *a=&p->source[0],*b=&p->source[1],*o=&p->canvas;uint32_t w=a->w,h=a->h;
  ok=(a->d[0]&255u)==1u&&(b->d[0]&255u)==1u&&(o->d[0]&255u)==1u&&w==b->w&&h==b->h&&w<=2992u&&h<=4000u&&!(w&15u)&&((orientation==1u||orientation==3u)?(o->w==2u*w&&o->h==h):(orientation==6u||orientation==8u)?(o->w==w&&o->h==2u*h):0);
  if(ok){tile(p->tiles[0],o,w,h,orientation==3u?w:0u,orientation==6u?h:0u);tile(p->tiles[1],o,w,h,orientation==1u?w:0u,orientation==8u?h:0u);fit(p->scaled[0],o,&p->preview[0]);fit(p->scaled[1],o,&p->preview[1]);if(!(p->scaled[0][4]&65535u)||!(p->scaled[0][4]>>16)||!(p->scaled[1][4]&65535u)||!(p->scaled[1][4]>>16))ok=0;}
 }
 if(ok){
  const image *all[5]={&p->source[0],&p->source[1],&p->canvas,&p->preview[0],&p->preview[1]};
  for(uint32_t i=0;i<5u;i++){if(metadata_overlap(U(p),sizeof(*p),all[i])||metadata_overlap(U(first),32,all[i])||metadata_overlap(U(second),32,all[i])||metadata_overlap(U(output),32,all[i])||metadata_overlap(U(previews),64,all[i]))ok=0;for(uint32_t j=0;j<i;j++)if(images_overlap(all[i],all[j]))ok=0;}
 }
 if(ok)ok=separator_plan(p,orientation);
 if(ok){p->fills.count=0;ok=fill_image(p,&p->canvas)&&fill_image(p,&p->preview[0])&&fill_image(p,&p->preview[1]);p->fills.tag=M10V_BORDER_FILL_BUNDLE_TAG;p->fills.bytes=12u+12u*p->fills.count;}
 if(!ok||!m10v_half_pair_iip_ready()){((void(*)(void*))0x536af2e4u)(p);return 0;}
 uint32_t gate=m10v_border_stage_enter(token);if(!gate){((void(*)(void*))0x536af2e4u)(p);return 0;}
 m10v_border_native_client client;TRACE(35u,token,U(&client),0u);m10v_border_client_construct(&client);TRACE(36u,token,U(&client),0u);
 cache_pre(&client,p->source[0].d);cache_pre(&client,p->source[1].d);cache_pre(&client,p->canvas.d);cache_pre(&client,p->preview[0].d);cache_pre(&client,p->preview[1].d);
 if(!m10v_border_fill_bundle_submit(&client,(const m10v_border_fill_bundle *)&p->fills))hold();
 transfer(&client,p->source[0].d,p->tiles[0]);transfer(&client,p->source[1].d,p->tiles[1]);
 if(!m10v_border_fill_bundle_submit(&client,(const m10v_border_fill_bundle *)&p->separator))hold();
 for(uint32_t i=0;i<2u;i++){
  if(!m10v_border_client_prepare(&client,0x03020002u,0x40u))hold();
  ((void(*)(void*,const void*,const void*,uint32_t))0x534ab6b8u)(&client,p->canvas.d,p->scaled[i],1u);
  if(!m10v_border_client_done(&client)||client.completed!=1u)hold();
 }
 cache_post(&client,p->canvas.d);cache_post(&client,p->preview[0].d);cache_post(&client,p->preview[1].d);
 if(!m10v_border_client_destroy_if_done(&client)||!m10v_border_stage_leave(gate,token))hold();
 ((void(*)(void*))0x536af2e4u)(p);return 1;
}
