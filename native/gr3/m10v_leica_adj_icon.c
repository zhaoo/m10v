#include <stdint.h>

uint32_t m10v_leica_adj_icon_decode(uint32_t id, const uint32_t *artwork) {
    if (id < 891u || id > 894u) return 0;
    uint32_t *pixels = ((void *(*)(uint32_t))0x536af2a8u)(6400);
    if (!pixels) return 0;
    const uint32_t *palette = artwork + (id - 891u) * 104u;
    const uint8_t *indices = (const uint8_t *)(palette + 4);
    for (uint32_t i = 0; i < 1600; ++i)
        pixels[i] = palette[(indices[i >> 2] >> ((i & 3u) * 2u)) & 3u];
    return (uint32_t)(uintptr_t)pixels;
}
