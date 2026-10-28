#ifndef M10V_BORDER_BANK_H
#define M10V_BORDER_BANK_H
#include "m10v_border.h"
typedef struct {
    uint32_t images[5][8]; /* R70,R90,Rb0,Rd0,Rf0 low descriptors */
    m10v_border_storage_info canvas;
    uint32_t bank,capacity,source_y,source_c,plane_bytes,preview_base,used_bytes;
} m10v_border_bank_info;
/* Pure full-source slot shape, rebuilt from unchanged common W/H even after
 * BackResize has cropped/aliased low descriptors. Images remain zero.
 * used_bytes covers only two padded planes plus the bank alignment prefix
 * (OFF:zero). No preview footprint, active workspace liveness or native pool
 * ownership is established by this API. Return-1 leaves out unchanged. */
int m10v_border_bank_shape(uint32_t style,uint32_t orientation,uint32_t width,
                          uint32_t height,uint32_t bank,uint32_t capacity,
                          m10v_border_bank_info *out);
/* PURE PLAN, not a live recipe mutation or hardware admission.
 * Keep the original native bank ID5/base/capacity/owner; use only its proven
 * interval. Source pixels must NOT have been produced when this plan is
 * applied. Final R2Y output pitch MUST separately be proven/updated, not inferred
 * from these low descriptors. Small-image pointer relationships are preserved.
 * No pixel pointer is dereferenced, allocation performed, or RAW field changed.
 */
int m10v_border_bank_plan(uint32_t style,uint32_t orientation,uint32_t bank,
                         uint32_t capacity,const uint32_t images[5][8],
                         m10v_border_bank_info *out);
#endif
