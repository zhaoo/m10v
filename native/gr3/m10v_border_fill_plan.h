#ifndef M10V_BORDER_FILL_PLAN_H
#define M10V_BORDER_FILL_PLAN_H
#include "m10v_border_canvas.h"
#include "m10v_border_fill_bundle.h"
typedef struct {
    uint32_t tag,count,bytes;
    m10v_border_fill_rectangle rectangles[M10V_BORDER_FILL_BUNDLE_MAX];
    uint32_t descriptors[M10V_BORDER_FILL_BUNDLE_MAX][8];
} m10v_border_fill_plan_info;
/* Metadata only. base is the caller-owned native address of *out; it is used
 * to relocate descriptor references. No photo address is dereferenced. Reject
 * metadata/photo overlap. Fill covers all padding but never inner pixels.
 * Each rectangle stays below native Fill's1MiPixel split/assert branch.
 * Return1 for a bundle plan,0 for OFF without touching out,-1 unchanged on
 * failure. Driver/cache/completion ownership are separate prerequisites. */
int m10v_border_fill_plan(const m10v_border_canvas_info *canvas,uint32_t base,
                          m10v_border_fill_plan_info *out);
#endif
