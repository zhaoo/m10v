/* RawDevelopmentModel UI adapters for GR III 2.10 and GR IIIx 1.60.
 * Native Image Control always sees an original enum. The selected film is
 * private to the guarded RawDevelopmentModel and travels with each request. */
#include <stdint.h>
#include "m10v_film_directory.h"

#define STOCK_MODEL 0x550666e0u
#define STOCK_MODEL_BYTES 0x3c4u
#define RAW_STOCK 0xffffu
#define RAW_REQUEST_TAG 0x4d520000u
#define RAW_FILM_ENUM 0x10000u
#define RAW_AS_SHOT_ENUM RAW_FILM_ENUM
#define STANDARD_ENUM 1u

typedef struct {
    uint8_t stock[STOCK_MODEL_BYTES];
    uint32_t selected; /* 0 = source, 0xffff = native style, otherwise film ID. */
    uint32_t before_picker;
} raw_menu;
_Static_assert(sizeof(raw_menu) == 0x3ccu, "RawDevelopmentModel extension layout");

typedef uint32_t (*fn1)(uint32_t);
typedef uint32_t (*fn3)(uint32_t, uint32_t, uint32_t);
extern int m10v_isp_frame_raw_supported(uint32_t);
extern uint32_t m10v_menu_film_resource(uint32_t);
extern uint32_t m10v_menu_recorded_icon(uint32_t);

static uint32_t *singleton_slot(void) { return (uint32_t *)(uintptr_t)STOCK_MODEL; }
static const uint8_t *bytes(uint32_t address) { return (const uint8_t *)(uintptr_t)address; }

uint32_t m10v_raw_menu_model(void) {
    uint32_t p = *singleton_slot();
    /* The original constructor stores a ROM vtable here. A successful
     * extended constructor publishes the heap object under the same guard. */
    return p >= 0x55000000u && p <= 0x80000000u - sizeof(raw_menu) &&
           !(p & 3) && p != STOCK_MODEL ? p : STOCK_MODEL;
}
static raw_menu *owner(uint32_t model) {
    return model != STOCK_MODEL && model == m10v_raw_menu_model() ?
        (raw_menu *)(uintptr_t)model : 0;
}
void m10v_raw_menu_init(uint32_t stock) {
    uint32_t allocated = ((fn1)0x536af2a8u)(sizeof(raw_menu));
    if (!allocated) {
        ((fn1)0x5327b940u)(stock);
        return;
    }
    ((fn1)0x5327b940u)(allocated);
    raw_menu *m = (raw_menu *)(uintptr_t)allocated;
    m->selected = 0;
    m->before_picker = 0;
    *singleton_slot() = allocated;
}
void m10v_raw_menu_destroy(void) {
    uint32_t model = m10v_raw_menu_model();
    ((fn1)0x5327edd8u)(model);
    if (model != STOCK_MODEL) {
        *singleton_slot() = 0;
        ((fn1)0x536af2e4u)(model);
    }
}
void m10v_raw_menu_clear(uint32_t model) {
    raw_menu *m = owner(model);
    if (m) {
        m->selected = 0;
        m->before_picker = 0;
    }
    ((fn1)0x5327ed08u)(model);
}

static uint32_t extra_count(uint32_t model) {
    if (!owner(model)) return 0;
    uint32_t count = 0;
    for (uint32_t i = 0; i < M10V_DIRECTORY_COUNT; ++i)
        count += !!m10v_isp_frame_raw_supported(m10v_directory[i].id);
    return count;
}
static uint32_t stock_count(uint32_t model) { return bytes(model)[5] ? 15u : 14u; }
uint32_t m10v_raw_menu_capacity(uint32_t model) { return 15u + extra_count(model); }
uint32_t m10v_raw_menu_count(uint32_t model) {
    return owner(model) ? m10v_raw_menu_capacity(model) : stock_count(model);
}
uint32_t m10v_raw_menu_row(uint32_t model, uint32_t row) {
    if (!owner(model)) return 0;
    if (row == 14 && !bytes(model)[5]) return RAW_AS_SHOT_ENUM;
    uint32_t index = row - 15u;
    if (index >= M10V_DIRECTORY_COUNT) return 0;
    for (uint32_t i = 0; i < M10V_DIRECTORY_COUNT; ++i) {
        uint32_t id = m10v_directory[i].id;
        if (m10v_isp_frame_raw_supported(id)) {
            if (!index) return RAW_FILM_ENUM | id;
            --index;
        }
    }
    return 0;
}

void m10v_raw_menu_choose(uint32_t model, uint32_t base, uint32_t value) {
    raw_menu *m = owner(model);
    uint32_t film = !base && !value && bytes(model)[5] ? 0 : RAW_STOCK;
    if (base > 2) return;
    if (value >= RAW_FILM_ENUM) {
        film = value - RAW_FILM_ENUM;
        if (base || !m) return;
        if (film) {
            if (!m10v_isp_frame_raw_supported(film)) return;
            value = STANDARD_ENUM;
        } else {
            if (m->stock[5] || !*(const uint32_t *)(uintptr_t)(model + 0x24u)) return;
            /* Native enum 0 reads the source SI's tone and parameters. */
            value = 0;
        }
    }
    if (m) m->selected = film;
    ((fn3)0x53289304u)(model, base, value);
}
uint32_t m10v_raw_menu_current(uint32_t model) {
    const raw_menu *m = owner(model);
    uint32_t value = ((fn1)0x53283860u)(model);
    if (!m || m->stock[0x82]) return value;
    if (!m->stock[5] && !m->selected) return RAW_AS_SHOT_ENUM;
    if (value == STANDARD_ENUM && m->selected && m->selected != RAW_STOCK)
        return RAW_FILM_ENUM | m->selected;
    return value;
}
uint32_t m10v_raw_menu_icon(uint32_t model, uint32_t base, uint32_t value) {
    if (value == RAW_AS_SHOT_ENUM) value = 0;
    if (!base && value >= RAW_FILM_ENUM)
        return m10v_menu_recorded_icon(0x20f00u + value - RAW_FILM_ENUM);
    return ((fn3)0x532891a8u)(model, base, value);
}
uint32_t m10v_raw_menu_name(uint32_t model, uint32_t base, uint32_t value) {
    if (value == RAW_AS_SHOT_ENUM) value = 0;
    if (!base && value >= RAW_FILM_ENUM)
        return m10v_menu_film_resource(value - RAW_FILM_ENUM);
    return ((fn3)0x532891f4u)(model, base, value);
}
void m10v_raw_menu_remember(uint32_t model) {
    raw_menu *m = owner(model);
    if (m) m->before_picker = m->selected;
    ((fn1)0x532846c4u)(model);
}
void m10v_raw_menu_restore(uint32_t model) {
    raw_menu *m = owner(model);
    if (m) m->selected = m->before_picker;
    ((fn1)0x53289314u)(model);
}
void m10v_raw_menu_request(uint32_t request, uint32_t save) {
    uint32_t model = m10v_raw_menu_model();
    uint32_t choice = RAW_STOCK;
    const uint8_t *state = bytes(model);
    if (state[4] == 1 && !state[0x82]) {
        const raw_menu *m = owner(model);
        uint32_t value = m10v_raw_menu_current(model);
        /* In mode zero, the native initializer already seeded this enum
         * from the source DNG. An explicit stock selection overrides it. */
        if (state[5] ? !value : m && !m->selected) choice = 0;
        else if (value >= RAW_FILM_ENUM && m10v_isp_frame_raw_supported(value - RAW_FILM_ENUM))
            choice = value - RAW_FILM_ENUM;
    }
    *(uint32_t *)(uintptr_t)(request + (save ? 0x82cu : 0x83cu)) = RAW_REQUEST_TAG | choice;
}
