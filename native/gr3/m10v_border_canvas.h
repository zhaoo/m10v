#ifndef M10V_BORDER_CANVAS_H
#define M10V_BORDER_CANVAS_H
#include "m10v_border.h"
typedef struct {
    uint32_t inner[8],canvas[8];
    m10v_border_storage_info layout;
} m10v_border_canvas_info;
/* Metadata only, after original BackResize completes. Consume the actual
 * cropped descriptor, not a second crop table. Normalize inner cache rows
 * before optional existing processing, and prepare the later outer descriptor.
 * y_base/c_base/plane_bytes are the separately admitted padded bank slots.
 * No pixels or driver are accessed. Success does not mean composition ran.
 * Main JPEG is native422 and requires8-byte plane starts. OFF copies exact
 * descriptors and needs no canvas capacity. Failure leaves output unchanged.
 */
int m10v_border_canvas_plan(uint32_t style,uint32_t orientation,
                            const uint32_t inner[8],uint32_t y_base,
                            uint32_t c_base,uint32_t plane_bytes,
                            m10v_border_canvas_info *out);
#endif
