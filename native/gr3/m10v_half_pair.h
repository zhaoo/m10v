#ifndef M10V_HALF_PAIR_H
#define M10V_HALF_PAIR_H
#include <stdint.h>

/* Spatial copy only, after native ISP processing. All lengths are bytes.
 * Inputs are independent packed YC422: w*h Y followed by w*h C bytes.
 * Caller owns the buffers; no allocation, RTOS or filesystem operations occur.
 */
typedef struct m10v_half_pair_plan_info {
    uint32_t width, height, stride, rows, plane_bytes, used_bytes;
    uint32_t first_x, first_y, second_x, second_y;
} m10v_half_pair_plan_info;

/* Accepted EXIF orientations: 1, 3, 6, 8. Failure leaves *out unchanged. */
int m10v_half_pair_plan(uint32_t w, uint32_t h, uint32_t orientation,
                       uint32_t capacity, m10v_half_pair_plan_info *out);
/* dest must be 64-byte aligned and disjoint from both independent inputs.
 * Failure leaves all buffers unchanged. Success initializes Y/C padding to
 * 16/128 and copies both frames without color conversion or interpolation.
 */
int m10v_half_pair_compose(const m10v_half_pair_plan_info *plan,
                          const uint8_t *first, const uint8_t *second,
                          uint8_t *dest, uint32_t capacity);
#endif
