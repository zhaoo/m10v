#ifndef M10V_LIVE_CLIP_H
#define M10V_LIVE_CLIP_H

#include <stdint.h>

enum {
    M10V_LIVE_FRAMES = 48,
    M10V_LIVE_JPEG_BYTES = 131072,
    M10V_LIVE_HALF_MS = 1500,
    M10V_LIVE_MIN_STEP_MS = 70,
    M10V_LIVE_POST_WAIT_MS = 5000,
    M10V_LIVE_MAX_SPAN_MS = 10000,
    M10V_LIVE_EDGE_MS = 250,
    M10V_LIVE_REJECT_BUSY = 1,
    M10V_LIVE_REJECT_TIME = 2,
    M10V_LIVE_REJECT_PRE_COVERAGE = 3,
    M10V_LIVE_REJECT_PRE_STALE = 4,
    M10V_LIVE_REJECT_FUTURE = 5,
    M10V_LIVE_REJECT_POST_TIMEOUT = 6,
    M10V_LIVE_REJECT_POST_EDGE = 7,
    M10V_LIVE_REJECT_TOO_FEW = 8,
    M10V_LIVE_REJECT_CAPACITY = 9,
};

typedef struct {
    uint64_t time;
    uint32_t bytes;
} m10v_live_frame;

typedef struct {
    uint8_t *storage;
    uint32_t stride;
    uint16_t width, height;
    uint32_t head, count;
    uint64_t shutter, end;
    uint8_t pending, complete, failed;
    m10v_live_frame frames[M10V_LIVE_FRAMES];
    uint8_t nv12;
    /* UINT64_MAX until the first validated post-event frame. A still capture
     * may temporarily remove the native display source; timestamps retain
     * that real gap instead of inventing frames or moving the still event. */
    uint64_t post_start;
    uint32_t rejection;
} m10v_live_clip;

typedef int (*m10v_live_write)(void *, const uint8_t *, uint32_t);

/* Called by one recorder owner. Storage is preallocated and retained by the
 * owner. Push copies a validated frame before the producer reuses it. */
int m10v_live_init(m10v_live_clip *, uint8_t *, uint32_t bytes,
                   uint32_t stride, uint16_t width, uint16_t height);
int m10v_live_init_nv12(m10v_live_clip *, uint8_t *, uint32_t bytes,
                       uint16_t width, uint16_t height);
int m10v_live_push(m10v_live_clip *, uint64_t time_ms, const uint8_t *, uint32_t bytes);
int m10v_live_shutter(m10v_live_clip *, uint64_t time_ms, int include_before);
int m10v_live_complete(m10v_live_clip *, uint64_t now_ms);
int m10v_live_write_clip(const m10v_live_clip *, m10v_live_write, void *context);
void m10v_live_reset(m10v_live_clip *);

#endif
