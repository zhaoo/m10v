#ifndef M10V_BORDER_SHOT_H
#define M10V_BORDER_SHOT_H
#include <stdint.h>
#include "m10v_save_trace.h"
#include "m10v_capture_raw_lifetime.h"
/* Sole unused aligned word between the color snapshot and RAW owner token.
 * The sole recipe factory already clears its entire allocated extension.
 * No film-state/SD ABI, RAW token word or HDF word is repurposed. */
#define M10V_BORDER_SHOT_OFFSET (M10V_SAVE_COLOR_OFFSET+M10V_SAVE_COLOR_BYTES)
int m10v_border_shot_freeze(uint32_t recipe);
int m10v_border_shot_read(uint32_t recipe,uint32_t *style);
int m10v_border_shot_orientation(uint32_t recipe,uint32_t *orientation);
enum { M10V_BORDER_PHASE_FROZEN=0, M10V_BORDER_PHASE_RUNNING=1,
       M10V_BORDER_PHASE_LIBRARY_ATTEMPTED=2, M10V_BORDER_PHASE_COMPLETE=3,
       M10V_BORDER_PHASE_FAILED_AFTER_LIBRARY=4, M10V_BORDER_PHASE_FAILED_BEFORE_LIBRARY=5,
       M10V_BORDER_PHASE_PREPARED=6,
       M10V_BORDER_PHASE_UNAVAILABLE=255 };
enum { M10V_BORDER_LIBRARY_STOCK_BYPASS=-14 };
/* Metadata phase only. COMPLETE may be published only by the owning stage
 * after all real hardware completions. Library-attempted is independent of
 * success and prevents applying existing residual processing twice. */
uint32_t m10v_border_shot_phase(uint32_t recipe);
int m10v_border_shot_transition(uint32_t recipe,uint32_t before,uint32_t after);
#endif
