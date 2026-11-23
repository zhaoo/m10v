#include "m10v_roll_save.h"

enum {
    STORE_JPEG_DESCRIPTOR = 0x14,
    STORE_DNG_DESCRIPTOR = 0x1178,
    STORE_DESCRIPTOR_STRIDE = 0x5cc,
    STORE_GROUP_BYTES = 0x365c,
    STORE_STREAM_COUNT = 3
};

static int ram_address(uint32_t address, uint32_t bytes)
{
    return !(address & 3u) && address >= 0x55000000u && address <= 0x80000000u - bytes;
}

static int matches(const m10v_roll_save *save, uint32_t ticket, uint32_t group)
{
    return save && ticket && save->ticket == ticket && save->group == group;
}

int m10v_roll_save_begin(m10v_roll_save *save, uint32_t ticket, uint32_t group,
                         uint32_t si, uint32_t stream, uint32_t expected)
{
    const uint32_t outputs = M10V_ROLL_SAVE_JPEG | M10V_ROLL_SAVE_DNG;
    if (!save || save->ticket || !ticket || !ram_address(group, STORE_GROUP_BYTES) ||
        !ram_address(si, sizeof(uint32_t)) || stream >= STORE_STREAM_COUNT ||
        !expected || (expected & ~outputs))
        return 0;

    save->ticket = ticket;
    save->group = group;
    save->si = si;
    save->stream = stream;
    save->expected = expected;
    save->seen = 0;
    save->succeeded = 0;
    save->conflicts = 0;
    return 1;
}

int m10v_roll_save_output(m10v_roll_save *save, uint32_t ticket, uint32_t group,
                          uint32_t descriptor, uint32_t si,
                          uint32_t reached_data_close, uint32_t status_ok)
{
    if (!matches(save, ticket, group) || save->si != si || reached_data_close > 1 || status_ok > 1)
        return 0;

    const uint32_t base = group + STORE_DESCRIPTOR_STRIDE * save->stream;
    uint32_t output;
    if (descriptor == base + STORE_JPEG_DESCRIPTOR)
        output = M10V_ROLL_SAVE_JPEG;
    else if (descriptor == base + STORE_DNG_DESCRIPTOR)
        output = M10V_ROLL_SAVE_DNG;
    else
        return 0;

    if (!(save->expected & output))
        return 0;

    const int ok = reached_data_close && status_ok;
    if (save->seen & output) {
        if (ok != ((save->succeeded & output) != 0)) save->conflicts |= output;
    } else if (ok) {
        save->succeeded |= output;
    }
    save->seen |= output;
    return 1;
}

int32_t m10v_roll_save_end(m10v_roll_save *save, uint32_t ticket,
                                        uint32_t group, uint32_t stock_event)
{
    if (!matches(save, ticket, group) || stock_event != M10V_ROLL_SAVE_GROUP_DONE)
        return M10V_ROLL_SAVE_IGNORED;

    const uint32_t verified = save->succeeded & ~save->conflicts;
    const int32_t result = verified ? (int32_t)verified :
        (save->seen != save->expected || save->conflicts ? M10V_ROLL_SAVE_UNKNOWN : 0);
    save->ticket = 0;
    return result;
}
