#ifndef M10V_HALF_PAIR_IIP_H
#define M10V_HALF_PAIR_IIP_H
#include <stdint.h>
/* GR III2.10 checked native spatial backend. Caller authenticates allocation
 * ownership and protects RAW/recipe/control intervals before calling. Inputs
 * contain native 32-byte image descriptors, never pixel pointers retained by
 * this module. All image allocations and metadata remain owned through return.
 *
 * Installation of the enlarged border recovery workers/hooks and exclusion of
 * factory teardown are mandatory, including when decorative borders are Off.
 * A nonzero unique live recipe token serializes the complete private chain.
 * Return1 means the exact final native callback has returned, not a physical
 * image/pixel/performance assertion. Return0 rejects before any enqueue. Any
 * post-enqueue loss of completion retains caller/allocations rather than UAF.
 * This module never reads/writes photo bytes, applies color, computes a photo
 * CRC, or opens a file. Metadata copies/cache maintenance are scalar only.
 */
int m10v_half_pair_iip_ready(void);
int m10v_half_pair_iip_copy(uint32_t token,const uint32_t source[8],const uint32_t destination[8]);
int m10v_half_pair_iip_compose(uint32_t token,const uint32_t first[8],const uint32_t second[8],const uint32_t output[8],const uint32_t previews[2][8],uint32_t orientation);
#endif
