#ifndef M10V_ROLL_RECOVERY_H
#define M10V_ROLL_RECOVERY_H

#include "m10v_roll.h"

enum {
    M10V_ROLL_RECOVERY_COMMAND = 8,
    M10V_ROLL_RECOVERY_NEEDED = 9,
    M10V_ROLL_RECOVERY_ABORT = 10,
    M10V_ROLL_DIAGNOSTIC_VERSION = 1,
    M10V_ROLL_NEEDED_BYTES = 5,
    M10V_ROLL_SD_ABSENT = 0,
    M10V_ROLL_SD_PRESENT = 1,
    M10V_ROLL_SD_DAMAGED = 2
};

/* The offline Linux service reads these same two card-root files as AppMain.
 * A damaged page is known to exist but does not contain a complete record. */
typedef struct {
    uint32_t pages[2];
    m10v_roll_record records[2];
    uint32_t found[2][2]; /* [JPEG/DNG][bit(frame - 1)], zero when no scan */
} m10v_roll_recovery;

/* Appended to RECOVERY_NEEDED after its original five bytes. All words are
 * native little endian. Counts and geometry are observations, not a frame lease. */
typedef struct {
    uint32_t version, lcd_direct, lcd_configured, still_producer, still_claimed;
    uint32_t lcd_direct_at_still, lcd_configured_at_still, visible_geometry;
    uint32_t channel_state, marked_outputs, reached_outputs, roll_status, confirmed_frames;
} m10v_roll_diagnostic;

_Static_assert(sizeof(m10v_roll_diagnostic) == 52, "roll diagnostic wire ABI");

/* Optional debug-only suffix after the unchanged recovery v1 diagnostic.
 * magic distinguishes it; producer counts never imply media durability. */
#define M10V_REVIEW_DIAGNOSTIC_MAGIC 0x3156524du
#define M10V_REVIEW_DIAGNOSTIC_BYTES 40u
typedef struct {
    uint32_t magic, jpeg_submits, jpeg_returns, jpeg_main_bytes, jpeg_extra_bytes;
    uint32_t model_state, model_busy, quick_state, timer_review, timer_wait;
} m10v_review_diagnostic;
_Static_assert(sizeof(m10v_review_diagnostic)==M10V_REVIEW_DIAGNOSTIC_BYTES,"review scalar ABI");



/* Extended suffix follows the original 40-byte suffix. Stage record words:
 * even global observation sequence, caller scalar, then eight exact native descriptor words.
 * Stage5 holds manager words instead; all values are observations, not leases. */
#define M10V_REVIEW_HANDOFF_MAGIC 0x3256524du
#define M10V_REVIEW_HANDOFF_STAGES 6u
typedef struct {
 uint32_t magic, records[M10V_REVIEW_HANDOFF_STAGES][10], bank[7];
} m10v_review_handoff;
_Static_assert(sizeof(m10v_review_handoff)==272u,"review handoff scalar ABI");

#endif
