#include "m10v_border_canvas.h"
static int fits(uint32_t p,uint32_t n,uint32_t base,uint32_t bytes){
    return p>=base&&n<=bytes&&p-base<=bytes-n;
}
int m10v_border_canvas_plan(uint32_t style,uint32_t orientation,
                            const uint32_t inner[8],uint32_t y_base,
                            uint32_t c_base,uint32_t plane_bytes,
                            m10v_border_canvas_info *out){
    if(!inner||!out)return -1;
    m10v_border_canvas_info result;
    uint32_t w=inner[4]&65535u,h=inner[4]>>16;
    if(m10v_border_storage_layout(style,w,h,orientation,1,&result.layout))return -1;
    for(uint32_t i=0;i<8u;++i)result.inner[i]=result.canvas[i]=inner[i];
    if(style!=M10V_BORDER_OFF){
        uint32_t stride=inner[5]&65535u,rows=inner[5]>>16;
        if((inner[0]&255u)!=1u||inner[3]||inner[6]||(inner[7]&255u)!=2u||
           stride<result.layout.outer.width||stride>16384u||(stride&63u)||
           rows<h||rows>16384u||((inner[1]|inner[2]|y_base|c_base)&7u)||
           y_base<0x55000000u||c_base<y_base||c_base>=0x80000000u||!plane_bytes||
           plane_bytes>0x80000000u-c_base||c_base-y_base<plane_bytes)return -1;
        uint32_t offset=result.layout.inner.y*stride+result.layout.inner.x;
        if(inner[1]<offset||inner[2]<offset)return -1;
        uint32_t y=inner[1]-offset,c=inner[2]-offset;
        uint32_t span=stride*result.layout.allocated_height;
        if((y|c)&7u||!fits(y,span,y_base,plane_bytes)||!fits(c,span,c_base,plane_bytes)||
           !fits(inner[1],stride*h,y_base,plane_bytes)||
           !fits(inner[2],stride*h,c_base,plane_bytes))return -1;
        result.inner[5]=stride|(h<<16);
        result.canvas[1]=y;result.canvas[2]=c;
        result.canvas[4]=result.layout.outer.width|(result.layout.outer.height<<16);
        result.canvas[5]=stride|(result.layout.allocated_height<<16);
        result.layout.stride=stride;result.layout.y_bytes=span;
        result.layout.chroma_bytes=span;result.layout.total_bytes=span*2u;
    }
    for(uint32_t i=0;i<sizeof(result)/4u;++i)
        ((volatile uint32_t *)out)[i]=((const uint32_t *)&result)[i];
    return 0;
}
