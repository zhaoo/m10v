#ifndef M10V_BORDER_H
#define M10V_BORDER_H
#include <stdint.h>

enum { M10V_BORDER_OFF = 0, M10V_BORDER_POLAROID = 1, M10V_BORDER_FILM = 2 };
typedef struct { uint32_t x, y, width, height; } m10v_border_rect;
typedef struct {
    m10v_border_rect first;
    uint32_t pitch, count;
} m10v_border_holes;
typedef struct {
    uint32_t style;
    m10v_border_rect outer, inner;
    m10v_border_holes holes[2];
} m10v_border_layout_info;

/* Pure, shared natural layout, with NO photo pointers or hardware calls.
 * Input dimensions are the actual crop in DISPLAY orientation, both even
 * and 2..65534 (native descriptor field range). Caller must transform back
 * using the shot's orientation before preparing hardware descriptors.
 * Inner pixels are never resized/cropped; 2-pixel geometry aligns chroma.
 * This does NOT admit output to the encoder or reserve image storage.
 * Caller must separately prove output field limits, strides and ownership.
 * Return 0, or -1 without changing output on invalid input. */
int m10v_border_layout(uint32_t style, uint32_t width, uint32_t height,
                       m10v_border_layout_info *out);
#endif
