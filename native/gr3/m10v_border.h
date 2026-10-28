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
 * Inner pixels are never resized/cropped. Margins align to8 bytes for the
 * native JPEG source-address contract; hole coordinates align to2 for chroma.
 * This does NOT admit output to the encoder or reserve image storage.
 * Caller must separately prove output field limits, strides and ownership.
 * Return 0, or -1 without changing output on invalid input. */
int m10v_border_layout(uint32_t style, uint32_t width, uint32_t height,
                       m10v_border_layout_info *out);

typedef struct {
    m10v_border_rect first;
    int32_t dx, dy;
    uint32_t count;
} m10v_border_storage_holes;
typedef struct {
    uint32_t style, format;
    m10v_border_rect outer, inner;
    m10v_border_storage_holes holes[2];
    uint32_t stride, allocated_height, y_bytes, chroma_bytes, total_bytes;
} m10v_border_storage_info;

/* Plan the canvas in ORIGINAL STORED pixel order. EXIF1..8 stays unchanged;
 * only rectangles move, never image pixels. Format1=422, format2=420.
 * 64-byte pitch and 8-row allocation cover DMA/JPEG padding, which hardware
 * must fill as part of the canvas. Reject coordinates exceeding the verified
 * 14-bit Loader/Store encoding; this is not hardware capacity admission.
 * OFF returns exact storage geometry with zero allocation quantities.
 * No allocation, photo reads/writes, or hardware work occurs here. */
int m10v_border_storage_layout(uint32_t style, uint32_t width, uint32_t height,
                               uint32_t orientation, uint32_t format,
                               m10v_border_storage_info *out);

/* Pure secondary-size plan. Fit the COMPLETE canvas into an existing native
 * preview allocation's visible bounding box, without enlarging that box.
 * Dimensions are even; ratio rounding is less than one2-pixel step. The
 * hardware resize must consume the full source with zero crop ROI. This does
 * not change pitches, allocation rows, pointers or RAW. Returns-1 without
 * writing output if the box cannot contain at least2x2 chroma-aligned pixels.
 */
int m10v_border_preview_fit(uint32_t width,uint32_t height,
                            uint32_t bound_width,uint32_t bound_height,
                            m10v_border_rect *out);
#endif
