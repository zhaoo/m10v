#ifndef M10V_ISP_EFFECTS_STATE_H
#define M10V_ISP_EFFECTS_STATE_H

#include <stddef.h>
#include <stdint.h>

/* Independent metadata journal; never reuse legacy film-state padding.
 * Wire format is 12 little-endian uint32 words, with IEEE CRC32 over the
 * first 44 bytes. No native struct layout or pointer enters the record. */
#define M10V_ISP_EFFECTS_RECORD_SIZE 48u
#define M10V_ISP_EFFECTS_RECORD_MAGIC 0x31505349u
#define M10V_ISP_EFFECTS_RECORD_VERSION 2u
/* V1 remains readable and is emitted for legacy settings without UI memory.
 * V2 gives the final word a tagged, bounded remembered-strength contract.
 * Per-shot settings clear this UI word before reaching the ISP renderer. */
#define M10V_ISP_EFFECT_PREF_TAG 0x46580000u

enum {
    M10V_ISP_GRAIN_INHERIT = 0,
    M10V_ISP_GRAIN_OFF = 1,
    M10V_ISP_GRAIN_WEAK = 2,
    M10V_ISP_GRAIN_MEDIUM = 3,
    M10V_ISP_GRAIN_STRONG = 4
};

typedef struct {
    uint32_t leak_gain;       /* 0 off, 1 weak, 2 medium, 3 strong */
    uint32_t leak_position;   /* 0 left, 1 right, 2 both */
    uint32_t leak_spread;     /* 0 narrow, 1 medium, 2 wide */
    uint32_t grain_mode;      /* M10V_ISP_GRAIN_* */
    uint32_t grain_size;      /* 0 fine, 1 standard, 2 coarse */
    uint32_t blur_gain;       /* 0 off, 1 weak, 2 medium, 3 strong */
    uint32_t blur_range;      /* 0 small, 1 medium, 2 large */
    uint32_t reserved;        /* 0 legacy, or tagged V2 UI strength memory */
} m10v_isp_effects_settings;

typedef struct {
    m10v_isp_effects_settings settings;
    uint32_t effective_grain_strength; /* 0 off, 1 weak, 2 medium, 3 strong */
} m10v_isp_effects_snapshot;

/* Defaults are leak/blur off, grain inherited, remaining fields zero. */
void m10v_isp_effects_defaults(m10v_isp_effects_settings *out);
int m10v_isp_effects_validate(const m10v_isp_effects_settings *settings);
/* kind: 0 leak, 1 grain, 2 blur. Strength is 1..3 for leak/blur,
 * and the original grain mode 0/2/3/4 (inherit/weak/medium/strong).
 * Setters preserve all other fields and never enable a disabled effect. */
uint32_t m10v_isp_effects_enabled(const m10v_isp_effects_settings *,uint32_t kind);
uint32_t m10v_isp_effects_strength(const m10v_isp_effects_settings *,uint32_t kind);
int m10v_isp_effects_set_enabled(m10v_isp_effects_settings *,uint32_t kind,uint32_t enabled);
int m10v_isp_effects_set_strength(m10v_isp_effects_settings *,uint32_t kind,uint32_t strength);
/* Return 1 on success, 0 on rejection. Exact record size required. Every
 * rejected operation leaves all output arguments unchanged. */
int m10v_isp_effects_encode(const m10v_isp_effects_settings *settings,
    uint32_t sequence, void *record, size_t record_size);
int m10v_isp_effects_decode(const void *record, size_t record_size,
    m10v_isp_effects_settings *settings, uint32_t *sequence);
/* Return chosen slot 0/1, or -1 without publishing on no valid records,
 * conflicting equal sequences or ambiguous half-range separation. Serial
 * comparison permits uint32 wrap; writers must keep surviving generations
 * less than 2^31 apart. Identical equal-sequence records select slot 0. */
int m10v_isp_effects_select_newest(const void *record_a, size_t size_a,
    const void *record_b, size_t size_b,
    m10v_isp_effects_settings *settings, uint32_t *sequence);
/* CPU metadata only. Caller freezes this snapshot at capture entry. A slot
 * grain strength outside 0..3 is rejected even for a global override. */
int m10v_isp_effects_resolve_snapshot(const m10v_isp_effects_settings *settings,
    uint32_t slot_grain_strength, m10v_isp_effects_snapshot *snapshot);

#endif
