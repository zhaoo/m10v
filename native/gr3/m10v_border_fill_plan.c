#include "m10v_border_fill_plan.h"
#include <stddef.h>
_Static_assert(sizeof(m10v_border_fill_plan_info)==5820,"fill metadata ABI");
_Static_assert(offsetof(m10v_border_fill_plan_info,descriptors)==1596,"fill references ABI");
static int overlap(uint32_t a,uint32_t an,uint32_t b,uint32_t bn){return a<b+bn&&b<a+an;}
static uint32_t slice_rows(uint32_t width,uint32_t height){
    uint32_t low=1,high=height/2u;
    while(low<high){uint32_t mid=(low+high+1u)/2u;
        if(width*mid*2u<0x100000u)low=mid;else high=mid-1u;}
    return low*2u;
}
static int outside(m10v_border_rect r,m10v_border_rect inner){
    return r.x+r.width<=inner.x||r.x>=inner.x+inner.width||
           r.y+r.height<=inner.y||r.y>=inner.y+inner.height;
}
static void emit(m10v_border_fill_plan_info *out,uint32_t base,uint32_t index,
                 const uint32_t canvas[8],m10v_border_rect r,uint16_t luminance){
    for(uint32_t i=0;i<8u;++i)((volatile uint32_t *)out->descriptors[index])[i]=canvas[i];
    out->descriptors[index][4]=r.width|(r.height<<16);
    out->descriptors[index][6]=r.x|(r.y<<16);
    m10v_border_fill_rectangle *entry=&out->rectangles[index];
    entry->destination=base+offsetof(m10v_border_fill_plan_info,descriptors)+index*32u;
    entry->y=luminance;entry->cb=entry->cr=128;entry->reserved=0;
}
int m10v_border_fill_plan(const m10v_border_canvas_info *c,uint32_t base,
                          m10v_border_fill_plan_info *out){
    if(!c)return -1;if(c->layout.style==M10V_BORDER_OFF)return 0;
    if(!out||(base&3u)||base<0x55000000u||base>0x80000000u-sizeof(*out))return -1;
    const m10v_border_storage_info *l=&c->layout;
    m10v_border_rect inner=l->inner;
    uint32_t stride=l->stride,rows=l->allocated_height,span=stride*rows;
    if(l->style>M10V_BORDER_FILM||l->format!=1u||l->outer.x||l->outer.y||
       stride<l->outer.width||stride>16384u||(stride&63u)||
       rows<l->outer.height||rows>16384u||(rows&7u)||
       l->outer.width<2u||l->outer.height<2u||
       !inner.x||!inner.y||!inner.width||!inner.height||
       ((inner.x|inner.y|inner.width|inner.height)&1u)||
       inner.x>l->outer.width||inner.width>=l->outer.width-inner.x||
       inner.y>l->outer.height||inner.height>=l->outer.height-inner.y||
       l->y_bytes!=span||l->chroma_bytes!=span||l->total_bytes!=2u*span||
       (c->canvas[0]&255u)!=1u||c->canvas[3]||c->canvas[6]||(c->canvas[7]&255u)!=2u||
       c->canvas[4]!=(l->outer.width|(l->outer.height<<16))||c->canvas[5]!=(stride|(rows<<16))||
       ((c->canvas[1]|c->canvas[2])&7u)||c->canvas[1]<0x55000000u||c->canvas[2]<0x55000000u||
       c->canvas[1]>0x80000000u-span||c->canvas[2]>0x80000000u-span||
       overlap(c->canvas[1],span,c->canvas[2],span)||
       overlap(base,sizeof(*out),c->canvas[1],span)||overlap(base,sizeof(*out),c->canvas[2],span)||
       c->inner[1]!=c->canvas[1]+inner.y*stride+inner.x||
       c->inner[2]!=c->canvas[2]+inner.y*stride+inner.x||
       c->inner[4]!=(inner.width|(inner.height<<16))||c->inner[5]!=(stride|(inner.height<<16)))return -1;
    m10v_border_rect bars[4]={{0,0,stride,inner.y},
        {0,inner.y+inner.height,stride,rows-inner.y-inner.height},
        {0,inner.y,inner.x,inner.height},
        {inner.x+inner.width,inner.y,stride-inner.x-inner.width,inner.height}};
    uint32_t slices[4],count=0;
    for(uint32_t b=0;b<4u;++b){
        slices[b]=slice_rows(bars[b].width,bars[b].height);
        if(!slices[b]||bars[b].width*slices[b]>=0x100000u)return -1;
        for(uint32_t y=0;y<bars[b].height;y+=slices[b])
            if(++count>M10V_BORDER_FILL_BUNDLE_MAX)return -1;
    }
    for(uint32_t b=0;b<2u;++b){
        const m10v_border_storage_holes *h=&l->holes[b];
        if((l->style==M10V_BORDER_POLAROID&&h->count)||
           (l->style==M10V_BORDER_FILM&&(!h->count||h->count>64u))||
           h->dx < -16384||h->dx>16384||h->dy < -16384||h->dy>16384)return -1;
        for(uint32_t i=0;i<h->count;++i){
            if(h->first.x>l->outer.width||h->first.y>l->outer.height)return -1;
            int32_t x=(int32_t)h->first.x+(int32_t)i*h->dx,y=(int32_t)h->first.y+(int32_t)i*h->dy;
            m10v_border_rect r={(uint32_t)x,(uint32_t)y,h->first.width,h->first.height};
            if(x<0||y<0||!r.width||!r.height||((r.x|r.y|r.width|r.height)&1u)||
               r.x>l->outer.width||r.width>l->outer.width-r.x||
               r.y>l->outer.height||r.height>l->outer.height-r.y||
               r.width*r.height>=0x100000u||!outside(r,inner)||++count>M10V_BORDER_FILL_BUNDLE_MAX)return -1;
        }
    }
    uint32_t n=0;
    for(uint32_t b=0;b<4u;++b){
        for(uint32_t y=0;y<bars[b].height;y+=slices[b]){
            m10v_border_rect r=bars[b];r.y+=y;r.height=bars[b].height-y;
            if(r.height>slices[b])r.height=slices[b];
            emit(out,base,n++,c->canvas,r,l->style==M10V_BORDER_POLAROID?255u:0u);
        }
    }
    for(uint32_t b=0;b<2u;++b){
        const m10v_border_storage_holes *h=&l->holes[b];
        for(uint32_t i=0;i<h->count;++i){m10v_border_rect r=h->first;
            r.x=(uint32_t)((int32_t)r.x+(int32_t)i*h->dx);
            r.y=(uint32_t)((int32_t)r.y+(int32_t)i*h->dy);
            emit(out,base,n++,c->canvas,r,224u);
        }
    }
    out->bytes=12u+12u*count;out->count=count;out->tag=M10V_BORDER_FILL_BUNDLE_TAG;
    return 1;
}
