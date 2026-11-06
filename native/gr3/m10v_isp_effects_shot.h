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
    M10V_ISP_EFFECTS_NATIVE_BLUR = 4,
    M10V_ISP_EFFECTS_NATIVE_IMPRINT = 8,
    M10V_ISP_EFFECTS_NATIVE_RAINBOW = 16
};
#define M10V_ISP_RAINBOW_TAG 0x52400000u
#define M10V_ISP_RAINBOW_TAG_MASK 0xffc00000u
static inline uint32_t m10v_isp_rainbow_pack(uint32_t kind,uint32_t variant,
        uint32_t phase,uint32_t strength){
    return M10V_ISP_RAINBOW_TAG|((strength&255u)<<12)|((phase&63u)<<6)|
        ((variant&3u)<<4)|(kind&3u);
}
static inline uint32_t m10v_isp_rainbow_valid(uint32_t value){
    uint32_t kind=value&3u;
    return (value&M10V_ISP_RAINBOW_TAG_MASK)==M10V_ISP_RAINBOW_TAG&&
        !(value&0x000c000cu)&&(kind==1u||kind==2u)&&
        ((value>>12)&255u)>=1u&&((value>>12)&255u)<=3u;
}
static inline uint32_t m10v_isp_rainbow_kind(uint32_t value){return value&3u;}
static inline uint32_t m10v_isp_rainbow_variant(uint32_t value){return (value>>4)&3u;}
static inline uint32_t m10v_isp_rainbow_phase(uint32_t value){return (value>>6)&63u;}
static inline uint32_t m10v_isp_rainbow_strength(uint32_t value){return (value>>12)&255u;}
typedef struct {
    uint32_t magic,owner,ready,sequence;
    m10v_isp_effects_settings settings;
    uint32_t planned_width,planned_height,workspace_bytes,effective_grain_strength;
    uint32_t planned,native_completed,failed,source_si;
    uint32_t stock_workspace_bytes,stock_query_valid;
    /* EXIF1/8/3/6 plus an immutable native rainbow descriptor. Rainbow
     * remains in sensor coordinates; saved orientation never rotates it. */
    uint32_t saved_orientation,rainbow;
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
 * Grain texture workspace is align16(width)*height*3/2; leak, imprint or
 * rainbow reserves *2 for the original full-height YUV422 chroma plane. Blur
 * uses original Clarity workspace. This API never allocates or marks completion. */
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
