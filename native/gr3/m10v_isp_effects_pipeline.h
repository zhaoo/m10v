#ifndef M10V_ISP_EFFECTS_PIPELINE_H
#define M10V_ISP_EFFECTS_PIPELINE_H
#include <stdint.h>
#include "m10v_isp_effects_shot.h"

/* Caller installs only in the verified standard still spatial path, after
 * original5350304c and existing frozen HDF settings. Native grain is always
 * zeroed here; rejected/unavailable own effects never fall back to CPU RNG.
 * params+20 carries recipe metadata; original53680dbc does not read it. */
uint32_t m10v_isp_effects_pipeline_settings(uint32_t recipe,uint32_t si,
    void *params,uint32_t slot_grain_strength);
/* Called after original53680dbc SIZING. Only stock_result==1 authorizes
 * recording original bytes and raising max capacity. Query and execution
 * parameters are different stack objects; shot retains original sizing. */
uint32_t m10v_isp_effects_pipeline_workspace(const void *params,
    uint32_t *queried_bytes,uint32_t stock_result);
/* Called after original53680dbc EXECUTION with the actual native r0 context.
 * Its final r6 descriptor is params+4 when original sizing is0, else params+8
 * (53680ee8..ef0 /53680f4c..f54). Final HDR0 call53680ff0→53680088 jumps to
 * 5368039c and returns without pixel work. HDR!=0 is not admitted here.
 * Texture max capacity must NOT determine which descriptor is final.
 * Render endpoint returns1 only after actual native success; no CPU fallback. */
int m10v_isp_effects_pipeline_execute(uint32_t recipe,uint32_t native_context,
    void *params,uint32_t stock_result);
/* JPEG ingress before any stock-slot early return. Unsupported original HDR,
 * Pixel/Char routes remain original. Supported active frames must carry this
 * recipe/SI's complete native mask; missing planning/query/completion retains
 * the caller forever via native yield, never authorizes a partial JPEG. */
int m10v_isp_effects_pipeline_encoder_admit(uint32_t recipe,uint32_t si);
int m10v_isp_effects_render(uint32_t native_context,const uint32_t photo[8],
    uint32_t workspace,uint32_t capacity,const m10v_isp_effects_shot_snapshot *shot);
#endif
