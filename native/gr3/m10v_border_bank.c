#include "m10v_border_bank.h"
static uint32_t maximum(uint32_t a,uint32_t b){return a>b?a:b;}
static int fits(uint32_t p,uint32_t n,uint32_t base,uint32_t bytes){
    return p>=base&&n<=bytes&&p-base<=bytes-n;
}
static void publish(m10v_border_bank_info *out,const m10v_border_bank_info *in){
    for(uint32_t i=0;i<sizeof(*out)/4u;++i)((volatile uint32_t *)out)[i]=((const uint32_t *)in)[i];
}
int m10v_border_bank_shape(uint32_t style,uint32_t orientation,uint32_t width,
                          uint32_t height,uint32_t bank,uint32_t capacity,
                          m10v_border_bank_info *out){
    if(!out||bank<0x55000000u||bank>=0x80000000u||!capacity||capacity>0x80000000u-bank)return -1;
    m10v_border_bank_info result;
    for(uint32_t i=0;i<sizeof(result)/4u;++i)((uint32_t *)&result)[i]=0;
    if(m10v_border_storage_layout(style,width,height,orientation,1,&result.canvas))return -1;
    result.bank=bank;result.capacity=capacity;
    if(style==M10V_BORDER_OFF){publish(out,&result);return 0;}
    /* Native BackResize aliases main to the cropped source. Reserve the
     * outer canvas at that later288-row start, retain144 source tail rows,
     * and add8 rounded cache rows. This is NOT a live-workspace proof. */
    uint32_t rows=(maximum(288u+result.canvas.allocated_height,
                          288u+result.canvas.inner.y+height+144u)+15u)&~7u;
    uint32_t stride=result.canvas.stride,plane=stride*rows;
    uint32_t base=(bank+63u)&~63u;
    if(!fits(base,plane*2u,bank,capacity))return -1;
    result.source_y=base+(288u+result.canvas.inner.y)*stride+result.canvas.inner.x;
    result.source_c=result.source_y+plane;
    result.plane_bytes=plane;result.preview_base=base+plane*2u;
    result.used_bytes=result.preview_base-bank;
    publish(out,&result);return 0;
}
int m10v_border_bank_plan(uint32_t style,uint32_t orientation,uint32_t bank,
                         uint32_t capacity,const uint32_t images[5][8],
                         m10v_border_bank_info *out){
    if(!images||!out)return -1;
    uint32_t w=images[0][4]&65535u,h=images[0][4]>>16;
    m10v_border_bank_info result;
    if(m10v_border_bank_shape(style,orientation,w,h,bank,capacity,&result))return -1;
    for(uint32_t i=0;i<5u;++i)for(uint32_t j=0;j<8u;++j)result.images[i][j]=images[i][j];
    if(style==M10V_BORDER_OFF){publish(out,&result);return 0;}
    uint32_t small_min=0xffffffffu,small_max=0;
    for(uint32_t i=0;i<5u;++i){
        const uint32_t *d=images[i];
        uint32_t f=d[0]&255u,iw=d[4]&65535u,ih=d[4]>>16,s=d[5]&65535u,rows=d[5]>>16;
        if((f!=1u&&f!=2u)||d[3]||!iw||!ih||((iw|ih|s)&1u)||s<iw||rows<ih||
            s>16384u||rows>16384u||d[6]||
            ((d[7]&255u)!=2u&&!(i==4u&&(d[7]&255u)==0u))||
            (f==2u&&(rows&1u)))return -1;
        uint32_t ybytes=s*rows,cbytes=f==2u?ybytes/2u:ybytes;
        if(!fits(d[1],ybytes,bank,capacity)||!fits(d[2],cbytes,bank,capacity)||
            (d[1]<d[2]+cbytes&&d[2]<d[1]+ybytes)||((d[1]|d[2])&1u))return -1;
        if(i==0u||i==2u){if(f!=1u||iw!=w||ih!=h||rows!=h)return -1;}
        else{
            if(d[1]<small_min)small_min=d[1];if(d[2]<small_min)small_min=d[2];
            if(d[1]+ybytes>small_max)small_max=d[1]+ybytes;
            if(d[2]+cbytes>small_max)small_max=d[2]+cbytes;
        }
    }
    /* BackResize's stock source is displaced by9*16 rows from its main
     * destination. Preserve that relationship: aliasing these two starts
     * changes the native producer/consumer overlap, even if both fit. */
    uint32_t original_stride=images[0][5]&65535u;
    if((images[2][5]&65535u)!=original_stride||
       images[0][1]!=images[2][1]+144u*original_stride||
       images[0][2]!=images[2][2]+144u*original_stride)return -1;
    uint32_t stride=result.canvas.stride;
    uint32_t small_bytes=small_max-small_min;
    if(!fits(result.preview_base,small_bytes,bank,capacity))return -1;
    result.used_bytes=result.preview_base+small_bytes-bank;
    for(uint32_t i=0;i<5u;++i){
        uint32_t *d=result.images[i];
        if(i==0u||i==2u){
            uint32_t displacement=i==0u?0u:144u*stride;
            d[1]=result.source_y-displacement;d[2]=result.source_c-displacement;
            d[5]=(d[5]&0xffff0000u)|stride;
        }else{
            d[1]=result.preview_base+(images[i][1]-small_min);
            d[2]=result.preview_base+(images[i][2]-small_min);
        }
    }
    publish(out,&result);return 0;
}
