/* GR III 2.10 / IIIx 1.60 AdjModeController. The original five cell/icon
 * pairs and still/movie cursor banks retain their original extent. */
#include "m10v_adj_extra_camera.h"
#include "m10v_tone.h"
#include "m10v_debug.h"

#ifndef M10V_ADJ_EXTRA_HDF
#define M10V_ADJ_EXTRA_HDF 0
#endif
#ifndef M10V_BORDER_ENABLED
#define M10V_BORDER_ENABLED 0
#endif

enum {
    ADJ_CELLS = 0x16c, ADJ_FRAME = 0x180, ADJ_ICONS = 0x184,
    ADJ_TITLE = 0x160, ADJ_LIST = 0x1f0, ADJ_SLOT = 0x1f4,
    ADJ_CURSOR = 0x1f8, ADJ_CURSOR_BYTES = 60, ADJ_MOVIE = 0x270,
    ADJ_VTABLE = 0x53b394e0, ADJ_ROUTE = 0x02000000, LIVE_ROUTE = 0x08000000,
    EXTRA_STOCK_ID = 20, EXTRA_PITCH = 50, STRIP_END = 715, ICON_OFFSET = 0xf0,
    STATE_MAGIC = 0x394a4441
};

#define PRIVATE_IDS ((1u << 24) | (1u << 25) | (1u << 26) | (1u << 27) | (1u << M10V_ADJ_EXTRA_BORDER))
#define PERSISTED_IDS ((((1u << 21) - 1u) & ~(1u << 15)) | PRIVATE_IDS)
#define CAMERA_IDS (PERSISTED_IDS & ~(M10V_ADJ_EXTRA_HDF ? 0u : (1u << 20)) & \
    ~(M10V_BORDER_ENABLED ? 0u : (1u << M10V_ADJ_EXTRA_BORDER)))

typedef uint32_t (*fn0)(void);
typedef uint32_t (*fn1)(uint32_t);
typedef uint32_t (*fn2)(uint32_t, uint32_t);
typedef uint32_t (*fn3)(uint32_t, uint32_t, uint32_t);
typedef uint32_t (*fn4)(uint32_t, uint32_t, uint32_t, uint32_t);
typedef uint32_t (*fn5)(uint32_t, uint32_t, uint32_t, uint32_t, uint32_t);
typedef uint32_t (*file_read)(uint32_t, const char *, uint32_t, void *);
typedef uint32_t (*file_write)(uint32_t, const char *, uint32_t, const void *);

extern uint32_t m10v_adj_extra_camera_stock_slot_type(uint32_t, uint32_t);

typedef struct {
    m10v_adj_extra_session session;
    m10v_adj_extra_widget_ops ops;
    uint32_t magic, controller, generation, extra_count, stock_position, focus;
    uint32_t closing, effects_action, suspended, retired_controller, geometry_pending;
    uint32_t lever_pressed, entering;
    uint8_t stock_cursor[ADJ_CURSOR_BYTES], extra_cursor[ADJ_CURSOR_BYTES];
} camera_state;
_Static_assert(sizeof(camera_state) <= 0x100u, "ADJ owner extent");

static const char journal_names[2][12] = {"M10VAD0.BIN", "M10VAD1.BIN"};

static int ram(uint32_t address, uint32_t size)
{
    return !(address & 3u) && address >= 0x55000000u &&
        address < 0x80000000u && size <= 0x80000000u - address;
}

static uint32_t word(uint32_t address, unsigned offset)
{
    return *(const uint32_t *)(uintptr_t)(address + offset);
}

static uint8_t byte(uint32_t address, unsigned offset)
{
    return *(const uint8_t *)(uintptr_t)(address + offset);
}

static void set_byte(uint32_t address, unsigned offset, uint8_t value)
{
    *(uint8_t *)(uintptr_t)(address + offset) = value;
}

static void copy_cursor(void *to, const void *from)
{
    volatile uint8_t *dest = to;
    const volatile uint8_t *source = from;
    for (unsigned i = 0; i < ADJ_CURSOR_BYTES; ++i) dest[i] = source[i];
}

static void clear(void *to, unsigned bytes)
{
    volatile uint8_t *dest = to;
    for (unsigned i = 0; i < bytes; ++i) dest[i] = 0;
}

static camera_state *state_at(uint32_t owner)
{
    if (!ram(owner, M10V_ADJ_EXTRA_OWNER_OFFSET + 0x100u)) return 0;
    return (camera_state *)(uintptr_t)(owner + M10V_ADJ_EXTRA_OWNER_OFFSET);
}

static camera_state *state(void)
{
    if (!(word(0x55063910u, 0) & 1u)) return 0;
    camera_state *s = state_at(word(0x55063988u, 0));
    return s && s->magic == STATE_MAGIC ? s : 0;
}

void m10v_adj_extra_camera_init(uint32_t owner)
{
    camera_state *s = state_at(owner);
    if (!s) return;
    clear(s, sizeof(*s));
    s->magic = STATE_MAGIC;
}

static uint32_t filesystem(void)
{
    uint32_t manager = ((fn0)0x53828014u)();
    if (!ram(manager, 12)) return 0;
    uint32_t app = word(manager, 8);
    if (!ram(app, 4)) return 0;
    uint32_t fs = word(app, 0);
    return ram(fs, 0x24) && byte(fs, 0x20) ? fs : 0;
}

static int latest(uint32_t fs, m10v_adj_extra_assignments *out,
    uint32_t *sequence, unsigned *read_mask)
{
    uint8_t data[2][M10V_ADJ_EXTRA_RECORD_SIZE];
    size_t sizes[2] = {0, 0};
    *read_mask = 0;
    for (unsigned i = 0; i < 2; ++i) {
        clear(data[i], sizeof(data[i]));
        if (((file_read)0x53825648u)(fs, journal_names[i], sizeof(data[i]), data[i])) {
            sizes[i] = sizeof(data[i]);
            *read_mask |= 1u << i;
        }
    }
    return m10v_adj_extra_select_newest(data[0], sizes[0], data[1], sizes[1],
        PERSISTED_IDS, out, sequence);
}

int m10v_adj_extra_camera_load(m10v_adj_extra_assignments *out)
{
    if (!out) return 0;
    clear(out, sizeof(*out));
    uint32_t fs = filesystem(), sequence;
    unsigned read_mask;
    return fs && latest(fs, out, &sequence, &read_mask) >= 0;
}

int m10v_adj_extra_camera_assign(unsigned logical_slot, unsigned function)
{
    unsigned index = logical_slot - M10V_ADJ_EXTRA_FIRST_SLOT;
    if (index >= M10V_ADJ_EXTRA_SLOT_COUNT ||
        function >= 32u || !(CAMERA_IDS & (1u << function))) return 0;
    uint32_t fs = filesystem(), sequence = 0;
    if (!fs) return 0;
    m10v_adj_extra_assignments a = {{0}}, back;
    unsigned read_mask;
    int current = latest(fs, &a, &sequence, &read_mask);
    /* Two unusable existing pages require an explicit recovery decision. */
    if (current < 0 && read_mask) return 0;
    if (a.function[index] == function) return 1;
    a.function[index] = (uint8_t)function;
    uint8_t data[M10V_ADJ_EXTRA_RECORD_SIZE];
    unsigned target = current == 0 ? 1 : 0;
    if (!m10v_adj_extra_encode(&a, PERSISTED_IDS, ++sequence, data, sizeof(data)) ||
        !((file_write)0x53825fa8u)(fs, journal_names[target], sizeof(data), data))
        return 0;
    uint32_t actual_sequence = 0;
    if (latest(fs, &back, &actual_sequence, &read_mask) != (int)target ||
        actual_sequence != sequence) return 0;
    for (unsigned i = 0; i < M10V_ADJ_EXTRA_SLOT_COUNT; ++i)
        if (a.function[i] != back.function[i]) return 0;
    return 1;
}

static uint32_t position_x(const camera_state *s, unsigned display_index)
{
    return STRIP_END - EXTRA_PITCH * (5u + s->extra_count - display_index);
}

static unsigned extra_position(const camera_state *s, unsigned logical_slot)
{
    unsigned display_index = 5;
    for (unsigned i = 0; i < logical_slot - M10V_ADJ_EXTRA_FIRST_SLOT; ++i)
        if (s->session.assignments.function[i]) ++display_index;
    return display_index;
}

static uint32_t vector_find(uint32_t parent, uint32_t child)
{
    uint32_t first = word(parent, 0xc), end = word(parent, 0x10);
    if (end < first || !ram(first, end - first) || end - first > 0x400u) return 0;
    for (uint32_t p = first; p < end; p += 4)
        if (word(p, 0) == child) return p;
    return 0;
}

static uint32_t parent_view(uint32_t c)
{
    uint32_t icon = word(c, ADJ_ICONS);
    return ram(icon, 8) ? word(icon, 4) : 0;
}

static void touch(unsigned slot, uint32_t c);
static void touch_token(uint32_t token)
{
    camera_state *s = state();
    if (s && (token >> 2) == s->generation)
        touch(M10V_ADJ_EXTRA_FIRST_SLOT + (token & 3u), s->controller);
}

static uint32_t icon_for(uint8_t function)
{
    unsigned id = function;
    switch (function) {
    case M10V_ADJ_EXTRA_GUIDES: id = 18; break;
    case M10V_ADJ_EXTRA_FILM: id = 12; break;
    case M10V_ADJ_EXTRA_EFFECTS: id = 13; break;
    case M10V_ADJ_EXTRA_ASPECT:
    case M10V_ADJ_EXTRA_BORDER: id = 4; break;
    }
    uint32_t root = ((fn0)0x5320ad88u)();
    uint32_t translator = ((fn1)0x5320b67cu)(root);
    return ((fn2)0x53293a30u)(translator, id);
}

static uintptr_t widget_create(void *context, uintptr_t owner, unsigned slot,
    uint8_t function)
{
    camera_state *s = context;
    (void)owner;
    uint32_t view = ((fn1)0x536af2a8u)(0x1e8u);
    if (!view) return 0;
    uint32_t icon = view + ICON_OFFSET;
    uint32_t x = position_x(s, extra_position(s, slot));
    ((fn5)0x53393d84u)(view, x, 5, 50, 50);
    ((fn2)0x53393e00u)(view, 0x10);
    ((fn5)0x5339a908u)(icon, x + 5, 10, 40, 40);
    ((fn2)0x5339a9a0u)(icon, icon_for(function));
    ((fn2)0x533ad3c0u)(view, 0);
    ((fn2)0x533ad3c0u)(icon, 0);

    /* A nonvirtual native touch binding passes the third word directly
     * when its adjustment is zero. Use a generation token rather than a
     * widget pointer that a queued callback could retain after deletion. */
    uint32_t token = (s->generation << 2) | (slot - M10V_ADJ_EXTRA_FIRST_SLOT);
    uint32_t binding[3] = {(uint32_t)(uintptr_t)touch_token, 0, token};
    uint32_t callbacks[4] = {(uint32_t)(uintptr_t)binding, 0,
        0x531a16c4u, 0x531a1874u};
    ((fn2)0x533abeb0u)(icon, (uint32_t)(uintptr_t)callbacks);
    ((fn2)0x533ac1b4u)(icon, 1);
    return view;
}

static void erase(uint32_t parent, uint32_t child)
{
    uint32_t position = vector_find(parent, child);
    if (position) ((fn2)0x536b6f68u)(parent + 8, position);
}

static int widget_attach(void *context, uintptr_t owner, uintptr_t widget)
{
    (void)context;
    uint32_t c = (uint32_t)owner, view = (uint32_t)widget;
    uint32_t parent = parent_view(c), icon = view + ICON_OFFSET;
    if (!ram(parent, 0x14)) return 0;
    uint32_t marker = vector_find(parent, word(c, ADJ_FRAME));
    if (!marker || !((fn3)0x536b6de4u)(parent + 8, marker,
        (uint32_t)(uintptr_t)&view)) return 0;
    if (!((fn3)0x536b6de4u)(parent + 8, word(parent, 0x10),
        (uint32_t)(uintptr_t)&icon)) {
        erase(parent, view);
        return 0;
    }
    ((fn2)0x533ac120u)(view, parent);
    ((fn2)0x533ac120u)(icon, parent);
    /* SetParent only links the object. For a published canvas, update the
     * new children's absolute bounds and clip against the current parent. */
    ((fn1)0x533ab5d8u)(view);
    ((fn1)0x533ab5d8u)(icon);
    return 1;
}

static void widget_detach(void *context, uintptr_t owner, uintptr_t widget)
{
    (void)context;
    (void)owner;
    uint32_t view = (uint32_t)widget, icon = view + ICON_OFFSET;
    uint32_t parent = word(view, 4);
    if (ram(parent, 0x14)) {
        /* SetParent(0) detaches the view but leaves overlap invalidation
         * references in the canvas and its descendants. Use the same
         * recursive unlink as stock Canvas::UpdateDependencies on removal. */
        ((fn2)0x533acf74u)(parent, icon);
        ((fn2)0x533acf74u)(parent, view);
        erase(parent, icon);
        erase(parent, view);
    }
    ((fn2)0x533ac120u)(icon, 0);
    ((fn2)0x533ac120u)(view, 0);
}

static void widget_destroy(void *context, uintptr_t widget)
{
    (void)context;
    ((fn1)0x5339a874u)((uint32_t)widget + ICON_OFFSET);
    ((fn1)0x53393d54u)((uint32_t)widget);
}

static void init_widget_ops(volatile m10v_adj_extra_widget_ops *ops)
{
    ops->create = widget_create;
    ops->attach = widget_attach;
    ops->detach = widget_detach;
    ops->destroy = widget_destroy;
}

static int native_adj(uint32_t c)
{
    return ram(c, 0x274) && word(c, 0) == ADJ_VTABLE && !byte(c, ADJ_MOVIE);
}

static int has_film(void)
{
    uint32_t root = ((fn0)0x5320ad88u)(), model = ((fn1)0x5320ba9cu)(root);
    if (!ram(model, 0x20) || byte(model, 0x1b) ||
        ((fn1)0x532bd6d4u)(model)) return 0;
    uint32_t slot = m10v_tone_slot(((fn1)0x532bd6b4u)(model));
    return M10V_APPENDED_SLOTS && slot < 10u &&
        slot + 12u < m10v_camera_library_shooting_count();
}

static int stock_available(uint32_t c, uint32_t function)
{
    if (!function || function > EXTRA_STOCK_ID) return 0;
    if (function == EXTRA_STOCK_ID) return M10V_ADJ_EXTRA_HDF;
    uint32_t record = 0x53b39a14u + 0x44u * function;
    uint32_t predicate = word(record, 0x3c), object = word(record, 0x40);
    if (!predicate) return 1;
    if (object & 1u) {
        predicate = word(word(c, object >> 1), predicate);
    }
    return !((fn1)(uintptr_t)predicate)(c + (object >> 1));
}

static unsigned focused(const camera_state *s, uint32_t c)
{
    return s && s->controller == c ? s->focus : 0;
}

uint32_t m10v_adj_extra_camera_virtual_focus(uint32_t c)
{
    return focused(state(), c) && native_adj(c);
}

static uint8_t assignment(const camera_state *s, uint32_t c, unsigned slot)
{
    return m10v_adj_extra_function(&s->session, c, s->generation, slot);
}

uint32_t m10v_adj_extra_camera_slot_type(uint32_t c, uint32_t slot)
{
    camera_state *s = state();
    if (native_adj(c) && focused(s, c) && slot < 5u) {
        if (s->effects_action) return slot == byte(c, ADJ_SLOT) ? 12 : 0;
        uint32_t id = assignment(s, c, M10V_ADJ_EXTRA_FIRST_SLOT + slot);
        return id <= EXTRA_STOCK_ID ? id : 0;
    }
    return m10v_adj_extra_camera_stock_slot_type(c, slot);
}

/* Original descriptor slots 1–3 share x=0,w=400,h=40. Their stock
 * y origins are 0 (title) and 50 (detail label and detail value). */
static void label_bounds(uint32_t c, uint32_t width)
{
    uint32_t rect[4] = {0, 0, width, 40};
    for (unsigned i = 0; i < 3; ++i) {
        uint32_t view = word(c, ADJ_TITLE + 4 * i);
        if (ram(view, 0x64))
            ((fn2)0x533ab548u)(view, (uint32_t)(uintptr_t)rect);
        rect[1] = 50;
    }
}

/* Stock refresh repositions the selection frame only. Keep the fixed
 * strip layout out of selection refresh and its invalidation callbacks. */
static void layout_strip(camera_state *s, uint32_t c)
{
    uint32_t left = position_x(s, 0);
    if (left < 400u) label_bounds(c, left - 10u);
    for (unsigned i = 0; i < 5; ++i) {
        uint32_t x = position_x(s, i);
        ((fn2)0x533ac568u)(word(c, ADJ_CELLS + i * 4), x);
        ((fn2)0x533ac568u)(word(c, ADJ_ICONS + i * 4), x + 5);
    }
}

static void render(camera_state *s, uint32_t c)
{
    unsigned slot = byte(c, ADJ_SLOT);
    if (slot > 4) return;
    unsigned display = s->focus ? extra_position(s, s->focus) : slot;
    ((fn2)0x533ac568u)(word(c, ADJ_FRAME), position_x(s, display));
    if (s->focus) ((fn2)0x533ad3c0u)(word(c, ADJ_FRAME), 1);
    for (unsigned i = 0; i < M10V_ADJ_EXTRA_SLOT_COUNT; ++i) {
        uint32_t view = (uint32_t)s->session.widget[i];
        if (view) {
            ((fn2)0x533ad3c0u)(view, 1);
            ((fn2)0x533ad3c0u)(view + ICON_OFFSET, 1);
        }
    }
    if (s->focus) {
        unsigned id = assignment(s, c, s->focus);
        /* Descriptor slot 1 constructs a CaptionView. Use its resource
         * setter, as stock 531a2be4 does. The ASCII LabelView setter would
         * interpret this object's flags at +0xf0 as a heap pointer. */
        if (id >= M10V_ADJ_EXTRA_GUIDES && id <= M10V_ADJ_EXTRA_BORDER) {
            uint32_t caption = id == M10V_ADJ_EXTRA_BORDER ? 1155u :
                1196u + id - M10V_ADJ_EXTRA_GUIDES;
            ((fn3)0x53396f80u)(word(c, ADJ_TITLE), caption, 0);
        }
    }
}

void m10v_adj_extra_camera_refresh(uint32_t c)
{
    camera_state *s = state();
    if (!s || !native_adj(c) || s->entering == c || s->retired_controller == c ||
        (s->controller && s->controller != c) ||
        !ram(word(c, ADJ_FRAME), 4) || !ram(parent_view(c), 0x14)) return;
    if (s->controller == c) {
        if (!s->closing && s->extra_count) render(s, c);
        return;
    }
    if (s->session.owner) return;
    for (unsigned i = 0; i < 5; ++i)
        if (!ram(word(c, ADJ_CELLS + i * 4), 4) ||
            !ram(word(c, ADJ_ICONS + i * 4), 4)) return;
    s->controller = c;
    s->generation = (s->generation + 1) & 0x3fffffffu;
    if (!s->generation) ++s->generation;
    m10v_adj_extra_assignments a;
    if (!m10v_adj_extra_camera_load(&a)) return;
    for (unsigned i = 0; i < M10V_ADJ_EXTRA_SLOT_COUNT; ++i) {
        uint32_t id = a.function[i];
        if (!(CAMERA_IDS & (1u << id)) ||
            (id <= EXTRA_STOCK_ID && !stock_available(c, id)) ||
            (id == M10V_ADJ_EXTRA_EFFECTS && !has_film()))
            a.function[i] = 0;
        if (a.function[i]) ++s->extra_count;
    }
    init_widget_ops(&s->ops);
    if (!m10v_adj_extra_open(&s->session, c, s->generation, &a,
        CAMERA_IDS, &s->ops, s)) {
        s->extra_count = 0;
        return;
    }
    layout_strip(s, c);
    render(s, c);
}

/* Replay the stock 531a462c register frame, skipping its outgoing cursor save.
 * The caller already saved and exchanged banks before changing the type. */
__attribute__((naked, noinline)) static void select_without_save(
    uint32_t c __attribute__((unused)), uint32_t slot __attribute__((unused)))
{
    __asm__ volatile("mov ip, sp\n"
        ".word 0xe92dd830\n"
        "mov r4, r0\n"
        "mov r5, r1\n"
        "sub fp, ip, #4\n"
        "movw ip, #0x4670\n"
        "movt ip, #0x531a\n"
        "bx ip");
}

static void save_cursor(uint32_t c)
{
    uint32_t slot = byte(c, ADJ_SLOT);
    if (slot > 4) return;
    uint32_t row = c + ADJ_CURSOR + 12 * slot;
    ((fn3)0x533947f0u)(word(c, ADJ_LIST), row + 4, row + 8);
}

static void focus_extra(camera_state *s, uint32_t c, unsigned slot)
{
    if (slot == s->focus) return;
    unsigned physical = slot - M10V_ADJ_EXTRA_FIRST_SLOT;
    if (s->focus) {
        s->focus = slot;
        ((fn2)0x531a462cu)(c, physical);
    } else {
        save_cursor(c);
        s->stock_position = byte(c, ADJ_SLOT);
        copy_cursor(s->stock_cursor, (const void *)(uintptr_t)(c + ADJ_CURSOR));
        copy_cursor((void *)(uintptr_t)(c + ADJ_CURSOR), s->extra_cursor);
        s->focus = slot;
        select_without_save(c, physical);
    }
}

static void restore_stock_bank(camera_state *s, uint32_t c)
{
    if (!s->focus) return;
    copy_cursor(s->extra_cursor, (const void *)(uintptr_t)(c + ADJ_CURSOR));
    copy_cursor((void *)(uintptr_t)(c + ADJ_CURSOR), s->stock_cursor);
    set_byte(c, ADJ_SLOT, (uint8_t)s->stock_position);
    s->focus = 0;
}

static void focus_stock(camera_state *s, uint32_t c, unsigned slot)
{
    save_cursor(c);
    restore_stock_bank(s, c);
    select_without_save(c, slot);
}

static void touch(unsigned slot, uint32_t c)
{
    camera_state *s = state();
    if (!s || !native_adj(c) || s->controller != c || s->closing ||
        s->suspended || !assignment(s, c, slot)) return;
    focus_extra(s, c, slot);
}

static void stock_touch(uint32_t c, unsigned slot)
{
    camera_state *s = state();
    if (s && ((s->controller == c && (s->suspended || s->closing)) ||
        (s->retired_controller == c && s->session.owner == c))) return;
    if (focused(s, c)) {
        if (!s->closing && stock_available(c,
            m10v_adj_extra_camera_stock_slot_type(c, slot)))
            focus_stock(s, c, slot);
    } else if (byte(c, ADJ_SLOT) != slot) {
        ((fn2)0x531a4864u)(c, slot);
    }
}

void m10v_adj_extra_camera_touch0(uint32_t c) { stock_touch(c, 0); }
void m10v_adj_extra_camera_touch1(uint32_t c) { stock_touch(c, 1); }
void m10v_adj_extra_camera_touch2(uint32_t c) { stock_touch(c, 2); }
void m10v_adj_extra_camera_touch3(uint32_t c) { stock_touch(c, 3); }
void m10v_adj_extra_camera_touch4(uint32_t c) { stock_touch(c, 4); }

static void restore_geometry(uint32_t c)
{
    label_bounds(c, 400);
    for (unsigned i = 0; i < 5; ++i) {
        uint32_t x = 425u + 60u * i;
        ((fn2)0x533ac568u)(word(c, ADJ_CELLS + 4 * i), x);
        ((fn2)0x533ac568u)(word(c, ADJ_ICONS + 4 * i), x + 5);
    }
    uint32_t slot = byte(c, ADJ_SLOT);
    if (slot < 5u)
        ((fn2)0x533ac568u)(word(c, ADJ_FRAME), 425u + 60u * slot);
}

void m10v_adj_extra_camera_after_route_leave(uint32_t c)
{
    camera_state *s = state();
    if (!s || s->retired_controller != c || !s->session.owner ||
        !ram(c, 0x274) || word(c, 0) != ADJ_VTABLE || word(c, 4)) return;
    (void)m10v_adj_extra_close(&s->session, c, s->generation);
    /* Keep the retired guard until a new native Enter. The outgoing
     * controller must ignore pending refresh and touch notifications. */
}

static unsigned finish_retired(camera_state *s, uint32_t c)
{
    if (!s || s->retired_controller != c) return 0;
    (void)m10v_adj_extra_close(&s->session, c, s->generation);
    unsigned restore = s->geometry_pending;
    s->retired_controller = 0;
    s->geometry_pending = 0;
    return restore;
}

static void refresh_entered(uint32_t c, unsigned restore)
{
    m10v_adj_extra_camera_refresh(c);
    camera_state *s = state();
    if (restore && s && !s->extra_count && ram(c, 0x274) && word(c, 0) == ADJ_VTABLE)
        restore_geometry(c);
}

void m10v_adj_extra_camera_initial_render(uint32_t c)
{
    camera_state *s = state();
    unsigned restore = s && s->entering != c ? finish_retired(s, c) : 0;
    ((fn1)0x531a4168u)(c);
    M10V_EXIT_LOG(285, c, 0, 0, 0);
    refresh_entered(c, restore);
}

#if M10V_DEBUG_MODE && M10V_ADJ_EXIT_TRACE
/* These call sites belong only to the original ADJ Enter callback. Keep
 * the native calls and arguments, and record their individual boundaries. */
#define TRACE_ENTER_STEP(name, address, stage) \
uint32_t m10v_adj_extra_camera_trace_##name(uint32_t c) \
{ \
    M10V_EXIT_LOG(stage, c, word(c, 4), word(c, 0x274), 0); \
    uint32_t result = ((fn1)address)(c); \
    M10V_EXIT_LOG(stage + 1, c, word(c, 4), word(c, 0x274), result); \
    return result; \
}

TRACE_ENTER_STEP(keys, 0x531a18dcu, 286)
TRACE_ENTER_STEP(aux_key, 0x531a1970u, 288)
TRACE_ENTER_STEP(touch, 0x531a2934u, 290)
TRACE_ENTER_STEP(timer, 0x531a1898u, 294)
#undef TRACE_ENTER_STEP

/* The latest crash window stops inside the original list refresh, before
 * canvas publication. Keep these checkpoints on that refresh call site. */
static void trace_refresh_step(uint32_t stage, uint32_t c)
{
    camera_state *s = state();
    if (s && s->entering == c)
        M10V_EXIT_LOG(stage, c, byte(c, ADJ_SLOT), word(c, ADJ_LIST), word(c, ADJ_FRAME));
}

#define TRACE_REFRESH_STEP(name, address, stage) \
uint32_t m10v_adj_extra_camera_trace_##name(uint32_t c) \
{ \
    trace_refresh_step(stage, c); \
    return ((fn1)address)(c); \
}

TRACE_REFRESH_STEP(list, 0x531a405cu, 306)
TRACE_REFRESH_STEP(selection, 0x531a2fa8u, 308)
TRACE_REFRESH_STEP(title, 0x531a2be4u, 309)
TRACE_REFRESH_STEP(detail, 0x531a2c28u, 310)
TRACE_REFRESH_STEP(footer, 0x531a2cf0u, 311)
#undef TRACE_REFRESH_STEP

uint32_t m10v_adj_extra_camera_trace_frame(uint32_t frame, uint32_t x)
{
    camera_state *s = state();
    if (s && s->entering)
        M10V_EXIT_LOG(307, s->entering, frame, x, 0);
    return ((fn2)0x533ac568u)(frame,x);
}

/* The stock canvas binder is shared. Only record its steps while the
 * matching ADJ controller enters and publishes its primary canvas. */
static void trace_canvas_step(uint32_t stage, uint32_t canvas, uint32_t arg, uint32_t detail)
{
    camera_state *s = state();
    if (s && s->entering && word(s->entering, 0x15c) == canvas)
        M10V_EXIT_LOG(stage, s->entering, canvas, arg, detail);
}

uint32_t m10v_adj_extra_camera_trace_primary(uint32_t display, uint32_t index)
{
    camera_state *s = state();
    if (s && s->entering)
        M10V_EXIT_LOG(304, s->entering, display, index, 0);
    return ((fn2)0x53233874u)(display, index);
}

uint32_t m10v_adj_extra_camera_trace_fallback(uint32_t display, uint32_t index)
{
    camera_state *s = state();
    if (s && s->entering)
        M10V_EXIT_LOG(305, s->entering, display, index, 0);
    return ((fn2)0x532338bcu)(display, index);
}

uint32_t m10v_adj_extra_camera_trace_area(uint32_t out, uint32_t display,
    uint32_t plane, uint32_t index)
{
    camera_state *s = state();
    if (s && s->entering)
        M10V_EXIT_LOG(298, s->entering, display, plane, index);
    return ((fn4)0x532336c4u)(out, display, plane, index);
}

uint32_t m10v_adj_extra_camera_trace_rect(uint32_t canvas, uint32_t rect,
    uint32_t unused, uint32_t target)
{
    (void)unused;
    trace_canvas_step(299, canvas, target, rect);
    return ((fn2)(uintptr_t)target)(canvas, rect);
}

uint32_t m10v_adj_extra_camera_trace_layout(uint32_t canvas, uint32_t a,
    uint32_t b, uint32_t target)
{
    trace_canvas_step(300, canvas, target, word(canvas, 0x10));
    return ((fn3)(uintptr_t)target)(canvas, a, b);
}

uint32_t m10v_adj_extra_camera_trace_children(uint32_t canvas, uint32_t a,
    uint32_t b, uint32_t target)
{
    trace_canvas_step(301, canvas, target, word(canvas, 0xc));
    return ((fn3)(uintptr_t)target)(canvas, a, b);
}

uint32_t m10v_adj_extra_camera_trace_invalidate(uint32_t canvas)
{
    trace_canvas_step(302, canvas, word(canvas, 0x88), word(canvas, 0x8c));
    return ((fn1)0x533ad308u)(canvas);
}

uint32_t m10v_adj_extra_camera_trace_finish(uint32_t rect)
{
    camera_state *s = state();
    if (s && s->entering)
        M10V_EXIT_LOG(303, s->entering, word(s->entering, 4), rect, 0);
    return ((fn1)0x536b5604u)(rect);
}

uint32_t m10v_adj_extra_camera_trace_canvas(uint32_t c, uint32_t slot, uint32_t canvas)
{
    M10V_EXIT_LOG(292, c, slot, canvas, word(c, 4));
    uint32_t result = ((fn3)0x5316d354u)(c, slot, canvas);
    M10V_EXIT_LOG(293, c, slot, canvas, word(c, 4));
    return result;
}
#endif

uint32_t m10v_adj_extra_camera_enter(uint32_t c, uint32_t route,
    uint32_t parent, uint32_t returning)
{
    camera_state *s = state();
    fn4 stock = (fn4)0x5316dfa8u;
    if (!s || s->entering || route != ADJ_ROUTE ||
        !ram(c, 0x274) || word(c, 0) != ADJ_VTABLE)
        return stock(c, route, parent, returning);

    /* The child has exited, and the old ADJ canvas is detached. Reclaim
     * the previous strip now; don't let either stock refresh site attach
     * it while the native Enter call is still publishing the canvas. */
    s->entering = c;
    M10V_EXIT_LOG(282, c, parent, returning, s->session.owner);
    unsigned restore = finish_retired(s, c);
    uint32_t result = stock(c, route, parent, returning);
    M10V_EXIT_LOG(283, c, result, word(c, 4), word(c, 0x15c));
    if (state() == s && s->entering == c) {
        s->entering = 0;
        if (word(c, 0x124) == route && word(c, 4) &&
            word(c, 4) == word(c, 0x15c))
            refresh_entered(c, restore);
    }
    M10V_EXIT_LOG(284, c, result, 0, 0);
    return result;
}

static int find_stock(uint32_t c, int begin, int end, int step)
{
    for (int i = begin; i != end; i += step)
        if (stock_available(c, m10v_adj_extra_camera_stock_slot_type(c, (unsigned)i)))
            return i;
    return -1;
}

static unsigned find_extra(const camera_state *s, uint32_t c, int begin, int end, int step)
{
    for (int i = begin; i != end; i += step)
        if (assignment(s, c, (unsigned)i)) return (unsigned)i;
    return 0;
}

static uint32_t navigate(camera_state *s, uint32_t c, unsigned forward)
{
    unsigned slot = byte(c, ADJ_SLOT);
    if (slot > 4u) return 0;
    int step = forward ? 1 : -1;
    int end = forward ? 5 : -1;
    unsigned extra;
    if (!s->focus) {
        if (find_stock(c, (int)slot + step, end, step) >= 0) return 0;
        extra = find_extra(s, c, forward ? 6 : 9, forward ? 10 : 5, step);
    } else {
        extra = find_extra(s, c, (int)s->focus + step, forward ? 10 : 5, step);
        if (!extra) {
            int next = find_stock(c, forward ? 0 : 4, end, step);
            if (next >= 0) {
                focus_stock(s, c, (unsigned)next);
                return 1;
            }
            extra = find_extra(s, c, forward ? 6 : 9, forward ? 10 : 5, step);
        }
    }
    if (!extra) return 0;
    focus_extra(s, c, extra);
    return 1;
}

uint32_t m10v_adj_extra_camera_lever_pending(uint32_t c)
{
    camera_state *s = state();
    return s && s->controller == c && s->lever_pressed;
}

uint32_t m10v_adj_extra_camera_event(uint32_t c, uint32_t event)
{
    camera_state *s = state();
    if (!s || !native_adj(c) || s->controller != c || !s->extra_count) return 0;
    uint32_t key = *(const uint16_t *)(uintptr_t)event;
    /* The stock keyboard queues 0xd8 for the physical lever's 0x1e release.
     * Other notifications may already be in the queue. Keep the release
     * pending until confirm or close, so the lever reaches stock's 0x86
     * LiveView exit and OK alone opens a shortcut child. */
    uint32_t lever_confirm = key == 0xd8 && s->lever_pressed;
    if (key == 0x1e) s->lever_pressed = 1;
    if (key == 0xd8) s->lever_pressed = 0;
    if (lever_confirm || key == 1 || key == 0x35 || key == 0x89 || key == 0xaa) {
        s->lever_pressed = 0;
        s->closing = lever_confirm || key == 1 || key == 0x35 ? 2u : 1u;
        return 0;
    }
    if (s->closing || s->suspended) return 0;
    if (key == 0xce || key == 0xcf) return navigate(s, c, key == 0xcf);
    uint32_t id = assignment(s, c, s->focus);
    if (key != 0xd8 || id <= EXTRA_STOCK_ID) return 0;
    if (id == M10V_ADJ_EXTRA_EFFECTS) {
        if (has_film()) {
            s->effects_action = 1;
            ((fn2)0x531a4a80u)(c, 2);
            if (state() == s && s->controller == c) s->effects_action = 0;
        }
        return 1;
    }
    uint32_t route = id == M10V_ADJ_EXTRA_GUIDES ? 0x020000a0u :
        id == M10V_ADJ_EXTRA_FILM ? 0x0200f100u :
        id == M10V_ADJ_EXTRA_BORDER ? M10V_ADJ_EXTRA_BORDER_ROUTE : 0x02000073u;
    /* These shortcuts open full controllers. Both confirmation and cancel
     * use the native parent route, so close to shooting LiveView. Re-enter
     * ADJ on the next lever press through its normal entry from LiveView. */
    ((fn3)0x5316c9d8u)(c, route, LIVE_ROUTE);
    return 1;
}

static void retire(camera_state *s, uint32_t c, unsigned mode)
{
    if (!s || !c) return;
    if (s->controller == c) {
        unsigned defer_geometry = mode != M10V_ADJ_RETIRE_RESTORE || s->closing == 2u;
        s->closing = 1;
        restore_stock_bank(s, c);
        s->retired_controller = c;
        s->geometry_pending = defer_geometry && s->extra_count;
        if (s->extra_count && !defer_geometry) restore_geometry(c);
        clear(s->extra_cursor, sizeof(s->extra_cursor));
        s->extra_count = 0;
        s->controller = 0;
        s->closing = 0;
        s->suspended = 0;
        s->lever_pressed = 0;
    }
    /* Stock owns the visible transition. During its exit callback, neither
     * invalidation nor child-vector mutation is safe. The dormant session
     * has no input owner and is reclaimed before next open or destruction. */
    if (mode != M10V_ADJ_RETIRE_DEFER)
        (void)m10v_adj_extra_close(&s->session, c, s->generation);
    if (mode == M10V_ADJ_RETIRE_DESTROY && s->retired_controller == c)
        s->geometry_pending = 0;
}

void m10v_adj_extra_camera_suspend(uint32_t c, unsigned suspended)
{
    camera_state *s = state();
    if (!s || s->controller != c) return;
    s->suspended = !!suspended;
    if (!suspended && !s->closing && s->extra_count && native_adj(c))
        render(s, c);
}

void m10v_adj_extra_camera_retire(uint32_t c, unsigned mode)
{
    retire(state(), c, mode);
}

void m10v_adj_extra_camera_dispose(uint32_t owner)
{
    camera_state *s = state_at(owner);
    if (!s || s->magic != STATE_MAGIC) return;
    uint32_t c = s->controller ? s->controller : (uint32_t)s->session.owner;
    retire(s, c, M10V_ADJ_RETIRE_DESTROY);
    s->magic = 0;
}
