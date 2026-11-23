#ifndef M10V_ROLL_H
#define M10V_ROLL_H

#include <stdint.h>

enum {
    M10V_ROLL_ACTIVE = 1,
    M10V_ROLL_PAUSED = 2,
    M10V_ROLL_CLOSED = 3,
    M10V_ROLL_MARKER_BYTES = 32,
    M10V_ROLL_EXIF_TAG = 0xc7f2,
    M10V_ROLL_SAVED_JPEG = 1,
    M10V_ROLL_SAVED_DNG = 2
};

typedef struct {
    uint32_t magic;
    uint32_t sequence;
    uint8_t id[16];
    uint32_t film;
    uint32_t aspect;
    uint32_t target;
    uint32_t count;
    uint32_t status;
    uint32_t crc;
} m10v_roll_record;

typedef struct {
    void *context;
    /* Read returns 1 for a complete page, 0 for a confirmed absent page,
     * and -1 for an inaccessible page. Write returns 1 on success. */
    int (*read)(void *, uint32_t page, m10v_roll_record *);
    int (*write)(void *, uint32_t page, const m10v_roll_record *);
} m10v_roll_journal;

/* Journal calls belong to one storage owner and run outside capture workers.
 * Load reports 0 for an empty journal and -1 for unknown or corrupt state. */
int m10v_roll_load(const m10v_roll_journal *, m10v_roll_record *);
int m10v_roll_store(const m10v_roll_journal *, const m10v_roll_record *expected,
                    const m10v_roll_record *next);

/* Outputs are provisional until the storage owner verifies journal readback.
 * Input and output may alias, which is useful for in-memory simulation. */
int m10v_roll_valid(const m10v_roll_record *);
int m10v_roll_latest(const m10v_roll_record *a, const m10v_roll_record *b);
int m10v_roll_open(const m10v_roll_record *previous, m10v_roll_record *out,
                   const uint8_t id[16], uint32_t film, uint32_t aspect,
                   uint32_t target);
int m10v_roll_change(const m10v_roll_record *current, m10v_roll_record *out,
                     uint32_t status);
int m10v_roll_complete(const m10v_roll_record *current, m10v_roll_record *out,
                       uint32_t saved_frame);
int m10v_roll_marker(const m10v_roll_record *, uint32_t frame,
                     uint8_t out[M10V_ROLL_MARKER_BYTES]);

typedef struct {
    void *context;
    /* 1 = exact tag in a fully saved original, 0 = exhaustively proven absent,
     * -1 = unknown (including incomplete scans, ambiguous output or a gap before
     * later saved frames). MakerNote bytes alone do not prove file completion. */
    int (*find)(void *, const uint8_t marker[M10V_ROLL_MARKER_BYTES]);
} m10v_roll_saved_probe;

/* AppMain startup / recovery only. All IO and proof must address the same
 * mounted generation. Returns 1 for a recovered record, 0 for an empty
 * journal, -1 when it is unsafe to arm the next frame. */
int m10v_roll_reconcile(const m10v_roll_journal *, const m10v_roll_saved_probe *,
                        m10v_roll_record *out);

/* AppMain receives the frozen tag and only positive terminal native receipts.
 * 1 confirms the durable frame, 0 rejects stale/invalid/no-success evidence,
 * -1 means write outcome unknown and requires reconciliation before rearming. */
int m10v_roll_apply_saved(const m10v_roll_journal *,
                          const uint8_t marker[M10V_ROLL_MARKER_BYTES],
                          uint32_t saved_outputs);

#endif
