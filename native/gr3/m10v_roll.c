#include "m10v_roll.h"
#include <stddef.h>

#define JOURNAL_MAGIC 0x314c4f52u
_Static_assert(sizeof(m10v_roll_record) == 48, "roll journal ABI");

static uint32_t crc32(const uint8_t *data, uint32_t bytes) {
    uint32_t crc = UINT32_MAX;
    for (uint32_t i = 0; i < bytes; i++) {
        crc ^= data[i];
        for (uint32_t bit = 0; bit < 8; bit++) {
            crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
        }
    }
    return ~crc;
}

static uint32_t checksum(const m10v_roll_record *roll) {
    return crc32((const uint8_t *)roll, offsetof(m10v_roll_record, crc));
}

static int identity_nonzero(const uint8_t id[16]) {
    uint8_t combined = 0;
    for (uint32_t i = 0; i < 16; i++) combined |= id[i];
    return combined != 0;
}

static int same_identity(const uint8_t a[16], const uint8_t b[16]) {
    for (uint32_t i = 0; i < 16; i++) {
        if (a[i] != b[i]) return 0;
    }
    return 1;
}

static int target_valid(uint32_t target) {
    return target == 24 || target == 36;
}

int m10v_roll_valid(const m10v_roll_record *roll) {
    return roll && roll->magic == JOURNAL_MAGIC && roll->sequence &&
        identity_nonzero(roll->id) && roll->film &&
        target_valid(roll->target) && roll->count <= roll->target &&
        roll->status >= M10V_ROLL_ACTIVE && roll->status <= M10V_ROLL_CLOSED &&
        (roll->count < roll->target || roll->status == M10V_ROLL_CLOSED) &&
        roll->crc == checksum(roll);
}

int m10v_roll_latest(const m10v_roll_record *a, const m10v_roll_record *b) {
    int valid_a = m10v_roll_valid(a), valid_b = m10v_roll_valid(b);
    if (!valid_a && !valid_b) return -1;
    if (!valid_a) return 1;
    return valid_b && b->sequence > a->sequence;
}

static void copy_record(m10v_roll_record *out, const m10v_roll_record *current) {
    for (uint32_t i = 0; i < sizeof(*out); i++) {
        ((uint8_t *)out)[i] = ((const uint8_t *)current)[i];
    }
}

int m10v_roll_open(const m10v_roll_record *previous, m10v_roll_record *out,
                   const uint8_t id[16], uint32_t film, uint32_t aspect,
                   uint32_t target) {
    if (!out || !id || !identity_nonzero(id) || !film || !target_valid(target)) return 0;
    uint32_t sequence = 1;
    if (previous) {
        if (!m10v_roll_valid(previous) || previous->status != M10V_ROLL_CLOSED ||
            previous->sequence == UINT32_MAX || same_identity(previous->id, id)) return 0;
        sequence = previous->sequence + 1;
    }
    out->magic = JOURNAL_MAGIC;
    out->sequence = sequence;
    for (uint32_t i = 0; i < 16; i++) out->id[i] = id[i];
    out->film = film;
    out->aspect = aspect;
    out->target = target;
    out->count = 0;
    out->status = M10V_ROLL_ACTIVE;
    out->crc = checksum(out);
    return 1;
}

int m10v_roll_change(const m10v_roll_record *current, m10v_roll_record *out,
                     uint32_t status) {
    if (!out || !m10v_roll_valid(current) || current->sequence == UINT32_MAX ||
        current->status == M10V_ROLL_CLOSED || status == current->status ||
        status < M10V_ROLL_ACTIVE || status > M10V_ROLL_CLOSED) return 0;
    copy_record(out, current);
    out->status = status;
    out->sequence++;
    out->crc = checksum(out);
    return 1;
}

int m10v_roll_complete(const m10v_roll_record *current, m10v_roll_record *out,
                       uint32_t saved_frame) {
    if (!out || !m10v_roll_valid(current) || current->sequence == UINT32_MAX ||
        current->status != M10V_ROLL_ACTIVE || saved_frame != current->count + 1) return 0;
    copy_record(out, current);
    out->count = saved_frame;
    if (saved_frame == out->target) out->status = M10V_ROLL_CLOSED;
    out->sequence++;
    out->crc = checksum(out);
    return 1;
}

static void put32(uint8_t *out, uint32_t value) {
    for (uint32_t i = 0; i < 4; i++) out[i] = (uint8_t)(value >> (i * 8));
}

static uint32_t little32(const uint8_t *in) {
    return (uint32_t)in[0] | (uint32_t)in[1] << 8 |
        (uint32_t)in[2] << 16 | (uint32_t)in[3] << 24;
}

int m10v_roll_marker(const m10v_roll_record *roll, uint32_t frame,
                     uint8_t out[M10V_ROLL_MARKER_BYTES]) {
    if (!out || !m10v_roll_valid(roll) || roll->status != M10V_ROLL_ACTIVE ||
        frame != roll->count + 1) return 0;
    put32(out, 0x5230314du);
    for (uint32_t i = 0; i < 16; i++) out[4 + i] = roll->id[i];
    put32(out + 20, frame);
    put32(out + 24, roll->target);
    put32(out + 28, crc32(out, 28));
    return 1;
}

static int same_record(const m10v_roll_record *a, const m10v_roll_record *b) {
    const uint8_t *left = (const uint8_t *)a, *right = (const uint8_t *)b;
    for (uint32_t i = 0; i < sizeof(*a); i++) {
        if (left[i] != right[i]) return 0;
    }
    return 1;
}

int m10v_roll_load(const m10v_roll_journal *io, m10v_roll_record *out) {
    if (!io || !io->read || !out) return -1;
    m10v_roll_record pages[2];
    int a = io->read(io->context, 0, &pages[0]);
    int b = io->read(io->context, 1, &pages[1]);
    if (a < 0 || b < 0) return -1;
    const m10v_roll_record *even =
        a && !(pages[0].sequence & 1u) ? &pages[0] : NULL;
    const m10v_roll_record *odd =
        b && (pages[1].sequence & 1u) ? &pages[1] : NULL;
    int newest = m10v_roll_latest(even, odd);
    if (newest < 0) return a || b ? -1 : 0;
    copy_record(out, &pages[newest]);
    return 1;
}

int m10v_roll_store(const m10v_roll_journal *io, const m10v_roll_record *expected,
                    const m10v_roll_record *next) {
    if (!io || !io->write || !m10v_roll_valid(next)) return 0;
    m10v_roll_record actual;
    int found = m10v_roll_load(io, &actual);
    if (expected) {
        if (found != 1 || !same_record(expected, &actual) ||
            actual.sequence == UINT32_MAX || next->sequence != actual.sequence + 1) return 0;
    } else if (found != 0 || next->sequence != 1) {
        return 0;
    }
    uint32_t page = next->sequence & 1u;
    return io->write(io->context, page, next) == 1 &&
        io->read(io->context, page, &actual) == 1 && same_record(&actual, next);
}

int m10v_roll_apply_saved(const m10v_roll_journal *io,
                          const uint8_t marker[M10V_ROLL_MARKER_BYTES],
                          uint32_t saved_outputs) {
    const uint32_t formats = M10V_ROLL_SAVED_JPEG | M10V_ROLL_SAVED_DNG;
    if (!marker || !saved_outputs || (saved_outputs & ~formats) ||
        little32(marker) != 0x5230314du ||
        little32(marker + 28) != crc32(marker, 28)) return 0;

    m10v_roll_record current, next;
    int loaded = m10v_roll_load(io, &current);
    if (loaded <= 0) return loaded;
    uint32_t frame = little32(marker + 20);
    if (!frame || frame > current.target || little32(marker + 24) != current.target ||
        !same_identity(current.id, marker + 4)) return 0;
    if (frame <= current.count) return 1;
    if (!m10v_roll_complete(&current, &next, frame)) return -1;
    return m10v_roll_store(io, &current, &next) ? 1 : -1;
}

int m10v_roll_reconcile(const m10v_roll_journal *io, const m10v_roll_saved_probe *probe,
                        m10v_roll_record *out) {
    if (!out) return -1;
    m10v_roll_record current;
    int loaded = m10v_roll_load(io, &current);
    if (loaded <= 0) return loaded;

    while (current.status == M10V_ROLL_ACTIVE) {
        uint8_t marker[M10V_ROLL_MARKER_BYTES];
        const uint32_t frame = current.count + 1;
        if (!probe || !probe->find || !m10v_roll_marker(&current, frame, marker)) return -1;
        int saved = probe->find(probe->context, marker);
        if (saved == 0) break;

        m10v_roll_record next;
        if (saved != 1 || !m10v_roll_complete(&current, &next, frame) ||
            !m10v_roll_store(io, &current, &next)) return -1;
        copy_record(&current, &next);
    }
    copy_record(out, &current);
    return 1;
}
