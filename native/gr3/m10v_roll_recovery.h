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

#endif
