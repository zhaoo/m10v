#include "m10v_border.h"

static uint32_t even_up(uint32_t value) { return (value + 1u) & ~1u; }
static uint32_t at_least_two(uint32_t value) { return value < 2u ? 2u : value; }

int m10v_border_layout(uint32_t style, uint32_t width, uint32_t height,
                       m10v_border_layout_info *out) {
    if (!out || style > M10V_BORDER_FILM || width < 2u || height < 2u ||
        width > 65534u || height > 65534u || ((width | height) & 1u)) return -1;
    m10v_border_layout_info result = {0};
    result.style = style;
    result.inner.width = result.outer.width = width;
    result.inner.height = result.outer.height = height;
    if (style != M10V_BORDER_OFF) {
        uint32_t short_side = width < height ? width : height;
        uint32_t margin = style == M10V_BORDER_POLAROID ?
            even_up((short_side + 24u) / 25u) :
            even_up((short_side * 3u + 49u) / 50u);
        result.inner.x = result.inner.y = margin;
        result.outer.width = width + margin * 2u;
        result.outer.height = height + margin * (style == M10V_BORDER_POLAROID ? 4u : 2u);
        if (style == M10V_BORDER_FILM) {
            uint32_t hole_width = at_least_two((margin / 2u) & ~1u);
            uint32_t hole_height = at_least_two((margin * 3u / 4u) & ~1u);
            uint32_t gap = at_least_two((margin / 2u) & ~1u);
            uint32_t pitch = hole_height + gap;
            uint32_t usable = result.outer.height - margin;
            /* At most 63 bounded control steps; no freestanding variable
             * divide helper and no work proportional to photo pixels. */
            uint32_t count = 1;
            while (count < 64u && (count + 1u) * pitch <= usable + gap) ++count;
            m10v_border_holes left;
            left.first.x = ((margin - hole_width) / 2u) & ~1u;
            left.first.y = ((result.outer.height - ((count - 1u) * pitch + hole_height)) / 2u) & ~1u;
            left.first.width = hole_width;
            left.first.height = hole_height;
            left.pitch = pitch;
            left.count = count;
            result.holes[0] = result.holes[1] = left;
            result.holes[1].first.x = result.outer.width - left.first.x - hole_width;
        }
    }
    *out = result;
    return 0;
}
