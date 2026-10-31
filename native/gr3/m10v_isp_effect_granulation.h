#ifndef M10V_ISP_EFFECT_GRANULATION_H
#define M10V_ISP_EFFECT_GRANULATION_H
#include <stdint.h>
/* All objects, descriptors, prepared plane and constant curves remain immutable
 * and alive until return. Caller performs native cache ownership transitions. */
typedef struct {
 uint32_t capacity,magic,context,noise_plane,noise_bytes,curves,nonce;
 volatile uint32_t failed,completed,wait_failures,rng_skipped,submitted,released;
 uint32_t noise_stride;
} m10v_isp_effect_granulation_info;
int m10v_isp_effect_granulation_owned(void *ctx,void *dst,const void *src,uint32_t strength,void *plane,uint32_t bytes,const int16_t curves[3][256]);
int m10v_isp_effect_granulation_luma(void *ctx,void *mask,const uint32_t photo[8],const int16_t curves[3][256]);
void m10v_isp_effect_granulation_setup(uint32_t *frame,uint32_t registers[14]);
uint32_t m10v_isp_effect_granulation_call(void*,void*,const void*,uint32_t,void*,m10v_isp_effect_granulation_info*);
int m10v_isp_effect_granulation_is_owned(uint32_t *frame);
int m10v_isp_effect_granulation_rng(uint32_t *frame);
void m10v_isp_effect_granulation_submit(uint32_t *frame,void *graph);
uint32_t m10v_isp_effect_granulation_wait(void *ctx,uint32_t mask,uint32_t *frame);
uint32_t m10v_isp_effect_granulation_release(void *graph,uint32_t *frame);
#endif
