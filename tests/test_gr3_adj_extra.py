"""Exercise the freestanding extra-slot core at the camera service boundary."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HARNESS = r"""
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include "m10v_adj_extra.h"

#define IDS ((1u << 12) | (1u << 20) | (1u << 23))
static const m10v_adj_extra_assignments assignments = {{12, 20, 23, 20}};

static void journal(void) {
    static const uint8_t expected[] = {
        0x4d,0x31,0x30,0x4a, 1,0,20,0, 0x78,0x56,0x34,0x12,
        12,20,23,20, 0x05,0x68,0xec,0xd3
    };
    static const uint8_t unsupported[][20] = {
        {0x4d, 0x31, 0x30, 0x4a, 0x02, 0x00, 0x14, 0x00, 0x78, 0x56,
         0x34, 0x12, 0x0c, 0x14, 0x17, 0x14, 0xf5, 0xba, 0x72, 0xa4},
        {0x4d, 0x31, 0x30, 0x4a, 0x01, 0x00, 0x14, 0x00, 0x78, 0x56,
         0x34, 0x12, 0x20, 0x14, 0x17, 0x14, 0x83, 0x78, 0x08, 0x39}
    };
    uint8_t a[20], b[20];
    assert(m10v_adj_extra_encode(&assignments, IDS, 0x12345678u, a, sizeof(a)));
    assert(memcmp(a, expected, sizeof(a)) == 0);

    m10v_adj_extra_assignments out = {{31, 31, 31, 31}};
    uint32_t seq = 999;
    assert(m10v_adj_extra_decode(a, sizeof(a), IDS, &out, &seq));
    assert(seq == 0x12345678u && memcmp(&out, &assignments, sizeof(out)) == 0);

    out.function[0] = 31;
    seq = 999;
    assert(!m10v_adj_extra_decode(a, 19, IDS, &out, &seq));
    assert(!m10v_adj_extra_decode(a, sizeof(a), IDS & ~(1u << 20), &out, &seq));
    for (unsigned index = 0; index < sizeof(a); ++index) {
        a[index] ^= 1;
        assert(!m10v_adj_extra_decode(a, sizeof(a), IDS, &out, &seq));
        a[index] ^= 1;
    }
    for (unsigned i = 0; i < 2; ++i)
        assert(!m10v_adj_extra_decode(unsupported[i], 20, UINT32_MAX, &out, &seq));
    assert(out.function[0] == 31 && seq == 999);
    assert(!m10v_adj_extra_encode(&out, IDS, 0, a, sizeof(a)));
    assert(memcmp(a, expected, sizeof(a)) == 0);

    assert(m10v_adj_extra_encode(&assignments, IDS, UINT32_MAX, a, sizeof(a)));
    assert(m10v_adj_extra_encode(&assignments, IDS, 0, b, sizeof(b)));
    assert(m10v_adj_extra_select_newest(a, 20, b, 20, IDS, &out, &seq) == 1 && seq == 0);
    b[19] ^= 1;
    assert(m10v_adj_extra_select_newest(a, 20, b, 20, IDS, &out, &seq) == 0 && seq == UINT32_MAX);
    assert(m10v_adj_extra_select_newest(0, 0, 0, 0, IDS, &out, &seq) == -1);

    assert(m10v_adj_extra_encode(&assignments, IDS, 0x7fffffffu, b, sizeof(b)));
    assert(m10v_adj_extra_select_newest(a, 20, b, 20, IDS, &out, &seq) == -1);
    assert(seq == UINT32_MAX);
    m10v_adj_extra_assignments different = {{0, 20, 23, 20}};
    assert(m10v_adj_extra_encode(&different, IDS, UINT32_MAX, b, sizeof(b)));
    assert(m10v_adj_extra_select_newest(a, 20, b, 20, IDS, &out, &seq) == -1);
    assert(m10v_adj_extra_select_newest(a, 20, a, 20, IDS, &out, &seq) == 0);
}

typedef struct {
    m10v_adj_extra_session session;
    unsigned failure_create;
    unsigned failure_attach;
    unsigned log[32];
    unsigned length;
    unsigned allocated;
    unsigned attached;
    uint8_t stock[16];
} harness;

static void record(harness *state, unsigned action) {
    assert(state->length < sizeof(state->log)/sizeof(*state->log));
    state->log[state->length++] = action;
}

static uintptr_t create(void *opaque, uintptr_t owner, unsigned slot, uint8_t function) {
    harness *state = opaque;
    assert(owner == (uintptr_t)state->stock && slot >= 6 && slot <= 9);
    assert(function == assignments.function[slot - 6]);
    assert(!m10v_adj_extra_function(&state->session, owner, 1, slot));
    record(state, 10 + slot);
    if (slot == state->failure_create) return 0;
    state->allocated |= 1u << slot;
    return slot;
}

static int attach(void *opaque, uintptr_t owner, uintptr_t widget) {
    harness *state = opaque;
    assert(owner == (uintptr_t)state->stock);
    assert(state->allocated & (1u << widget));
    record(state, 20 + (unsigned)widget);
    if (widget == state->failure_attach) return 0;
    state->attached |= 1u << widget;
    return 1;
}

static void detach(void *opaque, uintptr_t owner, uintptr_t widget) {
    harness *state = opaque;
    assert(owner == (uintptr_t)state->stock);
    assert(!m10v_adj_extra_function(&state->session, owner, 1, (unsigned)widget));
    assert(state->attached & (1u << widget));
    record(state, 30 + (unsigned)widget);
    state->attached &= ~(1u << widget);
}

static void destroy(void *opaque, uintptr_t widget) {
    harness *state = opaque;
    assert(state->allocated & (1u << widget));
    assert(!(state->attached & (1u << widget)));
    record(state, 40 + (unsigned)widget);
    state->allocated &= ~(1u << widget);
}

static const m10v_adj_extra_widget_ops ops = {create, attach, detach, destroy};

static void init(harness *state) {
    memset(state, 0, sizeof(*state));
    memset(state->stock, 0x55, sizeof(state->stock));
}

static void stock_untouched(const harness *state) {
    for (unsigned i = 0; i < sizeof(state->stock); ++i) assert(state->stock[i] == 0x55);
}

static void rollback(void) {
    harness state;
    for (unsigned slot = 6; slot <= 9; ++slot) {
        for (unsigned failure = 0; failure < 2; ++failure) {
            init(&state);
            if (failure) state.failure_attach = slot;
            else state.failure_create = slot;
            uintptr_t owner = (uintptr_t)state.stock;
            assert(!m10v_adj_extra_open(&state.session, owner, 1, &assignments, IDS, &ops, &state));
            assert(!state.allocated && !state.attached);
            assert(!m10v_adj_extra_close(&state.session, owner, 1));
            for (unsigned s = 6; s <= 9; ++s)
                assert(!m10v_adj_extra_function(&state.session, owner, 1, s));

            unsigned i = 0;
            for (unsigned s = 6; s < slot; ++s) {
                assert(state.log[i++] == 10 + s);
                assert(state.log[i++] == 20 + s);
            }
            assert(state.log[i++] == 10 + slot);
            if (failure) {
                assert(state.log[i++] == 20 + slot);
                assert(state.log[i++] == 40 + slot);
            }
            for (unsigned s = slot; s-- > 6;) {
                assert(state.log[i++] == 30 + s);
                assert(state.log[i++] == 40 + s);
            }
            assert(i == state.length);
            stock_untouched(&state);
        }
    }
}

static void ownership(void) {
    harness state;
    init(&state);
    uintptr_t owner = (uintptr_t)state.stock;
    m10v_adj_extra_assignments off = {{0, 0, 0, 0}};
    assert(!m10v_adj_extra_open(&state.session, owner, 1, &off, IDS, &ops, &state));
    assert(state.length == 0);

    m10v_adj_extra_assignments invalid = {{0, 20, 32, 20}};
    assert(!m10v_adj_extra_open(&state.session, owner, 1, &invalid, IDS, &ops, &state));
    assert(state.length == 0);

    m10v_adj_extra_assignments sparse = {{0, 20, 0, 20}};
    assert(!m10v_adj_extra_open(&state.session, owner, 0, &sparse, IDS, &ops, &state));
    assert(m10v_adj_extra_open(&state.session, owner, 1, &sparse, IDS, &ops, &state));
    sparse.function[1] = 0;
    assert(state.attached == ((1u << 7) | (1u << 9)));
    assert(!m10v_adj_extra_open(&state.session, owner + 1, 2, &assignments, IDS, &ops, &state));
    assert(!m10v_adj_extra_function(&state.session, owner, 1, 5));
    assert(!m10v_adj_extra_function(&state.session, owner, 1, 6));
    assert(m10v_adj_extra_function(&state.session, owner, 1, 7) == 20);
    assert(!m10v_adj_extra_function(&state.session, owner, 1, 10));
    assert(!m10v_adj_extra_function(&state.session, owner + 1, 1, 7));
    assert(!m10v_adj_extra_function(&state.session, owner, 2, 7));
    assert(!m10v_adj_extra_close(&state.session, owner, 2));
    assert(m10v_adj_extra_close(&state.session, owner, 1));
    assert(!m10v_adj_extra_close(&state.session, owner, 1));
    assert(!state.allocated && !state.attached);
    assert(state.length == 8);
    assert(state.log[4] == 39 && state.log[5] == 49);
    assert(state.log[6] == 37 && state.log[7] == 47);
    stock_untouched(&state);

    assert(m10v_adj_extra_open(&state.session, owner, 2, &assignments, IDS, &ops, &state));
    assert(!m10v_adj_extra_function(&state.session, owner, 1, 7));
    assert(m10v_adj_extra_function(&state.session, owner, 2, 7) == 20);
    assert(m10v_adj_extra_close(&state.session, owner, 2));
}

int main(int argc, char **argv) {
    assert(argc == 2);
    if (argv[1][0] == 'j') journal();
    else if (argv[1][0] == 'r') rollback();
    else if (argv[1][0] == 'o') ownership();
    else assert(0);
    return 0;
}
"""


class ExtraAdjTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc = shutil.which(os.environ.get("CC", "clang"))
        if cc is None:
            raise unittest.SkipTest("C compiler unavailable")
        temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        harness = directory / "harness.c"
        harness.write_text(HARNESS)
        cls.executable = directory / "extra-adj"
        native = ROOT / "native/gr3"
        subprocess.run([
            cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-ffreestanding",
            "-I", str(native), str(harness), str(native / "m10v_adj_extra.c"),
            "-o", str(cls.executable),
        ], check=True, cwd=directory)

    def test_journal_rejects_bad_records_and_recovers_valid_previous_record(self):
        subprocess.run([self.executable, "journal"], check=True, cwd=self.executable.parent)

    def test_each_widget_failure_unwinds_only_created_widgets_in_reverse(self):
        subprocess.run([self.executable, "rollback"], check=True, cwd=self.executable.parent)

    def test_live_tiles_require_matching_controller_and_lifetime(self):
        subprocess.run([self.executable, "ownership"], check=True, cwd=self.executable.parent)


if __name__ == "__main__":
    unittest.main()
