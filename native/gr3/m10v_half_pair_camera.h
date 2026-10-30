#ifndef M10V_HALF_PAIR_CAMERA_H
#define M10V_HALF_PAIR_CAMERA_H
#include <stdint.h>
/* Last owned JPEG pre-submit consumer, never a task ingress hook. No pixel or
 * native object pointers survive return. reset is for a filesystem-safe boot
 * or explicit mode-leave owner; do not call it from preview/producer hooks. */
void m10v_half_pair_init(uint32_t owner);
void m10v_half_pair_destroy(uint32_t owner);
int m10v_half_pair_camera(uint32_t context);
int m10v_half_pair_reset(void);
uint32_t m10v_half_pair_select(uint32_t model,uint32_t raw);
#endif
