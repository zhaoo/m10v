#include "m10v_live_camera.h"
#include "m10v_film_identity.h"

enum {
    SOURCE_PITCH = 1920,
    SOURCE_ROWS = 1088,
    SOURCE_WIDTH = 1008,
    SOURCE_HEIGHT = 448
};

static uint32_t load(const uint32_t *p) { return __atomic_load_n(p, __ATOMIC_ACQUIRE); }
static void publish(uint32_t *p, uint32_t value) { __atomic_store_n(p, value, __ATOMIC_RELEASE); }
static const uint8_t *bytes(uint32_t a) { return (const void *)(uintptr_t)a; }
static uint32_t word(uint32_t a) { return *(const volatile uint32_t *)(uintptr_t)a; }
static uint32_t lower_ram(uint32_t a, uint32_t n) { return a - 0x55000000u <= 0x2b000000u - n && !(a & 3u); }

static void clean(void *p, uint32_t count) {
    ((void (*)(void *, uint32_t))0x5383c870u)(p, count);
}

static uint32_t ticks(void) {
    uint32_t time[2];
    return ((int (*)(uint32_t *))0x53050b7cu)(time) ? 0 : time[1];
}

/* Return a diagnostic reason without weakening the original source contract.
 * Snapshot only scalar metadata whose range has already been validated. */
static uint32_t source_reason(uint32_t recipe, uint32_t config, uint32_t y, uint32_t uv,
                              m10v_live_ingress_diagnostic *d) {
    if (!lower_ram(recipe, 0x554)) return 1;
    d->recipe_kind = bytes(recipe)[4];
    /* 5345a7ec extracts ready1 as queued2. The display call at53449474
     * precedes534495a4 publishing that same recipe as state3. Both retain
     * their scoped native planes here; free0,building1,retired4 stay closed. */
    if ((d->recipe_kind | 1u) != 3u) return 2;
    if (!lower_ram(config, 100)) return 3;
    if (y & 63u) return 4;
    if (uv - y != SOURCE_PITCH * SOURCE_ROWS) return 5;
    if (!(lower_ram(y, SOURCE_PITCH * SOURCE_ROWS) ||
          (y >= 0xa0000000u && y <= 0xe0000000u - SOURCE_PITCH * SOURCE_ROWS))) return 6;
    const uint8_t *flags = bytes(config);
    uint32_t idx = 0;
    while (idx < 3 && flags[idx] != 1) ++idx;
    if (idx == 3) idx = 0;
    const uint32_t *desc = (const void *)bytes(config + 4 + idx * 32u);
    d->descriptor_index = idx;
    const uint32_t *scan = desc;
    uint32_t *saved = d->descriptor;
    do *saved++ = *scan++; while (scan != desc + 8);
    if (desc[0] != (SOURCE_PITCH << 16 | 2 << 8) ||
        desc[1] != (SOURCE_WIDTH << 16 | SOURCE_ROWS) ||
        desc[2] != SOURCE_HEIGHT || (desc[3] & 65535u) || (desc[7] & 255u)) return 7;
    if ((desc[5] || desc[6]) && (desc[5] != y || desc[6] != uv)) return 12;
    uint32_t backing = word(recipe + 0x9cu);
    if (!lower_ram(backing, 0x1cc) ||
        word(backing + 0x1c8) != (SOURCE_ROWS << 16 | SOURCE_PITCH) ||
        y - word(recipe + 0x60) != word(recipe + 0x550)) return 13;
    return 0;
}

static void diagnostic_publish(m10v_live_camera *camera, m10v_live_ingress *arena) {
    const m10v_live_ingress_diagnostic *source = &camera->diagnostic;
    if (source->version && source->tick - camera->diagnostic_tick < 1000u) return;
    camera->diagnostic.version = 2;
    camera->diagnostic_tick = source->tick;
    m10v_live_ingress_diagnostic *out = &arena->control.diagnostic;
    uint32_t next = (load(&out->seq) & ~1u) + 2u;
    if (!next) next = 2;
    publish(&out->seq, next - 1u);
    clean(&arena->control, sizeof(arena->control));
    const uint32_t *from = (const void *)source;
    uint32_t *to = (void *)out;
    ++from; ++to;
    const uint32_t *end = (const uint32_t *)(source + 1);
    do *to++ = *from++; while (from != end);
    publish(&out->seq, next);
    clean(&arena->control, sizeof(arena->control));
}

void m10v_live_camera_display(uint32_t recipe, uint32_t config, uint32_t y, uint32_t uv) {
    m10v_live_camera *camera = m10v_live_device_camera();
    if (!camera) return;
    m10v_live_ingress *arena = __atomic_load_n(&camera->arena, __ATOMIC_ACQUIRE);
    if (!arena) return;
    uint32_t request = load(&arena->control.request);
    uint32_t tick = ticks();
    m10v_live_ingress_diagnostic *d = &camera->diagnostic;
    ++d->entries;
    d->tick = tick;
    d->consumer_tick = load(&camera->consumer_tick);
    d->request = request;
    uint32_t counter = 0;
    if (!(request & 3u)) { counter = 3; goto finish; }
    if (!tick || tick - d->consumer_tick > M10V_LIVE_INGRESS_LEASE_MS) {
        counter = 4; goto finish;
    }
    if (tick - camera->frame_tick < M10V_LIVE_INGRESS_STEP_MS) {
        counter = 5; goto finish;
    }
    /* Lease/off/pacing failures retain this last safely inspected source.
     * Otherwise a later stale lease hides the source rejection that preceded
     * it, as happened with all216 source rejections in the R12 device log. */
    d->recipe = recipe; d->config = config; d->y = y; d->uv = uv;
    d->recipe_kind = d->descriptor_index = 0xffffffffu;
    d->reason = source_reason(recipe, config, y, uv, d);
    if (d->reason) { counter = 6; goto finish; }
    if ((request & 3u) == 2 &&
        (load(&arena->shutter.request) != request || tick - load(&arena->shutter.tick) > 6500u)) {
        counter = 7; goto finish;
    }
    uint32_t ordinal = camera->next_frame + 1u;
    if (ordinal >= 0x80000000u) goto finish;
    camera->next_frame = ordinal;
    camera->frame_tick = tick;
    uint32_t slot = camera->frame_slot;
    if (slot >= M10V_LIVE_INGRESS_SLOTS) goto finish;
    camera->frame_slot = slot == M10V_LIVE_INGRESS_SLOTS - 1u ? 0 : slot + 1u;
    m10v_live_ingress_frame *frame = &arena->frames[slot];
    publish(&frame->seq, (ordinal << 1) | 1u);
    clean(frame, M10V_LIVE_INGRESS_ALIGNMENT);
    /* The DMA-scaled source is borrowed only for this native display call.
     * Synchronize before a bounded luma copy, leaving stock planes untouched.
     * The fixed neutral chroma plane is initialized by the AppMain owner. */
    ((void (*)(const void *, uint32_t))0x5383c834u)(bytes(y), SOURCE_PITCH * SOURCE_HEIGHT);
    uint8_t *dst = frame->data;
    uint32_t step=0;
    do {
        const uint8_t *src=bytes(y+SOURCE_PITCH*(step>>1));
        uint32_t col=0;
        do { *dst++=src[col>>2]; col+=21u; } while (col!=192u*21u);
        step+=7u;
    } while (step!=128u*7u);
    if (load(&arena->control.request) != request) goto finish;
    clean(frame->data, M10V_LIVE_INGRESS_FRAME_BYTES);
    frame->tick = tick;
    frame->request = request;
    publish(&frame->seq, ordinal << 1);
    clean(frame, M10V_LIVE_INGRESS_ALIGNMENT);
    counter = 8;
finish:
    if (counter) ++((uint32_t *)d)[counter];
    diagnostic_publish(camera, arena);
}

void m10v_live_camera_shutter(uint32_t si, uint32_t generation) {
    m10v_live_camera *camera = m10v_live_device_camera();
    if (!camera || !generation) return;
    m10v_live_ingress *arena = __atomic_load_n(&camera->arena, __ATOMIC_ACQUIRE);
    if (!arena) return;
    uint32_t request = load(&arena->control.request);
    if (!(request & 3u)) return;
    m10v_live_ingress_shutter *shot = &arena->shutter;
    uint32_t tick = ticks(), next = load(&shot->seq) + 2u;
    /* One exposure can collect a post-window at a time. Neither the physical
     * shutter nor the still writer waits when a clip is already pending. */
    if (!tick || !next || tick - load(&camera->consumer_tick) > M10V_LIVE_INGRESS_LEASE_MS ||
        (shot->request == request && tick - shot->tick < 1700u)) return;
    publish(&shot->seq, next - 1u);
    clean(shot, sizeof(*shot));
    camera->shot_si = si;
    camera->shot_generation = generation;
    for (uint32_t i = 0; i < 3; ++i) shot->token[i] = camera->nonce[i];
    shot->token[3] = next >> 1;
    shot->request = request;
    shot->tick = tick;
    publish(&shot->seq, next);
    clean(shot, sizeof(*shot));
}

static __attribute__((noinline)) void insert_tag_common(void *ifd,uint32_t tag,uint32_t bytes) {
    uint32_t *entry = ((void *(*)(uint32_t))0x535d0998u)(24);
    if (!entry) return;
    ((void (*)(void *,uint32_t,uint32_t,uint32_t,uint32_t))0x535d0230u)
        (entry,tag,7,bytes,0);
    ((void (*)(void *,void *))0x535cfaa0u)(ifd,entry);
}
void m10v_live_camera_insert_tag(void *ifd) {
    insert_tag_common(ifd,M10V_LIVE_EXIF_TAG,M10V_LIVE_EXIF_WORDS*4);
}

int m10v_live_camera_write_tag(const uint32_t *setter, uint32_t *entry) {
    if (entry[1] != (7u << 16 | M10V_LIVE_EXIF_TAG) ||
        entry[2] != M10V_LIVE_EXIF_WORDS * 4 || !lower_ram(entry[4], M10V_LIVE_EXIF_WORDS * 4))
        return 1;
    ((void (*)(void *))0x535d02f4u)(entry);
    uint32_t si = setter[6];
    m10v_live_camera *camera = m10v_live_device_camera();
    if (!camera) return 1;
    m10v_live_ingress *arena = __atomic_load_n(&camera->arena, __ATOMIC_ACQUIRE);
    if (!arena) return 1;
    const m10v_live_ingress_shutter *shot = &arena->shutter;
    uint32_t seq = load(&shot->seq);
    if (!seq || (seq & 1u) || camera->shot_si != si) return 1;
    const m10v_film_identity *lease = m10v_film_identity_owned(si);
    if (!lease || load(&lease->generation) != camera->shot_generation) return 1;
    uint32_t marker[M10V_LIVE_EXIF_WORDS] = {M10V_LIVE_EXIF_MAGIC, M10V_LIVE_INGRESS_VERSION};
    for (uint32_t i = 0; i < 4; ++i) marker[i + 2] = load(&shot->token[i]);
    if (load(&shot->seq) == seq)
        ((void (*)(void *,const void *,uint32_t))0x535d034cu)(entry, marker, sizeof(marker));
    return 1;
}
