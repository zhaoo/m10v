#ifndef M10V_ROLL_CAPTURE_H
#define M10V_ROLL_CAPTURE_H

#include "m10v_roll.h"
#include "m10v_roll_save.h"

enum {
    M10V_ROLL_CAPTURE_EMPTY,
    M10V_ROLL_CAPTURE_TRANSITION,
    M10V_ROLL_CAPTURE_ARMED,
    M10V_ROLL_CAPTURE_CLAIMED,
    M10V_ROLL_CAPTURE_RESULT
};

/* Zero-initialized, boot-lifetime storage. AppMain owns arming and receipt
 * consumption. The normal capture producer and Store tasks use the remaining
 * fields while the reserved exposure runs. Use the functions below. */
typedef struct {
    uint32_t state;
    uint32_t ticket;
    uint32_t si;
    uint32_t si_generation;
    uint32_t group;
    uint32_t writer;
    uint32_t reached_outputs;
    uint32_t marked_outputs;
    uint8_t marker[M10V_ROLL_MARKER_BYTES];
    int32_t result;
    m10v_roll_save save;
    uint32_t expected_tone;
    uint32_t expected_aspect;
    uint32_t expected_film;
    uint32_t lcd_direct, lcd_configured, still_producer, still_claimed;
    uint32_t lcd_direct_at_still, lcd_configured_at_still, visible_geometry;
} m10v_roll_capture_channel;

int m10v_roll_capture_arm(m10v_roll_capture_channel *, uint32_t ticket,
                          const uint8_t marker[M10V_ROLL_MARKER_BYTES],
                          uint32_t tone, uint32_t aspect, uint32_t film);
int m10v_roll_capture_revoke(m10v_roll_capture_channel *, uint32_t ticket);
int m10v_roll_capture_take_result(m10v_roll_capture_channel *, uint32_t *ticket,
                                  uint8_t marker[M10V_ROLL_MARKER_BYTES], int32_t *saved_outputs);
int m10v_roll_capture_reserve(m10v_roll_capture_channel *, uint32_t si, uint32_t generation,
                              uint32_t tone, uint32_t aspect, uint32_t film);
int m10v_roll_capture_copy_marker(const m10v_roll_capture_channel *, uint32_t si, uint32_t generation,
                                  uint8_t marker[M10V_ROLL_MARKER_BYTES]);
int m10v_roll_capture_complete(m10v_roll_capture_channel *, uint32_t si, uint32_t generation,
                               int32_t saved_outputs);

/* Exposes only an already-live channel. This getter is callable from
 * scheduler and storage tasks, with no I/O, allocation, or lock. */
m10v_roll_capture_channel *m10v_roll_device_capture_channel(void);

#endif
