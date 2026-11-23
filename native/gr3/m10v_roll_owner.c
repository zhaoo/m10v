#include "m10v_roll_owner.h"

static void copy_bytes(void *out, const void *input, uint32_t bytes) {
    for (uint32_t i = 0; i < bytes; i++) {
        ((uint8_t *)out)[i] = ((const uint8_t *)input)[i];
    }
}

void m10v_roll_owner_init(m10v_roll_owner *owner, const m10v_roll_journal *io,
                          const m10v_roll_saved_probe *probe) {
    if (!owner) return;
    owner->journal.context = io ? io->context : 0;
    owner->journal.read = io ? io->read : 0;
    owner->journal.write = io ? io->write : 0;
    owner->probe.context = probe ? probe->context : 0;
    owner->probe.find = probe ? probe->find : 0;
    owner->loaded = -1;
    owner->armed = 0;
    owner->reservation = 0;
}

int m10v_roll_owner_recover(m10v_roll_owner *owner) {
    if (!owner || owner->armed || !owner->journal.write || !owner->probe.find) return -1;
    owner->loaded = m10v_roll_reconcile(&owner->journal, &owner->probe, &owner->current);
    return owner->loaded;
}

int m10v_roll_owner_snapshot(const m10v_roll_owner *owner, m10v_roll_record *out) {
    if (!owner || !out) return -1;
    if (owner->loaded == 1) copy_bytes(out, &owner->current, sizeof(*out));
    return owner->loaded;
}

static int commit(m10v_roll_owner *owner, const m10v_roll_record *next) {
    const m10v_roll_record *prior = owner->loaded == 1 ? &owner->current : 0;
    if (!m10v_roll_store(&owner->journal, prior, next)) {
        owner->loaded = -1;
        return 0;
    }
    copy_bytes(&owner->current, next, sizeof(*next));
    owner->loaded = 1;
    return 1;
}

int m10v_roll_owner_open(m10v_roll_owner *owner, const uint8_t id[16], uint32_t film,
                         uint32_t aspect, uint32_t target) {
    if (!owner || owner->loaded < 0 || owner->armed) return 0;
    const m10v_roll_record *prior = owner->loaded == 1 ? &owner->current : 0;
    m10v_roll_record next;
    return m10v_roll_open(prior, &next, id, film, aspect, target) && commit(owner, &next);
}

int m10v_roll_owner_change(m10v_roll_owner *owner, uint32_t status) {
    if (!owner || owner->loaded != 1 || owner->armed) return 0;
    m10v_roll_record next;
    return m10v_roll_change(&owner->current, &next, status) && commit(owner, &next);
}

uint32_t m10v_roll_owner_arm(m10v_roll_owner *owner, uint8_t marker[M10V_ROLL_MARKER_BYTES]) {
    if (!owner || !marker || owner->loaded != 1 || owner->armed ||
        owner->reservation == UINT32_MAX ||
        !m10v_roll_marker(&owner->current, owner->current.count + 1, owner->marker)) return 0;
    copy_bytes(marker, owner->marker, M10V_ROLL_MARKER_BYTES);
    owner->armed = 1;
    return ++owner->reservation;
}

int m10v_roll_owner_finish(m10v_roll_owner *owner, uint32_t ticket,
                            const uint8_t marker[M10V_ROLL_MARKER_BYTES],
                            int32_t saved_outputs) {
    if (!owner || !marker || owner->loaded != 1 || !owner->armed ||
        ticket != owner->reservation) return 0;
    for (uint32_t i = 0; i < M10V_ROLL_MARKER_BYTES; i++) {
        if (owner->marker[i] != marker[i]) return 0;
    }

    owner->armed = 0;
    if (saved_outputs == 0) return 1;
    const uint32_t formats = M10V_ROLL_SAVED_JPEG | M10V_ROLL_SAVED_DNG;
    m10v_roll_record next;
    if (saved_outputs < 0 || ((uint32_t)saved_outputs & ~formats) ||
        !m10v_roll_complete(&owner->current, &next, owner->current.count + 1) ||
        !commit(owner, &next)) {
        owner->loaded = -1;
        return -1;
    }
    return 1;
}
