#ifndef M10V_ROLL_SAVE_H
#define M10V_ROLL_SAVE_H

#include <stdint.h>

enum {
    M10V_ROLL_SAVE_JPEG = 1,
    M10V_ROLL_SAVE_DNG = 2,
    M10V_ROLL_SAVE_GROUP_DONE = 0x00800001
};

enum {
    M10V_ROLL_SAVE_IGNORED = -2,
    M10V_ROLL_SAVE_UNKNOWN = -1
};

/* Initialize to zero. One serialized caller owns each pending exposure and
 * supplies a nonzero ticket unique among callbacks that can still arrive.
 * Group, descriptor, and SI are opaque addresses from the checked GR III
 * 2.10 still Store chain. The bridge does not dereference them or write files. */
typedef struct {
    uint32_t ticket;
    uint32_t group;
    uint32_t si;
    uint32_t stream;
    uint32_t expected;
    uint32_t seen;
    uint32_t succeeded;
    uint32_t conflicts;
} m10v_roll_save;

/* Register only an independently identified normal shutter exposure. Use
 * the native group's requested output flags before dispatching its writers. */
int m10v_roll_save_begin(m10v_roll_save *save, uint32_t ticket, uint32_t group,
                         uint32_t si, uint32_t stream, uint32_t expected);
/* Submit each writer's outcome before end. reached_data_close requires the
 * original writer to reach its AND of data and close at 0x53598f80. The
 * W+0x18 result alone can be true on early return with neither phase run. */
int m10v_roll_save_output(m10v_roll_save *save, uint32_t ticket, uint32_t group,
                          uint32_t descriptor, uint32_t si,
                          uint32_t reached_data_close, uint32_t status_ok);
/* The matching stock group notification consumes the result even on failure.
 * Positive results are a mask of verified writer successes. Zero is a known
 * failure. UNKNOWN requires storage reconciliation before reusing a frame.
 * Writer completion itself does not prove physical card durability. */
int32_t m10v_roll_save_end(m10v_roll_save *save, uint32_t ticket,
                                        uint32_t group, uint32_t stock_event);

#endif
