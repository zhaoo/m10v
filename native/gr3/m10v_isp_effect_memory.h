#ifndef M10V_ISP_EFFECT_MEMORY_H
#define M10V_ISP_EFFECT_MEMORY_H
#include <stdint.h>
/* GR III2.10 / IIIx1.60 original startup table53004000: identity-mapped
 * data sections, attributes14c26, domain client. The unmapped gap800..9ff
 * and end>=e00 remain excluded. This validates a buffer span, not metadata
 * ownership, allocation lifetime, DMA completion or permission to free it. */
static inline int m10v_isp_effect_buffer_span(uint32_t p,uint32_t n){
    if(!n||n>0x40000000u)return 0;
    return (p>=0x55000000u&&p<0x80000000u&&n<=0x80000000u-p)||
           (p>=0xa0000000u&&p<0xe0000000u&&n<=0xe0000000u-p);
}
#endif
