#include "m10v_half_pair.h"

static int dimensions(uint32_t w, uint32_t h) {
    return w && h && !(w & 1u) && !(h & 1u) && w <= 2992u && h <= 4000u;
}

int m10v_half_pair_plan(uint32_t w, uint32_t h, uint32_t orientation,
                       uint32_t capacity, m10v_half_pair_plan_info *out) {
    m10v_half_pair_plan_info p;
    for (uint32_t i=0;i<10u;i++) ((volatile uint32_t *)&p)[i]=0;
    if (!out || !dimensions(w,h)) return 0;
    if (orientation == 1u || orientation == 3u) {
        p.width = w * 2u; p.height = h;
        if (orientation == 1u) p.second_x = w;
        else p.first_x = w;
    } else if (orientation == 6u || orientation == 8u) {
        p.width = w; p.height = h * 2u;
        if (orientation == 6u) p.first_y = h;
        else p.second_y = h;
    } else return 0;
    /* Bounded dimensions above keep every product within uint32_t. */
    p.stride = (p.width + 63u) & ~63u;
    p.rows = (p.height + 15u) & ~15u;
    p.plane_bytes = p.stride * p.rows;
    p.used_bytes = p.plane_bytes * 2u;
    if (p.used_bytes > capacity) return 0;
    *out = p;
    return 1;
}

static int extent(const void *p, uint32_t size) {
    return p && (uintptr_t)p <= UINTPTR_MAX - size;
}
static int overlap(const void *a, uint32_t as, const void *b, uint32_t bs) {
    return (uintptr_t)a < (uintptr_t)b + bs && (uintptr_t)b < (uintptr_t)a + as;
}
static void place(uint8_t *dest, uint32_t stride, uint32_t x, uint32_t y,
                  const uint8_t *source, uint32_t w, uint32_t h) {
    for (uint32_t row=0; row<h; ++row) {
        uint8_t *out = dest + (row+y)*stride + x;
        const uint8_t *in = source + row*w;
        for (uint32_t col=0; col<w; ++col) out[col] = in[col];
    }
}

int m10v_half_pair_compose(const m10v_half_pair_plan_info *plan,
                          const uint8_t *first, const uint8_t *second,
                          uint8_t *dest, uint32_t capacity) {
    m10v_half_pair_plan_info p, expected;
    uint32_t w, h, orientation;
    if (!plan || !dest) return 0;
    /* Snapshot before writes: even a plan resident in dest remains safe. */
    p = *plan;
    if (!p.first_y && !p.second_y && !(p.width & 1u)) {
        w = p.width/2u; h = p.height;
        if (!p.first_x && p.second_x == w) orientation = 1u;
        else if (p.first_x == w && !p.second_x) orientation = 3u;
        else return 0;
    } else if (!p.first_x && !p.second_x && !(p.height & 1u)) {
        w = p.width; h = p.height/2u;
        if (p.first_y == h && !p.second_y) orientation = 6u;
        else if (!p.first_y && p.second_y == h) orientation = 8u;
        else return 0;
    } else return 0;
    if (!m10v_half_pair_plan(w,h,orientation,capacity,&expected)) return 0;
    if (p.width != expected.width || p.height != expected.height ||
        p.stride != expected.stride || p.rows != expected.rows ||
        p.plane_bytes != expected.plane_bytes || p.used_bytes != expected.used_bytes ||
        p.first_x != expected.first_x || p.first_y != expected.first_y ||
        p.second_x != expected.second_x || p.second_y != expected.second_y) return 0;
    uint32_t pixels = w*h, input_bytes = pixels*2u;
    if (((uintptr_t)dest & 63u) || !extent(first,input_bytes) ||
        !extent(second,input_bytes) || !extent(dest,p.used_bytes) ||
        overlap(first,input_bytes,second,input_bytes) ||
        overlap(first,input_bytes,dest,p.used_bytes) ||
        overlap(second,input_bytes,dest,p.used_bytes)) return 0;
    for (uint32_t i=0; i<p.plane_bytes; ++i) {
        dest[i] = 16u; dest[p.plane_bytes+i] = 128u;
    }
    place(dest,p.stride,p.first_x,p.first_y,first,w,h);
    place(dest,p.stride,p.second_x,p.second_y,second,w,h);
    place(dest+p.plane_bytes,p.stride,p.first_x,p.first_y,first+pixels,w,h);
    place(dest+p.plane_bytes,p.stride,p.second_x,p.second_y,second+pixels,w,h);
    return 1;
}
