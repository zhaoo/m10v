#include "m10v_border_prepare.h"
#include "m10v_border_bank.h"
#include "m10v_border_shot.h"

static int ram(uint32_t p,uint32_t bytes){
    return !(p&3u)&&p>=0x55000000u&&p<=0x80000000u-bytes;
}
static uint32_t word(uint32_t p){return *(const volatile uint32_t *)(uintptr_t)p;}
static uint32_t half(uint32_t p){return *(const volatile uint16_t *)(uintptr_t)p;}
static uint32_t byte(uint32_t p){return *(const volatile uint8_t *)(uintptr_t)p;}
static void put(uint32_t p,uint32_t v){*(volatile uint32_t *)(uintptr_t)p=v;}

int m10v_border_prepare(uint32_t module,uint32_t config){
    if(!ram(config,0x60u)||config<0x5500096cu)return -1;
    uint32_t recipe=config-0x96cu,style,orientation;
    if(!m10v_border_shot_read(recipe,&style))return -1;
    if(style==M10V_BORDER_OFF)return 0;
    uint32_t phase=m10v_border_shot_phase(recipe);
    if(phase!=M10V_BORDER_PHASE_FROZEN&&phase!=M10V_BORDER_PHASE_PREPARED)return -1;
    if(!m10v_border_shot_orientation(recipe,&orientation)||!ram(module,0x9bacu))return -2;
    uint32_t status=recipe+0x1a8u,settings=word(recipe+0x44c8u);
    uint32_t bank=word(recipe+0x304u),capacity=word(recipe+0x364u);
    if(word(config+0x30u)!=status||word(module+0x9ba8u)!=status||
       word(config+0x34u)!=settings||!ram(settings,4u)||
       word(config+0x38u)!=word(recipe+0x5cu)||
       word(config+0x10u)!=bank||word(config+0x14u)!=capacity||byte(config+0x49u))return -3;
    /* These bytes are consumed directly by the original B2R/R2Y packers.
     * B2R output-enable byte4 is0; R2Y byte1 selects the live stream input. */
    if(word(module+0x9904u)!=0x01010101u||word(module+0x9908u)||
       word(module+0x9938u)!=0x01010101u||word(module+0x993cu))return -4;
    uint32_t channel=word(module+0x9944u);
    if(!ram(channel,0x14u)||byte(channel+8u)!=4u||!byte(channel+10u))return -5;
    uint32_t rgb[4];
    for(uint32_t i=0;i<4u;++i){
        uint32_t p=word(module+0x9914u+4u*i);rgb[i]=p;
        if(!ram(p,32u)||byte(p)!=8u||word(p+4u)||word(p+8u)||word(p+12u))return -6;
    }
    uint32_t images[5][8],output[8];
    for(uint32_t i=0;i<5u;++i)for(uint32_t j=0;j<8u;++j)
        images[i][j]=word(recipe+0x70u+32u*i+4u*j);
    for(uint32_t j=0;j<8u;++j)output[j]=word(module+0x994cu+4u*j);
    uint32_t width=images[0][4]&65535u,height=images[0][4]>>16;
    uint32_t native_pitch=half(status+0xaau),source_pitch=images[0][5]&65535u;
    uint32_t crop_enabled=byte(status+0xd0u);
    uint32_t write_height=crop_enabled?half(status+0xd8u):height;
    uint32_t roi_y=crop_enabled?half(status+0xd4u):0u;
    uint32_t y=word(config+0x18u),c=word(config+0x1cu);
    if(!crop_enabled||byte(channel+10u)!=crop_enabled||y!=images[0][1]||c!=images[0][2]||
       (output[0]&255u)!=1u||output[3]||
       (output[4]>>16)!=write_height||(output[5]>>16)!=height||
       (output[6]>>16)!=roi_y||!write_height||write_height>height+144u||
       output[1]<y||output[2]<c)return -7;
    uint32_t column=output[1]-y;
    if(output[2]-c!=column)return -7;
    uint32_t columns[3],widths[3],rois[3],selected=3u;
    for(uint32_t i=0;i<3u;++i){
        columns[i]=half(status+0x102u+2u*i);
        widths[i]=half(status+0xeeu+2u*i);
        rois[i]=half(status+0xdau+2u*i);
        /* Native halo widths can exceed visible width by12 bytes. The
         * original configured row capacity, not visible W, bounds the writes. */
        if(!widths[i]||((columns[i]|widths[i]|rois[i])&1u)||columns[i]>=native_pitch||
           widths[i]>native_pitch-columns[i]||columns[i]>=width||
           (i&&columns[i]<=columns[i-1u]))return -8;
        if(columns[i]==column)selected=i;
    }
    if(columns[0]||selected==3u||(output[4]&65535u)!=widths[selected]||
       (output[6]&65535u)!=rois[selected])return -9;
    if((output[5]&65535u)!=native_pitch&&(output[5]&65535u)!=source_pitch)return -10;
    m10v_border_bank_info plan;
    if(m10v_border_bank_plan(style,orientation,bank,capacity,images,&plan))return -11;
    /* The original TRM0H/TRM0V request and all its non-address parameters are
     * preserved. Also reserve the larger ROI+extent+1 rectangle, so even a
     * start/end interpretation stays inside the same plane and row. These
     * conservative bounds do not assert physical register behavior. */
    uint32_t stride=plan.canvas.stride,base=(bank+63u)&~63u;
    uint32_t source_offset=plan.source_y-base;
    uint32_t bounded_height=roi_y+write_height+1u;
    if(bounded_height>height+144u||source_offset>=plan.plane_bytes)return -12;
    for(uint32_t i=0;i<3u;++i){
        uint32_t extent=columns[i]+rois[i]+widths[i]+1u;
        if(extent>stride-plan.canvas.inner.x||
           (bounded_height-1u)*stride+extent>plan.plane_bytes-source_offset)return -13;
    }
    /* Recheck sampled metadata before the first write. This detects stale
     * snapshots; only the caller's exclusive owner contract excludes races. */
    uint32_t checked_style,checked_orientation;
    if(!m10v_border_shot_read(recipe,&checked_style)||checked_style!=style||
       m10v_border_shot_phase(recipe)!=phase||
       !m10v_border_shot_orientation(recipe,&checked_orientation)||checked_orientation!=orientation||
       word(recipe+0x304u)!=bank||word(recipe+0x364u)!=capacity||
       word(config+0x10u)!=bank||word(config+0x14u)!=capacity||
       word(config+0x18u)!=y||word(config+0x1cu)!=c||
       word(config+0x30u)!=status||word(config+0x34u)!=settings||
       word(recipe+0x44c8u)!=settings||word(module+0x9ba8u)!=status||
       byte(config+0x49u)||word(module+0x9904u)!=0x01010101u||word(module+0x9908u)||
       word(module+0x9938u)!=0x01010101u||word(module+0x993cu)||
       word(module+0x9944u)!=channel||byte(channel+8u)!=4u||byte(channel+10u)!=crop_enabled||
       half(status+0xaau)!=native_pitch||byte(status+0xd0u)!=crop_enabled||
       (crop_enabled&&(half(status+0xd8u)!=write_height||half(status+0xd4u)!=roi_y)))return -14;
    for(uint32_t i=0;i<4u;++i)if(word(module+0x9914u+4u*i)!=rgb[i]||
        byte(rgb[i])!=8u||word(rgb[i]+4u)||word(rgb[i]+8u)||word(rgb[i]+12u))return -15;
    for(uint32_t i=0;i<5u;++i)for(uint32_t j=0;j<8u;++j)
        if(word(recipe+0x70u+32u*i+4u*j)!=images[i][j])return -16;
    for(uint32_t j=0;j<8u;++j)if(word(module+0x994cu+4u*j)!=output[j])return -17;
    for(uint32_t i=0;i<3u;++i)if(half(status+0x102u+2u*i)!=columns[i]||
        half(status+0xeeu+2u*i)!=widths[i]||half(status+0xdau+2u*i)!=rois[i])return -18;
    for(uint32_t i=0;i<5u;++i)for(uint32_t j=0;j<8u;++j)
        put(recipe+0x70u+32u*i+4u*j,plan.images[i][j]);
    put(config+0x18u,plan.source_y);put(config+0x1cu,plan.source_c);
    put(module+0x9950u,plan.source_y+column);put(module+0x9954u,plan.source_c+column);
    *(volatile uint16_t *)(uintptr_t)(module+0x9960u)=(uint16_t)plan.canvas.stride;
    return 1;
}
