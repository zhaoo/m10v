#ifndef M10V_ISP_EFFECTS_RENDER_H
#define M10V_ISP_EFFECTS_RENDER_H
#include <stdint.h>
#include "m10v_isp_effects_shot.h"
/* Metadata-only orchestration. Frozen caller reservations, descriptors, recipe
 * context and immutable assets must remain owned through all native callbacks.
 * Order: existing native Clarity (caller), leak Y/Cb/Cr, then stock grain.
 * 1 actual checked native success (or disabled); -1 preflight; -4 invalid output.
 * The leak endpoint arithmetic is experimental and requires camera acceptance. */
int m10v_isp_effects_render(uint32_t ctx,const uint32_t photo[8],uint32_t work,
 uint32_t capacity,const m10v_isp_effects_shot_snapshot *shot);
#endif
