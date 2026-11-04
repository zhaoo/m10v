#include "m10v_debug.h"
#include "m10v_guides.h"
#include "m10v_guides_camera.h"

#ifndef M10V_GUIDES_OWNER_OFFSET
#error "Allocate the guides state in TopMenu before installing the hooks"
#endif
#ifndef M10V_GUIDES_ASPECT
#define M10V_GUIDES_ASPECT 0
#endif
#ifndef M10V_CAMERA_GR3X
#define M10V_CAMERA_GR3X 0
#endif

#define WORD(p, o) (*(volatile uint32_t *)((uintptr_t)(p) + (o)))
#define HALF(p, o) (*(volatile uint16_t *)((uintptr_t)(p) + (o)))
#define BYTE(p, o) (*(volatile uint8_t *)((uintptr_t)(p) + (o)))
#define CALL(address, type) ((type)(uintptr_t)(address))

enum {
    MAGIC = 0x5344474du,
    STOCK_STYLES = 2,
    FIRST_CAPTION = 1181,
    STOCK_ICON = 0x150,
    STOCK_TITLE = 0x1ed
};

typedef struct {
    uint32_t owner, magic;
    uint32_t live, canvas, active_mode, active_ratio;
    uint32_t painted_bitmap, dirty;
    uint32_t mode, restored;
#if M10V_DEBUG_MODE && M10V_ADJ_EXIT_TRACE
    uint32_t trace_update;
#endif
} guide_state;

_Static_assert(sizeof(guide_state) <= 0x700, "guides ownership allocation");

typedef struct {
    uint32_t magic, version, sequence, mode, crc;
} guide_record;

_Static_assert(sizeof(guide_record) == 20, "guides journal ABI");

static const char files[2][12] = {"M10VGD0.BIN", "M10VGD1.BIN"};

static int address_range(uint32_t address, uint32_t bytes, uint32_t low)
{
    return !(address & 3u) && address >= low && address < 0x80000000u &&
           bytes <= 0x80000000u - address;
}

static guide_state *state_at(uint32_t owner)
{
    if (!address_range(owner, M10V_GUIDES_OWNER_OFFSET + sizeof(guide_state), 0x55000000u))
        return 0;
    return (guide_state *)(uintptr_t)(owner + M10V_GUIDES_OWNER_OFFSET);
}

static guide_state *current_state(void)
{
    if (!(WORD(0x55063910u, 0) & 1u))
        return 0;
    uint32_t owner = WORD(0x55063988u, 0);
    guide_state *state = state_at(owner);
    return state && state->magic == MAGIC && state->owner == owner ? state : 0;
}

void m10v_guides_camera_init(uint32_t owner)
{
    guide_state *state = state_at(owner);
    if (!state)
        return;
    for (uint32_t offset = 0; offset < sizeof(*state); offset += 4)
        WORD(state, offset) = 0;
    state->owner = owner;
    state->magic = MAGIC;
}

void m10v_guides_camera_dispose(uint32_t owner)
{
    guide_state *state = state_at(owner);
    if (state && state->owner == owner)
        state->magic = 0;
}

static uint32_t mounted_storage(void)
{
    uint32_t manager = CALL(0x53828014, uint32_t (*)(void))();
    if (!address_range(manager, 12, 0x55000000u))
        return 0;
    uint32_t slot = WORD(manager, 8);
    if (!address_range(slot, 4, 0x55000000u))
        return 0;
    uint32_t fs = WORD(slot, 0);
    return address_range(fs, 0x24, 0x55000000u) && BYTE(fs, 0x20) ? fs : 0;
}

static uint32_t checksum(const guide_record *record)
{
    const uint8_t *data = (const uint8_t *)record;
    uint32_t crc = 0xffffffffu;
    for (uint32_t i = 0; i < 16; ++i) {
        crc ^= data[i];
        for (uint32_t bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}

static int read_record(uint32_t fs, uint32_t page, guide_record *record)
{
    for (uint32_t offset = 0; offset < sizeof(*record); offset += 4)
        WORD(record, offset) = 0;
    typedef uint32_t (*Read)(uint32_t, const char *, uint32_t, void *);
    return CALL(0x53825648, Read)(fs, files[page], sizeof(*record), record) &&
           record->magic == MAGIC && record->version == 1 && record->sequence &&
           (record->sequence & 1u) == page && record->mode < M10V_GUIDES_MODE_COUNT &&
           record->crc == checksum(record);
}

static uint32_t latest(uint32_t fs, uint32_t *mode)
{
    guide_record first, second;
    int have_first = read_record(fs, 0, &first);
    int have_second = read_record(fs, 1, &second);
    if (!have_first && !have_second)
        return 0;
    const guide_record *record =
        have_first && (!have_second || first.sequence > second.sequence) ? &first : &second;
    *mode = record->mode;
    return record->sequence;
}

static void restore(guide_state *state, uint32_t fs)
{
    if (state->restored)
        return;
    state->restored = 1;
    if (fs)
        latest(fs, &state->mode);
}

static uint32_t live_canvas(uint32_t live)
{
    if (!address_range(live, 0x2d3, 0x55000000u))
        return 0;
    uint32_t canvas = WORD(live, 0x15c);
    if (WORD(live, 4) != canvas || !address_range(canvas, 0xec + 4, 0x55000000u))
        return 0;
    return canvas;
}

static void retire_canvas(guide_state *state)
{
    state->canvas = 0;
    state->active_mode = 0;
    state->active_ratio = 0;
    state->painted_bitmap = 0;
    state->dirty = 0;
}

void m10v_guides_camera_restore(uint32_t live)
{
    guide_state *state = current_state();
    if (!state || !address_range(live, 0x2d3, 0x55000000u) || BYTE(live, 0x2d2))
        return;
    if (state->live != live) {
        retire_canvas(state);
        state->live = live;
    }
    if (!state->restored) {
        M10V_EXIT_LOG(276, live, state->mode, 0, 0);
        restore(state, mounted_storage());
#if M10V_DEBUG_MODE && M10V_ADJ_EXIT_TRACE
        state->trace_update = state->mode != M10V_GUIDES_OFF;
#endif
        M10V_EXIT_LOG(277, live, state->mode, 0, 0);
    }
    /* Native LiveView::Update schedules redraw after the screen handoff. */
}

void m10v_guides_camera_leave(uint32_t live)
{
    guide_state *state = current_state();
    if (!state || state->live != live)
        return;
    if (state->dirty && state->canvas && state->canvas == live_canvas(live))
        BYTE(state->canvas, 0xa0) = 1;
    state->live = 0;
    retire_canvas(state);
}

uint32_t m10v_guides_camera_mode(void)
{
    guide_state *state = current_state();
    return state && state->mode < M10V_GUIDES_MODE_COUNT ? state->mode : M10V_GUIDES_OFF;
}

uint32_t m10v_guides_camera_set_mode(uint32_t mode)
{
    guide_state *state = current_state();
    if (!state || mode >= M10V_GUIDES_MODE_COUNT)
        return 0;
    if (state->restored && state->mode == mode)
        return 1;

    uint32_t fs = mounted_storage();
    restore(state, fs);
    if (state->mode == mode)
        return 1;
    if (fs) {
        /* Read the mounted card at commit. It may differ from the card whose
         * settings were restored when this owner was created. */
        uint32_t old_mode;
        uint32_t sequence = latest(fs, &old_mode);
        if (sequence == UINT32_MAX)
            return 0;
        guide_record record = {MAGIC, 1, sequence + 1, mode, 0};
        record.crc = checksum(&record);
        uint32_t page = record.sequence & 1u;
        typedef uint32_t (*Write)(uint32_t, const char *, uint32_t, const void *);
        guide_record readback;
        if (!CALL(0x53825fa8, Write)(fs, files[page], sizeof(record), &record) ||
            !read_record(fs, page, &readback) ||
            readback.sequence != record.sequence || readback.mode != record.mode)
            return 0;
    }
    /* The option callback may run while its parent still owns the display.
     * Publish the mode here and leave redraw to native LiveView::Update. */
    state->mode = mode;
#if M10V_DEBUG_MODE && M10V_ADJ_EXIT_TRACE
    state->trace_update = 1;
#endif
    return 1;
}

uint32_t m10v_guides_camera_count(void)
{
    return STOCK_STYLES + M10V_GUIDES_MODE_COUNT - 1u;
}

static uint32_t caption(uint32_t mode)
{
    return FIRST_CAPTION + mode - 1;
}

void m10v_guides_camera_draw(uint32_t context, uint32_t view, uint32_t row)
{
    typedef void (*Draw)(uint32_t, uint32_t, uint32_t);
    if (row < STOCK_STYLES)
        CALL(0x531b5c74, Draw)(context, view, row);
    else if (row < m10v_guides_camera_count())
        CALL(0x5339e8b0, Draw)(view, STOCK_ICON, caption(row - STOCK_STYLES + 1));
}

/* Grid Style and Grid Guide are distinct native properties. Applying a
 * style explicitly enables the Grid Guide for the current DISP profile.
 * The native setters only update that flag in the user settings banks. */
static void enable_current_grid_profile(void)
{
    uint32_t root = CALL(0x5320ad88, uint32_t (*)(void))();
    if (!root)
        return;
    uint32_t wrapper = CALL(0x5320b31c, uint32_t (*)(uint32_t))(root);
    if (!address_range(wrapper, 0x24, 0x55000000u))
        return;
    uint32_t properties = WORD(wrapper, 4);
    if (!address_range(properties, 0x913, 0x55000000u))
        return;
    uint32_t display = CALL(0x53246318, uint32_t (*)(uint32_t))(wrapper);
    if (display > 2 || BYTE(properties, 0x8e2 + display * 2))
        return;
    for (uint32_t offset = 8; offset <= 0x20; offset += 4) {
        if (!address_range(WORD(wrapper, offset), 0x8e8, 0x55000000u))
            return;
    }
    typedef uint32_t (*Set)(uint32_t, uint32_t);
    CALL(0x5324325c + display * 0x24, Set)(wrapper, 1);
}

uint32_t m10v_guides_camera_apply(uint32_t context, uint32_t row)
{
    typedef uint32_t (*Apply)(uint32_t, uint32_t);
    M10V_EXIT_LOG(274, context, row, m10v_guides_camera_mode(), 0);
    uint32_t result;
    if (row < STOCK_STYLES) {
        result = m10v_guides_camera_mode() && !m10v_guides_camera_set_mode(M10V_GUIDES_OFF) ?
                 0 : CALL(0x531b7604, Apply)(context, row);
    } else {
        result = row < m10v_guides_camera_count() &&
                 m10v_guides_camera_set_mode(row - STOCK_STYLES + 1);
    }
    if (result)
        enable_current_grid_profile();
    M10V_EXIT_LOG(275, context, row, m10v_guides_camera_mode(), result);
    return result;
}

uint32_t m10v_guides_camera_checked(uint32_t context, uint32_t row)
{
    typedef uint32_t (*Checked)(uint32_t, uint32_t);
    uint32_t mode = m10v_guides_camera_mode();
    if (mode)
        return row == STOCK_STYLES + mode - 1;
    return row < STOCK_STYLES && CALL(0x531b8de8, Checked)(context, row);
}

void m10v_guides_camera_summary(uint32_t context, uint32_t view)
{
    uint32_t mode = m10v_guides_camera_mode();
    if (!mode) {
        CALL(0x53198560, void (*)(uint32_t, uint32_t))(context, view);
        return;
    }
    CALL(0x5339de20, void (*)(uint32_t, uint32_t))(view, STOCK_ICON);
    CALL(0x5339dc70, void (*)(uint32_t, uint32_t, uint32_t))(view, STOCK_TITLE, STOCK_TITLE);
}

/* Match the still Grid Guide visibility controls selected by the original
 * LiveView grid setup at 0x5317750c. The same stored flags remain editable
 * in the original DISP settings. This never takes over the DISP key. */
static int visible(uint32_t live)
{
    if (BYTE(live, 0x2d2))
        return 0;
    uint32_t display = BYTE(live, 0x2d1);
    if (display > 2)
        return 0;
    uint32_t owner = WORD(0x55063f34u, 0);
    if (!address_range(owner, 0x913, 0x55000000u) || BYTE(owner, 0x912) == 3)
        return 0;
    uint32_t root = CALL(0x5320ad88, uint32_t (*)(void))();
    if (!root)
        return 0;
    uint32_t wrapper = CALL(0x5320b31c, uint32_t (*)(uint32_t))(root);
    if (!address_range(wrapper, 8, 0x55000000u))
        return 0;
    uint32_t properties = WORD(wrapper, 4);
    if (!address_range(properties, 0x8e8, 0x55000000u))
        return 0;
    return BYTE(properties, 0x8e2 + display * 2) != 0;
}

/* Use the same still/no-override conditions as M10V's crop mask. A zoomed
 * view no longer describes the full saved photo and does not get guides. */
static int photo_ratio(uint32_t *ratio)
{
    uint32_t root = CALL(0x53525d5c, uint32_t (*)(void))();
    if (!address_range(root, 4, 0x55000000u))
        return 0;
    uint32_t info = WORD(root, 0);
    if (!address_range(info, 4, 0x55000000u) ||
        CALL(0x53549958, uint32_t (*)(uint32_t))(info) == 1)
        return 0;
    uint32_t manager = CALL(0x53654150, uint32_t (*)(void))();
    if (!manager || CALL(0x53654220, uint32_t (*)(uint32_t, uint32_t))(manager, 0x4a))
        return 0;
    uint32_t current = CALL(0x5354a778, uint32_t (*)(uint32_t))(info);
    uint32_t limit = M10V_GUIDES_ASPECT ? (M10V_CAMERA_GR3X ? 5u : 6u) : 3u;
    if (current > limit)
        return 0;
    *ratio = current;
    return 1;
}

void m10v_guides_camera_update(uint32_t live)
{
    guide_state *state = current_state();
    /* Only LiveView enter admits an owner. A queued update after native
     * leave must never reattach the guide to a retiring canvas. */
    if (!state || !live || state->live != live)
        return;
    uint32_t canvas = live_canvas(live);
    if (!canvas) {
        retire_canvas(state);
        return;
    }

    uint32_t mode = state->mode, ratio = 0;
    if (mode >= M10V_GUIDES_MODE_COUNT || !mode || !visible(live) || !photo_ratio(&ratio))
        mode = M10V_GUIDES_OFF;

    uint32_t old_mode = state->active_mode;
    int new_canvas = state->canvas != canvas;
    int redraw = new_canvas ? mode != 0 :
                 mode != old_mode || (mode && ratio != state->active_ratio);
    if (new_canvas) {
        state->dirty = 0;
        state->painted_bitmap = 0;
    }
    state->canvas = canvas;
    state->active_mode = mode;
    state->active_ratio = ratio;
#if M10V_DEBUG_MODE && M10V_ADJ_EXIT_TRACE
    uint32_t trace = state->trace_update;
    state->trace_update = 0;
    if (trace)
        M10V_EXIT_LOG(278, live, canvas, state->mode, (ratio << 16) | (mode << 8) | redraw);
#endif
    if (redraw)
        CALL(0x533ad308, void (*)(uint32_t))(canvas);
#if M10V_DEBUG_MODE && M10V_ADJ_EXIT_TRACE
    if (trace)
        M10V_EXIT_LOG(279, live, canvas, state->mode, redraw);
#endif
}

void m10v_guides_camera_prepare(uint32_t canvas)
{
    guide_state *state = current_state();
    if (!state || state->canvas != canvas || !canvas)
        return;
    state->painted_bitmap = 0;
    if (state->active_mode || state->dirty)
        BYTE(canvas, 0xa0) = 1;
}

static void photo_box(m10v_guides_rect *photo, uint32_t width, uint32_t height, uint32_t ratio)
{
    uint32_t left = 0, top = 0, visible_width = width, visible_height = height;
    switch (ratio) {
    case 1:
        visible_width = height * 4 / 3;
        break;
    case 2:
        if (M10V_GUIDES_ASPECT && !M10V_CAMERA_GR3X)
            visible_height = (height * 3376 / 4000 / 2) * 2;
        else
            visible_height = width * 9 / 16;
        break;
    case 3:
        visible_width = height;
        break;
    case 4:
        visible_height = height - (width == 720 ? 216 : 108);
        break;
    case 5:
        visible_width = width - (width == 720 ? 160 : 80);
        break;
    case 6:
        left = (width - height * 2992 / 4000 + 1) / 2;
        visible_width = width - 2 * left;
        break;
    default:
        break;
    }
    left = (width - visible_width) / 2;
    top = (height - visible_height) / 2;
    photo->left = left;
    photo->top = top;
    photo->right = left + visible_width;
    photo->bottom = top + visible_height;
}

void m10v_guides_camera_paint(uint32_t canvas, uint32_t bitmap)
{
    guide_state *state = current_state();
    if (!state || !canvas || state->canvas != canvas)
        return;
    state->painted_bitmap = 0;
    state->dirty = 0;
    if (!state->active_mode || !BYTE(canvas, 0x9e) || WORD(canvas, 0x20) || WORD(canvas, 0x24) ||
        WORD(canvas, 0xec) != bitmap || !address_range(bitmap, 0x20, 0x40000000u))
        return;

    uint32_t width = WORD(canvas, 0x28), height = WORD(canvas, 0x2c);
    if (!((width == 720 && height == 480) || (width == 360 && height == 240)) ||
        BYTE(bitmap, 2) != 5 || HALF(bitmap, 0x1c) != width || HALF(bitmap, 0x1e) != height)
        return;

    uint32_t stride = HALF(bitmap, 0x18), address = WORD(bitmap, 8);
    uint32_t bytes = WORD(bitmap, 4);
    if (stride < width || stride > 1024 || HALF(bitmap, 0x1a) != height ||
        bytes < stride * height * 4 || !address_range(address, bytes, 0x40000000u))
        return;

    m10v_guides_surface surface;
    surface.pixels = (volatile uint32_t *)(uintptr_t)address;
    surface.capacity_pixels = bytes / 4;
    surface.stride_pixels = stride;
    surface.width = width;
    surface.height = height;
    surface.clip.left = 0;
    surface.clip.top = 0;
    surface.clip.right = width;
    surface.clip.bottom = height;
    photo_box(&surface.photo, width, height, state->active_ratio);
    m10v_guides_draw(&surface, state->active_mode, 0x80000000u);
    state->dirty = 1;
    state->painted_bitmap = bitmap;
}

void m10v_guides_camera_finish(uint32_t canvas)
{
    guide_state *state = current_state();
    if (state && state->canvas == canvas)
        state->painted_bitmap = 0;
}

uint32_t m10v_guides_camera_suppress_grid(uint32_t grid, uint32_t bitmap)
{
    guide_state *state = current_state();
    if (!state || !state->live || !bitmap || state->painted_bitmap != bitmap ||
        !address_range(grid, 0xa3, 0x55000000u) || WORD(state->live, 0x160) != grid)
        return 0;

    /* Keep the native View::OnDraw bookkeeping from 0x533ab9bc, while
     * withholding just the GridView strokes and its diagonal child lines.
     * Visibility remains intact for GRLife's enclosing mask draw. */
    BYTE(grid, 0xa0) = 0;
    BYTE(grid, 0xa2) = 0;
    BYTE(grid, 0x40) = BYTE(grid, 0x9e) != 0;
    if (BYTE(grid, 0x40)) {
        for (uint32_t offset = 0; offset < 16; offset += 4)
            WORD(grid, 0x44 + offset) = WORD(grid, 0x30 + offset);
    }
    return 1;
}
