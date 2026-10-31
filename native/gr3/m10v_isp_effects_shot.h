#ifndef M10V_ISP_EFFECTS_SHOT_H
#define M10V_ISP_EFFECTS_SHOT_H
#include <stdint.h>
#include "m10v_isp_effects_state.h"

/* Builder reserves a new tail and supplies M10V_ISP_EFFECTS_SHOT_OFFSET.
 * Existing recipe/color/RAW/stamp fields are never reused. */
#define M10V_ISP_EFFECTS_SHOT_BYTES 96u
#define M10V_ISP_EFFECTS_SHOT_MAGIC 0x31584653u
enum {
    M10V_ISP_EFFECTS_NATIVE_GRAIN = 1,
    M10V_ISP_EFFECTS_NATIVE_LEAK = 2,
    M10V_ISP_EFFECTS_NATIVE_BLUR = 4
};
typedef struct {
    uint32_t magic,owner,ready,sequence;
    m10v_isp_effects_settings settings;
    uint32_t planned_width,planned_height,workspace_bytes,effective_grain_strength;
    uint32_t planned,native_completed,failed,source_si;
    uint32_t stock_workspace_bytes,stock_query_valid;
    uint32_t saved_orientation,reserved; /* EXIF1/8/3/6, frozen from saved SI by capture producer */
} m10v_isp_effects_shot_snapshot;

/* Explicit new exposure only. Caller owns serialized native recipe lifetime,
 * installs the matching allocator, and calls after original vptr/trace setup.
 * Reserve is the only operation allowed to reset frozen or pending state. */
void m10v_isp_effects_shot_reserve(uint32_t recipe);
/* Capture cache read once: ready1 valid, ready2 unavailable, ready3 publishing.
 * Saved SI identity and its EXIF direction (including SI override) freeze
 * here before queueing; plan never rereads a changed orientation.
 * Freeze unavailable too; later UI changes cannot retarget this exposure. */
int m10v_isp_effects_shot_freeze(uint32_t recipe);
/* Bounded metadata copy, no output mutation on unavailable/invalid ownership.
 * A ready valid off snapshot returns1. Output must be outside recipe storage. */
int m10v_isp_effects_shot_read(uint32_t recipe,m10v_isp_effects_shot_snapshot *out);
/* Plan only frozen metadata, with saved SI identity and even sizes2..6144.
 * Grain texture workspace is align16(width)*height*3/2; leak reserves *2
 * for the original full-height YUV422 chroma plane. Blur uses original
 * Clarity workspace. This API never allocates or marks completion. */
int m10v_isp_effects_shot_plan(uint32_t recipe,uint32_t si,uint32_t width,
    uint32_t height,uint32_t slot_grain_strength);
/* Owning executor calls only after actual native success; this records its
 * observation, not a hardware proof. Bits must belong to enabled own effects.
 * Plan/complete/fail run under original per-recipe worker serialization. */
int m10v_isp_effects_shot_complete(uint32_t recipe,uint32_t si,uint32_t flags);
void m10v_isp_effects_shot_fail(uint32_t recipe,uint32_t si);
/* Bind the first successful ORIGINAL native sizing result before a caller
 * raises it for texture work. Later query/execution parameter blocks differ;
 * this per-shot metadata preserves original ping-pong destination selection. */
int m10v_isp_effects_shot_stock_query(uint32_t recipe,uint32_t si,uint32_t bytes);
/* Authenticate only an untouched once-frozen unavailable cache decision.
 * No plan, settings, sequence, orientation or completion may be published. */
int m10v_isp_effects_shot_unavailable(uint32_t recipe,uint32_t si);
#endif
