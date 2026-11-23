/* Checked GR III 2.10 still Store adapters. Only metadata entry operations
 * use native allocation. Scheduler and writer observations only copy scalars. */
#include "m10v_film_identity.h"
#include "m10v_recorded_film.h"
#include "m10v_roll_capture.h"
#include "m10v_save_trace.h"
#if M10V_LIVE_NATIVE_DEVICE
#include "m10v_live_camera.h"
#endif

enum {
    STORE_REQUEST = 0x00800001,
    GROUP_METADATA_BYTES = 0x365c,
    GROUP_JPEG = 0x14,
    GROUP_DNG = 0x1178,
    GROUP_STRIDE = 0x5cc,
    DESCRIPTOR_SI = 0x134,
    DESCRIPTOR_WRITER = 0x45c,
    DESCRIPTOR_INFO = 0x478,
    DESCRIPTOR_REGISTRY = 0x3f0
};

static int ram(uint32_t address, uint32_t bytes) {
    return !(address & 3u) && address >= 0x55000000u && address <= 0x80000000u - bytes;
}

static uint32_t word(uint32_t address) {
    return *(const volatile uint32_t *)(uintptr_t)address;
}

static uint32_t load(const uint32_t *p) {
    return __atomic_load_n(p, __ATOMIC_ACQUIRE);
}

static void store(uint32_t *p, uint32_t value) {
    __atomic_store_n(p, value, __ATOMIC_RELEASE);
}

static uint32_t observe(const uint32_t *p) {
    return __atomic_load_n(p, __ATOMIC_RELAXED);
}

static void sample(uint32_t *p, uint32_t value) {
    __atomic_store_n(p, value, __ATOMIC_RELAXED);
}

static void lcd_submit(uint32_t recipe, int configured) {
    m10v_roll_capture_channel *channel = m10v_roll_device_capture_channel();
    if (!channel || !ram(recipe, 0x184)) return;
    uint32_t *counter = configured ? &channel->lcd_configured : &channel->lcd_direct;
    /* The calls originate in the same native display recipe, and only the
     * descriptor's small geometry word is read. Neither plane is touched. */
    sample(counter, observe(counter) + 1);
    sample(&channel->visible_geometry, word(recipe + 0x180));
}

#if M10V_LIVE_NATIVE_DEVICE
#define LCD_ARGS uint32_t recipe, uint32_t config, uint32_t y, uint32_t uv
#define LIVE_PREVIEW() m10v_live_camera_display(recipe, config, y, uv)
#else
#define LCD_ARGS uint32_t recipe
#define LIVE_PREVIEW() ((void)0)
#endif

void m10v_roll_camera_lcd_direct(LCD_ARGS) {
    lcd_submit(recipe, 0);
    LIVE_PREVIEW();
}

void m10v_roll_camera_lcd_configured(LCD_ARGS) {
    lcd_submit(recipe, 1);
    LIVE_PREVIEW();
}

static int claimed(const m10v_roll_capture_channel *channel) {
    return channel && load(&channel->state) == M10V_ROLL_CAPTURE_CLAIMED;
}

static int same_shot(const m10v_roll_capture_channel *channel, uint32_t si) {
    if (!claimed(channel) || load(&channel->si) != si) return 0;
    m10v_film_identity *lease = m10v_film_identity_owned(si);
    return lease && load(&lease->generation) == load(&channel->si_generation);
}

void m10v_roll_camera_reserve(uint32_t recipe) {
    m10v_roll_capture_channel *channel = m10v_roll_device_capture_channel();
    if (!channel || !ram(recipe, M10V_SAVE_RECIPE_BYTES + 4u) || word(recipe) != 0x53d0fc90u ||
        word(recipe + M10V_SAVE_RECIPE_BYTES) != M10V_SAVE_TRACE_MAGIC ||
        word(recipe + 0x18u) > 8u)
        return;
    sample(&channel->lcd_direct_at_still, observe(&channel->lcd_direct));
    sample(&channel->lcd_configured_at_still, observe(&channel->lcd_configured));
    sample(&channel->still_producer, observe(&channel->still_producer) + 1);
#if !M10V_LIVE_NATIVE_DEVICE
    if (load(&channel->state) != M10V_ROLL_CAPTURE_ARMED) return;
#endif
    uint32_t si = word(recipe + 0x44c8u);
    m10v_film_identity *lease = m10v_film_identity_owned(si);
    if (!lease) return;
#if M10V_LIVE_NATIVE_DEVICE
    m10v_live_camera_shutter(si, load(&lease->generation));
    if (load(&channel->state) != M10V_ROLL_CAPTURE_ARMED) return;
#endif
    const volatile uint8_t *shot = (const volatile uint8_t *)(uintptr_t)si;
    uint32_t tone = shot[0x77cu];
    /* 53510558 loads the captured ratio into the original size calculation.
     * The selected film ID must also agree with the frozen ImageTone marker. */
    uint32_t aspect = shot[0x7b6u], code = m10v_film_identity_read(si);
    m10v_recorded_film recorded;
    uint32_t film= tone == 22u ? 0x10016u :
        m10v_recorded_film_read(code,&recorded) ? recorded.id : 0;
    if (film && m10v_roll_capture_reserve(channel, si, load(&lease->generation), tone, aspect, film))
        sample(&channel->still_claimed, observe(&channel->still_claimed) + 1);
}

static uint32_t output_kind(const m10v_roll_capture_channel *channel, uint32_t group, uint32_t descriptor) {
    uint32_t base = group + GROUP_STRIDE * channel->save.stream;
    if (descriptor == base + GROUP_JPEG) return channel->save.expected & M10V_ROLL_SAVE_JPEG;
    if (descriptor == base + GROUP_DNG) return channel->save.expected & M10V_ROLL_SAVE_DNG;
    return 0;
}

void m10v_roll_camera_group_start(uint32_t request, uint32_t config) {
    (void)config;
    m10v_roll_capture_channel *channel = m10v_roll_device_capture_channel();
    if (!claimed(channel) || load(&channel->group) || !ram(request, 0x14u) ||
        word(request + 0xcu) != STORE_REQUEST)
        return;
    /* At the native enqueue r4 holds fp-0x38, the completion holder.
     * Use the reserved exposure and the descriptors' own frozen SI values. */
    uint32_t group = word(request + 8u), si = load(&channel->si);
    if (!same_shot(channel, si) || !ram(group, GROUP_METADATA_BYTES)) return;
    const volatile uint8_t *present = (const volatile uint8_t *)(uintptr_t)group;
    uint32_t mask = 0, stream = 0;
    /* The ordinary still plan uses one media stream. Other groups still pass
     * through stock. Keep the receipt unavailable if their outputs are opaque. */
    for (uint32_t i = 0; i < 3; i++) {
        uint32_t next = (present[i] ? M10V_ROLL_SAVE_JPEG : 0u) |
                        (present[i + 3] ? M10V_ROLL_SAVE_DNG : 0u);
        if (present[i + 6] || (mask && next)) {
            store(&channel->group, group);
            return;
        }
        if (next) {
            mask = next;
            stream = i;
        }
    }
    uint32_t base = group + GROUP_STRIDE * stream;
    if ((!(mask & M10V_ROLL_SAVE_JPEG) || word(base + GROUP_JPEG + DESCRIPTOR_SI) == si) &&
        (!(mask & M10V_ROLL_SAVE_DNG) || word(base + GROUP_DNG + DESCRIPTOR_SI) == si) &&
        m10v_roll_save_begin(&channel->save, load(&channel->ticket), group, si, stream, mask))
        store(&channel->group, group);
}

static uint32_t writer_kind(const m10v_roll_capture_channel *channel, uint32_t writer) {
    if (!claimed(channel) || !ram(writer, 0x1cu)) return 0;
    uint32_t group = load(&channel->group), descriptor = word(writer + 0x10u);
    if (!group || writer != descriptor + DESCRIPTOR_WRITER ||
        !ram(descriptor, DESCRIPTOR_INFO + 0x18u) ||
        word(writer + 4u) != descriptor + DESCRIPTOR_INFO ||
        word(writer + 8u) != descriptor + DESCRIPTOR_REGISTRY)
        return 0;
    uint32_t kind = output_kind(channel, group, descriptor);
    return kind && same_shot(channel, word(descriptor + DESCRIPTOR_SI)) ? kind : 0;
}

void m10v_roll_camera_writer_start(uint32_t writer) {
    m10v_roll_capture_channel *channel = m10v_roll_device_capture_channel();
    uint32_t kind = writer_kind(channel, writer);
    if (!kind) return;
    __atomic_fetch_and(&channel->marked_outputs, ~kind, __ATOMIC_RELEASE);
    __atomic_fetch_and(&channel->reached_outputs, ~kind, __ATOMIC_RELEASE);
    store(&channel->writer, writer);
}

void m10v_roll_camera_writer_finish(uint32_t writer) {
    m10v_roll_capture_channel *channel = m10v_roll_device_capture_channel();
    if (claimed(channel) && load(&channel->writer) == writer) store(&channel->writer, 0);
}

void m10v_roll_camera_writer_phases(uint32_t info) {
    m10v_roll_capture_channel *channel = m10v_roll_device_capture_channel();
    if (!claimed(channel)) return;
    uint32_t writer = load(&channel->writer), kind = writer_kind(channel, writer);
    if (kind && word(writer + 4u) == info)
        __atomic_fetch_or(&channel->reached_outputs, kind, __ATOMIC_RELEASE);
}

void m10v_roll_camera_output(uint32_t writer, uint32_t descriptor, uint32_t group, uint32_t status) {
    m10v_roll_capture_channel *channel = m10v_roll_device_capture_channel();
    uint32_t kind = writer_kind(channel, writer);
    if (!kind || load(&channel->group) != group || word(writer + 0x10u) != descriptor) return;
    uint32_t evidence = load(&channel->reached_outputs) & load(&channel->marked_outputs) & kind;
    (void)m10v_roll_save_output(&channel->save, load(&channel->ticket), group, descriptor,
                               word(descriptor + DESCRIPTOR_SI), evidence != 0, status);
}

void m10v_roll_camera_group_finish(uint32_t group, uint32_t event) {
    m10v_roll_capture_channel *channel = m10v_roll_device_capture_channel();
    if (!claimed(channel) || !group || load(&channel->group) != group || event != STORE_REQUEST) return;
    uint32_t si = load(&channel->si), generation = load(&channel->si_generation);
    int32_t result = m10v_roll_save_end(&channel->save, load(&channel->ticket), group, event);
    /* A partial or failed writer can still have left a tag on the medium.
     * Require storage reconciliation before attempting the same frame again. */
    (void)m10v_roll_capture_complete(channel, si, generation, result > 0 ? result : M10V_ROLL_SAVE_UNKNOWN);
}

void m10v_roll_camera_insert_tag(void *ifd) {
#if M10V_ROLL_LIVE_AMALGAMATION
    insert_tag_common(ifd, M10V_ROLL_EXIF_TAG, M10V_ROLL_MARKER_BYTES);
#else
    /* The stock JPEG and DNG contexts build their IFD before binding the
     * shot registry. Keep this slot fixed for the context's lifetime. */
    uint32_t *entry = ((void *(*)(uint32_t))0x535d0998u)(24);
    if (!entry) return;
    ((void (*)(void *,uint32_t,uint32_t,uint32_t,uint32_t))0x535d0230u)
        (entry, M10V_ROLL_EXIF_TAG, 7, M10V_ROLL_MARKER_BYTES, 0);
    ((void (*)(void *,void *))0x535cfaa0u)(ifd, entry);
#endif
}

int m10v_roll_camera_write_tag(const uint32_t *setter, uint32_t *entry) {
    if (entry[1] != (7u << 16 | M10V_ROLL_EXIF_TAG) ||
        entry[2] != M10V_ROLL_MARKER_BYTES || !ram(entry[4], M10V_ROLL_MARKER_BYTES))
        return 1;

    /* Offsets are already fixed. A reused context must serialize zeros for
     * a shot with no matching lease, never the previous shot's roll marker. */
    ((void (*)(void *))0x535d02f4u)(entry);
    uint32_t si = setter[6];
    m10v_roll_capture_channel *channel = m10v_roll_device_capture_channel();
    if (!same_shot(channel, si)) return 1;
    uint8_t marker[M10V_ROLL_MARKER_BYTES];
    if (!m10v_roll_capture_copy_marker(channel, si, load(&channel->si_generation), marker)) return 1;
    ((void (*)(void *,const void *,uint32_t))0x535d034cu)(entry, marker, sizeof(marker));

    const uint8_t *readback = (const void *)(uintptr_t)entry[4];
    for (uint32_t i = 0; i < sizeof(marker); i++)
        if (readback[i] != marker[i]) return 1;
    uint32_t writer = load(&channel->writer), kind = writer_kind(channel, writer);
    if (kind && word(word(writer + 0x10u) + DESCRIPTOR_SI) == si)
        __atomic_fetch_or(&channel->marked_outputs, kind, __ATOMIC_RELEASE);
    return 1;
}
