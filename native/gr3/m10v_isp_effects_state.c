/* Pure metadata codec and per-capture settings resolution. No filesystem,
 * firmware addresses, allocation, hardware submission or image access. */
#include "m10v_isp_effects_state.h"

/* Volatile metadata bytes prevent size-oriented freestanding builds from
 * lowering these bounded copies/clears to unavailable ARM libc helpers. */
static void copy_metadata(void *destination,const void *source,size_t bytes)
{
    volatile uint8_t *out=destination;
    const volatile uint8_t *in=source;
    for(size_t i=0;i<bytes;i++)out[i]=in[i];
}

static uint32_t read_le32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
        ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static void write_le32(uint8_t *p, uint32_t value)
{
    for (uint32_t i = 0; i < 4; ++i) p[i] = (uint8_t)(value >> (i * 8));
}

static uint32_t record_crc(const uint8_t *record)
{
    uint32_t crc = 0xffffffffu;
    for (uint32_t i = 0; i < M10V_ISP_EFFECTS_RECORD_SIZE - 4u; ++i) {
        crc ^= record[i];
        for (uint32_t bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}

void m10v_isp_effects_defaults(m10v_isp_effects_settings *out)
{
    if (out) {
        for(size_t i=0;i<sizeof(*out);i++)((volatile uint8_t*)out)[i]=0;
    }
}

int m10v_isp_effects_validate(const m10v_isp_effects_settings *s)
{
    return s && s->leak_gain <= 3 && s->leak_position <= 2 &&
        s->leak_spread <= 2 && s->grain_mode <= M10V_ISP_GRAIN_STRONG &&
        s->grain_size <= 2 && s->blur_gain <= 3 && s->blur_range <= 2 &&
        s->reserved == 0;
}

int m10v_isp_effects_encode(const m10v_isp_effects_settings *s,
    uint32_t sequence, void *record, size_t record_size)
{
    if (!record || record_size != M10V_ISP_EFFECTS_RECORD_SIZE ||
        !m10v_isp_effects_validate(s)) return 0;
    const uint32_t words[] = {
        M10V_ISP_EFFECTS_RECORD_MAGIC, M10V_ISP_EFFECTS_RECORD_VERSION,
        sequence, s->leak_gain, s->leak_position, s->leak_spread,
        s->grain_mode, s->grain_size, s->blur_gain, s->blur_range, s->reserved
    };
    uint8_t *bytes = record;
    for (uint32_t i = 0; i < 11; ++i) write_le32(bytes + 4 * i, words[i]);
    write_le32(bytes + 44, record_crc(bytes));
    return 1;
}

int m10v_isp_effects_decode(const void *record, size_t record_size,
    m10v_isp_effects_settings *settings, uint32_t *sequence)
{
    if (!record || record_size != M10V_ISP_EFFECTS_RECORD_SIZE ||
        !settings || !sequence) return 0;
    const uint8_t *bytes = record;
    if (read_le32(bytes) != M10V_ISP_EFFECTS_RECORD_MAGIC ||
        read_le32(bytes + 4) != M10V_ISP_EFFECTS_RECORD_VERSION ||
        read_le32(bytes + 44) != record_crc(bytes)) return 0;
    const m10v_isp_effects_settings decoded = {
        read_le32(bytes + 12), read_le32(bytes + 16), read_le32(bytes + 20),
        read_le32(bytes + 24), read_le32(bytes + 28), read_le32(bytes + 32),
        read_le32(bytes + 36), read_le32(bytes + 40)
    };
    if (!m10v_isp_effects_validate(&decoded)) return 0;
    const uint32_t decoded_sequence = read_le32(bytes + 8);
    copy_metadata(settings,&decoded,sizeof(decoded));
    *sequence = decoded_sequence;
    return 1;
}

int m10v_isp_effects_select_newest(const void *record_a, size_t size_a,
    const void *record_b, size_t size_b,
    m10v_isp_effects_settings *settings, uint32_t *sequence)
{
    if (!settings || !sequence) return -1;
    m10v_isp_effects_settings candidates[2];
    uint32_t sequences[2];
    int good_a = m10v_isp_effects_decode(record_a, size_a, &candidates[0], &sequences[0]);
    int good_b = m10v_isp_effects_decode(record_b, size_b, &candidates[1], &sequences[1]);
    if (!good_a && !good_b) return -1;
    int chosen = good_a ? 0 : 1;
    if (good_a && good_b) {
        uint32_t delta = sequences[1] - sequences[0];
        if (delta == 0x80000000u) return -1;
        if (delta == 0) {
            const uint8_t *a = record_a, *b = record_b;
            for (uint32_t i = 0; i < M10V_ISP_EFFECTS_RECORD_SIZE; ++i)
                if (a[i] != b[i]) return -1;
        } else if (delta < 0x80000000u) chosen = 1;
    }
    copy_metadata(settings,&candidates[chosen],sizeof(*settings));
    *sequence = sequences[chosen];
    return chosen;
}

int m10v_isp_effects_resolve_snapshot(const m10v_isp_effects_settings *settings,
    uint32_t slot_grain_strength, m10v_isp_effects_snapshot *snapshot)
{
    if (!snapshot || slot_grain_strength > 3 ||
        !m10v_isp_effects_validate(settings)) return 0;
    m10v_isp_effects_snapshot resolved;
    copy_metadata(&resolved.settings,settings,sizeof(*settings));
    resolved.effective_grain_strength = settings->grain_mode == M10V_ISP_GRAIN_INHERIT
        ? slot_grain_strength : settings->grain_mode - 1;
    copy_metadata(snapshot,&resolved,sizeof(resolved));
    return 1;
}
