#include "m10v_adj_extra.h"

#define RECORD_MAGIC 0x4a30314du
#define RECORD_VERSION_AND_SIZE (1u | (M10V_ADJ_EXTRA_RECORD_SIZE << 16))

enum { SESSION_IDLE, SESSION_CHANGING, SESSION_OPEN };

static int function_allowed(uint8_t function, uint32_t allowed)
{
    return !function || (function < 32u && (allowed & (1u << function)));
}

static int assignments_valid(const m10v_adj_extra_assignments *assignments,
    uint32_t allowed)
{
    if (!assignments) return 0;
    for (unsigned i = 0; i < M10V_ADJ_EXTRA_SLOT_COUNT; ++i)
        if (!function_allowed(assignments->function[i], allowed)) return 0;
    return 1;
}

static uint32_t read_le32(const uint8_t *bytes)
{
    return (uint32_t)bytes[0] | ((uint32_t)bytes[1] << 8) |
        ((uint32_t)bytes[2] << 16) | ((uint32_t)bytes[3] << 24);
}

static void write_le32(uint8_t *bytes, uint32_t value)
{
    for (unsigned i = 0; i < 4; ++i) bytes[i] = (uint8_t)(value >> (8u * i));
}

static uint32_t record_crc(const uint8_t *bytes)
{
    uint32_t crc = 0xffffffffu;
    for (unsigned i = 0; i < M10V_ADJ_EXTRA_RECORD_SIZE - 4u; ++i) {
        crc ^= bytes[i];
        for (unsigned bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}

int m10v_adj_extra_encode(const m10v_adj_extra_assignments *assignments,
    uint32_t allowed_functions, uint32_t sequence, void *record, size_t size)
{
    if (!record || size != M10V_ADJ_EXTRA_RECORD_SIZE ||
        !assignments_valid(assignments, allowed_functions)) return 0;

    uint8_t *bytes = record;
    m10v_adj_extra_assignments data = *assignments;
    write_le32(bytes, RECORD_MAGIC);
    write_le32(bytes + 4, RECORD_VERSION_AND_SIZE);
    write_le32(bytes + 8, sequence);
    for (unsigned i = 0; i < M10V_ADJ_EXTRA_SLOT_COUNT; ++i)
        bytes[12 + i] = data.function[i];
    write_le32(bytes + 16, record_crc(bytes));
    return 1;
}

int m10v_adj_extra_decode(const void *record, size_t size,
    uint32_t allowed_functions, m10v_adj_extra_assignments *assignments,
    uint32_t *sequence)
{
    if (!record || size != M10V_ADJ_EXTRA_RECORD_SIZE || !assignments ||
        !sequence) return 0;

    const uint8_t *bytes = record;
    if (read_le32(bytes) != RECORD_MAGIC ||
        read_le32(bytes + 4) != RECORD_VERSION_AND_SIZE ||
        read_le32(bytes + 16) != record_crc(bytes)) return 0;

    m10v_adj_extra_assignments decoded;
    for (unsigned i = 0; i < M10V_ADJ_EXTRA_SLOT_COUNT; ++i)
        decoded.function[i] = bytes[12 + i];
    if (!assignments_valid(&decoded, allowed_functions)) return 0;
    uint32_t decoded_sequence = read_le32(bytes + 8);
    *assignments = decoded;
    *sequence = decoded_sequence;
    return 1;
}

int m10v_adj_extra_select_newest(const void *a, size_t size_a,
    const void *b, size_t size_b, uint32_t allowed_functions,
    m10v_adj_extra_assignments *assignments, uint32_t *sequence)
{
    if (!assignments || !sequence) return -1;

    m10v_adj_extra_assignments decoded[2];
    uint32_t sequences[2];
    int valid_a = m10v_adj_extra_decode(a, size_a, allowed_functions,
        &decoded[0], &sequences[0]);
    int valid_b = m10v_adj_extra_decode(b, size_b, allowed_functions,
        &decoded[1], &sequences[1]);
    if (!valid_a && !valid_b) return -1;

    int chosen = valid_a ? 0 : 1;
    if (valid_a && valid_b) {
        uint32_t delta = sequences[1] - sequences[0];
        if (delta == 0x80000000u) return -1;
        if (delta == 0) {
            for (unsigned i = 0; i < M10V_ADJ_EXTRA_SLOT_COUNT; ++i)
                if (decoded[0].function[i] != decoded[1].function[i]) return -1;
        } else if (delta < 0x80000000u) {
            chosen = 1;
        }
    }
    *assignments = decoded[chosen];
    *sequence = sequences[chosen];
    return chosen;
}

static void release_widgets(m10v_adj_extra_session *session)
{
    for (unsigned i = M10V_ADJ_EXTRA_SLOT_COUNT; i-- > 0;) {
        uintptr_t widget = session->widget[i];
        if (widget) {
            session->ops->detach(session->context, session->owner, widget);
            session->ops->destroy(session->context, widget);
            session->widget[i] = 0;
        }
    }
    session->owner = 0;
    session->lifetime = 0;
    session->ops = 0;
    session->context = 0;
    session->phase = SESSION_IDLE;
}

int m10v_adj_extra_open(m10v_adj_extra_session *session,
    uintptr_t owner, uint32_t lifetime,
    const m10v_adj_extra_assignments *assignments, uint32_t allowed_functions,
    const m10v_adj_extra_widget_ops *ops, void *context)
{
    if (!session || session->phase != SESSION_IDLE || !owner || !lifetime ||
        !assignments_valid(assignments, allowed_functions) ||
        !ops || !ops->create || !ops->attach || !ops->detach || !ops->destroy)
        return 0;

    unsigned active = 0;
    for (unsigned i = 0; i < M10V_ADJ_EXTRA_SLOT_COUNT; ++i)
        active |= assignments->function[i];
    if (!active) return 0;

    session->phase = SESSION_CHANGING;
    session->owner = owner;
    session->lifetime = lifetime;
    session->ops = ops;
    session->context = context;
    session->assignments = *assignments;
    for (unsigned i = 0; i < M10V_ADJ_EXTRA_SLOT_COUNT; ++i) {
        uint8_t function = session->assignments.function[i];
        if (!function) continue;
        uintptr_t widget = ops->create(context, owner, M10V_ADJ_EXTRA_FIRST_SLOT + i,
            function);
        if (!widget || !ops->attach(context, owner, widget)) {
            if (widget) ops->destroy(context, widget);
            release_widgets(session);
            return 0;
        }
        session->widget[i] = widget;
    }
    session->phase = SESSION_OPEN;
    return 1;
}

static int owns(const m10v_adj_extra_session *session, uintptr_t owner,
    uint32_t lifetime)
{
    return session && session->phase == SESSION_OPEN &&
        session->owner == owner && session->lifetime == lifetime;
}

int m10v_adj_extra_close(m10v_adj_extra_session *session, uintptr_t owner,
    uint32_t lifetime)
{
    if (!owns(session, owner, lifetime)) return 0;

    session->phase = SESSION_CHANGING;
    release_widgets(session);
    return 1;
}

uint8_t m10v_adj_extra_function(const m10v_adj_extra_session *session,
    uintptr_t owner, uint32_t lifetime, unsigned logical_slot)
{
    unsigned i = logical_slot - M10V_ADJ_EXTRA_FIRST_SLOT;
    return i < M10V_ADJ_EXTRA_SLOT_COUNT && owns(session, owner, lifetime)
        ? session->assignments.function[i] : 0;
}
