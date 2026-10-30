#include "m10v_ui.h"
#include "../gr3/m10v_film_card.h"
/* The shared artwork renderer emits 0xAABBGGRR words for GR III's little
 * endian RGBA memory. Convert explicitly on BE32 before any GR II-specific
 * OSD/indexed/YUV upload. This function does not submit a screen bitmap. */
int gr2_film_card_rgba(uint8_t *out,uint32_t capacity,uint32_t film,uint32_t slot,uint32_t selected){
    uint32_t bytes=M10V_CARD_PIXELS*4u;
    if(!out||((uintptr_t)out&3)||capacity<bytes||(uintptr_t)out>UINTPTR_MAX-bytes||film<1||film>78||slot>=5)return 0;
    if(m10v_film_card_render((uint32_t *)out,film,slot,selected))return 0;
    for(uint32_t i=0;i<bytes;i+=4){uint8_t a=out[i],b=out[i+1];out[i]=out[i+3];out[i+1]=out[i+2];out[i+2]=b;out[i+3]=a;}
    return 1;
}
#include "m10v_model.h"
/* Existing UI owner only. Position packs physical x in low16, y in high16;
 * the full-resolution stock RGB context uses 720x480 logical coordinates. */
int gr2_card_draw(uint32_t film,uint32_t slot,uint32_t selected,uint32_t position){
    uint32_t x=position&65535u,y=position>>16;
    if(film<1||film>78||slot>=5||selected>1||x>720-M10V_CARD_WIDTH||y>480-M10V_CARD_HEIGHT)return 0;
    typedef uint8_t *(*context_fn)(uint32_t);
    uint8_t *context=((context_fn)(uintptr_t)0xA039DA57u)(1);
    const uint16_t *geometry=(const uint16_t *)(const void *)context;
    if(!context||geometry[2]!=720||geometry[3]!=480||geometry[4]!=720||geometry[5]!=480)return 0;
    const uint32_t *words=(const uint32_t *)(const void *)context;
    if(!words[4])return 0;
    uint8_t *memory=gr2_allocate(M10V_CARD_PIXELS*4u);if(!memory)return 0;
    if(!gr2_film_card_rgba(memory,M10V_CARD_PIXELS*4u,film,slot,selected)){gr2_release(memory);return 0;}
    for(uint32_t i=0;i<M10V_CARD_PIXELS;i++){
        uint32_t red=(memory[4*i]+8u)/17u,green=(memory[4*i+1]+8u)/17u,blue=(memory[4*i+2]+8u)/17u;
        uint32_t alpha=(memory[4*i+3]+8u)/17u;
        uint16_t pixel=(uint16_t)((red<<12)|(green<<8)|(blue<<4)|alpha);
        memory[2*i]=(uint8_t)(pixel>>8);memory[2*i+1]=(uint8_t)pixel;
    }
    uint32_t bitmap[3]={0,(uint32_t)(uintptr_t)memory,(M10V_CARD_WIDTH<<16)|M10V_CARD_HEIGHT};
    typedef void (*blit_fn)(void *,const void *,uint32_t,uint32_t);
    ((blit_fn)(uintptr_t)0xA03BE443u)(context,bitmap,x,y);
    if(gr2_release(memory))return 0;
    return 1;
}
