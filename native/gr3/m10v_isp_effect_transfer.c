#include "m10v_isp_effect_transfer.h"
#include <stddef.h>
#include "m10v_isp_effect_memory.h"
static int overlap(uintptr_t a,uint32_t an,uintptr_t b,uint32_t bn){
    return a<b+bn&&b<a+an;
}
int m10v_isp_effect_transfer_plan_format(const m10v_isp_effect_texture *t,
    uint32_t work,uint32_t capacity,uint32_t w,uint32_t h,
    uint32_t sw,uint32_t sh,uint32_t phase,uint32_t format,m10v_isp_effect_transfer *out){
    if(!w&&!h)return 0;
    if(!t||!out||((uintptr_t)t&3u)||((uintptr_t)out&3u)||
       (uintptr_t)t>UINTPTR_MAX-sizeof(*t)||(uintptr_t)out>UINTPTR_MAX-sizeof(*out)||
       overlap((uintptr_t)t,sizeof(*t),(uintptr_t)out,sizeof(*out)))return -1;
    if((format!=1u&&format!=2u)||!w||!h||w>6144u||h>6144u||((w|h|sw|sh)&1u)||
       !sw||!sh||sw>t->width||sh>t->height||phase>63u||
       !t->width||!t->height||((t->width|t->height)&1u)||
       t->width>3072u||t->height>2048u||t->stride<t->width||t->stride>3072u||
       (t->stride&63u)||t->base<0x540b6000u||(t->base&63u))return -1;
    uint32_t source_y=t->stride*t->height,source_bytes=source_y+source_y/2u;
    if(t->bytes!=source_bytes||source_bytes>0x55000000u-t->base||t->base>=0x55000000u)return -1;
    uint32_t stride=(w+15u)&~15u,y=stride*h,bytes=y+(format==1u?y:y/2u);
    if((work&15u)||!m10v_isp_effect_buffer_span(work,bytes)||capacity<bytes||
       overlap((uintptr_t)out,sizeof(*out),work,bytes)||
       overlap((uintptr_t)t,sizeof(*t),work,bytes))return -1;
    uint32_t x=(phase&7u)*2u,top=(phase>>3)*2u;
    if(x>t->width-sw)x=0;
    if(top>t->height-sh)top=0;
    m10v_isp_effect_transfer p={
        {2u,t->base,t->base+source_y,0u,sw|(sh<<16),t->stride|(t->height<<16),x|(top<<16),2u},
        {format,work,work+y,0u,w|(h<<16),stride|(h<<16),0u,2u},bytes};
    for(uint32_t i=0;i<8u;++i){((volatile uint32_t *)out->source)[i]=p.source[i];((volatile uint32_t *)out->destination)[i]=p.destination[i];}
    out->workspace_bytes=bytes;
    return 1;
}
int m10v_isp_effect_transfer_plan(const m10v_isp_effect_texture *t,
    uint32_t work,uint32_t capacity,uint32_t w,uint32_t h,
    uint32_t sw,uint32_t sh,uint32_t phase,m10v_isp_effect_transfer *out){
    return m10v_isp_effect_transfer_plan_format(t,work,capacity,w,h,sw,sh,phase,2u,out);
}
