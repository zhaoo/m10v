#include <stdint.h>
#include "m10v_isp_recipe_color.h"
#include "m10v_recorded_film.h"

#define RAW_TASK_VTABLE 0x53c5bf08u
#define RAW_MANAGER_GUARD 0x55086f4cu
#define RAW_MANAGER_TASK 0x55086f28u
#define RAW_SI_BYTES 0x74270u
#define RAW_CHOICE_MAGIC 0x4d520000u
#define RAW_LEASE_MAGIC 0x52530000u
#define RAW_PREVIEW 1u
#define RAW_SAVE 2u

typedef struct {
    uint32_t marker;
    uint32_t task;
    uint32_t item;
    uint32_t code;
} m10v_raw_lease;

_Static_assert(sizeof(m10v_raw_lease) == 16, "RAW source allocation tail");

static int raw_ram(uintptr_t address, uint32_t bytes) {
    return !(address & 3u) && address >= 0x55000000u && address <= 0x80000000u - bytes;
}

static uint32_t word(uintptr_t address) {
    return __atomic_load_n((const uint32_t *)address, __ATOMIC_ACQUIRE);
}

static uint32_t byte(uintptr_t address) {
    return *(const volatile uint8_t *)address;
}

static uint32_t active_task(void) {
    if (!(word(RAW_MANAGER_GUARD) & 1u)) return 0;
    uint32_t task = word(RAW_MANAGER_TASK);
    return raw_ram(task, 0x60) && word(task) == RAW_TASK_VTABLE && byte(task + 0x21) == 1 ? task : 0;
}

static m10v_raw_lease *lease(uint32_t task, uint32_t source) {
    if (!task || task != active_task() || source != word(task + 0x28) ||
        !raw_ram(source, RAW_SI_BYTES + sizeof(m10v_raw_lease))) return 0;
    return (m10v_raw_lease *)(uintptr_t)(source + RAW_SI_BYTES);
}

static int file_loaded(uint32_t item) {
    return raw_ram(item, 0x5d4) && byte(item + 0x12) - 1u <= 3u &&
        byte(item + 0x25) == 1 && byte(item + 0x26) == 1 &&
        raw_ram(word(item + 0x5d0), RAW_SI_BYTES);
}

static uint32_t recorded_choice(uint32_t choice, uint32_t tag) {
    if ((choice & 0xffff0000u) != RAW_CHOICE_MAGIC) return 0;
    uint32_t film = choice & 0xffffu;
    if (film) return M10V_BUILTIN(film) ? m10v_recorded_film_code(film, 0) : 0;
    if ((tag >> 16) != 2) return 0;
    uint32_t code = (tag & 0xffffu) + 0x100u;
    m10v_recorded_film recorded;
    return m10v_recorded_film_read(code, &recorded) ? code : 0;
}

void m10v_raw_ingress_stage(uint32_t task, uint32_t request, uint32_t source, uint32_t operation) {
    if (!task || task != active_task()) return;
    uint32_t si = word(task + 0x28);
    m10v_raw_lease *record = lease(task, si);
    if (!record) return;
    __atomic_store_n(&record->marker, 0, __ATOMIC_RELEASE);

    uint32_t offset = operation == RAW_PREVIEW ? 0x83cu : 0x82cu;
    uint32_t item = word(task + 0x24);
    if ((operation != RAW_PREVIEW && (operation != RAW_SAVE || source != si)) ||
        !raw_ram(request, offset + 4u) || !file_loaded(item)) return;

    uint32_t code = recorded_choice(word(request + offset), word(item + 0x220));
    if (!code) return;
    __atomic_store_n(&record->task, task, __ATOMIC_RELAXED);
    __atomic_store_n(&record->item, item, __ATOMIC_RELAXED);
    __atomic_store_n(&record->code, code, __ATOMIC_RELAXED);
    __atomic_store_n(&record->marker, RAW_LEASE_MAGIC | operation, __ATOMIC_RELEASE);
}

void m10v_raw_ingress_unstage(uint32_t task) {
    if (!task || task != active_task()) return;
    m10v_raw_lease *record = lease(task, word(task + 0x28));
    if (record) __atomic_store_n(&record->marker, 0, __ATOMIC_RELEASE);
}

void m10v_raw_ingress_after_copy(void *recipe, uint32_t kind, uint32_t source) {
    if (kind - 9u > 3u) return;
    uint32_t task = active_task();
    m10v_raw_lease *record = lease(task, source);
    uint32_t code = 0;
    uint32_t expected = RAW_LEASE_MAGIC | (kind == 12u ? RAW_SAVE : RAW_PREVIEW);
    if (record && word((uintptr_t)&record->marker) == expected &&
        word((uintptr_t)&record->task) == task) {
        uint32_t item = word((uintptr_t)&record->item);
        uint32_t value = word((uintptr_t)&record->code);
        m10v_recorded_film recorded;
        if (item == word(task + 0x24) && file_loaded(item) &&
            word((uintptr_t)&record->marker) == expected &&
            m10v_recorded_film_read(value, &recorded)) code = value;
    }
    m10v_isp_frame_raw_snapshot(recipe, kind, code);
}
