#ifndef M10V_ROLL_OWNER_H
#define M10V_ROLL_OWNER_H

#include "m10v_roll.h"

/* Allocate and access this state only on the permanent AppMain owner.
 * Native workers receive copies of the marker and pass terminal results
 * through the adapter. They never touch this owner or its journal. */
typedef struct {
    m10v_roll_journal journal;
    m10v_roll_saved_probe probe;
    m10v_roll_record current;
    uint8_t marker[M10V_ROLL_MARKER_BYTES];
    int loaded;
    int armed;
    uint32_t reservation;
} m10v_roll_owner;

/* The adapter must bind one mounted generation and finish its old captures
 * before reinitializing after a media change or owner replacement. */
void m10v_roll_owner_init(m10v_roll_owner *, const m10v_roll_journal *,
                          const m10v_roll_saved_probe *);
int m10v_roll_owner_recover(m10v_roll_owner *);
int m10v_roll_owner_snapshot(const m10v_roll_owner *, m10v_roll_record *);
int m10v_roll_owner_open(m10v_roll_owner *, const uint8_t id[16], uint32_t film,
                         uint32_t aspect, uint32_t target);
int m10v_roll_owner_change(m10v_roll_owner *, uint32_t status);
/* The nonzero ticket distinguishes attempts that share the same frame marker.
 * The adapter carries it with the original frozen shooting identity. */
uint32_t m10v_roll_owner_arm(m10v_roll_owner *, uint8_t marker[M10V_ROLL_MARKER_BYTES]);
/* Terminal result for the exact ticket: positive success mask, 0 when every
 * output definitively failed, -1 when ownership/result is uncertain.
 * Returns 1 for a settled group, 0 for a stale result, -1 if recovery is needed. */
int m10v_roll_owner_finish(m10v_roll_owner *, uint32_t ticket,
                            const uint8_t marker[M10V_ROLL_MARKER_BYTES],
                            int32_t saved_outputs);

#endif
