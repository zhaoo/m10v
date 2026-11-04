#ifndef M10V_SPATIAL_ACCEL_H
#define M10V_SPATIAL_ACCEL_H
#include <stdint.h>

/* Exact energy_blur primitive, NOT an equivalent complete ISP effects graph.
 * Caller owns two disjoint uint16 planes for the entire call. No allocation,
 * DMA, cache maintenance, MMIO, persistent state or asynchronous work.
 * ARM entry uses NEON caller-saved d16-d25; caller must run in a context whose
 * NEON ownership is established. Never invoke it from an unproved interrupt.
 * capacity is the number of uint16 cells available in EACH plane.
 * Returns 0, or -1 before any write on invalid dimensions/capacity/alias.
 */
int m10v_spatial_blur_u16(uint16_t *a,uint16_t *b,uint32_t capacity,
    uint32_t width,uint32_t height,uint32_t passes,uint32_t distance);

/* Same synchronous NEON ownership as blur. Cell width is 8 or 16 and
 * starts on a chroma pair. A null chroma pointer selects luminance only.
 * A null peak pointer requests only the sum. */
uint32_t m10v_spatial_halo_cell(const uint8_t *y,const uint8_t *chroma,
    uint32_t stride,uint32_t width,uint32_t rows,uint32_t gate,uint32_t *peak);

/* Fill only the vectorizable interior of one original image row.
 * Return the first unwritten index, or 0 when the scalar path is needed. */
uint32_t m10v_spatial_halo_line(const uint8_t *y,const uint8_t *chroma,
    uint16_t *line,uint32_t width,uint32_t gate,uint32_t distance);

/* Official Granulation workspace protocol, independently executed against
 * locked GR III 2.10 bytes: align16(width)*height + alignment headroom.
 * Pure query only; never allocates. Address 0 queries an aligned buffer.
 * Returns 0 or -1 without changing *required on invalid input/overflow.
 */
int m10v_spatial_grain_work_bytes(uint32_t width,uint32_t height,
    uint32_t work_address,uint32_t *required);

/* Native-stock adapter for the original three-level grain.
 * Accepts ORIGINAL 32-byte native image descriptors, never m10v_library_image.
 * Caller must already own the native IIP context/task, descriptors, planes and
 * full workspace until stock returns; establish scheduler/NEON/cache ownership
 * and exclusion from RAW/preview before calling. The wrapper cannot establish
 * those lifetimes. No implicit malloc or image conversion is performed here.
 * Rejects insufficient/overlapping workspace before the stock call. Native
 * failure may follow partial output writes: -4 is NOT permission to apply a
 * CPU effect to that partially processed destination. Use original owner error
 * handling. Returns -3 on non-ARM hosts, -1 preflight error, 0 native success.
 */
int m10v_spatial_stock_grain_execute(uint32_t context,const void *source,
    const void *destination,uint32_t stock_strength,void *workspace,uint32_t workspace_bytes);

#endif
