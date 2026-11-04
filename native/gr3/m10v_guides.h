#ifndef M10V_GUIDES_H
#define M10V_GUIDES_H

#include <stdint.h>

enum {
    M10V_GUIDES_OFF = 0,
    M10V_GUIDES_GOLDEN_GRID,
    M10V_GUIDES_SPIRAL_TOP_LEFT,
    M10V_GUIDES_SPIRAL_TOP_RIGHT,
    M10V_GUIDES_SPIRAL_BOTTOM_LEFT,
    M10V_GUIDES_SPIRAL_BOTTOM_RIGHT,
    M10V_GUIDES_MODE_COUNT
};

typedef struct {
    uint32_t left, top, right, bottom;
} m10v_guides_rect;

typedef struct {
    volatile uint32_t *pixels;
    uint32_t capacity_pixels, stride_pixels, width, height;
    m10v_guides_rect photo, clip;
} m10v_guides_surface;

/* Rectangles are half-open and use canvas coordinates. Each pixel is one RGBA
 * word, red in the low byte. Spiral modes name the location of the tight end. */
void m10v_guides_draw(const m10v_guides_surface *surface, uint32_t mode, uint32_t rgba);

#endif
