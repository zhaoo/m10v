#include "live_clip.h"

static int dimensions(uint16_t width, uint16_t height) {
    return width >= 16 && width <= 720 && height >= 16 && height <= 480 &&
        !((width | height) & 1u);
}

void m10v_live_reset(m10v_live_clip *clip) {
    clip->head = clip->count = 0;
    clip->shutter = clip->end = 0;
    clip->pending = clip->complete = clip->failed = 0;
    clip->post_start = UINT64_MAX;
    clip->rejection = 0;
}

int m10v_live_init(m10v_live_clip *clip, uint8_t *storage, uint32_t bytes,
                   uint32_t stride, uint16_t width, uint16_t height) {
    if (!clip || !storage || stride < 4 || stride > M10V_LIVE_JPEG_BYTES ||
        bytes < stride * M10V_LIVE_FRAMES || !dimensions(width, height)) return 0;
    clip->storage = storage;
    clip->stride = stride;
    clip->width = width;
    clip->height = height;
    clip->nv12 = 0;
    m10v_live_reset(clip);
    return 1;
}

int m10v_live_init_nv12(m10v_live_clip *clip, uint8_t *storage, uint32_t bytes,
                        uint16_t width, uint16_t height) {
    if (!dimensions(width, height) ||
        !m10v_live_init(clip, storage, bytes, (uint32_t)width * height * 3 / 2, width, height))
        return 0;
    clip->nv12 = 1;
    return 1;
}

static uint32_t at(const m10v_live_clip *clip, uint32_t index) {
    return (clip->head + index) % M10V_LIVE_FRAMES;
}

static void drop_first(m10v_live_clip *clip) {
    clip->head = at(clip, 1);
    clip->count--;
}

int m10v_live_push(m10v_live_clip *clip, uint64_t time,
                   const uint8_t *data, uint32_t bytes) {
    if (!clip || clip->complete || clip->failed || !data || bytes < 4 ||
        bytes > clip->stride) return 0;
    if (clip->nv12 ? bytes != clip->stride :
        data[0] != 255 || data[1] != 216 || data[bytes - 2] != 255 || data[bytes - 1] != 217) return 0;
    if (clip->count) {
        const uint64_t last = clip->frames[at(clip, clip->count - 1)].time;
        if (time <= last || time - last < M10V_LIVE_MIN_STEP_MS) return 0;
    }
    if (clip->pending) {
        if (time < clip->shutter) return 0;
        if (time > clip->end) {
            if (clip->post_start == UINT64_MAX) {
                clip->failed = 1;
                clip->rejection = M10V_LIVE_REJECT_POST_TIMEOUT;
            }
            return 0;
        }
        if (clip->post_start == UINT64_MAX) {
            clip->post_start = time;
            clip->end = time + M10V_LIVE_HALF_MS;
        }
    }
    if (!clip->pending) {
        while (clip->count && time - clip->frames[clip->head].time > M10V_LIVE_HALF_MS)
            drop_first(clip);
    }
    if (clip->count == M10V_LIVE_FRAMES) {
        if (clip->pending) {
            clip->failed = 1;
            clip->rejection = M10V_LIVE_REJECT_CAPACITY;
            return 0;
        }
        drop_first(clip);
    }
    uint32_t index = at(clip, clip->count);
    uint8_t *payload = clip->storage + index * clip->stride;
    for (uint32_t i = 0; i < bytes; ++i) payload[i] = data[i];
    clip->frames[index] = (m10v_live_frame){time, bytes};
    clip->count++;
    return 1;
}

int m10v_live_shutter(m10v_live_clip *clip, uint64_t time, int include_before) {
    if (!clip) return 0;
    if (clip->pending || clip->complete || clip->failed) {
        clip->rejection = M10V_LIVE_REJECT_BUSY;
        return 0;
    }
    if (time > UINT64_MAX - M10V_LIVE_POST_WAIT_MS - M10V_LIVE_HALF_MS) {
        clip->rejection = M10V_LIVE_REJECT_TIME;
        return 0;
    }
    if (clip->count && clip->frames[at(clip, clip->count - 1)].time > time) {
        clip->rejection = M10V_LIVE_REJECT_FUTURE;
        return 0;
    }
    if (include_before) {
        if (!clip->count) { clip->rejection = M10V_LIVE_REJECT_PRE_COVERAGE; return 0; }
        uint64_t newest = clip->frames[at(clip, clip->count - 1)].time;
        if (time - newest > M10V_LIVE_HALF_MS) {
            clip->rejection = M10V_LIVE_REJECT_PRE_STALE;
            return 0;
        }
        /* The still reserve event occurs during display blackout. Preserve
         * the real rolling history; do not trim its beginning against a later
         * event or require a source frame to exist during that blackout. */
        while (clip->count && newest - clip->frames[clip->head].time > M10V_LIVE_HALF_MS)
            drop_first(clip);
        if (newest - clip->frames[clip->head].time < M10V_LIVE_HALF_MS - M10V_LIVE_EDGE_MS) {
            clip->rejection = M10V_LIVE_REJECT_PRE_COVERAGE;
            return 0;
        }
    } else {
        while (clip->count) drop_first(clip);
    }
    clip->shutter = time;
    clip->end = time + M10V_LIVE_POST_WAIT_MS;
    clip->post_start = UINT64_MAX;
    clip->rejection = 0;
    clip->pending = 1;
    return 1;
}

int m10v_live_complete(m10v_live_clip *clip, uint64_t now) {
    if (!clip || !clip->pending || clip->failed || now < clip->end) return 0;
    clip->pending = 0;
    if (clip->post_start == UINT64_MAX) {
        clip->rejection = M10V_LIVE_REJECT_POST_TIMEOUT;
        clip->failed = 1;
        return 0;
    }
    if (clip->count < 2) {
        clip->rejection = M10V_LIVE_REJECT_TOO_FEW;
        clip->failed = 1;
        return 0;
    }
    uint64_t last = clip->frames[at(clip, clip->count - 1)].time;
    if (last <= clip->shutter || clip->end - last > M10V_LIVE_EDGE_MS) {
        clip->rejection = M10V_LIVE_REJECT_POST_EDGE;
        clip->failed = 1;
        return 0;
    }
    clip->rejection = 0;
    clip->complete = 1;
    return 1;
}

static void put16(uint8_t *out, uint16_t value) {
    out[0] = (uint8_t)value;
    out[1] = (uint8_t)(value >> 8);
}

static void put32(uint8_t *out, uint32_t value) {
    put16(out, (uint16_t)value);
    put16(out + 2, (uint16_t)(value >> 16));
}

int m10v_live_write_clip(const m10v_live_clip *clip, m10v_live_write write, void *context) {
    if (!clip || !clip->complete || !write) return 0;
    uint64_t first = clip->frames[clip->head].time;
    if (first > clip->shutter) first = clip->shutter;
    if (clip->end - first + 1u > M10V_LIVE_MAX_SPAN_MS) return 0;
    uint8_t header[24] = {'M','1','0','L'};
    put16(header + 4, clip->nv12 ? 2 : 1);
    put32(header + 20, clip->nv12);
    put16(header + 6, (uint16_t)clip->count);
    put16(header + 8, clip->width);
    put16(header + 10, clip->height);
    put32(header + 12, first < clip->shutter ? (uint32_t)(clip->shutter - first) : 0);
    put32(header + 16, (uint32_t)(clip->end - first + 1));
    if (!write(context, header, sizeof(header))) return 0;
    for (uint32_t i = 0; i < clip->count; ++i) {
        uint32_t index = at(clip, i);
        const m10v_live_frame *frame = &clip->frames[index];
        uint8_t entry[8];
        put32(entry, (uint32_t)(frame->time - first));
        put32(entry + 4, frame->bytes);
        if (!write(context, entry, sizeof(entry)) ||
            !write(context, clip->storage + index * clip->stride, frame->bytes)) return 0;
    }
    return 1;
}
