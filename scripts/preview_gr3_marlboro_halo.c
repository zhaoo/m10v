/* Host-only bridge to main's exact 800T kernel, with no firmware changes. */
#include "m10v_library.h"
#include "m10v_isp_frame_color.h"
#include "halation_energy.h"

int preview_halo(uint8_t *y, uint8_t *uv, uint32_t w, uint32_t h,
                 uint32_t shift, uint8_t *scratch, uint32_t bytes) {
    uint32_t step = 1u << shift;
    uint32_t gw = (w + step - 1) >> shift, gh = (h + step - 1) >> shift;
    if (!y || !uv || !scratch || (w & 1u) || bytes < 6u * gw * gh) return -1;
    m10v_library_image image = {y, uv, w * h, w * h, w, h, w};
    m10v_slot choice = {.film = 33};
    m10v_slot_default_halation(&choice);
    m10v_800t_effects(&image, &choice, scratch, gw, gh, shift);
    return 0;
}
