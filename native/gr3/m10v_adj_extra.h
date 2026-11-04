#ifndef M10V_ADJ_EXTRA_H
#define M10V_ADJ_EXTRA_H

#include <stddef.h>
#include <stdint.h>

#define M10V_ADJ_EXTRA_FIRST_SLOT 6u
#define M10V_ADJ_EXTRA_SLOT_COUNT 4u
#define M10V_ADJ_EXTRA_RECORD_SIZE 20u

typedef struct {
    uint8_t function[M10V_ADJ_EXTRA_SLOT_COUNT];
} m10v_adj_extra_assignments;

/* M10J v1 stores little-endian header, sequence, four function IDs and CRC32.
 * ID 0 is Off. Bits in allowed_functions authorize stable IDs 1 through 31.
 * Pass the format's accepted IDs, independent of live function availability.
 * On failure the encode destination and decode/select outputs are unchanged. */
int m10v_adj_extra_encode(const m10v_adj_extra_assignments *assignments,
    uint32_t allowed_functions, uint32_t sequence, void *record, size_t size);
int m10v_adj_extra_decode(const void *record, size_t size,
    uint32_t allowed_functions, m10v_adj_extra_assignments *assignments,
    uint32_t *sequence);
/* Returns the newest usable record index (0 or 1), or -1. */
int m10v_adj_extra_select_newest(const void *a, size_t size_a,
    const void *b, size_t size_b, uint32_t allowed_functions,
    m10v_adj_extra_assignments *assignments, uint32_t *sequence);

typedef struct {
    /* Create returns a unique, hidden widget pair or 0. It owns cleanup of
     * incomplete creation. Attach leaves it hidden and owns cleanup of any
     * partial native insertion on failure. */
    uintptr_t (*create)(void *context, uintptr_t owner, unsigned logical_slot,
        uint8_t function);
    int (*attach)(void *context, uintptr_t owner, uintptr_t widget);
    void (*detach)(void *context, uintptr_t owner, uintptr_t widget);
    void (*destroy)(void *context, uintptr_t widget);
} m10v_adj_extra_widget_ops;

/* Zero-initialize once. The caller owns this sidecar outside stock settings
 * and the controller object. Use from the serialized ADJ UI lifecycle.
 * While open, widget[] is available for the final geometry/visibility pass.
 * The ops table and context live through close. */
typedef struct {
    uintptr_t owner;
    uint32_t lifetime;
    uintptr_t widget[M10V_ADJ_EXTRA_SLOT_COUNT];
    m10v_adj_extra_assignments assignments;
    const m10v_adj_extra_widget_ops *ops;
    void *context;
    uint8_t phase;
} m10v_adj_extra_session;

/* Pass the currently eligible assignments, with unavailable entries Off.
 * On failure or all Off, the caller keeps the stock geometry and focus.
 * Each controller lifetime needs a new nonzero token, including address reuse. */
int m10v_adj_extra_open(m10v_adj_extra_session *session,
    uintptr_t owner, uint32_t lifetime,
    const m10v_adj_extra_assignments *assignments, uint32_t allowed_functions,
    const m10v_adj_extra_widget_ops *ops, void *context);
/* Retire before the native parent invalidates the child vector. */
int m10v_adj_extra_close(m10v_adj_extra_session *session, uintptr_t owner,
    uint32_t lifetime);
/* Returns Off for any stale owner, unavailable tile, or out-of-range index. */
uint8_t m10v_adj_extra_function(const m10v_adj_extra_session *session,
    uintptr_t owner, uint32_t lifetime, unsigned logical_slot);

#endif
